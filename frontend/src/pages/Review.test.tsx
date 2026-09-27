import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, expect, test, vi } from "vitest";
import { ActorProvider } from "../actor";
import Review from "./Review";

const row = {
  submission_id: 7, part_number: "BAT-1011", commodity: "Battery Cell", supplier_id: 8,
  supplier_name: "Ferncrest Components", fiscal_period: "FY26-Q3", submitted_unit_cost: 4.5,
  should_cost: 3.0, sample_size: 4, pct_over: 50, status: "pending",
  risk_note: "1 open risk event (max severity 5)",
};

function setup() {
  const fetchMock = vi.fn(async (_url: string, init?: RequestInit) => {
    if (init?.method === "POST") {
      return { ok: true, json: async () => ({ submission_id: 7, before: "pending", after: "approved" }) };
    }
    return { ok: true, json: async () => ({ threshold_pct: 20, rows: [row] }) };
  });
  vi.stubGlobal("fetch", fetchMock);
  render(<MemoryRouter><ActorProvider><Review /></ActorProvider></MemoryRouter>);
  return fetchMock;
}

beforeEach(() => localStorage.clear());
afterEach(() => vi.restoreAllMocks());

test("shows the flagged row with its should-cost and risk note; decisions need a name", async () => {
  setup();
  expect(await screen.findByText("BAT-1011")).toBeInTheDocument();
  expect(screen.getByText("+50.0%")).toBeInTheDocument();
  expect(screen.getByText("pending", { selector: ".badge" })).toBeInTheDocument();   // status column shows Pending
  expect(screen.getByText("commodity avg, n=4")).toBeInTheDocument();
  expect(screen.getByText(/1 open risk event/)).toBeInTheDocument();
  expect(screen.getByRole("button", { name: "Approve" })).toBeDisabled();
  expect(screen.getByRole("button", { name: "Reject" })).toBeDisabled();
});

test("approving posts the actor and reason, then confirms it was logged", async () => {
  localStorage.setItem("northpeak.actor", "Kevin");
  const fetchMock = setup();
  await userEvent.type(await screen.findByLabelText(/reason for submission 7/i), "checked quote");
  await userEvent.click(screen.getByRole("button", { name: "Approve" }));

  expect(await screen.findByRole("status")).toHaveTextContent("pending → approved (logged)");
  const post = fetchMock.mock.calls.find(([, init]) => init?.method === "POST")!;
  expect(post[0]).toBe("/api/review/7");
  expect(JSON.parse(post[1]!.body as string)).toEqual({ action: "approve", actor: "Kevin", reason: "checked quote" });
  await waitFor(() => expect(fetchMock.mock.calls.filter(([, i]) => !i?.method).length).toBeGreaterThan(1)); // list reloaded
});

const rows3 = [
  { ...row, submission_id: 7, part_number: "BAT-1011", commodity: "Battery Cell", supplier_name: "Ferncrest Components", submitted_unit_cost: 4.5, should_cost: 3.0, pct_over: 50, risk_note: "1 open risk event (max severity 5)" },
  { ...row, submission_id: 8, part_number: "CON-1013", commodity: "Connector", supplier_name: "Cascade Technologies", submitted_unit_cost: 0.7, should_cost: 0.55, pct_over: 27.3, risk_note: "No open risk events" },
  { ...row, submission_id: 9, part_number: "CON-1019", commodity: "Connector", supplier_name: "Ferncrest Components", submitted_unit_cost: 0.67, should_cost: 0.55, pct_over: 21.8, risk_note: "No open risk events" },
];

test("every column can be filtered, several at once, and the filters can be cleared", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ threshold_pct: 20, rows: rows3 }) })));
  render(<MemoryRouter><ActorProvider><Review /></ActorProvider></MemoryRouter>);
  await screen.findByText("BAT-1011");
  for (const col of ["submission_id", "part_number", "commodity", "supplier_name", "fiscal_period", "submitted_unit_cost",
    "should_cost", "pct_over", "status", "risk_note"]) {
    expect(screen.getByLabelText(`Filter ${col}`)).toBeInTheDocument(); // a filter box for every data column
  }
  const visible = () => ["BAT-1011", "CON-1013", "CON-1019"].filter((p) => screen.queryByText(p));

  await userEvent.type(screen.getByLabelText("Filter commodity"), "=connector");
  expect(visible()).toEqual(["CON-1013", "CON-1019"]);
  expect(screen.getByText("2 of 3 pending and flagged")).toBeInTheDocument();

  await userEvent.type(screen.getByLabelText("Filter supplier_name"), "ferncrest");   // second column: AND
  expect(visible()).toEqual(["CON-1019"]);

  await userEvent.click(screen.getByRole("button", { name: /clear 2 column filters/i }));
  expect(visible()).toEqual(["BAT-1011", "CON-1013", "CON-1019"]);

  await userEvent.type(screen.getByLabelText("Filter pct_over"), ">25");               // numeric on a computed column
  expect(visible()).toEqual(["BAT-1011", "CON-1013"]);
  await userEvent.clear(screen.getByLabelText("Filter pct_over"));
  await userEvent.type(screen.getByLabelText("Filter risk_note"), "open risk event (");  // text on the note
  expect(visible()).toEqual(["BAT-1011"]);
  await userEvent.type(screen.getByLabelText("Filter part_number"), "zzz");
  expect(await screen.findByText(/no rows match/i)).toBeInTheDocument();
});

