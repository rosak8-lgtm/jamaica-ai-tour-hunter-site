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


def safe_url(entry, country_id, *, origin_scope=None):
    """Rebuild an official price-list URL from whitelisted parameters only."""
    origin_id = bg.CITY_ID if origin_scope is None else origin_scope.origin_id
    if origin_scope is not None and country_id != origin_scope.country_id:
        raise bg.SyncHold("DETAIL_SCOPE_INVALID")
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
        values["flt2"] != origin_id or values["xml"] != "11"):
        raise bg.SyncHold("DETAIL_SCOPE_INVALID")
    if not DIGITS.fullmatch(values["tid"]) or not DIGITS.fullmatch(values["id_price"]):
        raise bg.SyncHold("DETAIL_IDS_INVALID")
    if bg.date_iso(values["data"]) is None:
        raise bg.SyncHold("DETAIL_DATE_INVALID")
    if bg.date_iso(values["data"]) < datetime.now(timezone.utc).date():
        raise bg.SyncHold("DETAIL_DATE_PAST")
    return DETAIL_BASE + "?" + urllib.parse.urlencode(values)


SAFE_ENTRY_FIELDS = {
    "hotel", "room", "town", "tour_date", "aircompany", "dt",
    "duration", "o_duration", "id_hotel", "id_ns", "quota",
    "prices", "isstop", "flights", "id_price"
}
SAFE_PRICE_FIELDS = {"amount", "RUR", "ag", "isstop", "concr"}

def shape(raw):
    """Report only allowlisted key names and aggregate counts; never raw values."""
    empty = {"format": "NON_JSON", "root": "UNKNOWN", "rows": 0,
             "fields": [], "entry_fields": [], "price_fields": [],
             "price_rows": 0, "amount_present": 0, "rur_present": 0,
             "adult_pair_markers": 0, "row_stop_markers": 0}
    try:
        data = json.loads(raw)
    except (ValueError, UnicodeDecodeError):
        return empty
    if not isinstance(data, (dict, list)):
        return {**empty, "format": "JSON", "root": "OTHER"}
    entries = data.get("entries") if isinstance(data, dict) else data
    result = {**empty, "format": "JSON",
              "root": "OBJECT" if isinstance(data, dict) else "ARRAY",
              "fields": sorted(k for k in data if k in SAFE_FIELDS) if isinstance(data, dict) else []}
    if not isinstance(entries, list):
        return result
    result["rows"] = len(entries)
    entry_keys, price_keys = set(), set()
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        entry_keys.update(entry.keys() & SAFE_ENTRY_FIELDS)
        if entry.get("isstop"):
            result["row_stop_markers"] += 1
        for price in entry.get("prices", []) if isinstance(entry.get("prices"), list) else []:
            if not isinstance(price, dict):
                continue
            result["price_rows"] += 1
            price_keys.update(price.keys() & SAFE_PRICE_FIELDS)
            if str(price.get("amount", "")).strip():
                result["amount_present"] += 1
            if str(price.get("RUR", "")).strip():
                result["rur_present"] += 1
            ag = str(price.get("ag", ""))
            if "12+" in ag or "14-99" in ag:
                result["adult_pair_markers"] += 1
    result["entry_fields"] = sorted(entry_keys)
    result["price_fields"] = sorted(price_keys)
    return result


def probe(directory, api, max_countries=MAX_COUNTRIES):
    countries = [c for c in directory.get("countries", [])
                 if c.get("has_tour_catalog") and bg.CITY_ID in c.get("origins", [])]
    outcomes = []
    selected = 0
    attempts = 0
    for country in countries:
        if selected >= max_countries or attempts >= 12:
            break
        attempts += 1
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
                outcomes.append({"country": bg.clean(country.get("name"), 60),
                                 "result": {"format": "NO_FUTURE_PRICE_LIST",
                                            "root": "UNKNOWN", "rows": 0, "fields": [],
                                            "entry_fields": [], "price_fields": [],
                                            "price_rows": 0, "amount_present": 0, "rur_present": 0,
                                            "adult_pair_markers": 0, "row_stop_markers": 0}})
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
                                        "rows": 0, "fields": [], "entry_fields": [], "price_fields": [],
                                        "price_rows": 0, "amount_present": 0, "rur_present": 0,
                                        "adult_pair_markers": 0, "row_stop_markers": 0}})
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
    print("COUNTRIES_ATTEMPTED=" + str(len(results)))
    print("COUNTRIES_DETAIL_JSON=" + str(sum(x["result"]["format"] == "JSON" for x in results)))
    for i, row in enumerate(results, 1):
        result = row["result"]
        print("COUNTRY_" + str(i) + "=" + row["country"])
        print("FORMAT_" + str(i) + "=" + result["format"])
        print("ROOT_" + str(i) + "=" + result["root"])
        print("ROWS_" + str(i) + "=" + str(result["rows"]))
        print("STRUCTURE_" + str(i) + "=" + ",".join(result["fields"]))
        print("ENTRY_FIELDS_" + str(i) + "=" + ",".join(result["entry_fields"]))
        print("PRICE_FIELDS_" + str(i) + "=" + ",".join(result["price_fields"]))
        print("PRICE_ROWS_" + str(i) + "=" + str(result["price_rows"]))
        print("AMOUNT_PRESENT_" + str(i) + "=" + str(result["amount_present"]))
        print("RUR_PRESENT_" + str(i) + "=" + str(result["rur_present"]))
        print("ADULT_MARKERS_" + str(i) + "=" + str(result["adult_pair_markers"]))
        print("ROW_STOP_MARKERS_" + str(i) + "=" + str(result["row_stop_markers"]))
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
