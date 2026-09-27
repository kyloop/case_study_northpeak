import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import { api } from "../api";
import { useActor } from "../actor";
import { useDataView } from "../dataview";
import { FILTER_HELP } from "../filters";
import { FilterRow, FilterSummary, SortHeaderRow, useTableView, type Column } from "../tableview";
import { UPLOAD_COLUMNS, type ReportRow, type UploadReport } from "../types";

const LABEL = { saved: "saved", duplicate: "already on file", failed: "failed" } as const;

const NUMERIC_UPLOAD_COLUMNS: readonly string[] = ["submitted_unit_cost", "material_cost", "labor_cost", "overhead_cost", "margin_pct"];

/** What the details cell says, as plain text (also what the details filter searches). */
function detailsText(r: ReportRow): string {
  const fields = [...new Set(r.errors.map((e) => e.field))].join(", ");
  return [
    r.errors.length > 0 ? `${r.errors.length} problem${r.errors.length === 1 ? "" : "s"}: ${fields}` : "",
    ...r.errors.map((e) => e.message),
    r.status === "duplicate" ? `identical to submission #${r.submission_id}` : "",
    r.status === "saved" ? `submission #${r.submission_id}` : "",
    ...r.warnings.map((w) => `warning: ${w}`),
  ].filter(Boolean).join(" ");
}

// Filterable / sortable columns: the row number, the result, the details, then the file's own columns.
const COLUMNS: Column<ReportRow>[] = [
  { key: "row", text: (r) => String(r.row), num: (r) => r.row },
  { key: "result", text: (r) => LABEL[r.status] },
  { key: "details", text: detailsText },
  ...UPLOAD_COLUMNS.map((c): Column<ReportRow> => ({
    key: c,
    text: (r) => r.values[c] ?? "",
    ...(NUMERIC_UPLOAD_COLUMNS.includes(c)
      ? { num: (r: ReportRow) => (r.values[c] !== undefined && r.values[c] !== "" && Number.isFinite(Number(r.values[c])) ? Number(r.values[c]) : null) }
      : {}),
  })),
];

export function ReportView({ report }: { report: UploadReport }) {
  const s = report.summary;
  const view = useTableView(report.rows, COLUMNS, { key: "row", dir: "asc" }); // file order
  return (
    <section>
      <h2>Report for {report.filename}</h2>
      {report.identical_file_seen_before && (
        <div className="flash">
          This exact file was uploaded before. Rows already on file are shown as duplicates and were not saved again.
        </div>
      )}
      <div className="cards">
        <div className="card"><b>{s.total}</b>rows</div>
        <div className="card saved"><b>{s.saved}</b>saved</div>
        <div className="card duplicate"><b>{s.duplicate}</b>already on file</div>
        <div className="card failed"><b>{s.failed}</b>failed</div>
      </div>
      <p>
        <FilterSummary view={view} total={report.rows.length} noun="rows" />
      </p>
      <div className="wrap">
        <table>
          <thead>
            <SortHeaderRow columns={COLUMNS} view={view} />
            <FilterRow columns={COLUMNS} view={view} />
          </thead>
          <tbody>
            {view.rows.map((r) => (
              <tr key={r.row}>
                <td className="num">{r.row}</td>
                <td><span className={`badge ${r.status}`}>{LABEL[r.status]}</span></td>
                <td className="details">
                  {r.errors.length > 0 && (
                    <span className="bad-text">
                      {r.errors.length} problem{r.errors.length === 1 ? "" : "s"}: {[...new Set(r.errors.map((e) => e.field))].join(", ")}
                    </span>
                  )}
                  {r.status === "duplicate" && <span className="muted">identical to submission #{r.submission_id}</span>}
                  {r.status === "saved" && <span className="muted">submission #{r.submission_id}</span>}
                  {r.warnings.map((w, i) => (
                    <div key={i} className="pending">warning: {w}</div>
                  ))}
                </td>
                {UPLOAD_COLUMNS.map((c) => {
                  const problems = r.errors.filter((e) => e.field === c);
                  if (problems.length === 0) return <td key={c} className="nowrap">{r.values[c]}</td>;
                  return (
                    <td key={c} className="bad">
                      {r.values[c] || <em>(blank)</em>}
                      {problems.map((e, i) => <div key={i} className="why">{e.message}</div>)}
                    </td>
                  );
                })}
              </tr>
            ))}
            {view.rows.length === 0 && (
              <tr><td colSpan={COLUMNS.length} className="muted">No rows match the column filters.</td></tr>
            )}
          </tbody>
        </table>
      </div>
      <p className="muted small">{FILTER_HELP}</p>
      {s.saved > 0 && <p><Link to="/review">Go to cost review</Link></p>}
    </section>
  );
}

export default function Upload() {
  const { actor } = useActor();
  const { bump, showTable } = useDataView();
  const [file, setFile] = useState<File | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [report, setReport] = useState<UploadReport | null>(null);

  async function submit(e: FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    setError(null);
    setReport(null);
    try {
      const rep = await api.upload(file, actor);
      setReport(rep);
      bump();
      // in split view, jump the side panel to the newest submissions so saved and already-on-file rows can be checked
      if (rep.summary.saved + rep.summary.duplicate > 0) showTable("cost_submissions", "submission_id", "desc");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <h1>Upload supplier cost submissions</h1>
      <p className="sub">
        CSV or Excel (.xlsx, first sheet). Every row is validated; valid rows are saved as <em>pending</em> even if
        others fail. Re-uploading identical rows never creates duplicates.
      </p>
      <form onSubmit={submit} className="uploadform">
        <input
          type="file"
          aria-label="Submissions file"
          accept=".csv,.xlsx,.xlsm"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
        />
        <button className="primary" disabled={!file || busy}>{busy ? "Uploading…" : "Upload and validate"}</button>
      </form>
      {error && <div className="flash error" role="alert">{error}</div>}
      {report && <ReportView report={report} />}
    </>
  );
}
