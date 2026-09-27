import { render, screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, expect, test, vi } from "vitest";
import Upload from "./Upload";

const report = {
  filename: "errors.csv",
  identical_file_seen_before: false,
  summary: { total: 2, saved: 1, duplicate: 0, failed: 1 },
  rows: [
    {
      row: 1,
      values: { part_number: "SNS-9999", supplier_name: "Unknown Supplier Co", fiscal_period: "FY26-Q4", submitted_unit_cost: "4.5" },
      status: "failed", warnings: [], submission_id: null,
      errors: [
        { field: "part_number", message: "part 'SNS-9999' does not exist in the parts master" },
        { field: "supplier_name", message: "supplier 'Unknown Supplier Co' does not exist in the suppliers master" },
      ],
    },
    {
      row: 2,
      values: { part_number: "ENC-1018", supplier_name: "Cascade Technologies", fiscal_period: "FY26-Q4", submitted_unit_cost: "3.395" },
      status: "saved", warnings: [], submission_id: 258, errors: [],
    },
  ],
};

afterEach(() => vi.restoreAllMocks());

test("uploads the chosen file and shows which rows failed and why", async () => {
  const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => report });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter><Upload /></MemoryRouter>);

  const button = screen.getByRole("button", { name: /upload and validate/i });
  expect(button).toBeDisabled(); // nothing chosen yet
  await userEvent.upload(screen.getByLabelText(/submissions file/i), new File(["x"], "errors.csv", { type: "text/csv" }));
  await userEvent.click(button);

  expect(await screen.findByText(/does not exist in the parts master/)).toBeInTheDocument();
  expect(screen.getByText(/does not exist in the suppliers master/)).toBeInTheDocument();
  expect(screen.getByText("failed", { selector: ".badge" })).toBeInTheDocument();
  expect(screen.getByText("saved", { selector: ".badge" })).toBeInTheDocument();
  expect(screen.getByRole("columnheader", { name: "part_number" })).toBeInTheDocument(); // CSV column names
  expect(screen.getByRole("columnheader", { name: "submitted_by" })).toBeInTheDocument();
  expect(screen.getByText("SNS-9999")).toHaveClass("bad"); // the failing cell is highlighted
  // ...and the reason is stated inside that same cell, next to the value
  expect(screen.getByText(/part 'SNS-9999' does not exist/).closest("td")).toBe(screen.getByText("SNS-9999"));
  expect(screen.getByText(/supplier 'Unknown Supplier Co' does not exist/).closest("td")).toBe(screen.getByText("Unknown Supplier Co"));
  expect(screen.getByText("Unknown Supplier Co")).toHaveClass("bad");
  expect(screen.getByText("ENC-1018")).not.toHaveClass("bad"); // valid row untouched
  expect(fetchMock).toHaveBeenCalledWith("/api/upload", expect.objectContaining({ method: "POST" }));
});

test("shows the server's message when the whole file is rejected", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
    ok: false, status: 400, statusText: "Bad Request",
    json: async () => ({ detail: "Missing required column(s): currency" }),
  }));
  render(<MemoryRouter><Upload /></MemoryRouter>);
  await userEvent.upload(screen.getByLabelText(/submissions file/i), new File(["x"], "bad.csv"));
  await userEvent.click(screen.getByRole("button", { name: /upload and validate/i }));
  expect(await screen.findByRole("alert")).toHaveTextContent("Missing required column(s): currency");
});

