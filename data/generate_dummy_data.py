#!/usr/bin/env python3
"""Generates fictional dummy data for the NorthPeak Components case study.

Everything here is invented — no real company, supplier, or person.
Deterministic (fixed seed) so consultants can regenerate/extend it.
Writes CSVs into ./data/ next to this script.
"""
import csv
import random
from datetime import date, timedelta
from pathlib import Path

random.seed(42)
OUT = Path(__file__).parent

SUPPLIER_ADJ = ["Cascade", "Pinnacle", "Vantree", "Meridian", "Northgate", "Silverline",
                "Redwood", "Alder", "Brightpoint", "Ironwood", "Solace", "Ferncrest",
                "Highmark", "Trueline", "Copperfield", "Westbrook", "Clearview", "Ashgrove",
                "Blackstone", "Cobalt"]
SUPPLIER_NOUN = ["Electronics", "Circuits", "Precision", "Sensor Works", "Manufacturing",
                 "Components", "Systems", "Industries", "Technologies", "Assembly"]

COUNTRY_COORDS = {
    "Taiwan": (23.7, 121.0), "Vietnam": (14.1, 108.3), "Malaysia": (4.2, 101.9),
    "Mexico": (23.6, -102.5), "Philippines": (12.9, 121.8), "China": (35.9, 104.2),
    "South Korea": (36.5, 127.8), "Thailand": (15.9, 100.9), "India": (20.6, 79.0),
    "Poland": (51.9, 19.1),
}
COUNTRIES = list(COUNTRY_COORDS.keys())

COMMODITIES = ["Sensor Module", "Battery Cell", "Connector", "PCB Assembly",
               "Camera Module", "RF Antenna", "Enclosure"]
COMMODITY_PREFIX = {"Sensor Module": "SNS", "Battery Cell": "BAT", "Connector": "CON",
                    "PCB Assembly": "PCB", "Camera Module": "CAM", "RF Antenna": "ANT",
                    "Enclosure": "ENC"}
COMMODITY_BASE_COST = {"Sensor Module": 4.20, "Battery Cell": 3.10, "Connector": 0.45,
                        "PCB Assembly": 6.80, "Camera Module": 8.90, "RF Antenna": 1.35,
                        "Enclosure": 2.60}

FISCAL_PERIODS = ["FY26-Q1", "FY26-Q2", "FY26-Q3"]
SUBMITTERS = ["j.alvarez@vendor-portal.example", "m.chen@vendor-portal.example",
              "s.patel@vendor-portal.example", "r.kowalski@vendor-portal.example",
              "t.nakamura@vendor-portal.example", "a.osei@vendor-portal.example"]

def gen_suppliers(n=20):
    rows = []
    used = set()
    for sid in range(1, n + 1):
        while True:
            name = f"{random.choice(SUPPLIER_ADJ)} {random.choice(SUPPLIER_NOUN)}"
            if name not in used:
                used.add(name)
                break
        region = random.choice(["APAC", "APAC", "APAC", "EMEA", "Americas"])  # APAC-heavy, like the real portfolio
        tier = random.choice(["Tier1", "Tier1", "Tier2"])
        risk = random.choices(["Low", "Medium", "High"], weights=[0.5, 0.35, 0.15])[0]
        rows.append([sid, name, region, tier, risk, "2025-01-15"])
    return rows

def gen_facilities(suppliers, n_target=28):
    rows = []
    fid = 1
    for s in suppliers:
        sid = s[0]
        region = s[2]
        candidate_countries = [c for c in COUNTRIES]
        n_fac = 1 if random.random() < 0.55 else 2
        for _ in range(n_fac):
            country = random.choice(candidate_countries)
            lat, lon = COUNTRY_COORDS[country]
            lat += random.uniform(-1.5, 1.5)
            lon += random.uniform(-1.5, 1.5)
            ftype = random.choices(["Fab", "Assembly", "Warehouse"], weights=[0.4, 0.45, 0.15])[0]
            rows.append([fid, sid, f"{s[1]} {ftype} {country[:3].upper()}", country,
                        round(lat, 4), round(lon, 4), ftype])
            fid += 1
            if len(rows) >= n_target:
                return rows
    return rows

