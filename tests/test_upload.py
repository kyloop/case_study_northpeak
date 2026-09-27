import io

import pytest
from openpyxl import Workbook

from src import ingest
from conftest import DATA


def upload(conn, name):
    """Run one of the CSV files in data/ through the real upload pipeline and return its report."""
    p = DATA / name
    return ingest.process_upload(conn, p.name, p.read_bytes(), "tester")


def count(conn, table="cost_submissions"):
    """Number of rows currently in a table (cost_submissions unless another is named)."""
    return conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]


def test_seed_loaded(conn):
    """A brand-new database contains the provided data: 250 submissions, 20 suppliers, 45 parts,
    28 facilities and 15 risk events.

    Why: every other test, and the app itself, assume this starting point. If loading the CSVs in
    data/ breaks (or the CSVs change), this fails first and explains why the counts elsewhere are off.
    """
    assert count(conn) == 250
    assert count(conn, "suppliers") == 20 and count(conn, "parts") == 45
    assert count(conn, "facilities") == 28 and count(conn, "risk_events") == 15


def test_clean_template_accepts_all_rows(conn):
    """The clean sample file (bulk_upload_template.csv) saves all 8 rows with no errors.

    Why: the brief supplies this file as the shape the pipeline must accept, so it is the basic
    "the happy path works" check.
    """
    rep = upload(conn, "bulk_upload_template.csv")
    assert rep["summary"] == {"total": 8, "saved": 8, "duplicate": 0, "failed": 0}
    assert count(conn) == 258


def test_error_file_rejects_exactly_the_five_broken_rows(conn):
    """bulk_upload_sample_with_errors.csv: rows 1 to 5 fail for the expected reasons and rows 6 to 8 are saved.

    Expected failures: row 1 unknown part AND unknown supplier, row 2 negative costs, row 3 blank unit
    cost, row 4 blank submitter, row 5 bad fiscal period. Only the 3 valid rows may reach the database.

    Why: the brief says to prove the pipeline catches these five deliberately broken rows and to report
    exactly which row failed and why, and that valid rows in the same file are still saved.
    """
    rep = upload(conn, "bulk_upload_sample_with_errors.csv")
    assert rep["summary"] == {"total": 8, "saved": 3, "duplicate": 0, "failed": 5}
    by_row = {r["row"]: r for r in rep["rows"]}
    assert [r for r in by_row if by_row[r]["status"] == "failed"] == [1, 2, 3, 4, 5]
    fields = {n: {e["field"] for e in by_row[n]["errors"]} for n in range(1, 6)}
    assert fields[1] == {"part_number", "supplier_name"}           # unknown part AND supplier
    assert {"submitted_unit_cost", "overhead_cost"} <= fields[2]  # negative costs
    assert fields[3] == {"submitted_unit_cost"}                    # blank cost
    assert "submitted_by" in fields[4]                             # blank submitter
    assert fields[5] == {"fiscal_period"}                          # bad period
    assert all(by_row[n]["status"] == "saved" for n in (6, 7, 8))
    assert count(conn) == 253  # only the 3 valid rows were saved


def test_reupload_is_idempotent(conn):
    """Uploading the same file twice does not add anything the second time.

    The second upload reports all 8 rows as "already on file", the row count and the sum of costs are
    unchanged, and the report notes that this exact file was seen before.

    Why: the brief requires that uploading the same file twice must not double-count anything.
    """
    upload(conn, "bulk_upload_template.csv")
    total_after_first = conn.execute("SELECT COUNT(*), SUM(submitted_unit_cost) FROM cost_submissions").fetchone()
    rep = upload(conn, "bulk_upload_template.csv")
    assert rep["summary"] == {"total": 8, "saved": 0, "duplicate": 8, "failed": 0}
    assert rep["identical_file_seen_before"]
    assert tuple(conn.execute("SELECT COUNT(*), SUM(submitted_unit_cost) FROM cost_submissions").fetchone()) == tuple(total_after_first)


def test_overlapping_files_do_not_double_count(conn):
    """Two different files that share rows do not double-count them.

    The error sample's 3 valid rows are identical to the first 3 rows of the template, so uploading the
    template and then the error file must report those 3 as duplicates and save nothing new.

    Why: duplicates are detected by row content, not by file name, so this covers the case where the
    same rows arrive in a different file.
    """
    upload(conn, "bulk_upload_template.csv")
    rep = upload(conn, "bulk_upload_sample_with_errors.csv")
    assert rep["summary"]["duplicate"] == 3 and rep["summary"]["saved"] == 0
    assert count(conn) == 258


def test_same_key_different_cost_saved_with_warning(conn):
    """The same part, supplier and period with a different cost is saved as a new row, with a warning.

    Why: the seed data already contains repeated part/supplier/period combinations with different
    costs, so those are treated as legitimate resubmissions and not as duplicates. The warning tells the
    user an earlier submission exists for that combination.
    """
    csv = (DATA / "bulk_upload_template.csv").read_text().splitlines()
    head, first = csv[0], csv[1].split(",")
    first[3], first[4], first[5], first[6] = "3.4", "2.04", "0.611", "0.749"
    upload(conn, "bulk_upload_template.csv")
    rep = ingest.process_upload(conn, "rev.csv", (head + "\n" + ",".join(first)).encode())
    row = rep["rows"][0]
    assert row["status"] == "saved" and row["warnings"]


