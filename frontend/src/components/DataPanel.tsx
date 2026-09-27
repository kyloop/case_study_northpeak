import { useEffect, useRef, useState } from "react";
import { api } from "../api";
import { useDataView } from "../dataview";
import { TableBrowser, type BrowserState, type LinkTo } from "../pages/Data";
import type { TableInfo } from "../types";

const KEY_H = "northpeak.vsplit";
const KEY_BOTTOM = "northpeak.bottomTable";
const KEY_ON = "northpeak.bottomOn";

function read(key: string, fallback: string): string {
  try {
    return localStorage.getItem(key) ?? fallback;
  } catch {
    return fallback;
  }
}
function write(key: string, value: string) {
  try {
    localStorage.setItem(key, value);
  } catch {
    /* ignore */
  }
}

function TablePicker({ id, label, value, tables, onChange }: {
  id: string; label: string; value: string; tables: TableInfo[]; onChange: (t: string) => void;
}) {
  return (
    <div className="panelhead">
      <label htmlFor={id}><b>{label}</b></label>
      <select id={id} value={value} onChange={(e) => onChange(e.target.value)}>
        {tables.map((t) => <option key={t.name} value={t.name}>{t.name} ({t.count})</option>)}
        {!tables.some((t) => t.name === value) && <option value={value}>{value}</option>}
      </select>
    </div>
  );
}

/**
 * Right-hand side of the split view: two stacked tables. The bottom one can follow the top one, so
 * filtering (or clicking a row in) the top table shows the related records in the bottom table.
 */
export default function DataPanel() {
  const { target, showTable, version } = useDataView();
  const [tables, setTables] = useState<TableInfo[]>([]);
  const [bottom, setBottom] = useState(() => read(KEY_BOTTOM, "parts"));
  const [showBottom, setShowBottom] = useState(() => read(KEY_ON, "1") === "1");
  const [linked, setLinked] = useState(true);
  const [topState, setTopState] = useState<BrowserState & { table: string }>({ table: "", q: "", filters: [], selected: null });
  // Ignore state left over from a previously shown top table (its columns may not exist in the new one).
  const top: BrowserState = topState.table === target.table ? topState : { q: "", filters: [], selected: null };
  const [topPct, setTopPct] = useState(() => Number(read(KEY_H, "50")) || 50);
  const stack = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    api.tables().then((r) => setTables(r.tables), () => setTables([]));
  }, [version]);

  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!dragging.current || !stack.current) return;
      const box = stack.current.getBoundingClientRect();
      setTopPct(Math.min(80, Math.max(20, ((e.clientY - box.top) / box.height) * 100)));
    };
    const up = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.classList.remove("resizing-v");
      setTopPct((p) => { write(KEY_H, String(Math.round(p))); return p; });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  // The bottom pane follows the top pane's search, column filters and clicked row.
  const link: LinkTo | null = linked
    ? {
        table: target.table,
        q: top.q,
        filters: top.selected ? [...top.filters, [top.selected.column, `=${top.selected.value}`]] : top.filters,
      }
    : null;

  return (
    <div className="stack" ref={stack}>
      <section className="subpane" style={showBottom ? { flex: `0 0 ${topPct}%` } : { flex: 1 }} aria-label="Top table">
        <TablePicker id="panel-table" label="Top table" value={target.table} tables={tables} onChange={(t) => showTable(t)} />
        <TableBrowser
          key={`${target.table}|${target.nonce}`}
          table={target.table}
          initialSort={target.sort}
          initialDir={target.dir}
          selectable
          onState={(s) => setTopState({ ...s, table: target.table })}
        />
      </section>

      {showBottom && (
        <>
          <div
            className="hdivider"
            role="separator"
            aria-orientation="horizontal"
            aria-label="Resize tables"
            onPointerDown={(e) => { e.preventDefault(); dragging.current = true; document.body.classList.add("resizing-v"); }}
          />
          <section className="subpane" style={{ flex: 1 }} aria-label="Bottom table">
            <div className="panelhead">
              <TablePicker
                id="panel-table-bottom" label="Bottom table" value={bottom} tables={tables}
                onChange={(t) => { setBottom(t); write(KEY_BOTTOM, t); }}
              />
              <label className="linkopt">
                <input type="checkbox" checked={linked} onChange={(e) => setLinked(e.target.checked)} /> follow top table
              </label>
              <button className="link" onClick={() => { setShowBottom(false); write(KEY_ON, "0"); }}>hide</button>
            </div>
            {linked && top.selected && (
              <p className="muted small">Showing records related to {target.table} {top.selected.column} {top.selected.value} (click the row again to clear).</p>
            )}
            <TableBrowser key={bottom} table={bottom} link={link} />
          </section>
        </>
      )}
      {!showBottom && (
        <p className="small"><button className="link" onClick={() => { setShowBottom(true); write(KEY_ON, "1"); }}>Show a related table below</button></p>
      )}
    </div>
  );
}
