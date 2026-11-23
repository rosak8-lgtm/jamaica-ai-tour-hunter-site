"""Private exact-age BG price bridge: all supplier calls intercepted offline."""
import copy
from dataclasses import replace
from datetime import datetime, timedelta, timezone
import unittest
import xml.etree.ElementTree as ET

from backend.bg_private_exact_party import select_exact_party_sources
from backend.bg_private_source_crosswalk import private_source_candidates
from backend.bg_private_quote_bridge import (
    PrivateBuyerPriceAuthorization, IndependentOperatorPreflight,
    price_exact_party_read_only,
)
from backend.bg_read_only_price_client import BGReadOnlyPriceClient
from backend.order_engine import BadOrder, NotAvailable
from backend.test_bg_private_exact_party import (
    PREVIEW, ROOMS, BIRTHDAYS, candidates, source_rows
)
from backend.test_bg_multiroom_quote import passenger

NOW = datetime(2026, 11, 23, 12, 0, tzinfo=timezone.utc)
COUNTRY = "100410504525"
SESSION = "private_session_TEST_1234567890"


def passengers():
    result = []
    counter = 10000000
    for group in BIRTHDAYS:
        records = []
        for index, born in enumerate(group):
            counter += 1
            records.append(passenger("PERSON",str(counter),born))
        result.append(records)
    return result


def grant(**changes):
    return replace(PrivateBuyerPriceAuthorization(
        buyer_session_id=SESSION, authenticated=True,
        personal_data_consent_verified=True,
        supplier_price_api_permission_verified=True,
        expires_at=NOW + timedelta(minutes=15),
    ), **changes)


def proof(rooms=None, born=None, sources=None, **changes):
    selected_rooms = rooms if rooms is not None else ROOMS
    birthdates = born if born is not None else BIRTHDAYS
    actual = select_exact_party_sources(
        PREVIEW,selected_rooms,birthdates,sources if sources is not None else candidates()
    )
    opts = (actual[0].group_options[0][0],actual[0].group_options[1][0])
    return replace(IndependentOperatorPreflight(
        buyer_session_id=SESSION, source_preview_id=PREVIEW["id"],
        country_id=COUNTRY, source_options=opts,
        checked_at=NOW - timedelta(seconds=30),
        exact_price_list_checked=True,
        actual_age_scope_checked=True,
        room_capacity_for_full_party_checked=True,
        shared_route_novirt_zero_checked=True,
        infant_policies_by_room=(False,False),
    ),**changes)


class FakeResponse:
    status = 200
    def __init__(self,data):
        self.data=data
    def read(self,n):
        return self.data[:n]
    def __enter__(self):
        return self
    def __exit__(self,*args):
        return False


class FakeOpener:
    def __init__(self, bad_reply=False):
        self.calls=[]
        self.bad_reply=bad_reply
    def open(self,req,timeout):
        self.calls.append(req)
        if req.full_url == "https://login.bgoperator.ru/auth":
            return FakeResponse(b"LOGIN_OK")
        xml=ET.fromstring(req.data)
        tour=xml.find("tour")
        tid=tour.get("clientTourId")
        self.assert_pricing_only(xml)
        if self.bad_reply:
            return FakeResponse(b"<bad>")
        return FakeResponse(
            ('<tours><tour clientTourId="'+tid+'">'
             '<sum><currency>USD</currency><fullamount>2700</fullamount></sum>'
             '<sum><currency>RUR</currency><fullamount>185000.0</fullamount>'
             '<amount>165000</amount></sum>'
             '</tour></tours>').encode("utf-8")
        )
    def assert_pricing_only(self,xml):
        if xml.find(".//confirm") is not None:
            raise AssertionError("READ-ONLY TEST MUST NEVER BOOK")


def quote(*, buyer=None, before=None, party=None, rooms=None, sources=None,
          selected=None, client=None, **changes):
    people = party if party is not None else passengers()
    selected_rooms = rooms if rooms is not None else ROOMS
    source_data = sources if sources is not None else candidates()
    prf = before if before is not None else proof()
    kwargs = dict(preview=PREVIEW, selected_rooms=selected_rooms,
                  private_passengers_by_room=people,
                  private_source_candidates=source_data,
                  selected_plan_index=0,
                  selected_option_indices=selected if selected is not None else [0,0],
                  buyer_authorization=buyer if buyer is not None else grant(),
                  operator_preflight=prf,
                  private_country_id=COUNTRY,
                  price_client=client, now=NOW)
    kwargs.update(changes)
    return price_exact_party_read_only(**kwargs)


