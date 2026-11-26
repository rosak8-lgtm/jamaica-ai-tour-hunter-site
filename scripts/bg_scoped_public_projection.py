"""V90: pure, scope-bound projection of trusted multi-city BG staging.

Not an active publisher. No supplier requests, file writes or live activation.
Caller must read owner-only ledgers and the current official registry.
"""
from datetime import datetime,timedelta,timezone
from scripts.bg_scoped_evidence import (
    SCHEMA, MAX_RECORDS, build_record, validated_registry_scope,
)
from scripts.catalog_property_identity import build_hotel_index, public_operator_name

def project(staged,registry,directory,*,now):
    """Return paired public rows/proofs, never internal source IDs or sessions."""
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise ValueError("CLOCK_REQUIRED")
    now=now.astimezone(timezone.utc)
    if (not isinstance(staged,dict) or set(staged)!={"schema","classification","origin_id","country_id","records"}
        or staged["schema"]!=SCHEMA or staged["classification"]!="PRIVATE_ONLY_NOT_PUBLIC_OFFERS"
        or not isinstance(staged["records"],list) or len(staged["records"])>MAX_RECORDS):
        raise ValueError("SCOPED_LEDGER_INVALID")
    scope=validated_registry_scope(registry,staged["origin_id"],staged["country_id"],now)
    hotels=build_hotel_index(directory)
    hotel_rows={str(h["id"]):h for h in directory["hotels"]}
    rows=[]; proofs=[]; seen=set()
    for raw in staged["records"]:
        if not isinstance(raw,dict) or set(raw)!={"preview","route","flight","price"}:
            raise ValueError("SCOPED_RECORD_INVALID")
        record=build_record(scope,raw["route"],raw["flight"],raw["preview"],raw["price"],now=now)
        if record is None:
            continue
        p=record["preview"]; price=record["price"]; uid=p["id"]
        if uid in seen:
            raise ValueError("SCOPED_DUPLICATE_ID")
        seen.add(uid)
        try:
            day=datetime.strptime(p["depart_date"],"%Y-%m-%d").date()
        except (ValueError,TypeError):
            continue
        if not now.date()<=day<=now.date()+timedelta(days=730):
            continue
        hid=p["hotel_id"]
        if not isinstance(hid,str) or hid not in hotels or hotels[hid][1]!=scope.country:
            continue
        if any(ord(c)<32 or c in "<>{}" for c in p["room"]):
            continue
        rows.append({
            "id":uid,"hotel_id":hid,"hotel":hotels[hid][0],
            "country":scope.country,"origin":scope.origin,
            "resort":public_operator_name(hotel_rows[hid].get("resort"))[:100],
            "room":p["room"],"depart_date":p["depart_date"],"nights":p["nights"],
            "status":"REFERENCE_PRICE_LIST_ONLY",
            "price_reference_rub":price["price_total_rub"],
            "price_reference_party":"TWO_ADULTS",
            "price_source":"BG_EXACT_SELECTED_GREEN_BROWSER",
            "price_observed_at_utc":price["observed_at_utc"],
            "bookable":False,"quote_verified":False,"availability_verified":False,"flight_verified":False,
        })
        proofs.append({"preview_id":uid,"observed_at_utc":price["observed_at_utc"],
            "route_best_price_seen":True,"both_green_planes_seen":True})
    return rows,proofs
