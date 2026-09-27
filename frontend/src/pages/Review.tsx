import { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useActor } from "../actor";
import { useDataView } from "../dataview";
import { FILTER_HELP } from "../filters";
import { FilterRow, FilterSummary, SortHeaderRow, useTableView, type Column } from "../tableview";
import type { ReviewResponse, ReviewRow } from "../types";

// The filterable columns, in display order. `text` is what the cell shows (used by contains / = / !=);
// `num` is the raw number for > >= < <=.
const COLUMNS: Column<ReviewRow>[] = [
  { key: "submission_id", text: (r) => String(r.submission_id), num: (r) => r.submission_id },
  { key: "part_number", text: (r) => r.part_number },
  { key: "commodity", text: (r) => r.commodity },
  { key: "supplier_name", text: (r) => r.supplier_name },
  { key: "fiscal_period", text: (r) => r.fiscal_period },
  { key: "submitted_unit_cost", right: true, text: (r) => r.submitted_unit_cost.toFixed(3), num: (r) => r.submitted_unit_cost },
  { key: "should_cost", right: true, text: (r) => r.should_cost.toFixed(3), num: (r) => r.should_cost },
  { key: "pct_over", right: true, text: (r) => r.pct_over.toFixed(1), num: (r) => r.pct_over },
  { key: "status", text: (r) => r.status },
  { key: "risk_note", text: (r) => r.risk_note },
];

export default function Review() {
  const { actor } = useActor();
  const { bump, showTable } = useDataView();
  const [data, setData] = useState<ReviewResponse | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [reasons, setReasons] = useState<Record<number, string>>({});
  const view = useTableView(data?.rows ?? [], COLUMNS, { key: "pct_over", dir: "desc" }); // worst first
  const rows = view.rows;

  const load = useCallback(async () => {
    try {
      setData(await api.review());
    } catch (e) {
      setError((e as Error).message);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  async function decide(id: number, action: "approve" | "reject") {
    setError(null);
    setNotice(null);
    try {
      const res = await api.decide(id, action, actor, reasons[id] ?? "");
      setNotice(`Submission ${id}: ${res.before} → ${res.after} (logged).`);
      setReasons((r) => ({ ...r, [id]: "" }));
      bump();
      showTable("audit_log", "audit_id", "desc"); // in split view, show the log row just written
      await load();
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <>
      <h1>Cost review</h1>
      <p className="sub">
        Pending submissions more than {data?.threshold_pct ?? 20}% above their should-cost estimate. Should-cost =
        average approved unit cost for the part's commodity. A decided row leaves this list; every decision is
        appended to the audit log.
      </p>
      <p>
        <FilterSummary view={view} total={data?.rows.length ?? 0} noun="pending and flagged" />
      </p>
      {!actor && (
        <div className="flash error">
          Enter your name (top right) before approving or rejecting so the decision can be attributed.
        </div>
      )}
      {notice && <div className="flash ok" role="status">{notice}</div>}
      {error && <div className="flash error" role="alert">{error}</div>}
      <div className="wrap">
        <table>
          <thead>
            <SortHeaderRow columns={COLUMNS} view={view}>
              <th>decision</th>
            </SortHeaderRow>
            <FilterRow columns={COLUMNS} view={view}>
              <th />
            </FilterRow>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.submission_id}>
                <td className="num">{r.submission_id}</td>
                <td>{r.part_number}</td>
                <td>{r.commodity}</td>
                <td>{r.supplier_name}</td>
                <td>{r.fiscal_period}</td>
                <td className="num">{r.submitted_unit_cost.toFixed(3)}</td>
                <td className="num">
                  {r.should_cost.toFixed(3)}
                  <div className="muted small">commodity avg, n={r.sample_size}</div>
                </td>
                <td className="num"><b>+{r.pct_over.toFixed(1)}%</b></td>
                <td><span className={`badge ${r.status}`}>{r.status}</span></td>
                <td>{r.risk_note}</td>
                <td>
                  <div className="rowform">
                    <input
                      aria-label={`Reason for submission ${r.submission_id}`}
                      placeholder="reason (required to reject)"
                      value={reasons[r.submission_id] ?? ""}
                      onChange={(e) => setReasons((x) => ({ ...x, [r.submission_id]: e.target.value }))}
                    />
                    <button className="approve" disabled={!actor} onClick={() => decide(r.submission_id, "approve")}>Approve</button>
                    <button className="reject" disabled={!actor} onClick={() => decide(r.submission_id, "reject")}>Reject</button>
                  </div>
                </td>
              </tr>
            ))}
            {data && rows.length === 0 && (
              <tr>
                <td colSpan={COLUMNS.length + 1} className="muted">
                  {data.rows.length > 0 ? "No rows match the column filters." : "Nothing pending is flagged."}
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="muted small">{FILTER_HELP}</p>
      <p className="sub">
        See the <Link to="/data/audit_log?sort=audit_id&dir=desc">audit log</Link>.
      </p>
    </>
  );
}
