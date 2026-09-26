import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = Path(os.environ.get("NORTHPEAK_DATA_DIR", ROOT / "data"))
SCHEMA_PATH = ROOT / "schema" / "schema.sql"
DB_PATH = Path(os.environ.get("NORTHPEAK_DB", ROOT / "northpeak.db"))

# A submission is flagged when its unit cost is more than this % above its should-cost.
FLAG_THRESHOLD_PCT = float(os.environ.get("NORTHPEAK_FLAG_PCT", "20"))
# material + labor + overhead must equal the submitted unit cost within this tolerance.
COST_SUM_TOLERANCE = 0.005
ALLOWED_CURRENCIES = {"USD"}
MAX_UPLOAD_BYTES = 5 * 1024 * 1024
