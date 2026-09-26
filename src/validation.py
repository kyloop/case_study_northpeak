"""Row-level validation for supplier cost uploads.

Every problem on a row is reported (we do not stop at the first one), each tagged with the
field it belongs to, so the user can fix a whole row in one pass.
"""
from __future__ import annotations

import math
import re

from . import config

REQUIRED_COLUMNS = [
    "part_number", "supplier_name", "fiscal_period", "submitted_unit_cost",
    "material_cost", "labor_cost", "overhead_cost", "margin_pct", "currency", "submitted_by",
]
COST_FIELDS = ["submitted_unit_cost", "material_cost", "labor_cost", "overhead_cost"]

FISCAL_RE = re.compile(r"^FY\d{2}-Q[1-4]$")
EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _to_number(s: str):
    try:
        n = float(s)
    except ValueError:
        return None
    return n if math.isfinite(n) else None


def validate_row(raw: dict, parts_by_number: dict, suppliers_by_name: dict):
    """Return (values, errors). `values` is only meaningful when `errors` is empty.

    parts_by_number / suppliers_by_name are keyed by lower-cased text, valued by the id.
    """
    errors = []

    def err(field, msg):
        errors.append({"field": field, "message": msg})

    r = {c: _text(raw.get(c)) for c in REQUIRED_COLUMNS}
    values = {}

    # Required fields: report each blank one and skip the deeper checks on it.
    for c in REQUIRED_COLUMNS:
        if r[c] == "":
            err(c, f"{c} is required but is blank")

    if r["part_number"]:
        pid = parts_by_number.get(r["part_number"].lower())
        if pid is None:
            err("part_number", f"part '{r['part_number']}' does not exist in the parts master")
        values["part_id"] = pid

    if r["supplier_name"]:
        sid = suppliers_by_name.get(r["supplier_name"].lower())
        if sid is None:
            err("supplier_name", f"supplier '{r['supplier_name']}' does not exist in the suppliers master")
        values["supplier_id"] = sid

    if r["fiscal_period"]:
        fp = r["fiscal_period"].upper()
        if not FISCAL_RE.match(fp):
            err("fiscal_period", f"'{r['fiscal_period']}' is not a valid fiscal period (expected FY##-Q1..Q4, e.g. FY26-Q4)")
        values["fiscal_period"] = fp

    nums = {}
    for c in COST_FIELDS:
        if r[c] == "":
            continue
        n = _to_number(r[c])
        if n is None:
            err(c, f"{c} '{r[c]}' is not a number")
        elif n <= 0:
            err(c, f"{c} must be a positive number (got {r[c]})")
        else:
            nums[c] = n
    values.update(nums)

    if r["margin_pct"] != "":
        m = _to_number(r["margin_pct"])
        if m is None:
            err("margin_pct", f"margin_pct '{r['margin_pct']}' is not a number")
        elif not 0 <= m < 100:
            err("margin_pct", f"margin_pct must be between 0 and 100 (got {r['margin_pct']})")
        else:
            values["margin_pct"] = m

    if r["currency"]:
        cur = r["currency"].upper()
        if cur not in config.ALLOWED_CURRENCIES:
            err("currency", f"currency '{r['currency']}' is not supported (allowed: {', '.join(sorted(config.ALLOWED_CURRENCIES))})")
        values["currency"] = cur

    if r["submitted_by"]:
        if not EMAIL_RE.match(r["submitted_by"]):
            err("submitted_by", f"submitted_by '{r['submitted_by']}' is not a valid email address")
        values["submitted_by"] = r["submitted_by"]

    # Cross-field check, only when all four cost fields parsed as positive numbers.
    if all(c in nums for c in COST_FIELDS):
        parts_sum = nums["material_cost"] + nums["labor_cost"] + nums["overhead_cost"]
        if abs(parts_sum - nums["submitted_unit_cost"]) > config.COST_SUM_TOLERANCE:
            err("submitted_unit_cost",
                f"submitted_unit_cost {nums['submitted_unit_cost']:g} does not equal material + labor + overhead ({parts_sum:.3f})")

    return values, errors
