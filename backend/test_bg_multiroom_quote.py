"""No production calls or real passenger data: synthetic offline fixtures only."""
import copy
import unittest
import xml.etree.ElementTree as ET

from backend.bg_multiroom_quote import (
    age_on, build_group_price_request, parse_group_price_response
)
from backend.bg_read_only_price_client import BGReadOnlyPriceClient
from backend.order_engine import BadOrder, NotAvailable

TOUR = {
    "client_tour_id": "order_abcdefghijklmnop",
    "source_preview_id": "p_" + "a"*24,
    "prx": "TEST_PRIVATE_PRX",
    "country_id": "100410504525",
    "hotel_id": "102616490643",
    "template_id": "121178311485",
    "depart_date": "2026-12-11",
    "hotel_start_date": "2026-12-11",
    "nights": 7,
}

ROOMS = [
    {"adults": 2, "child_ages": [6, 12]},
    {"adults": 1, "child_ages": [4]},
]


def passenger(first, number, dob):
    return {
        "birthday": dob, "first_name": first, "last_name": "TESTOV",
        "citizenship": "100410000050",
        "passport_series": "AA",
        "passport_number": number,
        "passport_expires": "2031-11-11",
        "gender": "m",
    }


def groups():
    people1 = [
        passenger("IVAN", "10000001", "1990-06-15"),
        passenger("ANNA", "10000002", "1992-03-14"),
        passenger("CHILD", "10000003", "2020-01-01"),
        passenger("TEEN", "10000004", "2014-06-01"),
    ]
    people2 = [
        passenger("PAVEL", "10000005", "1988-08-20"),
        passenger("KID", "10000006", "2022-06-01"),
    ]
    common = {
        "price_list_exact_match": True,
        "room_occupancy_verified": True,
        "passenger_age_scope_verified": True,
        "source_preview_id": TOUR["source_preview_id"],
        "hotel_id": TOUR["hotel_id"],
        "start_date": TOUR["hotel_start_date"],
        "duration_nights": TOUR["nights"],
        "sr": "SYNTHETIC_SR_NOT_A_SUPPLIER_BOOKING",
    }
    return [
        {**common, "roommeal_id": "104623691678", "passengers": people1},
        {**common, "roommeal_id": "104623691679", "passengers": people2},
    ]


# Mirrors the documented BG Tour API 3.1 response: one tour total,
# multiple currency sums, NO required group-level price breakdown.
RESPONSE = b"""<tours><tour clientTourId="order_abcdefghijklmnop">
    <sum><currency>USD</currency><fullamount>2600.0</fullamount>
      <comission>260.0</comission><amount>2340.0</amount></sum>
    <sum><currency>RUR</currency><fullamount>185000.0</fullamount>
      <comission>18500.0</comission><amount>166500.0</amount></sum>
</tour></tours>"""

ITEMIZED_RESPONSE = b"""<tours><tour clientTourId="order_abcdefghijklmnop">
    <group><sum><currency>RUR</currency><fullamount>120000.0</fullamount>
      <amount>80000</amount></sum></group>
    <group><sum><currency>RUB</currency><fullamount>65000</fullamount>
      <amount>40000</amount></sum></group>
    <sum><currency>RUB</currency><fullamount>185000.0</fullamount></sum>
</tour></tours>"""


