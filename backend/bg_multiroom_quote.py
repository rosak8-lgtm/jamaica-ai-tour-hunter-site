"""Private, READ-ONLY Biblio-Globus multi-room price-request serializer.

This module DOES NOT accept untrusted browser fields as supplier facts.
The caller must first bind every group to an authoritative operator price
option, roommeal ID, source preview and passenger-age tariff.  The operator
Tour API requests several <group> elements under one <tour> without <confirm/>.

No credentials, network calls, logging, booking, payment or storage of
personally identifiable passenger data occurs here.
Reference: https://www.bgoperator.ru/texts/tour-api.html
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
import xml.etree.ElementTree as ET

from backend.bg_tour_api_xml import (
    _require_text, _date_from_iso, _person, _customer_details,
    _xml, url_for_prx,
)
from backend.order_engine import BadOrder, NotAvailable
from backend.bg_price_age_scope import exact_ages_match

MAX_GROUPS = 5
MAX_ADULTS = 12
MAX_CHILDREN = 10
MAX_XML_BYTES = 65536


def _iso_date(value):
    if not isinstance(value, str):
        raise BadOrder("Date must be an exact ISO date")
    try:
        d = date.fromisoformat(value)
        if d.isoformat() != value:
            raise ValueError("Noncanonical date")
        return d
    except (ValueError, TypeError):
        raise BadOrder("Invalid private trip/passenger date") from None


def age_on(birthday: str, departure: str) -> int:
    """Exact attained age on the selected departure date, never a guessed DOB."""
    born, travel = _iso_date(birthday), _iso_date(departure)
    return travel.year - born.year - ((travel.month, travel.day) <
                                     (born.month, born.day))


def _selected_rooms(selected):
    if not isinstance(selected, list) or not 1 <= len(selected) <= MAX_GROUPS:
        raise BadOrder("Group count invalid")
    adults = children = 0
    safe = []
    for group in selected:
        if not isinstance(group, dict) or type(group.get("adults")) is not int:
            raise BadOrder("Adult count invalid")
        a, ages = group["adults"], group.get("child_ages")
        if not 1 <= a <= MAX_ADULTS or not isinstance(ages, list):
            raise BadOrder("Group occupants invalid")
        if len(ages) > MAX_CHILDREN or any(
            type(age) is not int or not 0 <= age <= 17 for age in ages
        ):
            raise BadOrder("Child ages invalid")
        adults += a
        children += len(ages)
        safe.append({"adults": a, "child_ages": tuple(ages)})
    if adults > MAX_ADULTS or children > MAX_CHILDREN:
        raise BadOrder("Too many travelers")
    return safe


def _source_tour(tour):
    if not isinstance(tour, dict):
        raise BadOrder("Trusted supplier tour metadata required")
    _require_text(tour.get("client_tour_id"), r"[A-Za-z0-9_-]{8,100}", 100)
    _require_text(tour.get("source_preview_id"), r"p_[a-f0-9]{24}", 26)
    _require_text(tour.get("prx"), r"[^\x00-\x1f\x7f]{1,512}", 512)
    _require_text(tour.get("country_id"), r"\d{7,20}")
    _require_text(tour.get("hotel_id"), r"\d{7,20}")
    template, commission = tour.get("template_id"), tour.get("commission_id")
    if bool(template) == bool(commission):
        raise BadOrder("Exactly one template or commission from operator price list required")
    _require_text(template or commission, r"\d{7,20}")
    if type(tour.get("nights")) is not int or not 1 <= tour["nights"] <= 180:
        raise BadOrder("Valid trip duration required")
    departure = _iso_date(tour.get("depart_date"))
    hotel_start = _iso_date(tour.get("hotel_start_date"))
    if hotel_start < departure or (hotel_start - departure).days > 4:
        raise BadOrder("Unmatched primary accommodation date")
    return departure, hotel_start


def build_group_price_request(tour: dict, selected_rooms: list[dict],
                              supplier_groups: list[dict],
                              customer: dict | None = None) -> tuple[str, bytes]:
    """Build only the initial read-only BG <tour> XML price inquiry.

    `selected_rooms`: client-requested totals/ages, *not* evidence of availability.
    `supplier_groups`: independent PRIVATE provider evidence and real passengers
    for each matching room; never supplied by the browser.
    """
    departure, hotel_start = _source_tour(tour)
    selected = _selected_rooms(selected_rooms)
    if not isinstance(supplier_groups, list) or len(supplier_groups) != len(selected):
        raise BadOrder("Supplier room groups do not match traveler rooms")

    root = ET.Element("tours")
    item = ET.SubElement(root, "tour", clientTourId=tour["client_tour_id"])
    ET.SubElement(item, "countryId").text = tour["country_id"]
    key = "comissionId" if tour.get("commission_id") else "templateId"
    ET.SubElement(item, key).text = tour.get("commission_id") or tour["template_id"]
    _customer_details(item, customer)
    groups = ET.SubElement(item, "groups")
    identity_keys = set()
    # One selected flight itinerary for every room in the same tour request.
    shared_sr = None

    for expected, sourced in zip(selected, supplier_groups):
        if not isinstance(sourced, dict):
            raise BadOrder("Supplier group record invalid")
        # These attestations MUST be set by a private source-matching adapter,
        # never copied from request JSON or a public preview.
        if (sourced.get("price_list_exact_match") is not True or
            sourced.get("room_occupancy_verified") is not True or
            sourced.get("passenger_age_scope_verified") is not True):
            raise NotAvailable("Supplier room / age-price source not independently verified")
        if (sourced.get("prx") != tour["prx"] or
            sourced.get("template_id") != tour.get("template_id") or
            sourced.get("commission_id") != tour.get("commission_id")):
            raise NotAvailable("Supplier price-list source differs across rooms")
        if (sourced.get("source_preview_id") != tour["source_preview_id"] or
            sourced.get("hotel_id") != tour["hotel_id"] or
            sourced.get("start_date") != hotel_start.isoformat() or
            type(sourced.get("duration_nights")) is not int or
            sourced["duration_nights"] != tour["nights"]):
            raise NotAvailable("Supplier group does not match selected preview")
        roommeal = _require_text(sourced.get("roommeal_id"), r"\d{7,20}")
        sr = _require_text(sourced.get("sr"), r"[^\x00-\x1f\x7f]{1,2048}", 2048)
        if shared_sr is None:
            shared_sr = sr
        elif sr != shared_sr:
            raise NotAvailable("Multiple incompatible flight itineraries in one tour")
        passengers = sourced.get("passengers")
        if not isinstance(passengers, list) or len(passengers) != (
            expected["adults"] + len(expected["child_ages"])
        ):
            raise BadOrder("Private passenger count does not match the selected group")
        group = ET.SubElement(groups, "group")
        ET.SubElement(group, "startDate").text = _date_from_iso(sourced["start_date"])
        if sourced.get("insurance_code") is not None:
            ins = _require_text(sourced["insurance_code"],
                                r"[A-Za-z0-9_.+-]{1,80}", 80)
            ET.SubElement(group, "ins").text = ins
        ET.SubElement(group, "roommeal",
                      duration=str(sourced["duration_nights"])).text = roommeal
        ET.SubElement(group, "sr").text = sr
        # BG Tour API documents <otv> from the exact prices[].href2 option,
        # not from the neighboring row or a browser-selected candidate.
        # Only a private source-matched numeric token may be serialized.
        if sourced.get("otv_id") is not None:
            ET.SubElement(group, "otv").text = _require_text(
                sourced["otv_id"], r"\d{7,20}")
        people = ET.SubElement(group, "persons")
        infant_parent_ids = set()
        actual_ages = []

        # Strict ordering: adults first, then children in chosen age order.
        for position, p in enumerate(passengers):
            if not isinstance(p, dict):
                raise BadOrder("Private passenger identity invalid")
            actual_age = age_on(p.get("birthday"), tour["depart_date"])
            actual_ages.append(actual_age)
            if position < expected["adults"]:
                if actual_age < 18 or actual_age > 120:
                    raise BadOrder("Adult birthdate does not match selected group")
                if "infant_allocation" in p or "parentnum" in p:
                    raise BadOrder("Adult cannot use infant allocation")
            else:
                intended_age = expected["child_ages"][position - expected["adults"]]
                if actual_age != intended_age:
                    raise BadOrder("Child birthdate / age at departure mismatch")
                if actual_age < 2:
                    if (sourced.get("infant_policy_verified") is not True or
                        p.get("infant_allocation") not in ("WITH_SEAT", "NO_SEAT")):
                        raise NotAvailable("Infant seat and tariff must be independently resolved")
                    if p["infant_allocation"] == "NO_SEAT":
                        parentnum = p.get("parentnum")
                        if (type(parentnum) is not int or
                            not 1 <= parentnum <= expected["adults"] or
                            parentnum in infant_parent_ids):
                            raise BadOrder("Infant without seat requires one unique adult")
                        infant_parent_ids.add(parentnum)
                    elif "parentnum" in p:
                        raise BadOrder("Seated infant must not have parentnum")
                elif "infant_allocation" in p or "parentnum" in p:
                    raise BadOrder("Only confirmed infant policy may use parentnum")
            identity = (p.get("citizenship"), p.get("passport_series"),
                        p.get("passport_number"))
            if not all(isinstance(v, str) and v for v in identity) or identity in identity_keys:
                raise BadOrder("Passenger identity missing or repeated across rooms")
            identity_keys.add(identity)
            if _iso_date(p.get("passport_expires")) < departure:
                raise BadOrder("Expired travel document cannot be priced as bookable")
            _person(people, p)  # Reuse existing private passport/date validation.
            if position >= expected["adults"] and actual_age < 2 and (
                p["infant_allocation"] == "NO_SEAT"
            ):
                ET.SubElement(people[-1], "parentnum").text = str(p["parentnum"])

        # The caller's "passenger_age_scope_verified" boolean is NOT proof:
        # cross-check real DOB-derived ages with the SAME prices[].ag marker
        # carried from the trusted private source option. Reject unknown
        # formats and tariffs before any authorized network call.
        if not exact_ages_match(actual_ages, sourced.get("age_marker")):
            raise NotAvailable("Real passenger ages do not match chosen price option")

    payload = ET.tostring(root, encoding="utf-8", xml_declaration=True)
    if len(payload) > MAX_XML_BYTES or b"<confirm" in payload:
        raise BadOrder("Read-only group price request invalid")
    return url_for_prx(tour["prx"]), payload


def _one_rub_amount(price):
    if (price is None or price.findtext("currency") not in ("RUR", "RUB")):
        raise NotAvailable("Supplier group price currency is not RUB")
    try:
        raw = (price.findtext("fullamount") or "").strip()
        amount = Decimal(raw)
        if (not amount.is_finite() or amount != amount.to_integral_value()
                or not 0 < amount <= 100_000_000):
            raise ValueError("amount")
        return int(amount)
    except (InvalidOperation, ValueError):
        raise NotAvailable("Supplier group gross retail price missing") from None


def _unique_rub_retail(sums):
    """Select exactly one RUR/RUB gross retail amount from currency alternatives.

    Official Tour API returns one <tour>/<sum> per currency, often USD + RUR.
    Never read <amount> (agent net), add currencies, or silently pick the first.
    """
    rub = [entry for entry in sums
           if (entry.findtext("currency") or "").strip() in ("RUR", "RUB")]
    if len(rub) != 1:
        raise NotAvailable("Missing or ambiguous RUB retail tour total")
    return _one_rub_amount(rub[0])


def parse_group_price_response(raw: bytes, client_tour_id: str,
                               *, expected_groups: int) -> dict:
    """One whole-tour retail cost from the official Tour API *price* reply.

    Actual documented reply: <tours>/<tour clientTourId=...>/<sum>, with
    currency alternatives; it does NOT enumerate one <sum> per room group.
    The caller already supplied and validated exactly expected_groups in
    its private XML request, but the reply does not echo their individual
    prices. Never claim per-room subtotals or hotel/flight availability.
    If an operator extension returns group subtotals, reconcile all of them
    with the whole-tour total or fail closed.
    """
    if type(expected_groups) is not int or not 1 <= expected_groups <= MAX_GROUPS:
        raise BadOrder("Expected supplier group count invalid")
    item = _xml(raw)
    if (item.get("clientTourId") != client_tour_id or
        item.find(".//confirm") is not None):
        raise NotAvailable("Supplier response itinerary mismatch")
    total = _unique_rub_retail(item.findall("sum"))

    # No groups are present in the documented 3.1 reply. If the provider
    # ever includes group sums, they must be complete and reconcile exactly.
    direct = item.findall("group")
    wrapped = item.findall("groups/group")
    if direct and wrapped:
        raise NotAvailable("Ambiguous supplier group response layouts")
    groups = direct or wrapped
    itemized = bool(groups)
    if itemized:
        if len(groups) != expected_groups:
            raise NotAvailable("Supplier omitted a requested room group")
        subtotals = [_unique_rub_retail(group.findall("sum"))
                     for group in groups]
        if sum(subtotals) != total:
            raise NotAvailable("Group subtotals differ from whole-tour retail total")

    return {"client_tour_id": client_tour_id, "currency": "RUB",
            "total_rub": total, "groups_requested": expected_groups,
            "supplier_total_scope": "WHOLE_TOUR",
            "group_price_breakdown_verified": itemized,
            "supplier_price_readonly": True, "availability_verified": False,
            "flight_verified": False, "bookable": False}
