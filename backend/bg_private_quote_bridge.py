"""JAMAICA private BG multi-room READ-ONLY price bridge.

This is the final in-memory interface between the exact-DOB source crosswalk
and BGReadOnlyPriceClient.price_groups_only. The authorized private service
must supply authenticated buyer consent, real passport records, and an
independent FRESH operator inventory/source preflight. No HTTP endpoint,
browser JSON, GitHub artifact, credential, logging, payment, or booking here.

A price from the official Tour API is not a confirmed hotel allotment, two
flight seats, best-price route badge, contract or supplier booking.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import re
import secrets

from backend.bg_multiroom_quote import _selected_rooms
from backend.bg_private_exact_party import select_exact_party_sources
from backend.bg_private_source_crosswalk import (
    PrivateTourSourceCandidate, PrivateRoomSourceOption, MAX_PRIVATE_PLANS,
)
from backend.order_engine import BadOrder, NotAvailable

MAX_PREFLIGHT_AGE_SECONDS = 300
MAX_PRICE_TOTAL_RUB = 100_000_000


@dataclass(frozen=True, repr=False)
class PrivateBuyerPriceAuthorization:
    """Issued solely by the future private buyer/consent/access middleware."""
    buyer_session_id: str
    authenticated: bool
    personal_data_consent_verified: bool
    supplier_price_api_permission_verified: bool
    expires_at: datetime

    def __repr__(self):
        return "<PrivateBuyerPriceAuthorization: REDACTED>"


@dataclass(frozen=True, repr=False)
class IndependentOperatorPreflight:
    """Fresh independent provider facts; NEVER filled from public preview.

    An authorized server-side verifier must confirm the exact source pricing
    options, shared non-virtual flight route from novirt=0, and aggregate room
    allotment for the entire requested party. Setting flags based only on a
    price-list candidate is not verification.
    """
    buyer_session_id: str
    source_preview_id: str
    country_id: str
    source_options: tuple[PrivateRoomSourceOption, ...]
    checked_at: datetime
    exact_price_list_checked: bool
    actual_age_scope_checked: bool
    room_capacity_for_full_party_checked: bool
    shared_route_novirt_zero_checked: bool
    infant_policies_by_room: tuple[bool, ...]
    status: str = "PRIVATE_OPERATOR_PREFLIGHT"

    def __repr__(self):
        return "<IndependentOperatorPreflight: REDACTED>"


def _utc(value):
    if not isinstance(value, datetime) or value.tzinfo is None:
        return None
    return value.astimezone(timezone.utc)


def _authorized(grant, now):
    if not isinstance(grant, PrivateBuyerPriceAuthorization):
        return False
    expires = _utc(grant.expires_at)
    return (
        grant.authenticated is True and
        grant.personal_data_consent_verified is True and
        grant.supplier_price_api_permission_verified is True and
        isinstance(grant.buyer_session_id, str) and
        re.fullmatch(r"[A-Za-z0-9_-]{16,128}", grant.buyer_session_id)
        is not None and
        expires is not None and
        now < expires <= now + timedelta(hours=24)
    )


def _preflight_ok(proof, grant, preview, country_id, options, rooms, now):
    if not isinstance(proof, IndependentOperatorPreflight):
        return False
    when = _utc(proof.checked_at)
    return (
        proof.status == "PRIVATE_OPERATOR_PREFLIGHT" and
        proof.buyer_session_id == grant.buyer_session_id and
        proof.source_preview_id == preview["id"] and
        proof.country_id == country_id and
        isinstance(proof.source_options, tuple) and
        proof.source_options == options and
        len(proof.source_options) == len(rooms) and
        proof.exact_price_list_checked is True and
        proof.actual_age_scope_checked is True and
        proof.room_capacity_for_full_party_checked is True and
        proof.shared_route_novirt_zero_checked is True and
        isinstance(proof.infant_policies_by_room, tuple) and
        len(proof.infant_policies_by_room) == len(rooms) and
        all(type(x) is bool for x in proof.infant_policies_by_room) and
        when is not None and
        timedelta(0) <= now - when <= timedelta(seconds=MAX_PREFLIGHT_AGE_SECONDS)
    )


def price_exact_party_read_only(*, preview, selected_rooms,
                                private_passengers_by_room,
                                private_source_candidates,
                                selected_plan_index, selected_option_indices,
                                buyer_authorization, operator_preflight,
                                private_country_id, price_client,
                                private_customer=None, now=None):
    """One explicitly authorized price-only supplier inquiry, never a booking.

    Caller responsibilities before invoking:
      1. Bind preview/source list to fresh authenticated BG response.
      2. Use private buyer session (not browser-provided buyer_id) and consent.
      3. Independently verify EXACT combined room allotments, rate options,
         non-virtual flight route and any infant seat allocation.
      4. Inject a BGReadOnlyPriceClient with genuine supplier permission.

    This interface never stores/logs supplier IDs, DOBs or passports. It
    returns only the whole-party RUB price as PRICE_ONLY_NOT_BOOKABLE.
    """
    clock = _utc(now) if now is not None else datetime.now(timezone.utc)
    if clock is None:
        raise BadOrder("Private clock invalid")
    if not _authorized(buyer_authorization, clock):
        raise NotAvailable("Private authenticated price authorization required")
    if (not isinstance(private_country_id, str) or
        re.fullmatch(r"\d{7,20}", private_country_id) is None or
        not isinstance(private_source_candidates, (list, tuple)) or
        len(private_source_candidates) > MAX_PRIVATE_PLANS):
        raise BadOrder("Trusted operator source scope invalid")

    rooms = _selected_rooms(selected_rooms)
    if (not isinstance(private_passengers_by_room, list) or
        len(private_passengers_by_room) != len(rooms) or
        not isinstance(selected_option_indices, list) or
        len(selected_option_indices) != len(rooms) or
        type(selected_plan_index) is not int):
        raise BadOrder("Selected private party option shape invalid")
    for room, passengers in zip(rooms, private_passengers_by_room):
        if (not isinstance(passengers, list) or
            len(passengers) != room["adults"] + len(room["child_ages"]) or
            any(not isinstance(p, dict) for p in passengers)):
            raise BadOrder("Selected private room passenger data invalid")

    births = [[p.get("birthday") for p in group]
              for group in private_passengers_by_room]
    exact_plans = select_exact_party_sources(
        preview, selected_rooms, births, private_source_candidates
    )
    if not 0 <= selected_plan_index < len(exact_plans):
        raise NotAvailable("Selected exact-age rate plan unavailable")
    plan = exact_plans[selected_plan_index]
    options = []
    for i, index in enumerate(selected_option_indices):
        if type(index) is not int or not 0 <= index < len(plan.group_options[i]):
            raise BadOrder("Selected private room rate option invalid")
        options.append(plan.group_options[i][index])
    chosen = tuple(options)

    if not _preflight_ok(operator_preflight, buyer_authorization,
                         preview, private_country_id, chosen, rooms, clock):
        raise NotAvailable("Fresh independent operator price preflight missing")

    # Only private source IDs become supplier fields. Never accept an
    # option-specific roommeal, otv, sr, ag or prx from browser JSON.
    supplier_groups = []
    for room_idx, (option, passengers) in enumerate(
            zip(chosen, private_passengers_by_room)):
        # Infant-policy evidence is separate from age matching: an age of
        # zero or one does not prove the ticket includes a seat.
        has_infant = any(x < 2 for x in rooms[room_idx]["child_ages"])
        infant_ok = operator_preflight.infant_policies_by_room[room_idx]
        if has_infant and not infant_ok:
            raise NotAvailable("Independent infant ticket policy missing")
        supplier_groups.append({
            "price_list_exact_match": True,
            "room_occupancy_verified": True,
            "passenger_age_scope_verified": True,
            "infant_policy_verified": infant_ok,
            "prx": option.prx,
            "template_id": option.template_id,
            "commission_id": option.commission_id,
            "source_preview_id": option.source_preview_id,
            "hotel_id": option.hotel_id,
            "start_date": option.start_date,
            "duration_nights": option.duration_nights,
            "roommeal_id": option.roommeal_id,
            "sr": option.sr,
            "otv_id": option.otv_id,
            "age_marker": option.age_marker,
            "passengers": passengers,
        })
    tour = {
        "client_tour_id": "order_" + secrets.token_hex(12),
        "source_preview_id": preview["id"],
        "country_id": private_country_id,
        "hotel_id": preview["hotel_id"],
        "prx": plan.prx,
        "template_id": plan.template_id,
        "commission_id": plan.commission_id,
        "depart_date": preview["depart_date"],
        "hotel_start_date": plan.hotel_start_date,
        "nights": preview["nights"],
    }

    # Exactly one supplier price-only operation. BGReadOnlyPriceClient is
    # responsible for strict TLS/host allowlisting, no redirects, no confirm.
    if not callable(getattr(price_client, "price_groups_only", None)):
        raise BadOrder("Authorized private supplier price client required")
    result = price_client.price_groups_only(
        tour, selected_rooms, supplier_groups, private_customer
    )
    if (not isinstance(result, dict) or
        result.get("supplier_price_readonly") is not True or
        result.get("bookable") is not False or
        result.get("availability_verified") is not False or
        result.get("flight_verified") is not False or
        type(result.get("total_rub")) is not int or
        not 0 < result["total_rub"] <= MAX_PRICE_TOTAL_RUB or
        type(result.get("groups_requested")) is not int or
        result["groups_requested"] != len(rooms)):
        raise NotAvailable("Private supplier price-only response invalid")

    expires = min(buyer_authorization.expires_at.astimezone(timezone.utc),
                  operator_preflight.checked_at.astimezone(timezone.utc)
                  + timedelta(seconds=MAX_PREFLIGHT_AGE_SECONDS))
    # No passports, DOB, operator internal IDs, per-room guessed price,
    # supplier credentials, proof, booking or final offer in return value.
    return {
        "status": "PRICE_ONLY_NOT_BOOKABLE",
        "source_preview_id": preview["id"],
        "total_rub": result["total_rub"],
        "currency": "RUB",
        "groups_requested": len(rooms),
        "supplier_total_scope": "WHOLE_TOUR",
        "expires_at": expires.isoformat(),
        "supplier_price_readonly": True,
        "quote_verified": False,
        "availability_verified": False,
        "flight_verified": False,
        "best_price_verified": False,
        "bookable": False,
        "booked": False,
        "payment_enabled": False,
    }
