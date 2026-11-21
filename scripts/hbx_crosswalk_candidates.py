#!/usr/bin/env python3
"""Private candidate stage: exact hotel name + ISO country crosswalk, NOT approval.

Given an independently and lawfully obtained HBX Content API JSON export,
find possible JAMAICA / BG hotel-ID -> HBX code matches without guessing
across countries or combining unrelated hotels. NEVER publish the candidates.
An independent identity evidence review remains required before using the
production jamaica.hbx-crosswalk.v1 manifest.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import re
import sys
import unicodedata

from hbx_licensed_hotel_photos import get_records, load_json, PATH, MediaHold

# Explicit, conservative mapping; unknown countries do not match by name alone.
COUNTRY_ISO={
 "Таиланд":"TH","Китай":"CN","Вьетнам":"VN","Турция":"TR",
 "Египет":"EG","ОАЭ":"AE","Россия":"RU","Индонезия":"ID",
 "Индия":"IN","Шри-Ланка":"LK","Мальдивы":"MV","Малайзия":"MY",
 "Филиппины":"PH","Сингапур":"SG","Камбоджа":"KH","Япония":"JP",
 "Тунис":"TN","Грузия":"GE","Армения":"AM","Азербайджан":"AZ",
 "Узбекистан":"UZ","Казахстан":"KZ","Испания":"ES","Италия":"IT",
 "Франция":"FR","Греция":"GR","Кипр":"CY","Португалия":"PT",
 "Черногория":"ME","Хорватия":"HR","Болгария":"BG","Албания":"AL",
 "Сербия":"RS","Германия":"DE","Австрия":"AT","Чехия":"CZ",
 "Оман":"OM","Катар":"QA","Бахрейн":"BH","Саудовская Аравия":"SA",
 "Южная Корея":"KR","Сейшелы":"SC","Маврикий":"MU",
 "Доминикана":"DO","Куба":"CU","Мексика":"MX","Бразилия":"BR"
}
MAX_HBX_RECORDS=250000
MAX_CANDIDATES=120000

def normalized_name(value):
    if isinstance(value,dict):
        value=value.get("content")
    if not isinstance(value,str):
        return ""
    value=unicodedata.normalize("NFKC",value).casefold()
    value=re.sub(r"[^0-9\w]+"," ",value,flags=re.UNICODE)
    return " ".join(value.split())

def _country_name(country):
    if not isinstance(country,str):
        return None
    return COUNTRY_ISO.get(country)

def _city(value):
    if isinstance(value,dict):value=value.get("content")
    if not isinstance(value,str):return ""
    return " ".join(value.split())[:100]

def build_candidates(directory, pages):
    if not isinstance(directory,dict) or directory.get("schema")!="jamaica.destination-directory.v1":
        raise MediaHold("UNVERIFIED_JAMAICA_DIRECTORY")
    source_hotels=directory.get("hotels")
    if not isinstance(source_hotels,list) or not len(source_hotels)<=120000:
        raise MediaHold("HOTEL_DIRECTORY_INVALID")
    by_key_bg={}
    bg_count=0
    for item in source_hotels:
        if not isinstance(item,dict):continue
        hid=str(item.get("id",""))
        name=item.get("name")
        country=item.get("country")
        iso=_country_name(country)
        key=(iso,normalized_name(name))
        if not re.fullmatch(r"\d{7,20}",hid) or not key[0] or len(key[1])<5:
            continue
        by_key_bg.setdefault(key,[]).append({
          "jamaica_hotel_id":hid,"hotel_name":name,
          "country":country,"resort":item.get("resort") or ""})
        bg_count+=1

    by_key_hbx={}
    seen_records=0
    for page in pages:
        rows=get_records(page)
        for item in rows:
            seen_records+=1
            if seen_records>MAX_HBX_RECORDS:
                raise MediaHold("HBX_DATASET_TOO_MANY_RECORDS")
            if not isinstance(item,dict):continue
            code=item.get("code")
            name=item.get("name")
            iso=item.get("countryCode")
            key=(iso,normalized_name(name))
            if type(code) is not int or code<=0 or code>=10**12 or not iso or \
               not re.fullmatch(r"[A-Z]{2}",iso) or len(key[1])<5:
                continue
            paths=item.get("images")
            image_count=sum(1 for p in paths if isinstance(p,dict) and
                isinstance(p.get("path"),str) and PATH.fullmatch(p["path"])) \
                if isinstance(paths,list) else 0
            by_key_hbx.setdefault(key,[]).append({
                "hbx_code":code,
                "hbx_verified_name":name.get("content") if isinstance(name,dict) else name,
                "hbx_country_code":iso,
                "hbx_city":_city(item.get("city")),
                "hbx_address":_city(item.get("address")),
                "hbx_image_paths":image_count})

    matches=[]
    for key,jamaica_matches in by_key_bg.items():
        hbx_matches=by_key_hbx.get(key,[])
        # Name+country exact but duplicated property names are ambiguous.
        # Do not auto-stage multiple candidate codes per same hotel.
        if len(jamaica_matches)!=1 or len(hbx_matches)!=1:
            continue
        bg=jamaica_matches[0]
        hbx=hbx_matches[0]
        matches.append({
            **bg,**hbx,
            "matched_by":"EXACT_NORMALIZED_NAME_AND_ISO_COUNTRY_UNIQUE",
            "status":"REQUIRES_INDEPENDENT_PROPERTY_ID_REVIEW",
            "identity_evidence_reference":None,
            "publication_authorized":False
        })
    matches.sort(key=lambda x:(x["country"],x["hotel_name"],x["jamaica_hotel_id"]))
    if len(matches)>MAX_CANDIDATES:
        raise MediaHold("CANDIDATE_COUNT_UNSAFE")
    return {
        "schema":"jamaica.private.hbx-crosswalk-candidates.v1",
        "classification":"PRIVATE_REVIEW_ONLY_NEVER_PUBLICATION",
        "publication_authorized":False,
        "bg_hotels_considered":bg_count,
        "hbx_hotels_considered":seen_records,
        "candidate_count":len(matches),
        "candidates":matches
    }

def write_private(path,data):
    target=Path(path).expanduser()
    if target.name in ("hotel-media-approved.json","index.json","crosswalk.json") or target.is_symlink():
        raise MediaHold("CANDIDATES_CANNOT_OVERWRITE_PUBLISHED_OR_APPROVED_MANIFEST")
    parent=target.parent
    parent.mkdir(parents=True,exist_ok=True,mode=0o700)
    if parent.is_symlink() or parent.stat().st_mode & 0o077:
        raise MediaHold("CANDIDATE_DIRECTORY_MUST_BE_PRIVATE")
    if target.exists() and target.stat().st_mode & 0o077:
        raise MediaHold("CANDIDATE_DESTINATION_UNSAFE_PERMISSIONS")
    blob=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode("utf-8")+b"\n"
    if len(blob)>35_000_000:
        raise MediaHold("CANDIDATES_TOO_BIG")
    temporary=target.with_name(target.name+".tmp")
    if temporary.is_symlink():raise MediaHold("UNSAFE_TEMPORARY_FILE")
    temporary.write_bytes(blob)
    temporary.chmod(0o600)
    temporary.replace(target)

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--directory",required=True)
    p.add_argument("--hbx-json",required=True,
       help="Private, lawfully obtained HBX Content API JSON response or pages bundle")
    p.add_argument("--output-private",required=True)
    args=p.parse_args()
    data=load_json(args.directory,limit=32_000_000)
    raw=load_json(args.hbx_json,limit=100_000_000)
    pages=raw["pages"] if isinstance(raw,dict) and isinstance(raw.get("pages"),list) else [raw]
    if len(pages)>300:raise MediaHold("TOO_MANY_INPUT_PAGES")
    result=build_candidates(data,pages)
    write_private(args.output_private,result)
    print("JAMAICA_HBX_PRIVATE_MATCH_CANDIDATES="+str(result["candidate_count"]))
    print("JAMAICA_HBX_CROSSWALK_AUTO_APPROVED=0")
    print("JAMAICA_HBX_PUBLICATION_ALLOWED=NO")
    print("JAMAICA_HBX_HOTEL_PHOTO_BYTES_DOWNLOADED=0")

if __name__=="__main__":
    try:main()
    except (MediaHold,ValueError,OSError,TypeError,KeyError):
        print("JAMAICA_HBX_CROSSWALK_HOLD=INVALID_INPUT_OR_UNSAFE_DESTINATION",file=sys.stderr)
        sys.exit(2)
