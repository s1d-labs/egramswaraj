"""eGramSwaraj geo-tagged works (task `geotag`). The public "Geo Tagged Asset Report" of the Ministry of Panchayati Raj
(egramswaraj.gov.in/geoTaggingReport.do) lists, for each gram panchayat and plan year, every work the panchayat geo-tagged in
mActionSoft: activity code, activity name, administratively approved cost, asset name, stage, photo (path, latitude, longitude)
and upload time. No login, no captcha. The counts tree (state, district, block, GP) is JSON; the GP page is HTML.

Queue items (each list item queues the next level):
  year-<plan year>                         state counts for one plan year ("2024-2025")
  zp-<plan year>-<state>                   district panchayats of a state
  bp-<plan year>-<state>-<zp>              block panchayats of a district
  gl-<plan year>-<state>-<bp>              gram panchayats of a block (only GPs with geo-tagged works)
  gp-<start year>-<gp code>                one GP page: one record, id "gp-<start year>-<gp code>"
Files: tree/<plan year>/<level>-<code>.json (the counts as served), raw/<start year>/<gp code>.html.gz (the GP page).
Local test: python geotag.py --local [gp code] [start year]
"""
import gzip
import html
import json
import os
import re
import signal
import sys
import time

import requests

BASE = "https://egramswaraj.gov.in"
UA = "Mozilla/5.0 (compatible; s1d-labs public records crawl; +https://labs.s1d.me)"
stop = False


def on_signal(*_):
    global stop
    stop = True


def text(s):
    return re.sub(r"\s+", " ", html.unescape(re.sub(r"<[^>]+>", " ", s or ""))).strip()


def num(s):
    try:
        return float(s.split(",")[0].strip())
    except (ValueError, AttributeError):
        return None


def parse_gp(page):
    """Rows of one GP page: a list of dicts, in page order (one row per photo; an activity has a row per stage). Pure."""
    head = [text(h) for h in re.findall(r"(?is)<th[^>]*>(.*?)</th>", page)]
    out = []
    for tr in re.findall(r"(?is)<tr[^>]*>(.*?)</tr>", page):
        tds = re.findall(r"(?is)<td[^>]*>(.*?)</td>", tr)
        if len(tds) < 8 or not text(tds[0]).isdigit():
            continue
        photo = tds[6]
        src = re.search(r'src="([^"]+)"', photo)
        lat = re.search(r"(?i)latitude\s*:\s*(?:&nbsp;)?\s*([0-9.,\s-]+)", photo)
        lon = re.search(r"(?i)longitude\s*:\s*(?:&nbsp;)?\s*([0-9.,\s-]+)", photo)
        row = {"sno": int(text(tds[0])), "activity_code": text(tds[1]), "activity": text(tds[2]), "approved_cost": text(tds[3]),
               "asset": text(tds[4]), "stage": text(tds[5]), "photo": html.unescape(src.group(1)) if src else "",
               "lat_text": lat.group(1).strip() if lat else "", "lon_text": lon.group(1).strip() if lon else "",
               "lat": num(lat.group(1)) if lat else None, "lon": num(lon.group(1)) if lon else None, "uploaded": text(tds[7])}
        if len(tds) > 8:
            row["extra"] = [text(t) for t in tds[8:]]
        out.append(row)
    return {"columns": head, "rows": out}


class Site:
    def __init__(self, hub=None, gap=1.5):
        self.hub, self.gap, self.last = hub, gap, 0.0
        self.s = requests.Session()
        self.s.headers.update({"User-Agent": UA})

    def get(self, path):
        if self.hub and self.hub.settings.get("delay_ms"):
            self.gap = max(1.0, self.hub.settings["delay_ms"] / 1000)
        wait = self.last + self.gap - time.time()
        if wait > 0:
            time.sleep(wait)
        t = time.time()
        try:
            r = self.s.get(BASE + path, timeout=(20, 180))
        except requests.RequestException:
            self.last = time.time()
            if self.hub:
                self.hub.metric("http_error")
                self.hub.error()
            raise
        self.last = time.time()
        if self.hub:
            self.hub.metric("n_http")
            self.hub.metric("t_http_s", self.last - t)
            if r.status_code != 200:
                self.hub.metric(f"http_{r.status_code}")
                if r.status_code in (403, 429, 503):
                    self.hub.block()
        if r.status_code != 200:
            raise RuntimeError(f"HTTP {r.status_code} for {path[:120]}")
        return r