def make_xlsx(csv_name, tmp_path):
    """Write an .xlsx copy of one of the CSV files in data/ and return its path.

    Numbers are stored as real numeric cells, the way a person would enter them in Excel, so the test
    exercises the Excel reader with numbers and not only text.
    """
    import csv
    wb = Workbook()
    ws = wb.active
    for row in csv.reader(open(DATA / csv_name)):
        # write numbers as real numeric cells, like a spreadsheet user would
        ws.append([float(c) if c.replace(".", "", 1).lstrip("-").isdigit() else (c or None) for c in row])
    p = tmp_path / (csv_name.replace(".csv", ".xlsx"))
    wb.save(p)
    return p


@pytest.mark.parametrize("name", ["bulk_upload_template.csv", "bulk_upload_sample_with_errors.csv"])
def test_excel_gives_same_result_as_csv(conn, tmp_path, name):
    """An Excel copy of each sample file gives exactly the same row-by-row result as the CSV.

    Runs for the clean template and for the file with errors. After the CSV has been saved, the Excel
    copy's rows must be recognised as already on file (nothing saved twice).

    Why: the brief says the pipeline must accept CSV or Excel, and users will not care which they send.
    """
    csv_rep = upload(conn, name)
    p = make_xlsx(name, tmp_path)
    x_rep = ingest.process_upload(conn, p.name, p.read_bytes())
    def shape(rep):
        """Reduce a report to what should match between CSV and Excel: each row's number, and its failing fields."""
        return [(r["row"], r["status"] == "failed" and sorted(e["field"] for e in r["errors"]))
                for r in rep["rows"]]
    assert shape(csv_rep) == shape(x_rep)
    # everything the CSV saved is recognised as already on file when the same data arrives as Excel
    assert x_rep["summary"]["saved"] == 0


@pytest.mark.parametrize("filename,data,msg", [
    ("x.xls", b"junk", "xls"),
    ("x.txt", b"junk", "Unsupported"),
    ("x.csv", b"", "empty"),
    ("x.csv", b"part_number,supplier_name\nA,B\n", "Missing required column"),
    ("x.xlsx", b"not a workbook", "Excel"),
])
def test_unprocessable_files_give_clear_error(conn, filename, data, msg):
    """A file that cannot be read at all fails with a clear message and records nothing.

    The five cases: an old .xls file, an unsupported type (.txt), an empty file, a file missing required
    columns, and a corrupt .xlsx.

    Why: the brief asks for errors that say what is wrong, not just "upload failed", and a bad file must
    not leave a half-finished upload record behind.
    """
    with pytest.raises(ingest.UploadError, match=msg):
        ingest.process_upload(conn, filename, data)
    assert count(conn, "uploads") == 0


def test_empty_database_is_not_reseeded_on_next_start(tmp_path):
    """A database created empty stays empty on the next start, and then rejects every upload row.

    Why: the app seeds data only when the database file is brand new. If it refilled an emptied
    database, "clear everything" could never stick. With no parts or suppliers loaded, each uploaded row
    fails validation with a reason.
    """
    from src import db
    path = tmp_path / "empty.db"
    db.init_db(path, seed_data=False).close()
    conn = db.init_db(path)  # a later start must leave an emptied database alone
    assert all(count(conn, t) == 0 for t in ("suppliers", "parts", "cost_submissions", "should_cost_estimates"))
    # with no master data every row is rejected, with a reason
    rep = upload(conn, "bulk_upload_template.csv")
    assert rep["summary"] == {"total": 8, "saved": 0, "duplicate": 0, "failed": 8}
    conn.close()


def test_existing_database_is_not_reseeded(tmp_path):
    """Emptying the master tables of an existing database does not make the app reload the seed data.

    Why: restarting the app must never wipe or refill a database that already exists, so uploads and
    decisions survive restarts. Only a brand-new file gets seeded.
    """
    from src import db
    path = tmp_path / "x.db"
    db.init_db(path).close()
    c = db.connect(path)
    c.execute("PRAGMA foreign_keys = OFF")
    c.executescript("DELETE FROM cost_submissions; DELETE FROM should_cost_estimates; DELETE FROM risk_events; DELETE FROM facilities; DELETE FROM parts; DELETE FROM suppliers;")
    c.close()
    assert count(db.init_db(path), "suppliers") == 0


def test_identical_row_is_blocked_by_the_database_itself(conn):
    """Inserting a row identical to an existing one is rejected by the database's unique index.

    The e-mail address is compared without regard to case, so the same row with the submitter in
    capitals is also rejected.

    Why: duplicate protection must not depend only on the upload code. The index guarantees it even if
    another code path, or two uploads at the same moment, tries to insert the same row.
    """
    import sqlite3
    from src import db
    row = dict(conn.execute("SELECT * FROM cost_submissions WHERE submission_id = 1").fetchone())
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_submission(conn, row, source_file="x.csv", submitted_at="2026-01-01")
    row["submitted_by"] = row["submitted_by"].upper()  # email compared case-insensitively
    with pytest.raises(sqlite3.IntegrityError):
        db.insert_submission(conn, row, source_file="x.csv", submitted_at="2026-01-01")
