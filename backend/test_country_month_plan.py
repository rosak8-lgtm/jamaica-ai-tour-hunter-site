import unittest
from datetime import datetime,timezone
from scripts.country_month_plan import plan, expiry_plan

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

class ExpiryPlanTests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,25,8,12,tzinfo=timezone.utc)
        self.feed=fixture()
        self.visual={"schema":"jamaica.visual-selection.v1","bookable":False,
                     "quote_verified":False,"availability_verified":False,"entries":[]}
        for i,row in enumerate(self.feed["previews"]):
            pid="p_"+str(i+1)*24
            stamp="2026-11-25T08:00:00Z" if i==0 else "2026-11-25T08:10:00Z"
            row.update(id=pid,price_observed_at_utc=stamp,price_source="BG_EXACT_SELECTED_GREEN_BROWSER")
            self.visual["entries"].append({"preview_id":pid,"observed_at_utc":stamp,
                 "route_best_price_seen":True,"both_green_planes_seen":True})
    def test_prioritize_expiring_and_reserve_expansion(self):
        result=expiry_plan(self.feed,self.visual,now=self.now)
        self.assertFalse(result["execution_allowed"])
        self.assertEqual(result["slots"][0]["country"],"Китай")
        self.assertEqual(result["expiring_rows_by_country"],{"Китай":1})
        self.assertTrue(any(x["country"]=="Египет" for x in result["slots"]))
        self.assertTrue(any(x["country"]=="Китай" and x["month"]=="2027-01" for x in result["slots"]))
        slots=result["slots"]
        self.assertLessEqual(len(slots),5)
        self.assertEqual([x["earliest_offset_seconds"] for x in slots],list(range(0,180*len(slots),180)))
        self.assertEqual(len({(x["country"],x["month"]) for x in slots}),len(slots))
    def test_expired_and_mismatched_proofs_not_counted(self):
        self.feed["previews"][0]["price_observed_at_utc"]="2026-11-25T07:59:00Z"
        self.visual["entries"][1]["both_green_planes_seen"]=False
        result=expiry_plan(self.feed,self.visual,now=self.now)
        self.assertEqual(result["fresh_rows_by_country"],{})
    def test_incomplete_root_is_not_actionable(self):
        self.feed["shards"]=[{"count":10}]
        result=expiry_plan(self.feed,self.visual,now=self.now)
        self.assertEqual(result["status"],"HOLD_INCOMPLETE_ROOT")
        self.assertEqual(result["slots"],[])

if __name__=="__main__":unittest.main()