def gen_parts(n=45):
    rows = []
    counters = {c: 1000 for c in COMMODITIES}
    for pid in range(1, n + 1):
        commodity = random.choice(COMMODITIES)
        counters[commodity] += random.randint(1, 9)
        part_number = f"{COMMODITY_PREFIX[commodity]}-{counters[commodity]}"
        base = COMMODITY_BASE_COST[commodity]
        target_cost = round(base * random.uniform(0.85, 1.25), 3)
        rows.append([pid, part_number, f"{commodity} rev {random.choice('ABC')}",
                    commodity, "EA", target_cost])
    return rows

def gen_cost_submissions(suppliers, parts, n=250):
    rows = []
    # each supplier plausibly ships 2-4 commodities
    supplier_commodities = {s[0]: random.sample(COMMODITIES, k=random.randint(2, 4)) for s in suppliers}
    parts_by_commodity = {}
    for p in parts:
        parts_by_commodity.setdefault(p[3], []).append(p)

    sid_list = [s[0] for s in suppliers]
    for subid in range(1, n + 1):
        sid = random.choice(sid_list)
        commodities = supplier_commodities[sid]
        commodity = random.choice(commodities)
        candidates = parts_by_commodity.get(commodity, [])
        if not candidates:
            continue
        part = random.choice(candidates)
        target = part[5]
        variance = random.uniform(0.8, 1.35)  # some submissions run well over should-cost, on purpose
        unit_cost = round(target * variance, 3)
        material = round(unit_cost * random.uniform(0.55, 0.7), 3)
        labor = round(unit_cost * random.uniform(0.12, 0.22), 3)
        overhead = round(unit_cost - material - labor, 3)
        margin = round(random.uniform(3.0, 14.0), 2)
        period = random.choice(FISCAL_PERIODS)
        status = random.choices(["approved", "pending", "rejected"], weights=[0.7, 0.2, 0.1])[0]
        days_ago = random.randint(1, 260)
        submitted_at = (date.today() - timedelta(days=days_ago)).isoformat()
        rows.append([subid, part[0], sid, period, unit_cost, material, labor, overhead,
                    margin, "USD", random.choice(SUBMITTERS), submitted_at, status,
                    "historical_seed.csv"])
    return rows

def gen_risk_events(facilities, n=15):
    rows = []
    types = ["earthquake", "typhoon", "flood", "labor_strike", "single_source_dependency"]
    descs = {
        "earthquake": "Regional seismic event near facility; production paused for inspection.",
        "typhoon": "Tropical storm warning issued; port and inbound logistics disrupted.",
        "flood": "Seasonal flooding affected access roads and on-site inventory storage.",
        "labor_strike": "Labor action at facility reduced line throughput for several days.",
        "single_source_dependency": "Facility identified as sole qualified source for this commodity in the region.",
    }
    for eid in range(1, n + 1):
        fac = random.choice(facilities)
        etype = random.choice(types)
        severity = random.randint(1, 5)
        days_ago = random.randint(1, 365)
        event_date = (date.today() - timedelta(days=days_ago)).isoformat()
        status = random.choices(["open", "monitoring", "resolved"], weights=[0.25, 0.25, 0.5])[0]
        rows.append([eid, fac[0], etype, severity, event_date, descs[etype], status])
    return rows

def write_csv(path, header, rows):
    with open(path, "w", newline="") as f:
        w = csv.writer(f)
        w.writerow(header)
        w.writerows(rows)
    print(f"wrote {len(rows)} rows -> {path.name}")

UPLOAD_HEADER = ["part_number", "supplier_name", "fiscal_period", "submitted_unit_cost",
                 "material_cost", "labor_cost", "overhead_cost", "margin_pct", "currency", "submitted_by"]

