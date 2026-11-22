"""JAMAICA private-only BG price-list group source candidate crosswalk.

No HTTP, no credentials, no passenger PII, no money, no booking. Turns raw
operator price-list ROWS already bound to their *own* source prx into strictly
bounded, in-memory candidate groups for a future trusted private quote adapter.

IMPORTANT: these are only POTENTIAL sources. No room allotment/stop-sale,
flight seats, actual adult DOB, final prices, or supplier authorization can be
inferred. Never send records or their fields to public endpoints/logs/JSON.
"""
from __future__ import annotations

from dataclasses import dataclass

from backend.bg_price_age_scope import (
    _iso, _operator_source_binding, candidate_report, possible_group,
)

MAX_PRIVATE_PLANS = 8
MAX_OPTIONS_PER_ROOM = 8


@dataclass(frozen=True, repr=False)
class PrivateRoomSourceOption:
    """Sensitive operator internals; redacted for accidental repr/logging."""
    prx: str
    template_id: str | None
    commission_id: str | None
    roommeal_id: str
    sr: str
    age_marker: str
    start_date: str
    duration_nights: int
    room_name: str
    source_preview_id: str
    hotel_id: str

    def __repr__(self) -> str:
        return "<PrivateRoomSourceOption: REDACTED CANDIDATE ONLY>"


@dataclass(frozen=True, repr=False)
class PrivateTourSourceCandidate:
    """One candidate operator price list with choices for each requested room."""
    prx: str
    template_id: str | None
    commission_id: str | None
    groups: tuple[tuple[PrivateRoomSourceOption, ...], ...]
    status: str = "POTENTIAL_ONLY_NOT_QUOTED"
    quote_verified: bool = False
    availability_verified: bool = False
    flight_verified: bool = False
    bookable: bool = False

    def __repr__(self) -> str:
        return "<PrivateTourSourceCandidate: REDACTED NOT QUOTED>"


def private_source_candidates(preview: dict, rooms: list[dict],
                              rows: list[dict], *,
                              max_plans: int = MAX_PRIVATE_PLANS
                              ) -> tuple[PrivateTourSourceCandidate, ...]:
    """Pure source crosswalk. This deliberately CANNOT certify group occupancy.

    Source entries must already have '_jamaica_private_prx' injected from the
    top-level authenticated BG price-list response by the private Oracle
    scanner. It is never taken from public preview fields. The first group
    must match the originally selected room type. Later groups may use other
    room types of the SAME hotel/date/main-stay price list.

    No source completeness -> empty tuple. Caller must verify exact DOB,
    group capacity/allotment, supplier access, both flights and final quote.
    """
    if type(max_plans) is not int or not 1 <= max_plans <= MAX_PRIVATE_PLANS:
        raise ValueError("Invalid bounded private source plan limit")
    summary = candidate_report(preview, rooms, rows)
    if not summary["shared_source_candidate_count"]:
        return ()
    per_group = []
    for group_index, group in enumerate(rooms):
        by_source = {}
        for row in rows:
            if not isinstance(row, dict) or row.get("isstop") or row.get("stop"):
                continue
            if (str(row.get("id_hotel", "")) != str(preview["hotel_id"]) or
                _iso(row.get("tour_date") or row.get("dt")) !=
                    _iso(preview["depart_date"]) or
                str(row.get("duration", "")) != str(preview["nights"]) or
                not isinstance(row.get("room"), str) or
                not row["room"].strip() or
                (group_index == 0 and row["room"] != preview["room"])):
                continue
            binding = _operator_source_binding(row)
            if binding is None:
                continue
            prx, kind, identifier, start_date, duration = binding
            options = by_source.setdefault(binding, {})
            if len(options) >= MAX_OPTIONS_PER_ROOM:
                continue
            for rate in row.get("prices", []):
                if not isinstance(rate, dict) or rate.get("isstop"):
                    continue
                marker = rate.get("ag")
                if not possible_group(group["adults"], group["child_ages"], marker):
                    continue
                # Only one operator source record per possible age/room/flight
                # tuple; do not publish or interpret pricing amounts.
                sig = (str(row["id_ns"]), str(row["sr"]), marker)
                if sig in options or len(options) >= MAX_OPTIONS_PER_ROOM:
                    continue
                options[sig] = PrivateRoomSourceOption(
                    prx=prx,
                    template_id=identifier if kind=="template" else None,
                    commission_id=identifier if kind=="commission" else None,
                    roommeal_id=str(row["id_ns"]), sr=str(row["sr"]),
                    age_marker=marker, start_date=start_date,
                    duration_nights=duration, room_name=row["room"],
                    source_preview_id=preview["id"], hotel_id=str(preview["hotel_id"]),
                )
        per_group.append({binding:tuple(items.values())
                          for binding,items in by_source.items() if items})
    shared=set.intersection(*(set(g) for g in per_group)) if per_group else set()
    plans=[]
    for binding in sorted(shared)[:max_plans]:
        prx,kind,identifier,_,_ = binding
        plans.append(PrivateTourSourceCandidate(
            prx=prx,
            template_id=identifier if kind=="template" else None,
            commission_id=identifier if kind=="commission" else None,
            groups=tuple(group[binding] for group in per_group),
        ))
    return tuple(plans)
