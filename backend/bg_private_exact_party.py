"""Private BG exact-age room source selector. No supplier network or PII output.

Between candidate source crosswalk and authorized supplier price inquiry, a
secured session's dates of birth must match prices[].ag for every traveler.
Outputs contain only PRIVATE source options, no DOB, names, passport, prices,
room availability, flight availability or booking confirmation.

This NEVER mints operator verification flags. Authorized quote, supplier
room allotment and seller permission remain independent mandatory checks.
"""
from __future__ import annotations

from dataclasses import dataclass
import re

from backend.bg_multiroom_quote import _selected_rooms, age_on, _iso_date
from backend.bg_price_age_scope import exact_ages_match
from backend.bg_private_source_crosswalk import (
    PrivateRoomSourceOption, PrivateTourSourceCandidate,
    MAX_PRIVATE_PLANS, MAX_OPTIONS_PER_ROOM,
)
from backend.order_engine import BadOrder

MAX_EXACT_PLANS = 8


@dataclass(frozen=True, repr=False)
class ExactPartySourcePlan:
    """One shared hotel start and flight route. REDACTED and never a quote."""
    group_options: tuple[tuple[PrivateRoomSourceOption, ...], ...]
    prx: str
    template_id: str | None
    commission_id: str | None
    hotel_start_date: str
    route_sr: str
    status: str = "EXACT_AGE_SOURCE_CANDIDATE_ONLY"
    quote_verified: bool = False
    availability_verified: bool = False
    flight_verified: bool = False
    bookable: bool = False

    def __repr__(self) -> str:
        return "<ExactPartySourcePlan: REDACTED NOT QUOTED>"


def _valid_preview(preview):
    return (
        isinstance(preview, dict) and
        isinstance(preview.get("id"), str) and
        re.fullmatch(r"p_[a-f0-9]{24}", preview["id"]) is not None and
        isinstance(preview.get("hotel_id"), str) and
        re.fullmatch(r"\d{7,20}", preview["hotel_id"]) is not None and
        isinstance(preview.get("room"), str) and
        bool(preview["room"].strip()) and
        type(preview.get("nights")) is int and 3 <= preview["nights"] <= 180 and
        isinstance(preview.get("depart_date"), str)
    )


def select_exact_party_sources(preview: dict, selected_rooms: list[dict],
                               birthdates_by_room: list[list[str]],
                               source_plans: tuple[PrivateTourSourceCandidate, ...]
                               ) -> tuple[ExactPartySourcePlan, ...]:
    """Check real DOBs, exact tariff ages, same source, stay and flight route.

    Inputs MUST come from a secure authenticated private session and trusted
    BG source crosswalk, never arbitrary public browser JSON. This is a
    source-only candidate, not a provider price/availability request.
    """
    if not _valid_preview(preview):
        raise BadOrder("Private preview is invalid")
    departure = _iso_date(preview["depart_date"])
    selected = _selected_rooms(selected_rooms)
    if (not isinstance(birthdates_by_room, list) or
        len(birthdates_by_room) != len(selected) or
        not isinstance(source_plans, (tuple, list)) or
        len(source_plans) > MAX_PRIVATE_PLANS):
        raise BadOrder("Private passenger group shape invalid")

    # Ephemeral age integers only; no DOBs or person data are returned.
    age_sets = []
    for expected, born in zip(selected, birthdates_by_room):
        if (not isinstance(born, list) or
            len(born) != expected["adults"] + len(expected["child_ages"])):
            raise BadOrder("Private room passenger count invalid")
        actual = [age_on(value, preview["depart_date"]) for value in born]
        if (any(not 18 <= age <= 120 for age in actual[:expected["adults"]]) or
            tuple(actual[expected["adults"]:]) != expected["child_ages"]):
            raise BadOrder("Private DOBs do not match chosen traveler rooms")
        age_sets.append(actual)

    results = []
    for plan in source_plans:
        if (not isinstance(plan, PrivateTourSourceCandidate) or
            plan.status != "POTENTIAL_ONLY_NOT_QUOTED" or
            plan.quote_verified is not False or
            plan.availability_verified is not False or
            plan.flight_verified is not False or plan.bookable is not False or
            not isinstance(plan.groups, tuple) or
            len(plan.groups) != len(selected) or
            not isinstance(plan.prx, str) or
            re.fullmatch(r"\d{7,20}", plan.prx) is None or
            bool(plan.template_id) == bool(plan.commission_id)):
            continue

        per_group = []
        for index, (group, ages) in enumerate(zip(plan.groups, age_sets)):
            if (not isinstance(group, tuple) or
                len(group) > MAX_OPTIONS_PER_ROOM):
                per_group.append({})
                continue
            by_route = {}
            for option in group:
                if not isinstance(option, PrivateRoomSourceOption):
                    continue
                if (option.prx != plan.prx or
                    option.template_id != plan.template_id or
                    option.commission_id != plan.commission_id or
                    option.source_preview_id != preview["id"] or
                    option.hotel_id != preview["hotel_id"] or
                    option.duration_nights != preview["nights"] or
                    (index == 0 and option.room_name != preview["room"]) or
                    not isinstance(option.sr, str) or
                    not 1 <= len(option.sr) <= 2048 or
                    any(ord(c) < 32 or ord(c) == 127 for c in option.sr) or
                    re.fullmatch(r"\d{7,20}", str(option.roommeal_id)) is None or
                    (option.otv_id is not None and
                     re.fullmatch(r"\d{7,20}", str(option.otv_id)) is None) or
                    not exact_ages_match(ages, option.age_marker)):
                    continue
                try:
                    stay = _iso_date(option.start_date)
                except BadOrder:
                    continue
                if not 0 <= (stay - departure).days <= 4:
                    continue
                by_route.setdefault((option.start_date, option.sr), []).append(option)
            per_group.append(by_route)

        if not per_group or any(not group for group in per_group):
            continue
        common = set.intersection(*(set(group) for group in per_group))
        for hotel_date, sr in sorted(common):
            groups = tuple(tuple(group[(hotel_date, sr)]) for group in per_group)
            if any(not x for x in groups):
                continue
            results.append(ExactPartySourcePlan(
                group_options=groups, prx=plan.prx,
                template_id=plan.template_id,
                commission_id=plan.commission_id,
                hotel_start_date=hotel_date, route_sr=sr
            ))
            if len(results) >= MAX_EXACT_PLANS:
                return tuple(results)
    return tuple(results)
