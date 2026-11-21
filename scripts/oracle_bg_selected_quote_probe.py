#!/usr/bin/env python3
"""Read-only price-list reconciliation for one selected public JAMAICA preview.

Does NOT produce a verified quote, flight confirmation, availability or booking.
Only exact preview-matching counts and price option metadata are exposed;
numeric values, links and supplier identifiers never leave Oracle.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
from decimal import Decimal, InvalidOperation
from datetime import datetime, timezone
from pathlib import Path

import oracle_bg_route_sync as bg
import oracle_bg_price_detail_probe as detail
import oracle_bg_preview_export as preview

ID_RE = re.compile(r"^p_[a-f0-9]{24}$")
MAX_DETAIL_LISTS = 4

def valid_positive_amount(value):
    """Reject arrays, booleans, zero, NaN and non-numeric supplier fields."""
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):
        return False
    try:
        amount=Decimal(str(value).strip())
        return amount.is_finite() and amount>0
    except (InvalidOperation,ValueError):
        return False


def adult_pair_marker(value):
    """Recognize two ADULT age bands, but do not infer group price scope."""
    if not isinstance(value, str):
        return False
    parts=[x.strip().strip("[]()") for x in value.split(",")]
    if len(parts)!=2:
        return False
    for part in parts:
        if part=="12+":
            continue
        m=re.fullmatch(r"(\d{1,2})-(\d{1,3})",part)
        if not m or int(m.group(1))<12 or int(m.group(2))<int(m.group(1)):
            return False
    return True


def rub_option_amount(price, currency=None):
    """Interpret RUB operator price-list amount, or explicit RUR converted field.

    This is only a preliminary price-list signal. NEVER a verified quote.
    """
    cur=currency.strip().upper() if isinstance(currency,str) else ""
    if cur in ("RUB","RUR"):
        return valid_positive_amount(price.get("amount"))
    return valid_positive_amount(price.get("RUR"))


def inspect_match(rows, selected, hotels, currency=None):
    """Match real operator rows to the exact selected site preview ID."""
    matches = 0
    prices = 0
    rub_price_fields = 0
    exact_two_adults = 0
    blocked = 0
    two_adults_with_rub = 0
    two_adults_amount_only = 0
    age_value_present = 0
    age_marker_unrecognized = 0
    for row in rows:
        candidate = preview.safe_preview(row, selected["country"], hotels)
        if not candidate or candidate["id"] != selected["id"]:
            continue
        # Safety: preview ID alone could collide for differing resorts/meal
        # conditions. Only record metadata, never treat these as a sale.
        matches += 1
        for p in row.get("prices", []):
            if not isinstance(p, dict):
                continue
            if p.get("isstop"):
                blocked += 1
                continue
            prices += 1
            if rub_option_amount(p,currency):
                rub_price_fields += 1
            age=str(p.get("ag", "")).strip()
            if age:
                age_value_present += 1
            adult_pair = adult_pair_marker(age)
            if age and not adult_pair:
                age_marker_unrecognized += 1
            if adult_pair:
                exact_two_adults += 1
                if rub_option_amount(p,currency):
                    two_adults_with_rub += 1
                elif valid_positive_amount(p.get("amount")):
                    two_adults_amount_only += 1
    return {"matched_rows": matches, "price_options": prices,
            "rub_price_fields": rub_price_fields,
            "two_adults_age_markers": exact_two_adults,
            "blocked_price_options": blocked,
            "two_adults_with_rub": two_adults_with_rub,
            "two_adults_amount_only":two_adults_amount_only,
            "age_value_present":age_value_present,
            "age_marker_unrecognized":age_marker_unrecognized}

def inspect_selected(directory, public_feed, chosen_id, api):
    if directory.get("schema") != "jamaica.destination-directory.v1":
        raise bg.SyncHold("DIRECTORY_SCHEMA_UNKNOWN")
    if (public_feed.get("schema") != "jamaica.tour-previews.v1" or
        public_feed.get("bookable") is not False):
        raise bg.SyncHold("PREVIEW_FEED_INVALID")
    matches = [p for p in public_feed.get("previews", []) if
               isinstance(p,dict) and p.get("id") == chosen_id]
    if len(matches) != 1:
        raise bg.SyncHold("PREVIEW_NOT_FOUND_OR_AMBIGUOUS")
    selected = matches[0]
    if selected.get("bookable") is not False or selected.get("quote_verified") is not False:
        raise bg.SyncHold("PREVIEW_CLAIMS_BOOKABILITY")
    if selected.get("origin") != preview.ALLOWED_ORIGIN:
        raise bg.SyncHold("ORIGIN_UNSUPPORTED")
    if selected.get("depart_date", "") < datetime.now(timezone.utc).date().isoformat():
        raise bg.SyncHold("PREVIEW_EXPIRED")
    country = next((c for c in directory.get("countries", []) if
                    c.get("name")==selected.get("country") and
                    bg.CITY_ID in c.get("origins", []) and c.get("has_tour_catalog")),None)
    if not country:
        raise bg.SyncHold("COUNTRY_UNSUPPORTED")
    hotels = {str(h.get("id")): h for h in directory.get("hotels", [])
              if isinstance(h,dict) and h.get("id") and h.get("country")}
    q=urllib.parse.urlencode({"action":"files", "flt":country["id"],
                               "flt2":bg.CITY_ID,"xml":"11"})
    file_feed=json.loads(api.get("https://export.bgoperator.ru/yandex?"+q))
    entries=file_feed.get("entries")
    if not isinstance(entries,list):
        raise bg.SyncHold("FILES_SCHEMA_UNKNOWN")
    # The public preview was taken from a specific departure date. Re-check
    # only that date; never scan unrelated dates or country inventories.
    matching_listings=[e for e in entries if isinstance(e,dict) and
                       bg.date_iso(e.get("date")) and
                       bg.date_iso(e.get("date")).isoformat()==selected["depart_date"] and
                       e.get("stop") is None][:MAX_DETAIL_LISTS]
    summary={"matched_rows":0,"price_options":0,"rub_price_fields":0,
             "two_adults_age_markers":0,"blocked_price_options":0,
             "two_adults_with_rub":0,
             "two_adults_amount_only":0,"age_value_present":0,
             "age_marker_unrecognized":0}
    detail_lists=0
    for item in matching_listings:
        url=detail.safe_url(item,country["id"])
        data=json.loads(api.get(url))
        rows=data.get("entries") if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)>preview.MAX_RESPONSE_ROWS:
            continue
        detail_lists+=1
        result=inspect_match(rows, selected, hotels, data.get('cur'))
        for key, value in result.items():
            summary[key]+=value
    return {"preview_id":chosen_id,"country":selected["country"],
            "depart_date":selected["depart_date"],"detail_lists":detail_lists,
            **summary,"quote_verified":False,"availability_verified":False,
            "flight_verified":False,"bookable":False,
            "status":("NO_CURRENT_MATCH" if not summary["matched_rows"] else
                      "POTENTIAL_2_ADULT_RUB_PRICE_OPTION" if summary["two_adults_with_rub"] else
                      "POTENTIAL_2_ADULT_AMOUNT_CURRENCY_UNVERIFIED" if summary["two_adults_amount_only"] else
                      "PRICE_REFERENCE_NOT_SUITABLE_FOR_2_ADULT_RUB_CHECK")}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",required=True)
    parser.add_argument("--previews",required=True)
    parser.add_argument("--preview-id",required=True)
    parser.add_argument("--credentials",default="")
    args=parser.parse_args()
    if not ID_RE.fullmatch(args.preview_id):
        raise bg.SyncHold("PREVIEW_ID_INVALID")
    directory=json.loads(Path(args.directory).read_text(encoding="utf-8"))
    feed=json.loads(Path(args.previews).read_text(encoding="utf-8"))
    login,password=bg.read_secret(bg.credentials_path(args.credentials))
    bg.BASE="https://export.bgoperator.ru/"
    result=inspect_selected(directory,feed,args.preview_id,bg.ApiClient(login,password))
    print("JAMAICA_SELECTED_PRICE_REFERENCE_V1")
    for key in ("preview_id","country","depart_date","detail_lists",
                "matched_rows","price_options","rub_price_fields",
                "two_adults_age_markers","two_adults_with_rub",
                "two_adults_amount_only","age_value_present","age_marker_unrecognized",
                "blocked_price_options","status"):
        print(key.upper()+"="+str(result[key]))
    print("QUOTE_VERIFIED=NO")
    print("NO_SALE_NO_PAYMENT_NO_SUPPLIER_IDENTIFIERS_EXPORTED=YES")
    if not result["matched_rows"]:
        return 2
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as error:
        print("JAMAICA_SELECTED_PRICE_HOLD="+type(error).__name__,file=sys.stderr)
        sys.exit(2)
