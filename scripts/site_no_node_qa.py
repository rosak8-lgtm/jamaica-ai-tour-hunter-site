#!/usr/bin/env python3
"""Strict dependency-free customer journey/data QA for Lenovo without Node.js.

This is NOT a JS parser and NOT a browser checkout test. CI runs the Node checks.
"""
from __future__ import annotations

import json
import hashlib
import re
from collections import Counter
from datetime import date, datetime, timezone
from html.parser import HTMLParser
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
REQUIRED_PAGES=("index.html","preview.html","route.html","hotel.html","tour.html",
                "quote.html","checkout.html","account.html")

class SiteStructure(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids=Counter()
        self.references=[]
    def handle_starttag(self,tag,attrs):
        props=dict(attrs)
        if "id" in props:self.ids[props["id"]]+=1
        if tag=="a" and "href" in props:self.references.append(props["href"])

def require(ok,why):
    if not ok:raise SystemExit("JAMAICA_NO_NODE_QA_HOLD="+why)

def read_page(name):
    path=ROOT/name
    require(path.is_file(),"PAGE_MISSING_"+name)
    source=path.read_text(encoding="utf-8")
    p=SiteStructure()
    p.feed(source)
    repeated=[name for name,n in p.ids.items() if n>1]
    require(not repeated,"DUPLICATE_IDS_"+name)
    require("<script" in source,"JS_TAG_MISSING_"+name)
    require(not re.search(r"(?:wa\.me|api\.whatsapp\.com|href=[\"']mailto:)",source,re.I),
            "MESSENGER_LINK_"+name)
    return source,p

def main():
    pages=dict((name,read_page(name)) for name in REQUIRED_PAGES)
    root=pages["index.html"][1]
    for key in ("tourSearchForm","departure","destination","dateFrom","nights",
                "adults","kids","budget","hotelSearch","offerCards",
                "previewCards","previewCountryChips","countryDatalist","routeCards","noOffers"):
        require(root.ids.get(key)==1,"MISSING_UI_ID_"+key)
    for key in ("heading","facts","bookingStatus","hotelLink","alternatives"):
        require(pages["preview.html"][1].ids.get(key)==1,"MISSING_PREVIEW_ID_"+key)
    require(pages["preview.html"][1].ids.get("quoteLink")==1,
            "NO_QUOTE_LINK_FROM_SELECTED_TOUR")
    require(pages["quote.html"][1].ids.get("checkQuote")==1,
            "NO_FIRST_QUOTE_UI")
    require(pages["account.html"][1].ids.get("verifySign")==1,
            "NO_SIGNED_CONTRACT_ACCOUNT")
    require("v1/contract-orders/draft" in pages["checkout.html"][0],
            "NO_CONTRACT_FIRST_DRAFT")
    require("v1/checkout/prepare" not in pages["checkout.html"][0],
            "UNSAFE_LEGACY_PAYMENT_PATH")
    main_src=pages["index.html"][0]
    require('window.jamaicaUpdatePreviews()' in main_src and
            'form.addEventListener("submit"' in main_src,
            "SEARCH_DOES_NOT_UPDATE_TOURS")
    require("preview.html?id=" in main_src and
            "preview.html?id=" in pages["route.html"][0],
            "SELECTED_TOUR_LINK_MISSING")
    require('if(!country&&!(sortMode==="price"&&partyTwoAdults))list=interleaveCountries(list)' in main_src,
            "MIXED_COUNTRY_RESULTS_MISSING")
    require("price_reference_party" in main_src and
            "Цена пока не подтверждена" in main_src,
            "UNVERIFIED_PRICE_LABEL_MISSING")
    def load(name):
        return json.loads((ROOT/name).read_text(encoding="utf-8"))
    preview=load("tour-previews.json")
    directory=load("destination-directory.json")
    routes=load("route-discovery.json")
    confirmed=load("verified-offers.json")
    checkout=load("checkout-config.json")
    require(preview.get("schema")=="jamaica.tour-previews.v1" and
            preview.get("bookable") is False and
            preview.get("quote_verified") is False and
            preview.get("availability_verified") is False,
            "PREVIEWS_WRONG_STATUS")
    records=preview.get("previews")
    require(isinstance(records,list) and 0<len(records)<=8000,"PREVIEWS_EMPTY")
    shards=preview.get("shards",[])
    require(isinstance(shards,list) and len(shards)<=13,"SHARD_MANIFEST_INVALID")
    count=len(records)
    for i,meta in enumerate(shards,1):
        path="tour-previews-shards/part-"+format(i,"03d")+".json"
        require(isinstance(meta,dict) and meta.get("path")==path and
                type(meta.get("count")) is int and 0<meta["count"]<=4000 and
                isinstance(meta.get("sha256"),str) and
                re.fullmatch(r"[a-f0-9]{64}",meta["sha256"]),
                "SHARD_METADATA_INVALID")
        file=ROOT/path
        require(file.is_file() and not file.is_symlink() and
                file.stat().st_size<4_000_000,"SHARD_FILE_INVALID")
        payload=json.loads(file.read_text(encoding="utf-8"))
        part=payload.get("previews")
        require(payload.get("schema")=="jamaica.tour-preview-shard.v1" and
                payload.get("refreshed_at_utc")==preview.get("refreshed_at_utc") and
                payload.get("bookable") is False and
                payload.get("quote_verified") is False and
                payload.get("availability_verified") is False and
                isinstance(part,list) and len(part)==meta["count"],
                "SHARD_CONTENT_INVALID")
        signature=hashlib.sha256(json.dumps(part,ensure_ascii=False,
            sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
        require(signature==meta["sha256"],"SHARD_CONTENT_HASH_MISMATCH")
        records.extend(part)
        count+=len(part)
    require(len(records)<=60000,"TOTAL_PREVIEW_CAP_EXCEEDED")
    if "total_published_previews" in preview:
        require(preview["total_published_previews"]==len(records),
                "PUBLIC_SHARD_COUNT_MISMATCH")
    require(directory.get("schema")=="jamaica.destination-directory.v1" and
            directory.get("total_countries")==251,"DIRECTORY_INVALID")
    require(routes.get("schema")=="jamaica.route-discovery.v1" and
            isinstance(routes.get("routes"),list),"ROUTES_INVALID")
    require(confirmed.get("schema")=="jamaica.verified-offers.v1" and
            isinstance(confirmed.get("offers"),list),"CONFIRMED_FEED_INVALID")
    require(checkout.get("schema")=="jamaica.checkout-config.v1","CHECKOUT_CONFIG_INVALID")
    if checkout.get("live_booking_enabled") is False:
        require(checkout.get("contract_first_enabled") is False and
                checkout.get("trusted_signature_enabled") is False and
                checkout.get("auth_api_enabled") is False,
                "CONTRACT_FIRST_FEATURE_FLAGS_UNSAFE")
    if checkout.get("live_booking_enabled") is True or checkout.get("payments_enabled") is True:
        require(bool(checkout.get("api_base_url") and checkout.get("seller_legal_name")
                     and checkout.get("terms_url") and checkout.get("privacy_url")),
                "UNSAFE_LIVE_CHECKOUT_CONFIG")
    hotel_ids={str(x.get("id")) for x in directory.get("hotels",[]) if isinstance(x,dict)}
    ids=set()
    by_country=Counter()
    future_by_country=Counter()
    reference_prices=0
    today=datetime.now(timezone.utc).date()
    for r in records:
        require(isinstance(r,dict),"MALFORMED_PREVIEW")
        uid=r.get("id","")
        require(isinstance(uid,str) and re.fullmatch(r"p_[a-f0-9]{24}",uid) and uid not in ids,
                "BAD_OR_DUPLICATE_PREVIEW_ID")
        ids.add(uid)
        require(str(r.get("hotel_id")) in hotel_ids,"PREVIEW_HOTEL_NOT_IN_DIRECTORY")
        require(all(r.get(flag) is False for flag in
                    ("bookable","quote_verified","availability_verified","flight_verified")),
                "PREVIEW_FALSE_BOOKING_CLAIM")
        by_country[r.get("country")]+=1
        try:
            d=date.fromisoformat(r["depart_date"])
        except (KeyError,TypeError,ValueError):
            raise SystemExit("JAMAICA_NO_NODE_QA_HOLD=INVALID_DATE")
        if d>today:future_by_country[r["country"]]+=1
        amount=r.get("price_reference_rub")
        if amount is not None:
            require(type(amount) is int and 0<amount<=100_000_000 and
                    r.get("price_reference_party")=="TWO_ADULTS",
                    "INVALID_PRICE_SCOPE")
            reference_prices+=1
    require(len(by_country)>=3,"TOO_FEW_COUNTRIES_IN_PREVIEWS")
    require(future_by_country,"NO_FUTURE_DEPARTURES_REFRESH_REQUIRED")
    expected=preview.get("indicative_two_adult_rub_count")
    if expected is not None:
        require(expected==reference_prices,"REFERENCE_PRICE_COUNT_MISMATCH")
    print("JAMAICA_NO_NODE_PREFLIGHT_PASS")
    print("COUNTRY_DIRECTORY="+str(directory["total_countries"]))
    print("TOUR_PREVIEWS="+str(len(records)))
    print("COUNTRIES_WITH_PREVIEWS="+str(len(by_country)))
    print("FUTURE_COUNTRIES="+",".join(sorted(future_by_country)))
    print("ROUTES="+str(len(routes["routes"])))
    print("INDICATIVE_2_ADULT_PRICES="+str(reference_prices))
    print("CONFIRMED_BOOKABLE_OFFERS="+str(len(confirmed["offers"])))
    print("LIVE_BOOKING_ENABLED="+str(checkout.get("live_booking_enabled")).lower())
    print("PAYMENTS_ENABLED="+str(checkout.get("payments_enabled")).lower())
    print("WARNING=NOT_A_JS_SYNTAX_OR_BROWSER_CHECK_USE_GITHUB_ACTIONS_OR_NODE")

if __name__=="__main__":
    main()
