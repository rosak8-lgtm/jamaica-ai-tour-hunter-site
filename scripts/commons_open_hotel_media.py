#!/usr/bin/env python3
"""Wikidata P18 -> Wikimedia Commons: real hotel photos, license verified per file.

All photos must belong to an INDEPENDENTLY REVIEWED exact JAMAICA hotel ID ↔
Wikidata item QID mapping with independently verified country. No fuzzy hotel
name matching, image searching by resort or speculative matching. Downloads
only bounded JSON metadata; image binaries stay on Commons.
"""
from __future__ import annotations
import argparse
from datetime import datetime,timezone,date
from html.parser import HTMLParser
import json
from pathlib import Path
import re
import sys
import urllib.parse
import urllib.request

SCHEMA="jamaica.commons-hotel-media.v1"
IDENTITY="jamaica.commons-hotel-identities.v1"
WD="https://www.wikidata.org/w/api.php"
COMMONS="https://commons.wikimedia.org/w/api.php"
UA="JamaicaHotelMedia/1.0 (https://github.com/rosak8-lgtm/jamaica-ai-tour-hunter-site; hotel photo reuse metadata)"
MAX_RESPONSE=400000
MAX_HOTELS=15000
MAX_FILES_PER_HOTEL=12
MAX_OUTPUT_SIZE=45000000
BATCH=200
QID=re.compile(r"^Q[1-9][0-9]{0,14}$")
IMAGE=re.compile(r"^[^/\\\x00-\x1f<>?%#]{5,180}\.(?:jpe?g|png|webp)$",re.I)
LICENSES={
 "CC BY 2.0":"https://creativecommons.org/licenses/by/2.0/",
 "CC BY 3.0":"https://creativecommons.org/licenses/by/3.0/",
 "CC BY 4.0":"https://creativecommons.org/licenses/by/4.0/",
 "CC BY-SA 2.0":"https://creativecommons.org/licenses/by-sa/2.0/",
 "CC BY-SA 3.0":"https://creativecommons.org/licenses/by-sa/3.0/",
 "CC BY-SA 4.0":"https://creativecommons.org/licenses/by-sa/4.0/",
 "CC0 1.0":"https://creativecommons.org/publicdomain/zero/1.0/",
}
# Verified Wikidata country item IDs; no cross-country name guessing.
COUNTRIES={"Таиланд":"Q869","Китай":"Q148","Вьетнам":"Q881",
 "Индонезия":"Q252","Индия":"Q668","Мальдивы":"Q826","Япония":"Q17",
 "Турция":"Q43","Египет":"Q79","ОАЭ":"Q878","Шри-Ланка":"Q854",
 "Малайзия":"Q833","Филиппины":"Q928","Камбоджа":"Q424",
 "Россия":"Q159","Грузия":"Q230","Узбекистан":"Q265",
 "Испания":"Q29","Италия":"Q38","Греция":"Q41","Франция":"Q142",
 "Германия":"Q183","Португалия":"Q45","Кипр":"Q229",
 "Болгария":"Q219","Черногория":"Q236","Хорватия":"Q224"}

class Hold(ValueError):pass
def require(check,msg):
    if not check:raise Hold(msg)

class PlainText(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True);self.parts=[]
    def handle_data(self,data):
        if data:self.parts.append(data)
def plain(value):
    p=PlainText();p.feed(str(value or ""))
    return " ".join(" ".join(p.parts).split())[:140]

def safe_file(name):
    if not isinstance(name,str) or not IMAGE.fullmatch(name) or ".." in name:
        return None
    return name

def load(path,max_size=25_000_000):
    p=Path(path)
    require(p.is_file() and not p.is_symlink() and p.stat().st_size<=max_size,
            "UNSAFE_INPUT_FILE")
    return json.loads(p.read_text(encoding="utf-8"))