class Tests(unittest.TestCase):
    def test_actual_private_pipeline_calls_operator_price_only_once(self):
        opener = FakeOpener()
        result = quote(client=BGReadOnlyPriceClient(
            "synthetic_login","synthetic_secret",opener=opener
        ))
        self.assertEqual(result["status"],"PRICE_ONLY_NOT_BOOKABLE")
        self.assertEqual(result["total_rub"],185000)
        self.assertEqual(result["currency"],"RUB")
        self.assertEqual(result["groups_requested"],2)
        self.assertEqual(result["supplier_total_scope"],"WHOLE_TOUR")
        self.assertTrue(result["supplier_price_readonly"])
        self.assertEqual(len(opener.calls),2)  # auth + ONE Tour API price request
        price_request=opener.calls[1]
        self.assertEqual(price_request.get_method(),"POST")
        self.assertIn("action=createtour",price_request.full_url)
        self.assertEqual(len(ET.fromstring(price_request.data).findall(
            "tour/groups/group")),2)
        self.assertEqual([n.text for n in ET.fromstring(price_request.data).findall(
            "tour/groups/group/otv")],["102510005340","102510005350"])
        self.assertIsNone(ET.fromstring(price_request.data).find("tour/confirm"))
        for name in ("quote_verified","availability_verified","flight_verified",
                     "best_price_verified","bookable","booked","payment_enabled"):
            self.assertIs(result[name],False)
        self.assertNotIn("source_options",str(result))
        for secret in ("1990-06-15","10000001","synthetic_secret",
                       "PRIVATE_SYNTHETIC_SAME_FLIGHT","104499999900000025",
                       "102510005340",SESSION):
            self.assertNotIn(secret,str(result))
        self.assertNotIn("passengers",result)

    def test_selected_second_otv_is_preserved_from_exact_rate(self):
        opener=FakeOpener()
        p=proof()
        opts=list(p.source_options)
        opts[0]=select_exact_party_sources(
            PREVIEW,ROOMS,BIRTHDAYS,candidates()
        )[0].group_options[0][1]
        result=quote(client=BGReadOnlyPriceClient("l","p",opener=opener),
                     selected=[1,0],
                     before=replace(p,source_options=tuple(opts)))
        self.assertEqual(result["total_rub"],185000)
        self.assertIn(b"<otv>102510005341</otv>",opener.calls[1].data)

    def test_buyer_consent_session_permission_and_expiry_fail_before_network(self):
        wrong=[
            grant(authenticated=False),
            grant(personal_data_consent_verified=False),
            grant(supplier_price_api_permission_verified=False),
            grant(buyer_session_id="browser"),
            grant(expires_at=NOW - timedelta(seconds=1)),
            grant(expires_at=NOW + timedelta(hours=25)),
            grant(expires_at=NOW),
        ]
        for bad in wrong:
            opener=FakeOpener()
            with self.subTest(bad=repr(bad)), self.assertRaises(NotAvailable):
                quote(client=BGReadOnlyPriceClient("l","p",opener=opener),
                      buyer=bad)
            self.assertEqual(opener.calls,[])
        opener=FakeOpener()
        with self.assertRaises(NotAvailable):
            quote(client=BGReadOnlyPriceClient("l","p",opener=opener),
                  buyer={"authenticated":True})
        self.assertEqual(opener.calls,[])

    def test_missing_incomplete_stale_future_or_cross_party_preflight_rejected(self):
        p=proof()
        mismatches=[
            replace(p,source_preview_id="p_"+"a"*24),
            replace(p,buyer_session_id="other_private_session_0123456789"),
            replace(p,country_id="100410000000"),
            replace(p,source_options=tuple(reversed(p.source_options))),
            replace(p,exact_price_list_checked=False),
            replace(p,actual_age_scope_checked=False),
            replace(p,room_capacity_for_full_party_checked=False),
            replace(p,shared_route_novirt_zero_checked=False),
            replace(p,checked_at=NOW-timedelta(seconds=301)),
            replace(p,checked_at=NOW+timedelta(seconds=1)),
            replace(p,checked_at=NOW.replace(tzinfo=None)),
            replace(p,infant_policies_by_room=(True,)),
            replace(p,status="BROWSER_UNTRUSTED"),
            None, {"status":"PRIVATE_OPERATOR_PREFLIGHT"},
        ]
        for index,bad in enumerate(mismatches):
            opener=FakeOpener()
            with self.subTest(index=index), self.assertRaises(NotAvailable):
                quote(client=BGReadOnlyPriceClient("l","p",opener=opener),
                      before=bad if bad is not None else "NOT_SUPPLIED")
            self.assertEqual(opener.calls,[])

    def test_changed_private_passengers_dob_or_source_block_network(self):
        for index,changed in enumerate(("child_age","adult_age","passport",
                                        "missing_plan","wrong_source")):
            opener=FakeOpener()
            people=passengers()
            source_data=candidates()
            if changed=="child_age":
                people[0][2]["birthday"]="2021-01-01"
            if changed=="adult_age":
                people[0][0]["birthday"]="2018-01-01"
            if changed=="passport":
                people[1][0]["passport_number"]=""
            if changed=="missing_plan":
                source_data=()
            if changed=="wrong_source":
                other=source_rows()
                other[1]["sr"]="DIFFERENT_OPERATOR_ITINERARY"
                source_data=candidates(other)
            try:
                quote(client=BGReadOnlyPriceClient("l","p",opener=opener),
                      party=people,sources=source_data)
            except (BadOrder,NotAvailable):
                pass
            else:
                self.fail("Changed private quote data must be rejected")
            with self.subTest(changed=changed):
                self.assertEqual(opener.calls,[])

    def test_malformed_selection_is_rejected(self):
        bads=(
            dict(selected=[True,0]),dict(selected=[-1,0]),
            dict(selected=[0,99]),dict(selected=[0]),
            dict(selected_plan_index=True),
            dict(selected_plan_index=22),
        )
        for bad in bads:
            opener=FakeOpener()
            with self.subTest(bad=bad),self.assertRaises((BadOrder,NotAvailable)):
                quote(client=BGReadOnlyPriceClient("l","p",opener=opener),**bad)
            self.assertEqual(opener.calls,[])

    def test_supplier_response_schema_rejection_does_not_publish_price(self):
        class InvalidClient:
            def __init__(self,response): self.calls=0;self.response=response
            def price_groups_only(self,*args):
                self.calls+=1
                return self.response
        failures=[
            {"total_rub":185000,"supplier_price_readonly":False,
             "bookable":False,"availability_verified":False,"flight_verified":False,
             "groups_requested":2},
            {"total_rub":185000,"supplier_price_readonly":True,
             "bookable":True,"availability_verified":False,"flight_verified":False,
             "groups_requested":2},
            {"total_rub":185000,"supplier_price_readonly":True,
             "bookable":False,"availability_verified":True,"flight_verified":False,
             "groups_requested":2},
            {"total_rub":185000,"supplier_price_readonly":True,
             "bookable":False,"availability_verified":False,"flight_verified":False,
             "groups_requested":1},
            {"total_rub":True,"supplier_price_readonly":True,
             "bookable":False,"availability_verified":False,"flight_verified":False,
             "groups_requested":2},
            {}, None,
        ]
        for x in failures:
            fake=InvalidClient(x)
            with self.subTest(response=x), self.assertRaises(NotAvailable):
                quote(client=fake)
            self.assertEqual(fake.calls,1)

    def test_operator_xml_errors_do_not_turn_into_synthetic_price(self):
        opener=FakeOpener(bad_reply=True)
        with self.assertRaises(NotAvailable):
            quote(client=BGReadOnlyPriceClient("l","p",opener=opener))
        self.assertEqual(len(opener.calls),2)

    def test_infant_requires_independent_policy_and_exact_rate(self):
        rooms=copy.deepcopy(ROOMS)
        rooms[1]["child_ages"]=[1]
        people=passengers()
        people[1][1]["birthday"]="2025-01-01"
        people[1][1]["infant_allocation"]="NO_SEAT"
        people[1][1]["parentnum"]=1
        source=source_rows()
        source[1]["prices"]=[{
            "ag":"12+,0-1","href2":"&otv=102510005350&p=PRIVATE_TEST_DATA#"
        }]
        plans=private_source_candidates(PREVIEW,rooms,source)
        birthday_sets=[[x["birthday"] for x in p] for p in people]
        prf=proof(rooms=rooms,born=birthday_sets,sources=plans,
                  infant_policies_by_room=(False,False))
        opener=FakeOpener()
        with self.assertRaises(NotAvailable):
            quote(client=BGReadOnlyPriceClient("l","p",opener=opener),
                  party=people,rooms=rooms,sources=plans,before=prf)
        self.assertEqual(len(opener.calls),0)
        result=quote(client=BGReadOnlyPriceClient("l","p",opener=opener),
                     party=people,rooms=rooms,sources=plans,
                     before=replace(prf,infant_policies_by_room=(False,True)))
        self.assertEqual(result["status"],"PRICE_ONLY_NOT_BOOKABLE")
        self.assertEqual(len(opener.calls),2)


if __name__=="__main__":
    unittest.main()
