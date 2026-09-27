import sqlite3

import pytest

from src import config, ingest, review, risk, shouldcost


def test_should_cost_is_separate_and_does_not_touch_submissions(conn):
    """Calculating the should-cost estimates leaves every submitted row exactly as it was.

    Compares the whole cost_submissions table before and after a recompute, and checks that 45
    estimate rows (one per part) were written to their own table.

    Why: the brief says submitted costs and calculated estimates must live in separate tables and one
    must never overwrite the other.
    """
    before = conn.execute("SELECT * FROM cost_submissions ORDER BY submission_id").fetchall()
    n = shouldcost.recompute(conn)
    after = conn.execute("SELECT * FROM cost_submissions ORDER BY submission_id").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]
    assert n == conn.execute("SELECT COUNT(*) FROM should_cost_estimates").fetchone()[0] == 45


def test_should_cost_is_the_commodity_average_of_approved_submissions(conn):
    """Every part's should-cost is the average approved unit cost of its commodity.

    For each commodity, recomputes the mean of its approved submissions and checks that all of that
    commodity's parts carry that one number, along with how many submissions it is based on.

    Why: this is the should-cost rule the brief asks for (an average per commodity type), so the
    calculation itself needs a check, not only the fact that estimates exist.
    """
    est = conn.execute("SELECT e.part_id, p.commodity, e.commodity AS e_commodity, e.should_cost, e.sample_size "
                       "FROM should_cost_estimates e JOIN parts p USING (part_id)").fetchall()
    assert len(est) == 45 and all(r["commodity"] == r["e_commodity"] for r in est)
    for commodity in {r["commodity"] for r in est}:
        n, avg = conn.execute("SELECT COUNT(*), AVG(s.submitted_unit_cost) FROM cost_submissions s JOIN parts p USING (part_id) "
                              "WHERE s.status = 'approved' AND p.commodity = ?", (commodity,)).fetchone()
        same = [r for r in est if r["commodity"] == commodity]
        assert all(r["sample_size"] == n and abs(r["should_cost"] - avg) < 1e-3 for r in same)  # one number per commodity


def test_pending_and_rejected_submissions_do_not_change_the_estimate(conn):
    """Only approved submissions feed the estimate: multiplying the costs of pending and rejected rows by
    10 changes no should-cost.

    Why: pending rows are unvetted and rejected rows are known to be wrong. If they counted, a
    suspiciously high price would raise the very estimate it is being compared with.
    """
    before = conn.execute("SELECT part_id, should_cost FROM should_cost_estimates ORDER BY part_id").fetchall()
    conn.execute("UPDATE cost_submissions SET submitted_unit_cost = submitted_unit_cost * 10 WHERE status != 'approved'")
    shouldcost.recompute(conn)
    after = conn.execute("SELECT part_id, should_cost FROM should_cost_estimates ORDER BY part_id").fetchall()
    assert [tuple(r) for r in before] == [tuple(r) for r in after]


def test_commodity_without_approved_history_gets_no_estimate(conn):
    """A commodity with no approved submissions gets no estimate; the other commodities are unaffected.

    Sets every Connector submission to pending, so the 8 Connector parts lose their estimate and the
    other 37 keep theirs.

    Why: with nothing to average there is no honest number to compare against. This pins down that
    behaviour so it is a decision, not an accident: such submissions cannot be flagged.
    """
    conn.execute("UPDATE cost_submissions SET status = 'pending' WHERE part_id IN (SELECT part_id FROM parts WHERE commodity = 'Connector')")
    shouldcost.recompute(conn)
    assert conn.execute("SELECT COUNT(*) FROM should_cost_estimates WHERE commodity = 'Connector'").fetchone()[0] == 0
    assert conn.execute("SELECT COUNT(*) FROM should_cost_estimates").fetchone()[0] == 45 - 8


def test_flagged_rows_are_all_above_threshold_and_pending(conn):
    """The review queue holds only pending submissions above the flag threshold, worst first.

    Also checks that a stricter threshold gives a shorter list.

    Why: the brief says to flag anything "a lot higher" than the should-cost and show those rows for
    review. This checks who is in the queue and in what order.
    """
    rows = review.flagged(conn)
    assert rows and all(r["status"] == "pending" and r["pct_over"] > config.FLAG_THRESHOLD_PCT for r in rows)
    assert [r["pct_over"] for r in rows] == sorted((r["pct_over"] for r in rows), reverse=True)
    # a stricter threshold flags fewer
    assert len(review.flagged(conn, threshold_pct=50)) < len(rows)


def test_decision_is_logged_with_before_and_after(conn):
    """Approving a row updates its status and writes one audit entry with the full record.

    The entry has who, when, the action, the status before and after, the cost and should-cost at that
    moment and the percentage over. Once decided, the row leaves the review queue.

    Why: the brief asks to log every approve or reject (who, when, before and after) rather than
    only updating the row in place.
    """
    sid = review.flagged(conn)[0]["submission_id"]
    review.decide(conn, sid, "approve", "Kevin", "ok for launch")
    row = conn.execute("SELECT * FROM audit_log").fetchone()
    assert (row["submission_id"], row["actor"], row["action"]) == (sid, "Kevin", "approve")
    assert (row["before_status"], row["after_status"]) == ("pending", "approved")
    assert row["acted_at"] and row["should_cost"] and row["pct_over_should_cost"] > config.FLAG_THRESHOLD_PCT
    assert conn.execute("SELECT status FROM cost_submissions WHERE submission_id=?", (sid,)).fetchone()[0] == "approved"
    assert sid not in [r["submission_id"] for r in review.flagged(conn)]


