"""Owner-only sink to attach directly INSIDE a trusted authenticated BG bot.

Not a CLI, HTTP endpoint, mock browser, proof generator or public-data import.
Call ONLY after the bot has actually CLICKED the BG route carrying
'ЛУЧШАЯ ЦЕНА' and inspected both green flight indicators on its selected
hotel/date/room, with exact original source IDs and timestamps.
This sink never manufactures badge/flight values from a price list.
"""
from __future__ import annotations

from datetime import datetime,timezone,timedelta
from pathlib import Path
import copy
import json
import os
import stat
import tempfile

# Package callers must use the same module identity even if the publisher
# previously inserted scripts/ into sys.path for its standalone entrypoint.
if __package__:
    from . import bot_visual_sidecar as visual
else:
    import bot_visual_sidecar as visual
from backend.bg_route_first_visual_gate import route_first_pair_matches

PRIVATE_PATH=Path.home()/".local"/"share"/"jamaica-oracle-catalog"/"private-bg-route-first-receipts.json"
ROUTE_KEYS=frozenset((
    "source_price_list_id","source_route_id","browser_session_digest",
    "source","badge_text","badge_scope","route_clicked","page_url",
    "origin_city_id","origin","country","depart_date",
    "badge_seen_at_utc","route_clicked_at_utc"))
FLIGHT_KEYS=frozenset((
    "source_price_list_id","source_route_id","browser_session_digest",
    "source","out_green","back_green","stop_sale","origin","country",
    "depart_date","hotel_id","room","nights","source_preview_id",
    "flight_checked_at_utc"))


def _validated_scope(route,flight,preview,now):
    if (not isinstance(route,dict) or set(route)!=ROUTE_KEYS or
        not isinstance(flight,dict) or set(flight)!=FLIGHT_KEYS or
        not isinstance(preview,dict)):
        return False
    return route_first_pair_matches(route,flight,preview,now=now)


def _private_directory(path):
    parent=path.parent
    info=parent.lstat()
    if (not stat.S_ISDIR(info.st_mode) or info.st_uid!=os.geteuid() or
        stat.S_IMODE(info.st_mode)&0o077):
        raise visual.VisualHold("RECEIPT_PARENT_NOT_OWNER_ONLY")


def save_from_trusted_browser(route,flight,preview, *,
                              path=PRIVATE_PATH, now=None):
    """Single-row compatibility wrapper; the same strict batch gate."""
    return bool(save_batch_from_trusted_browser([(route,flight,preview)],path=path,now=now))


def save_batch_from_trusted_browser(pairs, *, path=PRIVATE_PATH, now=None):
    """Validate each independently observed pair; atomically write one ledger.

    All pairs are supplied by the trusted browser process after a real click.
    No mixed or incomplete evidence can be elevated by batching.
    Return only accepted preview IDs; preserve previous fresh receipts.
    """
    if now is None:
        now=datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None:
        raise visual.VisualHold("TRUSTED_BOT_CLOCK_INVALID")
    if not isinstance(pairs,(list,tuple)) or len(pairs)>visual.MAX_PRIVATE_RECORDS:
        raise visual.VisualHold("TRUSTED_BOT_BATCH_INVALID")
    newest={}
    for pair in pairs:
        if not isinstance(pair,(tuple,list)) or len(pair)!=3:
            continue
        route,flight,preview=pair
        if not _validated_scope(route,flight,preview,now):
            continue
        newest[preview["id"]]={"preview_id":preview["id"],
            "route":copy.deepcopy(route),"flight":copy.deepcopy(flight)}
    if not newest:
        return []
    accepted=list(newest)
    path=Path(path)
    _private_directory(path)
    current=visual.read_private_receipts(path)
    if current is None:
        current={"schema":visual.PRIVATE_SCHEMA,"records":[]}
    # Keep other source-bound receipts only for their bounded lifetime.
    for old in current["records"]:
        if not isinstance(old,dict) or set(old)!={"preview_id","route","flight"}:
            continue
        uid=old.get("preview_id")
        if uid in newest or not isinstance(uid,str):
            continue
        old_flight=old.get("flight")
        if not isinstance(old_flight,dict):
            continue
        try:
            checked=datetime.fromisoformat(
                old_flight["flight_checked_at_utc"].replace("Z","+00:00"))
            if checked.tzinfo is None or not timedelta(0)<=(
                now.astimezone(timezone.utc)-
                checked.astimezone(timezone.utc))<=timedelta(minutes=15):
                continue
        except (TypeError,KeyError,AttributeError,ValueError):
            continue
        if len(newest)>=visual.MAX_PRIVATE_RECORDS:
            break
        newest[uid]=old
    payload={"schema":visual.PRIVATE_SCHEMA,
             "records":list(newest.values())}
    encoded=json.dumps(payload,ensure_ascii=False,separators=(",",":")).encode("utf-8")
    if not 2<=len(encoded)<=visual.MAX_SOURCE_BYTES:
        raise visual.VisualHold("TRUSTED_BOT_RECEIPT_TOO_LARGE")
    temp=None
    try:
        fd,filename=tempfile.mkstemp(prefix=".bg-route-proof-",dir=path.parent)
        temp=Path(filename)
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp,path)
        os.chmod(path,0o600)
        return accepted
    finally:
        if temp is not None and temp.exists():
            temp.unlink()
