"""Optional one-line risk note per supplier, from facilities.csv and risk_events.csv."""
from __future__ import annotations

from collections import defaultdict

ACTIVE = ("open", "monitoring")


def supplier_risk_notes(conn) -> dict:
    """Return {supplier_id: note}."""
    notes = {}

    events = defaultdict(list)
    for r in conn.execute(
        """SELECT f.supplier_id, e.event_type, e.severity, e.status
           FROM risk_events e JOIN facilities f USING (facility_id)"""):
        events[r["supplier_id"]].append(r)

    # "Only supplier for this part": no other supplier has ever submitted a cost for it.
    sole_parts = defaultdict(list)
    for r in conn.execute(
        """SELECT MIN(s.supplier_id) supplier_id, p.part_number
           FROM cost_submissions s JOIN parts p USING (part_id)
           GROUP BY p.part_id HAVING COUNT(DISTINCT s.supplier_id) = 1
           ORDER BY p.part_number"""):
        sole_parts[r["supplier_id"]].append(r["part_number"])

    for s in conn.execute("SELECT supplier_id FROM suppliers"):
        sid = s["supplier_id"]
        evs = events.get(sid, [])
        open_ = [e for e in evs if e["status"] == "open"]
        monitoring = [e for e in evs if e["status"] == "monitoring"]
        bits = []
        if open_:
            sev = max(e["severity"] or 0 for e in open_)
            bits.append(f"{len(open_)} open risk event{'s' if len(open_) != 1 else ''} (max severity {sev})")
        if monitoring:
            bits.append(f"{len(monitoring)} being monitored")
        if any(e["event_type"] == "single_source_dependency" and e["status"] in ACTIVE for e in evs):
            bits.append("flagged as sole qualified source")
        sp = sole_parts.get(sid, [])
        if sp:
            shown = ", ".join(sp[:3]) + (f" +{len(sp) - 3} more" if len(sp) > 3 else "")
            bits.append(f"only supplier for {shown}")
        notes[sid] = "; ".join(bits) if bits else "No open risk events"
    return notes
