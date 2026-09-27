import { useEffect, useRef, useState, type ReactNode } from "react";
import DataPanel from "./DataPanel";

const KEY_ON = "northpeak.split";
const KEY_W = "northpeak.splitWidth";

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

export function useSplit() {
  const [on, setOn] = useState(() => read(KEY_ON, "1") === "1");
  return { on, toggle: () => setOn((v) => { write(KEY_ON, v ? "0" : "1"); return !v; }) };
}

/** Left: the current page. Right: the data panel, with a draggable divider. */
export default function SplitLayout({ children, showPanel }: { children: ReactNode; showPanel: boolean }) {
  const [leftPct, setLeftPct] = useState(() => Number(read(KEY_W, "55")) || 55);
  const panes = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  useEffect(() => {
    const move = (e: PointerEvent) => {
      if (!dragging.current || !panes.current) return;
      const box = panes.current.getBoundingClientRect();
      setLeftPct(Math.min(75, Math.max(25, ((e.clientX - box.left) / box.width) * 100)));
    };
    const up = () => {
      if (!dragging.current) return;
      dragging.current = false;
      document.body.classList.remove("resizing");
      setLeftPct((p) => { write(KEY_W, String(Math.round(p))); return p; });
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", up);
    return () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", up);
    };
  }, []);

  if (!showPanel) return <div className="panes"><main className="pane">{children}</main></div>;

  return (
    <div className="panes" ref={panes}>
      <main className="pane" style={{ flex: `0 0 ${leftPct}%` }}>{children}</main>
      <div
        className="divider"
        role="separator"
        aria-orientation="vertical"
        aria-label="Resize panels"
        onPointerDown={(e) => { e.preventDefault(); dragging.current = true; document.body.classList.add("resizing"); }}
      />
      <aside className="pane side" aria-label="Data tables">
        <DataPanel />
      </aside>
    </div>
  );
}
