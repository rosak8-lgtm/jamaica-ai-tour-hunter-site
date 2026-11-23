"""Targeted read-only BG flight evidence for source-discovered extra countries."""
from datetime import datetime,timedelta,timezone
import json
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import oracle_bg_flight_evidence_probe as audit
import oracle_bg_route_sync as bg

DATE=(datetime.now(timezone.utc)+timedelta(days=8)).strftime("%d.%m.%Y")
EXTRA={"name":"Сейшелы","id":"100410000051","has_tour_catalog":True,
       "origins":[]}
PRIMARY={"name":"Таиланд","id":"100410000052","has_tour_catalog":True,
         "origins":[bg.CITY_ID]}
def source_url(country):
    return ("https://export.bgoperator.ru/partners?action=price&tid=211&flt="+
        country["id"]+"&flt2="+bg.CITY_ID+
        "&id_price=121132934133&data="+DATE+"&xml=11")
def flight_row(out="a0",ret="90",stop=False):
    return {"isstop":stop,"tourComposition":[
        {"type":"flight","id":"TEST_0","n":0,"q":out},
        {"type":"accomodation","n":2,"q":"0"},
        {"type":"flight","id":"TEST_1","n":1,"q":ret}]}

class Api:
    def __init__(self,country=EXTRA,has_list=True):
        self.country=country;self.has_list=has_list;self.calls=[]
    def get(self,url):
        self.calls.append(url)
        if "/yandex?" in url:
            assert "flt2="+bg.CITY_ID in url
            assert "flt="+self.country["id"] in url
            entries=[{"date":DATE,"url":source_url(self.country)}] if self.has_list else []
            return json.dumps({"entries":entries}).encode()
        if "/partners?" in url:
            assert "xml=31" in url and "novirt=0" in url
            return json.dumps({"entries":[
                flight_row(),flight_row("a0","00"),
                flight_row("a0","a0",stop=True),
                flight_row("r0","r0")]}).encode()
        raise AssertionError("UNAPPROVED_API_CALL")

class Tests(unittest.TestCase):
    def setUp(self):
        self.directory={"countries":[PRIMARY,EXTRA]}

    def test_extra_country_with_stale_origins_is_checked_by_real_irkutsk_api(self):
        api=Api()
        out=audit.inspect(self.directory,api,country_name="Сейшелы")
        self.assertEqual(len(out),1)
        self.assertEqual(out[0]["country"],"Сейшелы")
        self.assertEqual(out[0]["state"],"CHECKED_EXTENDED")
        self.assertEqual(out[0]["rows"],4)
        self.assertEqual(out[0]["both_green"],1)
        self.assertEqual(out[0]["one_green"],1)
        self.assertEqual(out[0]["stop_sale"],1)
        self.assertEqual(out[0]["structured_pairs"],3)
        self.assertEqual(len(api.calls),2)

    def test_no_irkutsk_source_list_is_not_green(self):
        api=Api(has_list=False)
        report=audit.inspect(self.directory,api,country_name="Сейшелы")
        self.assertEqual(report[0]["state"],"NO_FUTURE_LIST")
        self.assertEqual(report[0]["both_green"],0)
        self.assertEqual(len(api.calls),1)

    def test_unknown_country_or_control_character_cannot_query_provider(self):
        api=Api()
        for choice in ("Unknown","Сейшелы\n--other","x"*121):
            with self.subTest(choice=choice),self.assertRaises(bg.SyncHold):
                audit.inspect(self.directory,api,country_name=choice)
        self.assertEqual(api.calls,[])

    def test_default_scope_remains_bounded_primary_only(self):
        api=Api(country=PRIMARY,has_list=False)
        report=audit.inspect(self.directory,api)
        self.assertEqual([x["country"] for x in report],["Таиланд"])
        self.assertEqual(len(api.calls),1)

    def test_bad_extended_url_does_not_follow_external_url(self):
        with self.assertRaises(bg.SyncHold):
            audit.detailed_url({"url":"https://malicious.example/partners?action=price"},EXTRA["id"])

if __name__=="__main__":
    unittest.main()
