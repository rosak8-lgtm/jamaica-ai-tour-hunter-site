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

    def test_five_bounded_price_lists_can_discover_green_in_later_departure(self):
        # The first list has 0 green flights. The 4th authentic list in
        # another month does. This models the observed 0-result Thai/China
        # single-list audit without manufacturing any real provider quote.
        from datetime import timedelta
        today=datetime.now(timezone.utc)
        class MultiDateApi:
            def __init__(self):
                self.calls=[]
            def get(self,url):
                self.calls.append(url)
                if "/yandex?" in url:
                    items=[]
                    for i in range(5):
                        date=(today+timedelta(days=8+i*28)).strftime("%d.%m.%Y")
                        items.append({"date":date,
                            "id_price":str(121132934130+i),
                            "url":source_url(EXTRA).replace(
                                "121132934133",str(121132934130+i)
                            ).replace(DATE,date)})
                    return json.dumps({"entries":items}).encode()
                if "/partners?" in url:
                    good="id_price=121132934133" in url
                    return json.dumps({"entries":[
                        flight_row("a0","90") if good else flight_row("r0","00"),
                        flight_row("a0","00")]}).encode()
                raise AssertionError("UNAPPROVED_ENDPOINT")
        api=MultiDateApi()
        result=audit.inspect(self.directory,api,country_name="Сейшелы",
                             max_lists=5,probe_slot=0)[0]
        self.assertEqual(result["state"],"CHECKED_EXTENDED")
        self.assertEqual(result["lists_attempted"],5)
        self.assertEqual(result["lists_checked"],5)
        self.assertEqual(result["lists_failed"],0)
        self.assertEqual(result["rows"],10)
        self.assertEqual(result["both_green"],1)
        self.assertEqual(result["one_green"],5)
        self.assertEqual(result["out_regular_unconfirmed"],4)
        self.assertEqual(result["back_on_request"],9)
        self.assertEqual(result["out_green"],6)
        self.assertEqual(len(api.calls),6)
        self.assertTrue(all("xml=31" in u for u in api.calls[1:]))

    def test_partial_source_failure_keeps_only_successful_lists(self):
        from datetime import timedelta
        today=datetime.now(timezone.utc)
        class PartialApi:
            def __init__(self):self.calls=[]
            def get(self,url):
                self.calls.append(url)
                if "/yandex?" in url:
                    values=[]
                    for i in range(3):
                        date=(today+timedelta(days=5+30*i)).strftime("%d.%m.%Y")
                        values.append({"date":date,"id_price":str(121132934130+i),
                            "url":source_url(EXTRA).replace(
                                "121132934133",str(121132934130+i)
                            ).replace(DATE,date)})
                    return json.dumps({"entries":values}).encode()
                if "id_price=121132934131" in url:
                    return b"{INVALID"
                return json.dumps({"entries":[flight_row()]}).encode()
        result=audit.inspect(self.directory,PartialApi(),
                            country_name="Сейшелы",max_lists=3)[0]
        self.assertEqual(result["state"],"PARTIAL_EXTENDED")
        self.assertEqual(result["lists_attempted"],3)
        self.assertEqual(result["lists_checked"],2)
        self.assertEqual(result["lists_failed"],1)
        self.assertEqual(result["both_green"],2)

    def test_price_list_limit_and_probe_slot_are_strict(self):
        class MustNotCall:
            def get(self,url):
                raise AssertionError("INVALID_LIMIT_MUST_NOT_REACH_PROVIDER")
        for bound in (0,6,True,1.5,None):
            with self.subTest(max_lists=bound),self.assertRaises(bg.SyncHold):
                audit.inspect(self.directory,MustNotCall(),
                              country_name="Сейшелы",max_lists=bound)
        for slot in (-1,10001,True,1.5):
            with self.subTest(slot=slot),self.assertRaises(bg.SyncHold):
                audit.inspect(self.directory,MustNotCall(),
                              country_name="Сейшелы",probe_slot=slot)

    def test_observed_country_list_can_check_extra_and_primary_together(self):
        class NoListsApi:
            def __init__(self):self.calls=[]
            def get(self,url):
                self.calls.append(url)
                return json.dumps({"entries":[]}).encode()
        api=NoListsApi()
        reports=audit.inspect(self.directory,api,
            country_names=["Сейшелы","Таиланд"])
        self.assertEqual({x["country"] for x in reports},
                         {"Сейшелы","Таиланд"})
        self.assertEqual(len(api.calls),2)
        self.assertTrue(all(x["state"]=="NO_FUTURE_LIST" for x in reports))
        self.assertTrue(all("flt2="+bg.CITY_ID in x for x in api.calls))

    def test_observed_country_list_missing_unknown_duplicates_never_queried(self):
        class NoRequests:
            def get(self,url):
                raise AssertionError("INVALID_COUNTRY_FILE_SCOPE_MUST_FAIL_FIRST")
        for names in ([],["Unknown"],["Сейшелы","Сейшелы"],
                      [0],["Сейшелы\nInjected"],["Сейшелы"]*21):
            with self.subTest(names=names),self.assertRaises(bg.SyncHold):
                audit.inspect(self.directory,NoRequests(),country_names=names)

    def test_owner_only_country_file_and_symlinks_are_mandatory(self):
        import tempfile,os
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"countries.json"
            path.write_text(json.dumps(["Таиланд","Сейшелы"]),encoding="utf-8")
            os.chmod(path,0o600)
            self.assertEqual(audit.read_owner_only_country_names(str(path)),
                             ["Таиланд","Сейшелы"])
            os.chmod(path,0o644)
            with self.assertRaises(bg.SyncHold):
                audit.read_owner_only_country_names(str(path))
            os.chmod(path,0o600)
            link=Path(folder)/"alias.json"
            link.symlink_to(path)
            with self.assertRaises(bg.SyncHold):
                audit.read_owner_only_country_names(str(link))

    def test_bad_extended_url_does_not_follow_external_url(self):
        with self.assertRaises(bg.SyncHold):
            audit.detailed_url({"url":"https://malicious.example/partners?action=price"},EXTRA["id"])

if __name__=="__main__":
    unittest.main()
