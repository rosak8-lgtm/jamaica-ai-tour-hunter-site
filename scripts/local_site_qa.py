#!/usr/bin/env python3
"""Dependency-free JAMAICA deployment preflight; never changes live booking."""
import json
import hashlib
import re
import sys
from pathlib import Path
from datetime import date

ROOT=Path(__file__).resolve().parent.parent
def require(cond, message):
    if not cond: raise SystemExit("JAMAICA_QA_FAIL: "+message)

def load(name):
    return json.loads((ROOT/name).read_text(encoding="utf-8"))

def main():
    page=(ROOT/"index.html").read_text(encoding="utf-8")
    route_page=(ROOT/"route.html").read_text(encoding="utf-8")
    directory=load("destination-directory.json")
    offers=load("verified-offers.json")
    routes=load("route-discovery.json")
    previews=load("tour-previews.json")
    # Oracle now publishes a fast 8k index plus verified 4k-row JSON parts.
    # Validate *all* parts before comparing official price/booking counts.
    shards=previews.get("shards",[])
    require(isinstance(shards,list) and len(shards)<=13,"unsafe shard manifest")
    for i,meta in enumerate(shards,1):
        name="tour-previews-shards/part-"+format(i,"03d")+".json"
        require(isinstance(meta,dict) and meta.get("path")==name and
                type(meta.get("count")) is int and 0<meta["count"]<=4000 and
                isinstance(meta.get("sha256"),str) and
                re.fullmatch(r"[a-f0-9]{64}",meta["sha256"]),
                "invalid catalog shard metadata")
        path=ROOT/name
        require(path.is_file() and not path.is_symlink() and
                path.stat().st_size<=4_000_000,"invalid catalog shard file")
        payload=json.loads(path.read_text(encoding="utf-8"))
        rows=payload.get("previews")
        require(payload.get("schema")=="jamaica.tour-preview-shard.v1" and
                payload.get("bookable") is False and
                payload.get("quote_verified") is False and
                payload.get("availability_verified") is False and
                payload.get("refreshed_at_utc")==previews.get("refreshed_at_utc") and
                isinstance(rows,list) and len(rows)==meta["count"],
                "stale or invalid shard contents")
        digest=hashlib.sha256(json.dumps(rows,ensure_ascii=False,
            sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
        require(digest==meta["sha256"],"shard digest mismatch")
        previews["previews"].extend(rows)
    require(len(previews.get("previews",[]))<=60_000,"publication limit exceeded")
    if "total_published_previews" in previews:
        require(previews["total_published_previews"]==len(previews["previews"]),
                "catalog total does not match published shards")
    config=load("checkout-config.json")
    import catalog_property_identity as property_identity
    if previews["previews"]:
        try:
            property_identity.verify_catalog_hotel_identity(previews["previews"],directory)
        except property_identity.IdentityMismatch as exc:
            raise SystemExit("JAMAICA_HOTEL_IDENTITY_HOLD="+str(exc)) from exc
    else:
        require(previews.get("publication_rule")==
                "BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1",
                "EMPTY_PUBLIC_CATALOG_REQUIRES_STRICT_VISUAL_GATE")
    if previews.get("publication_rule")=="BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1":
        import public_tour_eligibility as public_gate
        from datetime import datetime
        try:
            snapshot_at=datetime.fromisoformat(
                previews["refreshed_at_utc"].replace("Z","+00:00"))
            expected=public_gate.select_public_source_rows(
                previews,load("tour-visual-evidence.json"),now=snapshot_at)
        except (ValueError,TypeError,KeyError) as exc:
            raise SystemExit("JAMAICA_VISUAL_PROOF_HOLD=INVALID_PUBLIC_GATE") from exc
        require([r["id"] for r in expected["previews"]]==
                [r["id"] for r in previews["previews"]],
                "PUBLIC_TOUR_WITHOUT_SOURCE_BESTPRICE_AND_TWO_GREEN_FLIGHTS")
    require(directory.get("schema")=="jamaica.destination-directory.v1","directory schema")
    require(directory.get("total_countries")==251,"countries missing")
    require(isinstance(directory.get("hotels"),list),"hotel directory missing")
    require(offers.get("schema")=="jamaica.verified-offers.v1","offer feed schema")
    require(isinstance(offers.get("offers"),list),"offer list missing")
    require(routes.get("schema")=="jamaica.route-discovery.v1","route feed schema")
    require(previews.get("schema")=="jamaica.tour-previews.v1","preview feed schema")
    require(previews.get("bookable") is False,"unverified previews marked bookable")
    require(previews.get("quote_verified") is False,"unverified preview quotes")
    require(previews.get("availability_verified") is False,"unverified preview availability")
    require(isinstance(previews.get("previews"),list),"preview list missing")
    require(all(p.get("bookable") is False and p.get("quote_verified") is False and
                p.get("availability_verified") is False and p.get("flight_verified") is False
                for p in previews["previews"]),"preview row claims booking or verification")
    for p in previews["previews"]:
        amount=p.get("price_reference_rub")
        if amount is not None:
            require(type(amount) is int and 0<amount<=100_000_000,
                    "invalid indicative two-adult amount")
            require(p.get("price_reference_party")=="TWO_ADULTS",
                    "indicative price has unverified party scope")
        elif "price_reference_party" in p:
            require(p["price_reference_party"]=="UNVERIFIED",
                    "unverified price reference scope incorrect")
    indicative_count=sum(p.get("price_reference_rub") is not None for p in previews["previews"])
    if "indicative_two_adult_rub_count" in previews:
        require(previews["indicative_two_adult_rub_count"]==indicative_count,
                "indicated price count mismatch")
    require(isinstance(routes.get("routes"),list),"route list missing")
    require(routes.get("bookable") is False,"unverified routes marked bookable")
    require(routes.get("quote_verified") is False,"unverified routes marked quoted")
    require(config.get("live_booking_enabled") is False or bool(config.get("api_base_url")),"live booking enabled without API")
    require(not config.get("payments_enabled") or bool(config.get("seller_legal_name") and config.get("terms_url") and config.get("privacy_url")),"payments enabled without legal disclosures")
    # The current selling/search UI is built around a direct result list,
    # fast source-backed country chips and an on-demand hotel directory.
    # routeCards/destinationGrid belonged to the removed 251-country card wall.
    # Validate the ACTUAL interactive elements rather than obsolete markup.
    for name in ("tourSearchForm","previewCards","catalogBreadth",
                 "filterCountry","quickCountries","hotelGuideCards","offerCards"):
        require('id="'+name+'"' in page,"missing "+name)
    for name in ("alternativeCountry","alternativeNights","alternativeDate","alternativeList"):
        require('id="'+name+'"' in route_page,"missing "+name)
    rows=routes["routes"]
    require(len(rows)>=1,"EMPTY_ROUTE_FEED: re-run authorized sync after git pull; do not deploy an empty feed")
    require(all(x.get("bookable") is False and x.get("quote_verified") is False for x in rows),"invalid route verification flag")
    countries=sorted({x["country"] for x in rows})
    require(len(countries)>=2,"cross-country route listing requires >=2 countries")
    print("JAMAICA_PYTHON_PREFLIGHT_PASS")
    print("COUNTRIES_DIRECTORY="+str(directory["total_countries"]))
    print("HOTELS_DIRECTORY="+str(len(directory["hotels"])))
    print("ROUTES="+str(len(rows)))
    print("TOUR_PREVIEWS="+str(len(previews["previews"])))
    print("INDICATIVE_TWO_ADULT_RUB_PRICES="+str(indicative_count))
    print("ROUTE_COUNTRIES="+str(len(countries)))
    print("CONFIRMED_OFFERS="+str(len(offers["offers"])))
    print("LIVE_BOOKING_ENABLED="+str(config.get("live_booking_enabled")).lower())
    print("PAYMENTS_ENABLED="+str(config.get("payments_enabled")).lower())
    print("NOTE=Python preflight is not a browser checkout test")
if __name__=="__main__":
    main()