def gen_bulk_upload_test(n=100, seed=100):
    """A mixed upload file for testing the pipeline: valid rows, rows that should fail (one
    problem each, of many kinds), exact duplicates and same-key resubmissions.

    Reads the existing suppliers.csv / parts.csv so every valid row uses real names, and uses its
    own random generator so it does not disturb the sequence that produced the other files.
    Rows are FY26-Q4 with part+supplier pairs that are not in bulk_upload_template.csv, so this file
    and the template can both be uploaded without colliding.
    """
    rnd = random.Random(seed)
    with open(OUT / "suppliers.csv", newline="") as f:
        suppliers = [r["name"] for r in csv.DictReader(f)]
    with open(OUT / "parts.csv", newline="") as f:
        parts = [(r["part_number"], float(r["target_cost"])) for r in csv.DictReader(f)]
    with open(OUT / "bulk_upload_template.csv", newline="") as f:
        taken = {(r["part_number"], r["supplier_name"]) for r in csv.DictReader(f)}

    pairs = [(p, s) for p in parts for s in suppliers if (p[0], s) not in taken]
    rnd.shuffle(pairs)
    pair_iter = iter(pairs)

    def make(variance=None, period="FY26-Q4"):
        (pn, target), sup = next(pair_iter)
        unit = round(target * (variance or rnd.uniform(0.85, 1.2)), 3)
        material = round(unit * 0.6, 3)
        labor = round(unit * 0.18, 3)
        overhead = round(unit - material - labor, 3)
        return [pn, sup, period, unit, material, labor, overhead,
                round(rnd.uniform(4, 12), 2), "USD", rnd.choice(SUBMITTERS)]

    def broken(kind):
        r = make()
        if kind == "unknown_part": r[0] = f"{rnd.choice(list(COMMODITY_PREFIX.values()))}-9{rnd.randint(100, 999)}"
        elif kind == "unknown_supplier": r[1] = rnd.choice(["Acme Widgets Ltd", "Unknown Supplier Co", "Zenith Parts Inc"])
        elif kind == "negative_unit_cost": r[3] = -abs(r[3])
        elif kind == "zero_cost": r[4] = 0
        elif kind == "negative_component": r[6] = -abs(r[6])
        elif kind == "blank_unit_cost": r[3] = ""
        elif kind == "blank_submitted_by": r[9] = ""
        elif kind == "blank_period": r[2] = ""
        elif kind == "blank_part": r[0] = ""
        elif kind == "blank_supplier": r[1] = ""
        elif kind == "blank_currency": r[8] = ""
        elif kind == "blank_margin": r[7] = ""
        elif kind == "bad_period": r[2] = rnd.choice(["FY26-Q5", "FY2026-Q1", "FY26Q4", "NOT-A-PERIOD", "2026-Q4", "FY26-Q0"])
        elif kind == "non_numeric_cost": r[rnd.choice([3, 4, 5])] = rnd.choice(["abc", "N/A", "12.3.4"])
        elif kind == "cost_sum_mismatch": r[3] = round(r[3] + rnd.uniform(0.5, 2.0), 3)
        elif kind == "bad_currency": r[8] = rnd.choice(["EUR", "JPY", "US$"])
        elif kind == "bad_email": r[9] = rnd.choice(["not-an-email", "m.chen@", "s patel@vendor.example"])
        elif kind == "margin_out_of_range": r[7] = rnd.choice([150, -3.5])
        return r

    # one entry per row that should fail; mix of every check the pipeline performs
    kinds = (["unknown_part"] * 3 + ["unknown_supplier"] * 3 + ["negative_unit_cost"] * 2 + ["zero_cost"]
             + ["negative_component"] * 2 + ["blank_unit_cost"] * 2 + ["blank_submitted_by"] * 2
             + ["blank_period", "blank_part", "blank_supplier", "blank_currency", "blank_margin"]
             + ["bad_period"] * 4 + ["non_numeric_cost"] * 2 + ["cost_sum_mismatch"] * 3
             + ["bad_currency"] * 2 + ["bad_email"] * 2 + ["margin_out_of_range"] * 2)
    scale = n / 100
    n_fail = round(len(kinds) * scale)
    n_dup = round(3 * scale)         # exact repeats of an earlier row in the same file -> "already on file"
    n_revision = round(2 * scale)    # same part+supplier+period, different cost -> saved, with a warning
    n_high = round(12 * scale)       # valid but 35-60% over typical cost -> should be flagged for review
    n_ok = n - n_fail - n_dup - n_revision - n_high

    valid = [make() for _ in range(n_ok)] + [make(rnd.uniform(1.35, 1.6)) for _ in range(n_high)]
    rows = list(valid)
    rows += [list(rnd.choice(valid)) for _ in range(n_dup)]
    for base in rnd.sample(valid, n_revision):
        rev = list(base)
        rev[3] = round(base[3] * 1.05, 3)
        rev[4] = round(rev[3] * 0.6, 3)
        rev[5] = round(rev[3] * 0.18, 3)
        rev[6] = round(rev[3] - rev[4] - rev[5], 3)
        rows.append(rev)
    rows += [broken(kinds[i % len(kinds)]) for i in range(n_fail)]
    rnd.shuffle(rows)
    return rows, {"total": len(rows), "should_fail": n_fail, "exact_duplicates": n_dup,
                  "resubmissions_with_warning": n_revision, "valid_high_cost": n_high, "valid_normal": n_ok}

