import { useMemo, useState } from "react";
import { isInvalidFilter, matchesFilter } from "./filters";

// Filter + sort for tables that hold all their rows in the browser (Cost Review, the upload report).
// The rules are in filters.ts and match the server-side filters on the data tables.

export interface Column<T> {
  key: string;
  /** what the cell shows; used by contains / = / != and for text sorting */
  text: (row: T) => string;
  /** the raw number, for > >= < <= and numeric sorting; null when the cell has none */
  num?: (row: T) => number | null;
  right?: boolean;
}

export interface Sort {
  key: string;
  dir: "asc" | "desc";
}

export function useTableView<T>(rows: T[], columns: Column<T>[], initialSort: Sort) {
  const [filters, setFilters] = useState<Record<string, string>>({});
  const [sort, setSort] = useState<Sort>(initialSort);

  const activeCount = Object.values(filters).filter((v) => v.trim() !== "").length;

  const visible = useMemo(() => {
    const col = columns.find((c) => c.key === sort.key) ?? columns[0];
    const shown = rows.filter((r) =>
      columns.every((c) => matchesFilter(c.text(r), c.num ? c.num(r) : null, filters[c.key] ?? "")),
    );
    const sign = sort.dir === "asc" ? 1 : -1;
    return [...shown].sort((a, b) => {
      if (col.num) {
        const x = col.num(a);
        const y = col.num(b);
        if (x === null || y === null) return x === y ? 0 : x === null ? 1 : -1; // cells with no number go last
        return sign * (x - y);
      }
      // text: case-insensitive, digits in natural order (CON-1013 before CON-1019, 9 before 10)
      return sign * col.text(a).localeCompare(col.text(b), undefined, { sensitivity: "base", numeric: true });
    });
  }, [rows, columns, filters, sort]);

  return {
    rows: visible,
    filters,
    activeCount,
    sort,
    setFilter: (key: string, value: string) => setFilters((f) => ({ ...f, [key]: value })),
    clearFilters: () => setFilters({}),
    sortBy: (key: string) => setSort((s) => ({ key, dir: s.key === key && s.dir === "asc" ? "desc" : "asc" })),
  };
}

type View<T> = ReturnType<typeof useTableView<T>>;

/** The header row: one clickable, sortable heading per column. Put extra <th> cells in `children`. */
export function SortHeaderRow<T>({ columns, view, children }: { columns: Column<T>[]; view: View<T>; children?: React.ReactNode }) {
  return (
    <tr>
      {columns.map((c) => (
        <th
          key={c.key}
          className={c.right ? "num" : undefined}
          aria-sort={view.sort.key === c.key ? (view.sort.dir === "asc" ? "ascending" : "descending") : undefined}
        >
          <button className="link th" onClick={() => view.sortBy(c.key)}>
            {c.key}{view.sort.key === c.key ? (view.sort.dir === "asc" ? " ▲" : " ▼") : ""}
          </button>
        </th>
      ))}
      {children}
    </tr>
  );
}

/** The row of filter boxes, one under each column heading. */
export function FilterRow<T>({ columns, view, children }: { columns: Column<T>[]; view: View<T>; children?: React.ReactNode }) {
  return (
    <tr className="filterrow">
      {columns.map((c) => (
        <th key={c.key}>
          <input
            aria-label={`Filter ${c.key}`}
            aria-invalid={isInvalidFilter(view.filters[c.key] ?? "") || undefined}
            placeholder="filter"
            value={view.filters[c.key] ?? ""}
            onChange={(e) => view.setFilter(c.key, e.target.value)}
          />
        </th>
      ))}
      {children}
    </tr>
  );
}

/** "3 of 8" plus a clear button, shown while filters are active. */
export function FilterSummary<T>({ view, total, noun }: { view: View<T>; total: number; noun: string }) {
  return (
    <>
      <span className="muted">
        {view.activeCount > 0 ? `${view.rows.length} of ${total}` : total} {noun}
      </span>
      {view.activeCount > 0 && (
        <>
          {" · "}
          <button className="link" onClick={view.clearFilters}>
            clear {view.activeCount} column filter{view.activeCount === 1 ? "" : "s"}
          </button>
        </>
      )}
    </>
  );
}
