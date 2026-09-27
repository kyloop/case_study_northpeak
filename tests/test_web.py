import pytest
from fastapi.testclient import TestClient

from conftest import DATA


@pytest.fixture
def client(app):
    """A test client for the API: it calls the app's routes in-process, with no real server or network."""
    return TestClient(app)


def post_file(client, name, data, **form):
    """Upload a file to /api/upload the way the browser does (multipart form) and return the response."""
    return client.post("/api/upload", files={"file": (name, data)}, data=form)


def test_upload_returns_row_level_report(client):
    """Uploading the file with errors returns a row-by-row report: 3 saved, 5 failed, with reasons.

    Checks the first failed row names both problems (unknown part and unknown supplier) and that each
    row's values come back keyed by the upload file's own column names, in file order.

    Why: the brief wants to know exactly which rows failed and why, not "upload failed". The React
    upload page builds its table straight from this report.
    """
    r = post_file(client, "errors.csv", (DATA / "bulk_upload_sample_with_errors.csv").read_bytes())
    assert r.status_code == 200
    rep = r.json()
    assert rep["summary"] == {"total": 8, "saved": 3, "duplicate": 0, "failed": 5}
    first = rep["rows"][0]
    assert first["status"] == "failed" and first["values"]["part_number"] == "SNS-9999"
    assert list(first["values"]) == ["part_number", "supplier_name", "fiscal_period", "submitted_unit_cost",
                                     "material_cost", "labor_cost", "overhead_cost", "margin_pct",
                                     "currency", "submitted_by"]  # same names/order as the upload file
    assert {e["field"] for e in first["errors"]} == {"part_number", "supplier_name"}


def test_upload_rejects_bad_file_type(client):
    """Uploading a .pdf is refused with a 400 error and an "Unsupported file type" message.

    Why: the user must be told what is wrong, and the message is what the upload page shows.
    """
    r = post_file(client, "a.pdf", b"x")
    assert r.status_code == 400 and "Unsupported file type" in r.json()["detail"]


def test_upload_without_file(client):
    """Sending an upload request with no file at all is refused (400, or 422 from FastAPI's own check).

    Why: the server must not crash or save anything if the form is submitted empty.
    """
    r = client.post("/api/upload")
    assert r.status_code in (400, 422)


def test_review_list_and_decision_flow(client, app):
    """The whole review cycle through the API: list the queue, be refused without a name, approve a row,
    and see it leave the queue with the decision on record.

    The list carries the threshold, a risk note and the percentage over for each row. Approving moves
    the row from pending to approved, it disappears from the queue, and the audit log shows the actor.

    Why: this is the cost-review half of the brief (flag, approve or reject, and log every decision),
    checked the way the browser uses it.
    """
    body = client.get("/api/review").json()
    assert body["threshold_pct"] == 20 and body["rows"]
    row = body["rows"][0]
    assert row["risk_note"] and row["pct_over"] > 20 and row["status"] == "pending"

    # without a name the decision is refused and nothing is logged
    r = client.post(f"/api/review/{row['submission_id']}", json={"action": "approve"})
    assert r.status_code == 400 and "name" in r.json()["detail"]

    r = client.post(f"/api/review/{row['submission_id']}",
                    json={"action": "approve", "actor": "Kevin", "reason": "ok"})
    assert r.json() == {"submission_id": row["submission_id"], "before": "pending", "after": "approved"}
    assert row["submission_id"] not in [x["submission_id"] for x in client.get("/api/review").json()["rows"]]
    # decided rows are not part of the queue, but the decision is on record
    assert all(x["status"] == "pending" for x in client.get("/api/review").json()["rows"])

    log = client.get("/api/tables/audit_log").json()
    assert log["total"] == 1 and log["rows"][0]["actor"] == "Kevin"


def test_reject_needs_reason(client):
    """Rejecting a submission without a reason is refused with a 400 error that mentions the reason.

    Why: the brief complains there is no record of why something was rejected, so a rejection has to
    carry a reason.
    """
    sid = client.get("/api/review").json()["rows"][0]["submission_id"]
    r = client.post(f"/api/review/{sid}", json={"action": "reject", "actor": "K"})
    assert r.status_code == 400 and "reason" in r.json()["detail"]


