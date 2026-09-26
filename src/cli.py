"""Command line: init the DB, upload a file, recompute should-costs, or start the web UI."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import config, db, ingest, shouldcost


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="src")
    sub = p.add_subparsers(dest="cmd", required=True)
    i = sub.add_parser("init", help="create and seed the database")
    i.add_argument("--reset", action="store_true", help="delete the existing database first")
    i.add_argument("--empty", action="store_true", help="create the tables but load no data at all")
    u = sub.add_parser("upload", help="run a CSV/Excel file through the upload pipeline")
    u.add_argument("file")
    sub.add_parser("recompute", help="rebuild should_cost_estimates")
    sub.add_parser("serve", help="start the web UI on http://127.0.0.1:5000")
    a = p.parse_args(argv)

    if a.cmd == "serve":
        from .web import main as serve
        serve()
        return 0

    conn = db.init_db(reset=getattr(a, "reset", False), seed_data=not getattr(a, "empty", False))
    if a.cmd == "init":
        print(f"Database ready at {config.DB_PATH}" + (" (empty)" if a.empty else ""))
    elif a.cmd == "recompute":
        print(f"Wrote {shouldcost.recompute(conn)} should-cost estimates")
    elif a.cmd == "upload":
        path = Path(a.file)
        try:
            rep = ingest.process_upload(conn, path.name, path.read_bytes(), "cli")
        except ingest.UploadError as e:
            print(f"Upload rejected: {e}", file=sys.stderr)
            return 1
        s = rep["summary"]
        print(f"{rep['filename']}: {s['total']} rows, {s['saved']} saved, "
              f"{s['duplicate']} duplicate, {s['failed']} failed")
        for r in rep["rows"]:
            for e in r["errors"]:
                print(f"  row {r['row']}: [{e['field']}] {e['message']}")
            for w in r["warnings"]:
                print(f"  row {r['row']}: warning: {w}")
        return 1 if s["failed"] else 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
