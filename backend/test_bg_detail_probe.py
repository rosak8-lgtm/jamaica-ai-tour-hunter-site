import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import oracle_bg_price_detail_probe as probe
import oracle_bg_route_sync as bg

DATE=(datetime.now(timezone.utc)+timedelta(days=7)).strftime("%d.%m.%Y")
COUNTRY={"name":"Таиланд","id":"100410000051","has_tour_catalog":True,"origins":[bg.CITY_ID]}
URL=("https://export.bgoperator.ru/partners?action=price&tid=211&flt="
     +COUNTRY["id"]+"&flt2="+bg.CITY_ID+"&id_price=121132934133&data="+DATE+"&xml=11")

class DetailPriceTests(unittest.TestCase):
    def test_safe_url(self):
        url=probe.safe_url({"url":URL},COUNTRY["id"])
        self.assertTrue(url.startswith("https://export.bgoperator.ru/partners?"))
        self.assertIn("action=price",url)
    def test_reject_unapproved_hosts(self):
        with self.assertRaises(bg.SyncHold):
            probe.safe_url({"url":URL.replace("export.bgoperator.ru","evil.example")},COUNTRY["id"])
    def test_reject_other_city(self):
        with self.assertRaises(bg.SyncHold):
            probe.safe_url({"url":URL.replace(bg.CITY_ID,"100510000863")},COUNTRY["id"])
    def test_shape_redacts_values(self):
        data={"entries":[{"price":12345,"name":"private hotel"}],"secret":"do not reveal","currency":"EUR"}
        s=probe.shape(json.dumps(data).encode())
        self.assertEqual(s["format"],"JSON")
        self.assertEqual(s["rows"],1)
        self.assertNotIn("secret",str(s))
        self.assertNotIn("private hotel",str(s))
        self.assertNotIn("12345",str(s))
    def test_nested_price_metadata_is_aggregate_only(self):
        payload={"entries":[
            {"hotel":"SECRET HOTEL", "room":"DBL HB", "quota":"3",
             "prices":[{"amount":"450","RUR":"42000","ag":"12+,12+",
                        "href2":"secret-token"}]},
            {"hotel":"ANOTHER HOTEL", "isstop":["hotel"],
             "prices":[{"amount":"","ag":"2-11,12+"}]}
        ], "prx":"internal-secret"}
        result=probe.shape(json.dumps(payload).encode())
        self.assertEqual(result["rows"],2)
        self.assertEqual(result["price_rows"],2)
        self.assertEqual(result["amount_present"],1)
        self.assertEqual(result["rur_present"],1)
        self.assertEqual(result["row_stop_markers"],1)
        self.assertIn("hotel",result["entry_fields"])
        self.assertIn("RUR",result["price_fields"])
        self.assertNotIn("href2",result["price_fields"])
        self.assertNotIn("prx",str(result))
        self.assertNotIn("SECRET HOTEL",str(result))
        self.assertNotIn("42000",str(result))
    def test_probe_limit(self):
        class Api:
            def get(self,url):
                if "/yandex?" in url:
                    return json.dumps({"entries":[{"url":URL,"date":DATE}]}).encode()
                return json.dumps({"entries":[{"hotel":"Example","prices":[1,2]}]}).encode()
        result=probe.probe({"countries":[COUNTRY]},Api(),1)
        self.assertEqual(len(result),1)
        self.assertEqual(result[0]["result"]["rows"],1)
        self.assertEqual(result[0]["result"]["fields"],["entries"])
if __name__=="__main__":unittest.main()
