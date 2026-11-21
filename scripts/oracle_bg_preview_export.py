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

MAX_ROWS = 60000
MAX_RESPONSE_ROWS = 25000
MAX_COUNTRIES = 120
MAX_PER_COUNTRY = 12000
MAX_LISTS_PER_COUNTRY = 5
EXTRA_DISCOVERY_BATCH = 8
PRIORITY_ADDITIONAL_COUNTRIES = ("Китай","Вьетнам")
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

def choose_price_lists(entries, limit=2, today=None, *, probe_slot=0):
    """Rotate source price-list dates across *all* available calendar months.

    The real source can advertise dozens of future departure lists while the
    authenticated read-only importer may fetch at most five per country per
    cycle. Always sample the nearest date; sample distinct later months next,
    rotating both eligible months and dates within each month across 5-minute
    cycles. This is coverage sampling, NOT a claim of exhaustive inventory.
    Preserve legacy nearest-date behavior for very small one/two-list probes.
    """
    today=today or datetime.now(timezone.utc).date()
    if type(limit) is not int or limit<=0 or type(probe_slot) is not int or probe_slot<0:
        return []
    candidates=[]
    for entry in entries:
        if not isinstance(entry,dict) or entry.get("stop") is not None:
            continue
        d=bg.date_iso(entry.get("date"))
        if d is None or d<=today or d>today+timedelta(days=180):
            continue
        candidates.append((d,entry))
    candidates.sort(key=lambda pair:pair[0])
    distinct=[]
    seen=set()
    for day,entry in candidates:
        if day not in seen:
            distinct.append((day,entry))
            seen.add(day)
    if len(distinct)<=limit or limit<=2:
        return [entry for _,entry in distinct[:limit]]

    months={}
    for day,entry in distinct:
        months.setdefault((day.year,day.month),[]).append((day,entry))
    first_day,first_entry=distinct[0]
    first_month=(first_day.year,first_day.month)
    selected=[(first_day,first_entry)]
    chosen={first_day}
    later_months=sorted(m for m in months if m!=first_month)
    if later_months:
        offset=probe_slot%len(later_months)
        rotated=later_months[offset:]+later_months[:offset]
        for month in rotated:
            options=months[month]
            # Cycling the exact departure within the month exposes later dates
            # instead of repeatedly sampling only the first price-list file.
            day,entry=options[(probe_slot//len(later_months))%len(options)]
            selected.append((day,entry))
            chosen.add(day)
            if len(selected)>=limit:
                break

    # When the source has fewer months than our read cap, rotate additional
    # distinct days without wasting supplier requests on duplicate dates.
    if len(selected)<limit:
        extra=distinct[1:]
        offset=probe_slot%len(extra) if extra else 0
        for day,entry in extra[offset:]+extra[:offset]:
            if day in chosen:
                continue
            selected.append((day,entry))
            chosen.add(day)
            if len(selected)>=limit:
                break
    return [entry for _,entry in sorted(selected,key=lambda pair:pair[0])]


def select_source_countries(directory, *, extra_priority_names=(), probe_slot=0,
                            discovery_batch=EXTRA_DISCOVERY_BATCH):
    """All primary Irkutsk catalogs + round-robin discovery of other tour countries.

    Every operator country tagged as a tour catalog gets checked over multiple
    5-minute server cycles. Countries with a discovered Irkutsk price list are
    promoted to the priority set by the private publisher on the next cycle.
    We never fabricate flights for countries not returned by the Irkutsk API.
    """
    countries=[c for c in directory.get("countries",[])
               if isinstance(c,dict) and c.get("has_tour_catalog") and
               isinstance(c.get("name"),str) and isinstance(c.get("id"),str)]
    primary=[c for c in countries if bg.CITY_ID in c.get("origins",[])]
    others=[c for c in countries if bg.CITY_ID not in c.get("origins",[])]
    chosen_names=set(extra_priority_names or ())|set(PRIORITY_ADDITIONAL_COUNTRIES)
    promoted=[c for c in others if c["name"] in chosen_names]
    pending=[c for c in others if c["name"] not in chosen_names]
    if type(probe_slot) is not int or probe_slot<0 or not 1<=discovery_batch<=20:
        raise bg.SyncHold("INVALID_COUNTRY_DISCOVERY_CONFIGURATION")
    # Deterministic disjoint blocks avoid repeatedly probing the first 8
    # countries. With 79 other countries, all are tested within ~50 minutes.
    start=(probe_slot*discovery_batch)%len(pending) if pending else 0
    explored=(pending[start:]+pending[:start])[:discovery_batch]
    selected=primary+promoted+explored
    if len(selected)>MAX_COUNTRIES:
        raise bg.SyncHold("SOURCE_SCOPE_TOO_LARGE")
    return selected,{
        "source_tour_countries":len(countries),
        "irkutsk_catalog_countries":len(primary),
        "other_tour_countries":len(others),
        "other_countries_probed_this_cycle":len(explored),
        "regular_additional_countries_checked":len(promoted),
    }


def fair_catalog(candidates, max_rows=MAX_ROWS):
    """Keep countries and departure dates represented; prefer lower priced rows per date.

    This is a *selection* of source-backed preliminary references, never a quote
    or a guarantee of available rooms. Preserve fair country mixing at the public cap.
    """
    if max_rows <= 0:
        return []
    groups={}
    for item in candidates:
        groups.setdefault(item["country"],{}).setdefault(item["depart_date"],[]).append(item)

    def ranking(item):
        ref=item.get("price_reference_rub")
        price=(ref if item.get("price_reference_party")=="TWO_ADULTS"
               and type(ref) is int and ref>0 else float("inf"))
        return (price,item["hotel"],item["room"],item["id"])

    by_country={}
    for country,dates in groups.items():
        for values in dates.values():
            values.sort(key=ranking)
        # Visit each date's best priced record before a second record for a date.
        date_keys=sorted(dates,key=lambda day:(ranking(dates[day][0])[0],day))
        chosen=[]
        for layer in range(max(len(values) for values in dates.values())):
            for day in date_keys:
                if layer<len(dates[day]):
                    chosen.append(dates[day][layer])
        by_country[country]=chosen

    names=sorted(by_country)
    result=[]
    for layer in range(max((len(values) for values in by_country.values()),default=0)):
        for country in names:
            if layer<len(by_country[country]):
                result.append(by_country[country][layer])
                if len(result)==max_rows:
                    result.sort(key=lambda r:(r["depart_date"],r["country"],r["hotel"]))
                    return result
    result.sort(key=lambda r:(r["depart_date"],r["country"],r["hotel"]))
    return result

def build(directory, api, max_countries=MAX_COUNTRIES, per_country=MAX_LISTS_PER_COUNTRY,
          *, extra_priority_names=(), probe_slot=0):
    if directory.get("schema") != "jamaica.destination-directory.v1":
        raise bg.SyncHold("DIRECTORY_SCHEMA_UNKNOWN")
    if not 1<=max_countries<=MAX_COUNTRIES or not 1<=per_country<=MAX_LISTS_PER_COUNTRY:
        raise bg.SyncHold("PROBE_LIMIT_INVALID")
    hotel_by_id={str(h["id"]):h for h in directory.get("hotels",[])
                 if isinstance(h,dict) and h.get("id") and h.get("country")}
    countries,scope=select_source_countries(
        directory,extra_priority_names=extra_priority_names,probe_slot=probe_slot)
    results,statuses=[],[]
    total_candidates_before_country_cap=0
    for country in countries[:max_countries]:
        # Enforce country cap only AFTER sampling independent source lists.
        country_by_id={}
        stats={"country":bg.clean(country.get("name"),70),
               "lists_read":0,"previews":0,"candidate_previews":0,"rows_scanned":0,
               "known_hotel_ids":0,"sampled_departure_months":[],
               "status":"NO_CONFIRMED_LIST"}
        try:
            q=urllib.parse.urlencode({"action":"files","flt":country["id"],
                                       "flt2":bg.CITY_ID,"xml":"11"})
            listings=json.loads(api.get("https://export.bgoperator.ru/yandex?"+q))
            entries=listings.get("entries") if isinstance(listings,dict) else None
            if not isinstance(entries,list):
                raise bg.SyncHold("FILES_SCHEMA_UNKNOWN")
            selected_lists=choose_price_lists(entries,per_country,probe_slot=probe_slot)
            stats["sampled_departure_months"]=sorted({
                bg.date_iso(item["date"]).strftime("%Y-%m")
                for item in selected_lists
            })
            for listed in selected_lists:
                new_from_this_list=0
                url=detail.safe_url(listed,country["id"])
                payload=json.loads(api.get(url))
                rows=payload.get("entries") if isinstance(payload,dict) else None
                if not isinstance(rows,list) or len(rows)>MAX_RESPONSE_ROWS:
                    raise bg.SyncHold("PRICE_LIST_SCHEMA_OR_SIZE")
                stats["lists_read"]+=1
                currency=payload.get("cur")
                for row in rows:
                    stats["rows_scanned"]+=1
                    if isinstance(row,dict) and str(row.get("id_hotel","")) in hotel_by_id:
                        stats["known_hotel_ids"]+=1
                    candidate=safe_preview(row,country["name"],hotel_by_id,currency)
                    if not candidate:continue
                    old=country_by_id.get(candidate["id"])
                    if old is not None:
                        incoming=candidate["price_reference_rub"]
                        previous=old["price_reference_rub"]
                        if incoming is not None and (previous is None or incoming<previous):
                            old["price_reference_rub"]=incoming
                            old["price_reference_party"]="TWO_ADULTS"
                    elif new_from_this_list<MAX_PER_COUNTRY:
                        country_by_id[candidate["id"]]=candidate
                        new_from_this_list+=1
            stats["candidate_previews"]=len(country_by_id)
            total_candidates_before_country_cap+=len(country_by_id)
            # Favor cheaper known prices and date coverage before final cap.
            results.extend(fair_catalog(list(country_by_id.values()),max_rows=MAX_PER_COUNTRY))
            stats["status"]="CHECKED" if stats["lists_read"] else "NO_FUTURE_LIST"
        except (bg.SyncHold,urllib.error.HTTPError,urllib.error.URLError,
                ValueError,TimeoutError,KeyError):
            stats["status"]="UNVERIFIED"
        statuses.append(stats)
    selected=fair_catalog(results)
    count_by_country={}
    for row in selected:
        count_by_country[row["country"]]=count_by_country.get(row["country"],0)+1
    for stats in statuses:
        stats["previews"]=count_by_country.get(stats["country"],0)
    indicative=sum(p["price_reference_rub"] is not None for p in selected)
    return {"schema":"jamaica.tour-previews.v1",
            "refreshed_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "classification":"PRELIMINARY_DETAILS_NOT_OFFERS",
            "origin":ALLOWED_ORIGIN,
            "countries_status":statuses,
            "source_scope":scope,
            "total_candidate_previews":total_candidates_before_country_cap,
            "truncated_to_public_limit":total_candidates_before_country_cap>len(selected),
            "previews":selected,
            "indicative_two_adult_rub_count":indicative,
            "quote_verified":False,"availability_verified":False,"bookable":False}


def main():
    p = argparse.ArgumentParser()
    p.add_argument("--directory", required=True)
    p.add_argument("--output", required=True)
    p.add_argument("--credentials", default="")
    p.add_argument("--max-countries", type=int, default=MAX_COUNTRIES)
    p.add_argument("--per-country", type=int, default=MAX_LISTS_PER_COUNTRY)
    p.add_argument("--discover-state", default="")
    args = p.parse_args()
    if not 1<=args.max_countries<=MAX_COUNTRIES or not 1<=args.per_country<=MAX_LISTS_PER_COUNTRY:
        raise bg.SyncHold("PROBE_LIMIT_INVALID")
    extra_priority=[]
    if args.discover_state:
        path=Path(args.discover_state)
        if path.is_symlink() or (path.exists() and path.stat().st_size>10000):
            raise bg.SyncHold("DISCOVERY_STATE_INVALID")
        if path.exists():
            state=json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(state,list) or len(state)>40 or not all(
                isinstance(name,str) and 2<=len(name)<=120 for name in state):
                raise bg.SyncHold("DISCOVERY_STATE_SCHEMA_INVALID")
            extra_priority=state
    catalog = json.loads(Path(args.directory).read_text(encoding="utf-8"))
    login, password = bg.read_secret(bg.credentials_path(args.credentials))
    # API only on an explicitly allowed host and paths; no arbitrary external URLs.
    bg.BASE = "https://export.bgoperator.ru/"
    result=build(catalog,bg.ApiClient(login,password),
                 args.max_countries,args.per_country,
                 extra_priority_names=extra_priority,
                 probe_slot=int(datetime.now(timezone.utc).timestamp()//300))
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
    print("COUNTRIES_ELIGIBLE_FOR_ORIGIN="+str(len([c for c in catalog["countries"]
       if c.get("has_tour_catalog") and bg.CITY_ID in c.get("origins",[])])))
    print("COUNTRIES_WITH_PREVIEWS="+str(len({p["country"] for p in result["previews"]})))
    print("COUNTRIES_WITH_TOUR_CATALOG="+str(result["source_scope"]["source_tour_countries"]))
    print("COUNTRIES_WITHOUT_IRKUTSK_FLAG_CHECKED="+str(result["source_scope"]["other_countries_probed_this_cycle"]))
    print("CANDIDATE_PREVIEWS_BEFORE_CAPPING="+str(result["total_candidate_previews"]))
    print("PUBLIC_PREVIEWS_TRUNCATED="+str(result["truncated_to_public_limit"]))
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
