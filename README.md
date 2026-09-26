# NorthPeak Components: Supplier Cost Tool

A small tool that replaces part of the manual "open each supplier file and copy numbers into a
spreadsheet" process: a validated bulk-upload pipeline, a cost-review screen with an audit trail,
and a one-line risk note per supplier. All data is fictional. The requirements come from the case-study brief.

## Run it

Needs Python 3.9+ and Node 20+ (Node is only needed to build the React frontend).

```bash
# 1. Create and activate a virtual environment, then install the Python packages
python3 -m venv .venv
source .venv/bin/activate                    # Windows: .venv\Scripts\activate
pip install -r requirements.txt

# 2. Build the frontend (needs Node 20+; see below if you don't have it)
cd frontend && npm install && npm run build && cd ..

# 3. Start the app
python -m src serve                          # http://127.0.0.1:5000  (API + built React app)
```

Activate the environment (`source .venv/bin/activate`) in every new terminal before running `python`,
`pip` or `npm` commands from this README; the commands below assume it is active. Without activating,
`python` is the system Python, which does not have the packages installed. (Alternatively, call
`.venv/bin/python` and `.venv/bin/pytest` directly.) Type `deactivate` to leave the environment.

**No Node installed?** This puts Node and npm inside the virtual environment (no admin rights, no global
install). Run it after step 1, then continue with step 2:

```bash
pip install nodeenv && nodeenv -p --node=22.11.0
```

The SQLite database (`northpeak.db`) is created and seeded from `data/` on first start
(20 suppliers, 28 facilities, 45 parts, 250 historical submissions, 15 risk events, plus computed
should-costs). `python -m src init --reset` rebuilds it from scratch; `python -m src init --reset --empty`
creates the tables with no data at all. Seeding happens only when the database file is brand new, so an
emptied database stays empty across restarts. Note that an empty database has no parts or suppliers, so
every uploaded row fails validation until the master data is loaded.

**Frontend development** (hot reload): run `python -m src serve` in one terminal and
`cd frontend && npm run dev` in another, then open http://localhost:5173 (Vite proxies `/api`
to port 5000).

**UI** (React + TypeScript + Vite, in `frontend/`)

| Page | What it does |
|---|---|
| `/upload` | Upload a `.csv` or `.xlsx`; shows the per-row validation report using the file's own column names, with each failing cell highlighted and the reason stated in it. Click a header to sort, and use the filter box under each column (e.g. `result` = `=failed`, `submitted_unit_cost` `>5`) |
| `/review` | Flagged submissions with Approve / Reject; click a column header to sort (default: largest `pct_over` first) and use the filter box under every column (same rules as the data tables; combine several); set "Working as" (top right) first |
| `/data` | Read-only browser for all tables: a filter box under every column header (combine several; all must match), global search, sort, paging; suppliers include the risk note |

**Sticky header** (toggle in the top bar, on by default): in every table, the column headings and filter boxes stay pinned while
the rows scroll (the table scrolls inside its own box; in the split-view panels the search box and summary stay in view too).
Turn it off and tables simply grow with their rows. The choice is remembered.

**Split view** (toggle in the header, on by default): the current page (Upload or Review) on the left and,
on the right, two stacked data tables with a draggable divider between them.

- Each table has its own picker, column filters, search, sort and paging.
- **The bottom table follows the top one.** Filter the top table (say `parts` where `commodity` is
  `=Connector`) and the bottom (say `cost_submissions`) shows only the records related to those rows.
  Click a row in the top table to narrow the bottom to just that row's related records; click again to clear.
  Untick "follow top table" for an independent bottom table, or "hide" to drop it.
- Relations come from the schema's keys: suppliers to facilities, cost_submissions, parts and
  (through those) risk_events; parts to cost_submissions and should_cost_estimates; facilities to
  risk_events; cost_submissions to audit_log; uploads to cost_submissions (by file name). Links work in
  both directions and follow at most two steps, so e.g. suppliers to risk_events goes via facilities.
  Tables with no such link (say parts and risk_events) show a "Not linked" note.
- After an upload the top table jumps to `cost_submissions` (newest first); after an approve/reject to
  `audit_log`. Both panes refresh after every change. Below 900px wide the panel stacks underneath.

The backend is a JSON API (`/api/upload`, `/api/review`, `/api/tables`); interactive docs at `/api/docs`.

**Column filters:** all filters must match. On text columns, plain text = contains (case-insensitive), `=text`
exact, `!=text` not equal. On number columns (ids, costs, percentages) a plain number means *equals*: `5` finds 5
(and 5.0) but not 25 or 5.5; `=5` and `!=5` also compare as numbers; `>5`, `>=5`, `<5`, `<=5` compare too. Text
typed in a number column falls back to the text rules. Filters apply after a short pause in typing, or straight
away on Enter. The UI has one box per column; the API (`GET /api/tables/{table}?f=column:value&f=...`) also accepts
several filters on the same column, e.g. `f=submitted_unit_cost:>=5&f=submitted_unit_cost:<=6`.

