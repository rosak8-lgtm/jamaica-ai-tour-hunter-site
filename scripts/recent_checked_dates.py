"""Adaptive 30/120-minute history of actually verified BG date groups, not live inventory.
No supplier I/O, no renewal of proof timestamps, no booking permission.
"""
from datetime import datetime, timezone, timedelta
import re

SCHEMA="jamaica.recent-checked-dates.v1"
FILENAME="recent-checked-dates.json"
MAX_GROUPS=2000
WINDOW=timedelta(hours=2)
URGENT_WINDOW=timedelta(minutes=30)
URGENT_DAYS=7
KEYS={"origin","country","date","nights","observed_at_utc","count","last_min_rub"}
def instant(value):
    try:
        t=datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (ValueError,AttributeError,TypeError):
        return None

def group_key(g):
    return (g["origin"],g["country"],g["date"],g["nights"])

def valid_group(g,now):
    if not isinstance(g,dict) or set(g)!=KEYS:return False
    for k in ("origin","country"):
        v=g[k]
        if not isinstance(v,str) or not 2<=len(v)<=100 or v!=v.strip() or any(ord(c)<32 or c in "<>" for c in v):return False
    try:
        if not re.fullmatch(r"20\d{2}-\d{2}-\d{2}",g["date"]):return False
        day=datetime.strptime(g["date"],"%Y-%m-%d").date()
    except (ValueError,TypeError):return False
    at=instant(g["observed_at_utc"])
    return (now.date()<=day<=now.date()+timedelta(days=730) and at is not None
        and -timedelta(seconds=30)<=now-at<=(URGENT_WINDOW if (day-now.date()).days<=URGENT_DAYS else WINDOW)
        and type(g["nights"]) is int and 3<=g["nights"]<=180
        and type(g["count"]) is int and 1<=g["count"]<=10000
        and type(g["last_min_rub"]) is int and 1000<=g["last_min_rub"]<=10_000_000)

def build(previous,rows,visual_feed,*,now):
    """Only accept fresh exact same-observation two-adult prices; retain groups
    for 30 minutes for departures within 7 days, otherwise 120 minutes from original observation. A new batch replaces a group's
    older observation rather than summing old and new counts.
    """
    merged={}
    if isinstance(previous,dict) and previous.get("schema")==SCHEMA and previous.get("classification")=="HISTORICAL_SEARCH_ONLY_NOT_OFFERS" and isinstance(previous.get("groups"),list) and len(previous["groups"])<=MAX_GROUPS:
        for g in previous["groups"]:
            if valid_group(g,now):
                k=group_key(g)
                if k not in merged or instant(g["observed_at_utc"])>instant(merged[k]["observed_at_utc"]):
                    merged[k]=dict(g)
    proofs={}
    if isinstance(visual_feed,dict):
        for p in visual_feed.get("entries",[]):
            if isinstance(p,dict) and p.get("route_best_price_seen") is True and p.get("both_green_planes_seen") is True:
                proofs[p.get("preview_id")]=p.get("observed_at_utc")
    batches={}
    seen=set()
    for r in rows:
        if not isinstance(r,dict):continue
        pid=r.get("id")
        at=r.get("price_observed_at_utc")
        stamp=instant(at)
        if (not isinstance(pid,str) or not re.fullmatch(r"p_[0-9a-f]{24}",pid) or pid in seen or
            stamp is None or not -timedelta(seconds=30)<=now-stamp<=timedelta(minutes=15) or
            proofs.get(pid)!=at or r.get("status")!="REFERENCE_PRICE_LIST_ONLY" or
            any(r.get(k) is not False for k in ("bookable","quote_verified","availability_verified","flight_verified")) or
            r.get("price_source")!="BG_EXACT_SELECTED_GREEN_BROWSER" or r.get("price_reference_party")!="TWO_ADULTS"):
            continue
        g={"origin":r.get("origin"),"country":r.get("country"),"date":r.get("depart_date"),
           "nights":r.get("nights"),"observed_at_utc":at,"count":1,"last_min_rub":r.get("price_reference_rub")}
        if not valid_group(g,now):continue
        seen.add(pid)
        key=(*group_key(g),stamp)
        if key not in batches:batches[key]=g
        else:
            b=batches[key]
            b["count"]=min(10000,b["count"]+1)
            b["last_min_rub"]=min(b["last_min_rub"],g["last_min_rub"])
    for g in batches.values():
        k=group_key(g)
        if k not in merged or instant(g["observed_at_utc"])>=instant(merged[k]["observed_at_utc"]):
            merged[k]=g
    groups=sorted(merged.values(),key=lambda g:(instant(g["observed_at_utc"]),group_key(g)),reverse=True)[:MAX_GROUPS]
    return {"schema":SCHEMA,"classification":"HISTORICAL_SEARCH_ONLY_NOT_OFFERS","groups":groups}
