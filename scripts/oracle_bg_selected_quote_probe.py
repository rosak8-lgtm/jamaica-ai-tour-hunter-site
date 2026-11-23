#!/usr/bin/env python3
"""Read-only price-list reconciliation for one selected public JAMAICA preview.

Does NOT produce a verified quote, flight confirmation, availability or booking.
Only exact preview-matching counts and price option metadata are exposed;
numeric values, links and supplier identifiers never leave Oracle.
"""
from __future__ import annotations
import argparse
import json
import os
import stat
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

# Reuse private, source-only age-bucket matching with no passenger PII.
sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend.bg_price_age_scope import candidate_report
from backend.bg_private_source_crosswalk import private_source_candidates

ID_RE = re.compile(r"^p_[a-f0-9]{24}$")
MAX_DETAIL_LISTS = 16
MAX_SOURCE_FILE_ENTRIES = 20000

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


def inspect_match(rows, selected, hotels):
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
            if valid_positive_amount(p.get("RUR")):
                rub_price_fields += 1
            age=str(p.get("ag", "")).strip()
            if age:
                age_value_present += 1
            adult_pair = adult_pair_marker(age)
            if age and not adult_pair:
                age_marker_unrecognized += 1
            if adult_pair:
                exact_two_adults += 1
                if valid_positive_amount(p.get("RUR")):
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

def matching_source_listings(entries, departure, nights, *,
                             limit=MAX_DETAIL_LISTS):
    """Bounded supplier FILES inventory for the EXACT selected departure.

    Operator directories can omit Irkutsk even when a real authenticated
    Irkutsk price list exists. Never treat the directory flag as proof:
    examine only FILES responses queried with the trusted Irkutsk city ID.
    A previous limit of four unsorted same-day lists hid authentic tours
    when the selected preview came from the 5th or later list.

    Explicit duration mismatches are skipped; missing duration metadata is
    treated as unknown (probe required), never fabricated as a match.
    """
    if (not isinstance(entries,list) or len(entries)>MAX_SOURCE_FILE_ENTRIES or
        not isinstance(departure,str) or type(nights) is not int or
        not 3<=nights<=180 or type(limit) is not int or
        not 1<=limit<=MAX_DETAIL_LISTS):
        raise bg.SyncHold("SOURCE_LIST_SELECTION_INVALID")
    candidates=[]
    for position,item in enumerate(entries):
        if not isinstance(item,dict) or item.get("stop") is not None:
            continue
        date_value=bg.date_iso(item.get("date"))
        if date_value is None or date_value.isoformat()!=departure:
            continue
        advertised=preview.advertised_nights(item)
        if advertised and nights not in advertised:
            continue
        # Prefer lists which explicitly advertise the selected number of
        # nights. Stable ordering among equally qualified source lists.
        candidates.append((0 if nights in advertised else 1,position,item))
    return [item for _,_,item in sorted(candidates)[:limit]]


