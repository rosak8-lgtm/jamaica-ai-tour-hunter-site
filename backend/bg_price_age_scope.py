"""Privacy-safe Biblio-Globus age-bucket reconnaissance for selected tour.

The public preview price is always for TWO_ADULTS. This module merely counts
PRIVATE price-list candidates whose published age-band marker COULD fit all
requested passengers. Adults' dates of birth are not known at search time;
therefore a match is a POSSIBILITY, never proof of room availability, gross
cost, flight seats or booking eligibility.

Official BG price format may contain "ag": "[14-99][14-99]" or
"12+,12+,2-11". Age range endpoints in BG price lists are inclusive.

No network, credentials, passport details, log output, booking or payments.
"""
from __future__ import annotations

from datetime import date, datetime
import re

MAX_ROOMS=5
MAX_PASSENGERS=22
MAX_ROWS=10000
_RE_COMPACT=re.compile(r"(?:\[\d{1,3}-\d{1,3}\]){1,22}")
_RE_PART=re.compile(r"^(?:\[)?(\d{1,3})(?:-(\d{1,3})|\+)(?:\])?$")
_RE_ID=re.compile(r"\d{7,20}")
_RE_PREVIEW=re.compile(r"p_[a-f0-9]{24}")


def parse_age_ranges(marker: str):
    """Return inclusive ranges or None. Never silently accept unknown markup."""
    if not isinstance(marker,str) or len(marker)>512:
        return None
    marker=marker.strip()
    if not marker:
        return None
    if _RE_COMPACT.fullmatch(marker):
        values=re.findall(r"\[(\d{1,3})-(\d{1,3})\]",marker)
        out=[(int(a),int(b)) for a,b in values]
    else:
        raw=[part.strip() for part in marker.split(",")]
        if not 1<=len(raw)<=MAX_PASSENGERS:
            return None
        out=[]
        for part in raw:
            if part.startswith("[") != part.endswith("]"):
                return None
            m=_RE_PART.fullmatch(part)
            if not m:
                return None
            lo=int(m.group(1))
            hi=int(m.group(2)) if m.group(2) is not None else 120
            out.append((lo,hi))
    return tuple(out) if 1<=len(out)<=MAX_PASSENGERS and all(
        0<=low<=high<=120 for low,high in out
    ) else None


def _assignable(passenger_ranges,price_ranges):
    """One-to-one bipartite match: never reuse a single tariff slot."""
    if len(passenger_ranges)!=len(price_ranges):
        return False
    matched=[-1]*len(price_ranges)
    def dfs(person,seen):
        lo,hi=passenger_ranges[person]
        for option,(a,b) in enumerate(price_ranges):
            if option in seen or max(lo,a)>min(hi,b):
                continue
            seen.add(option)
            previous=matched[option]
            if previous==-1 or dfs(previous,seen):
                matched[option]=person
                return True
        return False
    # Less flexible people first: exact child age before an adult unknown DOB.
    order=sorted(range(len(passenger_ranges)),key=lambda i:
                 passenger_ranges[i][1]-passenger_ranges[i][0])
    return all(dfs(person,set()) for person in order)


def possible_group(adults:int,child_ages:list[int],marker:str)->bool:
    """Candidate only: adult ages are unknown in public search (18..120)."""
    if (type(adults) is not int or not 1<=adults<=12 or
        not isinstance(child_ages,list) or len(child_ages)>10 or
        any(type(x) is not int or not 0<=x<=17 for x in child_ages)):
        return False
    tariff=parse_age_ranges(marker)
    return tariff is not None and _assignable(
        [(18,120)]*adults+[(a,a) for a in child_ages],tariff)


def exact_ages_match(ages:list[int],marker:str)->bool:
    """Private DOB-verified ages, not a fallback for absent DOBs."""
    if (not isinstance(ages,list) or len(ages)>MAX_PASSENGERS or
        not ages or any(type(a) is not int or not 0<=a<=120 for a in ages)):
        return False
    tariff=parse_age_ranges(marker)
    return tariff is not None and _assignable([(a,a) for a in ages],tariff)


def _iso(raw):
    if not isinstance(raw,str):
        return None
    try:
        d=date.fromisoformat(raw) if "-" in raw else datetime.strptime(raw,"%d.%m.%Y").date()
        return d if 2020<=d.year<=2100 and raw in (d.isoformat(),d.strftime("%d.%m.%Y")) else None
    except ValueError:
        return None


