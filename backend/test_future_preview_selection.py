import sys
import unittest
from pathlib import Path
from datetime import date,timedelta
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import select_future_preview as selection

TODAY=date(2026,11,20)
def row(country,days,idpart,**patch):
    p={"id":"p_"+idpart*24,"country":country,"origin":"Иркутск",
       "depart_date":(TODAY+timedelta(days=days)).isoformat(),
       "bookable":False,"quote_verified":False,"availability_verified":False,
       "flight_verified":False}
    p.update(patch)
    return p
def feed(rows):
    return {"schema":"jamaica.tour-previews.v1","bookable":False,"previews":rows}

class Tests(unittest.TestCase):
    def test_prefers_future_international_over_todays_first_entry(self):
        f=feed([row("Россия",0,"a"),row("Россия",7,"b"),row("Индонезия",10,"c")])
        self.assertEqual(selection.choose(f,today=TODAY),"p_"+"c"*24)
    def test_skips_unverified_or_bookable_claims(self):
        f=feed([row("Индонезия",2,"a",bookable=True),
                row("Турция",5,"b",flight_verified=True),
                row("Шри-Ланка",8,"c")])
        self.assertEqual(selection.choose(f,today=TODAY),"p_"+"c"*24)
    def test_rejects_today_and_past(self):
        with self.assertRaises(ValueError):
            selection.choose(feed([row("Индонезия",0,"a"),row("Индонезия",-1,"b")]),today=TODAY)
    def test_country_filter(self):
        f=feed([row("Индонезия",4,"a"),row("Турция",2,"b")])
        self.assertEqual(selection.choose(f,today=TODAY,preferred_country="Турция"),"p_"+"b"*24)
    def test_schema_block(self):
        with self.assertRaises(ValueError):
            selection.choose({"schema":"unknown","bookable":False,"previews":[]},today=TODAY)
    def test_same_country_earlier_date_first(self):
        f=feed([row("Турция",10,"a"),row("Турция",2,"b")])
        self.assertEqual(selection.choose(f,today=TODAY),"p_"+"b"*24)

if __name__=="__main__":unittest.main()
