#!/usr/bin/env python3
"""Synchronize public tourism directory on GitHub Actions.

Only published reference data is fetched: countries, cities/resorts, hotel names.
No prices, sessions, booking actions, private credentials or copyrighted photos.
No storefront supplier branding. On failures, previous verified directory remains.
"""
from __future__ import annotations
import gzip, json, re, sys, urllib.request
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

SOURCES={
    "countries":"https://export.bgoperator.ru/yandex?action=countries",
    "hotels":"https://export.bgoperator.ru/yandex?action=hotelsJson",
    "resorts":"https://export.bgoperator.ru/auto/jsonResorts.json",
}
DEST=Path("destination-directory.json")
MAX_SOURCE=25*1024*1024
MAX_HOTELS=120000
IRKUTSK="100510397223"
COUNTRY_PRIORITY=["Таиланд","Китай","Вьетнам"]
RE_SAFE=re.compile(r"^[\w .,&'()\-/+*№А-Яа-яЁё]{2,180}$",re.UNICODE)
DIGITS=re.compile(r"^\d{7,20}$")

def fetch_json(url: str):
    if not url.startswith("https://export.bgoperator.ru/"):
        raise ValueError("unapproved provider endpoint")
    req=urllib.request.Request(url,headers={
        "Accept-Encoding":"gzip",
        "Accept":"application/json",
        "User-Agent":"JAMAICA-public-directory/1.0 (+public reference sync)"
    })
    with urllib.request.urlopen(req,timeout=35) as resp:
        if resp.status!=200:raise ValueError("HTTP_INVALID")
        raw=resp.read(MAX_SOURCE+1)
        if len(raw)>MAX_SOURCE:raise ValueError("SOURCE_TOO_LARGE")
        if resp.headers.get("Content-Encoding","").lower()=="gzip":
            raw=gzip.decompress(raw)
        if len(raw)>MAX_SOURCE*5:raise ValueError("SOURCE_DECOMPRESSED_TOO_LARGE")
        obj=json.loads(raw)
        if not isinstance(obj,list):raise ValueError("SOURCE_NOT_ARRAY")
        return obj

def clean(v,limit=160):
    if not isinstance(v,str):return ""
    s=" ".join(v.split())[:limit]
    if len(s)<2 or any(ord(ch)<32 or ch in "<>{}" for ch in s):return ""
    return s

def build(countries,hotels,resorts):
    if not (180<=len(countries)<=400 and 500<=len(hotels)<=MAX_HOTELS and 100<=len(resorts)<=25000):
        raise ValueError("UNEXPECTED_DIRECTORY_SIZE")
    raw_c=[]
    ids=set()
    for c in countries:
        if not isinstance(c,dict):continue
        cid=str(c.get("id",""))
        name=clean(c.get("title_ru"))
        if not DIGITS.fullmatch(cid) or not name or cid in ids or name.lower()=="x":continue
        ids.add(cid)
        raw_c.append({
          "id":cid,"name":name,"code":clean(c.get("code"),10),
          "has_tour_catalog":c.get("tours")=="Да",
          "irkutsk_in_catalog":IRKUTSK in str(c.get("town_from","")).split("#"),
          "origins":[x for x in str(c.get("town_from","")).split("#") if DIGITS.fullmatch(x)][:120]
        })
    if len(raw_c)<180:raise ValueError("VALID_COUNTRIES_TOO_FEW")
    raw_c.sort(key=lambda c:(COUNTRY_PRIORITY.index(c["name"]) if c["name"] in COUNTRY_PRIORITY else 999,c["name"]))
    known={c["id"]:c["name"] for c in raw_c}
    loc={}
    for r in resorts:
        if not isinstance(r,dict):continue
        rid=str(r.get("id",""))
        title=clean(r.get("title_ru"))
        if rid and title:loc[rid]=title
    raw_h=[]
    seen=set()
    for h in hotels:
        if not isinstance(h,dict):continue
        hid=str(h.get("key",""))
        country=str(h.get("countryKey",""))
        city=str(h.get("cityKey",""))
        name=clean(h.get("name"))
        stars=clean(h.get("stars"),12)
        if not DIGITS.fullmatch(hid) or country not in known or not name or hid in seen:continue
        seen.add(hid)
        raw_h.append({"id":hid,"name":name,"country":known[country],
                      "country_id":country,"resort":loc.get(city,""),
                      "stars":stars})
    if len(raw_h)<500:raise ValueError("HOTELS_TOO_FEW")
    raw_h.sort(key=lambda h:(COUNTRY_PRIORITY.index(h["country"]) if h["country"] in COUNTRY_PRIORITY else 999,h["country"],h["resort"],h["name"]))
    return {
      "schema":"jamaica.destination-directory.v1",
      "updated_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
      "classification":"REFERENCE_NOT_BOOKABLE",
      "availability_verified":False,
      "quote_verified":False,
      "total_hotels":len(raw_h),
      "total_countries":len(raw_c),
      "countries":raw_c,
      "hotels":raw_h,
    }

def main():
    data={name:fetch_json(url) for name,url in SOURCES.items()}
    obj=build(data["countries"],data["hotels"],data["resorts"])
    payload=json.dumps(obj,ensure_ascii=False,separators=(",",":"))+"\n"
    if len(payload.encode("utf-8"))>12*1024*1024:raise ValueError("PUBLIC_DIRECTORY_TOO_LARGE")
    temp=DEST.with_suffix(".json.new")
    temp.write_text(payload,encoding="utf-8")
    temp.replace(DEST)
    counts=Counter(h["country"] for h in obj["hotels"])
    print("JAMAICA_DIRECTORY_SYNC_PASS")
    print("COUNTRIES="+str(obj["total_countries"]))
    print("HOTELS="+str(obj["total_hotels"]))
    print("PRIORITY_HOTELS="+json.dumps({k:counts[k] for k in COUNTRY_PRIORITY},ensure_ascii=False))
    print("PUBLIC_BOOKABLE_OFFERS_ADDED=0")
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        # Never replace catalog with stale empty data; CI logs never contain secrets.
        print("JAMAICA_DIRECTORY_SYNC_HOLD="+type(exc).__name__+":"+str(exc)[:140],file=sys.stderr)
        sys.exit(2)
