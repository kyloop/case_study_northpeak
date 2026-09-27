import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { DataTable } from "./Data";

const payload = (filters: { column: string; value: string }[] = []) => ({
  table: "cost_submissions", columns: ["submission_id", "fiscal_period", "status"],
  rows: [{ submission_id: 1, fiscal_period: "FY26-Q3", status: "pending" }],
  total: 1, page: 1, pages: 1, sort: "submission_id", dir: "asc", q: "", filters,
});

let fetchMock: ReturnType<typeof vi.fn>;
const lastFilters = () => {
  const url = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][0] as string;
  return new URL(url, "http://x").searchParams.getAll("f");
};

beforeEach(() => {
  fetchMock = vi.fn(async () => ({ ok: true, json: async () => payload() }));
  vi.stubGlobal("fetch", fetchMock);
  render(
    <MemoryRouter initialEntries={["/data/cost_submissions"]}>
      <Routes><Route path="/data/:table" element={<DataTable />} /></Routes>
    </MemoryRouter>,
  );
});
afterEach(() => vi.restoreAllMocks());

test("every column gets its own filter box and filters on several columns are sent together", async () => {
  await screen.findByLabelText("Filter status");
  expect(screen.getByLabelText("Filter submission_id")).toBeInTheDocument();
  expect(screen.getByLabelText("Filter fiscal_period")).toBeInTheDocument();
  expect(lastFilters()).toEqual([]);

  await userEvent.type(screen.getByLabelText("Filter fiscal_period"), "FY26-Q3");
  await userEvent.type(screen.getByLabelText("Filter status"), "pending");
  await waitFor(() => expect(lastFilters()).toEqual(["fiscal_period:FY26-Q3", "status:pending"]));
  expect(screen.getByRole("button", { name: /clear 2 column filters/i })).toBeInTheDocument();
});

test("typing does not fire one request per keystroke", async () => {
  await screen.findByLabelText("Filter status");
  const before = fetchMock.mock.calls.length;
  await userEvent.type(screen.getByLabelText("Filter status"), "pending");
  await waitFor(() => expect(lastFilters()).toEqual(["status:pending"]));
  expect(fetchMock.mock.calls.length - before).toBeLessThanOrEqual(2);
});

test("clearing filters removes them from the request and empties the boxes", async () => {
  await screen.findByLabelText("Filter status");
  await userEvent.type(screen.getByLabelText("Filter status"), "approved");
  await userEvent.click(await screen.findByRole("button", { name: /clear 1 column filter/i }));
  await waitFor(() => expect(lastFilters()).toEqual([]));
  expect(screen.getByLabelText("Filter status")).toHaveValue("");
});

test("a rejected filter shows the server's message and keeps the filter boxes so it can be fixed", async () => {
  await screen.findByLabelText("Filter status");
  fetchMock.mockResolvedValue({ ok: false, status: 400, statusText: "Bad Request",
    json: async () => ({ detail: "Filter on target_cost: '>abc' needs a number after >" }) });
  await userEvent.type(screen.getByLabelText("Filter status"), ">abc");
  expect(await screen.findByRole("alert")).toHaveTextContent("needs a number after >");
  expect(screen.getByLabelText("Filter status")).toHaveValue(">abc");
});

test("pressing Enter in a filter box applies it straight away, without waiting for the typing pause", async () => {
  await screen.findByLabelText("Filter status");
  await userEvent.type(screen.getByLabelText("Filter status"), "5{Enter}");
  await waitFor(() => expect(lastFilters()).toEqual(["status:5"]), { timeout: 200 }); // the pause is 300 ms
});