def main():
    suppliers = gen_suppliers()
    facilities = gen_facilities(suppliers)
    parts = gen_parts()
    submissions = gen_cost_submissions(suppliers, parts)
    risk_events = gen_risk_events(facilities)

    write_csv(OUT / "suppliers.csv",
              ["supplier_id", "name", "region", "tier", "risk_rating", "created_at"], suppliers)
    write_csv(OUT / "facilities.csv",
              ["facility_id", "supplier_id", "name", "country", "latitude", "longitude", "facility_type"], facilities)
    write_csv(OUT / "parts.csv",
              ["part_id", "part_number", "description", "commodity", "uom", "target_cost"], parts)
    write_csv(OUT / "cost_submissions.csv",
              ["submission_id", "part_id", "supplier_id", "fiscal_period", "submitted_unit_cost",
               "material_cost", "labor_cost", "overhead_cost", "margin_pct", "currency",
               "submitted_by", "submitted_at", "status", "source_file"], submissions)
    write_csv(OUT / "risk_events.csv",
              ["event_id", "facility_id", "event_type", "severity", "event_date", "description", "status"],
              risk_events)

    # A clean template for the bulk-upload pipeline consultants must build.
    sample_parts = random.sample(parts, 8)
    sample_suppliers = random.sample(suppliers, 8)
    template_rows = []
    for i, (p, s) in enumerate(zip(sample_parts, sample_suppliers), start=1):
        unit = round(p[5] * random.uniform(0.9, 1.2), 3)
        material = round(unit * 0.6, 3)
        labor = round(unit * 0.18, 3)
        overhead = round(unit - material - labor, 3)
        template_rows.append([p[1], s[1], "FY26-Q4", unit, material, labor, overhead,
                              round(random.uniform(4, 12), 2), "USD", random.choice(SUBMITTERS)])
    write_csv(OUT / "bulk_upload_template.csv",
              ["part_number", "supplier_name", "fiscal_period", "submitted_unit_cost",
               "material_cost", "labor_cost", "overhead_cost", "margin_pct", "currency", "submitted_by"],
              template_rows)

    # A deliberately dirty version of the same template, to test the pipeline's
    # validation/error-reporting (this is the part of the brief graded most closely).
    dirty_rows = [
        ["SNS-9999", "Unknown Supplier Co", "FY26-Q4", 4.50, 2.70, 0.80, 1.00, 8.0, "USD", "x@vendor.example"],  # unknown part + supplier
        [sample_parts[0][1], sample_suppliers[0][1], "FY26-Q4", -1.20, 0.5, 0.2, -1.9, 5.0, "USD", "y@vendor.example"],  # negative cost
        [sample_parts[1][1], sample_suppliers[1][1], "FY26-Q4", "", 1.0, 0.3, 0.2, 6.0, "USD", "z@vendor.example"],  # missing cost
        [sample_parts[2][1], sample_suppliers[2][1], "FY26-Q4", 3.00, 1.0, 0.3, 0.2, 6.0, "USD", ""],  # missing submitter
        [sample_parts[3][1], sample_suppliers[3][1], "NOT-A-PERIOD", 2.50, 1.5, 0.4, 0.6, 7.0, "USD", "w@vendor.example"],  # bad fiscal period
    ] + template_rows[:3]  # plus a few valid rows mixed in
    write_csv(OUT / "bulk_upload_sample_with_errors.csv",
              ["part_number", "supplier_name", "fiscal_period", "submitted_unit_cost",
               "material_cost", "labor_cost", "overhead_cost", "margin_pct", "currency", "submitted_by"],
              dirty_rows)

if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--bulk-test", type=int, metavar="N",
                    help="write only bulk_upload_test_N.csv (N mixed valid/invalid upload rows) and leave the other files alone")
    args = ap.parse_args()
    if args.bulk_test:
        test_rows, info = gen_bulk_upload_test(args.bulk_test)
        write_csv(OUT / f"bulk_upload_test_{args.bulk_test}.csv", UPLOAD_HEADER, test_rows)
        print(info)
    else:
        main()