def test_repeated_decisions_append_rows(conn):
    """Approving and then rejecting the same row leaves two audit entries, not one overwritten.

    The second entry starts from "approved", showing the first decision really happened.

    Why: the log has to be a history. A changed mind must add to it and never rewrite it.
    """
    sid = review.flagged(conn)[0]["submission_id"]
    review.decide(conn, sid, "approve", "Kevin")
    review.decide(conn, sid, "reject", "Dana", "quote was stale")
    rows = conn.execute("SELECT actor, before_status, after_status FROM audit_log ORDER BY audit_id").fetchall()
    assert [tuple(r) for r in rows] == [("Kevin", "pending", "approved"), ("Dana", "approved", "rejected")]


def test_audit_log_is_append_only(conn):
    """The database itself refuses to update or delete an audit entry.

    Why: an audit trail is only trustworthy if entries cannot be changed afterwards, even by a bug or
    a hand-typed query. The rule lives in database triggers, so this test tries to break it directly.
    """
    review.decide(conn, review.flagged(conn)[0]["submission_id"], "approve", "Kevin")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("UPDATE audit_log SET actor = 'someone else'")
    with pytest.raises(sqlite3.DatabaseError, match="append-only"):
        conn.execute("DELETE FROM audit_log")


@pytest.mark.parametrize("action,actor,reason,msg", [
    ("approve", "", "", "name"),
    ("reject", "Kevin", "", "reason"),
    ("delete", "Kevin", "x", "Unknown action"),
])
def test_invalid_decisions_change_nothing(conn, action, actor, reason, msg):
    """A refused decision leaves no trace: no audit entry and the status is unchanged.

    The three cases: no name given, a reject without a reason, and an unknown action.

    Why: every decision must be attributable, and a rejection must say why. A half-accepted decision
    would put an entry in the audit log that should never have been there.
    """
    sid = review.flagged(conn)[0]["submission_id"]
    with pytest.raises(review.ReviewError, match=msg):
        review.decide(conn, sid, action, actor, reason)
    assert conn.execute("SELECT COUNT(*) FROM audit_log").fetchone()[0] == 0
    assert conn.execute("SELECT status FROM cost_submissions WHERE submission_id=?", (sid,)).fetchone()[0] == "pending"


def test_unknown_submission(conn):
    """Deciding on a submission id that does not exist gives a clear error.

    Why: the API takes the id from the caller, so it must not fail obscurely or write an audit entry
    for a row that is not there.
    """
    with pytest.raises(review.ReviewError, match="does not exist"):
        review.decide(conn, 99999, "approve", "Kevin")


def test_uploaded_expensive_row_shows_up_for_review(conn):
    """End to end: an uploaded row priced at twice its should-cost is saved as pending and appears in the
    review queue.

    Why: this joins the two halves of the brief (the upload pipeline and the cost review) and shows a
    new upload really reaches the reviewer.
    """
    part = conn.execute("SELECT part_number, should_cost FROM should_cost_estimates JOIN parts USING (part_id) LIMIT 1").fetchone()
    cost = round(part["should_cost"] * 2, 3)
    csv = ("part_number,supplier_name,fiscal_period,submitted_unit_cost,material_cost,labor_cost,overhead_cost,margin_pct,currency,submitted_by\n"
           f"{part['part_number']},Cascade Technologies,FY26-Q4,{cost},{cost/2},{cost/4},{cost/4},5,USD,a@b.example\n")
    rep = ingest.process_upload(conn, "hi.csv", csv.encode())
    assert rep["summary"]["saved"] == 1
    assert rep["rows"][0]["submission_id"] in [r["submission_id"] for r in review.flagged(conn)]


def test_risk_notes_cover_every_supplier(conn):
    """Every one of the 20 suppliers gets a one-line risk note, and both kinds of note appear.

    Checks that some notes mention an open risk event and some say "only supplier for" a part.

    Why: this is the optional risk-note feature in the brief; it makes sure no supplier is left blank
    and that the facilities and risk-event data actually feed the notes.
    """
    notes = risk.supplier_risk_notes(conn)
    assert len(notes) == 20 and all(notes.values())
    assert any("open risk event" in n for n in notes.values())
    assert any("only supplier for" in n for n in notes.values())


def test_review_queue_lists_only_pending_rows_even_though_approved_ones_can_be_over_threshold(conn):
    """The seed data has approved and rejected rows above the threshold; the queue leaves them out and
    lists every pending row above it.

    Why: only undecided submissions need a decision, and the seed statuses were assigned at random, so
    decided rows above the line are normal. This guards against approved rows creeping into the queue.
    """
    over = conn.execute("""SELECT s.status, COUNT(*) FROM cost_submissions s JOIN should_cost_estimates e USING (part_id)
                           WHERE (s.submitted_unit_cost / e.should_cost - 1) * 100 > ? GROUP BY s.status""",
                        (config.FLAG_THRESHOLD_PCT,)).fetchall()
    assert {r[0] for r in over} == {"pending", "approved", "rejected"}     # seed data has decided rows above the line
    queue = review.flagged(conn)
    assert queue and all(r["status"] == "pending" for r in queue)
    assert len(queue) == {r[0]: r[1] for r in over}["pending"]   # and every pending one above it is listed
