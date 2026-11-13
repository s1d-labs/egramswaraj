# egramswaraj

Scrape-pool family for public reports of eGramSwaraj (egramswaraj.gov.in, Ministry of Panchayati Raj).

| Project | Task | What |
|---|---|---|
| `egramswaraj-geotag` | `geotag` | Geo Tagged Asset Report: for each gram panchayat and plan year, every geo-tagged work (activity code, activity name, approved cost, asset, stage, photo path with latitude and longitude, upload time). Plan years 2023-2024 to 2026-2027. |

- The queue starts with one item per plan year. Each list item (state, district, block) queues the next level; the block list
  queues one item per gram panchayat that has geo-tagged works.
- One record per GP and plan year: id `gp-<start year>-<GP code>` (the GP code is the LGD code). Rows keep every column of the page.
- Files in the family bucket: `tree/<plan year>/<level>-<code>.json` (counts as served) and `raw/<start year>/<GP code>.html.gz`.
- Photos are not fetched. Each row keeps the photo path.
- The action plan, activity status and expenditure reports ask for a captcha. They are not collected.

Check: `python -m pytest tests` and `scrape-check --project egramswaraj-geotag --task geotag --item '{"key":"gp-2024-273090","payload":{"start_year":"2024","gp":273090}}'`.
Local run of one GP page: `python geotag.py --local 273090 2024`.
