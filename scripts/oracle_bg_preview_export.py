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
import catalog_size_budget as byte_limit

MAX_ROWS = 60000
MAX_RESPONSE_ROWS = 25000
MAX_COUNTRIES = 120
MAX_PER_COUNTRY = 12000
MAX_LISTS_PER_COUNTRY = 5
EXTRA_DISCOVERY_BATCH = 8
PRIORITY_ADDITIONAL_COUNTRIES = ("Китай","Вьетнам")
ALLOWED_ORIGIN = "Иркутск"
# Align exact source rows with the independent native-browser route horizon.
# Broad price-list discovery retains its existing 180-day request scope.
EXACT_DEPARTURE_HORIZON_DAYS = 730

def normalize_date(value):
    d = bg.date_iso(value)
    today = datetime.now(timezone.utc).date()
    if d and today <= d <= today + timedelta(days=EXACT_DEPARTURE_HORIZON_DAYS):
        return d.isoformat()
    return None

def nights_value(value):
    try:
        n = int(str(value))
        return n if 3 <= n <= 180 else None
    except (TypeError, ValueError):
        return None

def safe_preview(entry, country, hotel_by_id, price_currency=None, *, origin_scope=None):
    if origin_scope is not None and country != origin_scope.country:
        return None
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
        "id": ("p_" + hashlib.sha256(key.encode()).hexdigest()[:24] if origin_scope is None else origin_scope.preview_id(hotel_id,tour_date,nights,room)),
        "hotel_id": hotel_id,
        "hotel": name,
        "country": country,
        "origin": ALLOWED_ORIGIN if origin_scope is None else origin_scope.origin,
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

def advertised_nights(entry):
    """Only real nights from BG FILES metadata, NEVER inferred tour availability."""
    raw=entry.get("duration") if isinstance(entry,dict) else None
    if type(raw) is int:raw=str(raw)
    if not isinstance(raw,str) or len(raw)>1200 or not re.fullmatch(r"[0-9/,;\s]+",raw):
        return []
    return sorted({int(x) for x in re.findall(r"\d+",raw) if 3<=int(x)<=180})


def _listing_identity(day,entry):
    """Different id_price on the same date is NOT a duplicate."""
    ident=str(entry.get("id_price","")).strip()
    if re.fullmatch(r"\d{4,25}",ident):
        return (day,"id",ident)
    url=entry.get("url")
    if isinstance(url,str) and len(url)<=2048:
        try:
            p=urllib.parse.urlsplit(url)
            if p.hostname in ("export.bgoperator.ru","www.bgoperator.ru") and p.scheme in ("http","https"):
                ids=urllib.parse.parse_qs(p.query).get("id_price",[])
                if len(ids)==1 and re.fullmatch(r"\d{4,25}",ids[0]):
                    return (day,"id",ids[0])
        except ValueError:
            pass
    route=entry.get("route")
    if isinstance(route,str) and 0<len(route)<=500:
        return (day,"route",route)
    return (day,"anonymous","")


def _future_listings(entries,today):
    rows=[]
    if not isinstance(entries,list):return rows
    for entry in entries:
        if not isinstance(entry,dict) or entry.get("stop") is not None:
            continue
        d=bg.date_iso(entry.get("date"))
        if d is not None and today<d<=today+timedelta(days=180):
            rows.append((d,entry,_listing_identity(d,entry)))
    rows.sort(key=lambda x:x[0])
    seen=set()
    result=[]
    for row in rows:
        if row[2] not in seen:
            result.append(row)
            seen.add(row[2])
    return result