def check_identities(data,directory):
    require(isinstance(data,dict) and data.get("schema")==IDENTITY and
       isinstance(data.get("hotels"),dict),"IDENTITY_SCHEMA_INVALID")
    require(isinstance(directory,dict) and
       directory.get("schema")=="jamaica.destination-directory.v1",
       "DIRECTORY_SCHEMA_INVALID")
    known={str(h["id"]):h for h in directory.get("hotels",[])
           if isinstance(h,dict) and h.get("id") and h.get("name")}
    used=set();valid={}
    require(len(data["hotels"])<=MAX_HOTELS,"IDENTITY_COUNT_UNSAFE")
    for hotel_id,item in data["hotels"].items():
        if not isinstance(item,dict):raise Hold("UNVERIFIED_IDENTITY_ENTRY")
        h=known.get(hotel_id)
        qid=item.get("wikidata_qid")
        if (h is None or not re.fullmatch(r"\d{7,20}",hotel_id) or
            h.get("name")!=item.get("hotel_name") or
            h.get("country")!=item.get("country") or
            not QID.fullmatch(str(qid)) or qid in used or
            COUNTRIES.get(item.get("country"))!=item.get("wikidata_country_qid") or
            item.get("identity_reviewed") is not True or
            not isinstance(item.get("review_reference"),str) or
            not item["review_reference"].startswith("https://") or
            not isinstance(item.get("reviewed_at"),str)):
            raise Hold("HOTEL_WIKIDATA_IDENTITY_NOT_VERIFIED")
        try:dt=date.fromisoformat(item["reviewed_at"])
        except ValueError as exc:raise Hold("IDENTITY_DATE_INVALID") from exc
        require(dt<=date.today(),"IDENTITY_REVIEW_FUTURE_DATED")
        extras=item.get("additional_photos",[])
        require(isinstance(extras,list) and len(extras)<=MAX_FILES_PER_HOTEL,
                "EXTRA_PHOTOS_UNSAFE")
        for photo in extras:
            if (not isinstance(photo,dict) or not safe_file(photo.get("file")) or
                photo.get("kind") not in ("hotel_exterior","hotel_public_area") or
                photo.get("property_photo_reviewed") is not True or
                not isinstance(photo.get("review_reference"),str) or
                not photo["review_reference"].startswith("https://")):
                raise Hold("UNVERIFIED_EXTRA_PROPERTY_PHOTO")
        used.add(qid);valid[hotel_id]=item
    return valid

def source_json(url, params, transport=None):
    require(url in (WD,COMMONS),"UNKNOWN_REMOTE_MEDIA_HOST")
    query=urllib.parse.urlencode({"action":params.pop("action"),"format":"json",**params})
    req=urllib.request.Request(url+"?"+query,headers={
      "User-Agent":UA,"Accept":"application/json"})
    if transport is not None:
        response=transport(req)
    else:
        response=urllib.request.urlopen(req,timeout=18)
    with response:
        require(getattr(response,"status",200)==200,"WIKI_API_HTTP_UNEXPECTED")
        content=response.read(MAX_RESPONSE+1)
    require(len(content)<=MAX_RESPONSE,"WIKI_METADATA_TOO_LARGE")
    return json.loads(content)

def _q_values(entity,prop):
    return {v.get("mainsnak",{}).get("datavalue",{}).get("value",{}).get("id")
            for v in entity.get("claims",{}).get(prop,[])
            if isinstance(v,dict)}

def _main_image(entity):
    for item in entity.get("claims",{}).get("P18",[]):
        raw=item.get("mainsnak",{}).get("datavalue",{}).get("value")
        if safe_file(raw):return raw
    return None

def _validated_file(resp,file):
    pages=resp.get("query",{}).get("pages",{})
    if not isinstance(pages,dict):return None
    for page in pages.values():
        if not isinstance(page,dict) or page.get("missing") is not None:continue
        ii=page.get("imageinfo")
        if not isinstance(ii,list) or not ii:continue
        record=ii[0]
        ext=record.get("extmetadata",{})
        if not isinstance(ext,dict):continue
        def meta(name):
            x=ext.get(name)
            return x.get("value","") if isinstance(x,dict) else ""
        lic=plain(meta("LicenseShortName"))
        if lic not in LICENSES and lic not in ("Public domain",):
            continue
        lic_url=meta("LicenseUrl")
        expected=LICENSES.get(lic)
        if expected and not lic_url.startswith(expected):
            continue
        # Public domain still needs accurate provenance, source file and author.
        author=plain(meta("Artist")) or plain(meta("Credit"))
        if not author:continue
        mime=record.get("mime")
        if mime and mime not in ("image/jpeg","image/png","image/webp"):continue
        source="https://commons.wikimedia.org/wiki/File:"+urllib.parse.quote(
                    file.replace(" ","_"),safe="()_-.,")
        if page.get("title","").replace("_"," ")!="File:"+file.replace("_"," "):
            continue
        src="https://commons.wikimedia.org/wiki/Special:FilePath/"+urllib.parse.quote(file,safe="")+"?width=720"
        return {"file":file,"src":src,"source":source,
          "license":lic,"license_url":expected or "https://commons.wikimedia.org/wiki/Commons:Licensing",
          "author":author,"alt":"Фотография конкретной гостиницы: "+file[:120],
          "kind":"hotel_property"}
    return None

