import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from src import db  # noqa: E402

DATA = ROOT / "data"


@pytest.fixture
def conn(tmp_path):
    c = db.init_db(tmp_path / "test.db")
    yield c
    c.close()


@pytest.fixture
def app(tmp_path):
    from src.web import create_app
    dist = tmp_path / "dist"
    (dist / "assets").mkdir(parents=True)
    (dist / "index.html").write_text("<html>spa</html>")
    (dist / "assets" / "x.js").write_text("console.log(1)")
    a = create_app(tmp_path / "web.db", dist=dist)
    a.state.db_path = tmp_path / "web.db"
    return a
