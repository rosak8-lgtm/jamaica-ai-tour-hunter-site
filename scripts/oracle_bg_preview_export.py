#!/usr/bin/env python3
"""Generate a PUBLIC, non-bookable catalog of real hotel/date/room combinations.

Oracle-only: authenticated, read-only source requests. Never exports actual prices,
private reservation/session IDs, cookies, supplier URLs, passenger data or booking links.
Data is explicitly descriptive, not a verified offer or order.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import urllib.parse
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

import oracle_bg_route_sync as bg
import oracle_bg_price_detail_probe as detail
import tour_price_reference as price_ref

MAX_ROWS = 6000
MAX_RESPONSE_ROWS = 25000
MAX_COUNTRIES = 13
ALLOWED_ORIGIN = "Иркутск"

def normalize_date(value):
    d = bg.date_iso(value)
    today = datetime.now(timezone.utc).date()
    if d and today <= d <= today + timedelta(days=180):
        return d.isoformat()
    return None

def nights_value(value):
    try:
        n = int(str(value))
        return n if 3 <= n <= 180 else None
    except (TypeError, ValueError):
        return None

def safe_preview(entry, country, hotel_by_id, price_currency=None):
    if not isinstance(entry, dict):
        return None
    hotel_id = str(entry.get("id_hotel", ""))
    hotel = hotel_by_id.get(hotel_id)
    if not hotel or hotel.get("country") != country:
        return None
    tour_date = normalize_date(entry.get("tour_date") or entry.get("dt"))
    nights = nights_value(entry.get("duration"))
    room = bg.clean(entry.get("room"), 115)
    resort = bg.clean(entry.get("town"), 100)
    if not tour_date or not nights or not room or not isinstance(entry.get("prices"), list):
        return None
    if entry.get("isstop") or entry.get("stop"):
        return None
    # A non-empty amount only indicates an indicative listed price EXISTS,
    # NOT availability, currency, total-party quote, confirmed seats, or a sale.
    priced = any(isinstance(p, dict) and str(p.get("amount", "")).strip()
                 and not p.get("isstop") for p in entry["prices"])
    if not priced:
        return None
    name = bg.clean(hotel.get("name"), 110)
    if not name:
        return None
    listed_price=price_ref.indicative_two_adult_rub(entry["prices"], price_currency)
    key = "|".join((country, hotel_id, tour_date, str(nights), room))
    return {
        "id": "p_" + hashlib.sha256(key.encode()).hexdigest()[:24],
        "hotel_id": hotel_id,
        "hotel": name,
        "country": country,
        "origin": ALLOWED_ORIGIN,
        "resort": resort or bg.clean(hotel.get("resort"), 100),
        "room": room,
        "depart_date": tour_date,
        "nights": nights,
        "status": "REFERENCE_PRICE_LIST_ONLY",
        "price_reference_rub": listed_price,
        "price_reference_party": "TWO_ADULTS" if listed_price is not None else "UNVERIFIED",
        "quote_verified": False,
        "availability_verified": False,
        "flight_verified": False,
        "bookable": False,
    }

def choose_price_lists(entries, limit=2, today=None):
    """Prefer future departures on separate dates over same-day duplicate files."""
    today=today or datetime.now(timezone.utc).date()
    candidates=[]
    for entry in entries:
        if not isinstance(entry,dict) or entry.get("stop") is not None:
            continue
        d=bg.date_iso(entry.get("date"))
        if d is None or d<=today or d>today+timedelta(days=180):
            continue
        candidates.append((d,entry))
    candidates.sort(key=lambda pair:pair[0])
    seen=set()
    selected=[]
    for day,entry in candidates:
        if day in seen:
            continue
        selected.append(entry)
        seen.add(day)
        if len(selected)==limit:
            break
    return selected


def build(directory, api, max_countries=5, per_country=2):
    if directory.get("schema") != "jamaica.destination-directory.v1":
        raise bg.SyncHold("DIRECTORY_SCHEMA_UNKNOWN")
    hotel_by_id = {str(h["id"]): h for h in directory.get("hotels", [])
                   if isinstance(h, dict) and h.get("id") and h.get("country")}
    countries = [c for c in directory.get("countries", [])
                 if c.get("has_tour_catalog") and bg.CITY_ID in c.get("origins", [])]
    results, statuses, ids = [], [], set()
    by_id={}
    for country in countries[:MAX_COUNTRIES]:
        if len(statuses) >= max_countries:
            break
        stats = {"country": bg.clean(country.get("name"), 70),
                 "lists_read": 0, "previews": 0, "rows_scanned": 0,
                 "known_hotel_ids": 0, "status": "NO_CONFIRMED_LIST"}
        try:
            q = urllib.parse.urlencode({"action": "files",
                                        "flt": country["id"],
                                        "flt2": bg.CITY_ID, "xml": "11"})
            listings = json.loads(api.get("https://export.bgoperator.ru/yandex?" + q))
            entries = listings.get("entries")
            if not isinstance(entries, list):
                raise bg.SyncHold("FILES_SCHEMA_UNKNOWN")
            selected_lists=choose_price_lists(entries,per_country)
            for listed in selected_lists:
                url = detail.safe_url(listed, country["id"])
                payload = json.loads(api.get(url))
                rows = payload.get("entries") if isinstance(payload, dict) else None
                if not isinstance(rows, list) or len(rows) > MAX_RESPONSE_ROWS:
                    raise bg.SyncHold("PRICE_LIST_SCHEMA_OR_SIZE")
                stats["lists_read"] += 1
                currency=payload.get("cur")
                for row in rows:
                    stats["rows_scanned"] += 1
                    if isinstance(row, dict) and str(row.get("id_hotel", "")) in hotel_by_id:
                        stats["known_hotel_ids"] += 1
                    candidate = safe_preview(row, country["name"], hotel_by_id, currency)
                    if candidate and candidate["id"] in by_id:
                        existing=by_id[candidate["id"]]
                        incoming=candidate["price_reference_rub"]
                        previous=existing["price_reference_rub"]
                        if incoming is not None and (previous is None or incoming<previous):
                            existing["price_reference_rub"]=incoming
                            existing["price_reference_party"]="TWO_ADULTS"
                    elif candidate:
                        ids.add(candidate["id"])
                        by_id[candidate["id"]]=candidate
                        results.append(candidate)
                        stats["previews"] += 1
                        if len(results) >= MAX_ROWS:
                            break
                if len(results) >= MAX_ROWS:
                    break
            stats["status"] = "CHECKED" if stats["lists_read"] else "NO_FUTURE_LIST"
        except (bg.SyncHold, urllib.error.HTTPError, urllib.error.URLError,
                ValueError, TimeoutError, KeyError):
            stats["status"] = "UNVERIFIED"
        statuses.append(stats)
        if len(results) >= MAX_ROWS:
            break
    results.sort(key=lambda r: (r["depart_date"], r["country"], r["hotel"]))
    indicative_count=sum(p["price_reference_rub"] is not None for p in results)
    return {"schema": "jamaica.tour-previews.v1",
            "refreshed_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "classification": "PRELIMINARY_DETAILS_NOT_OFFERS",
            "origin": ALLOWED_ORIGIN,
            "countries_status": statuses,
            "previews": results,
            "indicative_two_adult_rub_count":indicative_count,
            "quote_verified": False, "availability_verified": False,
            "bookable": False}

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--credentials", default="")
    p.add_argument("--max-countries", type=int, default=5)
    p.add_argument("--per-country", type=int, default=2)
    args = p.parse_args()
    if not 1 <= args.max_countries <= 13 or not 1 <= args.per_country <= 3:
        raise bg.SyncHold("PROBE_LIMIT_INVALID")
    catalog = json.loads(Path(args.directory).read_text(encoding="utf-8"))
    login, password = bg.read_secret(bg.credentials_path(args.credentials))
    # API only on an explicitly allowed host and paths; no arbitrary external URLs.
    bg.BASE = "https://export.bgoperator.ru/"
    result = build(catalog, bg.ApiClient(login, password),
                   args.max_countries, args.per_country)
    if not result["previews"]:
        for i, stats in enumerate(result["countries_status"], 1):
            print("COUNTRY_"+str(i)+"="+stats["country"])
            print("ROWS_SCANNED_"+str(i)+"="+str(stats["rows_scanned"]))
            print("HOTEL_IDS_MATCHED_"+str(i)+"="+str(stats["known_hotel_ids"]))
        raise bg.SyncHold("NO_MATCHED_HOTEL_PREVIEWS_DO_NOT_PUBLISH_EMPTY")
    destination = Path(args.output)
    if destination.is_symlink():
        raise bg.SyncHold("OUTPUT_SYMLINK")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(destination)
    print("JAMAICA_PREVIEW_EXPORT_PASS")
    print("COUNTRIES_ATTEMPTED="+str(len(result["countries_status"])))
    print("COUNTRIES_WITH_PREVIEWS="+str(len({p["country"] for p in result["previews"]})))
    print("PREVIEW_COUNT="+str(len(result["previews"])))
    print("INDICATIVE_2_ADULT_RUB_PRICES="+str(result["indicative_two_adult_rub_count"]))
    for i, stats in enumerate(result["countries_status"], 1):
        print("COUNTRY_"+str(i)+"="+stats["country"])
        print("STATUS_"+str(i)+"="+stats["status"])
        print("PRICE_LISTS_"+str(i)+"="+str(stats["lists_read"]))
        print("ROWS_SCANNED_"+str(i)+"="+str(stats["rows_scanned"]))
        print("HOTEL_IDS_MATCHED_"+str(i)+"="+str(stats["known_hotel_ids"]))
        print("PUBLIC_PREVIEWS_"+str(i)+"="+str(stats["previews"]))
    print("NO_CONFIRMED_SALE_NO_BOOKING_NO_SECRET_EXPORTED=YES")

if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("JAMAICA_PREVIEW_EXPORT_HOLD="+type(exc).__name__, file=sys.stderr)
        sys.exit(2)
