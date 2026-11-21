#!/usr/bin/env python3
"""Bounded read-only comparison of future offers from different destinations.

Never interprets price-list references as a payable tour. Only aggregates and
public preview IDs are printed. Runs with existing private Oracle credentials.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.error
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

import oracle_bg_route_sync as bg
import oracle_bg_selected_quote_probe as selected

MAX_CANDIDATES=4

def select_candidates(feed,today=None,limit=MAX_CANDIDATES):
    today=today or datetime.now(timezone.utc).date()
    if feed.get("schema")!="jamaica.tour-previews.v1" or feed.get("bookable") is not False:
        raise bg.SyncHold("PREVIEW_FEED_INVALID")
    rows=feed.get("previews",[])
    if not isinstance(rows,list):
        raise bg.SyncHold("PREVIEW_ROWS_INVALID")
    found={}
    for item in rows:
        if not isinstance(item,dict):
            continue
        try:day=date.fromisoformat(item.get("depart_date",""))
        except (ValueError,TypeError):continue
        if not today+timedelta(days=1)<=day<=today+timedelta(days=180):
            continue
        country=item.get("country")
        if not isinstance(country,str) or country=="Россия":
            continue
        if (not selected.ID_RE.fullmatch(str(item.get("id",""))) or
            item.get("bookable") is not False or item.get("quote_verified") is not False or
            item.get("availability_verified") is not False or item.get("flight_verified") is not False):
            continue
        rank=(day,item["id"])
        if country not in found or rank<(found[country][0],found[country][1]["id"]):
            found[country]=(day,item)
    # Approved Irkutsk search priority: these destinations first, then every other country.
    # This controls only bounded READ-ONLY preview sampling, not tour verification or publishing.
    priority=("Таиланд","Китай","Вьетнам")
    countries=sorted(found,key=lambda name:(priority.index(name) if name in priority else 100,name))
    return [found[name][1] for name in countries[:limit]]

def catalog_summary(feed, today=None):
    """Safe aggregate reasons why a public catalog cannot provide candidates."""
    today=today or datetime.now(timezone.utc).date()
    rows=feed.get("previews",[])
    if not isinstance(rows,list):
        raise bg.SyncHold("PREVIEW_ROWS_INVALID")
    summary={"total":0,"future":0,"future_non_domestic":0,
             "future_non_domestic_unverified":0,"countries":set(),
             "earliest_future":None,"latest_future":None}
    for item in rows:
        if not isinstance(item,dict):
            continue
        summary["total"]+=1
        try:day=date.fromisoformat(item.get("depart_date",""))
        except (ValueError,TypeError):continue
        if day<=today or day>today+timedelta(days=180):
            continue
        summary["future"]+=1
        d=day.isoformat()
        summary["earliest_future"]=min(summary["earliest_future"] or d,d)
        summary["latest_future"]=max(summary["latest_future"] or d,d)
        if item.get("country")!="Россия":
            summary["future_non_domestic"]+=1
            if (item.get("bookable") is False and item.get("quote_verified") is False and
                item.get("availability_verified") is False and item.get("flight_verified") is False):
                summary["future_non_domestic_unverified"]+=1
                if isinstance(item.get("country"),str):
                    summary["countries"].add(item["country"])
    summary["countries"]=sorted(summary["countries"])
    return summary

def run(directory,feed,api,limit=MAX_CANDIDATES,today=None):
    result=[]
    for p in select_candidates(feed,today,limit):
        try:
            item=selected.inspect_selected(directory,feed,p["id"],api)
            result.append(item)
        except (bg.SyncHold,urllib.error.URLError,urllib.error.HTTPError,
                ValueError,KeyError,TimeoutError):
            result.append({"preview_id":p["id"],"country":p["country"],
                           "depart_date":p["depart_date"],"status":"UNVERIFIED",
                           "detail_lists":0,"matched_rows":0,"price_options":0,
                           "rub_price_fields":0,"two_adults_age_markers":0,
                           "two_adults_with_rub":0,"two_adults_amount_only":0,
                           "age_value_present":0,"age_marker_unrecognized":0,
                           "blocked_price_options":0})
    return result

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True)
    p.add_argument("--previews",required=True)
    p.add_argument("--limit",type=int,default=3)
    p.add_argument("--credentials",default="")
    args=p.parse_args()
    if not 1<=args.limit<=4:
        raise bg.SyncHold("LIMIT_INVALID")
    directory=json.loads(Path(args.directory).read_text(encoding="utf-8"))
    feed=json.loads(Path(args.previews).read_text(encoding="utf-8"))
    login,password=bg.read_secret(bg.credentials_path(args.credentials))
    bg.BASE="https://export.bgoperator.ru/"
    results=run(directory,feed,bg.ApiClient(login,password),args.limit)
    print("JAMAICA_MULTICOUNTRY_PRICE_REFERENCE_SCAN_V1")
    meta=catalog_summary(feed)
    print("CATALOG_ROWS="+str(meta["total"]))
    print("FUTURE_PREVIEWS="+str(meta["future"]))
    print("FUTURE_INTERNATIONAL_PREVIEWS="+str(meta["future_non_domestic_unverified"]))
    print("FUTURE_COUNTRIES="+",".join(meta["countries"]))
    print("EARLIEST_FUTURE="+str(meta["earliest_future"] or "NONE"))
    print("LATEST_FUTURE="+str(meta["latest_future"] or "NONE"))
    print("COUNTRIES_CHECKED="+str(len(results)))
    for i,item in enumerate(results,1):
        print("PREVIEW_"+str(i)+"="+item["preview_id"])
        print("COUNTRY_"+str(i)+"="+item["country"])
        print("DEPART_DATE_"+str(i)+"="+item["depart_date"])
        print("STATUS_"+str(i)+"="+item["status"])
        print("MATCHED_ROWS_"+str(i)+"="+str(item["matched_rows"]))
        print("TWO_ADULTS_WITH_RUB_"+str(i)+"="+str(item["two_adults_with_rub"]))
        print("TWO_ADULTS_AMOUNT_ONLY_"+str(i)+"="+str(item["two_adults_amount_only"]))
        print("AGE_VALUE_PRESENT_"+str(i)+"="+str(item["age_value_present"]))
        print("AGE_MARKER_UNRECOGNIZED_"+str(i)+"="+str(item["age_marker_unrecognized"]))
    print("NO_VERIFIED_QUOTES_NO_BOOKING_NO_PRICES_EXPORTED=YES")
    if not results or all(item["matched_rows"]==0 for item in results):
        return 2
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("JAMAICA_MULTICOUNTRY_SCAN_HOLD="+type(exc).__name__,file=sys.stderr)
        sys.exit(2)