// ---- filtering and sorting the report ----
const blankValues = { part_number: "", supplier_name: "", fiscal_period: "FY26-Q4", submitted_unit_cost: "", material_cost: "", labor_cost: "", overhead_cost: "", margin_pct: "", currency: "USD", submitted_by: "a@b.example" };
const mkRow = (row: number, status: string, values: Record<string, string>, errors: { field: string; message: string }[] = []) => ({
  row, status, errors, warnings: [], submission_id: status === "failed" ? null : 200 + row, values: { ...blankValues, ...values },
});
const bigReport = {
  filename: "big.csv", identical_file_seen_before: false,
  summary: { total: 5, saved: 1, duplicate: 1, failed: 3 },
  rows: [
    mkRow(1, "failed", { part_number: "SNS-9999", supplier_name: "Unknown Supplier Co", submitted_unit_cost: "4.5" },
      [{ field: "part_number", message: "part 'SNS-9999' does not exist" }, { field: "supplier_name", message: "supplier does not exist" }]),
    mkRow(2, "failed", { part_number: "ENC-1018", supplier_name: "Cascade Technologies", submitted_unit_cost: "-1.2" },
      [{ field: "submitted_unit_cost", message: "must be a positive number (got -1.2)" }]),
    mkRow(3, "failed", { part_number: "BAT-1011", supplier_name: "Ferncrest Components", submitted_unit_cost: "" },
      [{ field: "submitted_unit_cost", message: "is required but is blank" }]),
    mkRow(4, "saved", { part_number: "ENC-1018", supplier_name: "Cascade Technologies", submitted_unit_cost: "3.395" }),
    mkRow(5, "duplicate", { part_number: "CAM-1022", supplier_name: "Copperfield Precision", submitted_unit_cost: "12.5" }),
  ],
};
const shownRows = () => Array.from(document.querySelectorAll("tbody tr td:first-child")).map((td) => td.textContent);

async function renderBigReport() {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => bigReport }));
  render(<MemoryRouter><Upload /></MemoryRouter>);
  await userEvent.upload(screen.getByLabelText(/submissions file/i), new File(["x"], "big.csv"));
  await userEvent.click(screen.getByRole("button", { name: /upload and validate/i }));
  await screen.findByText("Report for big.csv");
}

test("the report has a filter box and a sortable heading for every column, including the file's own", async () => {
  await renderBigReport();
  for (const col of ["row", "result", "details", "part_number", "supplier_name", "fiscal_period", "submitted_unit_cost",
    "material_cost", "labor_cost", "overhead_cost", "margin_pct", "currency", "submitted_by"]) {
    expect(screen.getByLabelText(`Filter ${col}`)).toBeInTheDocument();
    expect(screen.getByRole("columnheader", { name: new RegExp(`^${col}`) })).toBeInTheDocument();
  }
  expect(shownRows()).toEqual(["1", "2", "3", "4", "5"]);       // default: file order
});

test("report rows can be filtered by result, by value, and by several columns at once", async () => {
  await renderBigReport();
  await userEvent.type(screen.getByLabelText("Filter result"), "=failed");
  expect(shownRows()).toEqual(["1", "2", "3"]);
  expect(screen.getByText("3 of 5 rows")).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("Filter submitted_unit_cost"), ">0");   // numeric; blank/negative cells drop out
  expect(shownRows()).toEqual(["1"]);

  await userEvent.click(screen.getByRole("button", { name: /clear 2 column filters/i }));
  expect(shownRows()).toEqual(["1", "2", "3", "4", "5"]);

  await userEvent.type(screen.getByLabelText("Filter details"), "supplier_name");     // searches the problems text
  expect(shownRows()).toEqual(["1"]);
  await userEvent.clear(screen.getByLabelText("Filter details"));
  await userEvent.type(screen.getByLabelText("Filter part_number"), "enc");           // case-insensitive contains
  expect(shownRows()).toEqual(["2", "4"]);
  await userEvent.type(screen.getByLabelText("Filter result"), "already");
  expect(await screen.findByText(/no rows match the column filters/i)).toBeInTheDocument();
});

test("report rows sort by number or text, ascending then descending, with unparseable numbers last", async () => {
  await renderBigReport();
  const sortBtn = (col: string) => within(screen.getByRole("columnheader", { name: new RegExp(`^${col}`) })).getByRole("button");

  await userEvent.click(sortBtn("submitted_unit_cost"));
  expect(shownRows()).toEqual(["2", "4", "1", "5", "3"]);       // -1.2, 3.395, 4.5, 12.5, then the blank one
  await userEvent.click(sortBtn("submitted_unit_cost"));
  expect(shownRows()).toEqual(["5", "1", "4", "2", "3"]);       // 12.5, 4.5, 3.395, -1.2, blank still last

  await userEvent.click(sortBtn("part_number"));
  expect(shownRows()).toEqual(["3", "5", "2", "4", "1"]);       // BAT, CAM, ENC, ENC, SNS
  await userEvent.click(sortBtn("row"));
  await userEvent.click(sortBtn("row"));
  expect(shownRows()).toEqual(["5", "4", "3", "2", "1"]);
  expect(screen.getByRole("columnheader", { name: /^row/ })).toHaveAttribute("aria-sort", "descending");
});
