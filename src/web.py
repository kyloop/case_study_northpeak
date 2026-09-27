"""FastAPI backend: JSON API under /api, plus the built React app (frontend/dist) if present."""
from __future__ import annotations

import os
from pathlib import Path

from typing import List

from fastapi import Depends, FastAPI, Form, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel

from . import config, db, ingest, review, risk
from .browse import TABLES, BrowseError, build_where, link_clause, table_columns

PAGE_SIZE = 50
DIST = config.ROOT / "frontend" / "dist"


class Decision(BaseModel):
    action: str
    actor: str = ""
    reason: str = ""


def create_app(db_path=None, dist: Path = DIST) -> FastAPI:
    app = FastAPI(title="NorthPeak Cost Tool", docs_url="/api/docs", redoc_url=None,
                  openapi_url="/api/openapi.json")
    db_path = db_path or config.DB_PATH
    db.init_db(db_path).close()

    def get_conn():
        # One connection per request; FastAPI may run the dependency and the endpoint on
        # different worker threads, so the same-thread check is off (never shared concurrently).
        conn = db.connect(db_path, check_same_thread=False)
        try:
            yield conn
        finally:
            conn.close()

    # ---- Upload (FR-1 / FR-4.1) -------------------------------------------------
    @app.post("/api/upload")
    def upload(file: UploadFile = None, uploaded_by: str = Form(""), conn=Depends(get_conn)):
        if file is None or not file.filename:
            raise HTTPException(400, "Choose a .csv or .xlsx file first.")
        data = file.file.read(config.MAX_UPLOAD_BYTES + 1)
        if len(data) > config.MAX_UPLOAD_BYTES:
            raise HTTPException(413, f"File too large (limit {config.MAX_UPLOAD_BYTES // 1024 // 1024} MB).")
        try:
            return ingest.process_upload(conn, file.filename, data, uploaded_by)
        except ingest.UploadError as e:
            raise HTTPException(400, str(e))

    # ---- Cost review (FR-2) -----------------------------------------------------
    @app.get("/api/review")
    def review_list(conn=Depends(get_conn)):
        notes = risk.supplier_risk_notes(conn)
        rows = [dict(r, risk_note=notes[r["supplier_id"]]) for r in review.flagged(conn)]
        return {"threshold_pct": config.FLAG_THRESHOLD_PCT, "rows": rows}

    @app.post("/api/review/{submission_id}")
    def review_decide(submission_id: int, body: Decision, conn=Depends(get_conn)):
        try:
            return review.decide(conn, submission_id, body.action, body.actor, body.reason)
        except review.ReviewError as e:
            raise HTTPException(400, str(e))

    # ---- Data browser (FR-4.2, read-only) ---------------------------------------
    @app.get("/api/tables")
    def tables(conn=Depends(get_conn)):
        return {"tables": [{"name": t, "count": conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]}
                           for t in TABLES]}

    @app.get("/api/tables/{table}")
    def table_rows(table: str, q: str = "", sort: str = "", dir: str = "asc", page: int = 1,
                   f: List[str] = Query([], description="column filter as 'column:value'; repeat to combine"),
                   link_table: str = Query("", description="show only rows related to this other table's rows"),
                   link_q: str = "",
                   link_f: List[str] = Query([], description="filters on link_table, same format as f"),
                   conn=Depends(get_conn)):
        if table not in TABLES:
            raise HTTPException(404, "Unknown table")
        try:
            cols = table_columns(conn, table)
            clauses, args, filters = build_where(conn, table, q, f)
            link = None
            if link_table:
                clause, link_args, link = link_clause(conn, table, link_table, link_q, link_f)
                if clause:
                    clauses.append(clause)
                    args += link_args
        except BrowseError as e:
            raise HTTPException(400, str(e))
        if sort not in cols:  # whitelist: sort is interpolated into SQL
            sort = cols[0]
        direction = "DESC" if dir == "desc" else "ASC"
        page = max(page, 1)
        where = " WHERE " + " AND ".join(clauses) if clauses else ""
        total = conn.execute(f"SELECT COUNT(*) FROM {table}{where}", args).fetchone()[0]
        rows = [dict(r) for r in conn.execute(
            f"SELECT {', '.join(cols)} FROM {table}{where} ORDER BY {sort} {direction} LIMIT ? OFFSET ?",
            args + [PAGE_SIZE, (page - 1) * PAGE_SIZE])]
        if table == "suppliers":
            notes = risk.supplier_risk_notes(conn)
            for r in rows:
                r["risk_note"] = notes[r["supplier_id"]]
            cols = cols + ["risk_note"]
        return {"table": table, "columns": cols, "rows": rows, "total": total, "page": page,
                "pages": max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1), "sort": sort,
                "dir": direction.lower(), "q": q.strip(), "filters": filters, "link": link}

    # ---- React app (built by `npm run build` in frontend/) ----------------------
    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        if path == "api" or path.startswith("api/"):
            raise HTTPException(404, "Not found")
        if not (dist / "index.html").exists():
            raise HTTPException(404, "Frontend not built. Run `npm run build` in frontend/ "
                                     "(or `npm run dev` for development).")
        candidate = (dist / path).resolve()
        if path and candidate.is_file() and dist.resolve() in candidate.parents:
            return FileResponse(candidate)
        if Path(path).suffix:  # a missing asset is a 404, not the app shell
            raise HTTPException(404, "Not found")
        return FileResponse(dist / "index.html")  # client-side routes

    return app


def main():
    import uvicorn
    uvicorn.run(create_app(), host="127.0.0.1", port=int(os.environ.get("PORT", "5000")))
