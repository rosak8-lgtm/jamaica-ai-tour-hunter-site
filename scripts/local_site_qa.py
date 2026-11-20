#!/usr/bin/env python3
"""Dependency-free JAMAICA deployment preflight; never changes live booking."""
import json
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
    config=load("checkout-config.json")
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
    for name in ("routeCards","offerCards","destinationGrid"):
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
