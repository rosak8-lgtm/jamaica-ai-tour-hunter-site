#!/usr/bin/env python3
"""Oracle-only official BG flight pair evidence audit. NO applicant or booking calls.

Only verified aggregate counts are printed. No raw operator responses, prices,
flight IDs, passenger info, HTML, auth tokens or supplier URLs are exported.
"""
from __future__ import annotations
import argparse
import json
import os
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
from flight_availability_evidence import flight_pair_evidence,flight_pair_reasons

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

def inspect(directory,api,*,country_name:str="",country_names=None,
            max_lists:int=1,probe_slot:int=0):
    # This is an operator-hosted READ ONLY diagnostic, not an inventory promise.
    # Explicit bounds protect supplier rate limits and time on old Oracle.
    if (type(max_lists) is not int or not 1<=max_lists<=5 or
        type(probe_slot) is not int or not 0<=probe_slot<=10000):
        raise bg.SyncHold("FLIGHT_LIST_OR_SLOT_LIMIT_INVALID")
    if (not isinstance(country_name,str) or len(country_name)>120 or
        any(x in country_name for x in ("\n","\r","\x00"))):
        raise bg.SyncHold("INVALID_FLIGHT_COUNTRY_FILTER")
    countries=directory.get("countries",[])
    if not isinstance(countries,list) or len(countries)>300:
        raise bg.SyncHold("FLIGHT_COUNTRY_DIRECTORY_INVALID")
    official=[c for c in countries if isinstance(c,dict)
              and c.get("has_tour_catalog") is True
              and isinstance(c.get("name"),str)
              and isinstance(c.get("id"),str)]
    allowed_names={c["name"] for c in official}
    if country_names is not None:
        if (country_name or type(country_names) is not list or
            not 1<=len(country_names)<=20 or
            any(type(name) is not str or name not in allowed_names
                for name in country_names) or
            len(set(country_names))!=len(country_names)):
            raise bg.SyncHold("OBSERVED_COUNTRY_SCOPE_INVALID")
        selected_names=set(country_names)
        eligible=[c for c in official if c["name"] in selected_names]
    else:
        eligible=[c for c in official
                  if (c["name"]==country_name if country_name else
                      bg.CITY_ID in c.get("origins",[]))]
    if not eligible or len(eligible)>80:
        raise bg.SyncHold("FLIGHT_COUNTRY_SCOPE_INVALID")
    # An exact named extra country may lack an old origins[] annotation.
    # The authenticated FILES request below STILL binds flt2=Irkutsk,
    # and without actual returned Irkutsk lists the result remains NO_FUTURE_LIST.
    reports=[]
    for c in eligible:
        report={"country":c["name"],"state":"UNVERIFIED",
                "lists_attempted":0,"lists_checked":0,"lists_failed":0,
                "rows":0,"structured_pairs":0,"both_green":0,
                "one_green":0,"neither_green":0,"stop_sale":0,
                "missing_composition":0,
                "out_green":0,"back_green":0,
                "out_on_request":0,"back_on_request":0,
                "out_sold_out":0,"back_sold_out":0,
                "out_regular_unconfirmed":0,"back_regular_unconfirmed":0,
                "out_unknown":0,"back_unknown":0}
        try:
            url="https://export.bgoperator.ru/yandex?"+urllib.parse.urlencode({
                "action":"files","flt":c["id"],"flt2":bg.CITY_ID,"xml":"11"})
            data=json.loads(api.get(url))
            lists=choose_price_lists(
                data.get("entries",[]) if isinstance(data,dict) else [],
                max_lists,probe_slot=probe_slot)
            if not lists:
                report["state"]="NO_FUTURE_LIST"
                reports.append(report)
                continue
            report["lists_attempted"]=len(lists)
            for list_index,listing in enumerate(lists):
                if list_index:
                    # Bound the request rate; no background loop or auto sending.
                    time.sleep(.25)
                try:
                    full=json.loads(api.get(detailed_url(listing,c["id"])))
                    rows=full.get("entries") if isinstance(full,dict) else None
                    if not isinstance(rows,list) or len(rows)>25000:
                        raise bg.SyncHold("EXTENDED_PRICE_SCHEMA_INVALID")
                except (ValueError,KeyError,TimeoutError,bg.SyncHold,
                        urllib.error.URLError,urllib.error.HTTPError):
                    report["lists_failed"]+=1
                    continue
                report["lists_checked"]+=1
                report["rows"]+=len(rows)
                for row in rows:
                    if not isinstance(row,dict):
                        continue
                    evidence=flight_pair_evidence(row)
                    if evidence["status"]=="STOP_SALE":
                        report["stop_sale"]+=1
                        continue
                    if evidence["status"]=="UNVERIFIED":
                        report["missing_composition"]+=1
                        continue
                    report["structured_pairs"]+=1
                    if evidence["both_green"]:
                        report["both_green"]+=1
                    elif evidence["out_green"] or evidence["back_green"]:
                        report["one_green"]+=1
                    else:
                        report["neither_green"]+=1
                    outward,returning=flight_pair_reasons(row)
                    for name,reason in (("out",outward),("back",returning)):
                        field={"GREEN":"green","ON_REQUEST":"on_request",
                               "SOLD_OUT":"sold_out",
                               "REGULAR_NOT_SEAT_VERIFIED":"regular_unconfirmed",
                               "UNKNOWN":"unknown"}[reason]
                        report[name+"_"+field]+=1
            if report["lists_checked"]==report["lists_attempted"]:
                report["state"]="CHECKED_EXTENDED"
            elif report["lists_checked"]>0:
                report["state"]="PARTIAL_EXTENDED"
            else:
                report["state"]="UNVERIFIED"
        except (ValueError,KeyError,TimeoutError,bg.SyncHold,
                urllib.error.URLError,urllib.error.HTTPError):
            report["state"]="UNVERIFIED"
        reports.append(report)
        time.sleep(.5)
    return reports