test("an invalid numeric filter is marked and ignored rather than hiding every row", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ threshold_pct: 20, rows: rows3 }) })));
  render(<MemoryRouter><ActorProvider><Review /></ActorProvider></MemoryRouter>);
  await screen.findByText("BAT-1011");
  await userEvent.type(screen.getByLabelText("Filter pct_over"), ">abc");
  expect(screen.getByLabelText("Filter pct_over")).toHaveAttribute("aria-invalid", "true");
  expect(screen.getByText("CON-1013")).toBeInTheDocument();
});

const partOrder = () => screen.getAllByText(/^(BAT|CON)-\d+$/).map((e) => e.textContent);
const header = (name: string) => screen.getByRole("columnheader", { name: new RegExp(`^${name}`) });

test("columns sort ascending, then descending; the default is largest pct_over first", async () => {
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ threshold_pct: 20, rows: rows3 }) })));
  render(<MemoryRouter><ActorProvider><Review /></ActorProvider></MemoryRouter>);
  await screen.findByText("BAT-1011");
  expect(header("pct_over")).toHaveAttribute("aria-sort", "descending");
  expect(partOrder()).toEqual(["BAT-1011", "CON-1013", "CON-1019"]);        // 50, 27.3, 21.8

  await userEvent.click(within(header("pct_over")).getByRole("button"));   // same column again: flips
  expect(header("pct_over")).toHaveAttribute("aria-sort", "ascending");
  expect(partOrder()).toEqual(["CON-1019", "CON-1013", "BAT-1011"]);

  await userEvent.click(within(header("part_number")).getByRole("button"));  // new column: ascending first
  expect(header("part_number")).toHaveAttribute("aria-sort", "ascending");
  expect(header("pct_over")).not.toHaveAttribute("aria-sort");
  expect(partOrder()).toEqual(["BAT-1011", "CON-1013", "CON-1019"]);
  await userEvent.click(within(header("part_number")).getByRole("button"));
  expect(partOrder()).toEqual(["CON-1019", "CON-1013", "BAT-1011"]);

  await userEvent.click(within(header("supplier_name")).getByRole("button")); // text: Cascade before Ferncrest
  expect(partOrder()[0]).toBe("CON-1013");
});

test("numbers sort as numbers, not as text, and sorting works together with filters", async () => {
  const rows = [
    { ...rows3[0], submission_id: 10, part_number: "BAT-1010" },
    { ...rows3[1], submission_id: 9, part_number: "CON-1009" },
    { ...rows3[2], submission_id: 100, part_number: "CON-1100" },
  ];
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ threshold_pct: 20, rows }) })));
  render(<MemoryRouter><ActorProvider><Review /></ActorProvider></MemoryRouter>);
  await screen.findByText("BAT-1010");
  await userEvent.click(within(header("submission_id")).getByRole("button"));
  expect(partOrder()).toEqual(["CON-1009", "BAT-1010", "CON-1100"]);         // 9, 10, 100 (text order would be 10, 100, 9)

  await userEvent.type(screen.getByLabelText("Filter part_number"), "CON");   // filter keeps the sort
  expect(partOrder()).toEqual(["CON-1009", "CON-1100"]);
});

test("a plain number in a number column finds exactly that value, not every value containing it", async () => {
  const rows = [
    { ...rows3[0], submission_id: 5, part_number: "BAT-1005" },
    { ...rows3[1], submission_id: 25, part_number: "CON-1025" },
    { ...rows3[2], submission_id: 35, part_number: "CON-1035" },
  ];
  vi.stubGlobal("fetch", vi.fn(async () => ({ ok: true, json: async () => ({ threshold_pct: 20, rows }) })));
  render(<MemoryRouter><ActorProvider><Review /></ActorProvider></MemoryRouter>);
  await screen.findByText("BAT-1005");
  await userEvent.type(screen.getByLabelText("Filter submission_id"), "5");
  expect(screen.getByText("BAT-1005")).toBeInTheDocument();
  expect(screen.queryByText("CON-1025")).not.toBeInTheDocument();
  expect(screen.queryByText("CON-1035")).not.toBeInTheDocument();
});
