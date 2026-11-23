"""No-network tests for source-only cards, stale bot proof and 0 public tours."""
from datetime import datetime,timedelta,timezone
import unittest

from scripts import public_tour_eligibility as eligibility
from scripts import bot_visual_sidecar as visual

NOW=datetime(2026,11,23,13,0,tzinfo=timezone.utc)
ID="p_"+"a"*24
SECOND="p_"+"b"*24

def row(uid=ID,**kw):
    return {"id":uid,"hotel_id":"102612345678",
            "hotel":"ART DELUXE HOTEL","country":"Вьетнам",
            "origin":"Иркутск","resort":"Нячанг","room":"STANDARD",
            "depart_date":"2026-12-02","nights":7,
            "status":"REFERENCE_PRICE_LIST_ONLY",
            "price_reference_rub":137099,
            "price_reference_party":"TWO_ADULTS",
            "bookable":False,"quote_verified":False,
            "flight_verified":False,"availability_verified":False,
            **kw}

def source(rows):
    return {"schema":"jamaica.tour-previews.v1",
            "refreshed_at_utc":NOW.isoformat(),
            "bookable":False,"quote_verified":False,
            "availability_verified":False,
            "indicative_two_adult_rub_count":len(rows),
            "countries_status":[
                {"country":"Вьетнам","previews":len(rows)},
                {"country":"Таиланд","previews":0},
            ],"previews":rows}

def proof(uid=ID,seconds=0):
    return {"preview_id":uid,
            "observed_at_utc":(NOW-timedelta(seconds=seconds)).isoformat(),
            "route_best_price_seen":True,
            "both_green_planes_seen":True}

def receipts(entries):
    return {**visual.empty_public(),"entries":entries}

class Tests(unittest.TestCase):
    def test_zero_receipts_publishes_exactly_zero_public_tours(self):
        public=eligibility.select_public_source_rows(
            source([row(),row(SECOND)]),receipts([]),now=NOW)
        self.assertEqual(public["previews"],[])
        self.assertEqual(public["publication_rule"],
                         "BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1")
        self.assertEqual(public["indicative_two_adult_rub_count"],0)
        self.assertTrue(all(c["previews"]==0
                            for c in public["countries_status"]))
        self.assertEqual(public["bookable"],False)

    def test_only_exact_receipt_of_same_preview_id_can_publish(self):
        public=eligibility.select_public_source_rows(source([
            row(),row(SECOND)]),receipts([proof()]),now=NOW)
        self.assertEqual([x["id"] for x in public["previews"]],[ID])
        self.assertEqual(public["indicative_two_adult_rub_count"],1)
        self.assertEqual(public["countries_status"][0]["previews"],1)
        self.assertEqual(public["countries_status"][1]["previews"],0)

    def test_never_inherit_badge_or_plane_from_other_hotel(self):
        x=eligibility.select_public_source_rows(
            source([row()]),receipts([proof(SECOND)]),now=NOW)
        self.assertEqual(x["previews"],[])

    def test_receipt_expired_or_invalid_is_rejected_not_substituted(self):
        for e in [
            proof(seconds=901),
            {**proof(),"both_green_planes_seen":False},
            {**proof(),"route_best_price_seen":False},
            {**proof(),"observed_at_utc":"not-a-date"},
            {**proof(),"unsafe_url":"https://example.com"},
        ]:
            with self.subTest(e=e),self.assertRaises(ValueError):
                eligibility.select_public_source_rows(
                    source([row()]),receipts([e]),now=NOW)

    def test_old_price_list_history_cannot_publish_even_with_valid_proof(self):
        p=row(status="PREVIOUSLY_SEEN_NOT_RECHECKED",
              price_reference_rub=None,price_reference_party="UNVERIFIED")
        pub=eligibility.select_public_source_rows(
            source([p]),receipts([proof()]),now=NOW)
        self.assertEqual(pub["previews"],[])

    def test_no_injected_bookability_or_unknown_source_claims(self):
        for bad in [
            row(bookable=True),row(flight_verified=True),
            row(quote_verified=True),row(availability_verified=True),
        ]:
            pub=eligibility.select_public_source_rows(
                source([bad]),receipts([proof()]),now=NOW)
            self.assertEqual(pub["previews"],[])

    def test_keep_source_feed_unchanged_on_projection(self):
        private=source([row(),row(SECOND)])
        public=eligibility.select_public_source_rows(
            private,receipts([proof()]),now=NOW)
        self.assertEqual(len(private["previews"]),2)
        self.assertEqual(private["indicative_two_adult_rub_count"],2)
        self.assertEqual(public["previews"][0]["price_reference_rub"],137099)
        self.assertNotIn("publication_rule",private)
        self.assertIsNot(private["previews"],public["previews"])

if __name__=="__main__":
    unittest.main()
