import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
import oracle_bg_preview_export as exporter
import oracle_bg_route_sync as bg

COUNTRY="Индонезия"
HOTEL_ID="102610001486"
DATE=(datetime.now(timezone.utc)+timedelta(days=7)).strftime("%d.%m.%Y")

def row(**override):
    result={"id_hotel":HOTEL_ID,"tour_date":DATE,"duration":"7",
            "room":"STANDARD HB","town":"Бали",
            "prices":[{"amount":"1450","RUR":"130000","ag":"12+,12+"}]}
    result.update(override)
    return result

class Tests(unittest.TestCase):
    def setUp(self):
        self.hotels={HOTEL_ID:{"id":HOTEL_ID,"country":COUNTRY,
                               "name":"Verified Catalog Hotel","resort":"Бали"}}

    def test_choose_different_future_price_list_dates(self):
        from datetime import date, timedelta
        today=date(2026,11,20)
        def entry(delta,name):
            return {"date":(today+timedelta(days=delta)).strftime("%d.%m.%Y"),"file":name}
        candidates=[entry(0,"today"),entry(1,"a"),entry(1,"b"),
                    entry(3,"c"),entry(8,"d")]
        chosen=exporter.choose_price_lists(candidates,2,today=today)
        self.assertEqual([x["file"] for x in chosen],["a","c"])
    def test_no_past_or_today_only_listings(self):
        from datetime import date,timedelta
        today=date(2026,11,20)
        rows=[{"date":today.strftime("%d.%m.%Y")},
              {"date":(today-timedelta(days=1)).strftime("%d.%m.%Y")}]
        self.assertEqual(exporter.choose_price_lists(rows,2,today=today),[])
    def test_preview_contains_only_safe_descriptive_fields(self):
        p=exporter.safe_preview(row(),COUNTRY,self.hotels)
        self.assertEqual(p["hotel"],"Verified Catalog Hotel")
        self.assertEqual(p["room"],"STANDARD HB")
        self.assertFalse(p["bookable"])
        self.assertFalse(p["quote_verified"])
        self.assertFalse(p["availability_verified"])
        for banned in ("amount","RUR","ag","currency","href0","href1","href2",
                       "operator","session","total_rub"):
            self.assertNotIn(banned,p)
        self.assertNotIn("130000",json.dumps(p))
    def test_skip_unmatched_hotel(self):
        self.assertIsNone(exporter.safe_preview(row(id_hotel="99999999999"),COUNTRY,self.hotels))
    def test_skip_empty_price(self):
        self.assertIsNone(exporter.safe_preview(row(prices=[{"amount":""}]),COUNTRY,self.hotels))
    def test_skip_stopped_price(self):
        self.assertIsNone(exporter.safe_preview(row(prices=[{"amount":"100","isstop":["avia_from"]}]),COUNTRY,self.hotels))
    def test_skip_past_date(self):
        self.assertIsNone(exporter.safe_preview(row(tour_date="01.01.2020"),COUNTRY,self.hotels))
    def test_skip_invalid_nights(self):
        self.assertIsNone(exporter.safe_preview(row(duration="0"),COUNTRY,self.hotels))
    def test_require_country_match(self):
        self.assertIsNone(exporter.safe_preview(row(),"Таиланд",self.hotels))
    def test_no_fabricated_bookability_on_build(self):
        class Api:
            def get(self,url):
                if "/yandex?" in url:
                    return json.dumps({"entries":[{
                        "date":DATE,"url":"https://export.bgoperator.ru/partners?action=price&tid=211&flt=100410000051&flt2="
                         +bg.CITY_ID+"&id_price=121132934133&data="+DATE+"&xml=11"
                    }]}).encode()
                return json.dumps({"entries":[row()]}).encode()
        directory={"schema":"jamaica.destination-directory.v1",
                   "countries":[{"name":COUNTRY,"id":"100410000051","has_tour_catalog":True,"origins":[bg.CITY_ID]}],
                   "hotels":list(self.hotels.values())}
        result=exporter.build(directory,Api(),max_countries=1,per_country=1)
        self.assertEqual(len(result["previews"]),1)
        self.assertFalse(result["bookable"])
        self.assertEqual(result["countries_status"][0]["status"],"CHECKED")

if __name__=="__main__": unittest.main()
