"""What this family scrapes: public reports of eGramSwaraj (egramswaraj.gov.in, Ministry of Panchayati Raj).

- geotag: the "Geo Tagged Asset Report". For every gram panchayat and plan year, each work the panchayat geo-tagged (activity code,
  activity name, approved cost, asset, stage, photo path with latitude and longitude, upload time). Plan years with data:
  2023-2024 (1,579,233 tags in 224,416 GPs), 2024-2025 (1,575,960 in 223,492), 2025-2026 (1,151,457 in 187,839), 2026-2027 (started).
  Years before 2023-2024 show 0. The queue starts with one item per plan year and grows by itself (state, district, block, GP).
  Photos are not fetched: each row keeps the photo path (getMactionPhoto.do?imgId=...).

Not collected: the action plan, activity status and expenditure reports ask for a captcha (never passed).
Runners reach the site through the pool's Mumbai proxies (proxy="IN"), as the other Indian government sites.
"""
import json
from pathlib import Path

FAMILY = json.loads((Path(__file__).parent / "scrape.json").read_text())["family"]
YEARS = ["2023-2024", "2024-2025", "2025-2026", "2026-2027"]

PROJECTS = [
    {
        "name": f"{FAMILY}-geotag",
        "title": "eGramSwaraj geo-tagged gram panchayat works (activity, approved cost, stage, photo GPS), plan years 2023-24 onward",
        "task": "geotag",
        "target": "egramswaraj.gov.in",
        "env": {},
        "probe": f"{FAMILY}:egramswaraj.gov.in",
        "unit_label": "list or GP page", "record_label": "GP year",
        "items": [{"key": f"year-{y}", "payload": {"year": y}} for y in YEARS],
        "workers": 2,
        "delay_ms": 1500,
    },
]

PROBES = [{"name": f"{FAMILY}:egramswaraj.gov.in", "url": "https://egramswaraj.gov.in/geoTaggingStateReport.do?year=2024-2025",
           "expect": "totalGpCount"}]