def read_owner_only_country_names(path:str):
    """Explicit 0600 public-country list staged from validated source shards."""
    name=Path(path)
    if not name.is_file() or name.is_symlink():
        raise bg.SyncHold("OBSERVED_COUNTRY_FILE_INVALID")
    info=name.stat()
    if (info.st_uid!=os.geteuid() or info.st_mode&0o077 or
        not 2<=info.st_size<=4000):
        raise bg.SyncHold("OBSERVED_COUNTRY_FILE_UNSAFE")
    value=json.loads(name.read_text(encoding="utf-8"))
    if (type(value) is not list or not 1<=len(value)<=20 or
        any(type(x) is not str or not 1<=len(x)<=120 or
            any(c in x for c in ("\n","\r","\x00")) for x in value) or
        len(set(value))!=len(value)):
        raise bg.SyncHold("OBSERVED_COUNTRY_LIST_INVALID")
    return value


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True)
    p.add_argument("--credentials",default="")
    p.add_argument("--country",default="")
    p.add_argument("--countries-file",default="")
    p.add_argument("--max-lists",type=int,default=1)
    p.add_argument("--probe-slot",type=int,default=0)
    args=p.parse_args()
    directory=json.loads(Path(args.directory).read_text(encoding="utf-8"))
    if directory.get("schema")!="jamaica.destination-directory.v1":
        raise bg.SyncHold("DIRECTORY_SCHEMA_INVALID")
    login,password=bg.read_secret(bg.credentials_path(args.credentials))
    bg.BASE="https://export.bgoperator.ru/"
    selected_names=(read_owner_only_country_names(args.countries_file)
                    if args.countries_file else None)
    reports=inspect(directory,bg.ApiClient(login,password),
                    country_name=args.country,country_names=selected_names,
                    max_lists=args.max_lists,probe_slot=args.probe_slot)
    print("JAMAICA_FLIGHT_EVIDENCE_READ_ONLY_V1")
    print("COUNTRIES_CHECKED="+str(len(reports)))
    print("COUNTRIES_WITH_BOTH_GREEN_EVIDENCE="+str(sum(r["both_green"]>0 for r in reports)))
    print("NOTE=FLIGHT_Q_IS_SNAPSHOT_NOT_CONFIRMED_BOOKING")
    print("BG_BEST_PRICE_MARKER_VERIFIED=NO")
    print("SALE_ELIGIBILITY=NO_SUPPLIER_QUOTE_OR_MARKER")
    print("LIST_LIMIT_PER_COUNTRY="+str(args.max_lists))
    print("PRICE_LIST_ROTATION_SLOT="+str(args.probe_slot))
    print("COUNTRY_AGGREGATES_ARE_SOURCE_ROWS_NOT_UNIQUE_SELLABLE_TOURS=YES")
    for i,r in enumerate(reports,1):
        for k in (
            "country","state","lists_attempted","lists_checked","lists_failed",
            "rows","structured_pairs","both_green","one_green","neither_green",
            "stop_sale","missing_composition","out_green","back_green",
            "out_on_request","back_on_request","out_sold_out","back_sold_out",
            "out_regular_unconfirmed","back_regular_unconfirmed",
            "out_unknown","back_unknown"
        ):
            print("COUNTRY_"+str(i)+"_"+k.upper()+"="+str(r[k]))
    print("NO_BOOKING_NO_PASSENGERS_NO_PRICES_NO_SECRET_EXPORTED=YES")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("JAMAICA_FLIGHT_EVIDENCE_HOLD="+type(exc).__name__,file=sys.stderr)
        raise SystemExit(2)