def run_item(hub, S, item, seed):
    k, p = item["key"], item.get("payload") or {}
    kind = k.split("-", 1)[0]
    if kind == "gp":
        y, gp = p["start_year"], p["gp"]
        page = S.get(f"/geotaggedDetailsforgpdp.do?year={y}&gpcode={gp}").text
        hub.upload_many([(f"raw/{y}/{gp}.html.gz", gzip.compress(page.encode()), "application/gzip")])
        d = parse_gp(page)
        acts = len({r["activity_code"] for r in d["rows"]})
        hub.record(f"gp-{y}-{gp}", {**p, **d, "activities": acts, "photos": len(d["rows"]), "raw": f"raw/{y}/{gp}.html.gz",
                                    "source": f"{BASE}/geotaggedDetailsforgpdp.do?year={y}&gpcode={gp}",
                                    "fetched_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())})
        hub.complete([k], "done", fetched=1)
        return
    y = p["year"]
    if kind == "year":
        path, level = f"/geoTaggingStateReport.do?year={y}", "state-all"
    elif kind == "zp":
        path, level = f"/geoTaggingZpReport.do?stateId={p['state']}&year={y}", f"zp-{p['state']}"
    elif kind == "bp":
        path, level = f"/geoTaggingBpReport.do?stateId={p['state']}&code={p['zp']}&year={y}", f"bp-{p['zp']}"
    else:
        path, level = f"/geoTaggingGpReport.do?stateId={p['state']}&code={p['bp']}&year={y}", f"gp-{p['bp']}"
    body = S.get(path).content
    rows = json.loads(body)
    hub.upload_many([(f"tree/{y}/{level}.json", body, "application/json")])
    fresh = []
    for r in rows:
        if not r.get("count"):
            continue
        c, n = r["code"], r.get("name")
        if kind == "year":
            fresh.append({"key": f"zp-{y}-{c}", "payload": {"year": y, "state": c, "state_name": n}})
        elif kind == "zp":
            fresh.append({"key": f"bp-{y}-{p['state']}-{c}", "payload": {**p, "zp": c, "zp_name": n}})
        elif kind == "bp":
            fresh.append({"key": f"gl-{y}-{p['state']}-{c}", "payload": {**p, "bp": c, "bp_name": n}})
        else:
            sy = y.split("-")[0]
            fresh.append({"key": f"gp-{sy}-{c}", "payload": {**{q: v for q, v in p.items() if q != "year"}, "plan_year": y,
                                                              "start_year": sy, "gp": c, "gp_name": n, "count": r["count"]}})
    if fresh:
        seed(fresh)
    hub.complete([k], "done", fetched=len(rows))


def main():
    from scrape_hub_client import HubClient, seed_queue
    project = os.environ["SCRAPE_POOL_PROJECT"]
    deadline = time.time() + float(os.environ.get("SCRAPE_MAX_HOURS", "1")) * 3600 - 300
    hub = HubClient(project, job_index=int(os.environ.get("SCRAPE_JOB_INDEX", 0)), total_jobs=int(os.environ.get("SCRAPE_TOTAL_JOBS", 1)))
    signal.signal(signal.SIGINT, on_signal)
    signal.signal(signal.SIGTERM, on_signal)
    S = Site(hub)
    try:
        while time.time() < deadline and not stop:
            if hub.settings.get("paused"):
                time.sleep(30)
                continue
            items = hub.claim(1, steal=True, retry_failed=True)
            if not items:
                break
            item = items[0]
            try:
                run_item(hub, S, item, lambda fresh: seed_queue(project, fresh))
            except Exception as e:
                hub.failure("bad-item", item["key"], f"{type(e).__name__}: {e}"[:200])
                hub.complete([item["key"]], "failed", error=type(e).__name__)
        hub.close("finished" if not stop else "failed", "" if not stop else "stopped by signal")
    except Exception as e:
        hub.close("failed", str(e)[:200])
        raise


class LocalHub:
    settings = {}

    def __getattr__(self, name):
        return lambda *a, **k: None

    def upload_many(self, files):
        for p, body, _ in files:
            print("file", p, len(body))

    def record(self, rid, data):
        print("record", rid, json.dumps({**data, "rows": data["rows"][:2]}, ensure_ascii=False)[:1500])

    def complete(self, keys, status, **k):
        print("complete", keys, status, k)


if __name__ == "__main__":
    if sys.argv[1:2] == ["--local"]:
        gp = sys.argv[2] if len(sys.argv) > 2 else "215148"
        y = sys.argv[3] if len(sys.argv) > 3 else "2024"
        run_item(LocalHub(), Site(None), {"key": f"gp-{y}-{gp}", "payload": {"start_year": y, "gp": int(gp)}}, print)
        sys.exit(0)
    sys.exit(main())