def test_every_table_is_browsable(client):
    """The table list has all 8 tables with the right counts, every table loads, and suppliers include
    their calculated risk note.

    Why: the data-browser requirement is that the user can view every table. This catches a table
    that is missing from the list or errors when opened.
    """
    listing = client.get("/api/tables").json()["tables"]
    assert [t["name"] for t in listing] == ["suppliers", "facilities", "parts", "cost_submissions",
                                            "should_cost_estimates", "risk_events", "audit_log", "uploads"]
    counts = {t["name"]: t["count"] for t in listing}
    assert counts["cost_submissions"] == 250 and counts["parts"] == 45
    for t in counts:
        assert client.get(f"/api/tables/{t}").status_code == 200, t
    sup = client.get("/api/tables/suppliers").json()
    assert "risk_note" in sup["columns"] and all(r["risk_note"] for r in sup["rows"])


def test_table_paging_sorting_search(client):
    """Paging, sorting and the global search work, and bad input is handled safely.

    Checks page 2 of a sorted list, that a search narrows the rows, that an invalid sort column is
    ignored (falling back to the first column), and that an unknown table gives 404.

    Why: the sort column and table name are put into SQL, so unknown values must be refused, not passed
    through.
    """
    r = client.get("/api/tables/cost_submissions?sort=submitted_unit_cost&dir=desc&page=2").json()
    assert r["page"] == 2 and r["pages"] == 5 and len(r["rows"]) == 50
    assert client.get("/api/tables/cost_submissions?q=FY26-Q3").json()["total"] < 250
    r = client.get("/api/tables/cost_submissions?sort=1;DROP TABLE x").json()  # bad sort ignored
    assert r["sort"] == "submission_id"
    assert client.get("/api/tables/sqlite_master").status_code == 404


def test_serves_built_frontend_with_spa_fallback(client):
    """The server hands out the built React app: the home page, client-side routes like /review, and
    asset files.

    Also checks that a missing asset is a 404, an unknown /api path is a 404 (not the app page), and
    that a path like /../../etc/passwd cannot read files outside the app folder.

    Why: one Python server has to serve both the API and the web pages, without leaking other files.
    """
    assert "spa" in client.get("/").text
    assert "spa" in client.get("/review").text                      # client-side route
    assert "console.log" in client.get("/assets/x.js").text
    assert client.get("/assets/missing.js").status_code == 404
    assert client.get("/api/nope").status_code == 404               # API misses stay JSON 404s
    assert "spa" in client.get("/../../etc/passwd").text            # no path traversal


def rows(client, url):
    """GET an API address and return its JSON body."""
    return client.get(url).json()


def test_multiple_column_filters_are_anded(client):
    """Filters on several columns all have to match, and each added filter narrows the result.

    Uses period, then period and status, then period, status and supplier, and checks the applied
    filters are echoed back.

    Why: the data tables let users filter several columns at once, and "all must match" is the
    expected meaning.
    """
    everything = rows(client, "/api/tables/cost_submissions")["total"]
    one = rows(client, "/api/tables/cost_submissions?f=fiscal_period:FY26-Q3")
    two = rows(client, "/api/tables/cost_submissions?f=fiscal_period:FY26-Q3&f=status:pending")
    three = rows(client, "/api/tables/cost_submissions?f=fiscal_period:FY26-Q3&f=status:pending&f=supplier_id:=18")
    assert everything > one["total"] > two["total"] >= three["total"] > 0
    assert all(r["fiscal_period"] == "FY26-Q3" and r["status"] == "pending" for r in two["rows"])
    assert all(r["supplier_id"] == 18 for r in three["rows"])
    assert two["filters"] == [{"column": "fiscal_period", "value": "FY26-Q3"}, {"column": "status", "value": "pending"}]


def test_filters_combine_with_search_and_paging(client):
    """Column filters and the global search box apply together.

    Why: a user can type in the search box and in the column filters at the same time, and both must
    count.
    """
    both = rows(client, "/api/tables/cost_submissions?q=FY26-Q3&f=status:approved&page=1")
    assert all(r["status"] == "approved" and r["fiscal_period"] == "FY26-Q3" for r in both["rows"])
    assert both["total"] == rows(client, "/api/tables/cost_submissions?f=status:approved&f=fiscal_period:Q3")["total"]


def test_filter_operators(client):
    """The filter operators work: > for a number, >= with <= for a range, = for an exact match (ignoring
    case), != for not equal, and plain text for "contains".

    Why: these are the rules the filter hint under every table promises.
    """
    hi = rows(client, "/api/tables/cost_submissions?f=submitted_unit_cost:>10")
    assert hi["total"] > 0 and all(r["submitted_unit_cost"] > 10 for r in hi["rows"])
    band = rows(client, "/api/tables/cost_submissions?f=submitted_unit_cost:>=5&f=submitted_unit_cost:<=6")
    assert band["total"] > 0 and all(5 <= r["submitted_unit_cost"] <= 6 for r in band["rows"])
    exact = rows(client, "/api/tables/parts?f=commodity:=connector")  # exact, case-insensitive
    assert exact["total"] == 8 and all(r["commodity"] == "Connector" for r in exact["rows"])
    assert rows(client, "/api/tables/parts?f=commodity:!=Connector")["total"] == 45 - 8
    assert rows(client, "/api/tables/parts?f=commodity:Conn")["total"] == 8  # plain text = contains


