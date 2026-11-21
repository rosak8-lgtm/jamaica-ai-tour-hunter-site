#!/usr/bin/env python3
"""Private Oracle source photo discovery. Never publishes unlicensed images.

Official operator JSON API documents hotelPic + hotelId for
instant-confirmation special offers:
https://export.bgoperator.ru/ # section 6

Use only read-only official GET. Save candidate image references in a PRIVATE
0600 file; never copy bytes, write public JSON or enable any booking operation.
"""
from __future__ import annotations
import argparse
import json
import re
import sys
import urllib.parse
import urllib.error
from datetime import datetime,timezone
from pathlib import Path

import oracle_bg_route_sync as bg

SOURCE_CITY=bg.CITY_ID
SPO_HOST="export.bgoperator.ru"
MAX_FEED_BYTES=5*1024*1024
MAX_CANDIDATES=2500
IMAGE_RE=re.compile(r"^/pr_img/[A-Za-z0-9_.\-/]{5,260}\.(?:jpe?g|png|webp)$",re.I)

def safe_operator_image(raw):
    if not isinstance(raw,str) or len(raw)>400:
        return None
    try:
        u=urllib.parse.urlsplit(raw)
        if u.scheme not in ("http","https") or u.hostname not in (
                "bgoperator.ru","www.bgoperator.ru"):
            return None
        if u.port is not None or u.username or u.password or u.query or u.fragment:
            return None
        if not IMAGE_RE.fullmatch(u.path) or ".." in u.path:
            return None
        return "https://"+u.hostname+u.path
    except ValueError:
        return None

def parse_candidates(raw,hotels):
    if not isinstance(raw,(bytes,bytearray)) or len(raw)>MAX_FEED_BYTES:
        raise bg.SyncHold("SPO_MEDIA_RESPONSE_SIZE_INVALID")
    try:
        feed=json.loads(raw.decode("utf-8-sig"))
    except (ValueError,UnicodeError) as exc:
        raise bg.SyncHold("SPO_MEDIA_FORMAT_NOT_JSON") from exc
    if not isinstance(feed,list) or len(feed)>40000:
        raise bg.SyncHold("SPO_MEDIA_SCHEMA_INVALID")
    known={str(h["id"]):h for h in hotels if isinstance(h,dict) and h.get("id")}
    result={}
    for item in feed:
        if not isinstance(item,dict):
            continue
        hotel_id=str(item.get("hotelId",""))
        if not re.fullmatch(r"\d{7,20}",hotel_id) or hotel_id not in known:
            continue
        url=safe_operator_image(item.get("hotelPic"))
        if not url:
            continue
        hotel=known[hotel_id]
        # ID is an exact identity match: never match photos by fuzzy names.
        found=result.setdefault(hotel_id,{
            "hotel_id":hotel_id,"hotel_name":hotel["name"],
            "country":hotel["country"],"candidate_urls":[],
            "rights_status":"NOT_VERIFIED_NO_PUBLICATION",
        })
        if url not in found["candidate_urls"] and len(found["candidate_urls"])<10:
            found["candidate_urls"].append(url)
        if len(result)>MAX_CANDIDATES:
            raise bg.SyncHold("SPO_MEDIA_TOO_MANY_HOTELS")
    return [result[k] for k in sorted(result)]

def build_private(catalog,api,endpoint=None):
    if catalog.get("schema")!="jamaica.destination-directory.v1":
        raise bg.SyncHold("HOTEL_DIRECTORY_UNKNOWN")
    url=endpoint or ("https://"+SPO_HOST+"/auto/auto-spo-"+
                     SOURCE_CITY+"v2-124331253701.js")
    parts=urllib.parse.urlsplit(url)
    if parts.scheme!="https" or parts.hostname!=SPO_HOST or not parts.path.startswith("/auto/auto-spo-") or parts.query:
        raise bg.SyncHold("SPO_URL_NOT_ALLOWLISTED")
    bg.BASE="https://export.bgoperator.ru/"
    raw=api.get(url)
    candidates=parse_candidates(raw,catalog["hotels"])
    return {
        "schema":"jamaica.private.hotel-photo-candidates.v1",
        "checked_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "origin":"Иркутск",
        "publication_authorized":False,
        "hotel_count":len(candidates),"candidates":candidates,
    }

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True)
    p.add_argument("--output-private",required=True)
    p.add_argument("--credentials",default="")
    args=p.parse_args()
    directory=json.loads(Path(args.directory).read_text(encoding="utf-8"))
    output=Path(args.output_private).expanduser()
    if output.is_symlink() or output.name in ("tour-previews.json","hotel-media-approved.json"):
        raise bg.SyncHold("PRIVATE_MEDIA_DESTINATION_INVALID")
    output.parent.mkdir(mode=0o700,parents=True,exist_ok=True)
    if output.parent.stat().st_mode & 0o077:
        raise bg.SyncHold("PRIVATE_MEDIA_DIRECTORY_PERMISSIONS")
    login,pwd=bg.read_secret(bg.credentials_path(args.credentials))
    result=build_private(directory,bg.ApiClient(login,pwd))
    temporary=output.with_suffix(".tmp")
    if temporary.is_symlink():
        raise bg.SyncHold("PRIVATE_MEDIA_TEMP_SYMLINK")
    temporary.write_text(json.dumps(result,ensure_ascii=False,
                    separators=(",",":"))+"\n",encoding="utf-8")
    temporary.chmod(0o600)
    temporary.replace(output)
    print("JAMAICA_OFFICIAL_HOTEL_PHOTO_CANDIDATES="+str(result["hotel_count"]))
    print("JAMAICA_OFFICIAL_HOTEL_PHOTO_PUBLICATION_ALLOWED=NO")
    print("JAMAICA_OPERATOR_IMAGE_DOWNLOAD_OR_PUBLISH=NO")

if __name__=="__main__":
    try:main()
    except Exception as exc:
        print("JAMAICA_OFFICIAL_HOTEL_PHOTO_DISCOVERY_HOLD="+type(exc).__name__,
              file=sys.stderr)
        raise SystemExit(2)
