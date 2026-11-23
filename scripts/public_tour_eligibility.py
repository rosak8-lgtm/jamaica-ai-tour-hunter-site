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