class Tests(unittest.TestCase):
    def test_birthday_boundaries_are_based_on_departure_not_today(self):
        self.assertEqual(age_on("2020-12-12", "2026-12-11"), 5)
        self.assertEqual(age_on("2020-12-11", "2026-12-11"), 6)
        self.assertEqual(age_on("2008-12-12", "2026-12-11"), 17)
        self.assertEqual(age_on("2008-12-11", "2026-12-11"), 18)
        with self.assertRaises(BadOrder):
            age_on("2020-02-30", "2026-12-11")

    def test_exact_two_group_price_request_and_no_booking(self):
        url, raw = build_group_price_request(TOUR, ROOMS, groups())
        self.assertTrue(url.startswith("https://www.bgoperator.ru/zayavkaapi?prx="))
        self.assertNotIn("10000001", url)
        self.assertNotIn("CHILD", url)
        self.assertNotIn("confirm", raw.decode().lower())
        root = ET.fromstring(raw)
        self.assertEqual(len(root.findall("tour/groups/group")), 2)
        self.assertEqual(len(root.findall("tour/groups/group/persons/person")), 6)
        self.assertEqual(
            [x.text for x in root.findall("tour/groups/group/roommeal")],
            ["104623691678", "104623691679"],
        )
        self.assertEqual(
            [x.text for x in root.findall("tour/groups/group/startDate")],
            ["11.12.2026", "11.12.2026"],
        )
        self.assertIsNone(root.find("tour/confirm"))
        self.assertEqual(root.findtext("tour/templateId"), TOUR["template_id"])

    def test_missing_supplier_matching_flags_blocks_before_network(self):
        for key in ("price_list_exact_match", "room_occupancy_verified",
                    "passenger_age_scope_verified"):
            g = groups()
            g[1][key] = False
            with self.subTest(flag=key), self.assertRaises(NotAvailable):
                build_group_price_request(TOUR, ROOMS, g)

    def test_hotel_room_date_preview_and_nights_must_match(self):
        for key, changed in (
            ("source_preview_id", "p_"+"f"*24),
            ("hotel_id", "100000000000"),
            ("start_date", "2026-12-12"),
            ("duration_nights", 8),
        ):
            g = groups()
            g[1][key] = changed
            with self.subTest(key=key), self.assertRaises(NotAvailable):
                build_group_price_request(TOUR, ROOMS, g)

    def test_wrong_age_and_missing_child_passport_block(self):
        for mutate in ("wrong_age", "no_passport", "expired_passport",
                       "duplicate_passport"):
            g = groups()
            p = g[1]["passengers"][1]
            if mutate == "wrong_age":
                p["birthday"] = "2021-06-01"
            if mutate == "no_passport":
                p.pop("passport_number")
            if mutate == "expired_passport":
                p["passport_expires"] = "2026-12-10"
            if mutate == "duplicate_passport":
                p["passport_number"] = g[0]["passengers"][0]["passport_number"]
            with self.subTest(mutation=mutate), self.assertRaises(BadOrder):
                build_group_price_request(TOUR, ROOMS, g)

    def test_multiple_groups_and_totals_are_strict(self):
        for rooms, sourced in (
            (ROOMS + [{"adults":1,"child_ages":[]}], groups()),
            ([{"adults":13,"child_ages":[]}], [groups()[0]]),
            ([{"adults":True,"child_ages":[]}], [groups()[0]]),
            ([{"adults":2,"child_ages":[6,None]}], groups()),
            ([{"adults":1,"child_ages":list(range(11))}], [groups()[0]]),
        ):
            with self.assertRaises(BadOrder):
                build_group_price_request(TOUR, rooms, sourced)

    def test_one_infant_without_seat_requires_explicit_parent_and_policy(self):
        g = groups()
        rooms = copy.deepcopy(ROOMS)
        rooms[1]["child_ages"] = [1]
        baby = g[1]["passengers"][1]
        baby["birthday"] = "2025-01-01"
        baby["infant_allocation"] = "NO_SEAT"
        baby["parentnum"] = 1
        with self.assertRaises(NotAvailable):
            build_group_price_request(TOUR, rooms, g)
        g[1]["infant_policy_verified"] = True
        _, raw = build_group_price_request(TOUR, rooms, g)
        root = ET.fromstring(raw)
        self.assertEqual(
            root.findtext("tour/groups/group[2]/persons/person[2]/parentnum"),
            "1",
        )
        g[1]["passengers"][1]["parentnum"] = 2
        with self.assertRaises(BadOrder):
            build_group_price_request(TOUR, rooms, g)
        del g[1]["passengers"][1]["parentnum"]
        g[1]["passengers"][1]["infant_allocation"] = "WITH_SEAT"
        _, raw = build_group_price_request(TOUR, rooms, g)
        self.assertIsNone(ET.fromstring(raw).find(".//parentnum"))

    def test_documented_tour_level_rub_gross_is_not_agent_net_or_usd(self):
        result = parse_group_price_response(
            RESPONSE, TOUR["client_tour_id"], expected_groups=2
        )
        self.assertEqual(result["total_rub"], 185000)
        self.assertEqual(result["groups_requested"], 2)
        self.assertEqual(result["supplier_total_scope"], "WHOLE_TOUR")
        self.assertFalse(result["group_price_breakdown_verified"])
        self.assertTrue(result["supplier_price_readonly"])
        self.assertFalse(result["bookable"])
        self.assertFalse(result["flight_verified"])
        self.assertFalse(result["availability_verified"])
        self.assertNotIn("166500", str(result))
        self.assertNotIn("2340", str(result))

    def test_optional_complete_group_subtotals_are_reconciled(self):
        result = parse_group_price_response(
            ITEMIZED_RESPONSE, TOUR["client_tour_id"], expected_groups=2
        )
        self.assertEqual(result["total_rub"], 185000)
        self.assertTrue(result["group_price_breakdown_verified"])
        self.assertFalse(result["bookable"])

    def test_ambiguous_or_invalid_whole_tour_reply_is_rejected(self):
        bad = [
            RESPONSE.replace(b"<currency>RUR</currency>", b"<currency>USD</currency>"),
            RESPONSE.replace(b"<fullamount>185000.0</fullamount>",
                             b"<amount>185000.0</amount>"),
            RESPONSE.replace(b"<fullamount>185000.0</fullamount>",
                             b"<fullamount>185000.50</fullamount>"),
            RESPONSE.replace(b"<fullamount>185000.0</fullamount>",
                             b"<fullamount>NaN</fullamount>"),
            RESPONSE.replace(b"<fullamount>185000.0</fullamount>",
                             b"<fullamount>-185000.0</fullamount>"),
            RESPONSE.replace(b"</tour>", b"<sum><currency>RUB</currency>"
                                           b"<fullamount>185000</fullamount></sum></tour>"),
            RESPONSE.replace(b'<tour clientTourId="order_abcdefghijklmnop">',
                             b'<tour clientTourId="another">'),
            RESPONSE.replace(b"</tour>", b"<confirm/></tour>"),
            ITEMIZED_RESPONSE.replace(b"<fullamount>65000</fullamount>",
                                      b"<fullamount>64000</fullamount>"),
            ITEMIZED_RESPONSE.replace(b"<group><sum><currency>RUB",
                                      b"<wrong><sum><currency>RUB"),
        ]
        for raw in bad:
            with self.subTest(raw=raw[:65]), self.assertRaises(NotAvailable):
                parse_group_price_response(raw, TOUR["client_tour_id"],
                                           expected_groups=2)
        with self.assertRaises(BadOrder):
            parse_group_price_response(RESPONSE, TOUR["client_tour_id"],
                                       expected_groups=0)
        with self.assertRaises(BadOrder):
            parse_group_price_response(RESPONSE, TOUR["client_tour_id"],
                                       expected_groups=True)


