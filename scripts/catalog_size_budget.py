"""Source-backed, memory-safe public JAMAICA feed byte limiter.

Every chosen row is sourced from an already validated operator preview. No fake
countries, prices or bookable flags are generated. Limits total published data
before GitHub Pages sharding; preserve current-source rows ahead of 24h history
and rotate fairly across countries. This does NOT verify stock or price.
"""
from collections import Counter, deque
import json

DEFAULT_MAX_BYTES=32_000_000
MAX_ROWS=60_000
ARCHIVED_STATUS="PREVIOUSLY_SEEN_NOT_RECHECKED"

def encoded_size(value):
    return len(json.dumps(value,ensure_ascii=False,separators=(",",":")).encode("utf-8"))

def _interleave_countries(rows):
    groups={}
    for row in rows:
        country=row.get("country")
        groups.setdefault(country,deque()).append(row)
    names=sorted(groups)
    while names:
        waiting=[]
        for name in names:
            q=groups[name]
            yield q.popleft()
            if q:
                waiting.append(name)
        names=waiting

def fit_feed(feed, *, max_bytes=DEFAULT_MAX_BYTES, max_rows=MAX_ROWS):
    """Produce exact-size-bounded feed and number dropped, with honest counters.

    Upper bounds leave room for root/shard wrappers and for a private cache.
    Historical preview prices are always stripped by the 24h cache adapter;
    this limiter nevertheless refuses a priced historical row (fail closed).
    """
    if (not isinstance(feed,dict) or
        type(max_bytes) is not int or not 1000<=max_bytes<=40_000_000 or
        type(max_rows) is not int or not 1<=max_rows<=MAX_ROWS):
        raise ValueError("BAD_FEED_LIMITS")
    rows=feed.get("previews")
    if not isinstance(rows,list) or not rows or len(rows)>MAX_ROWS:
        raise ValueError("BAD_SOURCE_PREVIEW_ROWS")
    # Retain the rest of the prevalidated document metadata as-is.
    metadata={**feed,"previews":[]}
    used=encoded_size(metadata)
    if used>=max_bytes:
        raise ValueError("FEED_METADATA_EXCEEDS_BUDGET")
    fresh=[];historical=[];ids=set()
    for row in rows:
        if not isinstance(row,dict) or row.get("id") in ids:
            raise ValueError("BAD_OR_DUPLICATE_SOURCE_ROW")
        ids.add(row.get("id"))
        if row.get("status")==ARCHIVED_STATUS:
            if row.get("price_reference_rub") is not None or row.get("price_reference_party")!="UNVERIFIED":
                raise ValueError("HISTORICAL_PRICE_MUST_BE_EMPTY")
            historical.append(row)
        else:
            fresh.append(row)
    chosen=[];skipped=0
    # Current supplier-sampled rows have priority, but all observed countries
    # receive equal selection opportunities within the current/historical tier.
    for group in (fresh,historical):
        for row in _interleave_countries(group):
            size=encoded_size(row)+1
            if len(chosen)<max_rows and used+size<=max_bytes:
                used+=size
                chosen.append(row)
            else:
                skipped+=1
    if not chosen:
        raise ValueError("NO_PREVIEW_FITS_BYTE_BUDGET")
    out={**feed,"previews":chosen}
    out["indicative_two_adult_rub_count"]=sum(
        type(x.get("price_reference_rub")) is int for x in chosen)
    out["truncated_to_public_limit"]=(
        feed.get("truncated_to_public_limit") is True or skipped>0)
    out["total_candidate_previews"]=max(
        len(rows),len(chosen),int(feed.get("total_candidate_previews",len(rows))))
    scope=out.get("source_scope")
    if isinstance(scope,dict) and "last_24h_unrechecked_previews" in scope:
        old=[x for x in chosen if x.get("status")==ARCHIVED_STATUS]
        out["source_scope"]={**scope,
            "last_24h_unrechecked_previews":len(old),
            "last_24h_unrechecked_countries":len({x.get("country") for x in old})}
    countries_status=out.get("countries_status")
    if isinstance(countries_status,list):
        counts=Counter(x.get("country") for x in chosen)
        out["countries_status"]=[
            {**st,"previews":counts[st["country"]]}
            if isinstance(st,dict) and isinstance(st.get("country"),str)
            else st for st in countries_status]
    # Size check includes recomputed metadata and exact compact serialization.
    if encoded_size(out)>max_bytes:
        # Compact metadata can grow due to newly encoded counts; extremely
        # small input budgets should fail closed instead of overpublishing.
        raise ValueError("POST_SELECTION_FEED_TOO_LARGE")
    return out,skipped
