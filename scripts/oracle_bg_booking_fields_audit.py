#!/usr/bin/env python3
"""Operator quote prerequisite audit on Oracle; strictly read-only.

The tour operator's quote request needs original PRIVATE price fields and a
separate authorized booking API. This script proves presence of source inputs
for selected existing Jamaica preview IDs without sending any quote/booking
request, exposing prices, IDs, PII, tokens or secret URLs.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

import oracle_bg_route_sync as bg
import oracle_bg_price_detail_probe as detail
import oracle_bg_preview_export as preview
import oracle_bg_multicountry_price_scan as scan
import tour_price_reference as price_ref

SAFE_FLAGS=("template_id","roommeal_id","main_duration","departure_date",
            "operator_prx","two_adult_price_option","flight_selection_reference")
MAX_LISTS_PER_PREVIEW=12

def assess_row(row,payload,listing,selected,hotels):
    if not isinstance(row,dict) or not isinstance(payload,dict):
        return None
    candidate=preview.safe_preview(row,selected["country"],hotels,payload.get("cur"))
    if not candidate or candidate["id"]!=selected["id"]:
        return None
    prices=row.get("prices",[])
    age_prices=[p for p in prices if isinstance(p,dict) and
                not p.get("isstop") and price_ref.adult_pair(p.get("ag"))]
    return {
        "template_id":bool(re.fullmatch(r"[0-9]{7,22}",str(
            row.get("id_price") or listing.get("id_price") or ""))),
        "roommeal_id":bool(re.fullmatch(r"[0-9]{7,22}",str(row.get("id_ns") or ""))),
        "main_duration":bool(preview.nights_value(row.get("o_duration"))),
        "departure_date":bool(bg.date_iso(row.get("dt") or row.get("tour_date"))),
        "operator_prx":bool(isinstance(payload.get("prx"),str) and
                            1<=len(payload["prx"])<=512),
        "two_adult_price_option":bool(age_prices),
        "flight_selection_reference":bool(
            row.get("sr") or any(p.get("sr") or p.get("href2")
                                 for p in age_prices))
    }

def audit(directory,feed,api,limit=3):
    if (directory.get("schema")!="jamaica.destination-directory.v1" or
        feed.get("schema")!="jamaica.tour-previews.v1"):
        raise bg.SyncHold("BAD_FEED_SCHEMA")
    chosen=scan.select_candidates(feed,limit=limit)
    hotels={str(h["id"]):h for h in directory.get("hotels",[])
            if isinstance(h,dict) and h.get("id") and h.get("country")}
    countries={c["name"]:c for c in directory.get("countries",[])
               if isinstance(c,dict) and c.get("name")}
    outputs=[]
    for selected in chosen:
        country=countries.get(selected["country"])
        counts=dict.fromkeys(SAFE_FLAGS,0)
        matched=0
        lists=0
        status="NO_PRICE_INPUT"
        if not country:continue
        query=urllib.parse.urlencode({"action":"files","flt":country["id"],
                                       "flt2":bg.CITY_ID,"xml":"11"})
        try:
            file_feed=json.loads(api.get("https://export.bgoperator.ru/yandex?"+query))
            sources=file_feed.get("entries",[])
            if not isinstance(sources,list):raise bg.SyncHold("FILES_SCHEMA")
            # Same on-demand source matching used by customer tour detail:
            # independent same-day price lists may contain selected route in
            # the 5th or later file, and FILES origins[] may lag the live API.
            sources=scan.selected.matching_source_listings(
                sources,selected["depart_date"],selected["nights"],
                limit=MAX_LISTS_PER_PREVIEW)
            for item in sources:
                url=detail.safe_url(item,country["id"])
                raw=json.loads(api.get(url))
                rows=raw.get("entries") if isinstance(raw,dict) else None
                if not isinstance(rows,list) or len(rows)>preview.MAX_RESPONSE_ROWS:
                    continue
                lists+=1
                for row in rows:
                    flags=assess_row(row,raw,item,selected,hotels)
                    if flags is None:continue
                    matched+=1
                    for key,val in flags.items():
                        counts[key]+=int(val)
            if matched:
                status="INSPECTED_SOURCE_ONLY"
        except (bg.SyncHold,urllib.error.HTTPError,urllib.error.URLError,
                ValueError,KeyError,TimeoutError):
            status="SOURCE_UNVERIFIED"
        outputs.append({"country":selected["country"],"preview_id":selected["id"],
                        "depart_date":selected["depart_date"],"lists":lists,
                        "matched":matched,"fields":counts,"status":status,
                        "live_quote_verified":False,"bookable":False})
    return outputs

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True)
    p.add_argument("--previews",required=True)
    p.add_argument("--credentials",default="")
    p.add_argument("--limit",type=int,default=3)
    args=p.parse_args()
    if not 1<=args.limit<=3:raise bg.SyncHold("SCAN_LIMIT")
    directory=json.loads(Path(args.directory).read_text(encoding="utf-8"))
    feed=json.loads(Path(args.previews).read_text(encoding="utf-8"))
    login,password=bg.read_secret(bg.credentials_path(args.credentials))
    bg.BASE="https://export.bgoperator.ru/"
    outputs=audit(directory,feed,bg.ApiClient(login,password),args.limit)
    print("JAMAICA_BOOKING_FIELDS_READONLY_AUDIT_V1")
    print("COUNTRIES_CHECKED="+str(len(outputs)))
    for i,row in enumerate(outputs,1):
        print("COUNTRY_"+str(i)+"="+row["country"])
        print("STATUS_"+str(i)+"="+row["status"])
        print("MATCHED_ROWS_"+str(i)+"="+str(row["matched"]))
        for field in SAFE_FLAGS:
            print(field.upper()+"_"+str(i)+"="+str(row["fields"][field]))
    print("NO_POST_NO_QUOTE_NO_BOOKING_NO_CARD_DATA=YES")
    if not outputs or all(x["matched"]==0 for x in outputs):
        return 2
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("JAMAICA_BOOKING_FIELD_AUDIT_HOLD="+type(exc).__name__,file=sys.stderr)
        sys.exit(2)
