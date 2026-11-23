"""Synthetic private-source DOB tests. No real passenger data or network."""
from dataclasses import replace
import unittest

from backend.bg_private_exact_party import select_exact_party_sources
from backend.bg_private_source_crosswalk import private_source_candidates
from backend.order_engine import BadOrder

PREVIEW = {
    "id": "p_" + "c"*24, "hotel_id": "102616490643",
    "room": "STANDARD HB", "depart_date": "2026-12-11",
    "nights": 7, "country": "Вьетнам", "origin": "Иркутск",
}
ROOMS = [
    {"adults": 2, "child_ages": [6, 12]},
    {"adults": 1, "child_ages": [4]},
]
BIRTHDAYS = [
    ["1990-06-15", "1992-03-14", "2020-01-01", "2014-06-01"],
    ["1988-08-20", "2022-06-01"],
]
PRX = "104499999900000025"
SR = "PRIVATE_SYNTHETIC_SAME_FLIGHT"


def row(room, ns, rates, **changes):
    return {
        "id_hotel": PREVIEW["hotel_id"], "tour_date": "11.12.2026",
        "duration": "7", "dt": "12.12.2026", "o_duration": "7",
        "room": room, "id_ns": ns, "sr": SR,
        "id_price": "121120516103", "_jamaica_private_prx": PRX,
        "prices": rates, **changes,
    }


def source_rows():
    return [
        row("STANDARD HB", "104623691678", [
            {"ag":"[14-99][14-99][2-11][12-17]",
             "href2":"&otv=102510005340&p=PRIVATE_TEST_DATA#"},
            {"ag":"[18-45][18-45][2-11][12-17]",
             "href2":"&otv=102510005341&p=PRIVATE_TEST_DATA#"},
        ]),
        row("FAMILY HB", "104623691679", [
            {"ag":"12+,2-11", "href2":"&otv=102510005350&p=PRIVATE_TEST_DATA#"},
        ]),
    ]


def candidates(rows=None):
    return private_source_candidates(PREVIEW, ROOMS, rows or source_rows())


class Tests(unittest.TestCase):
    def test_two_rooms_exact_age_match_no_person_data_or_price(self):
        plans = select_exact_party_sources(PREVIEW, ROOMS, BIRTHDAYS, candidates())
        self.assertEqual(len(plans), 1)
        plan = plans[0]
        self.assertEqual(plan.hotel_start_date, "2026-12-12")
        self.assertEqual(len(plan.group_options), 2)
        self.assertEqual({r.otv_id for r in plan.group_options[0]},
                         {"102510005340", "102510005341"})
        self.assertEqual(plan.group_options[1][0].otv_id, "102510005350")
        self.assertEqual(plan.status, "EXACT_AGE_SOURCE_CANDIDATE_ONLY")
        for flag in ("quote_verified","availability_verified",
                     "flight_verified","bookable"):
            self.assertIs(getattr(plan,flag), False)
        for secret in ("1990-06-15", "PRIVATE_SYNTHETIC",
                       "PRIVATE_TEST_DATA", "102510005350", PRX):
            self.assertNotIn(secret, repr(plans))

    def test_known_adult_dob_removes_only_incompatible_price_option(self):
        births=[list(x) for x in BIRTHDAYS]
        births[0][0]="1970-06-15"  # 56 years: age unknown during public search
        plans=select_exact_party_sources(PREVIEW,ROOMS,births,candidates())
        self.assertEqual(len(plans),1)
        self.assertEqual(len(plans[0].group_options[0]),1)
        self.assertEqual(plans[0].group_options[0][0].otv_id,"102510005340")

    def test_route_and_start_date_must_agree_across_rooms(self):
        rows=source_rows()
        rows[1]["sr"]="DIFFERENT_FLIGHT"
        self.assertEqual(select_exact_party_sources(
            PREVIEW,ROOMS,BIRTHDAYS,candidates(rows)),())
        rows=source_rows()
        rows[1]["dt"]="13.12.2026"
        self.assertEqual(select_exact_party_sources(
            PREVIEW,ROOMS,BIRTHDAYS,candidates(rows)),())

    def test_source_option_cannot_shift_hotel_room_or_prx(self):
        plan=candidates()[0]
        for bad in (
            replace(plan.groups[1][0],hotel_id="102616490644"),
            replace(plan.groups[1][0],prx="104499999900000026"),
            replace(plan.groups[1][0],start_date="2026-12-16"),
            replace(plan.groups[1][0],roommeal_id=""),
            replace(plan.groups[1][0],otv_id="BAD"),
        ):
            mixed=replace(plan,groups=(plan.groups[0],(bad,)))
            with self.subTest(bad_type=bad.__class__.__name__):
                self.assertEqual(select_exact_party_sources(
                    PREVIEW,ROOMS,BIRTHDAYS,(mixed,)),())
        self.assertEqual(select_exact_party_sources(
            PREVIEW,ROOMS,BIRTHDAYS,("browser-submitted-plan",)),())

    def test_invalid_birthdays_and_room_party_fail_closed(self):
        for i,j,value in (
            (0,0,"not-a-date"),
            (0,0,"2010-06-15"), # under-age supposed adult
            (0,2,"2021-01-01"), # child 5 instead of 6 at departure
            (0,3,"2013-06-01"), # child 13 instead of 12
            (1,1,"2021-06-01"), # child 5 instead of 4
            (1,0,"2100-01-01"), # future DOB
        ):
            births=[list(x) for x in BIRTHDAYS]
            births[i][j]=value
            with self.subTest(i=i,j=j),self.assertRaises(BadOrder):
                select_exact_party_sources(PREVIEW,ROOMS,births,candidates())
        with self.assertRaises(BadOrder):
            select_exact_party_sources(PREVIEW,ROOMS,[BIRTHDAYS[0]],candidates())
        with self.assertRaises(BadOrder):
            select_exact_party_sources(PREVIEW,ROOMS,[BIRTHDAYS[0],[]],candidates())
        with self.assertRaises(BadOrder):
            select_exact_party_sources({**PREVIEW,"nights":True},
                                        ROOMS,BIRTHDAYS,candidates())

    def test_same_source_different_ag_cannot_be_misassigned(self):
        rows=source_rows()
        rows[1]["prices"]=[{
            "ag":"12+,6-11", "href2":"&otv=102510005350&p=PRIVATE#"}]
        self.assertEqual(select_exact_party_sources(
            PREVIEW,ROOMS,BIRTHDAYS,candidates(rows)),())

    def test_never_replaces_missing_source_or_allocations(self):
        self.assertEqual(select_exact_party_sources(
            PREVIEW,ROOMS,BIRTHDAYS,()),())
        plan=select_exact_party_sources(
            PREVIEW,ROOMS,BIRTHDAYS,candidates())[0]
        self.assertNotIn("passengers",plan.__dict__)
        self.assertNotIn("buyer",plan.__dict__)
        self.assertNotIn("total_rub",plan.__dict__)
        self.assertFalse(plan.bookable)


if __name__ == "__main__":
    unittest.main()