def test_filter_edge_cases(client):
    """Unusual filter input is handled safely.

    A % in a filter is taken literally and is not a wildcard, blank filters are ignored, and an unknown
    column, a SQL-injection-style column name, a bad number after > and a hidden column all give 400.

    Why: filter column names go into the SQL query, so they must be checked against the real columns.
    """
    assert rows(client, "/api/tables/parts?f=commodity:%")["total"] == 0        # % is literal, not a wildcard
    assert rows(client, "/api/tables/parts?f=commodity:&f=uom:")["total"] == 45  # blank filters ignored
    assert client.get("/api/tables/parts?f=nope:x").status_code == 400          # unknown column
    assert client.get("/api/tables/parts?f=1;DROP TABLE parts--:x").status_code == 400
    assert client.get("/api/tables/parts?f=target_cost:>abc").status_code == 400
    assert client.get("/api/tables/uploads?f=report_json:x").status_code == 400  # hidden column
    assert rows(client, "/api/tables/parts")["total"] == 45


def link(client, bottom, top, **extra):
    """GET the `bottom` table restricted to rows related to the `top` table's rows, and return the JSON.

    Extra keyword arguments become extra query parameters (for example link_f for the top table's
    filters, or f and q for the bottom table's own filters).
    """
    url = f"/api/tables/{bottom}?link_table={top}" + "".join(f"&{k}={v}" for k, v in extra.items())
    return client.get(url).json()


def test_linked_table_follows_the_top_tables_filters(client):
    """Filtering the top table limits the linked table to the related rows.

    Parts filtered to one commodity: the linked cost_submissions and should_cost_estimates then hold
    only those parts' rows.

    Why: this is the "filter commodity on top, see the relevant parts below" feature of the two-table
    data view.
    """
    # parts filtered to one commodity on top -> the bottom (cost_submissions) shows only those parts' submissions
    parts = rows(client, "/api/tables/parts?f=commodity:=Connector")
    ids = {r["part_id"] for r in parts["rows"]}
    assert len(ids) == 8
    r = link(client, "cost_submissions", "parts", **{"link_f": "commodity:=Connector"})
    assert r["link"] == {"path": ["parts", "cost_submissions"], "note": None}
    assert 0 < r["total"] < 250 and {x["part_id"] for x in r["rows"]} <= ids
    # and the same link shows the parts' estimates
    est = link(client, "should_cost_estimates", "parts", **{"link_f": "commodity:=Connector"})
    assert est["total"] == 8 and all(x["commodity"] == "Connector" for x in est["rows"])


def test_link_works_in_both_directions_and_narrows_to_one_row(client):
    """A link works from parent to child and from child to parent, and one selected row narrows the
    other table to its own related rows.

    Suppliers to facilities and back: facility 1 leads back to supplier 1.

    Why: users click a row in the top table to see just that row's related records, and can start from
    either side.
    """
    fac = link(client, "facilities", "suppliers", **{"link_f": "supplier_id:=1"})
    assert fac["total"] > 0 and all(x["supplier_id"] == 1 for x in fac["rows"])
    back = link(client, "suppliers", "facilities", **{"link_f": "facility_id:=1"})   # child -> parent
    assert [x["supplier_id"] for x in back["rows"]] == [1]                          # facility 1 belongs to supplier 1


def test_link_follows_chains_of_relations(client):
    """A link can pass through a middle table: suppliers to facilities to risk events, and suppliers to
    cost_submissions to parts.

    Why: there is no direct key between those tables. The path through the middle one is what lets
    you see, say, a supplier's risk events.
    """
    r = link(client, "risk_events", "suppliers", **{"link_f": "supplier_id:=8"})    # suppliers -> facilities -> risk_events
    assert r["link"]["path"] == ["suppliers", "facilities", "risk_events"]
    fac_ids = {x["facility_id"] for x in rows(client, "/api/tables/facilities?f=supplier_id:=8")["rows"]}
    assert all(x["facility_id"] in fac_ids for x in r["rows"])
    p = link(client, "parts", "suppliers", **{"link_f": "supplier_id:=18"})         # suppliers -> cost_submissions -> parts
    assert p["link"]["path"] == ["suppliers", "cost_submissions", "parts"] and 0 < p["total"] < 45


