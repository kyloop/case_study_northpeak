import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useParams, useSearchParams } from "react-router-dom";
import { api } from "../api";
import { useDataView } from "../dataview";
import { FILTER_HELP } from "../filters";
import type { TableData, TableInfo } from "../types";

export function DataIndex() {
  const { version } = useDataView();
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    api.tables().then((r) => setTables(r.tables), (e: Error) => setError(e.message));
  }, [version]);
  return (
    <>
      <h1>Data tables</h1>
      <p className="sub">Read-only view of everything in the database.</p>
      {error && <div className="flash error">{error}</div>}
      <table style={{ maxWidth: 420 }}>
        <thead><tr><th>Table</th><th className="num">Rows</th></tr></thead>
        <tbody>
          {tables.map((t) => (
            <tr key={t.name}>
              <td><Link to={`/data/${t.name}`}>{t.name}</Link></td>
              <td className="num">{t.count}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </>
  );
}

const FILTER_DELAY_MS = 300;

export type Filters = [column: string, value: string][];

/** What a table pane tells its owner, so another pane can follow it. */
export interface BrowserState {
  q: string;
  filters: Filters;
  selected: { column: string; value: string | number } | null; // the clicked row, by its first (key) column
}

/** Show only rows related to another table's rows (the top pane's search, filters and clicked row). */
export interface LinkTo {
  table: string;
  q: string;
  filters: Filters;
}

/**
 * Search / per-column filters / sort / page over one table. Used by the full-page view and by both
 * panes of the split-view side panel. `selectable` lets rows be clicked (reported through
 * `onState`); `link` restricts the rows to those related to another table's rows.
 */
export function TableBrowser({ table, initialSort = "", initialDir = "asc", selectable = false, onState, link = null }: {
  table: string;
  initialSort?: string;
  initialDir?: "asc" | "desc";
  selectable?: boolean;
  onState?: (s: BrowserState) => void;
  link?: LinkTo | null;
}) {
  const { version } = useDataView();
  const [q, setQ] = useState("");
  const [draft, setDraft] = useState("");
  // what is typed in the filter boxes vs. what has been applied (after a short pause in typing)
  const [filterDraft, setFilterDraft] = useState<Record<string, string>>({});
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [sort, setSort] = useState(initialSort);
  const [dir, setDir] = useState<"asc" | "desc">(initialDir);
  const [page, setPage] = useState(1);
  const [data, setData] = useState<TableData | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [selected, setSelected] = useState<BrowserState["selected"]>(null);

  const activeFilters: Filters = useMemo(
    () => Object.entries(filters).filter(([, v]) => v.trim() !== ""),
    [filters],
  );

  useEffect(() => {
    const timer = setTimeout(() => {
      setFilters((current) => {
        const same = JSON.stringify(current) === JSON.stringify(filterDraft);
        if (!same) {
          setPage(1);
          setSelected(null); // the clicked row may no longer match
        }
        return same ? current : filterDraft;
      });
    }, FILTER_DELAY_MS);
    return () => clearTimeout(timer);
  }, [filterDraft]);

  // report search / filters / clicked row to the owner (the bottom pane follows them)
  useEffect(() => {
    onState?.({ q, filters: activeFilters, selected });
  }, [q, activeFilters, selected]); // eslint-disable-line react-hooks/exhaustive-deps

  const linkKey = JSON.stringify(link);
  useEffect(() => {
    setError(null);
    const params = new URLSearchParams({ q, sort, dir, page: String(page) });
    for (const [col, value] of activeFilters) params.append("f", `${col}:${value}`);
    if (link) {
      params.set("link_table", link.table);
      params.set("link_q", link.q);
      for (const [col, value] of link.filters) params.append("link_f", `${col}:${value}`);
    }
    // On failure keep the previous rows (and the filter boxes) so the user can correct the filter.
    api.table(table, params).then(setData, (e: Error) => setError(e.message));
  }, [table, q, sort, dir, page, activeFilters, version, linkKey]); // eslint-disable-line react-hooks/exhaustive-deps

  // a new link means a different set of rows: go back to page 1
  useEffect(() => { setPage(1); }, [linkKey]);

  function search(e: FormEvent) {
    e.preventDefault();
    setQ(draft.trim());
    setPage(1);
    setSelected(null);
  }

  function sortBy(col: string) {
    const desc = data?.sort === col && data.dir === "asc";
    setSort(col);
    setDir(desc ? "desc" : "asc");
    setPage(1);
  }

  // Enter in a filter box applies it right away instead of waiting for the typing pause
  function applyFiltersNow() {
    if (JSON.stringify(filters) === JSON.stringify(filterDraft)) return;
    setFilters(filterDraft);
    setPage(1);
    setSelected(null);
  }

  function clearFilters() {
    setFilterDraft({});
    setFilters({});
    setPage(1);
    setSelected(null);
  }

  function clickRow(row: TableData["rows"][number]) {
    if (!selectable || !data) return;
    const column = data.columns[0]; // every table's first column is its key
    const value = row[column] as string | number;
    setSelected((cur) => (cur && cur.column === column && cur.value === value ? null : { column, value }));
  }

  return (
    <>
      <p className="sub">
        {data ? <>{data.total} row{data.total === 1 ? "" : "s"}{data.q && <> matching “{data.q}”</>}</> : "\u00a0"}
        {data?.link?.path && <> · linked: <b>{data.link.path.join(" → ")}</b></>}
        {data?.link?.note && <> · {data.link.note}</>}
      </p>
      <form onSubmit={search} className="searchform">
        <input type="search" aria-label="Search all columns" placeholder="search all columns" value={draft} onChange={(e) => setDraft(e.target.value)} />
        <button>Search</button>
        {q && <button type="button" className="link" onClick={() => { setDraft(""); setQ(""); setPage(1); setSelected(null); }}>clear</button>}
        {activeFilters.length > 0 && (
          <button type="button" className="link" onClick={clearFilters}>
            clear {activeFilters.length} column filter{activeFilters.length === 1 ? "" : "s"}
          </button>
        )}
      </form>
      {error && <div className="flash error" role="alert">{error}</div>}
      {data && (
        <>
          <div className="wrap">
            <table>
              <thead>
                <tr>
                  {data.columns.map((c) => (
                    <th key={c}>
                      {c === "risk_note" ? c : (
                        <button className="link th" onClick={() => sortBy(c)}>
                          {c}{data.sort === c ? (data.dir === "asc" ? " ▲" : " ▼") : ""}
                        </button>
                      )}
                    </th>
                  ))}
                </tr>
                <tr className="filterrow">
                  {data.columns.map((c) => (
                    <th key={c}>
                      {c !== "risk_note" && (
                        <input
                          aria-label={`Filter ${c}`}
                          placeholder="filter"
                          value={filterDraft[c] ?? ""}
                          onChange={(e) => setFilterDraft((d) => ({ ...d, [c]: e.target.value }))}
                          onKeyDown={(e) => { if (e.key === "Enter") applyFiltersNow(); }}
                        />
                      )}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {data.rows.map((r, i) => {
                  const isSel = selected !== null && r[selected.column] === selected.value;
                  return (
                    <tr
                      key={i}
                      className={[selectable ? "clickable" : "", isSel ? "sel" : ""].join(" ").trim()}
                      aria-selected={selectable ? isSel : undefined}
                      onClick={selectable ? () => clickRow(r) : undefined}
                    >
                      {data.columns.map((c) => <td key={c}>{r[c] ?? ""}</td>)}
                    </tr>
                  );
                })}
                {data.rows.length === 0 && <tr><td colSpan={data.columns.length} className="muted">No rows.</td></tr>}
              </tbody>
            </table>
          </div>
          <p className="muted small">{FILTER_HELP}</p>
          <div className="pager">
            {data.page > 1 && <button className="link" onClick={() => setPage(data.page - 1)}>← Prev</button>}
            <span className="muted">Page {data.page} of {data.pages}</span>
            {data.page < data.pages && <button className="link" onClick={() => setPage(data.page + 1)}>Next →</button>}
          </div>
        </>
      )}
    </>
  );
}

export function DataTable() {
  const { table = "" } = useParams();
  const [params] = useSearchParams(); // e.g. /data/audit_log?sort=audit_id&dir=desc (from the review page)
  return (
    <>
      <h1>{table}</h1>
      <p className="sub"><Link to="/data">All tables</Link></p>
      <TableBrowser key={table} table={table} initialSort={params.get("sort") ?? ""} initialDir={params.get("dir") === "desc" ? "desc" : "asc"} />
    </>
  );
}
