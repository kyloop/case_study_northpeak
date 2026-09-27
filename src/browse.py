"""Read-only table browsing: column filters, and links between tables for the two-pane data view."""
from __future__ import annotations

from collections import deque
from typing import List, Optional

TABLES = ["suppliers", "facilities", "parts", "cost_submissions", "should_cost_estimates",
          "risk_events", "audit_log", "uploads"]

# How the tables relate: (table, column) = (table, column). Used in both directions, and chained,
# so e.g. suppliers -> risk_events is found via facilities. Keep in step with schema.sql.
EDGES = [
    (("suppliers", "supplier_id"), ("facilities", "supplier_id")),
    (("suppliers", "supplier_id"), ("cost_submissions", "supplier_id")),
    (("parts", "part_id"), ("cost_submissions", "part_id")),
    (("parts", "part_id"), ("should_cost_estimates", "part_id")),
    (("facilities", "facility_id"), ("risk_events", "facility_id")),
    (("cost_submissions", "submission_id"), ("audit_log", "submission_id")),
    (("uploads", "filename"), ("cost_submissions", "source_file")),
]

# Longest chain of relations followed. Beyond two steps almost everything relates to everything,
# which stops being informative (e.g. parts -> risk_events would go through four tables).
MAX_HOPS = 2

NUMERIC_OPS = {">=": ">=", "<=": "<=", ">": ">", "<": "<"}


class BrowseError(ValueError):
    """A bad table, column or filter from the caller (becomes HTTP 400)."""


def like(value: str) -> str:
    """LIKE pattern for 'contains', with the user's own % and _ taken literally."""
    return "%" + value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"


def _number(text: str):
    try:
        return float(text.strip())
    except ValueError:
        return None


def column_filter(col: str, raw: str, numeric: bool = False):
    """Turn one column filter into (sql, args). `col` must already be whitelisted.

    plain text  -> contains (case-insensitive)
    =text / !=text -> exact match / not equal (case-insensitive)
    >n >=n <n <=n  -> numeric comparison
    On a numeric column (INTEGER/REAL) a plain number, =n and !=n compare as numbers, so `5` finds
    5 and 5.0 but not 25 or 5.5; text that is not a number falls back to the text rules.
    """
    raw = raw.strip()
    if numeric:
        for prefix, op in (("!=", "<>"), ("=", "="), ("", "=")):
            if raw.startswith(prefix):
                n = _number(raw[len(prefix):])
                if n is not None:
                    return f"CAST({col} AS REAL) {op} ?", [n]
                break  # not a number: use the text rules below
    if raw.startswith("!="):
        return f"CAST({col} AS TEXT) <> ? COLLATE NOCASE", [raw[2:].strip()]
    if raw.startswith("="):
        return f"CAST({col} AS TEXT) = ? COLLATE NOCASE", [raw[1:].strip()]
    for op in (">=", "<=", ">", "<"):
        if raw.startswith(op):
            try:
                n = float(raw[len(op):].strip())
            except ValueError:
                raise BrowseError(f"Filter on {col}: '{raw}' needs a number after {op}")
            return f"CAST({col} AS REAL) {NUMERIC_OPS[op]} ?", [n]
    return f"CAST({col} AS TEXT) LIKE ? ESCAPE '\\'", [like(raw)]


def table_columns(conn, table: str) -> List[str]:
    if table not in TABLES:  # whitelist: table is interpolated into SQL
        raise BrowseError(f"Unknown table '{table}'")
    cols = [r["name"] for r in conn.execute(f"PRAGMA table_info({table})")]
    return [c for c in cols if not (table == "uploads" and c == "report_json")]


def numeric_columns(conn, table: str) -> set:
    """Names of the table's INTEGER / REAL columns."""
    table_columns(conn, table)  # validates `table`
    return {r["name"] for r in conn.execute(f"PRAGMA table_info({table})") if r["type"].upper() in ("INTEGER", "REAL")}


def build_where(conn, table: str, q: str, f: List[str]):
    """Return (clauses, args, applied_filters) for the global search plus column filters (ANDed)."""
    cols = table_columns(conn, table)
    numeric = numeric_columns(conn, table)
    clauses, args, applied = [], [], []
    q = q.strip()
    if q:
        clauses.append("(" + " OR ".join(f"CAST({c} AS TEXT) LIKE ? ESCAPE '\\'" for c in cols) + ")")
        args += [like(q)] * len(cols)
    for item in f:
        col, _, value = item.partition(":")
        if col not in cols:  # whitelist: col is interpolated into SQL
            raise BrowseError(f"Cannot filter on unknown column '{col}'")
        if value.strip():
            sql, a = column_filter(col, value, numeric=col in numeric)
            clauses.append(sql)
            args += a
            applied.append({"column": col, "value": value.strip()})
    return clauses, args, applied


def find_path(src: str, dst: str) -> Optional[list]:
    """Shortest chain (at most MAX_HOPS) of relations from src to dst, as [(from_tbl, from_col, to_tbl, to_col), ...]."""
    if src == dst:
        return None
    graph = {}
    for (ta, ca), (tb, cb) in EDGES:
        graph.setdefault(ta, []).append((ta, ca, tb, cb))
        graph.setdefault(tb, []).append((tb, cb, ta, ca))
    queue, seen = deque([(src, [])]), {src}
    while queue:
        table, path = queue.popleft()
        for edge in graph.get(table, []):
            if edge[2] in seen:
                continue
            new = path + [edge]
            if len(new) > MAX_HOPS:
                continue
            if edge[2] == dst:
                return new
            seen.add(edge[2])
            queue.append((edge[2], new))
    return None


def link_clause(conn, bottom: str, top: str, top_q: str, top_f: List[str]):
    """Restrict `bottom` to rows related to the rows of `top` that match top's search/filters.

    Returns (clause, args, info). If the tables are not related, clause is None and info explains.
    """
    table_columns(conn, top)  # validates `top`
    path = find_path(top, bottom)
    if path is None:
        why = "same table" if top == bottom else f"no relation between {top} and {bottom}"
        return None, [], {"path": None, "note": f"Not linked: {why}."}
    clauses, args, _ = build_where(conn, top, top_q, top_f)
    sql = f"SELECT {path[0][1]} FROM {top}" + (" WHERE " + " AND ".join(clauses) if clauses else "")
    for i, (_a_tbl, _a_col, b_tbl, b_col) in enumerate(path[:-1]):
        sql = f"SELECT {path[i + 1][1]} FROM {b_tbl} WHERE {b_col} IN ({sql})"
    clause = f"{path[-1][3]} IN ({sql})"
    return clause, args, {"path": [path[0][0]] + [e[2] for e in path], "note": None}
