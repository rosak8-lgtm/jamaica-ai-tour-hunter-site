"""No-network tests for Oracle's independent five-minute catalog publisher."""
import importlib.util
import json
import tempfile
import unittest
from unittest.mock import patch
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location(
    "oracle_site_publisher",ROOT/"scripts"/"oracle_site_publisher.py")
publisher=importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)

NOW=datetime.now(timezone.utc)
def directory():
    return {
        "schema":"jamaica.destination-directory.v1",
        "countries":[{"name":"Турция"} for i in range(190)],
        "hotels":[{"id":str(i)} for i in range(550)],
        "updated_at_utc":NOW.isoformat(),
    }

def feed(n=1):
    return {
        "schema":"jamaica.tour-previews.v1",
        "refreshed_at_utc":NOW.isoformat(),
        "bookable":False,"quote_verified":False,"availability_verified":False,
        "countries_status":[{"country":"Турция","status":"CHECKED"}],
        "previews":[{
            "id":"p_"+"a"*24,"hotel_id":"123456789",
            "hotel":"TEST","country":"Турция","origin":"Иркутск",
            "resort":"Анталия","room":"DBL",
            "depart_date":"2026-12-12","nights":7,
            "status":"REFERENCE_PRICE_LIST_ONLY",
            "price_reference_rub":88000,"price_reference_party":"TWO_ADULTS",
            "quote_verified":False,"availability_verified":False,
            "flight_verified":False,"bookable":False,
        } for _ in range(n)]
    }

class Tests(unittest.TestCase):
    def test_valid_source_backed_feed_can_be_published(self):
        self.assertEqual(publisher.validate(feed(),directory()),1)

    def test_operator_price_changes_are_published_immediately(self):
        old=feed();new=feed()
        new["previews"][0]["price_reference_rub"]=89000
        self.assertTrue(publisher.needs_publish(old,new,now=NOW+timedelta(minutes=5)))

    def test_unchanged_source_does_not_create_new_github_commit_every_five_minutes(self):
        old=feed();new=feed()
        new["refreshed_at_utc"]=(NOW+timedelta(minutes=5)).isoformat()
        self.assertFalse(publisher.needs_publish(old,new,now=NOW+timedelta(minutes=5)))
        self.assertTrue(publisher.needs_publish(old,new,now=NOW+timedelta(minutes=31)))

    def test_reject_bookable_or_confirmed_without_real_supplier_verification(self):
        for change in (
            {"bookable":True},{"quote_verified":True},{"availability_verified":True}
        ):
            f=feed();f.update(change)
            with self.assertRaises(publisher.CatalogHold):
                publisher.validate(f,directory())

    def test_reject_payment_or_personal_fields_and_supplier_identifiers(self):
        for name,value in (
          ("passport","AA 123"),("supplier_url","https://operator.invalid"),
          ("supplier_booking_id","100") ,("payments_enabled",True)
        ):
            f=feed();f["previews"][0][name]=value
            with self.assertRaises(publisher.CatalogHold):
                publisher.validate(f,directory())

    def test_reject_wrong_origin_and_country(self):
        for name,value in (("origin","Москва"),("country","Неизвестная страна")):
            f=feed();f["previews"][0][name]=value
            with self.assertRaises(publisher.CatalogHold):
                publisher.validate(f,directory())

    def test_no_unverified_ruble_price_or_party(self):
        for name,value in (("price_reference_rub",True),
                           ("price_reference_rub",0),
                           ("price_reference_party","ONE_ADULT")):
            f=feed();f["previews"][0][name]=value
            with self.assertRaises(publisher.CatalogHold):
                publisher.validate(f,directory())

    def test_old_data_not_published_as_fresh(self):
        f=feed()
        f["refreshed_at_utc"]=(NOW-timedelta(hours=1)).isoformat()
        with self.assertRaises(publisher.CatalogHold):
            publisher.validate(f,directory())

    def test_directory_must_be_recent_known_scope(self):
        stale=directory()
        stale["updated_at_utc"]=(NOW-timedelta(days=9)).isoformat()
        with self.assertRaises(publisher.CatalogHold):
            publisher.directory_check(stale)

    def test_discovered_irkutsk_country_is_promoted_to_regular_server_checks(self):
        with tempfile.TemporaryDirectory() as tmp:
            state_path=Path(tmp)/"extra_irkutsk_source_countries.json"
            d=directory()
            d["countries"].append({"name":"Вьетнам","has_tour_catalog":True,
                                   "origins":["100510000863"]})
            actual=feed()
            actual["countries_status"].append({"country":"Вьетнам",
                                               "status":"CHECKED","lists_read":1})
            count=publisher.update_discovered_source_countries(
                actual,d,state_path=state_path)
            self.assertEqual(count,1)
            self.assertEqual(json.loads(state_path.read_text()),["Вьетнам"])
            count=publisher.update_discovered_source_countries(
                actual,d,state_path=state_path)
            self.assertEqual(count,1)
    def test_server_reads_updated_api_adapters_from_its_github_clone(self):
        self.assertEqual(publisher.SCRIPTS,publisher.CHECKOUT/"scripts")
    def test_disabled_github_deploy_key_prevents_publish(self):
        with self.assertRaises(publisher.CatalogHold):
            with patch.object(publisher,"KEY",Path("/some/nonexistent/key")):
                publisher.git_env()

if __name__=="__main__":
    unittest.main()
