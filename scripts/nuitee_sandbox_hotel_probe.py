#!/usr/bin/env python3
"""Read-only, single-request Nuitee/LiteAPI sandbox hotel media discovery.

This is NOT an image license or a production data import. API key is read
only from private process environment and is never printed. The script does
not download image binaries, identify BG operator hotels, or book rooms.
"""
from __future__ import annotations
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

BASE="https://api.liteapi.travel/v3.0/data/hotels"
MAX_BYTES=2_000_000
MAX_ITEMS=10
COUNTRIES={"TH":"Pattaya","CN":"Sanya","VN":"Nha Trang"}
IMG_FIELDS=("main_photo","thumbnail","mainPhoto")
SAFE_CITY=re.compile(r"^[A-Za-z][A-Za-z ]{1,35}$")

class ProbeHold(ValueError):pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ProbeHold("UNEXPECTED_REDIRECT")

def request_for(key,*,country="TH",city=None):
    if not isinstance(key,str) or not 8<=len(key)<=512:
        raise ProbeHold("SANDBOX_API_KEY_MISSING")
    if country not in COUNTRIES:
        raise ProbeHold("COUNTRY_NOT_ALLOWED")
    city=city or COUNTRIES[country]
    if not SAFE_CITY.fullmatch(city):
        raise ProbeHold("INVALID_CITY")
    query=urllib.parse.urlencode({"countryCode":country,"cityName":city,
                                    "limit":MAX_ITEMS,"offset":0})
    url=BASE+"?"+query
    return urllib.request.Request(url,headers={
      "X-API-Key":key,"Accept":"application/json",
      "User-Agent":"JamaicaNuiteeSandboxPhotoProbe/1.0"})

def rows_from(data):
    if not isinstance(data,dict):raise ProbeHold("UNEXPECTED_RESPONSE_SCHEMA")
    rows=data.get("data")
    if isinstance(rows,dict):
        rows=rows.get("hotels") or rows.get("items") or rows.get("data")
    if not isinstance(rows,list) or len(rows)>MAX_ITEMS:
        raise ProbeHold("HOTEL_LIST_RESPONSE_UNEXPECTED")
    return rows

def parse_summary(raw):
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>MAX_BYTES:
        raise ProbeHold("RESPONSE_TOO_LARGE")
    try:
        rows=rows_from(json.loads(raw))
    except (ValueError,UnicodeError,TypeError,AttributeError) as exc:
        raise ProbeHold("INVALID_OR_UNRECOGNIZED_RESPONSE") from exc
    hotels=0;main=0;images=0;unique=set();countries=set()
    for h in rows:
        if not isinstance(h,dict):continue
        hotels+=1
        country=h.get("country")
        if isinstance(country,str) and re.fullmatch(r"[A-Za-z]{2}",country):
            countries.add(country.upper())
        for fld in IMG_FIELDS:
            val=h.get(fld)
            if isinstance(val,str) and val.startswith("https://"):
                main+=1;unique.add(val[:500]);break
        for img in h.get("hotelImages",[]) if isinstance(h.get("hotelImages"),list) else []:
            if not isinstance(img,dict):continue
            link=img.get("url") or img.get("urlHd")
            if isinstance(link,str) and link.startswith("https://"):
                images+=1;unique.add(link[:500])
    return {"sample_hotels":hotels,"main_photos":main,
            "image_entries":images,"unique_image_urls":len(unique),
            "countries":sorted(countries)}

def check(key,*,country="TH",city=None,opener=None):
    req=request_for(key,country=country,city=city)
    opener=opener or urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(req,timeout=20) as response:
            if response.status!=200:raise ProbeHold("HTTP_"+str(response.status))
            raw=response.read(MAX_BYTES+1)
    except urllib.error.HTTPError as exc:
        raise ProbeHold("HTTP_"+str(exc.code)) from None
    except urllib.error.URLError:
        raise ProbeHold("NETWORK_UNAVAILABLE") from None
    return parse_summary(raw)

def main():
    if os.environ.get("NUITEE_MODE")!="SANDBOX":
        print("JAMAICA_NUITEE_HOLD=SANDBOX_MODE_REQUIRED")
        return 2
    key=os.environ.get("NUITEE_SANDBOX_API_KEY","")
    country=os.environ.get("NUITEE_TEST_COUNTRY","TH").upper()
    try:
        stats=check(key,country=country)
    except ProbeHold as exc:
        print("JAMAICA_NUITEE_HOLD="+str(exc))
        return 2
    print("JAMAICA_NUITEE_SANDBOX_HOTEL_CONTENT=PASS")
    print("JAMAICA_NUITEE_SAMPLE_HOTELS="+str(stats["sample_hotels"]))
    print("JAMAICA_NUITEE_MAIN_PHOTOS="+str(stats["main_photos"]))
    print("JAMAICA_NUITEE_GALLERY_IMAGE_ENTRIES="+str(stats["image_entries"]))
    print("JAMAICA_NUITEE_DISTINCT_IMAGE_URLS="+str(stats["unique_image_urls"]))
    print("JAMAICA_NUITEE_COUNTRIES="+",".join(stats["countries"]))
    print("JAMAICA_NUITEE_API_CALLS=1")
    print("JAMAICA_NUITEE_IMAGE_BINARY_DOWNLOADS=0")
    print("JAMAICA_NUITEE_COMMERCIAL_PUBLICATION=DISABLED")
    print("JAMAICA_NUITEE_BOOKING_AND_PAYMENT=DISABLED")
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except (OSError,ValueError,TypeError,KeyError):
        print("JAMAICA_NUITEE_HOLD=UNEXPECTED_FAILURE",file=sys.stderr)
        sys.exit(2)
