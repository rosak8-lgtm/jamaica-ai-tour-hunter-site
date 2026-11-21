#!/usr/bin/env python3
"""One-request, read-only Hotelbeds/HBX Evaluation Content API diagnosis.

Designed for a newly registered "HOTELBEDS SPAIN - PRUEBAS" TEST key.
- Exactly one GET to the vendor's documented TEST content endpoint.
- Credentials only from environment, never printed or saved.
- No write, image download, booking, checkout, Git push or public JSON.
- Does NOT grant rights to display vendor photos commercially.
"""
from __future__ import annotations
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from collections import Counter

TEST_URL = ("https://api.test.hotelbeds.com/hotel-content-api/1.0/hotels"
            "?fields=all&language=ENG&from=1&to=10")
MAX_BYTES = 2_500_000
MAX_ROWS = 10

class ProbeHold(ValueError):
    pass

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,req,fp,code,msg,headers,newurl):
        raise ProbeHold("UNEXPECTED_EXTERNAL_REDIRECT")

def signed_request(key,secret,*,now=None):
    if (not isinstance(key,str) or not isinstance(secret,str)
            or not 8<=len(key)<=512 or not 8<=len(secret)<=512):
        raise ProbeHold("TEST_CREDENTIALS_MISSING")
    stamp=str(int(time.time() if now is None else now))
    signature=hashlib.sha256((key+secret+stamp).encode("utf-8")).hexdigest()
    return urllib.request.Request(TEST_URL,headers={
        "Api-key":key,"X-Signature":signature,
        "Accept":"application/json",
        "User-Agent":"Jamaica-HBX-Evaluation-Probe/1.0"})

def parse_summary(raw):
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>MAX_BYTES:
        raise ProbeHold("TEST_RESPONSE_OVERSIZE")
    try:
        payload=json.loads(raw)
        data=payload.get("hotels")
        rows=data.get("hotels") if isinstance(data,dict) else data
    except (ValueError,UnicodeError,AttributeError,TypeError) as exc:
        raise ProbeHold("TEST_RESPONSE_INVALID_JSON") from exc
    if not isinstance(rows,list) or len(rows)>MAX_ROWS:
        raise ProbeHold("TEST_RESPONSE_SCHEMA_INVALID")
    photos=0
    property_count=0
    hotels_with_photos=0
    main_pictures=0
    distinct=set()
    type_codes=Counter()
    by_country=Counter()
    for hotel in rows:
        if not isinstance(hotel,dict):
            continue
        property_count+=1
        code=hotel.get("countryCode")
        if isinstance(code,str) and len(code)==2 and code.isalpha():
            by_country[code.upper()]+=1
        images=hotel.get("images")
        if isinstance(images,list) and images:
            hotels_with_photos+=1
            for image in images[:1200]:
                if not isinstance(image,dict):continue
                path=image.get("path")
                if not isinstance(path,str):continue
                photos+=1
                if len(path)<=250:distinct.add(path)
                order=image.get("visualOrder")
                if order==0 or order=="0":main_pictures+=1
                type_code=image.get("imageTypeCode")
                if not isinstance(type_code,str):
                    nested=image.get("type")
                    type_code=nested.get("code") if isinstance(nested,dict) else None
                if (isinstance(type_code,str) and type_code.isascii() and
                    type_code.isalnum() and 2<=len(type_code)<=5):
                    type_codes[type_code]+=1
    common_types=dict(type_codes.most_common(8))
    return {"hotels":property_count,"photo_paths":photos,
            "hotels_with_photos":hotels_with_photos,
            "distinct_paths":len(distinct),
            "main_photo_candidates":main_pictures,
            "image_type_counts":common_types,
            "country_counts":dict(by_country.most_common(12))}

def check(*,key,secret,opener=None,now=None):
    request=signed_request(key,secret,now=now)
    opener=opener or urllib.request.build_opener(NoRedirect())
    try:
        with opener.open(request,timeout=20) as response:
            if response.status!=200:
                raise ProbeHold("TEST_CONTENT_HTTP_"+str(response.status))
            raw=response.read(MAX_BYTES+1)
    except urllib.error.HTTPError as exc:
        # 403 can mean key, scope or Evaluation daily quota; do not
        # disclose request/response headers, response body or auth values.
        raise ProbeHold("TEST_CONTENT_HTTP_"+str(exc.code)) from None
    except urllib.error.URLError:
        raise ProbeHold("TEST_CONTENT_NETWORK_UNAVAILABLE") from None
    return parse_summary(raw)

def main():
    key=os.environ.get("HBX_TEST_API_KEY","")
    secret=os.environ.get("HBX_TEST_API_SECRET","")
    if not key or not secret:
        print("JAMAICA_HBX_TEST_HOLD=TEST_CREDENTIALS_NOT_SET")
        return 2
    try:
        result=check(key=key,secret=secret)
    except ProbeHold as exc:
        print("JAMAICA_HBX_TEST_HOLD="+str(exc))
        return 2
    print("JAMAICA_HBX_TEST_CONTENT_API=PASS")
    print("JAMAICA_HBX_TEST_SAMPLE_HOTELS="+str(result["hotels"]))
    print("JAMAICA_HBX_TEST_SAMPLE_PHOTO_PATHS="+str(result["photo_paths"]))
    print("JAMAICA_HBX_TEST_HOTELS_WITH_PHOTOS="+str(result["hotels_with_photos"]))
    print("JAMAICA_HBX_TEST_DISTINCT_IMAGE_PATHS="+str(result["distinct_paths"]))
    print("JAMAICA_HBX_TEST_MAIN_IMAGES_VISUAL_ORDER_ZERO="+str(result["main_photo_candidates"]))
    print("JAMAICA_HBX_TEST_IMAGE_TYPE_COUNTS="+
          ",".join(str(key)+":"+str(value) for key,value in result["image_type_counts"].items()))
    print("JAMAICA_HBX_TEST_COUNTRIES="+
          ",".join(key+":"+str(value) for key,value in result["country_counts"].items()))
    print("JAMAICA_HBX_TEST_REQUESTS_USED=1")
    print("JAMAICA_HBX_IMAGE_BYTES_DOWNLOADED=0")
    print("JAMAICA_HBX_COMMERCIAL_PUBLICATION=DISABLED")
    print("JAMAICA_HBX_BOOKINGS=DISABLED")
    return 0

if __name__=="__main__":
    try:
        sys.exit(main())
    except (ProbeHold,OSError,ValueError,TypeError):
        print("JAMAICA_HBX_TEST_HOLD=PROBE_UNEXPECTED_FAILURE")
        sys.exit(2)
