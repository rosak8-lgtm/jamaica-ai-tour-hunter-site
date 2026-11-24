"""Private JAMAICA route-first visual gate for authenticated BG bot evidence.

The operator's published booking instructions put the route-level
'ЛУЧШАЯ ЦЕНА' badge BEFORE opening an expanded hotel-tour selection.
The browser bot must first select that exact route, then check BOTH
flight icons for the same source price list, hotel and passenger party.

This is a validation boundary, NOT a browser automation or supplier quote.
No client, static web page or historical JSON may produce this proof.
"""
from __future__ import annotations

from datetime import datetime,timezone,timedelta
from urllib.parse import urlsplit,parse_qs
from scripts.bg_origin_scope import Scope
import re

ALLOWED_ORIGIN="Иркутск"
ORIGIN_CITY_ID="100510397223"
BADGE="ЛУЧШАЯ ЦЕНА"
PROOF_MAX_AGE=timedelta(minutes=15)
MAX_ROUTE_TO_FLIGHT=timedelta(minutes=10)
ID_PRICE=re.compile(r"^[0-9]{7,25}$")
SHA256=re.compile(r"^[0-9a-f]{64}$")
PREVIEW_ID=re.compile(r"^p_[0-9a-f]{24}$")

def _time(value):
    if not isinstance(value,str):
        return None
    try:
        instant=datetime.fromisoformat(value.replace("Z","+00:00"))
        if instant.tzinfo is None:
            return None
        return instant.astimezone(timezone.utc)
    except ValueError:
        return None

def _operator_page(url):
    if not isinstance(url,str) or len(url)>2048:
        return False
    try:
        u=urlsplit(url)
        return (u.scheme=="https" and u.hostname in
            ("www.bgoperator.ru","bgoperator.ru") and
            u.port in (None,443) and
            u.path in ("/price.shtml","/index.shtml") and
            u.username is None and u.password is None and
            not u.fragment)
    except ValueError:
        return False

def route_first_pair_matches(route:dict|None,flight:dict|None,preview:dict|None,
                             *,now:datetime|None=None,origin_scope:Scope|None=None)->bool:
    """Verify exact stage order and *same* route and row, not nearby UI icons.

    The bot must generate this evidence INSIDE a trusted server-side
    Playwright session after interacting with official BG pages. Pure
    metadata, a green icon screenshot or two unrelated timestamps do NOT
    establish live inventory, supplier quote, contract or bookability.
    """
    if not all(isinstance(x,dict) for x in (route,flight,preview)):
        return False
    if now is None:
        now=datetime.now(timezone.utc)
    if not isinstance(now,datetime) or now.tzinfo is None:
        return False
    now=now.astimezone(timezone.utc)
    # New cities require an explicitly supplied trusted directory scope.
    # Existing production callers still accept Irkutsk only.
    if origin_scope is not None and not isinstance(origin_scope,Scope):return False
    expected_origin=ALLOWED_ORIGIN if origin_scope is None else origin_scope.origin
    expected_id=ORIGIN_CITY_ID if origin_scope is None else origin_scope.origin_id
    if (preview.get("bookable") is not False or
        preview.get("quote_verified") is not False or
        not isinstance(preview.get("id"),str) or
        not PREVIEW_ID.fullmatch(preview["id"]) or
        preview.get("origin")!=expected_origin):
        return False

    # Route badge belongs to the selected ROUTE ROW, not the results
    # title, cheapest hotel row or another date/destination.
    if (route.get("source")!="BG_OFFICIAL_BROWSER_ROUTE" or
        route.get("badge_text")!=BADGE or
        route.get("badge_scope")!="SELECTED_ROUTE_ROW" or
        route.get("route_clicked") is not True or
        not _operator_page(route.get("page_url")) or
        route.get("origin_city_id")!=expected_id or
        route.get("origin")!=preview.get("origin") or
        route.get("country")!=preview.get("country") or
        route.get("depart_date")!=preview.get("depart_date")):
        return False
    if origin_scope is not None:
        # For multi-origin receipts, bind the exact official clicked URL,
        # registry country and city, and the city-specific canonical ID.
        # Do not reinterpret any legacy receipt for another city.
        try:
            q=parse_qs(urlsplit(route["page_url"]).query,keep_blank_values=True)
            if (q.get("flt")!=[origin_scope.country_id] or
                q.get("flt2")!=[origin_scope.origin_id] or
                preview.get("country")!=origin_scope.country or
                route.get("source_route_id")!=origin_scope.country_id or
                flight.get("origin_city_id")!=origin_scope.origin_id or
                q.get("action")!=["price"] or
                q.get("id_price")!=[route.get("source_price_list_id")] or
                q.get("data")!=[datetime.strptime(preview["depart_date"],"%Y-%m-%d").strftime("%d.%m.%Y")] or
                preview["id"]!=origin_scope.preview_id(str(preview["hotel_id"]),
                    preview["depart_date"],preview["nights"],preview["room"])):
                return False
        except (KeyError,ValueError,TypeError,AttributeError):
            return False
    # Flight details MUST come from the route which was clicked first,
    # and exactly match the public preview ID/hotel/room/nights/date.
    if (flight.get("source")!="BG_OFFICIAL_BROWSER_SELECTED_DETAIL" or
        flight.get("out_green") is not True or
        flight.get("back_green") is not True or
        flight.get("stop_sale") is not False or
        flight.get("origin")!=preview.get("origin") or
        flight.get("country")!=preview.get("country") or
        flight.get("depart_date")!=preview.get("depart_date") or
        str(flight.get("hotel_id"))!=str(preview.get("hotel_id")) or
        flight.get("room")!=preview.get("room") or
        type(flight.get("nights")) is not int or
        flight["nights"]!=preview.get("nights") or
        flight.get("source_preview_id")!=preview.get("id")):
        return False
    list_id=route.get("source_price_list_id")
    route_id=route.get("source_route_id")
    session=route.get("browser_session_digest")
    if (not isinstance(list_id,str) or not ID_PRICE.fullmatch(list_id) or
        not isinstance(route_id,str) or not ID_PRICE.fullmatch(route_id) or
        not isinstance(session,str) or not SHA256.fullmatch(session) or
        flight.get("source_price_list_id")!=list_id or
        flight.get("source_route_id")!=route_id or
        flight.get("browser_session_digest")!=session):
        return False
    discovered=_time(route.get("badge_seen_at_utc"))
    clicked=_time(route.get("route_clicked_at_utc"))
    checked=_time(flight.get("flight_checked_at_utc"))
    if not all((discovered,clicked,checked)):
        return False
    if (not discovered<=clicked<=checked<=now+timedelta(seconds=30) or
        checked-discovered>MAX_ROUTE_TO_FLIGHT or
        now-checked>PROOF_MAX_AGE):
        return False
    return True
