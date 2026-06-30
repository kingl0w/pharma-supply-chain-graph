"""openfda connector: fetch raw label pages into the landing zone.

needs network (api.fda.gov). trim keeps only the structured fields; trim=False keeps full records.
"""
import datetime
import json
import os
import time
import urllib.parse
import urllib.request

from .config import API_LABEL, LANDING_DIR, PAGE_SIZE, SOURCE_LICENSE, SOURCE_NAME

KEEP = ("openfda", "effective_time", "id", "set_id")


def _trim(rec):
    return {k: rec[k] for k in KEEP if k in rec}


def fetch(total=3000, page=PAGE_SIZE, trim=True, landing=LANDING_DIR):
    os.makedirs(landing, exist_ok=True)
    key = os.environ.get("OPENFDA_API_KEY")          # optional, raises rate limit
    stamp = datetime.date.today().isoformat().replace("-", "")
    got = 0
    for skip in range(0, total, page):
        want = min(page, total - skip)
        params = {"limit": want, "skip": skip}
        if key:
            params["api_key"] = key
        url = API_LABEL + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": "supplygraph/0.1"})
        with urllib.request.urlopen(req, timeout=30) as r:
            payload = json.loads(r.read())
        results = payload.get("results", [])
        meta_in = payload.get("meta", {})
        if trim:
            results = [_trim(x) for x in results]
        page_doc = {
            "meta": {
                "source": SOURCE_NAME,
                "license": meta_in.get("license", SOURCE_LICENSE),
                "last_updated": meta_in.get("last_updated"),
                "skip": skip,
                "trimmed": trim,
            },
            "results": results,
        }
        path = os.path.join(landing, f"openfda_label_{stamp}_skip{skip}.json")
        with open(path, "w") as f:
            json.dump(page_doc, f)
        got += len(results)
        print(f"  wrote {path} ({len(results)} records)")
        if len(results) < want:
            break                                    # reached end of dataset
        time.sleep(0.3)                              # stay under the rate limit
    print(f"fetched {got} records into {landing}/")
