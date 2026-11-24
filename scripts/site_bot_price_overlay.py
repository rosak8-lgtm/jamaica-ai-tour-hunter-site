"""Exact same-session DOM price overlay for independently verified BG site tours.

A price-list amount is NOT the browser-observed total. Only an owner-only 0600
ledger emitted by the separate website browser after a genuine SAME-ROUTE
best-price click + both green flights may update a public card. Proof matches
must be *exact* by preview_id, source price-list ID, browser session hash,
flight timestamp, and max 15 minutes age. Anything missing -> no price.
"""
from __future__ import annotations

from datetime import datetime,timezone
import json,os,stat,re
from pathlib import Path

SCHEMA="jamaica.bg-site-dom-prices.v1"
MAX_RECORDS=2000
MAX_BYTES=1000000
IDENT=re.compile(r"^p_[0-9a-f]{24}$")
SOURCE=re.compile(r"^\d{7,25}$")
SESSION=re.compile(r"^[0-9a-f]{64}$")

def _instant(raw):
    if not isinstance(raw,str):return None
    try:
        t=datetime.fromisoformat(raw.replace("Z","+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except ValueError:return None

def read_ledger(path:Path):
    """O_NOFOLLOW and owner-only. Fail closed if unreadable/corrupt."""
    path=Path(path)
    flags=os.O_RDONLY|getattr(os,"O_NOFOLLOW",0)
    try:fd=os.open(path,flags)
    except FileNotFoundError:return None
    try:
        st=os.fstat(fd)
        if (not stat.S_ISREG(st.st_mode) or st.st_uid!=os.geteuid() or
            stat.S_IMODE(st.st_mode)&0o077 or not 2<=st.st_size<=MAX_BYTES):
            raise ValueError("PRIVATE_PRICE_LEDGER_NOT_OWNER_ONLY")
        content=os.read(fd,MAX_BYTES+1)
    finally:os.close(fd)
    if len(content)>MAX_BYTES:raise ValueError("PRIVATE_PRICE_LEDGER_TOO_LARGE")
    try:ledger=json.loads(content)
    except (UnicodeError,ValueError):
        raise ValueError("PRIVATE_PRICE_LEDGER_INVALID_JSON") from None
    if (not isinstance(ledger,dict) or set(ledger)!={"schema","records"} or
        ledger["schema"]!=SCHEMA or not isinstance(ledger["records"],list) or
        len(ledger["records"])>MAX_RECORDS):
        raise ValueError("PRIVATE_PRICE_LEDGER_INVALID_SCHEMA")
    return ledger

def apply(public_feed, private_receipts, visual_public, ledger, *, now=None):
    """Return filtered cards with fresh actual BG *two-adult* DOM totals.

    There is no amount if the independent site bot did not prove price in
    the selected green flight row. Never fall back to stale XML/API amount
    on a visual-gated tour. Original source feed is unchanged.
    """
    now=now or datetime.now(timezone.utc)
    if not isinstance(now,datetime) or not now.tzinfo:
        raise ValueError("CLOCK_REQUIRED")
    now=now.astimezone(timezone.utc)
    proofs={}
    if isinstance(private_receipts,dict):
        for record in private_receipts.get("records",[]):
            if not isinstance(record,dict) or set(record)!={"preview_id","route","flight"}:
                continue
            id=record["preview_id"]
            if isinstance(id,str) and IDENT.fullmatch(id):
                proofs[id]=record
    public_ids={}
    if isinstance(visual_public,dict):
        for proof in visual_public.get("entries",[]):
            if isinstance(proof,dict) and proof.get("route_best_price_seen") is True and proof.get("both_green_planes_seen") is True:
                public_ids[proof.get("preview_id")]=proof.get("observed_at_utc")
    prices={}
    if isinstance(ledger,dict) and ledger.get("schema")==SCHEMA and isinstance(ledger.get("records"),list):
        for record in ledger["records"][:MAX_RECORDS]:
            if not isinstance(record,dict) or set(record)!={
                "preview_id","source_price_list_id","browser_session_digest",
                "observed_at_utc","price_total_rub"}:continue
            ident=record["preview_id"];source=record["source_price_list_id"];session=record["browser_session_digest"]
            amount=record["price_total_rub"];when=record["observed_at_utc"]
            if (not isinstance(ident,str) or not IDENT.fullmatch(ident) or
                not isinstance(source,str) or not SOURCE.fullmatch(source) or
                not isinstance(session,str) or not SESSION.fullmatch(session) or
                type(amount) is not int or not 1000<=amount<=10000000 or
                when!=public_ids.get(ident)):continue
            checked=_instant(when)
            if checked is None or not -30<=(now-checked).total_seconds()<=15*60:
                continue
            receipt=proofs.get(ident)
            if not receipt or not isinstance(receipt.get("route"),dict) or not isinstance(receipt.get("flight"),dict):
                continue
            route,flight=receipt["route"],receipt["flight"]
            if not (route.get("source_price_list_id")==source==
                    flight.get("source_price_list_id") and
                    route.get("browser_session_digest")==session==
                    flight.get("browser_session_digest") and
                    flight.get("flight_checked_at_utc")==when):
                continue
            prices[ident]=record
    updated=[]
    for row in public_feed.get("previews",[]):
        new=dict(row)
        # Every public card is visual verified. Hide old reference amounts:
        # price changes intraday and stale source reference would mislead.
        new["price_reference_rub"]=None
        new["price_reference_party"]="UNVERIFIED"
        price=prices.get(row.get("id"))
        if price:
            new["price_reference_rub"]=price["price_total_rub"]
            new["price_reference_party"]="TWO_ADULTS"
            new["price_source"]="BG_EXACT_SELECTED_GREEN_BROWSER"
            new["price_observed_at_utc"]=price["observed_at_utc"]
        updated.append(new)
    out=dict(public_feed)
    out["previews"]=updated
    out["indicative_two_adult_rub_count"]=sum(
        x.get("price_source")=="BG_EXACT_SELECTED_GREEN_BROWSER" for x in updated)
    return out
