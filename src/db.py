"""SQLite connection, schema creation, and loading of the provided dummy data."""
from __future__ import annotations

import csv
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from . import config


def now_iso() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def connect(path=None, check_same_thread: bool = True) -> sqlite3.Connection:
    conn = sqlite3.connect(str(path or config.DB_PATH), check_same_thread=check_same_thread)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def find_duplicate(conn, v: dict):
    """Return the submission_id of an existing row with identical content, else None.

    Same test as the uq_sub_content unique index: every value column must match.
    """
    row = conn.execute(
        """SELECT submission_id FROM cost_submissions
           WHERE part_id = ? AND supplier_id = ? AND fiscal_period = ? AND submitted_unit_cost = ?
             AND material_cost = ? AND labor_cost = ? AND overhead_cost = ? AND margin_pct = ?
             AND currency = ? AND submitted_by = ? COLLATE NOCASE""",
        (v["part_id"], v["supplier_id"], v["fiscal_period"], v["submitted_unit_cost"],
         v["material_cost"], v["labor_cost"], v["overhead_cost"], v["margin_pct"],
         v["currency"], v["submitted_by"].strip())).fetchone()
    return row["submission_id"] if row else None


def insert_submission(conn, v: dict, *, source_file: str, submitted_at: str,
                      status: str = "pending", submission_id=None) -> int:
    cur = conn.execute(
        """INSERT INTO cost_submissions
           (submission_id, part_id, supplier_id, fiscal_period, submitted_unit_cost,
            material_cost, labor_cost, overhead_cost, margin_pct, currency, submitted_by,
            submitted_at, status, source_file)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (submission_id, v["part_id"], v["supplier_id"], v["fiscal_period"],
         v["submitted_unit_cost"], v["material_cost"], v["labor_cost"], v["overhead_cost"],
         v["margin_pct"], v["currency"], v["submitted_by"].strip(), submitted_at,
         status, source_file))
    return cur.lastrowid


SEED_SOURCE = "historical_seed.csv"  # source_file of the provided historical submissions


def _migrate_cost_submissions(conn) -> None:
    """One-off upgrade of a database whose cost_submissions still has `row_hash` or `uploaded_at`.

    Both columns were dropped (duplicates are now caught by the uq_sub_content index, and the upload
    time lives in `submitted_at` and in the `uploads` table). Keeps every row and its submission_id, so
    audit_log links stay valid. Rows from an upload that had an `uploaded_at` get it back as `submitted_at`;
    seed rows keep their own submission date.
    """
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(cost_submissions)")]
    if not cols or not {"row_hash", "uploaded_at"} & set(cols):
        return
    old = [dict(r) for r in conn.execute("SELECT * FROM cost_submissions")]
    conn.execute("PRAGMA foreign_keys = OFF")
    conn.execute("DROP TABLE cost_submissions")  # its indexes go with it
    init_schema(conn)
    for r in old:
        submitted_at = r["submitted_at"]
        if r.get("uploaded_at") and r["source_file"] != SEED_SOURCE:
            submitted_at = r["uploaded_at"]
        insert_submission(conn, r, source_file=r["source_file"], submitted_at=submitted_at,
                          status=r["status"], submission_id=r["submission_id"])
    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")


def _migrate_should_cost(conn) -> bool:
    """Upgrade a database whose should_cost_estimates still has the old `method` column.

    The table is derived data, so it is dropped and rebuilt by the caller. Returns True if it was dropped.
    """
    cols = [r["name"] for r in conn.execute("PRAGMA table_info(should_cost_estimates)")]
    if "method" not in cols:
        return False
    conn.execute("DROP TABLE should_cost_estimates")
    conn.commit()
    return True


def init_schema(conn) -> None:
    conn.executescript(config.SCHEMA_PATH.read_text())


def _read(name: str):
    with open(config.DATA_DIR / name, newline="", encoding="utf-8-sig") as f:
        return list(csv.DictReader(f))


def _insert_many(conn, table: str, cols: list, rows: list) -> None:
    conn.executemany(
        f"INSERT INTO {table} ({','.join(cols)}) VALUES ({','.join('?' * len(cols))})",
        [[r[c] if r[c] != "" else None for c in cols] for r in rows],
    )


def seed(conn) -> None:
    """Load the provided master data and the 250 historical submissions."""
    for table, cols in [
        ("suppliers", ["supplier_id", "name", "region", "tier", "risk_rating", "created_at"]),
        ("facilities", ["facility_id", "supplier_id", "name", "country", "latitude",
                        "longitude", "facility_type"]),
        ("parts", ["part_id", "part_number", "description", "commodity", "uom", "target_cost"]),
        ("risk_events", ["event_id", "facility_id", "event_type", "severity", "event_date",
                         "description", "status"]),
    ]:
        _insert_many(conn, table, cols, _read(f"{table}.csv"))

    for r in _read("cost_submissions.csv"):
        v = {k: r[k] for k in ("fiscal_period", "currency", "submitted_by")}
        v.update({k: int(r[k]) for k in ("part_id", "supplier_id")})
        v.update({k: float(r[k]) for k in ("submitted_unit_cost", "material_cost", "labor_cost",
                                            "overhead_cost", "margin_pct")})
        insert_submission(conn, v, source_file=r["source_file"], submitted_at=r["submitted_at"],
                          status=r["status"], submission_id=int(r["submission_id"]))
    conn.commit()


def init_db(path=None, *, reset: bool = False, seed_data: bool = True) -> sqlite3.Connection:
    """Create the DB if needed, and seed it only when it is brand new. Safe to call repeatedly.

    An existing database is never re-seeded, even if its tables were emptied on purpose.
    `seed_data=False` creates an empty database (schema only).
    """
    path = Path(path or config.DB_PATH)
    if reset and path.exists():
        path.unlink()
    conn = connect(path)
    is_new = conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name='suppliers'").fetchone() is None
    _migrate_cost_submissions(conn)
    rebuild_estimates = _migrate_should_cost(conn)
    init_schema(conn)
    if is_new and seed_data:
        from . import shouldcost
        seed(conn)
        shouldcost.recompute(conn)
    elif rebuild_estimates:
        from . import shouldcost
        shouldcost.recompute(conn)
    return conn
