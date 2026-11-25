"""V55 trusted local catalog resolver. No network requests.

The owner-controlled publisher checkout is the trust boundary. Never
accept paths, proof fields or prices from an inquiry body. No booking.
"""
import hashlib
import json
import os
import re
import stat
from datetime import datetime, timezone
from pathlib import Path
from backend.customer_inquiry_store import ID

def read(path,limit):
    fd=os.open(path,os.O_RDONLY|os.O_NOFOLLOW|os.O_NONBLOCK)
    try:
        st=os.fstat(fd)
        if not stat.S_ISREG(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode&0o022 or st.st_nlink!=1 or st.st_size>limit:raise ValueError("UNSAFE_FILE")
        with os.fdopen(fd,"rb",closefd=False) as f:raw=f.read(limit+1)
        if len(raw)>limit:raise ValueError("FILE_LIMIT")
        return json.loads(raw),hashlib.sha256(raw).hexdigest()
    finally:os.close(fd)

def fresh(value,now):
    try:
        if not isinstance(value,str):return False
        stamp=datetime.fromisoformat(value.replace("Z","+00:00"))
        return stamp.tzinfo is not None and -30<=(now-stamp).total_seconds()<=900
    except (ValueError,TypeError):return False

def safe_row(row,pid,now):
    if not isinstance(row,dict) or row.get("id")!=pid:return False
    if any(row.get(k) is not False for k in ("bookable","quote_verified","availability_verified","flight_verified")):return False
    if any(not isinstance(row.get(k),str) or not 1<=len(row[k])<=200 or any(ord(c)<32 or c in "<>{}" for c in row[k]) for k in ("origin","country","hotel","room")):return False
    if type(row.get("nights")) is not int or not 3<=row["nights"]<=180:return False
    try:
        day=datetime.strptime(row["depart_date"],"%Y-%m-%d").date()
        return day.isoformat()==row["depart_date"] and day>now.astimezone(timezone.utc).date()
    except (KeyError,ValueError,TypeError):return False

def select(rows,pid,now):
    if not isinstance(rows,list):return None
    matches=[r for r in rows if isinstance(r,dict) and r.get("id")==pid]
    return matches[0] if len(matches)==1 and safe_row(matches[0],pid,now) else None

class LocalCatalog:
    def __init__(self,root):
        self.root=Path(root)
        self.directory(self.root)
    @staticmethod
    def directory(path):
        if not path.is_absolute() or path.resolve()!=path:raise ValueError("UNSAFE_CATALOG")
        st=path.stat()
        if not stat.S_ISDIR(st.st_mode) or st.st_uid!=os.getuid() or st.st_mode&0o022:raise ValueError("UNSAFE_CATALOG")
    def __call__(self,pid,now):
        if not isinstance(pid,str) or not ID.fullmatch(pid) or now.tzinfo is None:return None
        try:
            self.directory(self.root)
            return self.second(pid,now) if pid.startswith("pg_") else self.first(pid,now)
        except (OSError,ValueError,TypeError,KeyError,AttributeError,OverflowError):return None
    def second(self,pid,now):
        feed,_=read(self.root/"application-reference.json",12*1024*1024)
        if feed.get("schema")!="jamaica.pegas-reference-catalog.v1" or feed.get("bookable") is not False or feed.get("quote_verified") is not False or not fresh(feed.get("refreshed_at_utc"),now):return None
        rows=feed.get("previews")
        if not isinstance(rows,list) or len(rows)>5000:return None
        row=select(rows,pid,now)
        if not row or row.get("status")!="PEGAS_APPLICATION_PRICE_REFERENCE_ONLY" or row.get("price_source")!="PEGAS_OPEN_APPLICATION_MANDATORY_FEES_INCLUDED" or row.get("price_reference_party")!="TWO_ADULTS":return None
        if row["country"]=="Вьетнам" and row["nights"] in (45,60):return None
        if type(row.get("price_reference_rub")) is not int or not 0<row["price_reference_rub"]<=10000000:return None
        e=row.get("evidence")
        if not isinstance(e,dict) or not all(e.get(k) is True for k in ("hotel_filter_verified","flight_filter_verified","cheapest_eligible_price_clicked","final_price_observed","mandatory_fees_included")):return None
        if not fresh(e.get("observed_at_utc"),now) or e["observed_at_utc"]!=row.get("price_observed_at_utc"):return None
        if datetime.fromisoformat(e["observed_at_utc"].replace("Z","+00:00")).timestamp()>datetime.fromisoformat(feed["refreshed_at_utc"].replace("Z","+00:00")).timestamp()+30:return None
        return row
    def first(self,pid,now):
        proof,_=read(self.root/"tour-visual-evidence.json",5*1024*1024)
        if set(proof)!={"schema","bookable","quote_verified","availability_verified","entries"} or proof["schema"]!="jamaica.visual-selection.v1" or any(proof[k] is not False for k in ("bookable","quote_verified","availability_verified")):return None
        entries=proof["entries"]
        if not isinstance(entries,list) or len(entries)>10000:return None
        seen=set();observed=None
        for p in entries:
            if not isinstance(p,dict) or set(p)!={"preview_id","route_best_price_seen","both_green_planes_seen","observed_at_utc"} or not isinstance(p["preview_id"],str) or not re.fullmatch(r"p_[a-f0-9]{24}",p["preview_id"]) or p["preview_id"] in seen or p["route_best_price_seen"] is not True or p["both_green_planes_seen"] is not True:return None
            seen.add(p["preview_id"])
            if p["preview_id"]==pid:observed=p["observed_at_utc"]
        if not fresh(observed,now):return None
        feed,_=read(self.root/"tour-previews.json",24*1024*1024)
        if feed.get("schema")!="jamaica.tour-previews.v1" or any(feed.get(k) is not False for k in ("bookable","quote_verified","availability_verified")):return None
        rows=feed.get("previews")
        if not isinstance(rows,list) or len(rows)>8000:return None
        parts=feed.get("shards",[])
        if not isinstance(parts,list) or len(parts)>13:return None
        total=len(rows)
        if parts:self.directory(self.root/"tour-previews-shards")
        matches=[r for r in rows if isinstance(r,dict) and r.get("id")==pid]
        for i,p in enumerate(parts,1):
            expected=f"tour-previews-shards/part-{i:03}.json"
            if not isinstance(p,dict) or p.get("path")!=expected or type(p.get("count")) is not int or not 1<=p["count"]<=4000:return None
            shard,digest=read(self.root/expected,16*1024*1024)
            if digest!=p.get("sha256") or shard.get("schema")!="jamaica.tour-preview-shard.v1" or shard.get("refreshed_at_utc")!=feed.get("refreshed_at_utc") or any(shard.get(k) is not False for k in ("bookable","quote_verified","availability_verified")):return None
            sub=shard.get("previews")
            if not isinstance(sub,list) or len(sub)!=p["count"]:return None
            total+=len(sub);matches.extend(r for r in sub if isinstance(r,dict) and r.get("id")==pid)
        if total>60000 or total!=feed.get("total_published_previews"):return None
        row=select(matches,pid,now)
        if not row or row.get("status")!="REFERENCE_PRICE_LIST_ONLY" or row.get("price_source")!="BG_EXACT_SELECTED_GREEN_BROWSER" or row.get("price_reference_party")!="TWO_ADULTS" or row.get("price_observed_at_utc")!=observed:return None
        if type(row.get("price_reference_rub")) is not int or row["price_reference_rub"]<=0:return None
        return row