def test_link_combines_with_the_bottoms_own_filters_and_search(client):
    """A linked table's own filters and search still apply on top of the link.

    Why: the bottom table has its own filter boxes, and using them must narrow the linked rows further,
    not replace the link.
    """
    r = link(client, "cost_submissions", "parts", **{"link_f": "commodity:=Connector", "f": "status:approved", "q": "FY26-Q3"})
    assert all(x["status"] == "approved" and x["fiscal_period"] == "FY26-Q3" for x in r["rows"])


def test_link_between_unrelated_or_identical_tables_is_a_note_not_an_error(client):
    """Tables with no relation, or the same table, give a "Not linked" note and all their rows, not an error.

    Why: the bottom table may be set to something unrelated to the top one. The user should see a
    plain explanation, and the page must not break.
    """
    same = link(client, "parts", "parts")
    assert same["link"]["path"] is None and "same table" in same["link"]["note"] and same["total"] == 45
    none = link(client, "parts", "risk_events")   # parts -> ... -> risk_events has no chain
    assert none["link"]["path"] is None and "no relation" in none["link"]["note"] and none["total"] == 45


def test_link_upload_records_to_their_submissions_and_bad_link_params(client):
    """An upload record links to the submissions it created (matched by file name), and bad link input
    gives 400.

    Why: this is the cross-check between what was uploaded and what landed in cost_submissions.
    Link table and column names go into SQL, so unknown ones must be refused.
    """
    post_file(client, "u1.csv", (DATA / "bulk_upload_template.csv").read_bytes())
    r = link(client, "cost_submissions", "uploads", **{"link_f": "filename:=u1.csv"})
    assert r["total"] == 8 and all(x["source_file"] == "u1.csv" for x in r["rows"])
    assert client.get("/api/tables/parts?link_table=nope").status_code == 400
    assert client.get("/api/tables/cost_submissions?link_table=parts&link_f=nope:x").status_code == 400
    assert client.get("/api/tables/parts?link_table=cost_submissions&link_f=1;DROP TABLE x:1").status_code == 400


def test_plain_number_on_a_numeric_column_means_equals_not_contains(client):
    """On a number column a plain number means equals: typing 1 in supplier_id finds only supplier 1, not
    10 to 19; 0.434 finds one part and 0.43 finds none.

    Also checks that != excludes the value and that 0.434000 is the same number as 0.434.

    Why: typing 5 and getting 25 and 35 as well was a reported problem, so this pins the fix.
    """
    everything = rows(client, "/api/tables/cost_submissions")["rows"]
    one = rows(client, "/api/tables/cost_submissions?f=supplier_id:1")
    assert one["total"] > 0 and all(r["supplier_id"] == 1 for r in one["rows"])      # not 10..19
    assert one["total"] == rows(client, "/api/tables/cost_submissions?f=supplier_id:=1")["total"]
    others = rows(client, "/api/tables/cost_submissions?f=supplier_id:!=1")
    assert others["total"] + one["total"] == rows(client, "/api/tables/cost_submissions")["total"]
    assert all(r["supplier_id"] != 1 for r in others["rows"])
    # a real REAL column: 0.434 is CON-1008's target_cost, and 0.43 (a prefix of it) must not match
    assert [r["part_number"] for r in rows(client, "/api/tables/parts?f=target_cost:0.434")["rows"]] == ["CON-1008"]
    assert rows(client, "/api/tables/parts?f=target_cost:0.43")["total"] == 0
    assert rows(client, "/api/tables/parts?f=target_cost:0.434000")["total"] == 1     # 0.434000 is the same number
    assert everything  # sanity


def test_numeric_filters_leave_text_columns_alone_and_fall_back_for_non_numbers(client):
    """Text columns keep "contains" matching, and text typed into a number column matches nothing and
    does not crash.

    Why: the equals rule applies only to number columns. Part numbers and fiscal periods still need
    partial matching.
    """
    assert rows(client, "/api/tables/parts?f=part_number:1011")["total"] > 0        # text column: still 'contains'
    assert rows(client, "/api/tables/cost_submissions?f=fiscal_period:26")["total"] > 0
    assert client.get("/api/tables/cost_submissions?f=supplier_id:abc").json()["total"] == 0   # not a number: text rule, no crash
    assert client.get("/api/tables/cost_submissions?f=supplier_id:1&f=fiscal_period:Q3").status_code == 200
