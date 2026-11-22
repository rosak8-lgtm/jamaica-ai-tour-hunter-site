"""Offline byte-bound catalog regression checks; all rows are synthetic."""
import unittest
from scripts.catalog_size_budget import fit_feed, encoded_size
from datetime import date

def row(i,country,*,old=False):
    return {
        "id":"p_"+format(i,"024x"),"hotel_id":"102610001486",
        "hotel":"H"*110,"country":country,"origin":"Иркутск",
        "resort":"R"*100,"room":"S"*115,
        "depart_date":"2026-12-11","nights":7,
        "status":"PREVIOUSLY_SEEN_NOT_RECHECKED" if old else "REFERENCE_PRICE_LIST_ONLY",
        "price_reference_rub":None if old else 100000,
        "price_reference_party":"UNVERIFIED" if old else "TWO_ADULTS",
        "quote_verified":False,"availability_verified":False,
        "flight_verified":False,"bookable":False,
    }

def feed(rows):
    return {"schema":"jamaica.tour-previews.v1","previews":rows,
            "countries_status":[{"country":c,"previews":0}
                for c in sorted({x["country"] for x in rows})],
            "total_candidate_previews":len(rows),
            "source_scope":{"last_24h_unrechecked_previews":sum(
                r["status"]=="PREVIOUSLY_SEEN_NOT_RECHECKED" for r in rows),
                "last_24h_unrechecked_countries":len({
                r["country"] for r in rows
                if r["status"]=="PREVIOUSLY_SEEN_NOT_RECHECKED"})},
            "indicative_two_adult_rub_count":0,
            "truncated_to_public_limit":False}

class Tests(unittest.TestCase):
    def test_oversized_60000_record_source_is_bounded_and_country_fair(self):
        # ~40MB synthetic original, MUST shrink for a 2MB trial budget.
        rows=[row(i,["Таиланд","Вьетнам","Китай","Индонезия"][i%4])
              for i in range(60000)]
        src=feed(rows)
        self.assertGreater(encoded_size(src),2_000_000)
        result,dropped=fit_feed(src,max_bytes=2_000_000)
        self.assertGreater(dropped,0)
        self.assertLessEqual(encoded_size(result),2_000_000)
        self.assertEqual({x["country"] for x in result["previews"]},
                         {"Таиланд","Вьетнам","Китай","Индонезия"})
        self.assertEqual(result["indicative_two_adult_rub_count"],len(result["previews"]))
        self.assertTrue(result["truncated_to_public_limit"])
        self.assertEqual(result["total_candidate_previews"],len(rows))
        self.assertEqual(sum(x["previews"] for x in result["countries_status"]),
                         len(result["previews"]))
        self.assertFalse(any(x["bookable"] for x in result["previews"]))

    def test_fresh_source_is_never_evicted_by_old_unpriced_source(self):
        rows=[row(i,"Непал",old=True) for i in range(4000)]
        rows.extend([row(5000+i,["Таиланд","Китай"][i%2]) for i in range(150)])
        result,miss=fit_feed(feed(rows),max_bytes=90_000)
        self.assertGreater(miss,0)
        self.assertTrue(all(x["status"]=="REFERENCE_PRICE_LIST_ONLY"
                            for x in result["previews"]))
        self.assertEqual(result["source_scope"]["last_24h_unrechecked_previews"],0)
        self.assertEqual(result["source_scope"]["last_24h_unrechecked_countries"],0)

    def test_small_source_is_not_shrunk_and_recounts_prices(self):
        source=feed([row(1,"Таиланд"),row(2,"Китай",old=True)])
        new,n=fit_feed(source,max_bytes=1_000_000)
        self.assertEqual(n,0)
        self.assertEqual(len(new["previews"]),2)
        self.assertEqual(new["indicative_two_adult_rub_count"],1)
        self.assertEqual(new["source_scope"]["last_24h_unrechecked_previews"],1)

    def test_cannot_publish_unrechecked_number_or_duplicate(self):
        record=row(1,"Таиланд",old=True)
        with self.assertRaises(ValueError):
            fit_feed(feed([{**record,"price_reference_rub":95000}]),max_bytes=3000)
        with self.assertRaises(ValueError):
            fit_feed(feed([record,record]),max_bytes=3000)
        with self.assertRaises(ValueError):
            fit_feed(feed([record]),max_bytes=999)
        with self.assertRaises(ValueError):
            fit_feed(feed([record]),max_rows=True)