class FakeOpener:
    def __init__(self):
        self.calls = []

    def open(self, req, timeout):
        self.calls.append(req)
        class Response:
            status = 200
            def __init__(self, content): self.content = content
            def read(self, length): return self.content[:length]
            def __enter__(self): return self
            def __exit__(self, *args): return False
        return Response(b"LOGIN_OK" if len(self.calls) == 1 else RESPONSE)


class ClientTests(unittest.TestCase):
    def test_private_client_only_sends_read_only_two_group_xml(self):
        opener = FakeOpener()
        client = BGReadOnlyPriceClient("test_account", "test_secret", opener=opener)
        result = client.price_groups_only(TOUR, ROOMS, groups())
        self.assertEqual(result["total_rub"], 185000)
        self.assertFalse(result["bookable"])
        self.assertFalse(result["hotel_verified"])
        self.assertEqual(len(opener.calls), 2)
        self.assertEqual(opener.calls[1].get_method(), "POST")
        self.assertEqual(ET.fromstring(opener.calls[1].data).findall(
            "tour/groups/group/persons/person").__len__(), 6)
        self.assertIsNone(ET.fromstring(opener.calls[1].data).find("tour/confirm"))

    def test_no_authentication_called_if_room_source_unverified(self):
        opener = FakeOpener()
        client = BGReadOnlyPriceClient("test_account", "test_secret", opener=opener)
        g = groups()
        g[0]["room_occupancy_verified"] = False
        with self.assertRaises(NotAvailable):
            client.price_groups_only(TOUR, ROOMS, g)
        self.assertEqual(len(opener.calls), 0)


if __name__ == "__main__":
    unittest.main()
