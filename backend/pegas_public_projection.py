"""V50: pure private-to-public PEGAS projection. No supplier I/O or writes.

The input is trusted normalized browser evidence, NOT listing HTML, a
public JSON file, a user request or a historical price. This module is
not activated by the existing BG publisher. The future PEGAS browser
adapter must explicitly satisfy this contract before enabling publication.
"""
from datetime import datetime,timezone
from hashlib import sha256
import json
import re
from backend.pegas_application_evidence import validate_application_evidence

SCHEMA="jamaica.pegas-reference-catalog.v1"
MAX_ROWS=5000
PARTY=[{"adults":2,"child_ages":[]}]
PARTY_DIGEST=sha256(json.dumps(PARTY,sort_keys=True,separators=(",",":")).encode()).hexdigest()
TEXT_KEYS=("origin","country","hotel","room","resort")

def clean_text(value):
    return (isinstance(value,str) and 1<=len(value)<=200 and value==value.strip()
            and not any(ord(c)<32 or c in "<>{}" for c in value))

def projection_id(e):
    fields=[e[k] for k in ("origin_id","country_id","hotel_id","room_id","departure_date","nights","party_digest","selected_offer_id")]
    return "pg_"+sha256(json.dumps(fields,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()[:24]

def project_one(search,application,*,now):
    if not validate_application_evidence(search,application,now=now):return None
    # An explicit party binding prevents publishing a family price as a
    # reference for two adults. Other parties require private calculation.
    if search.get("party_digest")!=PARTY_DIGEST:return None
    # The official adapter must read matching itinerary labels from both
    # the selected listing and the opened application.
    for key in TEXT_KEYS:
        if not clean_text(search.get(key)) or search[key]!=application.get(key):return None
    if search["country"]=="Вьетнам" and search["nights"] in (45,60):return None
    return {
        "id":projection_id(search),"status":"PEGAS_APPLICATION_PRICE_REFERENCE_ONLY",
        "origin":search["origin"],"country":search["country"],"hotel":search["hotel"],
        "room":search["room"],"resort":search["resort"],
        "depart_date":search["departure_date"],"nights":search["nights"],
        "price_reference_rub":application["total_rub"],"price_reference_party":"TWO_ADULTS",
        "price_source":"PEGAS_OPEN_APPLICATION_MANDATORY_FEES_INCLUDED",
        "price_observed_at_utc":application["observed_at_utc"],
        "evidence":{"hotel_filter_verified":True,"flight_filter_verified":True,
                    "cheapest_eligible_price_clicked":True,"final_price_observed":True,
                    "mandatory_fees_included":True,"observed_at_utc":application["observed_at_utc"]},
        "bookable":False,"quote_verified":False,"availability_verified":False,"flight_verified":False,
    }

def build_catalog(pairs,*,now):
    """Reject stale/mismatched evidence; never carry forward historic prices."""
    if not isinstance(now,datetime) or now.tzinfo is None:raise ValueError("CLOCK_REQUIRED")
    if not isinstance(pairs,(list,tuple)) or len(pairs)>MAX_ROWS:raise ValueError("BATCH_INVALID")
    records={};conflicted=set()
    for pair in pairs:
        if not isinstance(pair,(list,tuple)) or len(pair)!=2:continue
        row=project_one(*pair,now=now)
        if row is None:continue
        key=row["id"]
        if key in conflicted:continue
        if key in records and records[key]!=row:
            # Contradictory observations must be independently reconciled,
            # not silently select a cheaper price.
            records.pop(key);conflicted.add(key);continue
        records[key]=row
    return {"schema":SCHEMA,"refreshed_at_utc":now.astimezone(timezone.utc).isoformat(),
            "bookable":False,"quote_verified":False,
            "previews":sorted(records.values(),key=lambda x:(x["price_reference_rub"],x["depart_date"],x["id"]))}
