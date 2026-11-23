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

    def test_sharded_60000_catalogue_preserves_rows_and_bounds(self):
        f=feed()
        template=f["previews"][0]
        f["previews"]=[{**template,"id":"p_"+format(i,"024x")}
                       for i in range(16_432)]
        self.assertEqual(publisher.validate(f,directory()),16432)
        root,chunks=publisher.make_sharded_catalog(f)
        self.assertEqual(len(root["previews"]),8000)
        self.assertEqual(root["total_published_previews"],16432)
        self.assertEqual(len(chunks),3)
        self.assertEqual([x["count"] for x in root["shards"]],[4000,4000,432])
        self.assertEqual(sum(len(c["previews"]) for c in chunks.values())+8000,16432)
        self.assertEqual(publisher.validate(root,directory()),8000)
        self.assertEqual({c["schema"] for c in chunks.values()},
                         {"jamaica.tour-preview-shard.v1"})
        self.assertTrue(all(c["bookable"] is False for c in chunks.values()))
        self.assertTrue(all(c["refreshed_at_utc"]==root["refreshed_at_utc"]
                            for c in chunks.values()))
        new=json.loads(json.dumps(f))
        new["refreshed_at_utc"]=(NOW+timedelta(minutes=5)).isoformat()
        root_new,_=publisher.make_sharded_catalog(new)
        self.assertFalse(publisher.needs_publish(root,root_new,
                         now=NOW+timedelta(minutes=5)))
        new["previews"][-1]["price_reference_rub"]=42000
        root_changed,_=publisher.make_sharded_catalog(new)
        self.assertTrue(publisher.needs_publish(root,root_changed,
                        now=NOW+timedelta(minutes=5)))

    def test_fast_root_diversifies_real_countries_and_months(self):
        original=feed()["previews"][0]
        source=[]
        # Chronological source: 100 cheap nearby Thailand rows otherwise
        # push 2027 China/Vietnam/Philippines outside the first 12.
        for i in range(100):
            source.append({**original,"id":"p_"+format(i,"024x"),
                "country":"Таиланд","depart_date":"2026-12-10",
                "price_reference_rub":50000+i})
        for i,(country,month) in enumerate((
            ("Китай","2026-12-20"),("Китай","2027-01-20"),
            ("Китай","2027-02-20"),("Вьетнам","2026-12-30"),
            ("Вьетнам","2027-01-10"),("Филиппины","2027-03-15")
        ),start=100):
            source.append({**original,"id":"p_"+format(i,"024x"),
                "country":country,"depart_date":month,
                "price_reference_rub":75000+i})
        with patch.object(publisher,"ROOT_ITEMS",12):
            root,chunks=publisher.make_sharded_catalog({
                **feed(),"previews":source
            })
        self.assertEqual(len(root["previews"]),12)
        self.assertEqual({x["country"] for x in root["previews"]},
                         {"Таиланд","Китай","Вьетнам","Филиппины"})
        self.assertIn("2027-03",
            {x["depart_date"][:7] for x in root["previews"]})
        self.assertIn("2027-02",
            {x["depart_date"][:7] for x in root["previews"]})
        flat=root["previews"]+[x for part in chunks.values()
                               for x in part["previews"]]
        self.assertEqual(len(flat),len(source))
        self.assertEqual(set(x["id"] for x in flat),
                         set(x["id"] for x in source))
        self.assertEqual({x["id"]:x for x in flat},
                         {x["id"]:x for x in source})
        self.assertTrue(all(x["bookable"] is False for x in flat))
        self.assertTrue(all(x["quote_verified"] is False for x in flat))
        self.assertEqual(root["total_published_previews"],len(source))
        self.assertEqual(sum(x["count"] for x in root["shards"]),len(source)-12)
        with patch.object(publisher,"ROOT_ITEMS",12):
            repeat,_=publisher.make_sharded_catalog({
                **feed(),"previews":source
            })
        self.assertEqual([x["id"] for x in root["previews"]],
                         [x["id"] for x in repeat["previews"]])
        self.assertEqual(root["shards"],repeat["shards"])

    def test_root_month_diversity_never_makes_up_a_rate(self):
        original=feed()["previews"][0]
        source=[{**original,"id":"p_"+format(i,"024x"),
                 "country":"Китай","depart_date":
                    ("2027-01-11" if i%2==0 else "2027-02-11"),
                 "price_reference_rub":None if i%3==0 else 100000+i,
                 "price_reference_party":
                    "UNVERIFIED" if i%3==0 else "TWO_ADULTS"}
                for i in range(40)]
        with patch.object(publisher,"ROOT_ITEMS",8):
            root,chunks=publisher.make_sharded_catalog({
                **feed(),"previews":source
            })
        self.assertEqual(len(root["previews"]),8)
        self.assertEqual({x["depart_date"][:7] for x in root["previews"]},
                         {"2027-01","2027-02"})
        self.assertTrue(all(x["price_reference_rub"] is not None
                            for x in root["previews"]))
        self.assertEqual(len(root["previews"])+sum(
            len(chunk["previews"]) for chunk in chunks.values()),len(source))

    def test_zero_qualified_tours_is_valid_safest_public_catalog(self):
        current=feed()
        current["previews"]=[]
        current["publication_rule"]="BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1"
        with self.assertRaises(publisher.CatalogHold):
            publisher.validate(current,directory())
        self.assertEqual(publisher.validate(current,directory(),allow_empty=True),0)
        root,chunks=publisher.make_sharded_catalog(current)
        self.assertEqual(root["previews"],[])
        self.assertEqual(root["total_published_previews"],0)
        self.assertEqual(root["shards"],[])
        self.assertEqual(chunks,{})
        self.assertEqual(publisher.validate(root,directory(),allow_empty=True),0)

    def test_shard_limit_cannot_silently_overrun(self):
        with patch.object(publisher,"MAX_SHARDS",0):
            f=feed()
            f["previews"]=[{**f["previews"][0],"id":"p_"+format(i,"024x")}
                            for i in range(8001)]
            with self.assertRaises(publisher.CatalogHold):
                publisher.make_sharded_catalog(f)

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

    def test_old_unrechecked_record_cannot_keep_numeric_price(self):
        f=feed()
        f["previews"][0]["status"]="PREVIOUSLY_SEEN_NOT_RECHECKED"
        with self.assertRaises(publisher.CatalogHold):
            publisher.validate(f,directory())
        f["previews"][0]["price_reference_rub"]=None
        f["previews"][0]["price_reference_party"]="UNVERIFIED"
        self.assertEqual(publisher.validate(f,directory()),1)
        f["previews"][0]["status"]="UNKNOWN_OPERATOR_CLAIM"
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
    def test_old_24h_archive_plus_fresh_oversized_feed_is_byte_bounded(self):
        from scripts import recent_preview_catalog as recent
        from scripts import catalog_size_budget as budget
        # Source-only synthetic high volume; never invent airline seats or price.
        sample=feed()["previews"][0]
        old_rows=[{**sample,"id":"p_"+format(i,"024x"),
                   "hotel":"ARCHIVE "+("X"*85),
                   "country":["Таиланд","Китай","Вьетнам"][i%3],
                   "status":"PREVIOUSLY_SEEN_NOT_RECHECKED",
                   "price_reference_rub":None,"price_reference_party":"UNVERIFIED"}
                  for i in range(4000)]
        current=[{**sample,"id":"p_"+format(5000+i,"024x"),
                  "country":"Индонезия",
                  "hotel":"CURRENT "+("Y"*85)} for i in range(180)]
        src={**feed(),"previews":current}
        extended={**src,"previews":current+old_rows,
                  "source_scope":{"last_24h_unrechecked_previews":len(old_rows),
                                  "last_24h_unrechecked_countries":3}}
        result,removed=budget.fit_feed(extended,max_bytes=100_000)
        self.assertLessEqual(budget.encoded_size(result),100_000)
        self.assertGreater(removed,0)
        # Every fresh source row stays; only *spare* bytes can be assigned
        # to stale 24h previews, which must carry zero reference price.
        fresh=[x for x in result["previews"]
               if x["status"]=="REFERENCE_PRICE_LIST_ONLY"]
        old=[x for x in result["previews"]
             if x["status"]=="PREVIOUSLY_SEEN_NOT_RECHECKED"]
        self.assertEqual(len(fresh),180)
        self.assertTrue(all(x["country"]=="Индонезия" for x in fresh))
        self.assertTrue(all(x["price_reference_rub"] is None and
                            x["price_reference_party"]=="UNVERIFIED"
                            for x in old))
        self.assertEqual(result["source_scope"]["last_24h_unrechecked_previews"],
                         len(old))
        self.assertTrue(result["truncated_to_public_limit"])
        self.assertFalse(any(x["bookable"] for x in result["previews"]))

    def test_private_recent_country_state_is_owner_only_and_atomic(self):
        from scripts import recent_preview_catalog as recent
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"recent-price-list-previews.json"
            self.assertIsNone(publisher.load_recent_source_cache(path))
            current,next_cache=recent.combine(feed(),None,now=NOW)
            publisher.save_recent_source_cache(next_cache,path)
            self.assertEqual(path.stat().st_mode&0o777,0o600)
            actual=publisher.load_recent_source_cache(path)
            self.assertEqual(actual["schema"],recent.CACHE_SCHEMA)
            self.assertEqual(len(actual["entries"]),1)
            path.chmod(0o644)
            with self.assertRaises(publisher.CatalogHold):
                publisher.load_recent_source_cache(path)
            path.chmod(0o600)
            combined,another=recent.combine(feed(),actual,
                         now=NOW+timedelta(minutes=5))
            self.assertEqual(len(combined["previews"]),1)
            publisher.save_recent_source_cache(another,path)
            self.assertEqual(len(publisher.load_recent_source_cache(path)["entries"]),1)

    def test_private_cache_invalid_file_and_symlink_cannot_be_published(self):
        with tempfile.TemporaryDirectory() as folder:
            path=Path(folder)/"recent-price-list-previews.json"
            path.write_text('{"schema":"other"}',encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaises(publisher.CatalogHold):
                publisher.load_recent_source_cache(path)
            path.unlink()
            path.symlink_to(Path(folder)/"does-not-exist")
            with self.assertRaises(publisher.CatalogHold):
                publisher.load_recent_source_cache(path)
            with self.assertRaises(publisher.CatalogHold):
                publisher.save_recent_source_cache({"schema":"test"},path)

    def test_server_reads_updated_api_adapters_from_its_github_clone(self):
        self.assertEqual(publisher.SCRIPTS,publisher.CHECKOUT/"scripts")
    def test_disabled_github_deploy_key_prevents_publish(self):
        with self.assertRaises(publisher.CatalogHold):
            with patch.object(publisher,"KEY",Path("/some/nonexistent/key")):
                publisher.git_env()

if __name__=="__main__":
    unittest.main()
