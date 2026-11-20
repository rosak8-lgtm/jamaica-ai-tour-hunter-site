#!/usr/bin/env python3
"""Read-only authenticated BG price-list discovery, executed ONLY on the owner's Oracle.
It never creates bookings, submits forms, fetches passports or takes payments.
Credentials stay on Oracle. Output contains only sanitized public route metadata,
NO operator URL, ID, cookie, password, or non-final prices.
"""
from __future__ import annotations
import argparse, gzip, hashlib, html, http.cookiejar, json, os, re, stat, sys, time
import urllib.error, urllib.parse, urllib.request
from datetime import datetime, date, timezone, timedelta
from pathlib import Path
from collections import Counter

BASE="https://export.bgoperator.ru/yandex"
AUTH="https://login.bgoperator.ru/auth"
CITY_ID="100510397223"
MAX_BYTES=15*1024*1024
SCOPE_DAYS=180
NAME_RE=re.compile(r"\s+")
HTML_TAG_RE=re.compile(r"<[^>]{0,300}>")
TIMING_SECONDS=0.4
MAX_ITEMS=24000

class SyncHold(Exception):pass

def read_secret(path:Path):
    if not path.is_file() or path.is_symlink():raise SyncHold("CREDENTIALS_NOT_FOUND")
    st=path.stat()
    if st.st_mode & (stat.S_IRWXG|stat.S_IRWXO):
        raise SyncHold("CREDENTIALS_PERMISSIONS_NOT_PRIVATE")
    if st.st_size>65536:raise SyncHold("CREDENTIALS_FILE_TOO_LARGE")
    obj=json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj,dict):raise SyncHold("CREDENTIALS_SCHEMA_UNKNOWN")
    def find(o,names):
        for name in names:
            if isinstance(o.get(name),str) and o[name].strip():return o[name]
        for key in ("credentials","auth","bg","bg_credentials","account","private","data"):
            if isinstance(o.get(key),dict):
                v=find(o[key],names)
                if v:return v
        return None
    login=find(obj,("login","username","user","agency_login","bg_login","api_login"))
    password=find(obj,("pwd","password","pass","agency_password","bg_password","api_password"))
    if not login or not password:raise SyncHold("CREDENTIALS_FIELDS_NOT_IDENTIFIED")
    return login,password

def credentials_path(requested:str):
    if requested:return Path(requested).expanduser()
    home=Path.home()
    for p in (
        home/"jamaica-site-monitor"/"private"/"bg_readonly_credentials.json",
        home/"jamaica-web-pwa"/"jamaica-site-monitor"/"private"/"bg_readonly_credentials.json",
        home/".local"/"share"/"jamaica-site-monitor"/"private"/"bg_readonly_credentials.json",
        home/".local"/"opt"/"jamaica-site-monitor"/"private"/"bg_readonly_credentials.json",
        home/".config"/"jamaica-site-monitor"/"private"/"bg_readonly_credentials.json",
    ):
        if p.is_file() and not p.is_symlink():return p
    raise SyncHold("CREDENTIALS_PATH_NOT_FOUND_USE_OPTION")

class ApiClient:
    def __init__(self,login,password):
        self.login=login
        self.password=password
        jar=http.cookiejar.CookieJar()
        self.opener=urllib.request.build_opener(urllib.request.HTTPCookieProcessor(jar))
    def call(self,url,post=None):
        if not url.startswith(BASE) and url!=AUTH:raise SyncHold("UNAPPROVED_DOMAIN")
        h={"Accept-Encoding":"gzip","Accept":"application/json",
           "User-Agent":"JAMAICA-Authorized-ReadOnly/1.0"}
        req=urllib.request.Request(url,data=post,headers=h)
        with self.opener.open(req,timeout=28) as response:
            raw=response.read(MAX_BYTES+1)
            if len(raw)>MAX_BYTES:raise SyncHold("OPERATOR_RESPONSE_TOO_LARGE")
            if response.headers.get("Content-Encoding","").lower()=="gzip":
                raw=gzip.decompress(raw)
            if len(raw)>MAX_BYTES*5:raise SyncHold("DECOMPRESSED_RESPONSE_TOO_LARGE")
            return raw
    def login_once(self):
        body=urllib.parse.urlencode({"login":self.login,"pwd":self.password}).encode()
        self.call(AUTH,body)
        # CookieJar refreshes the rotating Z1 cookie automatically between requests.
    def get(self,url):
        try:return self.call(url)
        except urllib.error.HTTPError as err:
            if err.code not in (401,403):raise
            self.login_once()
            return self.call(url)

def date_iso(value):
    if not isinstance(value,str):return None
    for fmt in ("%d.%m.%Y","%Y-%m-%d"):
        try:return datetime.strptime(value.strip(),fmt).date()
        except ValueError:continue
    return None

def clean(value,maxlen=160):
    if not isinstance(value,str):return ""
    x=HTML_TAG_RE.sub(" ",html.unescape(value))
    x=NAME_RE.sub(" ",x).strip()[:maxlen]
    if any(ord(c)<32 or c in "<>{}" for c in x):return ""
    return x

