#!/usr/bin/env python3
"""Validate ALL published JAMAICA preview shards and stage ONE public tour.

Offline Lenovo-side selector for read-only Oracle diagnostics. The browser
supports up to 60k verified-source preliminary cards across hashed JSON shards.
A selected ID may live in any shard, not just the first 8k root previews.
No provider credentials, booking XML, passenger details or prices leave Oracle.
Only the chosen ALREADY PUBLIC descriptive row is copied to a private 0600
temporary feed, after every source shard/hash/row has been validated.
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta, datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import sys

ID=re.compile(r"^p_[a-f0-9]{24}$")
HOTEL_ID=re.compile(r"^\d{7,20}$")
SHA256=re.compile(r"^[a-f0-9]{64}$")
DATE=re.compile(r"^\d{4}-\d{2}-\d{2}$")
ALLOWED_FIELDS={"id","hotel_id","hotel","country","origin","resort","room",
    "depart_date","nights","status","price_reference_rub",
    "price_reference_party","quote_verified","availability_verified",
    "flight_verified","bookable"}
PRIORITY=("Таиланд","Китай","Вьетнам")

def _json_at(path:Path, max_bytes:int):
    if (path.is_symlink() or not path.is_file() or
        not 2<=path.stat().st_size<=max_bytes):
        raise ValueError("UNSAFE_CATALOG_FILE")
    return json.loads(path.read_text(encoding="utf-8"))

def _safe_row(row):
    if not isinstance(row,dict) or set(row)!=ALLOWED_FIELDS:
        return False
    if (not isinstance(row["id"],str) or not ID.fullmatch(row["id"]) or
        not isinstance(row["hotel_id"],str) or
        not HOTEL_ID.fullmatch(row["hotel_id"])):
        return False
    if (any(not isinstance(row[key],str) or not row[key] or
            len(row[key])>200 for key in ("hotel","country","room","origin")) or
        not isinstance(row["resort"],str) or
        row["origin"]!="Иркутск" or
        type(row["nights"]) is not int or not 3<=row["nights"]<=180):
        return False
    if (row["bookable"] is not False or
        row["quote_verified"] is not False or
        row["availability_verified"] is not False or
        row["flight_verified"] is not False):
        return False
    if (not isinstance(row["depart_date"],str) or
        not DATE.fullmatch(row["depart_date"])):
        return False
    try:
        if date.fromisoformat(row["depart_date"]).isoformat()!=row["depart_date"]:
            return False
    except ValueError:
        return False
    price=row["price_reference_rub"]
    if row["status"]=="PREVIOUSLY_SEEN_NOT_RECHECKED":
        return price is None and row["price_reference_party"]=="UNVERIFIED"
    if row["status"]!="REFERENCE_PRICE_LIST_ONLY":
        return False
    return ((price is None and row["price_reference_party"]=="UNVERIFIED")
        or (type(price) is int and 0<price<=100_000_000 and
            row["price_reference_party"]=="TWO_ADULTS"))

def _all_previews(root_path:Path):
    feed=_json_at(root_path,8_000_000)
    if (not isinstance(feed,dict) or
        feed.get("schema")!="jamaica.tour-previews.v1" or
        feed.get("bookable") is not False or
        feed.get("quote_verified") is not False or
        feed.get("availability_verified") is not False):
        raise ValueError("INVALID_ROOT_CATALOG")
    root_rows=feed.get("previews")
    if (not isinstance(root_rows,list) or
        not 0<len(root_rows)<=8000):
        raise ValueError("INVALID_ROOT_ROWS")
    manifest=feed.get("shards",[])
    if not isinstance(manifest,list) or len(manifest)>13:
        raise ValueError("INVALID_SHARD_MANIFEST")
    rows=[];seen=set()
    def append(all_rows):
        for row in all_rows:
            if not _safe_row(row) or row["id"] in seen:
                raise ValueError("UNSAFE_OR_DUPLICATE_PREVIEW")
            seen.add(row["id"])
            rows.append(row)
    append(root_rows)
    total=len(rows)
    for number,entry in enumerate(manifest,1):
        path="tour-previews-shards/part-"+str(number).zfill(3)+".json"
        if (not isinstance(entry,dict) or
            entry.get("path")!=path or
            type(entry.get("count")) is not int or
            not 1<=entry["count"]<=4000 or
            not isinstance(entry.get("sha256"),str) or
            not SHA256.fullmatch(entry["sha256"])):
            raise ValueError("INVALID_SHARD_METADATA")
        total+=entry["count"]
        if total>60000:
            raise ValueError("CATALOG_ROW_LIMIT_EXCEEDED")
        shard=_json_at(root_path.parent/path,4_000_000)
        if (not isinstance(shard,dict) or
            shard.get("schema")!="jamaica.tour-preview-shard.v1" or
            shard.get("refreshed_at_utc")!=feed.get("refreshed_at_utc") or
            any(shard.get(flag) is not False for flag in
                ("bookable","quote_verified","availability_verified"))):
            raise ValueError("INVALID_SHARD_CONTENT")
        part=shard.get("previews")
        if not isinstance(part,list) or len(part)!=entry["count"]:
            raise ValueError("INVALID_SHARD_ROW_COUNT")
        exact=hashlib.sha256(json.dumps(part,ensure_ascii=False,
            sort_keys=True,separators=(",",":")).encode("utf-8")).hexdigest()
        if exact!=entry["sha256"]:
            raise ValueError("INVALID_SHARD_SHA256")
        append(part)
    published=feed.get("total_published_previews")
    if (manifest and (type(published) is not int or published!=len(rows))) or (
        not manifest and published is not None and published!=len(rows)):
        raise ValueError("CATALOG_TOTAL_INCONSISTENT")
    return feed,rows

def selected(root_path:Path, *, preview_id:str="", country:str="",
             today:date|None=None):
    if preview_id and (not isinstance(preview_id,str) or not ID.fullmatch(preview_id)):
        raise ValueError("INVALID_SELECTED_PREVIEW_ID")
    if country and (not isinstance(country,str) or
                    not 1<=len(country)<=120 or any(c in country for c in "\r\n\x00")):
        raise ValueError("INVALID_COUNTRY_SELECTION")
    feed,rows=_all_previews(root_path)
    today=today or datetime.now(timezone.utc).date()
    latest=today+timedelta(days=180)
    matches=[]
    for item in rows:
        if preview_id and item["id"]!=preview_id:
            continue
        if country and item["country"]!=country:
            continue
        depart=date.fromisoformat(item["depart_date"])
        if not today<depart<=latest:
            continue
        matches.append(item)
    if not matches:
        raise ValueError("SELECTED_PREVIEW_NOT_IN_CURRENT_FULL_CATALOG")
    if preview_id and len(matches)!=1:
        raise ValueError("AMBIGUOUS_SELECTED_PREVIEW_ID")
    def rank(item):
        name=item["country"]
        return (
            item["status"]!="REFERENCE_PRICE_LIST_ONLY",
            PRIORITY.index(name) if name in PRIORITY else
                3 if name!="Россия" else 4,
            item["price_reference_rub"] is None,
            item["depart_date"],name,item["id"]
        )
    chosen=min(matches,key=rank)
    # Staging contains exactly one existing PUBLIC row; no directory/supplier
    # metadata, unrelated hotel options or externally supplied private fields.
    minimal={"schema":"jamaica.tour-previews.v1",
             "refreshed_at_utc":feed.get("refreshed_at_utc"),
             "bookable":False,"quote_verified":False,
             "availability_verified":False,"previews":[chosen]}
    return chosen["id"],minimal

def save_private_feed(path:Path,feed:dict):
    if path.is_symlink() or path.exists():
        raise ValueError("STAGING_OUTPUT_ALREADY_EXISTS")
    payload=json.dumps(feed,ensure_ascii=False,separators=(",",":")).encode("utf-8")+b"\n"
    flags=os.O_WRONLY|os.O_CREAT|os.O_EXCL
    if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
    fd=os.open(path,flags,0o600)
    try:
        with os.fdopen(fd,"wb") as stream:
            os.fchmod(stream.fileno(),0o600)
            stream.write(payload)
    except BaseException:
        path.unlink(missing_ok=True)
        raise

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",required=True)
    p.add_argument("--preview-id",default="")
    p.add_argument("--country",default="")
    p.add_argument("--output",default="")
    args=p.parse_args()
    preview_id,feed=selected(Path(args.root),
        preview_id=args.preview_id,country=args.country)
    if args.output:
        save_private_feed(Path(args.output),feed)
    print(preview_id)

if __name__=="__main__":
    try:
        main()
    except (ValueError,TypeError,OSError,UnicodeError,KeyError):
        print("JAMAICA_LOCAL_SHARDED_SELECTION_HOLD=SOURCE_OR_SELECTION_INVALID",
              file=sys.stderr)
        sys.exit(2)
