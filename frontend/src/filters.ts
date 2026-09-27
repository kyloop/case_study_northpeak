// Column-filter rules for tables filtered in the browser (Cost Review, the upload report). Same rules as the
// server-side filters on the data tables (src/browse.py): plain text = contains (case-insensitive),
// "=x" exact, "!=x" not equal, ">n" ">=n" "<n" "<=n" numeric. On a numeric column a plain number, "=n" and
// "!=n" compare as numbers ("5" finds 5 and 5.0, not 25), and text that is not a number uses the text rules.

const NUMERIC_OPS = [">=", "<=", ">", "<"] as const;

/** True when the filter starts with a numeric operator but has no valid number after it. */
export function isInvalidFilter(expr: string): boolean {
  const e = expr.trim();
  const op = NUMERIC_OPS.find((o) => e.startsWith(o));
  if (!op) return false;
  const arg = e.slice(op.length).trim();
  return arg === "" || !Number.isFinite(Number(arg));
}

/**
 * Does a cell match a filter? `text` is what the user sees in the cell; `num` is its raw number
 * (or null for text columns), used by the numeric operators. An empty or invalid filter matches everything.
 */
export function matchesFilter(text: string, num: number | null, expr: string): boolean {
  const e = expr.trim();
  if (e === "" || isInvalidFilter(e)) return true;
  const lower = text.toLowerCase();
  if (num !== null) {
    // numeric column: compare what the cell shows, as a number (so 43.8 finds a cell displaying 43.8)
    const shown = text.trim() === "" ? NaN : Number(text);
    for (const [prefix, test] of [["!=", (n: number) => shown !== n], ["=", (n: number) => shown === n], ["", (n: number) => shown === n]] as const) {
      if (!e.startsWith(prefix)) continue;
      const arg = e.slice(prefix.length).trim();
      if (arg !== "" && Number.isFinite(Number(arg))) return test(Number(arg));
      break;
    }
  }
  if (e.startsWith("!=")) return lower !== e.slice(2).trim().toLowerCase();
  if (e.startsWith("=")) return lower === e.slice(1).trim().toLowerCase();
  const op = NUMERIC_OPS.find((o) => e.startsWith(o));
  if (op) {
    if (num === null) return false;
    const n = Number(e.slice(op.length).trim());
    return op === ">=" ? num >= n : op === "<=" ? num <= n : op === ">" ? num > n : num < n;
  }
  return lower.includes(e.toLowerCase());
}

export const FILTER_HELP =
  "Column filters combine (all must match). Text columns: plain text = contains; =text exact; !=text not equal. Number columns: 5 = exactly 5; !=5 not 5; >5 >=5 <5 <=5.";
