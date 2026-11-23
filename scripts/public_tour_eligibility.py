"""Publish no source-only tour cards: require fresh strict route-first BG proofs.

This is an immutable PUBLIC projection of private authenticated source rows
and independently observed trusted bot receipts. A BG price-list entry alone
does NOT authorize publication; a sighting of both green flights from some
other date/room/hotel also does NOT. Never synthesize evidence or quotes.

If the proof feed is absent, invalid, expired or empty, publish ZERO cards
(not a gallery of unverified tours). Source scanning and the owner-only
historical price-list cache remain independent and operational.
"""
from __future__ import annotations

from datetime import datetime, timezone

try:
    # The installed Oracle publisher imports from its pinned checkout's
    # scripts/ directory, not necessarily from the repository root.
    import bot_visual_sidecar as visual
except ModuleNotFoundError:
    # CI/tests import as scripts.public_tour_eligibility from repo root.
    from scripts import bot_visual_sidecar as visual

PUBLICATION_RULE="BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1"

def select_public_source_rows(source_feed:dict, visual_feed:dict,
                              *, now:datetime|None=None)->dict:
    if not isinstance(source_feed,dict) or not isinstance(source_feed.get("previews"),list):
        raise ValueError("INVALID_PRIVATE_SOURCE_CATALOG")
    if not visual.validate_public_feed(visual_feed,now=now):
        raise ValueError("INVALID_OR_STALE_BOT_VISUAL_FEED")
    evidence={p["preview_id"] for p in visual_feed["entries"]}
    # Exact preview-ID intersection only; no matching by country, travel date,
    # similar property names, airport, or price. Old history never qualifies.
    approved=[row for row in source_feed["previews"]
              if isinstance(row,dict) and row.get("id") in evidence and
                 row.get("status")=="REFERENCE_PRICE_LIST_ONLY" and
                 row.get("bookable") is False and
                 row.get("quote_verified") is False and
                 row.get("availability_verified") is False and
                 row.get("flight_verified") is False]
    published=dict(source_feed)
    # Source coverage is explicitly NOT a list of purchasable tours.
    # Keep only bounded country names, counts and actually sampled months
    # even when mandatory route-first proof leaves ZERO public tour cards.
    coverage=[]
    for stat in source_feed.get("countries_status",[]):
        if not isinstance(stat,dict):
            continue
        country=stat.get("country")
        count=stat.get("previews")
        if (not isinstance(country,str) or not 2<=len(country)<=80 or
                any(c in country for c in "<>{}") or
                type(count) is not int or not 0<count<=60000):
            continue
        sampled=stat.get("sampled_departure_months")
        months=sorted(set(m for m in sampled
            if isinstance(m,str) and len(m)==7 and
            m[:4].isdigit() and m[4]=="-" and m[5:7].isdigit() and
            1<=int(m[5:7])<=12))[:24] if isinstance(sampled,list) else []
        coverage.append({"country":country,
                         "source_rows_observed":count,
                         "sampled_departure_months":months})
        if len(coverage)>=120:
            break
    published["search_coverage"]={
        "classification":"SOURCE_SCAN_ONLY_NOT_OFFERS",
        "countries":coverage}
    published["previews"]=approved
    published["publication_rule"]=PUBLICATION_RULE
    published["indicative_two_adult_rub_count"]=sum(
        type(x.get("price_reference_rub")) is int and
        x["price_reference_rub"]>0 and
        x.get("price_reference_party")=="TWO_ADULTS"
        for x in approved)
    if isinstance(published.get("countries_status"),list):
        counts={}
        for x in approved:
            counts[x["country"]]=counts.get(x["country"],0)+1
        published["countries_status"]=[
            {**x,"previews":counts.get(x.get("country"),0)}
            if isinstance(x,dict) else x
            for x in published["countries_status"]
        ]
    return published