def choose_price_lists(entries, limit=2, today=None, *, probe_slot=0):
    """Rotate real lists across dates/months/routes under the unchanged 5-list cap.

    A departure date may contain multiple id_price values AND different sets
    of durations. Never remove those on date equality alone. Source metadata
    is only a PREVIEW, not verified seats/room/price.
    """
    today=today or datetime.now(timezone.utc).date()
    if type(limit) is not int or not 1<=limit<=MAX_LISTS_PER_COUNTRY:
        return []
    if type(probe_slot) is not int or probe_slot<0:return []
    rows=_future_listings(entries,today)
    if not rows:return []
    if limit<=2:
        out=[]
        days=set()
        for day,entry,_ in rows:
            if day not in days:
                out.append(entry)
                days.add(day)
                if len(out)==limit:break
        return out
    if len(rows)<=limit:return [r[1] for r in rows]
    nearest=rows[0][0]
    first_options=[r for r in rows if r[0]==nearest]
    first=first_options[probe_slot%len(first_options)]
    chosen=[first]
    keys={first[2]}
    months={}
    for row in rows:
        months.setdefault((row[0].year,row[0].month),[]).append(row)
    later=sorted(m for m in months if m!=(nearest.year,nearest.month))
    if later:
        offset=probe_slot%len(later)
        for month in later[offset:]+later[:offset]:
            opts=months[month]
            pick=opts[(probe_slot//len(later))%len(opts)]
            if pick[2] not in keys:
                chosen.append(pick)
                keys.add(pick[2])
            if len(chosen)==limit:break
    while len(chosen)<limit and len(keys)<len(rows):
        rest=[r for r in rows if r[2] not in keys]
        offset=probe_slot%len(rest)
        rest=rest[offset:]+rest[:offset]
        covered={n for _,entry,_ in chosen for n in advertised_nights(entry)}
        used_days={r[0] for r in chosen}
        pick=max(rest,key=lambda r:(len(set(advertised_nights(r[1]))-covered),
                                     int(r[0] not in used_days)))
        chosen.append(pick)
        keys.add(pick[2])
    return [r[1] for r in sorted(chosen,key=lambda x:x[0])]



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
        # A popular 3- or 7-night tariff can produce thousands of room variants.
        # Rank *each actual duration* separately inside each departure date;
        # only then revisit repeated rooms of a duration. Without this, a
        # bounded public catalog can suppress genuine 10/12/14/21-night tours.
        # These remain unverified PREVIEWS, never saleable prices or offers.
        dates_by_night={}
        for day,values in dates.items():
            grouped={}
            for item in values:
                night=item.get("nights")
                key=night if type(night) is int and 3<=night<=180 else None
                grouped.setdefault(key,[]).append(item)
            for same_night in grouped.values():
                same_night.sort(key=ranking)
            night_order=sorted(grouped,key=lambda k:(
                ranking(grouped[k][0])[0],k if k is not None else 999))
            interleaved=[]
            for layer in range(max(len(v) for v in grouped.values())):
                for night in night_order:
                    if layer<len(grouped[night]):
                        interleaved.append(grouped[night][layer])
            dates_by_night[day]=interleaved
        # Continue fairly across dates before taking more from any one date.
        date_keys=sorted(dates_by_night,
                         key=lambda day:(ranking(dates_by_night[day][0])[0],day))
        chosen=[]
        for layer in range(max(len(v) for v in dates_by_night.values())):
            for day in date_keys:
                if layer<len(dates_by_night[day]):
                    chosen.append(dates_by_night[day][layer])
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
               "source_price_lists":0,"source_advertised_nights":[],
               "selected_price_lists":0,"selected_advertised_nights":[],
               "status":"NO_CONFIRMED_LIST"}
        try:
            q=urllib.parse.urlencode({"action":"files","flt":country["id"],
                                       "flt2":bg.CITY_ID,"xml":"11"})
            listings=json.loads(api.get("https://export.bgoperator.ru/yandex?"+q))
            entries=listings.get("entries") if isinstance(listings,dict) else None
            if not isinstance(entries,list):
                raise bg.SyncHold("FILES_SCHEMA_UNKNOWN")
            source_lists=_future_listings(entries,datetime.now(timezone.utc).date())
            stats["source_price_lists"]=len(source_lists)
            stats["source_advertised_nights"]=sorted({
                n for _,entry,_ in source_lists for n in advertised_nights(entry)})
            selected_lists=choose_price_lists(entries,per_country,probe_slot=probe_slot)
            stats["selected_price_lists"]=len(selected_lists)
            stats["selected_advertised_nights"]=sorted({
                n for entry in selected_lists for n in advertised_nights(entry)})
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
        except urllib.error.HTTPError as exc:
            # Stop the entire broad sweep after a supplier access/rate hold.
            # Do not continue issuing requests to the other countries.
            if exc.code in (401,403,429):raise
            stats["status"]="UNVERIFIED"
        except (bg.SyncHold,urllib.error.URLError,ValueError,TimeoutError,KeyError):
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
    p.add_argument("--probe-slot",type=int,default=None)
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
                 probe_slot=(args.probe_slot if args.probe_slot is not None else int(datetime.now(timezone.utc).timestamp()//300)))
    if not result["previews"]:
        for i, stats in enumerate(result["countries_status"], 1):
            print("COUNTRY_"+str(i)+"="+stats["country"])
            print("ROWS_SCANNED_"+str(i)+"="+str(stats["rows_scanned"]))
            print("HOTEL_IDS_MATCHED_"+str(i)+"="+str(stats["known_hotel_ids"]))
        raise bg.SyncHold("NO_MATCHED_HOTEL_PREVIEWS_DO_NOT_PUBLISH_EMPTY")
    # Compact real, preliminary source rows *before* writing the file.
    # A 60k-entry feed can exceed Oracle's 45MB guard. Keep representative
    # hotels/dates/countries, never fabricate a missing country or a price.
    result,dropped_by_budget=byte_limit.fit_feed(result,max_bytes=32_000_000)
    destination = Path(args.output)
    if destination.is_symlink():
        raise bg.SyncHold("OUTPUT_SYMLINK")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temp = destination.with_suffix(".tmp")
    temp.write_text(json.dumps(result, ensure_ascii=False, separators=(",", ":"))+"\n", encoding="utf-8")
    temp.chmod(0o600)
    temp.replace(destination)
    print("JAMAICA_PREVIEW_EXPORT_PASS")
    print("JAMAICA_PREVIEW_OUTPUT_BYTES="+str(destination.stat().st_size))
    print("JAMAICA_PREVIEW_DROPPED_BY_BYTE_BUDGET="+str(dropped_by_budget))
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