def inspect_selected(directory, public_feed, chosen_id, api, *, selected_rooms=None):
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
    if selected_rooms is not None:
        try:
            candidate_report(selected, selected_rooms, [])
        except ValueError as exc:
            raise bg.SyncHold("INVALID_SELECTED_ROOM_GROUPS") from None
    if selected.get("bookable") is not False or selected.get("quote_verified") is not False:
        raise bg.SyncHold("PREVIEW_CLAIMS_BOOKABILITY")
    if selected.get("origin") != preview.ALLOWED_ORIGIN:
        raise bg.SyncHold("ORIGIN_UNSUPPORTED")
    if selected.get("depart_date", "") < datetime.now(timezone.utc).date().isoformat():
        raise bg.SyncHold("PREVIEW_EXPIRED")
    country = next((c for c in directory.get("countries", []) if
                    isinstance(c,dict) and
                    c.get("name")==selected.get("country") and
                    c.get("has_tour_catalog") is True and
                    isinstance(c.get("id"),str)),None)
    if not country:
        raise bg.SyncHold("COUNTRY_UNSUPPORTED")
    # The directory's optional origins[] annotation is not authoritative.
    # Subsequent authenticated /yandex FILES query ALWAYS pins bg.CITY_ID
    # and only the selected country/hotel/room/date may match. No source
    # preview -> no claimed option; no supplier quote -> no booking.
    hotels = {str(h.get("id")): h for h in directory.get("hotels", [])
              if isinstance(h,dict) and h.get("id") and h.get("country")}
    q=urllib.parse.urlencode({"action":"files", "flt":country["id"],
                               "flt2":bg.CITY_ID,"xml":"11"})
    file_feed=json.loads(api.get("https://export.bgoperator.ru/yandex?"+q))
    entries=file_feed.get("entries")
    if not isinstance(entries,list):
        raise bg.SyncHold("FILES_SCHEMA_UNKNOWN")
    # Bounded exact-date/duration lookup across independent price lists,
    # including lists which rotate into the public preview exporter.
    matching_listings=matching_source_listings(
        entries,selected["depart_date"],selected["nights"])
    summary={"matched_rows":0,"price_options":0,"rub_price_fields":0,
             "two_adults_age_markers":0,"blocked_price_options":0,
             "two_adults_with_rub":0,
             "two_adults_amount_only":0,"age_value_present":0,
             "age_marker_unrecognized":0}
    detail_lists=0
    party_rows=[]  # private only; never log raw rows or operator IDs
    for item in matching_listings:
        url=detail.safe_url(item,country["id"])
        data=json.loads(api.get(url))
        rows=data.get("entries") if isinstance(data,dict) else None
        if not isinstance(rows,list) or len(rows)>preview.MAX_RESPONSE_ROWS:
            continue
        detail_lists+=1
        if selected_rooms is not None:
            # Crosswalk must compare alternative rooms in the SAME hotel,
            # date and duration. Unrelated hotel rows can number in tens
            # of thousands; never let those exhaust the private 10k cap.
            relevant=[row for row in rows if isinstance(row,dict) and
                str(row.get("id_hotel",""))==str(selected["hotel_id"]) and
                preview.normalize_date(row.get("tour_date") or row.get("dt"))
                    ==selected["depart_date"] and
                preview.nights_value(row.get("duration"))==selected["nights"]]
            if len(party_rows)+len(relevant)>10000:
                raise bg.SyncHold("TOO_MANY_PRIVATE_AGE_CANDIDATES")
            # Bind each row to its OWN authenticated price-list prx.
            # Never print/export prx or infer it from a neighboring response.
            private_prx=data.get("prx") if isinstance(data,dict) else None
            safe_prx=(str(private_prx) if
                type(private_prx) in (str,int) and
                re.fullmatch(r"[0-9]{7,20}",str(private_prx))
                else None)
            party_rows.extend({**row,"_jamaica_private_prx":safe_prx}
                              for row in relevant)
        result=inspect_match(rows, selected, hotels)
        for key, value in result.items():
            summary[key]+=value
        # For the basic two-adult read-only audit a genuinely matching,
        # RUB-valued age option is sufficient. Multiroom checking scans all
        # selected bound source lists to preserve same-prx group candidates.
        if selected_rooms is None and summary["two_adults_with_rub"]>0:
            break
    party_status={}
    if selected_rooms is not None:
        checked=candidate_report(selected, selected_rooms, party_rows)
        # PRIVATE full ID/roommeal/sr matching is performed in-memory only.
        # Report candidate count, never internal plan records or price.
        plans=private_source_candidates(selected, selected_rooms, party_rows)
        party_status={
            "group_status":checked["status"],
            "group_count":checked["requested_rooms"],
            "group_age_candidate_counts":checked["candidate_counts"],
            "group_source_metadata_counts":checked["source_metadata_counts"],
            "shared_source_candidate_count":checked["shared_source_candidate_count"],
            "source_status":checked["source_status"],
            "private_source_plan_count":len(plans),
        }
    return {"preview_id":chosen_id,"country":selected["country"],
            "depart_date":selected["depart_date"],"detail_lists":detail_lists,
            **summary,**party_status,"quote_verified":False,"availability_verified":False,
            "flight_verified":False,"bookable":False,
            "status":("NO_CURRENT_MATCH" if not summary["matched_rows"] else
                      "POTENTIAL_2_ADULT_RUB_PRICE_OPTION" if summary["two_adults_with_rub"] else
                      "POTENTIAL_2_ADULT_AMOUNT_CURRENCY_UNVERIFIED" if summary["two_adults_amount_only"] else
                      "PRICE_REFERENCE_NOT_SUITABLE_FOR_2_ADULT_RUB_CHECK")}

