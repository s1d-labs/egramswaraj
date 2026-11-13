"""Parsing tests on a saved GP page: fast, no network."""
from pathlib import Path

import geotag

PAGES = Path(__file__).parent / "pages"


def test_gp_page_rows():
    d = geotag.parse_gp((PAGES / "gp-2024-273090.html").read_text(encoding="utf-8"))
    assert d["columns"][:3] == ["S.No", "Activity Code", "Activity Name"]
    rows = d["rows"]
    assert rows and all(r["activity_code"].isdigit() for r in rows)
    assert all(r["photo"].startswith("getMactionPhoto.do") for r in rows)
    assert all(r["lat"] and 6 < r["lat"] < 38 and 68 < r["lon"] < 98 for r in rows if r["lat"])
    assert [r["sno"] for r in rows] == list(range(1, len(rows) + 1))


def test_empty_page_gives_nothing():
    assert geotag.parse_gp("<html><body>No data</body></html>")["rows"] == []