def build(directory,identity,*,transport=None):
    verified=check_identities(identity,directory)
    entries={};stats={"mapped":len(verified),"country_rejected":0,
       "unavailable":0,"license_rejected":0,"hotels":0,"photos":0}
    for hotel_id,item in verified.items():
        qid=item["wikidata_qid"]
        data=source_json(WD,{"action":"wbgetentities",
            "ids":qid,"props":"claims"},transport=transport)
        entity=data.get("entities",{}).get(qid)
        if not isinstance(entity,dict) or item["wikidata_country_qid"] not in _q_values(entity,"P17"):
            stats["country_rejected"]+=1;continue
        requested=[]
        p18=_main_image(entity)
        if p18:requested.append((p18,"hotel_property"))
        for extra in item.get("additional_photos",[]):
            requested.append((extra["file"],extra["kind"]))
        photos=[];seen=set()
        for file,kind in requested[:MAX_FILES_PER_HOTEL]:
            if file in seen:continue
            seen.add(file)
            result=source_json(COMMONS,{"action":"query",
                "prop":"imageinfo","iiprop":"extmetadata|mime",
                "titles":"File:"+file},transport=transport)
            photo=_validated_file(result,file)
            if not photo:
                stats["license_rejected"]+=1;continue
            photo["kind"]=kind
            photo["wikidata_qid"]=qid
            photos.append(photo)
        if not photos:stats["unavailable"]+=1;continue
        entries[hotel_id]={"hotel_name":item["hotel_name"],
            "country":item["country"],"wikidata_qid":qid,
            "identity_review_reference":item["review_reference"],
            "identity_reviewed":True,"photos":photos}
        stats["hotels"]+=1;stats["photos"]+=len(photos)
    return entries,stats

def stage(output_dir,entries):
    root=Path(output_dir)
    require(not root.is_symlink(),"PUBLIC_OUTPUT_DIR_SYMLINK")
    root.mkdir(parents=True,exist_ok=True)
    directory=root/"hotel-open-media"
    require(not directory.is_symlink(),"OPEN_MEDIA_DIR_SYMLINK")
    directory.mkdir(exist_ok=True)
    index={};parts={}
    ids=sorted(entries)
    for i in range(0,len(ids),BATCH):
        filename="part-"+str(i//BATCH+1).zfill(4)+".json"
        rel="hotel-open-media/"+filename
        subset=ids[i:i+BATCH]
        parts[filename]={"schema":"jamaica.hotel-open-media-part.v1",
            "hotels":{hotel_id:entries[hotel_id] for hotel_id in subset}}
        for hotel_id in subset:index[hotel_id]=rel
    files={"index.json":{"schema":"jamaica.hotel-open-media-index.v1",
       "total_hotels":len(ids),"entries":index},**parts}
    # Stage/validate all byte lengths before mutating any public files.
    encoded={name:(json.dumps(payload,ensure_ascii=False,
        separators=(",",":"))+"\n").encode() for name,payload in files.items()}
    require(all(len(raw)<=4_000_000 for raw in encoded.values()) and
       sum(len(raw) for raw in encoded.values())<=MAX_OUTPUT_SIZE,
       "OPEN_MEDIA_PUBLIC_BUNDLE_TOO_LARGE")
    for filename,raw in encoded.items():
        p=directory/filename
        require(not p.is_symlink(),"OPEN_MEDIA_PUBLIC_FILE_SYMLINK")
        tmp=p.with_name(filename+".tmp")
        require(not tmp.is_symlink(),"OPEN_MEDIA_TEMP_SYMLINK")
        tmp.write_bytes(raw);tmp.replace(p)
    for old in directory.glob("part-*.json"):
        if old.name not in parts:
            require(not old.is_symlink(),"OPEN_MEDIA_STALE_SYMLINK")
            old.unlink()
    return len(parts)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--directory",required=True)
    ap.add_argument("--reviewed-mapping",required=True)
    ap.add_argument("--output-dir",required=True)
    args=ap.parse_args()
    directory=load(args.directory)
    identity=load(args.reviewed_mapping,max_size=12_000_000)
    # Refuse to remove existing verified photos during an empty/upstream outage.
    validated=check_identities(identity,directory)
    require(bool(validated),"NO_REVIEWED_WIKIDATA_HOTEL_IDS")
    photos,stats=build(directory,identity)
    require(bool(photos),"NO_VALID_OPEN_HOTEL_PHOTOS_NO_PUBLICATION")
    n=stage(args.output_dir,photos)
    print("JAMAICA_OPEN_MEDIA_VERIFIED_HOTELS="+str(stats["hotels"]))
    print("JAMAICA_OPEN_MEDIA_LICENSED_IMAGES="+str(stats["photos"]))
    print("JAMAICA_OPEN_MEDIA_SHARDS="+str(n))
    print("JAMAICA_OPEN_MEDIA_IMAGE_BYTES_DOWNLOADED=0")
    print("JAMAICA_OPEN_MEDIA_BOOKINGS_OR_PAYMENTS=0")

if __name__=="__main__":
    try:main()
    except (Hold,ValueError,KeyError,TypeError,OSError):
        print("JAMAICA_OPEN_MEDIA_HOLD=UNVERIFIED_IDENTITY_OR_IMAGE_LICENSE",
              file=sys.stderr);sys.exit(2)
