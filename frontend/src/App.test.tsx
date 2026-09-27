import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import App from "./App";
import { ActorProvider } from "./actor";
import { DataViewProvider } from "./dataview";

const tableData = {
  table: "cost_submissions", columns: ["submission_id", "part_id"], rows: [{ submission_id: 250, part_id: 3 }],
  total: 1, page: 1, pages: 1, sort: "submission_id", dir: "asc", q: "",
};

beforeEach(() => {
  localStorage.clear();
  document.body.classList.remove("no-sticky");
  vi.stubGlobal("fetch", vi.fn(async (url: string) => ({
    ok: true,
    json: async () => {
      if (url.startsWith("/api/tables/")) return tableData;
      if (url.startsWith("/api/tables")) return { tables: [{ name: "cost_submissions", count: 1 }, { name: "audit_log", count: 0 }] };
      return { threshold_pct: 20, rows: [] };
    },
  })));
});
afterEach(() => vi.restoreAllMocks());

function renderAt(path: string) {
  render(
    <MemoryRouter initialEntries={[path]}>
      <ActorProvider><DataViewProvider><App /></DataViewProvider></ActorProvider>
    </MemoryRouter>,
  );
}

test("split view shows the data tables next to the page and can be toggled off", async () => {
  renderAt("/review");
  const panel = await screen.findByRole("complementary", { name: /data tables/i });
  const [top, bottom] = await screen.findAllByRole("combobox"); // two stacked tables
  expect(top).toHaveValue("cost_submissions");
  expect(bottom).toHaveValue("parts");
  expect(panel).toHaveTextContent("submission_id");
  expect(screen.getByRole("heading", { name: "Cost review" })).toBeInTheDocument(); // page still on the left

  await userEvent.click(screen.getByRole("button", { name: /split view/i }));
  expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
});

test("no side panel on the full-page data view", async () => {
  renderAt("/data");
  expect(await screen.findByRole("heading", { name: "Data tables" })).toBeInTheDocument();
  expect(screen.queryByRole("complementary")).not.toBeInTheDocument();
});

test("table headers are pinned by default, and the toggle switches that off and on (and is remembered)", async () => {
  renderAt("/review");
  const button = await screen.findByRole("button", { name: /sticky header: on/i });
  expect(document.body.classList.contains("no-sticky")).toBe(false);

  await userEvent.click(button);
  expect(screen.getByRole("button", { name: /sticky header: off/i })).toBeInTheDocument();
  expect(document.body.classList.contains("no-sticky")).toBe(true);
  expect(localStorage.getItem("northpeak.sticky")).toBe("0");

  await userEvent.click(screen.getByRole("button", { name: /sticky header: off/i }));
  expect(document.body.classList.contains("no-sticky")).toBe(false);
});