def _operator_source_binding(row:dict):
    """Privacy-safe source candidate, not a live quote or booking.

    BG JSON keeps id_ns, sr, id_price/ic, dt, and o_duration on the
    parent price-list row rather than the individual prices[] option.
    prx comes from the top-level authorized price-list response.
    """
    # prx originates in the authenticated top-level JSON response. Never
    # combine same-template rows from different price-list documents.
    private_prx=row.get("_jamaica_private_prx")
    if (not _RE_ID.fullmatch(str(private_prx or "")) or
        not _RE_ID.fullmatch(str(row.get("id_ns","")))):
        return None
    # This private serializer handles ONLY one main stay per room; any
    # before/after roommeal must not silently be dropped from the request.
    if any(row.get(field) not in (None,"",0) for field in
           ("id_ns_b","id_ns_ab","id_ns_ba","id_ns_a",
            "b_duration","ab_duration","ba_duration","a_duration")):
        return None
    started_tour=_iso(row.get("tour_date") or row.get("dt"))
    started_hotel=_iso(row.get("dt") or row.get("tour_date"))
    total_nights=row.get("duration")
    primary_nights=row.get("o_duration",total_nights)
    # BG tour_date is the tour departure; dt is the start of the primary
    # hotel stay. Overnight / connecting journeys may start the hotel later.
    # The private quote serializer already permits a 0..4 day lag; keep
    # identical guardrails here, never accept a date before departure.
    if (started_tour is None or started_hotel is None or
        not 0 <= (started_hotel-started_tour).days <= 4 or
        str(primary_nights)!=str(total_nights)):
        return None
    sr=row.get("sr")
    if (not isinstance(sr,str) or not 1<=len(sr.strip())<=2048 or
        any(ord(c)<32 or ord(c)==127 for c in sr)):
        return None
    ic=row.get("ic")
    if ic not in (None,""):
        kind,identifier="commission",str(ic)
    else:
        kind,identifier="template",str(row.get("id_price",""))
    if not _RE_ID.fullmatch(identifier):
        return None
    started=_iso(row.get("dt") or row.get("tour_date"))
    raw_nights=row.get("o_duration",row.get("duration"))
    if (started is None or type(raw_nights) not in (int,str) or
        not re.fullmatch(r"[1-9][0-9]{0,2}",str(raw_nights)) or
        not 1<=int(raw_nights)<=180):
        return None
    return (str(private_prx),kind,identifier,started.isoformat(),int(raw_nights))


def candidate_report(preview:dict,selected_rooms:list[dict],rows:list[dict])->dict:
    """Private audit counts only, never individual prices, IDs or operator URLs.

    The first room remains bound to the public reference room. Extra groups
    may use another room type in the same hotel/date, but selection remains
    unverified until the private supplier roommeal crosswalk is complete.
    """
    if (not isinstance(preview,dict) or
        not _RE_PREVIEW.fullmatch(str(preview.get("id",""))) or
        not _RE_ID.fullmatch(str(preview.get("hotel_id",""))) or
        not isinstance(preview.get("room"),str) or
        not _iso(preview.get("depart_date")) or
        type(preview.get("nights")) is not int or
        not 1<=preview["nights"]<=180 or
        not isinstance(rows,list) or len(rows)>MAX_ROWS or
        not isinstance(selected_rooms,list) or
        not 1<=len(selected_rooms)<=MAX_ROOMS):
        raise ValueError("Invalid private age-price audit scope")
    adults=children=0
    for room in selected_rooms:
        if not isinstance(room,dict) or not isinstance(room.get("child_ages"),list):
            raise ValueError("Invalid traveler group")
        a=room.get("adults")
        if (type(a) is not int or not 1<=a<=12 or
            any(type(x) is not int or not 0<=x<=17 for x in room["child_ages"])):
            raise ValueError("Invalid traveler age composition")
        adults+=a
        children+=len(room["child_ages"])
    if adults>12 or children>10:
        raise ValueError("Too many travelers")
    usable=[]
    for row in rows:
        if not isinstance(row,dict) or row.get("isstop") or row.get("stop"):
            continue
        if (str(row.get("id_hotel",""))!=str(preview["hotel_id"]) or
            _iso(row.get("tour_date") or row.get("dt"))!=_iso(preview["depart_date"]) or
            str(row.get("duration",""))!=str(preview["nights"]) or
            not isinstance(row.get("room"),str) or not row["room"].strip() or
            not isinstance(row.get("prices"),list)):
            continue
        usable.append(row)
    counts=[]
    evidence=[]
    shared_bindings=[]
    for index,group in enumerate(selected_rooms):
        candidates=source_complete=0
        matched_bindings=set()
        for row in usable:
            if index==0 and row["room"]!=preview["room"]:
                continue
            for option in row["prices"]:
                if not isinstance(option,dict) or option.get("isstop"):
                    continue
                if not possible_group(group["adults"],group["child_ages"],
                                      option.get("ag")):
                    continue
                candidates+=1
                # Read sr from the official BG ROW, not prices[].
                binding=_operator_source_binding(row)
                if binding is not None:
                    source_complete+=1
                    matched_bindings.add(binding)
        counts.append(candidates)
        evidence.append(source_complete)
        shared_bindings.append(matched_bindings)
    common=set.intersection(*shared_bindings) if shared_bindings else set()
    return {
        "status":"POTENTIAL_CANDIDATES_ONLY" if all(x>0 for x in counts)
                 else "MISSING_GROUP_AGE_CANDIDATES",
        "requested_rooms":len(selected_rooms),
        "candidate_counts":counts,
        "source_metadata_counts":evidence,
        "shared_source_candidate_count":len(common),
        "source_status":("POTENTIAL_SAME_PRX_PRICE_LIST_ONLY" if common else
                         "MISSING_COMMON_PRICE_LIST_SOURCE"),
        "exact_supplier_quote":False,
        "availability_verified":False,
        "flight_verified":False,
        "bookable":False,
    }
