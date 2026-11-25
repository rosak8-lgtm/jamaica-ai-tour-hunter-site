"""Private JAMAICA inquiry queue, not a quote, reservation or payment.

Deploy only after legal controller, retention, consent and hosting are
approved. No supplier calls. Contacts never enter GitHub or public feeds.
The trusted server must inject a locally verified offer resolver.
"""
import hashlib
import hmac
import json
import os
import re
import secrets
import sqlite3
import stat
from contextlib import contextmanager
from datetime import datetime, timezone, timedelta
from pathlib import Path

ID=re.compile(r"(?:p|pg)_[a-f0-9]{24}")
TOKEN=re.compile(r"[a-f0-9]{32}")
VERSION=re.compile(r"[A-Za-z0-9._-]{1,64}")

class InquiryError(ValueError):pass

def canonical(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(",",":"))

def normalized(body,policy_version):
    if not isinstance(body,dict) or set(body)!={"request_id","preview_id","rooms","contact","consent","policy_version"}:
        raise InquiryError("INVALID_REQUEST")
    if body["consent"] is not True or body["policy_version"]!=policy_version:
        raise InquiryError("CONSENT_REQUIRED")
    if not isinstance(body["request_id"],str) or not TOKEN.fullmatch(body["request_id"]):
        raise InquiryError("INVALID_REQUEST_ID")
    if not isinstance(body["preview_id"],str) or not ID.fullmatch(body["preview_id"]):
        raise InquiryError("INVALID_PREVIEW")
    rooms=body["rooms"]
    if not isinstance(rooms,list) or not 1<=len(rooms)<=5:raise InquiryError("INVALID_PARTY")
    for r in rooms:
        if not isinstance(r,dict) or set(r)!={"adults","child_ages"}:raise InquiryError("INVALID_PARTY")
        if type(r["adults"]) is not int or not 1<=r["adults"]<=12 or not isinstance(r["child_ages"],list) or len(r["child_ages"])>10:
            raise InquiryError("INVALID_PARTY")
        if any(type(a) is not int or not 0<=a<=17 for a in r["child_ages"]):raise InquiryError("INVALID_PARTY")
    if sum(r["adults"] for r in rooms)>12 or sum(len(r["child_ages"]) for r in rooms)>10:
        raise InquiryError("INVALID_PARTY")
    c=body["contact"]
    if not isinstance(c,dict) or set(c)!={"kind","value"} or not isinstance(c["value"],str):raise InquiryError("INVALID_CONTACT")
    value=c["value"].strip()
    if c["kind"]=="phone":
        value=re.sub(r"[ ()-]","",value)
        if not re.fullmatch(r"\+[1-9][0-9]{7,14}",value):raise InquiryError("INVALID_CONTACT")
    elif c["kind"]=="email":
        if len(value)>254 or not re.fullmatch(r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]{1,64}@[A-Za-z0-9.-]+\.[A-Za-z]{2,63}",value):raise InquiryError("INVALID_CONTACT")
        local,domain=value.rsplit("@",1)
        if ".." in value or local.startswith(".") or local.endswith(".") or any(not re.fullmatch(r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?",part) for part in domain.split(".")):
            raise InquiryError("INVALID_CONTACT")
        value=local+"@"+domain.lower()
    else:raise InquiryError("INVALID_CONTACT")
    return {**body,"contact":{"kind":c["kind"],"value":value}}

def safe_directory(path):
    path=Path(path)
    if not path.is_absolute() or path.resolve()!=path:raise InquiryError("PRIVATE_PATH_REQUIRED")
    info=path.stat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o700:
        raise InquiryError("PRIVATE_DIRECTORY_REQUIRED")
    return path

class InquiryStore:
    def __init__(self,db_path,secret,policy_version,resolver,*,retention_days=30):
        if not isinstance(secret,bytes) or len(secret)<32 or not isinstance(policy_version,str) or not VERSION.fullmatch(policy_version) or not callable(resolver) or type(retention_days) is not int or not 1<=retention_days<=90:
            raise InquiryError("CONFIG_REQUIRED")
        self.path=Path(db_path)
        safe_directory(self.path.parent)
        fd=os.open(self.path,os.O_RDWR|os.O_CREAT|os.O_NOFOLLOW|os.O_NONBLOCK,0o600)
        try:
            info=os.fstat(fd)
            if not stat.S_ISREG(info.st_mode) or info.st_uid!=os.getuid() or stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1:
                raise InquiryError("PRIVATE_DB_REQUIRED")
        finally:os.close(fd)
        self.secret=secret;self.policy_version=policy_version;self.resolve=resolver;self.retention=retention_days*86400
        with self.db() as db:
            db.execute("CREATE TABLE IF NOT EXISTS inquiries(ticket TEXT PRIMARY KEY, request_id TEXT UNIQUE NOT NULL, digest TEXT NOT NULL, actor TEXT NOT NULL, contact_digest TEXT NOT NULL, created INTEGER NOT NULL, payload TEXT NOT NULL, itinerary TEXT NOT NULL)")
            db.execute("CREATE INDEX IF NOT EXISTS inquiries_created ON inquiries(created)")
    @contextmanager
    def db(self):
        db=sqlite3.connect(self.path,timeout=5)
        try:
            db.execute("PRAGMA secure_delete=ON")
            with db:yield db
        finally:db.close()
    def digest(self,v):
        return hmac.new(self.secret,v.encode("utf-8"),hashlib.sha256).hexdigest()
    def purge(self,now=None):
        clock=now or datetime.now(timezone.utc)
        if clock.tzinfo is None:raise InquiryError("CLOCK_REQUIRED")
        with self.db() as db:
            return db.execute("DELETE FROM inquiries WHERE created<?",(int(clock.timestamp())-self.retention,)).rowcount
    def submit(self,body,actor,now=None):
        clock=now or datetime.now(timezone.utc)
        if clock.tzinfo is None or not isinstance(actor,str) or not 1<=len(actor)<=128:raise InquiryError("INVALID_ACTOR")
        ts=int(clock.timestamp());b=normalized(body,self.policy_version)
        digest=self.digest(canonical(b));key=self.digest("actor:"+actor);contact=self.digest("contact:"+canonical(b["contact"]))
        with self.db() as db:
            db.execute("BEGIN IMMEDIATE")
            db.execute("DELETE FROM inquiries WHERE created<?",(ts-self.retention,))
            prior=db.execute("SELECT ticket,digest FROM inquiries WHERE request_id=?",(b["request_id"],)).fetchone()
            if prior:
                if not hmac.compare_digest(prior[1],digest):raise InquiryError("REQUEST_CONFLICT")
                return {"status":"INQUIRY_RECEIVED","ticket":prior[0],"booked":False,"payment_required":False}
            if db.execute("SELECT COUNT(*) FROM inquiries WHERE created>=? AND (actor=? OR contact_digest=?)",(ts-3600,key,contact)).fetchone()[0]>=5:
                raise InquiryError("RATE_LIMIT")
            if db.execute("SELECT COUNT(*) FROM inquiries WHERE created>=?",(ts-3600,)).fetchone()[0]>=200:
                raise InquiryError("RATE_LIMIT")
            itinerary=self.resolve(b["preview_id"],clock)
            if not isinstance(itinerary,dict) or itinerary.get("id")!=b["preview_id"]:raise InquiryError("TOUR_NOT_CURRENT")
            # Store only the exact normalized, trusted itinerary. Never client-supplied prices.
            allowed=("id","origin","country","hotel","room","depart_date","nights")
            if any(k not in itinerary for k in allowed):raise InquiryError("TOUR_NOT_CURRENT")
            ticket="j_"+secrets.token_hex(16)
            db.execute("INSERT INTO inquiries VALUES(?,?,?,?,?,?,?,?)",(ticket,b["request_id"],digest,key,contact,ts,canonical(b),canonical({k:itinerary[k] for k in allowed})))
        return {"status":"INQUIRY_RECEIVED","ticket":ticket,"booked":False,"payment_required":False}