**CLI** (same pipeline, no browser)

```bash
python -m src upload data/bulk_upload_sample_with_errors.csv
python -m src recompute      # rebuild should_cost_estimates
```

## Data

### Provided files (`data/`)

| File | Rows | Columns | Used for |
|---|---|---|---|
| `suppliers.csv` | 20 | `supplier_id`, `name`, `region`, `tier`, `risk_rating`, `created_at` | Supplier master list (14 APAC, 4 EMEA, 2 Americas). |
| `facilities.csv` | 28 | `facility_id`, `supplier_id`, `name`, `country`, `latitude`, `longitude`, `facility_type` | Where each supplier's factories and warehouses are; feeds the risk notes. |
| `parts.csv` | 45 | `part_id`, `part_number`, `description`, `commodity`, `uom`, `target_cost` | Part master list across 7 commodities (Battery Cell 11, Enclosure 10, Connector 8, Sensor Module 7, Camera Module 5, RF Antenna 3, PCB Assembly 1). `target_cost` is not used for should-cost. |
| `cost_submissions.csv` | 250 | `submission_id`, `part_id`, `supplier_id`, `fiscal_period`, `submitted_unit_cost`, `material_cost`, `labor_cost`, `overhead_cost`, `margin_pct`, `currency`, `submitted_by`, `submitted_at`, `status`, `source_file` | Historical submissions that seed the database: periods FY26-Q1 to FY26-Q3, all USD, 171 approved / 52 pending / 27 rejected. |
| `risk_events.csv` | 15 | `event_id`, `facility_id`, `event_type`, `severity`, `event_date`, `description`, `status` | Earthquake, typhoon, flood, labor strike and single-source events tied to a facility (2 open, 5 monitoring, 8 resolved). |
| `bulk_upload_template.csv` | 8 | the upload columns below | A clean upload file (FY26-Q4). |
| `bulk_upload_sample_with_errors.csv` | 8 | the upload columns below | The same shape with 5 deliberately broken rows and 3 valid ones (see "Why each bad row ... is caught"). |
| `generate_dummy_data.py` | | | The generator behind all of the above; see "Test data" for making extra upload files. |

### Upload file format

A `.csv` or `.xlsx` (first sheet) with these ten columns, all required:

| Column | Rule |
|---|---|
| `part_number` | Must exist in `parts`. |
| `supplier_name` | Must exist in `suppliers` (matched ignoring case). |
| `fiscal_period` | Format `FY##-Q1` to `FY##-Q4`, e.g. `FY26-Q4`. |
| `submitted_unit_cost` | Positive number; must equal `material_cost` + `labor_cost` + `overhead_cost` (within 0.005). |
| `material_cost`, `labor_cost`, `overhead_cost` | Positive numbers. |
| `margin_pct` | A number from 0 up to (not including) 100. |
| `currency` | `USD` only. |
| `submitted_by` | A valid email address. |

Uploads identify parts and suppliers by name; the database stores their ids.

### Database tables

| Table | Holds | Comes from |
|---|---|---|
| `suppliers`, `facilities`, `parts`, `risk_events` | Master data | The CSV files above, loaded once; the app only reads them. |
| `cost_submissions` | Raw costs as submitted, with a `status` of pending, approved or rejected | The 250 seed rows plus every valid uploaded row (`source_file` says which file). |
| `should_cost_estimates` | The calculated should-cost, one row per part, kept separate from submissions | Calculated by the tool. |
| `audit_log` | One row per approve or reject decision; cannot be edited or deleted | Written by the Cost Review screen. |
| `uploads` | One row per uploaded file: name, hash, time, uploader, row counts and the validation report | Written by the upload pipeline. |

### Things to know about the data

- `parts` has no `supplier_id`, and there is no supplier-to-part table. The link between a supplier and a part exists only through `cost_submissions`, so any supplier can submit any part.
- The seed statuses were assigned at random, independent of price, so some approved rows are well above their should-cost. Likewise `fiscal_period` was chosen independently of `submitted_at`, so the two often disagree.
- The seed data has 34 cases of the same part, supplier and period submitted more than once with different costs. These are treated as legitimate resubmissions.
- Commodities are uneven: `PCB Assembly` has a single part, so its should-cost comes from one part's history.

## Test data

Extra upload test data, a file mixing valid and invalid rows, can be generated with the provided script
without touching the other data files: `python data/generate_dummy_data.py --bulk-test 100` writes
`data/bulk_upload_test_100.csv` (use any row count in place of 100). Running the script with no arguments
regenerates every CSV in `data/` instead.

