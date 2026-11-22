"""Private 24-hour memory of source-observed *preliminary* JAMAICA previews.

The BG exporter rotates authentic future price lists across 5-minute cycles.
Without memory, destinations disappear as soon as a different date/list is
sampled. This cache keeps only previously observed preview identities, NEVER
last-cycle prices or any supplier credentials. Historical cards are marked as
not rechecked and unpriced, so no outdated amount can appear saleable.

The caller validates all incoming and cached rows against its public schema,
and saves the returned cache only after a successful source publication.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re

CACHE_SCHEMA="jamaica.recent-price-list-previews.v1"
HISTORICAL_STATUS="PREVIOUSLY_SEEN_NOT_RECHECKED"
MAX_TTL=timedelta(hours=24)
MAX_CLOCK_DRIFT=timedelta(minutes=5)
ISO_DAY=re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")


def _moment(value):
    if not isinstance(value,str) or len(value)>48:
        raise ValueError("CACHE_TIMESTAMP_INVALID")
    try:
        moment=datetime.fromisoformat(value.replace("Z","+00:00"))
    except ValueError:
        raise ValueError("CACHE_TIMESTAMP_INVALID") from None
    if moment.tzinfo is None:
        raise ValueError("CACHE_TIMESTAMP_NOT_UTC")
    return moment.astimezone(timezone.utc)


def combine(source_feed:dict, old_cache:dict|None, *, now:datetime|None=None,
            max_rows:int=60000):
    """Return (public feed, next private cache) with no unverified old price.

    Full-row records in private history are public-safe source-backed previews
    from earlier *successful* scans, NOT operator sessions or booking quotes.
    No record is retained beyond 24 hours after its last actual source read.
    """
    now=now or datetime.now(timezone.utc)
    if now.tzinfo is None or type(max_rows) is not int or not 1<=max_rows<=60000:
        raise ValueError("CACHE_PARAMETERS_INVALID")
    now=now.astimezone(timezone.utc)
    current=source_feed.get("previews")
    if not isinstance(current,list) or not 0<len(current)<=max_rows:
        raise ValueError("CACHE_SOURCE_PREVIEWS_INVALID")
    existing={}
    for row in current:
        if not isinstance(row,dict) or not isinstance(row.get("id"),str) or row["id"] in existing:
            raise ValueError("CACHE_DUPLICATE_SOURCE")
        existing[row["id"]]={"row":dict(row),"last_seen_at_utc":now.isoformat(timespec="seconds")}
    old_entries=[]
    if old_cache is not None:
        if not isinstance(old_cache,dict) or old_cache.get("schema")!=CACHE_SCHEMA:
            raise ValueError("CACHE_SCHEMA_INVALID")
        old_entries=old_cache.get("entries")
        if not isinstance(old_entries,list) or len(old_entries)>60000:
            raise ValueError("CACHE_ENTRY_COUNT_INVALID")
    kept={}
    for item in old_entries:
        if not isinstance(item,dict) or set(item)!={"row","last_seen_at_utc"}:
            raise ValueError("CACHE_ENTRY_INVALID")
        row=item["row"]
        if not isinstance(row,dict) or not isinstance(row.get("id"),str):
            raise ValueError("CACHE_ROW_INVALID")
        row_id=row["id"]
        # No duplicate rows in the private cache: unexpected writes are a HOLD.
        if row_id in kept or row_id in existing:
            if row_id in kept:
                raise ValueError("CACHE_DUPLICATE_ID")
            continue
        observed=_moment(item["last_seen_at_utc"])
        if observed>now+MAX_CLOCK_DRIFT:
            raise ValueError("CACHE_CLOCK_SKEW")
        if now-observed>MAX_TTL:
            continue
        departure=row.get("depart_date")
        if not isinstance(departure,str) or not ISO_DAY.fullmatch(departure):
            raise ValueError("CACHE_DEPARTURE_INVALID")
        try:
            future=date.fromisoformat(departure)>now.date()
        except ValueError:
            raise ValueError("CACHE_DEPARTURE_INVALID") from None
        if future:
            kept[row_id]={"row":dict(row),
                          "last_seen_at_utc":observed.isoformat(timespec="seconds")}
    # Reserve every slot first for ACTUALLY rechecked current supplier rows.
    # Fairly round-robin the spare room over countries and dates from history.
    spare=max_rows-len(current)
    by_country={}
    for item in kept.values():
        row=item["row"]
        by_country.setdefault(row.get("country",""),[]).append(item)
    for items in by_country.values():
        items.sort(key=lambda x:(
            x["row"].get("depart_date",""), x["row"].get("nights",0),
            x["row"].get("hotel",""), x["row"]["id"]))
    selected=[]
    countries=sorted(by_country)
    offset=0
    while len(selected)<spare and countries:
        next_round=[]
        for country in countries:
            candidates=by_country[country]
            if offset<len(candidates):
                selected.append(candidates[offset])
                if len(selected)>=spare:
                    break
                if offset+1<len(candidates):
                    next_round.append(country)
        if len(selected)>=spare:
            break
        countries=next_round
        offset+=1
    # Drop ALL old prices and explicitly mark these as NOT checked in this scan.
    archived=[]
    for item in selected:
        row=dict(item["row"])
        row["status"]=HISTORICAL_STATUS
        row["price_reference_rub"]=None
        row["price_reference_party"]="UNVERIFIED"
        archived.append(row)
    all_rows=current+archived
    public=dict(source_feed)
    public["previews"]=all_rows
    public["indicative_two_adult_rub_count"]=sum(
        type(row.get("price_reference_rub")) is int for row in all_rows)
    public["total_candidate_previews"]=max(
        len(all_rows),int(source_feed.get("total_candidate_previews",len(current))))
    public["truncated_to_public_limit"]=(
        source_feed.get("truncated_to_public_limit") is True or
        len(kept)>len(selected))
    source_scope=source_feed.get("source_scope",{})
    public["source_scope"]={
        **(source_scope if isinstance(source_scope,dict) else {}),
        "last_24h_unrechecked_previews":len(archived),
        "last_24h_unrechecked_countries":len({r["country"] for r in archived}),
    }
    # Only retain selected bounded records plus freshly source-checked records.
    next_cache={"schema":CACHE_SCHEMA,"entries":(
        list(existing.values())+selected)}
    return public,next_cache
