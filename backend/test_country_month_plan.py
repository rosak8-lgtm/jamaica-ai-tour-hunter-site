import unittest
from datetime import datetime,timezone
from scripts.country_month_plan import plan

def fixture():
    return {"schema":"jamaica.tour-previews.v1","refreshed_at_utc":"2026-11-25T08:00:00Z",
            "total_published_previews":2,
            "previews":[{"origin":"Иркутск","country":"Китай","depart_date":"2026-12-19"},
                        {"origin":"Иркутск","country":"Таиланд","depart_date":"2026-12-01"}],
            "countries_status":[{"country":"Китай","previews":1},{"country":"Таиланд","previews":1},{"country":"Египет","previews":0}],
            "search_coverage":{"classification":"SOURCE_SCAN_ONLY_NOT_OFFERS","countries":[
                {"country":"Китай","source_rows_observed":100,"sampled_departure_months":["2026-12","2027-01"]},
                {"country":"Таиланд","source_rows_observed":80,"sampled_departure_months":["2026-12"]},
                {"country":"Египет","source_rows_observed":20,"sampled_departure_months":["2026-10","2026-12","2027-01"]}]}}

class PlanTests(unittest.TestCase):
    def setUp(self):self.now=datetime(2026,11,25,tzinfo=timezone.utc)
    def test_core_and_expansion(self):
        f=fixture();p=plan(f,now=self.now)
        self.assertEqual(p["classification"],"PUBLIC_SNAPSHOT_COVERAGE_NOT_SEARCH_EXECUTION")
        rows={x["country"]:x for x in p["countries"]}
        self.assertEqual(rows["Китай"]["missing_sampled_months"],["2027-01"])
        self.assertEqual(rows["Египет"]["missing_sampled_months"],["2026-12","2027-01"])
        self.assertEqual(rows["Египет"]["published_country_count"],0)
        self.assertEqual(rows["Египет"]["role"],"EXPANSION")
        self.assertEqual(rows["Китай"]["role"],"CORE_REFRESH")
        self.assertEqual(len(f["previews"]),2)
    def test_sharded_root_not_full_month_coverage(self):
        f=fixture();f["shards"]=[{"count":10}];f["total_published_previews"]=12
        f["countries_status"][2]["previews"]=10
        p=plan(f,now=self.now)
        self.assertTrue(p["shards_incomplete"])
        self.assertTrue(all(x["missing_sampled_months"] is None for x in p["countries"]))
        self.assertEqual(next(x for x in p["countries"] if x["country"]=="Египет")["published_country_count"],10)
    def test_invalid_metadata(self):
        f=fixture();f["search_coverage"]["countries"][0]["sampled_departure_months"]=["2027-13"]
        with self.assertRaises(ValueError):plan(f,now=self.now)
    def test_duplicate(self):
        f=fixture();f["search_coverage"]["countries"].append(f["search_coverage"]["countries"][0])
        with self.assertRaises(ValueError):plan(f,now=self.now)
    def test_no_metadata_no_plan(self):
        f=fixture();f.pop("search_coverage")
        with self.assertRaises(ValueError):plan(f,now=self.now)

if __name__=="__main__":unittest.main()
