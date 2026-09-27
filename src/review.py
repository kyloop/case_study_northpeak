"""Cost review: flag submissions well above should-cost; record approve/reject decisions."""
from __future__ import annotations

from . import config, db

ACTIONS = {"approve": "approved", "reject": "rejected"}

_BASE = """
SELECT s.submission_id, s.fiscal_period, s.submitted_unit_cost, s.status, s.submitted_by,
       s.submitted_at, s.source_file, s.supplier_id,
       p.part_number, p.commodity, sup.name AS supplier_name,
       e.should_cost, e.sample_size,
       (s.submitted_unit_cost / e.should_cost - 1) * 100 AS pct_over
FROM cost_submissions s
JOIN parts p USING (part_id)
JOIN suppliers sup USING (supplier_id)
JOIN should_cost_estimates e USING (part_id)
"""


class ReviewError(ValueError):
    pass


def flagged(conn, threshold_pct: float = None):
    """Pending submissions more than threshold_pct over their should-cost, worst first.

    This is the review queue: rows that have been approved or rejected are not listed.
    """
    threshold = config.FLAG_THRESHOLD_PCT if threshold_pct is None else threshold_pct
    sql = (_BASE + " WHERE s.status = 'pending' AND (s.submitted_unit_cost / e.should_cost - 1) * 100 > ?"
           " ORDER BY pct_over DESC")
    return conn.execute(sql, [threshold]).fetchall()


def decide(conn, submission_id: int, action: str, actor: str, reason: str = "") -> dict:
    """Approve or reject a submission. Status change + audit row commit together."""
    actor, reason = (actor or "").strip(), (reason or "").strip()
    if action not in ACTIONS:
        raise ReviewError(f"Unknown action '{action}'.")
    if not actor:
        raise ReviewError("Enter your name before approving or rejecting.")
    if action == "reject" and not reason:
        raise ReviewError("A reason is required when rejecting a submission.")

    row = conn.execute(_BASE.replace("JOIN should_cost_estimates", "LEFT JOIN should_cost_estimates")
                       + " WHERE s.submission_id = ?", (submission_id,)).fetchone()
    if row is None:
        raise ReviewError(f"Submission {submission_id} does not exist.")

    after = ACTIONS[action]
    try:
        conn.execute("UPDATE cost_submissions SET status = ? WHERE submission_id = ?", (after, submission_id))
        conn.execute(
            """INSERT INTO audit_log (submission_id, action, actor, acted_at, before_status, after_status,
                                      reason, submitted_unit_cost, should_cost, pct_over_should_cost)
               VALUES (?,?,?,?,?,?,?,?,?,?)""",
            (submission_id, action, actor, db.now_iso(), row["status"], after, reason or None,
             row["submitted_unit_cost"], row["should_cost"],
             None if row["pct_over"] is None else round(row["pct_over"], 2)))
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return {"submission_id": submission_id, "before": row["status"], "after": after}
