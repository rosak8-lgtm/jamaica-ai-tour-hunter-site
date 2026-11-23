#!/usr/bin/env python3
"""Oracle-only official BG flight pair evidence audit. NO applicant or booking calls.

Only verified aggregate counts are printed. No raw operator responses, prices,
flight IDs, passenger info, HTML, auth tokens or supplier URLs are exported.
"""
from __future__ import annotations
import argparse
import json
import urllib.parse
import urllib.error
import sys
import time
from collections import Counter
from datetime import datetime,timezone
from pathlib import Path

import oracle_bg_route_sync as bg
import oracle_bg_price_detail_probe as detail
from oracle_bg_preview_export import choose_price_lists
from flight_availability_evidence import flight_pair_evidence

def detailed_url(listing,country_id):
    """Validate source URL and add documented read-only extended flight fields."""
    base=detail.safe_url(listing,country_id)
    parts=urllib.parse.urlsplit(base)
    p=dict(urllib.parse.parse_qsl(parts.query))
    if p.get("action")!="price" or p.get("xml")!="11":
        raise bg.SyncHold("FLIGHT_SOURCE_INVALID")
    p["xml"]="31"
    p["novirt"]="0"
    p["entr"]="21"
    return urllib.parse.urlunsplit(
        ("https","export.bgoperator.ru","/partners",
         urllib.parse.urlencode(p),""))

def inspect(directory,api,*,country_name:str=""):
    if (not isinstance(country_name,str) or len(country_name)>120 or
        any(x in country_name for x in ("\\n","\\r","\\x00"))):
        raise bg.SyncHold("INVALID_FLIGHT_COUNTRY_FILTER")
    countries=directory.get("countries",[])
    if not isinstance(countries,list) or len(countries)>300:
        raise bg.SyncHold("FLIGHT_COUNTRY_DIRECTORY_INVALID")
    eligible=[c for c in countries
              if isinstance(c,dict) and c.get("has_tour_catalog") is True
              and isinstance(c.get("name"),str) and
              isinstance(c.get("id"),str) and
              (c["name"]==country_name if country_name else
               bg.CITY_ID in c.get("origins",[]))]
    if not eligible or len(eligible)>80:
        raise bg.SyncHold("FLIGHT_COUNTRY_SCOPE_INVALID")
    # An exact named extra country may lack an old origins[] annotation.
    # The authenticated FILES request below STILL binds flt2=Irkutsk,
    # and without actual returned Irkutsk lists the result remains NO_FUTURE_LIST.
    reports=[]
    for c in eligible:
        report={"country":c["name"],"state":"UNVERIFIED",
                "rows":0,"structured_pairs":0,"both_green":0,
                "one_green":0,"stop_sale":0,"missing_composition":0}
        try:
            url="https://export.bgoperator.ru/yandex?"+urllib.parse.urlencode({
                "action":"files","flt":c["id"],"flt2":bg.CITY_ID,"xml":"11"})
            data=json.loads(api.get(url))
            lists=choose_price_lists(data.get("entries",[]) if isinstance(data,dict) else [],1)
            if not lists:
                report["state"]="NO_FUTURE_LIST"
                reports.append(report)
                continue
            full=json.loads(api.get(detailed_url(lists[0],c["id"])))
            rows=full.get("entries") if isinstance(full,dict) else None
            if not isinstance(rows,list) or len(rows)>25000:
                raise bg.SyncHold("EXTENDED_PRICE_SCHEMA_INVALID")
            report["rows"]=len(rows)
            for row in rows:
                if not isinstance(row,dict):continue
                evidence=flight_pair_evidence(row)
                if evidence["status"]=="STOP_SALE":
                    report["stop_sale"]+=1
                elif evidence["status"]=="UNVERIFIED":
                    report["missing_composition"]+=1
                else:
                    report["structured_pairs"]+=1
                    if evidence["both_green"]:report["both_green"]+=1
                    elif evidence["out_green"] or evidence["back_green"]:
                        report["one_green"]+=1
            report["state"]="CHECKED_EXTENDED"
        except (ValueError,KeyError,TimeoutError,bg.SyncHold,
                urllib.error.URLError,urllib.error.HTTPError):
            report["state"]="UNVERIFIED"
        reports.append(report)
        time.sleep(.5)
    return reports

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True)
    p.add_argument("--credentials",default="")
    p.add_argument("--country",default="")
    args=p.parse_args()
    directory=json.loads(Path(args.directory).read_text(encoding="utf-8"))
    if directory.get("schema")!="jamaica.destination-directory.v1":
        raise bg.SyncHold("DIRECTORY_SCHEMA_INVALID")
    login,password=bg.read_secret(bg.credentials_path(args.credentials))
    bg.BASE="https://export.bgoperator.ru/"
    reports=inspect(directory,bg.ApiClient(login,password),
                    country_name=args.country)
    print("JAMAICA_FLIGHT_EVIDENCE_READ_ONLY_V1")
    print("COUNTRIES_CHECKED="+str(len(reports)))
    print("COUNTRIES_WITH_BOTH_GREEN_EVIDENCE="+str(sum(r["both_green"]>0 for r in reports)))
    print("NOTE=FLIGHT_Q_IS_SNAPSHOT_NOT_CONFIRMED_BOOKING")
    print("BG_BEST_PRICE_MARKER_VERIFIED=NO")
    print("SALE_ELIGIBILITY=NO_SUPPLIER_QUOTE_OR_MARKER")
    for i,r in enumerate(reports,1):
        for k in ("country","state","rows","structured_pairs","both_green",
                  "one_green","stop_sale","missing_composition"):
            print("COUNTRY_"+str(i)+"_"+k.upper()+"="+str(r[k]))
    print("NO_BOOKING_NO_PASSENGERS_NO_PRICES_NO_SECRET_EXPORTED=YES")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("JAMAICA_FLIGHT_EVIDENCE_HOLD="+type(exc).__name__,file=sys.stderr)
        raise SystemExit(2)
