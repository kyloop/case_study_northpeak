"""Rough should-cost estimates, stored in their own table (never in cost_submissions)."""
from __future__ import annotations

from . import db


def recompute(conn) -> int:
    """Rebuild should_cost_estimates from approved submissions. Returns rows written.

    The estimate for every part is the mean approved unit cost of its commodity. Commodities
    with no approved submissions get no estimate (their submissions can't be flagged). Only reads
    cost_submissions; only writes should_cost_estimates.
    """
    commodity_stats = {r["commodity"]: (r["n"], r["avg"]) for r in conn.execute(
        """SELECT p.commodity, COUNT(*) n, AVG(s.submitted_unit_cost) avg
           FROM cost_submissions s JOIN parts p USING (part_id)
           WHERE s.status = 'approved' GROUP BY p.commodity""")}

    now = db.now_iso()
    rows = []
    for p in conn.execute("SELECT part_id, commodity FROM parts"):
        if p["commodity"] in commodity_stats:
            n, avg = commodity_stats[p["commodity"]]
            rows.append((p["part_id"], p["commodity"], round(avg, 4), n, now))

    conn.execute("DELETE FROM should_cost_estimates")
    conn.executemany("INSERT INTO should_cost_estimates VALUES (?,?,?,?,?)", rows)
    conn.commit()
    return len(rows)
