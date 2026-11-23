"""Publish ONLY safe read-only previews of independently observed BG visual events.

Private receipt format is for a *future* trusted bot adapter. The current
V183 bot produces no authorized records in this format; zero entries means
zero visual matches. A receipt is not a fresh quote, seat hold or booking.

The 5-minute Oracle publisher may read a regular owner-only (0600) file
written by the local trusted bot. No user/browser input path is accepted.
"""
from __future__ import annotations
from datetime import datetime, timezone
from pathlib import Path
import json
import os
import stat
import sys

sys.path.insert(0,str(Path(__file__).resolve().parent.parent))
from backend.bg_route_first_visual_gate import route_first_pair_matches

PRIVATE_SCHEMA="jamaica.bg-bot-private-receipts.v1"
PUBLIC_SCHEMA="jamaica.visual-selection.v1"
MAX_SOURCE_BYTES=1_500_000
MAX_PRIVATE_RECORDS=500
MAX_PUBLIC_RECORDS=300

class VisualHold(ValueError):pass

def read_private_receipts(path:Path)->dict|None:
    """Read securely by descriptor; never log URLs, IDs, or raw receipts."""
    path=Path(path)
    flags=os.O_RDONLY
    if hasattr(os,"O_NOFOLLOW"):flags|=os.O_NOFOLLOW
    if hasattr(os,"O_CLOEXEC"):flags|=os.O_CLOEXEC
    try:
        fd=os.open(path,flags)
    except FileNotFoundError:
        return None
    except OSError:
        raise VisualHold("PRIVATE_BOT_EVIDENCE_UNREADABLE") from None
    try:
        info=os.fstat(fd)
        if (not stat.S_ISREG(info.st_mode) or
            info.st_uid!=os.geteuid() or
            stat.S_IMODE(info.st_mode)&0o077 or
            not 2<=info.st_size<=MAX_SOURCE_BYTES):
            raise VisualHold("PRIVATE_BOT_EVIDENCE_PERMISSIONS_OR_SIZE")
        payload=os.read(fd,MAX_SOURCE_BYTES+1)
    finally:
        os.close(fd)
    if len(payload)>MAX_SOURCE_BYTES:raise VisualHold("PRIVATE_BOT_EVIDENCE_OVERSIZE")
    try:
        data=json.loads(payload)
    except (UnicodeError,ValueError):
        raise VisualHold("PRIVATE_BOT_EVIDENCE_JSON_INVALID") from None
    if (not isinstance(data,dict) or set(data)!={"schema","records"} or
        data.get("schema")!=PRIVATE_SCHEMA or
        not isinstance(data.get("records"),list) or
        len(data["records"])>MAX_PRIVATE_RECORDS):
        raise VisualHold("PRIVATE_BOT_EVIDENCE_SCHEMA_INVALID")
    return data

def empty_public()->dict:
    return {"schema":PUBLIC_SCHEMA,"bookable":False,
            "quote_verified":False,"availability_verified":False,
            "entries":[]}

def build_visual_feed(public_previews:list, private:dict|None,
                      *,now:datetime|None=None)->dict:
    """Intersect exact source-checked previews with valid route-first evidence.

    Source proof cannot be derived from a similar route, same-country offer,
    XML price list, or other hotel's date/room. Any invalid row is discarded.
    The PUBLIC sidecar has no supplier ID, browser URL, session or price.
    """
    result=empty_public()
    if private is None:return result
    if (not isinstance(private,dict) or
        private.get("schema")!=PRIVATE_SCHEMA or
        type(private.get("records")) is not list or
        len(private["records"])>MAX_PRIVATE_RECORDS):
        raise VisualHold("VISUAL_INPUT_SCHEMA_INVALID")
    if now is None:now=datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise VisualHold("VISUAL_CLOCK_INVALID")
    if not isinstance(public_previews,list) or len(public_previews)>60000:
        raise VisualHold("VISUAL_SOURCE_FEED_INVALID")
    previews={p["id"]:p for p in public_previews if isinstance(p,dict) and
              isinstance(p.get("id"),str) and
              p.get("status")=="REFERENCE_PRICE_LIST_ONLY"}
    chosen={}
    for receipt in private["records"]:
        if not isinstance(receipt,dict) or set(receipt)!={"preview_id","route","flight"}:
            continue
        p=previews.get(receipt.get("preview_id"))
        if not p or not route_first_pair_matches(receipt["route"],
                                                  receipt["flight"],p,now=now):
            continue
        # Browser observation is NOT seat inventory or a verified quote.
        # No best-price or both-green status is published for anything other
        # than the exact selected source-backed preview.
        checked=receipt["flight"]["flight_checked_at_utc"]
        row={"preview_id":p["id"],"observed_at_utc":checked,
             "route_best_price_seen":True,"both_green_planes_seen":True}
        prior=chosen.get(p["id"])
        if prior is None or prior["observed_at_utc"]<checked:
            chosen[p["id"]]=row
    result["entries"]=sorted(chosen.values(),
                             key=lambda x:(x["observed_at_utc"],x["preview_id"]),
                             reverse=True)[:MAX_PUBLIC_RECORDS]
    return result

def validate_public_feed(payload:dict, *,now:datetime|None=None)->bool:
    """Defence in depth for the published status, never booking data."""
    if not isinstance(payload,dict) or set(payload)!={
        "schema","bookable","quote_verified","availability_verified","entries"
    } or payload.get("schema")!=PUBLIC_SCHEMA or
        payload.get("bookable") is not False or
        payload.get("quote_verified") is not False or
        payload.get("availability_verified") is not False or
        not isinstance(payload.get("entries"),list) or
        len(payload["entries"])>MAX_PUBLIC_RECORDS):
        return False
    if now is None:now=datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None:return False
    seen=set()
    for e in payload["entries"]:
        if not isinstance(e,dict) or set(e)!={
            "preview_id","observed_at_utc","route_best_price_seen",
            "both_green_planes_seen"}:
            return False
        preview_id=e["preview_id"]
        if (not isinstance(preview_id,str) or len(preview_id)!=26 or
            not preview_id.startswith("p_") or
            not all(c in "0123456789abcdef" for c in preview_id[2:]) or
            preview_id in seen or
            e["route_best_price_seen"] is not True or
            e["both_green_planes_seen"] is not True):
            return False
        seen.add(preview_id)
        try:
            timestamp=datetime.fromisoformat(
                e["observed_at_utc"].replace("Z","+00:00"))
            if timestamp.tzinfo is None:return False
            seconds=(now.astimezone(timezone.utc)-timestamp.astimezone(timezone.utc)).total_seconds()
            if not -30<=seconds<=15*60:return False
        except (TypeError,AttributeError,ValueError):
            return False
    return True