def parse_entries(obj,country,cutoff,end):
    if not isinstance(obj,dict) or not isinstance(obj.get("entries"),list):
        raise SyncHold("OFFICIAL_PRICE_LIST_SCHEMA_UNKNOWN")
    rows=[]
    for item in obj["entries"]:
        if not isinstance(item,dict) or item.get("stop") is not None:continue
        dateval=date_iso(item.get("date"))
        if dateval is None or not (cutoff<=dateval<=end):continue
        route=clean(item.get("route"),160)
        id_price=str(item.get("id_price",""))
        if not route or not re.fullmatch(r"\d{7,22}",id_price):continue
        duration_text=str(item.get("duration",""))
        nights=sorted({int(x) for x in re.findall(r"\d+",duration_text) if 3<=int(x)<=SCOPE_DAYS})
        if not nights:continue
        key="|".join((country["id"],id_price,dateval.isoformat(),",".join(map(str,nights))))
        rows.append({
          "id":"r_"+hashlib.sha256(key.encode()).hexdigest()[:24],
          "country":country["name"],"origin":"Иркутск",
          "date":dateval.isoformat(),"nights":nights,
          "route":route,"status":"PRICE_LIST_REFERENCE_ONLY",
          "quote_verified":False,"availability_verified":False,"bookable":False
        })
    return rows

def build(directory,api):
    if directory.get("schema")!="jamaica.destination-directory.v1":
        raise SyncHold("DIRECTORY_SCHEMA_UNKNOWN")
    countries=[c for c in directory.get("countries",[])
         if c.get("has_tour_catalog") and CITY_ID in c.get("origins",[])]
    if not countries or len(countries)>80:raise SyncHold("IRKUTSK_SCOPE_INVALID")
    today=datetime.now(timezone.utc).date()
    end=today+timedelta(days=SCOPE_DAYS)
    all_rows=[];statuses=[];ids=set()
    for c in countries:
        q=urllib.parse.urlencode({"action":"files","flt":c["id"],"flt2":CITY_ID,"xml":"11"})
        try:
            obj=json.loads(api.get(BASE+"?"+q))
            rows=parse_entries(obj,c,today,end)
            statuses.append({"country":c["name"],"status":"CHECKED","routes":len(rows)})
            for r in rows:
                if r["id"] not in ids:
                    all_rows.append(r);ids.add(r["id"])
        except (SyncHold,urllib.error.HTTPError,urllib.error.URLError,ValueError,TimeoutError) as error:
            statuses.append({"country":c["name"],"status":"UNVERIFIED","routes":0})
        if len(all_rows)>MAX_ITEMS:raise SyncHold("ROUTE_LIMIT_REACHED")
        time.sleep(TIMING_SECONDS)
    if not any(s["status"]=="CHECKED" for s in statuses):
        raise SyncHold("ALL_OFFICIAL_PRICE_LISTS_FAILED_CHECK_AUTH")
    all_rows.sort(key=lambda r:(r["date"],r["country"],r["route"]))
    return {"schema":"jamaica.route-discovery.v1",
            "refreshed_at_utc":datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "classification":"PRICE_LIST_REFERENCES_NOT_BOOKABLE",
            "origin":"Иркутск","countries_checked":len(countries),
            "countries_success":sum(s["status"]=="CHECKED" for s in statuses),
            "countries_status":statuses,"routes":all_rows,
            "quote_verified":False,"availability_verified":False,
            "bookable":False}

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--directory",required=True)
    parser.add_argument("--output",required=True)
    parser.add_argument("--credentials",default="")
    args=parser.parse_args()
    country_directory=json.loads(Path(args.directory).read_text(encoding="utf-8"))
    login,password=read_secret(credentials_path(args.credentials))
    result=build(country_directory,ApiClient(login,password))
    dest=Path(args.output)
    if dest.is_symlink():raise SyncHold("OUTPUT_SYMLINK")
    dest.parent.mkdir(parents=True,exist_ok=True)
    tmp=dest.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(result,ensure_ascii=False,separators=(",",":"))+"\n",encoding="utf-8")
    tmp.chmod(0o600)
    tmp.replace(dest)
    print("JAMAICA_AUTHENTICATED_ROUTE_DISCOVERY_PASS")
    print("COUNTRIES_CHECKED="+str(result["countries_checked"]))
    print("COUNTRIES_SUCCESS="+str(result["countries_success"]))
    print("PRICE_LIST_ROUTES="+str(len(result["routes"])))
    print("AUTH_CREDENTIALS_REMAIN_ON_ORACLE=YES")
    print("NO_PRICE_NO_BOOKING_NO_SECRET_EXPORTED=YES")
    return 0

if __name__=="__main__":
    try:sys.exit(main())
    except Exception as exc:
        print("JAMAICA_ROUTE_SYNC_HOLD="+type(exc).__name__+":"+str(exc)[:90],file=sys.stderr)
        sys.exit(2)
