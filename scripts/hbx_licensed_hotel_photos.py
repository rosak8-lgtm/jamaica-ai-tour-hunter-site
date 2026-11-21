#!/usr/bin/env python3
"""JAMAICA: licensed HBX Content API -> exact hotel-ID, external-URL-only media feed.

NO supplier credentials or hotel photos are copied into the public repository.
Fail closed unless a separate written commercial publication grant and an
evidence-backed BG/JAMAICA -> HBX property crosswalk are supplied.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.request
from datetime import date

API = "https://api.hotelbeds.com/hotel-content-api/1.0/hotels"
IMG = "https://photos.hotelbeds.com/giata/"
MAX_RESPONSE = 25_000_000
MAX_HOTELS = 50000
MAX_PAGES = 300
SHARD_SIZE = 250
MAX_PHOTOS = 12
ID = re.compile(r"^[0-9]{7,20}$")
PATH = re.compile(r"^[a-zA-Z0-9_-]+(?:/[a-zA-Z0-9_.-]+)*\.(?:jpe?g|png|webp)$", re.I)
COUNTRY_CODE = re.compile(r"^[A-Z]{2}$")
SAFE_TEXT = re.compile(r"^[^\x00-\x1f<>]{3,250}$")

class MediaHold(ValueError):
    pass

def assert_true(test, error):
    if not test:
        raise MediaHold(error)

def exact_name(name):
    if isinstance(name,dict):
        name = name.get("content")
    if not isinstance(name,str):
        return ""
    return " ".join(name.casefold().split())

def load_json(path, limit=12_000_000):
    file=Path(path)
    assert_true(file.is_file() and not file.is_symlink() and file.stat().st_size<=limit,
                "INPUT_FILE_MISSING_UNSAFE_OR_TOO_BIG")
    return json.loads(file.read_text(encoding="utf-8"))

def license_gate(grant, today=None):
    today=today or date.today()
    assert_true(isinstance(grant,dict),"HBX_LICENSE_SCHEMA_INVALID")
    assert_true(grant.get("schema")=="jamaica.hbx-license-grant.v1" and
       grant.get("provider")=="HBX Group" and
       grant.get("commercial_publication_allowed") is True and
       grant.get("direct_external_image_display_allowed") is True and
       grant.get("publication_site")=="https://rosak8-lgtm.github.io/jamaica-ai-tour-hunter-site/" and
       isinstance(grant.get("public_permission_reference"),str) and
       len(grant["public_permission_reference"].strip())>=12 and
       isinstance(grant.get("attribution_text"),str) and
       3<=len(grant["attribution_text"])<=120 and
       grant.get("license_verified_at"),"HBX_WRITTEN_IMAGE_RIGHTS_NOT_VERIFIED")
    try:
        verified=date.fromisoformat(grant["license_verified_at"])
        expires=date.fromisoformat(grant["rights_expires_at"])
    except (ValueError,TypeError,KeyError) as exc:
        raise MediaHold("HBX_LICENSE_DATE_INVALID") from exc
    assert_true(verified<=today<=expires,"HBX_LICENSE_EXPIRED_OR_NOT_YET_VERIFIED")
    return grant

def verified_map(mapping, directory):
    assert_true(isinstance(mapping,dict),"HOTEL_CROSSWALK_SCHEMA_INVALID")
    assert_true(mapping.get("schema")=="jamaica.hbx-crosswalk.v1" and
       isinstance(mapping.get("mappings"),list),"HOTEL_CROSSWALK_SCHEMA_INVALID")
    known={str(h["id"]):h for h in directory.get("hotels",[])
           if isinstance(h,dict) and h.get("id") and h.get("name")}
    result={};provider_ids=set()
    for item in mapping["mappings"]:
        if not isinstance(item,dict):raise MediaHold("HOTEL_MAP_ROW_NOT_OBJECT")
        hid=str(item.get("jamaica_hotel_id",""))
        code=item.get("hbx_code")
        country=item.get("country")
        name=item.get("hotel_name")
        hbxname=item.get("hbx_verified_name")
        cc=item.get("hbx_country_code")
        evidence=item.get("identity_evidence_reference")
        assert_true(bool(ID.fullmatch(hid)) and hid in known and
            type(code) is int and 0<code<10**12 and
            code not in provider_ids and hid not in result and
            known[hid].get("name")==name and known[hid].get("country")==country and
            isinstance(hbxname,str) and len(exact_name(hbxname))>=4 and
            isinstance(cc,str) and bool(COUNTRY_CODE.fullmatch(cc)) and
            isinstance(evidence,str) and len(evidence.strip())>=12,
            "UNVERIFIED_OR_AMBIGUOUS_HOTEL_CROSSWALK")
        provider_ids.add(code);result[code]=(hid,item)
    assert_true(len(result)<=MAX_HOTELS,"HOTEL_MAP_TOO_LARGE")
    return result

def get_records(payload):
    if not isinstance(payload,dict):
        raise MediaHold("HBX_RESPONSE_NOT_OBJECT")
    rows=payload.get("hotels")
    if isinstance(rows,dict):
        rows=rows.get("hotels")
    assert_true(isinstance(rows,list) and len(rows)<=1200,"HBX_RESPONSE_HOTELS_INVALID")
    return rows

def hotel_photos(hotel, item, grant):
    photos=[];seen=set()
    name=item["hotel_name"]
    records=hotel.get("images")
    if not isinstance(records,list):
        return photos
    for record in records[:120]:
        if not isinstance(record,dict):continue
        path=record.get("path")
        if not isinstance(path,str) or not PATH.fullmatch(path) or ".." in path or path.startswith("/"):
            continue
        src=IMG+"bigger/"+path
        original=IMG+path
        if src in seen:continue
        seen.add(src)
        photos.append({
            "src":src,"source":original,
            "license":"contract-authorized",
            "alt":"Фото гостиницы "+name+" — источник HBX Group",
            "credit":grant["attribution_text"],
            "kind":"other"
        })
        if len(photos)>=MAX_PHOTOS:break
    return photos

def build(license_doc, mapping, directory, pages, *, today=None):
    grant=license_gate(license_doc,today=today)
    assert_true(isinstance(directory,dict) and
                directory.get("schema")=="jamaica.destination-directory.v1",
                "HOTEL_DIRECTORY_UNVERIFIED")
    by_code=verified_map(mapping,directory)
    joined={};read=0
    for page in pages:
        for hotel in get_records(page):
            read+=1
            if not isinstance(hotel,dict):continue
            code=hotel.get("code")
            if type(code) is not int or code not in by_code:continue
            hid,match=by_code[code]
            # Identity must agree with an INDEPENDENT crosswalk entry, not
            # automatically guessed from similar names and country strings.
            if exact_name(hotel.get("name"))!=exact_name(match["hbx_verified_name"]) or \
               hotel.get("countryCode")!=match["hbx_country_code"]:
                continue
            photos=hotel_photos(hotel,match,grant)
            if not photos:continue
            joined[hid]={
              "hotel_name":match["hotel_name"],"country":match["country"],
              "rights_verified":True,"commercial_publication_allowed":True,
              "permission_reference":grant["public_permission_reference"],
              "rights_verified_at":grant["license_verified_at"],
              "rights_expires_at":grant["rights_expires_at"],
              "approved_image_hosts":["photos.hotelbeds.com"],
              "approved_source_hosts":["photos.hotelbeds.com"],
              "photos":photos
            }
    assert_true(len(joined)<=MAX_HOTELS,"RESULT_HOTELS_TOO_MANY")
    return joined,{"provider_records_examined":read,
                   "mapped_hotel_ids":len(by_code),
                   "published_hotel_ids":len(joined),
                   "public_image_urls":sum(len(v["photos"]) for v in joined.values())}

def require_production_environment(env):
    """Never route an Evaluation account to the PRODUCTION photo publisher.

    API test keys must be checked separately with hbx_test_probe.py; no
    test content may be claimed to be licensed public hotel photos.
    """
    assert_true(isinstance(env,dict) and
        env.get("HBX_API_ENV")=="PRODUCTION" and
        env.get("HBX_LIVE_CONTENT_RIGHTS_CONFIRMED")=="yes",
        "LIVE_HBX_CREDENTIALS_AND_RIGHTS_NOT_ACTIVATED")
    assert_true(len(env.get("HBX_API_KEY",""))>=8 and
        len(env.get("HBX_API_SECRET",""))>=8,
        "LIVE_HBX_CREDENTIALS_MISSING")


def authenticated_pages(api_key,secret,max_pages=MAX_PAGES):
    assert_true(8<=len(api_key)<=512 and 8<=len(secret)<=512,
                "HBX_API_CREDENTIALS_MISSING")
    assert_true(1<=max_pages<=MAX_PAGES,"HBX_MAX_PAGES_INVALID")
    for i in range(max_pages):
        first=i*1000+1;last=first+999
        from urllib.parse import urlencode
        url=API+"?"+urlencode({"fields":"all","language":"ENG","from":first,"to":last})
        stamp=str(int(time.time()))
        signature=hashlib.sha256((api_key+secret+stamp).encode("utf-8")).hexdigest()
        request=urllib.request.Request(url,headers={
            "Api-key":api_key,"X-Signature":signature,
            "Accept":"application/json","User-Agent":"JamaicaLicensedHotelMedia/1.0"})
        # urllib follows redirects by default: deny any other origin.
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self,req,fp,code,msg,headers,newurl):
                raise MediaHold("HBX_UNEXPECTED_REDIRECT")
        with urllib.request.build_opener(NoRedirect()).open(request,timeout=25) as response:
            assert_true(response.status==200,"HBX_NON_200_RESPONSE")
            raw=response.read(MAX_RESPONSE+1)
        assert_true(len(raw)<=MAX_RESPONSE,"HBX_RESPONSE_TOO_LARGE")
        payload=json.loads(raw)
        rows=get_records(payload)
        if not rows:break
        yield payload
        if len(rows)<1000:break
        # Gentle enough for a once-daily background content sync.
        time.sleep(0.35)

def write_feed(output_dir, entries):
    root=Path(output_dir)
    assert_true(not root.is_symlink(),"HOTEL_MEDIA_DIR_SYMLINK")
    root.mkdir(parents=True,exist_ok=True)
    files={};lookup={}
    ids=sorted(entries,key=lambda k:(entries[k]["country"],k))
    for i,offset in enumerate(range(0,len(ids),SHARD_SIZE),start=1):
        part_ids=ids[offset:offset+SHARD_SIZE]
        rel="hotel-media-feed/part-"+format(i,"04d")+".json"
        for hid in part_ids:lookup[hid]=rel
        files[rel]={"schema":"jamaica.hotel-media-feed-part.v1",
                    "hotels":{hid:entries[hid] for hid in part_ids}}
    files["hotel-media-feed/index.json"]={
       "schema":"jamaica.hotel-media-feed-index.v1",
       "total_hotels":len(entries),"entries":lookup}
    for rel,payload in files.items():
        file=root/rel
        file.parent.mkdir(parents=True,exist_ok=True)
        assert_true(not file.is_symlink(),"HOTEL_MEDIA_FILE_SYMLINK")
        content=(json.dumps(payload,ensure_ascii=False,separators=(",",":"))+"\n").encode()
        assert_true(len(content)<=4_000_000,"HOTEL_MEDIA_CHUNK_TOO_LARGE")
        temp=file.with_suffix(".tmp")
        assert_true(not temp.is_symlink(),"HOTEL_MEDIA_TEMP_SYMLINK")
        temp.write_bytes(content)
        temp.replace(file)
    folder=root/"hotel-media-feed"
    for stale in folder.glob("part-*.json"):
        if stale.relative_to(root).as_posix() not in files:
            assert_true(not stale.is_symlink(),"HOTEL_MEDIA_STALE_SYMLINK")
            stale.unlink()
    return len(files)-1

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True)
    p.add_argument("--crosswalk",required=True)
    p.add_argument("--grant",required=True)
    p.add_argument("--output-dir",required=True)
    p.add_argument("--feed-json",help="Local authorized HBX Content API export")
    p.add_argument("--live",action="store_true",help="Read official HBX API using env credentials")
    p.add_argument("--max-pages",type=int,default=250)
    args=p.parse_args()
    assert_true(args.live!=bool(args.feed_json),"CHOOSE_LIVE_OR_OFFLINE_SOURCE")
    grant=load_json(args.grant,10000)
    license_gate(grant)
    directory=load_json(args.directory,32_000_000)
    mapping=load_json(args.crosswalk,8_000_000)
    verified_map(mapping,directory)
    if args.feed_json:
        raw=load_json(args.feed_json,50_000_000)
        pages=raw["pages"] if isinstance(raw,dict) and isinstance(raw.get("pages"),list) else [raw]
    else:
        require_production_environment(os.environ)
        pages=authenticated_pages(os.environ.get("HBX_API_KEY",""),
                                  os.environ.get("HBX_API_SECRET",""),
                                  max_pages=args.max_pages)
    entries,stats=build(grant,mapping,directory,pages)
    # A provider outage must NEVER erase a previously published hotel gallery.
    assert_true(bool(entries),"NO_VERIFIED_HOTEL_MEDIA_NO_PUBLICATION")
    count=write_feed(args.output_dir,entries)
    print("JAMAICA_HBX_VERIFIED_HOTELS="+str(stats["published_hotel_ids"]))
    print("JAMAICA_HBX_VERIFIED_IMAGES="+str(stats["public_image_urls"]))
    print("JAMAICA_HBX_MEDIA_SHARDS="+str(count))
    print("JAMAICA_HBX_IMAGE_BYTES_DOWNLOADED=0")
    print("JAMAICA_HBX_SALES_OR_BOOKINGS=0")

if __name__=="__main__":
    try:main()
    except (MediaHold,OSError,ValueError,KeyError,TypeError) as exc:
        # Never emit any credential, API body, hotel name or private map.
        print("JAMAICA_HBX_MEDIA_HOLD="+
            (str(exc) if isinstance(exc,MediaHold) else type(exc).__name__),file=sys.stderr)
        sys.exit(2)
