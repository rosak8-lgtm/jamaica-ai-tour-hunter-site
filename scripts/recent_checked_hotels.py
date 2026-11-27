"""Previously checked hotel/room price references, never live offers.
Only the final strict public projection can contribute new records.
No supplier I/O, no private identifiers, no refreshed proof timestamps.
"""
from datetime import timedelta
import json
import re
from collections import defaultdict
from recent_checked_dates import instant,valid_group

FILENAME="recent-checked-hotels.json"
SCHEMA="jamaica.recent-checked-hotels.v1"
CLASSIFICATION="HISTORICAL_HOTELS_NOT_OFFERS"
MAX_ROWS=20000
MAX_BYTES=8_000_000
FIELDS={"id","hotel_id","hotel","origin","country","date","nights","room","resort","observed_at_utc","last_price_rub"}

def safe_text(value,limit,empty=False):
    return isinstance(value,str) and (empty or bool(value.strip())) and len(value)<=limit and not any(ord(c)<32 or c in "<>{}" for c in value)

def group(row):
    return (row["origin"],row["country"],row["date"],row["nights"])

def valid(row,now,hotels):
    if not isinstance(row,dict) or set(row)!=FIELDS:return False
    if not isinstance(row["id"],str) or not re.fullmatch(r"p_[0-9a-f]{24}",row["id"]):return False
    if not isinstance(row["hotel_id"],str) or not re.fullmatch(r"[0-9]{7,20}",row["hotel_id"]):return False
    if not all(safe_text(row[k],limit,k=="resort") for k,limit in (("hotel",110),("room",300),("resort",100))):return False
    if hotels.get(row["hotel_id"])!=(row["hotel"],row["country"]):return False
    return valid_group({k:row[k] for k in ("origin","country","date","nights","observed_at_utc")}|
        {"count":1,"last_min_rub":row["last_price_rub"]},now)

def build(previous,rows,visual,hotels,*,now):
    old={}
    if isinstance(previous,dict) and previous.get("schema")==SCHEMA and previous.get("classification")==CLASSIFICATION and isinstance(previous.get("rows"),list) and len(previous["rows"])<=MAX_ROWS:
        for row in previous["rows"]:
            if valid(row,now,hotels):
                key=row["id"]
                if key not in old or instant(row["observed_at_utc"])>instant(old[key]["observed_at_utc"]):
                    old[key]=dict(row)
    proof={}
    for p in visual.get("entries",[]):
        if isinstance(p,dict) and p.get("route_best_price_seen") is True and p.get("both_green_planes_seen") is True and isinstance(p.get("preview_id"),str):
            proof[p["preview_id"]]=p.get("observed_at_utc")
    current={}
    newest={}
    for r in rows:
        if not isinstance(r,dict):continue
        at=r.get("price_observed_at_utc")
        t=instant(at)
        uid=r.get("id")
        if (not isinstance(uid,str) or t is None or not -timedelta(seconds=30)<=now-t<=timedelta(minutes=15)
                or proof.get(uid)!=at or r.get("status")!="REFERENCE_PRICE_LIST_ONLY"
                or r.get("price_source")!="BG_EXACT_SELECTED_GREEN_BROWSER" or r.get("price_reference_party")!="TWO_ADULTS"
                or any(r.get(k) is not False for k in ("bookable","quote_verified","availability_verified","flight_verified"))):
            continue
        record={k:r.get(k) for k in ("id","hotel_id","hotel","origin","country","nights","room","resort")}
        record.update(date=r.get("depart_date"),observed_at_utc=at,last_price_rub=r.get("price_reference_rub"))
        if not valid(record,now,hotels):continue
        if uid not in current or t>instant(current[uid]["observed_at_utc"]):current[uid]=record
        k=group(record)
        if k not in newest or t>newest[k]:newest[k]=t
    # When a newer batch is observed for the same route/day/nights, discard
    # its older batch instead of accumulating old rooms as if still available.
    merged={uid:r for uid,r in old.items() if group(r) not in newest or instant(r["observed_at_utc"])>=newest[group(r)]}
    for uid,r in current.items():
        t=instant(r["observed_at_utc"])
        if t==newest[group(r)] and (uid not in merged or t>=instant(merged[uid]["observed_at_utc"])):merged[uid]=r
    pools=defaultdict(list)
    for r in sorted(merged.values(),key=lambda x:(x["last_price_rub"],x["id"])):
        pools[group(r)].append(r)
    ordered=sorted(pools,key=lambda k:(max(instant(r["observed_at_utc"]) for r in pools[k]),k),reverse=True)
    out=[]
    used=256
    # Round-robin across date groups under a strict total bytes/rows bound.
    # Preserve broad date coverage rather than one huge price list.
    depth=0
    while ordered and len(out)<MAX_ROWS:
        remaining=[]
        for k in ordered:
            r=pools[k][depth]
            size=len(json.dumps(r,ensure_ascii=False,separators=(",",":")).encode("utf-8"))+1
            if used+size>MAX_BYTES or len(out)>=MAX_ROWS:
                return {"schema":SCHEMA,"classification":CLASSIFICATION,"rows":out}
            out.append(r);used+=size
            if depth+1<len(pools[k]):remaining.append(k)
        ordered=remaining;depth+=1
    return {"schema":SCHEMA,"classification":CLASSIFICATION,"rows":out}
