"""Bulk upload pipeline: read CSV/Excel -> validate every row -> save valid rows -> report."""
from __future__ import annotations

import csv
import hashlib
import io
import json
from pathlib import Path

from . import db, validation


class UploadError(Exception):
    """The file as a whole cannot be processed (unreadable, wrong type, missing columns)."""


def read_rows(filename: str, data: bytes):
    """Return a list of {column: value} dicts, one per non-blank data row."""
    ext = Path(filename).suffix.lower()
    if ext == ".csv":
        raw_rows = _read_csv(data)
    elif ext in (".xlsx", ".xlsm"):
        raw_rows = _read_xlsx(data)
    elif ext == ".xls":
        raise UploadError("Legacy .xls files are not supported; save the file as .xlsx or .csv.")
    else:
        raise UploadError(f"Unsupported file type '{ext or filename}'. Upload a .csv or .xlsx file.")

    if not raw_rows:
        raise UploadError("The file is empty.")
    header = raw_rows[0]
    header = [str(h).strip().lower() if h is not None else "" for h in header]
    missing = [c for c in validation.REQUIRED_COLUMNS if c not in header]
    if missing:
        raise UploadError("Missing required column(s): " + ", ".join(missing))

    rows = []
    for cells in raw_rows[1:]:
        rec = {h: (cells[i] if i < len(cells) else None) for i, h in enumerate(header) if h}
        if all(v is None or str(v).strip() == "" for v in rec.values()):
            continue  # fully blank row, ignore
        rows.append(rec)
    return rows


def _read_csv(data: bytes):
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError:
        raise UploadError("The CSV is not valid UTF-8 text.")
    return list(csv.reader(io.StringIO(text, newline="")))


def _read_xlsx(data: bytes):
    from openpyxl import load_workbook
    try:
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
    except Exception:
        raise UploadError("Could not open the file as an Excel workbook.")
    ws = wb.worksheets[0]  # first sheet only
    out = [list(row) for row in ws.iter_rows(values_only=True)]
    # skip leading fully-empty rows so the header can start below row 1
    while out and all(c is None or str(c).strip() == "" for c in out[0]):
        out.pop(0)
    return out


def process_upload(conn, filename: str, data: bytes, uploaded_by: str = "") -> dict:
    """Validate and save an upload. Returns the per-row report (also persisted in `uploads`)."""
    file_hash = hashlib.sha256(data).hexdigest()
    rows = read_rows(filename, data)

    parts = {r["part_number"].lower(): r["part_id"] for r in conn.execute("SELECT part_id, part_number FROM parts")}
    suppliers = {r["name"].lower(): r["supplier_id"] for r in conn.execute("SELECT supplier_id, name FROM suppliers")}
    seen_before = conn.execute("SELECT upload_id FROM uploads WHERE file_sha256 = ?", (file_hash,)).fetchone()

    now = db.now_iso()
    report_rows = []
    counts = {"saved": 0, "duplicate": 0, "failed": 0}

    for n, raw in enumerate(rows, start=1):
        values, errors = validation.validate_row(raw, parts, suppliers)
        entry = {
            "row": n,
            # the row exactly as uploaded, keyed by the CSV column names
            "values": {c: ("" if raw.get(c) is None else str(raw[c]).strip()) for c in validation.REQUIRED_COLUMNS},
            "errors": errors, "warnings": [], "submission_id": None,
        }
        if errors:
            entry["status"] = "failed"
        else:
            existing_id = db.find_duplicate(conn, values)
            if existing_id:
                entry["status"] = "duplicate"
                entry["submission_id"] = existing_id
            else:
                same_key = [r["submission_id"] for r in conn.execute(
                    "SELECT submission_id FROM cost_submissions WHERE part_id=? AND supplier_id=? AND fiscal_period=?",
                    (values["part_id"], values["supplier_id"], values["fiscal_period"]))]
                if same_key:
                    entry["warnings"].append(
                        "another submission with different values already exists for this part, supplier and "
                        "period (id " + ", ".join(map(str, same_key)) + "); saved as a new pending submission")
                entry["submission_id"] = db.insert_submission(
                    conn, values, source_file=filename, submitted_at=now)
                entry["status"] = "saved"
        counts[entry["status"]] += 1
        report_rows.append(entry)

    report = {
        "filename": filename, "sha256": file_hash,
        "identical_file_seen_before": bool(seen_before),
        "summary": {"total": len(rows), **counts},
        "rows": report_rows,
    }
    cur = conn.execute(
        """INSERT INTO uploads (filename, file_sha256, uploaded_at, uploaded_by, rows_total,
                                rows_saved, rows_duplicate, rows_failed, report_json)
           VALUES (?,?,?,?,?,?,?,?,?)""",
        (filename, file_hash, now, uploaded_by or None, len(rows), counts["saved"],
         counts["duplicate"], counts["failed"], json.dumps(report)))
    report["upload_id"] = cur.lastrowid
    conn.commit()
    return report
