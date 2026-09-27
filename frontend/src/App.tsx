import { useEffect, useState } from "react";
import { NavLink, Navigate, Route, Routes, useLocation } from "react-router-dom";
import { useActor } from "./actor";
import Review from "./pages/Review";
import Upload from "./pages/Upload";
import { DataIndex, DataTable } from "./pages/Data";
import SplitLayout, { useSplit } from "./components/SplitLayout";

const KEY_STICKY = "northpeak.sticky";

/** Pin table headers (column names + filter boxes) while the rows scroll. On by default. */
function useStickyHeaders() {
  const [on, setOn] = useState(() => {
    try {
      return localStorage.getItem(KEY_STICKY) !== "0";
    } catch {
      return true;
    }
  });
  useEffect(() => {
    document.body.classList.toggle("no-sticky", !on);
    try {
      localStorage.setItem(KEY_STICKY, on ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [on]);
  return { on, toggle: () => setOn((v) => !v) };
}

function ActorBox() {
  const { actor, setActor } = useActor();
  const [draft, setDraft] = useState(actor);
  return (
    <form
      className="actor"
      onSubmit={(e) => {
        e.preventDefault();
        setActor(draft.trim());
      }}
    >
      <label htmlFor="actor" className="muted">
        Working as
      </label>
      <input id="actor" value={draft} onChange={(e) => setDraft(e.target.value)} placeholder="your name" size={16} />
      <button type="submit">Set</button>
    </form>
  );
}

export default function App() {
  const split = useSplit();
  const sticky = useStickyHeaders();
  const onDataPage = useLocation().pathname.startsWith("/data"); // already full-page data: no side panel
  return (
    <>
      <header>
        <strong>NorthPeak Cost Tool</strong>
        <nav>
          <NavLink to="/review">Cost review</NavLink>
          <NavLink to="/upload">Upload</NavLink>
          <NavLink to="/data">Data tables</NavLink>
        </nav>
        <button
          className="toggle"
          aria-pressed={split.on}
          title="Show the data tables next to this page"
          onClick={split.toggle}
        >
          Split view: {split.on ? "on" : "off"}
        </button>
        <button
          className="toggle"
          aria-pressed={sticky.on}
          title="Keep table column headings and filter boxes in view while scrolling rows"
          onClick={sticky.toggle}
        >
          Sticky header: {sticky.on ? "on" : "off"}
        </button>
        <ActorBox />
      </header>
      <SplitLayout showPanel={split.on && !onDataPage}>
        <Routes>
          <Route path="/" element={<Navigate to="/review" replace />} />
          <Route path="/review" element={<Review />} />
          <Route path="/upload" element={<Upload />} />
          <Route path="/data" element={<DataIndex />} />
          <Route path="/data/:table" element={<DataTable />} />
          <Route path="*" element={<p className="muted">Page not found.</p>} />
        </Routes>
      </SplitLayout>
    </>
  );
}
