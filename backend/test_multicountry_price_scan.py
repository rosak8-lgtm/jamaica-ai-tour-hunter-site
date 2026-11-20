import sys
import unittest
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import oracle_bg_multicountry_price_scan as scan
from oracle_bg_route_sync import SyncHold

TODAY=date(2026,11,20)
def item(country,day,code,**extra):
    p={"id":"p_"+code*24,"country":country,"origin":"Иркутск",
       "depart_date":(TODAY+timedelta(days=day)).isoformat(),
       "bookable":False,"quote_verified":False,"availability_verified":False,
       "flight_verified":False}
    p.update(extra)
    return p
def feed(rows):
    return {"schema":"jamaica.tour-previews.v1","bookable":False,"previews":rows}

class Tests(unittest.TestCase):
    def test_three_distinct_future_countries(self):
        f=feed([item("Россия",5,"a"),item("Индонезия",1,"b"),
                item("Индонезия",5,"c"),item("Индонезия",8,"d"),
                item("Шри-Ланка",7,"e"),item("Турция",4,"f")])
        rows=scan.select_candidates(f,today=TODAY,limit=3)
        self.assertEqual([x["country"] for x in rows],["Индонезия","Турция","Шри-Ланка"])
        self.assertEqual(rows[0]["id"],"p_"+"c"*24)
    def test_skip_unsupported_and_no_fabricated_booking(self):
        f=feed([item("Индонезия",5,"a",bookable=True),
                item("Турция",6,"b",availability_verified=True),
                item("Шри-Ланка",9,"c")])
        self.assertEqual([x["country"] for x in scan.select_candidates(f,today=TODAY)],["Шри-Ланка"])
    def test_expired_and_invalid(self):
        f=feed([item("Турция",-1,"a"),item("Турция",0,"b"),
                item("Турция",1,"c"),item("Турция",181,"d")])
        self.assertEqual(scan.select_candidates(f,today=TODAY),[])
    def test_invalid_schema_fails_closed(self):
        with self.assertRaises(SyncHold):
            scan.select_candidates({"schema":"bad","bookable":False,"previews":[]},today=TODAY)
    def test_result_safe_when_api_unavailable(self):
        f=feed([item("Индонезия",6,"a")])
        out=scan.run({"schema":"invalid"},f,object(),limit=1,today=TODAY)
        self.assertEqual(out[0]["status"],"UNVERIFIED")
        self.assertEqual(out[0]["matched_rows"],0)
if __name__=="__main__": unittest.main()
