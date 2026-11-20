#!/usr/bin/env python3
"""JAMAICA: authenticated, read-only probe of detailed BG price lists.

Run on Oracle, where credentials are already stored. No booking, payments,
passenger data, public prices, raw payloads, URLs or secret values are printed.
Only counts and top-level structural fields are emitted.
"""
from __future__ import annotations
import argparse
import json
import re
import urllib.parse
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

import oracle_bg_route_sync as bg

DETAIL_BASE = "https://export.bgoperator.ru/partners"
SAFE_FIELDS = {"entries", "prices", "hotels", "rooms", "date", "country",
               "currency", "valut", "id_valut", "nights", "duration",
               "flight", "flights", "hotel", "resort", "meals", "boarding"}
DIGITS = re.compile(r"^[0-9]{1,22}$")
CANDIDATES_PER_COUNTRY = 1
MAX_COUNTRIES = 3


def safe_url(entry, country_id):
    """Rebuild an official price-list URL from whitelisted parameters only."""
    raw = entry.get("url")
    if not isinstance(raw, str):
        raise bg.SyncHold("DETAIL_URL_ABSENT")
    parsed = urllib.parse.urlsplit(raw)
    if parsed.hostname != "export.bgoperator.ru" or parsed.path != "/partners":
        raise bg.SyncHold("DETAIL_URL_UNAPPROVED")
    params = urllib.parse.parse_qs(parsed.query, keep_blank_values=True)
    required = ("action", "tid", "flt", "flt2", "id_price", "data", "xml")
    if any(len(params.get(k, [])) != 1 for k in required):
        raise bg.SyncHold("DETAIL_QUERY_INVALID")
    values = {k: params[k][0] for k in required}
    if (values["action"] != "price" or values["flt"] != country_id or
        values["flt2"] != bg.CITY_ID or values["xml"] != "11"):
        raise bg.SyncHold("DETAIL_SCOPE_INVALID")
    if not DIGITS.fullmatch(values["tid"]) or not DIGITS.fullmatch(values["id_price"]):
        raise bg.SyncHold("DETAIL_IDS_INVALID")
    if bg.date_iso(values["data"]) is None:
        raise bg.SyncHold("DETAIL_DATE_INVALID")
    if bg.date_iso(values["data"]) < datetime.now(timezone.utc).date():
        raise bg.SyncHold("DETAIL_DATE_PAST")
    return DETAIL_BASE + "?" + urllib.parse.urlencode(values)


def shape(raw):
    """Inspect JSON shape, never expose raw operator content."""
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return {"format": "NON_JSON", "root": "UNKNOWN", "rows": 0, "fields": []}
    if isinstance(data, dict):
        keys = sorted(k for k in data if k in SAFE_FIELDS)
        entries = data.get("entries")
        return {"format": "JSON", "root": "OBJECT",
                "rows": len(entries) if isinstance(entries, list) else 0,
                "fields": keys}
    if isinstance(data, list):
        return {"format": "JSON", "root": "ARRAY",
                "rows": len(data), "fields": []}
    return {"format": "JSON", "root": "OTHER", "rows": 0, "fields": []}


def probe(directory, api, max_countries=MAX_COUNTRIES):
    countries = [c for c in directory.get("countries", [])
                 if c.get("has_tour_catalog") and bg.CITY_ID in c.get("origins", [])]
    outcomes = []
    selected = 0
    for country in countries:
        if selected >= max_countries:
            break
        query = urllib.parse.urlencode({
            "action": "files", "flt": country["id"],
            "flt2": bg.CITY_ID, "xml": "11"
        })
        try:
            listing = json.loads(api.get("https://export.bgoperator.ru/yandex?" + query))
            entries = listing.get("entries")
            if not isinstance(entries, list):
                raise bg.SyncHold("FILES_SCHEMA_UNKNOWN")
            candidates = [e for e in entries if isinstance(e, dict) and
                          e.get("stop") is None and bg.date_iso(e.get("date")) is not None and
                          bg.date_iso(e["date"]) >= datetime.now(timezone.utc).date()]
            if not candidates:
                continue
            item = candidates[0]
            url = safe_url(item, country["id"])
            selected += 1
            result = shape(api.get(url))
            outcomes.append({"country": bg.clean(country["name"], 60),
                             "result": result})
        except (bg.SyncHold, urllib.error.HTTPError, urllib.error.URLError,
                ValueError, KeyError, TimeoutError):
            outcomes.append({"country": bg.clean(country.get("name"), 60),
                             "result": {"format": "UNVERIFIED", "root": "UNKNOWN",
                                        "rows": 0, "fields": []}})
    return outcomes


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True)
    p.add_argument("--credentials", default="")
    p.add_argument("--max-countries", type=int, default=3)
    args = p.parse_args()
    if not 1 <= args.max_countries <= 5:
        raise bg.SyncHold("COUNTRY_LIMIT_INVALID")
    directory = json.loads(Path(args.directory).read_text(encoding="utf-8"))
    if directory.get("schema") != "jamaica.destination-directory.v1":
        raise bg.SyncHold("DIRECTORY_INVALID")
    login, password = bg.read_secret(bg.credentials_path(args.credentials))
    # Existing authenticated API client accepts only BASE-prefix paths.
    # Keep both official read-only endpoints inside the same exact HTTPS host.
    bg.BASE = "https://export.bgoperator.ru/"
    client = bg.ApiClient(login, password)
    results = probe(directory, client, args.max_countries)
    print("JAMAICA_DETAIL_PRICE_PROBE_V1")
    print("COUNTRIES_INSPECTED=" + str(len(results)))
    for i, row in enumerate(results, 1):
        result = row["result"]
        print("COUNTRY_" + str(i) + "=" + row["country"])
        print("FORMAT_" + str(i) + "=" + result["format"])
        print("ROOT_" + str(i) + "=" + result["root"])
        print("ROWS_" + str(i) + "=" + str(result["rows"]))
        print("STRUCTURE_" + str(i) + "=" + ",".join(result["fields"]))
    print("NO_PRICE_NO_BOOKING_NO_SECRET_EXPORTED=YES")
    if not results or not any(x["result"]["format"] == "JSON" for x in results):
        print("DETAIL_PRICE_NOT_YET_CONFIRMED")
        return 2
    print("DETAIL_PRICE_JSON_RETRIEVED=YES")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("JAMAICA_DETAIL_PRICE_HOLD=" + type(exc).__name__)
        raise SystemExit(2)
