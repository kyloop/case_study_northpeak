import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { DataViewProvider } from "../dataview";
import DataPanel from "./DataPanel";

const tables = { tables: [
  { name: "suppliers", count: 20 }, { name: "facilities", count: 28 }, { name: "parts", count: 45 },
  { name: "cost_submissions", count: 250 },
] };

const page = (table: string, columns: string[], rows: Record<string, string | number>[], path: string[] | null = null) => ({
  table, columns, rows, total: rows.length, page: 1, pages: 1, sort: columns[0], dir: "asc", q: "", filters: [],
  link: path ? { path, note: null } : null,
});

let calls: URL[];
beforeEach(() => {
  localStorage.clear();
  calls = [];
  vi.stubGlobal("fetch", vi.fn(async (url: string) => {
    const u = new URL(url, "http://x");
    calls.push(u);
    const name = u.pathname.replace("/api/tables/", "");
    return { ok: true, json: async () => {
      if (u.pathname === "/api/tables") return tables;
      if (name === "cost_submissions") return page(name, ["submission_id", "part_id"], [{ submission_id: 7, part_id: 3 }, { submission_id: 8, part_id: 4 }]);
      if (name === "parts") return page(name, ["part_id", "commodity"], [{ part_id: 3, commodity: "Connector" }], u.searchParams.get("link_table") ? ["cost_submissions", "parts"] : null);
      return page(name, ["x"], []);
    } };
  }));
});
afterEach(() => vi.restoreAllMocks());

const lastCall = (table: string) => [...calls].reverse().find((u) => u.pathname === `/api/tables/${table}`)!;

function setup() {
  render(<DataViewProvider><DataPanel /></DataViewProvider>);
}

test("shows two tables, top and bottom, each with its own picker", async () => {
  setup();
  const top = await screen.findByRole("region", { name: "Top table" });
  const bottom = screen.getByRole("region", { name: "Bottom table" });
  expect(await within(top).findByRole("button", { name: /^submission_id/ })).toBeInTheDocument();
  expect(await within(bottom).findByRole("button", { name: /^commodity/ })).toBeInTheDocument();
  expect(within(top).getByRole("combobox")).toHaveValue("cost_submissions");
  expect(within(bottom).getByRole("combobox")).toHaveValue("parts");
});

test("filtering the top table makes the bottom table show only the related records", async () => {
  setup();
  const top = await screen.findByRole("region", { name: "Top table" });
  await within(top).findByLabelText("Filter part_id");
  expect(lastCall("parts").searchParams.get("link_table")).toBe("cost_submissions");
  expect(lastCall("parts").searchParams.getAll("link_f")).toEqual([]);

  await userEvent.type(within(top).getByLabelText("Filter part_id"), "3");
  await waitFor(() => expect(lastCall("parts").searchParams.getAll("link_f")).toEqual(["part_id:3"]));
  expect(await screen.findByText(/linked:/)).toHaveTextContent("cost_submissions → parts");
});

test("clicking a row in the top table narrows the bottom table to that row; clicking again clears it", async () => {
  setup();
  const top = await screen.findByRole("region", { name: "Top table" });
  const row = (await within(top).findByText("7")).closest("tr")!;
  await userEvent.click(row);
  await waitFor(() => expect(lastCall("parts").searchParams.getAll("link_f")).toEqual(["submission_id:=7"]));
  expect(row).toHaveAttribute("aria-selected", "true");

  await userEvent.click(row);
  await waitFor(() => expect(lastCall("parts").searchParams.getAll("link_f")).toEqual([]));
});

test("the bottom table can be unlinked, switched, and hidden", async () => {
  setup();
  const bottom = await screen.findByRole("region", { name: "Bottom table" });
  await userEvent.click(within(bottom).getByRole("checkbox", { name: /follow top table/i }));
  await waitFor(() => expect(lastCall("parts").searchParams.get("link_table")).toBeNull());

  await userEvent.selectOptions(within(bottom).getAllByRole("combobox")[0], "suppliers");
  await waitFor(() => expect(lastCall("suppliers")).toBeDefined());

  await userEvent.click(within(bottom).getByRole("button", { name: "hide" }));
  expect(screen.queryByRole("region", { name: "Bottom table" })).not.toBeInTheDocument();
  expect(screen.getByRole("button", { name: /show a related table/i })).toBeInTheDocument();
});

test("switching the top table does not apply the old table's filters to the new one", async () => {
  setup();
  const top = await screen.findByRole("region", { name: "Top table" });
  await userEvent.type(await within(top).findByLabelText("Filter part_id"), "3");
  await waitFor(() => expect(lastCall("parts").searchParams.getAll("link_f")).toEqual(["part_id:3"]));

  const before = calls.length;
  await userEvent.selectOptions(within(top).getByRole("combobox"), "suppliers");
  await waitFor(() => expect(calls.slice(before).some((u) => u.searchParams.get("link_table") === "suppliers")).toBe(true));
  // no request ever asked for suppliers filtered by the old table's part_id filter
  expect(calls.slice(before).some((u) => u.searchParams.getAll("link_f").includes("part_id:3"))).toBe(false);
});
