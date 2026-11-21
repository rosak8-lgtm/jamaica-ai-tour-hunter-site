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
    def test_five_list_scans_cover_near_and_later_calendar_months(self):
        from datetime import date, timedelta
        today=date(2026,11,21)
        def listing(delta):
            when=today+timedelta(days=delta)
            return {"date":when.strftime("%d.%m.%Y"),"file":str(delta)}
        # Seven calendar months in the future 180-day horizon.
        rows=[listing(delta) for delta in range(1,181)]
        selected=exporter.choose_price_lists(rows,5,today=today,probe_slot=0)
        self.assertLessEqual(len(selected),5)
        self.assertEqual(selected[0]["file"],"1")
        future_months={ (today+timedelta(days=int(x["file"]))).strftime("%Y-%m")
                        for x in selected }
        self.assertGreaterEqual(len(future_months),4)
        # A week of scans must revisit all months actually advertised by source.
        expected={ (today+timedelta(days=d)).strftime("%Y-%m")
                   for d in range(1,181) }
        observed=set()
        later_dates=set()
        for cycle in range(14):
            chosen=exporter.choose_price_lists(rows,5,today=today,probe_slot=cycle)
            self.assertLessEqual(len(chosen),5)
            self.assertEqual(chosen[0]["file"],"1")
            for x in chosen:
                day=today+timedelta(days=int(x["file"]))
                observed.add(day.strftime("%Y-%m"))
                later_dates.add(day)
        self.assertEqual(observed,expected)
        self.assertGreater(len(later_dates),5)

    def test_source_read_limit_and_invalid_dates_are_respected(self):
        from datetime import date,timedelta
        today=date(2026,11,21)
        rows=[{"date":(today+timedelta(days=d)).strftime("%d.%m.%Y"),"file":str(d)}
              for d in range(-5,190)]
        rows.extend([{"date":"not-a-date"},{"stop":True,"date":"02.12.2026"}])
        for cap in (1,2,3,4,5):
            picked=exporter.choose_price_lists(rows,cap,today=today,probe_slot=19)
            self.assertLessEqual(len(picked),cap)
            for row_ in picked:
                from_date=exporter.bg.date_iso(row_["date"])
                self.assertTrue(today<from_date<=today+timedelta(days=180))
        self.assertEqual(exporter.choose_price_lists(rows,0,today=today),[])

    def test_no_past_or_today_only_listings(self):
        from datetime import date,timedelta
        today=date(2026,11,20)
        rows=[{"date":today.strftime("%d.%m.%Y")},
              {"date":(today-timedelta(days=1)).strftime("%d.%m.%Y")}]
        self.assertEqual(exporter.choose_price_lists(rows,2,today=today),[])
    def test_catalog_cap_selects_cheaper_rows_but_keeps_dates_and_countries(self):
        def reference(country,day,price,ident):
            return {"country":country,"depart_date":day,
                    "price_reference_rub":price,
                    "price_reference_party":"TWO_ADULTS",
                    "hotel":"Sample Hotel","room":"STANDARD","id":ident}
        rows=[
            reference("A","2026-11-25",90000,"1"),
            reference("A","2026-11-25",40000,"2"),
            reference("A","2026-12-05",45000,"3"),
            reference("A","2026-12-05",80000,"4"),
            reference("B","2026-11-25",70000,"5"),
            reference("B","2026-11-25",35000,"6"),
        ]
        selected=exporter.fair_catalog(rows,max_rows=4)
        self.assertEqual({x["id"] for x in selected},{"2","3","5","6"})
        self.assertEqual({x["country"] for x in selected},{"A","B"})
        self.assertEqual({x["depart_date"] for x in selected},
                         {"2026-11-25","2026-12-05"})
        self.assertEqual(exporter.fair_catalog(rows,max_rows=0),[])

    def test_unpriced_records_never_rank_cheaper_than_known_prices(self):
        rows=[
            {"country":"A","depart_date":"2026-12-03","hotel":"B",
             "room":"S","id":"unknown","price_reference_rub":None,
             "price_reference_party":"UNVERIFIED"},
            {"country":"A","depart_date":"2026-12-03","hotel":"A",
             "room":"S","id":"known","price_reference_rub":55000,
             "price_reference_party":"TWO_ADULTS"},
        ]
        self.assertEqual(exporter.fair_catalog(rows,max_rows=1)[0]["id"],"known")

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
    def test_indicative_rub_reference_for_two_adults(self):
        p=exporter.safe_preview(row(),COUNTRY,self.hotels,"EUR")
        self.assertEqual(p["price_reference_rub"],130000)
        self.assertEqual(p["price_reference_party"],"TWO_ADULTS")
        self.assertFalse(p["bookable"])
        self.assertFalse(p["quote_verified"])
        self.assertNotIn("href2",p)
    def test_no_reference_without_currency(self):
        p=exporter.safe_preview(row(),COUNTRY,self.hotels)
        self.assertIsNone(p["price_reference_rub"])
        self.assertEqual(p["price_reference_party"],"UNVERIFIED")
    def test_no_reference_for_child_scope(self):
        p=exporter.safe_preview(row(prices=[{"amount":"1500","RUR":"100000","ag":"12+,2-11"}]),COUNTRY,self.hotels,"EUR")
        self.assertIsNone(p["price_reference_rub"])
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
                return json.dumps({"cur":"EUR","entries":[row()]}).encode()
        directory={"schema":"jamaica.destination-directory.v1",
                   "countries":[{"name":COUNTRY,"id":"100410000051","has_tour_catalog":True,"origins":[bg.CITY_ID]}],
                   "hotels":list(self.hotels.values())}
        result=exporter.build(directory,Api(),max_countries=1,per_country=1)
        self.assertEqual(len(result["previews"]),1)
        self.assertEqual(result["indicative_two_adult_rub_count"],1)
        self.assertEqual(result["previews"][0]["price_reference_rub"],130000)
        self.assertFalse(result["bookable"])
        self.assertEqual(result["countries_status"][0]["status"],"CHECKED")

if __name__=="__main__": unittest.main()
