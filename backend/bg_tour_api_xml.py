"""Private BG zayavkaapi XML protocol: safe serialization, no network calls.

References:
https://www.bgoperator.ru/texts/tour-api.html

Request #1: <tour> WITHOUT <confirm/> => read-only price.
Request #2: <tour> WITH <confirm/> => creates agency application.
Never make request #2 from any public browser. The API's application ID
does NOT by itself prove flight/hotel booking was finally confirmed.

Passenger identities belong ONLY in a private server over TLS. This module
does not read credentials, write logs, perform HTTP, payments or reservations.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation
import re
import urllib.parse
import xml.etree.ElementTree as ET

from backend.order_engine import BadOrder, NotAvailable

BG_HOST="https://www.bgoperator.ru/zayavkaapi"
BG_CONFIRM_TAG="confirm"

def _require_text(value,pattern:str,max_chars=255):
    if not isinstance(value,str) or len(value)>max_chars or not re.fullmatch(pattern,value):
        raise BadOrder("Invalid private operator request field")
    return value

def _date_from_iso(value:str)->str:
    if not isinstance(value,str):
        raise BadOrder("Invalid tour date")
    try:
        x=date.fromisoformat(value)
        if x.isoformat()!=value:raise ValueError("not exact ISO")
        return x.strftime("%d.%m.%Y")
    except ValueError as exc:
        raise BadOrder("Invalid passenger or travel date") from exc

def _person(node,person:dict):
    if not isinstance(person,dict):
        raise BadOrder("Passenger record invalid")
    specs=(
       ("birthday",_date_from_iso(person.get("birthday"))),
       ("firstName",_require_text(person.get("first_name"),r"[A-Z][A-Z '-]{0,79}",80)),
       ("lastName",_require_text(person.get("last_name"),r"[A-Z][A-Z '-]{0,79}",80)),
       ("citizenship",_require_text(person.get("citizenship"),r"\d{7,20}")),
       ("passportSeries",_require_text(person.get("passport_series"),r"[A-Z0-9]{1,15}",15)),
       ("passportNumber",_require_text(person.get("passport_number"),r"[A-Z0-9]{4,20}",20)),
       ("passportTill",_date_from_iso(person.get("passport_expires"))),
       ("gender",_require_text(person.get("gender"),r"[mf]",1)),
    )
    try:
        if date.fromisoformat(person["passport_expires"]) <= date.fromisoformat(person["birthday"]):
            raise BadOrder("Passport date invalid")
    except ValueError as exc:
        raise BadOrder("Date invalid") from exc
    p=ET.SubElement(node,"person")
    for key,value in specs:ET.SubElement(p,key).text=value
    middle=person.get("middle_name")
    absent=person.get("no_middle_name") is True
    if middle and absent:raise BadOrder("Middle name status contradictory")
    if middle:
        ET.SubElement(p,"middleName").text=_require_text(
            middle,r"[A-ZА-ЯЁ][A-ZА-ЯЁ '-]{0,79}",80)
    elif absent:
        ET.SubElement(p,"notHaveMiddleName").text="1"

def _customer_details(item:ET.Element,customer:dict|None):
    """Optional but strongly recommended customer GAIS EP data."""
    if customer is None:
        return
    if not isinstance(customer,dict):
        raise BadOrder("Customer identity must be a private verified record")
    fields=(
       ("customerFirstName",_require_text(customer.get("first_name"),r"[A-Z][A-Z '-]{0,79}",80)),
       ("customerLastName",_require_text(customer.get("last_name"),r"[A-Z][A-Z '-]{0,79}",80)),
       ("customerAddress",_require_text(customer.get("address"),r"[^<>\\x00-\\x1f\\x7f]{8,160}",160)),
       ("customerCitizen",_require_text(customer.get("citizenship"),r"\\d{7,20}",20)),
       ("customerPassportSeries",_require_text(customer.get("passport_series"),r"[A-Z0-9]{1,15}",15)),
       ("customerPassportNumber",_require_text(customer.get("passport_number"),r"[A-Z0-9]{4,20}",20)),
    )
    for key,val in fields:
        ET.SubElement(item,key).text=val
    if customer.get("middle_name"):
        ET.SubElement(item,"customerMiddleName").text=_require_text(
            customer["middle_name"],r"[A-ZА-ЯЁ][A-ZА-ЯЁ '-]{0,79}",80)
    if customer.get("phone"):
        ET.SubElement(item,"customerPhone").text=_require_text(
            customer["phone"],r"[+0-9() -]{7,25}",25)
    if customer.get("email"):
        ET.SubElement(item,"customerEmail").text=_require_text(
            customer["email"],r"[A-Za-z0-9.!#$%&'*+/=?^_`{|}~-]+@[A-Za-z0-9.-]+\\.[A-Za-z]{2,30}",120)

def _check_model(tour,persons):
    if not isinstance(tour,dict):
        raise BadOrder("Tour source record invalid")
    if not isinstance(persons,list) or len(persons)!=2:
        raise NotAvailable("Only two adult passengers currently supported")
    _require_text(tour.get("client_tour_id"),r"[A-Za-z0-9_-]{8,100}",100)
    _require_text(tour.get("prx"),r"[^\x00-\x1f\x7f]{1,512}",512)
    _require_text(tour.get("country_id"),r"\d{7,20}")
    template=tour.get("template_id")
    commission=tour.get("commission_id")
    if bool(template)==bool(commission):
        raise BadOrder("Exactly one private templateId or comissionId required")
    _require_text(template if template else commission,r"\d{7,20}")
    _require_text(tour.get("roommeal_id"),r"\d{7,20}")
    try:
        duration=tour["duration_nights"]
        if type(duration) is not int or not 1<=duration<=180:raise BadOrder("Invalid nights")
    except KeyError as exc:raise BadOrder("Nights required") from exc
    _date_from_iso(tour.get("start_date"))
    _require_text(tour.get("sr"),r"[^\x00-\x1f\x7f]{1,2048}",2048)
    if tour.get("insurance_code") is not None:
        _require_text(tour.get("insurance_code"),r"[A-Za-z0-9_.+-]{1,80}",80)

def url_for_prx(prx:str)->str:
    _require_text(prx,r"[^\x00-\x1f\x7f]{1,512}",512)
    # Exact required order: ?prx=<encoded>&action=createtour
    return BG_HOST+"?prx="+urllib.parse.quote(prx,safe="")+"&action=createtour"

def build_price_request(tour:dict,persons:list[dict],
                        customer:dict|None=None)->tuple[str,bytes]:
    """Build a READ-ONLY price inquiry; never produces <confirm/>."""
    _check_model(tour,persons)
    root=ET.Element("tours")
    item=ET.SubElement(root,"tour",clientTourId=tour["client_tour_id"])
    ET.SubElement(item,"countryId").text=tour["country_id"]
    key="comissionId" if tour.get("commission_id") else "templateId"
    ET.SubElement(item,key).text=tour.get("commission_id") or tour["template_id"]
    _customer_details(item,customer)
    groups=ET.SubElement(item,"groups")
    group=ET.SubElement(groups,"group")
    ET.SubElement(group,"startDate").text=_date_from_iso(tour["start_date"])
    if tour.get("insurance_code"):
        ET.SubElement(group,"ins").text=tour["insurance_code"]
    ET.SubElement(group,"roommeal",duration=str(tour["duration_nights"])).text=tour["roommeal_id"]
    ET.SubElement(group,"sr").text=tour["sr"]
    people=ET.SubElement(group,"persons")
    for person in persons:_person(people,person)
    body=ET.tostring(root,encoding="utf-8",xml_declaration=True)
    if b"<confirm" in body:
        raise BadOrder("Price inquiry must never include confirmation")
    return url_for_prx(tour["prx"]),body

def add_confirm_only_with_paid_gate(price_request:bytes,*,paid_and_verified:bool,
                                    third_quote_exact:bool,
                                    buyer_contract_signature_verified:bool)->bytes:
    """Internal serializer only; final authorization belongs to signed PSP/order DB.

    Do not expose these booleans to public callers. No HTTP request is sent.
    """
    if (paid_and_verified is not True or third_quote_exact is not True or
        buyer_contract_signature_verified is not True):
        raise BadOrder("Booking is forbidden before payment, 3rd quote and signed contract")
    if not isinstance(price_request,bytes) or len(price_request)>65536 or b"<!DOCTYPE" in price_request.upper():
        raise BadOrder("Invalid private operator request")
    root=ET.fromstring(price_request)
    if root.tag!="tours" or len(root)!=1 or root[0].tag!="tour":
        raise BadOrder("Only one authorized agency order per request")
    if root.find(".//confirm") is not None:
        raise BadOrder("Confirmation cannot be repeated")
    # Provider requires <confirm/> INSIDE selected <tour>
    ET.SubElement(root[0],"confirm")
    return ET.tostring(root,encoding="utf-8",xml_declaration=True)

def _xml(raw:bytes):
    if not isinstance(raw,bytes) or len(raw)>65536 or b"<!DOCTYPE" in raw.upper() or b"<!ENTITY" in raw.upper():
        raise NotAvailable("Unsafe or too large operator XML response")
    try:
        root=ET.fromstring(raw)
    except ET.ParseError as exc:
        raise NotAvailable("Malformed operator XML") from exc
    if root.tag!="tours" or len(root)!=1 or root[0].tag!="tour":
        raise NotAvailable("Unknown operator XML response")
    return root[0]

def parse_price_response(raw:bytes,client_tour_id:str)->dict:
    """FULLAMOUNT (retail gross), NEVER amount (agent payable net)."""
    item=_xml(raw)
    if item.get("clientTourId")!=client_tour_id:
        raise NotAvailable("Operator response tour mismatch")
    amounts=[]
    for price in item.findall("sum"):
        if (price.findtext("currency") or "").strip() not in ("RUR","RUB"):
            continue
        value=(price.findtext("fullamount") or "").strip()
        try:
            amount=Decimal(value)
            if amount.is_finite() and amount>0 and amount<=100_000_000 and amount==amount.to_integral_value():
                amounts.append(int(amount))
        except InvalidOperation:continue
    if len(set(amounts))!=1:
        raise NotAvailable("No unambiguous ruble retail fullamount")
    return {"client_tour_id":client_tour_id,"currency":"RUB",
            "total_rub":amounts[0],"operator_price_readonly":True}

def parse_created_application(raw:bytes,client_tour_id:str)->dict:
    """An application ID is NOT confirmation of hotel/flight allocation."""
    item=_xml(raw)
    if item.get("clientTourId")!=client_tour_id:
        raise NotAvailable("Operator application response mismatch")
    number=_require_text(item.findtext("number"),r"\d{4,25}")
    id_=_require_text(item.findtext("id"),r"\d{6,25}")
    return {"status":"SUBMITTED","supplier_booking_id":id_,
            "supplier_application_number":number,
            "hotel_confirmed":False,"flight_confirmed":False}
