"""Cross-check ALL published JAMAICA tour cards against exact operator directory IDs.

Every price-list preview must have an exact hotel ID, name and country in the
same independently sourced hotel directory. Similar spellings, hotel brands,
nearby properties and photographs are NOT substitutable. Does not assert hotel
room inventory, actual airline seats, price quotes, photo content or booking.
"""
from __future__ import annotations

import html
import re

HOTEL_ID = re.compile(r"^\d{7,20}$")
_TAGS = re.compile(r"<[^>]{0,300}>")
_WS = re.compile(r"\s+")


class IdentityMismatch(ValueError):
    """The full published source feed must not go live with wrong hotel IDs."""


def public_operator_name(value):
    """Match BG route-sync's 110-char source preview normalization exactly."""
    if not isinstance(value, str):
        return ""
    name = _TAGS.sub(" ", html.unescape(value))
    name = _WS.sub(" ", name).strip()[:110]
    if any(ord(c) < 32 or c in "<>{}" for c in name):
        return ""
    return name


def build_hotel_index(directory):
    if not isinstance(directory, dict) or not isinstance(directory.get("hotels"), list):
        raise IdentityMismatch("DIRECTORY_HOTEL_LIST_MISSING")
    known = {}
    for hotel in directory["hotels"]:
        if not isinstance(hotel, dict):
            raise IdentityMismatch("DIRECTORY_HOTEL_ROW_INVALID")
        hid = str(hotel.get("id", ""))
        name = public_operator_name(hotel.get("name"))
        country = hotel.get("country")
        if (not HOTEL_ID.fullmatch(hid) or not name or
                not isinstance(country, str) or not country.strip()):
            raise IdentityMismatch("DIRECTORY_HOTEL_IDENTITY_INVALID")
        if hid in known:
            raise IdentityMismatch("DIRECTORY_HOTEL_ID_DUPLICATED")
        known[hid] = (name, country)
    if not known:
        raise IdentityMismatch("DIRECTORY_HOTELS_EMPTY")
    return known


def public_departure_cities(page):
    """Read the explicit site city choices for public QA only, not admission."""
    from html.parser import HTMLParser
    class CityChoices(HTMLParser):
        def __init__(self):
            super().__init__()
            self.active=False;self.selects=0;self.names=[]
        def handle_starttag(self,tag,attrs):
            props=dict(attrs)
            if tag=="select" and props.get("id")=="departure":
                self.active=True;self.selects+=1
            elif self.active and tag=="option":
                name=props.get("value")
                if isinstance(name,str) and name and name==name.strip() and len(name)<=100 and not any(c in name for c in "<>{}|"):
                    self.names.append(name)
        def handle_endtag(self,tag):
            if tag=="select":self.active=False
    parser=CityChoices();parser.feed(page)
    if parser.selects!=1 or not 1<=len(parser.names)<=200 or len(set(parser.names))!=len(parser.names) or "Иркутск" not in parser.names:
        raise IdentityMismatch("PUBLIC_DEPARTURE_CHOICES_INVALID")
    return frozenset(parser.names)


def verify_catalog_hotel_identity(rows, directory, *, public_qa_origins=None):
    """Check every row and fail closed before the publisher writes public JSON.

    Exact source name and country are non-negotiable. A card with only an ID
    match can still be for a different hotel after upstream catalog changes.
    """
    if not isinstance(rows, list) or not rows:
        raise IdentityMismatch("SOURCE_PREVIEW_ROWS_EMPTY")
    origins={"Иркутск"} if public_qa_origins is None else public_qa_origins
    if not isinstance(origins,(set,frozenset)) or "Иркутск" not in origins or len(origins)>200:
        raise IdentityMismatch("PUBLIC_DEPARTURE_CHOICES_INVALID")
    known = build_hotel_index(directory)
    checked = set()
    matched_countries = set()
    for row in rows:
        if not isinstance(row, dict):
            raise IdentityMismatch("SOURCE_PREVIEW_ROW_INVALID")
        hid = row.get("hotel_id")
        if not isinstance(hid, str) or not HOTEL_ID.fullmatch(hid):
            raise IdentityMismatch("SOURCE_PREVIEW_HOTEL_ID_INVALID")
        expected = known.get(hid)
        if expected is None:
            raise IdentityMismatch("SOURCE_PREVIEW_HOTEL_UNKNOWN_ID")
        name = row.get("hotel")
        country = row.get("country")
        if not isinstance(name, str) or name != expected[0]:
            raise IdentityMismatch("SOURCE_PREVIEW_HOTEL_NAME_MISMATCH")
        if not isinstance(country, str) or country != expected[1]:
            raise IdentityMismatch("SOURCE_PREVIEW_HOTEL_COUNTRY_MISMATCH")
        if not isinstance(row.get("origin"),str) or row["origin"] not in origins:
            raise IdentityMismatch("SOURCE_PREVIEW_WRONG_DEPARTURE_CITY")
        if row.get("bookable") is not False or row.get("flight_verified") is not False:
            raise IdentityMismatch("SOURCE_PREVIEW_UNVERIFIED_BOOKING_CLAIM")
        uid = row.get("id")
        if not isinstance(uid, str) or not re.fullmatch(r"p_[0-9a-f]{24}", uid):
            raise IdentityMismatch("SOURCE_PREVIEW_INVALID_CARD_ID")
        if uid in checked:
            raise IdentityMismatch("SOURCE_PREVIEW_DUPLICATE_CARD_ID")
        checked.add(uid)
        matched_countries.add(country)
    return {"checked":len(checked), "hotels":len(known),
            "countries":len(matched_countries), "hotel_id_match":True,
            "hotel_name_match":True, "country_match":True}
