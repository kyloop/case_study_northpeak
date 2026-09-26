-- NorthPeak Components supplier cost tool: SQLite schema.
-- Written from the table list in the brief (no schema.sql was supplied).
-- Two hard rules from the brief are enforced here, not just in code:
--   1. submitted costs and should-cost estimates live in separate tables;
--   2. approvals/rejections are appended to audit_log (UPDATE/DELETE blocked by triggers).

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS suppliers (
    supplier_id  INTEGER PRIMARY KEY,
    name         TEXT NOT NULL UNIQUE,
    region       TEXT,
    tier         TEXT,
    risk_rating  TEXT,
    created_at   TEXT
);

CREATE TABLE IF NOT EXISTS facilities (
    facility_id    INTEGER PRIMARY KEY,
    supplier_id    INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    name           TEXT NOT NULL,
    country        TEXT,
    latitude       REAL,
    longitude      REAL,
    facility_type  TEXT
);

CREATE TABLE IF NOT EXISTS parts (
    part_id      INTEGER PRIMARY KEY,
    part_number  TEXT NOT NULL UNIQUE,
    description  TEXT,
    commodity    TEXT NOT NULL,
    uom          TEXT,
    target_cost  REAL
);

-- Raw, as-submitted supplier costs. Nothing computed by the tool is ever written here
-- (only `status` changes, and every change is mirrored in audit_log).
CREATE TABLE IF NOT EXISTS cost_submissions (
    submission_id        INTEGER PRIMARY KEY,
    part_id              INTEGER NOT NULL REFERENCES parts(part_id),
    supplier_id          INTEGER NOT NULL REFERENCES suppliers(supplier_id),
    fiscal_period        TEXT NOT NULL CHECK (fiscal_period GLOB 'FY[0-9][0-9]-Q[1-4]'),
    submitted_unit_cost  REAL NOT NULL CHECK (submitted_unit_cost > 0),
    material_cost        REAL NOT NULL CHECK (material_cost > 0),
    labor_cost           REAL NOT NULL CHECK (labor_cost > 0),
    overhead_cost        REAL NOT NULL CHECK (overhead_cost > 0),
    margin_pct           REAL NOT NULL,
    currency             TEXT NOT NULL,
    submitted_by         TEXT NOT NULL,
    submitted_at         TEXT NOT NULL,   -- seed rows: submission date; uploaded rows: upload timestamp (UTC)
    status               TEXT NOT NULL DEFAULT 'pending'
                         CHECK (status IN ('pending', 'approved', 'rejected')),
    source_file          TEXT
);
-- Idempotency: two rows with identical content cannot both exist, so re-uploading the same
-- row never creates a second copy. (The submitter email is compared case-insensitively.)
CREATE UNIQUE INDEX IF NOT EXISTS uq_sub_content ON cost_submissions
    (part_id, supplier_id, fiscal_period, submitted_unit_cost, material_cost, labor_cost,
     overhead_cost, margin_pct, currency, submitted_by COLLATE NOCASE);
CREATE INDEX IF NOT EXISTS idx_sub_part ON cost_submissions(part_id);
CREATE INDEX IF NOT EXISTS idx_sub_supplier ON cost_submissions(supplier_id);
CREATE INDEX IF NOT EXISTS idx_sub_status ON cost_submissions(status);

-- Calculated estimates, one current row per part. Separate from cost_submissions.
-- should_cost is the average approved unit cost of the part's commodity; sample_size is how many
-- approved submissions that average is based on.
CREATE TABLE IF NOT EXISTS should_cost_estimates (
    part_id            INTEGER PRIMARY KEY REFERENCES parts(part_id),
    commodity          TEXT NOT NULL,
    should_cost        REAL NOT NULL,
    sample_size        INTEGER NOT NULL,
    computed_at        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS risk_events (
    event_id     INTEGER PRIMARY KEY,
    facility_id  INTEGER NOT NULL REFERENCES facilities(facility_id),
    event_type   TEXT NOT NULL,
    severity     INTEGER,
    event_date   TEXT,
    description  TEXT,
    status       TEXT
);

-- Append-only record of every approve/reject decision.
CREATE TABLE IF NOT EXISTS audit_log (
    audit_id             INTEGER PRIMARY KEY AUTOINCREMENT,
    submission_id        INTEGER NOT NULL REFERENCES cost_submissions(submission_id),
    action               TEXT NOT NULL CHECK (action IN ('approve', 'reject')),
    actor                TEXT NOT NULL CHECK (length(trim(actor)) > 0),
    acted_at             TEXT NOT NULL,
    before_status        TEXT NOT NULL,
    after_status         TEXT NOT NULL,
    reason               TEXT,
    -- context frozen at decision time, so the log stays meaningful after estimates are recomputed
    submitted_unit_cost  REAL NOT NULL,
    should_cost          REAL,
    pct_over_should_cost REAL
);
CREATE INDEX IF NOT EXISTS idx_audit_sub ON audit_log(submission_id);

CREATE TRIGGER IF NOT EXISTS audit_log_no_update BEFORE UPDATE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;
CREATE TRIGGER IF NOT EXISTS audit_log_no_delete BEFORE DELETE ON audit_log
BEGIN SELECT RAISE(ABORT, 'audit_log is append-only'); END;

-- One row per file upload (summary + the report shown to the user).
CREATE TABLE IF NOT EXISTS uploads (
    upload_id     INTEGER PRIMARY KEY AUTOINCREMENT,
    filename      TEXT NOT NULL,
    file_sha256   TEXT NOT NULL,
    uploaded_at   TEXT NOT NULL,
    uploaded_by   TEXT,
    rows_total    INTEGER NOT NULL,
    rows_saved    INTEGER NOT NULL,
    rows_duplicate INTEGER NOT NULL,
    rows_failed   INTEGER NOT NULL,
    report_json   TEXT NOT NULL
);
