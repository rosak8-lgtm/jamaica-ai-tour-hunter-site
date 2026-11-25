"""Local owner console for the existing inquiry store. No HTTP or messaging.
No contact disclosure in summary/list; explicit single-ticket inspection only.
The legal controller must configure the same retention as the private API.
"""
import argparse
import json
import os
import re
import sqlite3
import stat
import sys
from contextlib import contextmanager
from datetime import datetime,timezone
from pathlib import Path
from backend.customer_inquiry_store import safe_directory, InquiryError

TICKET=re.compile(r"j_[a-f0-9]{32}\Z")

@contextmanager
def read_db(path):
    path=Path(path)
    safe_directory(path.parent)
    info=path.lstat()
    if (not stat.S_ISREG(info.st_mode) or info.st_uid!=os.geteuid() or
        stat.S_IMODE(info.st_mode)!=0o600 or info.st_nlink!=1):
        raise InquiryError("PRIVATE_DB_REQUIRED")
    db=sqlite3.connect(path.as_uri()+"?mode=ro",uri=True,timeout=5)
    try:
        db.execute("PRAGMA query_only=ON")
        yield db
    finally:db.close()

def cutoff(retention_days,now):
    if type(retention_days) is not int or not 1<=retention_days<=90 or now.tzinfo is None:
        raise InquiryError("RETENTION_REQUIRED")
    return int(now.timestamp())-retention_days*86400

def summarize(path,retention_days,now,limit=50):
    if type(limit) is not int or not 1<=limit<=200:raise InquiryError("LIMIT")
    after=cutoff(retention_days,now)
    with read_db(path) as db:
        total=db.execute("SELECT COUNT(*) FROM inquiries WHERE created>=?",(after,)).fetchone()[0]
        rows=db.execute("SELECT ticket,created,itinerary FROM inquiries WHERE created>=? ORDER BY created DESC,ticket LIMIT ?",(after,limit)).fetchall()
    entries=[]
    for ticket,created,itinerary in rows:
        row=json.loads(itinerary)
        entries.append({"ticket":ticket,"received_at_utc":datetime.fromtimestamp(created,timezone.utc).isoformat(),
                        "country":row["country"],"origin":row["origin"],"depart_date":row["depart_date"],"nights":row["nights"]})
    return {"classification":"INQUIRIES_NOT_BOOKINGS","retained_count":total,"entries":entries}

def inspect_ticket(path,retention_days,now,ticket):
    if not isinstance(ticket,str) or not TICKET.fullmatch(ticket):raise InquiryError("INVALID_TICKET")
    with read_db(path) as db:
        row=db.execute("SELECT created,payload,itinerary FROM inquiries WHERE ticket=? AND created>=?",(ticket,cutoff(retention_days,now))).fetchone()
    if row is None:raise InquiryError("TICKET_NOT_FOUND_OR_EXPIRED")
    created,payload,itinerary=row
    p=json.loads(payload)
    return {"classification":"PRIVATE_CUSTOMER_INQUIRY_NOT_BOOKING","ticket":ticket,
            "received_at_utc":datetime.fromtimestamp(created,timezone.utc).isoformat(),
            "contact":p["contact"],"rooms":p["rooms"],"consent":p["consent"],
            "policy_version":p["policy_version"],"itinerary":json.loads(itinerary)}

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--db",required=True,type=Path)
    p.add_argument("--retention-days",required=True,type=int)
    p.add_argument("--limit",type=int,default=50)
    p.add_argument("--ticket")
    a=p.parse_args()
    if os.getenv("JAMAICA_INQUIRY_LEGAL_APPROVED")!="yes":raise SystemExit("LEGAL_APPROVAL_REQUIRED")
    if a.ticket and not sys.stdout.isatty():raise SystemExit("PRIVATE_TERMINAL_REQUIRED")
    now=datetime.now(timezone.utc)
    try:
        result=inspect_ticket(a.db,a.retention_days,now,a.ticket) if a.ticket else summarize(a.db,a.retention_days,now,a.limit)
        print(json.dumps(result,ensure_ascii=False,indent=2))
    except (InquiryError,OSError,sqlite3.Error,ValueError,KeyError):
        raise SystemExit("INQUIRY_OWNER_HOLD")
if __name__=="__main__":main()
