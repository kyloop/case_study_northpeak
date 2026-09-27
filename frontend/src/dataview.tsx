import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

// Shared state for the split-screen data panel: which table it shows, and a version counter
// that pages bump after they change data (upload, approve/reject) so the panel refetches.
export interface PanelTarget {
  table: string;
  sort: string;
  dir: "asc" | "desc";
  nonce: number; // changes every time a page asks the panel to jump somewhere, resetting its state
}

interface DataViewValue {
  version: number;
  bump: () => void;
  target: PanelTarget;
  showTable: (table: string, sort?: string, dir?: "asc" | "desc") => void;
}

const noop = () => {};
const DataViewContext = createContext<DataViewValue>({
  version: 0,
  bump: noop,
  target: { table: "cost_submissions", sort: "", dir: "asc", nonce: 0 },
  showTable: noop,
});

export function DataViewProvider({ children }: { children: ReactNode }) {
  const [version, setVersion] = useState(0);
  const [target, setTarget] = useState<PanelTarget>({ table: "cost_submissions", sort: "", dir: "asc", nonce: 0 });
  const bump = useCallback(() => setVersion((v) => v + 1), []);
  const showTable = useCallback(
    (table: string, sort = "", dir: "asc" | "desc" = "asc") =>
      setTarget((t) => ({ table, sort, dir, nonce: t.nonce + 1 })),
    [],
  );
  const value = useMemo(() => ({ version, bump, target, showTable }), [version, bump, target, showTable]);
  return <DataViewContext.Provider value={value}>{children}</DataViewContext.Provider>;
}

export const useDataView = () => useContext(DataViewContext);
