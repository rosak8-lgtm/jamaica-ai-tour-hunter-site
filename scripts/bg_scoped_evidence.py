"""Private city-specific BG evidence staging, V43. No supplier I/O or public writes.

Trusted browser callers only, after genuine selected-route observation.
One atomic receipt/price/identity bundle per scope. No legacy ledger mutation.
"""
from __future__ import annotations
from datetime import datetime,timezone,timedelta
import copy
import fcntl
import json
import os
import stat
import tempfile
from pathlib import Path
from scripts.bg_origin_scope import Scope, IRKUTSK_ID
from scripts.trusted_bot_receipt_sink import ROUTE_KEYS, FLIGHT_KEYS
from backend.bg_route_first_visual_gate import route_first_pair_matches

SCHEMA="jamaica.bg-scoped-evidence-staging.v1"
MAX_RECORDS=1000
MAX_BYTES=5_000_000
PREVIEW_KEYS=("id","origin","country","hotel_id","depart_date","nights","room","bookable","quote_verified")
PRICE_KEYS={"preview_id","source_price_list_id","browser_session_digest","observed_at_utc","price_total_rub"}

def instant(raw):
    try:
        t=datetime.fromisoformat(raw.replace("Z","+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (ValueError,TypeError,AttributeError):
        return None

def validated_registry_scope(registry,origin_id,country_id,now):
    if not isinstance(now,datetime) or now.tzinfo is None:raise ValueError("CLOCK_REQUIRED")
    if not isinstance(registry,dict) or registry.get("source")!="BG_FLTX":raise ValueError("REGISTRY_SOURCE")
    seen=instant(registry.get("observed_at_utc"))
    if seen is None or not -timedelta(minutes=1)<=now-seen<=timedelta(days=1):
        raise ValueError("REGISTRY_EXPIRED")
    scope=Scope.from_registry(registry,origin_id,country_id)
    if scope.origin_id==IRKUTSK_ID:raise ValueError("LEGACY_ORIGIN_USE_EXISTING_SINK")
    pair=next(p for p in registry["pairs"] if p.get("origin_id")==origin_id and p.get("country_id")==country_id)
    if type(pair.get("transport_indicator")) is not int or not 2<=pair["transport_indicator"]<=255:
        raise ValueError("REGISTRY_TRANSPORT")
    return scope

def build_record(scope,route,flight,preview,price,*,now):
    if not isinstance(scope,Scope) or scope.origin_id==IRKUTSK_ID:return None
    if not all(isinstance(x,dict) for x in (route,flight,preview,price)):return None
    if set(route)!=ROUTE_KEYS or set(flight)!=FLIGHT_KEYS|{"origin_city_id"} or set(price)!=PRICE_KEYS:return None
    if not route_first_pair_matches(route,flight,preview,now=now,origin_scope=scope):return None
    if (preview.get("availability_verified",False) is not False or
        preview.get("flight_verified",False) is not False or
        type(preview.get("nights")) is not int or not 3<=preview["nights"]<=180 or
        not isinstance(preview.get("room"),str) or not 1<=len(preview["room"])<=300):
        return None
    if (price["preview_id"]!=preview["id"] or
        price["source_price_list_id"]!=route["source_price_list_id"] or
        price["browser_session_digest"]!=route["browser_session_digest"] or
        price["observed_at_utc"]!=flight["flight_checked_at_utc"] or
        type(price["price_total_rub"]) is not int or not 1000<=price["price_total_rub"]<=10_000_000):
        return None
    # Store only the necessary preview identity; no passenger data or extras.
    return copy.deepcopy({"preview":{k:preview[k] for k in PREVIEW_KEYS},
                          "route":route,"flight":flight,"price":price})

def save_staged_batch(root,registry,origin_id,country_id,pairs,*,now):
    """Trusted browser-only atomic private stage; no legacy publication."""
    scope=validated_registry_scope(registry,origin_id,country_id,now)
    if not isinstance(pairs,(tuple,list)) or len(pairs)>MAX_RECORDS:
        raise ValueError("BATCH_SIZE")
    root=Path(root)
    if root.name!="private-bg-scoped-staging":raise ValueError("STAGING_DIRECTORY_REQUIRED")
    if root.resolve()==Path.home()/".local/share/jamaica-oracle-catalog":raise ValueError("LEGACY_DIRECTORY")
    st=root.lstat()
    if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode&0o077:
        raise ValueError("STAGING_DIRECTORY_UNSAFE")
    records={}
    for pair in pairs:
        if not isinstance(pair,(list,tuple)) or len(pair)!=4:continue
        record=build_record(scope,*pair,now=now)
        if record is not None:records[record["preview"]["id"]]=record
    if not records:return []
    path=root/(scope.origin_id+"-"+scope.country_id+".json")
    lock=path.with_suffix(".lock")
    fd=os.open(lock,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode&0o077 or st.st_nlink!=1:
            raise ValueError("STAGING_LOCK_UNSAFE")
        fcntl.flock(fd,fcntl.LOCK_EX|fcntl.LOCK_NB)
        accepted=list(records)
        # Read the existing scoped file, validate every old row again, retain
        # only fresh evidence. Never replace a corrupt or wrong-scope ledger.
        try:rfd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
        except FileNotFoundError:rfd=None
        if rfd is not None:
            with os.fdopen(rfd,"rb") as f:
                st=os.fstat(f.fileno())
                if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or st.st_mode&0o077 or st.st_nlink!=1 or not 2<=st.st_size<=MAX_BYTES:
                    raise ValueError("STAGING_LEDGER_UNSAFE")
                old=json.loads(f.read(MAX_BYTES+1))
            if (not isinstance(old,dict) or old.get("schema")!=SCHEMA or old.get("origin_id")!=origin_id or
                old.get("country_id")!=country_id or not isinstance(old.get("records"),list) or len(old["records"])>MAX_RECORDS):
                raise ValueError("STAGING_LEDGER_INVALID")
            for row in old["records"]:
                if not isinstance(row,dict) or set(row)!={"route","flight","preview","price"}:raise ValueError("STAGING_ROW_INVALID")
                p=row["preview"]
                if not isinstance(p,dict):raise ValueError("STAGING_ROW_INVALID")
                if p.get("id") in records:continue
                kept=build_record(scope,row["route"],row["flight"],p,row["price"],now=now)
                if kept is not None and len(records)<MAX_RECORDS:records[p["id"]]=kept
        data=json.dumps({"schema":SCHEMA,"origin_id":origin_id,"country_id":country_id,
                         "classification":"PRIVATE_ONLY_NOT_PUBLIC_OFFERS","records":list(records.values())},
                         ensure_ascii=False,separators=(",",":")).encode()
        if len(data)>MAX_BYTES:raise ValueError("STAGING_LEDGER_OVERSIZE")
        out,tmp=tempfile.mkstemp(prefix=".scope-",dir=root)
        try:
            with os.fdopen(out,"wb") as f:
                os.fchmod(f.fileno(),0o600);f.write(data);f.flush();os.fsync(f.fileno())
            os.replace(tmp,path)
        finally:
            if os.path.exists(tmp):os.unlink(tmp)
        return accepted
    finally:
        os.close(fd)