def read_local_room_groups(path: str):
    """Read tiny age-only search groups from user-owned, mode-0600 file.

    Do not accept group data from a public URL, CLI argument string, or a
    shared group-writable path; the data is not echoed/logged.
    """
    if not isinstance(path,str) or not path or len(path)>1024:
        raise bg.SyncHold("PRIVATE_GROUP_FILE_INVALID")
    flags=os.O_RDONLY
    if hasattr(os,"O_NOFOLLOW"):
        flags|=os.O_NOFOLLOW
    if hasattr(os,"O_CLOEXEC"):
        flags|=os.O_CLOEXEC
    try:
        fd=os.open(path,flags)
        try:
            info=os.fstat(fd)
            if (not stat.S_ISREG(info.st_mode) or
                info.st_uid!=os.geteuid() or
                stat.S_IMODE(info.st_mode)&0o077 or
                info.st_size<2 or info.st_size>2048):
                raise bg.SyncHold("PRIVATE_GROUP_FILE_PERMISSIONS")
            raw=os.read(fd,2049)
        finally:
            os.close(fd)
    except OSError:
        raise bg.SyncHold("PRIVATE_GROUP_FILE_UNAVAILABLE") from None
    if len(raw)>2048:
        raise bg.SyncHold("PRIVATE_GROUP_FILE_TOO_LARGE")
    try:
        rooms=json.loads(raw)
    except (ValueError,UnicodeError):
        raise bg.SyncHold("PRIVATE_GROUP_FILE_JSON_INVALID") from None
    if (not isinstance(rooms,list) or not 1<=len(rooms)<=5 or
        any(not isinstance(room,dict) or
            set(room.keys())!={"adults","child_ages"} for room in rooms)):
        raise bg.SyncHold("PRIVATE_GROUP_FILE_SCHEMA_INVALID")
    # Validator is reused by inspect_selected before any supplier requests.
    return rooms

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",required=True)
    parser.add_argument("--previews",required=True)
    parser.add_argument("--preview-id",required=True)
    parser.add_argument("--credentials",default="")
    parser.add_argument("--private-rooms-file",default="")
    args=parser.parse_args()
    if not ID_RE.fullmatch(args.preview_id):
        raise bg.SyncHold("PREVIEW_ID_INVALID")
    directory=json.loads(Path(args.directory).read_text(encoding="utf-8"))
    feed=json.loads(Path(args.previews).read_text(encoding="utf-8"))
    rooms=read_local_room_groups(args.private_rooms_file) if args.private_rooms_file else None
    login,password=bg.read_secret(bg.credentials_path(args.credentials))
    bg.BASE="https://export.bgoperator.ru/"
    result=inspect_selected(directory,feed,args.preview_id,bg.ApiClient(login,password),
                            selected_rooms=rooms)
    print("JAMAICA_SELECTED_PRICE_REFERENCE_V1")
    for key in ("preview_id","country","depart_date","detail_lists",
                "matched_rows","price_options","rub_price_fields",
                "two_adults_age_markers","two_adults_with_rub",
                "two_adults_amount_only","age_value_present","age_marker_unrecognized",
                "blocked_price_options","status"):
        print(key.upper()+"="+str(result[key]))
    if rooms is not None:
        print("AGE_GROUP_COUNT="+str(result["group_count"]))
        print("AGE_GROUP_CANDIDATE_COUNTS="+",".join(
            map(str,result["group_age_candidate_counts"])))
        print("AGE_GROUP_SOURCE_METADATA_COUNTS="+",".join(
            map(str,result["group_source_metadata_counts"])))
        print("AGE_GROUP_STATUS="+result["group_status"])
        print("AGE_SHARED_SOURCE_CANDIDATES="+str(result["shared_source_candidate_count"]))
        print("AGE_SOURCE_STATUS="+result["source_status"])
        print("AGE_PRIVATE_SOURCE_PLANS="+str(result["private_source_plan_count"]))
        print("AGE_GROUP_QUOTE_VERIFIED=NO")
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
