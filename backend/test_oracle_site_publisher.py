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
    def test_public_catalog_modes_repair_without_relaxing_reader(self):
        from backend.customer_inquiry_catalog import read
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            shard_dir=root/publisher.SHARD_FOLDER
            shard_dir.mkdir(mode=0o700)
            paths=[root/name for name in ("tour-previews.json","tour-visual-evidence.json",
                                           "application-reference.json","inquiry-config.json")]
            paths.append(shard_dir/"part-001.json")
            for path in paths:
                path.write_text('{"previews":[]}')
                path.chmod(0o664)
                with self.assertRaisesRegex(ValueError,"UNSAFE_FILE"):
                    read(path,1024)
            private=root/"private-test.json"
            private.write_text("{}");private.chmod(0o600)
            publisher.normalize_public_catalog_modes(root)
            publisher.normalize_public_catalog_modes(root)
            for path in paths:
                self.assertEqual(path.stat().st_mode&0o777,0o644)
                self.assertEqual(read(path,1024)[0],{"previews":[]})
            self.assertEqual(private.stat().st_mode&0o777,0o600)

    def test_public_catalog_modes_reject_links_and_unsafe_directory(self):
        import os
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            path=root/"tour-previews.json"
            target=root/"unrelated.json"
            target.write_text("{}");target.chmod(0o664)
            path.symlink_to(target)
            with self.assertRaisesRegex(publisher.CatalogHold,"UNSAFE_PUBLIC_CATALOG_FILE"):
                publisher.normalize_public_catalog_modes(root)
            self.assertEqual(target.stat().st_mode&0o777,0o664)
            path.unlink();os.link(target,path)
            with self.assertRaisesRegex(publisher.CatalogHold,"UNSAFE_PUBLIC_CATALOG_FILE"):
                publisher.normalize_public_catalog_modes(root)
            path.unlink()
            shard_dir=root/publisher.SHARD_FOLDER
            shard_dir.mkdir();shard_dir.chmod(0o775)
            with self.assertRaisesRegex(publisher.CatalogHold,"UNSAFE_PUBLIC_CATALOG_DIRECTORY"):
                publisher.normalize_public_catalog_modes(root)
            self.assertEqual(target.stat().st_mode&0o777,0o664)

    def test_pegas_handoff_disabled_by_default_and_missing_evidence_is_empty(self):
        from backend import pegas_private_handoff
        from backend.test_pegas_public_projection import Tests as Fixture
        fixture=Fixture()
        fixture.setUp()
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            folder=root/"private-pegas-site"
            folder.mkdir(mode=0o700)
            path=folder/"evidence.json"
            with patch.object(publisher,"RUNROOT",root),patch.object(publisher,"CHECKOUT",ROOT):
                with patch.dict(publisher.os.environ,{},clear=True):
                    self.assertIsNone(publisher.optional_pegas_projection(now=fixture.now))
                with patch.dict(publisher.os.environ,{"JAMAICA_ENABLE_PEGAS_SITE_HANDOFF":"yes"},clear=True):
                    self.assertEqual(publisher.optional_pegas_projection(now=fixture.now)["previews"],[])
                    path.write_text(json.dumps({"schema":pegas_private_handoff.SCHEMA,"pairs":[[fixture.s,fixture.a]]}))
                    path.chmod(0o600)
                    result=publisher.optional_pegas_projection(now=fixture.now)
                    self.assertEqual(len(result["previews"]),1)
                    self.assertFalse(result["previews"][0]["bookable"])
                    self.assertEqual(publisher.optional_pegas_projection(now=fixture.now+timedelta(minutes=16))["previews"],[])

    def test_upgrade_gate_structure_accepts_clock_keyword_and_rejects_missing_gate(self):
        from verify_publisher_gate import verify
        source=(ROOT/"scripts"/"oracle_site_publisher.py").read_text(encoding="utf-8")
        self.assertTrue(verify(source))
        old="def publish(env):\n    published=eligibility.select_public_source_rows(new,visual_public)\n    published=browser_price.apply(published, receipts, visual_public, ledger)\n"
        self.assertTrue(verify(old))
        self.assertTrue(verify(old.replace("new,visual_public)", "new, visual_public, now=clock)")))
        self.assertFalse(verify(old.replace("eligibility.select_public_source_rows(new,visual_public)", "new")))
        self.assertFalse(verify(old.replace("published=browser_price.apply", "unused=browser_price.apply")))
        self.assertFalse(verify(old.replace("new,visual_public)", "new,wrong_proof)")))

    def test_proof_health_distinguishes_expiry_and_missing_handoff(self):
        from site_proof_health import report
        moment=datetime.now(timezone.utc)
        def rec(uid,minutes):
            return {"preview_id":uid,"route":{"source_price_list_id":"123456789"},
                    "flight":{"flight_checked_at_utc":(moment-timedelta(minutes=minutes)).isoformat()}}
        records=[rec("fresh",2),rec("expiring",11),rec("expired",16),rec("future",-2)]
        exact={"records":[{"preview":{"id":"fresh"},"source_price_list_id":"123456789",
                          "observed_at_utc":records[0]["flight"]["flight_checked_at_utc"]}]}
        result=report({"records":records},exact,moment)
        self.assertEqual(result["receipt_fresh"],2)
        self.assertEqual(result["receipt_expired"],1)
        self.assertEqual(result["receipt_future"],1)
        self.assertEqual(result["receipt_expires_within_5m"],1)
        self.assertEqual(result["fresh_ids_missing_exact"],1)
        self.assertEqual(result["exact_timestamp_and_list_matches"],1)

    def test_exact_route_handoff_survives_rotating_source_and_public_price_validation(self):
        import hashlib
        moment=datetime.now(timezone.utc)
        current=feed()
        current["refreshed_at_utc"]=moment.isoformat()
        row=dict(current["previews"][0])
        row.update(depart_date=(moment.date()+timedelta(days=365)).isoformat(),
                   price_reference_rub=None,price_reference_party="UNVERIFIED")
        key="|".join((row["country"],row["hotel_id"],row["depart_date"],str(row["nights"]),row["room"]))
        row["id"]="p_"+hashlib.sha256(key.encode()).hexdigest()[:24]
        d={"countries":[{"name":"Турция"}],"hotels":[{"id":row["hotel_id"],"name":"TEST","country":"Турция"}]}
        when=moment.isoformat()
        common={"source_price_list_id":"123456789","source_route_id":"123456788",
                "browser_session_digest":"b"*64,"origin":"Иркутск","country":"Турция",
                "depart_date":row["depart_date"]}
        route={**common,"source":"BG_OFFICIAL_BROWSER_ROUTE","badge_text":"ЛУЧШАЯ ЦЕНА",
               "badge_scope":"SELECTED_ROUTE_ROW","route_clicked":True,
               "page_url":"https://www.bgoperator.ru/price.shtml",
               "origin_city_id":"100510397223","badge_seen_at_utc":when,"route_clicked_at_utc":when}
        flight={**common,"source":"BG_OFFICIAL_BROWSER_SELECTED_DETAIL","out_green":True,
                "back_green":True,"stop_sale":False,"hotel_id":row["hotel_id"],"room":row["room"],
                "nights":row["nights"],"source_preview_id":row["id"],"flight_checked_at_utc":when}
        receipts={"schema":"jamaica.bg-bot-private-receipts.v1","records":[
            {"preview_id":row["id"],"route":route,"flight":flight}]}
        record={"preview":row,"source_price_list_id":"123456789","observed_at_utc":when}
        with tempfile.TemporaryDirectory() as work:
            target=Path(work)/"private-site-exact-source.json"
            def save(item):
                target.write_text(json.dumps({"schema":"jamaica.bg-site-exact-source.v1","records":[item]}))
                target.chmod(0o600)
            save(record)
            merged,n=publisher.merge_exact_browser_source(current,d,receipts,path=target,now=moment)
            self.assertEqual(n,1)
            self.assertEqual(merged["previews"][0],row)
            projected,n2=publisher.merge_exact_browser_source({**current,"previews":[]},d,receipts,path=target,now=moment)
            self.assertEqual(n2,1)
            self.assertEqual(projected["previews"],[row])
            visual=publisher.visual.build_visual_feed(merged["previews"],receipts,now=moment)
            public=publisher.eligibility.select_public_source_rows(merged,visual,now=moment)
            prices={"schema":"jamaica.bg-site-dom-prices.v1","records":[
                {"preview_id":row["id"],"source_price_list_id":"123456789","browser_session_digest":"b"*64,
                 "observed_at_utc":when,"price_total_rub":99000}]}
            priced=publisher.browser_price.apply(public,receipts,visual,prices,now=moment)
            self.assertEqual(priced["previews"][0]["price_reference_rub"],99000)
            self.assertEqual(publisher.validate(priced,d,allow_browser_prices=True),1)
            with self.assertRaises(publisher.CatalogHold):publisher.validate(priced,d)
            stale={**priced,"previews":[{**priced["previews"][0],
                "price_observed_at_utc":(moment-timedelta(minutes=16)).isoformat()}]}
            with self.assertRaises(publisher.CatalogHold):publisher.validate(stale,d,allow_browser_prices=True)
            self.assertEqual(publisher.merge_exact_browser_source(current,d,None,path=target,now=moment)[1],0)
            self.assertEqual(publisher.merge_exact_browser_source(current,d,receipts,path=target,now=moment+timedelta(minutes=16))[1],0)
            save({**record,"source_price_list_id":"123456780"})
            self.assertEqual(publisher.merge_exact_browser_source(current,d,receipts,path=target,now=moment)[1],0)
            save(record);target.chmod(0o644)
            self.assertEqual(publisher.merge_exact_browser_source(current,d,receipts,path=target,now=moment)[1],0)

    def test_cooldown_and_broad_scan_throttle(self):
        moment=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            state=root/"state.json"
            with patch.object(publisher,"RUNROOT",root):
                self.assertFalse(publisher.provider_hold_active(path=state,now=moment))
                state.write_text(json.dumps({"schema":"jamaica.site-bot.v1",
                    "provider_hold_until_utc":(moment+timedelta(minutes=25)).isoformat()}))
                state.chmod(0o600)
                self.assertTrue(publisher.provider_hold_active(path=state,now=moment))
                self.assertFalse(publisher.provider_hold_active(path=state,now=moment+timedelta(minutes=26)))
                state.chmod(0o644)
                self.assertTrue(publisher.provider_hold_active(path=state,now=moment))
                self.assertTrue(publisher.source_scan_due(now=moment))
                publisher.mark_source_attempt(now=moment)
                self.assertFalse(publisher.source_scan_due(now=moment+timedelta(minutes=29)))
                self.assertTrue(publisher.source_scan_due(now=moment+timedelta(minutes=31)))

    def test_discovery_slot_survives_missed_intervals_and_migrates(self):
        moment=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            marker=root/".source-scan-last-attempt-v21.json"
            marker.write_text(json.dumps({"attempt_at_utc":(moment-timedelta(hours=1)).isoformat()}))
            marker.chmod(0o600)
            with patch.object(publisher,"RUNROOT",root):
                first=publisher.mark_source_attempt(now=moment)
                self.assertEqual(first,int(moment.timestamp()//1800))
                self.assertFalse(publisher.source_scan_due(now=moment+timedelta(minutes=29)))
                self.assertTrue(publisher.source_scan_due(now=moment+timedelta(hours=7)))
                self.assertEqual(publisher.mark_source_attempt(now=moment+timedelta(hours=7)),first+1)
                self.assertEqual(publisher.mark_source_attempt(now=moment+timedelta(days=1)),first+2)
                self.assertEqual(json.loads(marker.read_text())["probe_slot"],first+2)
                self.assertEqual(marker.stat().st_mode&0o777,0o600)
                marker.write_text(json.dumps({"attempt_at_utc":moment.isoformat(),"probe_slot":True}))
                self.assertFalse(publisher.source_scan_due(now=moment+timedelta(days=2)))
                with self.assertRaises(ValueError):publisher.mark_source_attempt(now=moment+timedelta(days=2))

    def test_browser_recovery_priority_is_bounded_and_not_a_hold_override(self):
        moment=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as work:
            path=Path(work)/"state.json"
            state={"schema":"jamaica.site-bot.v1",
                   "provider_hold_until_utc":moment.isoformat(),
                   "last_completed_at_utc":(moment-timedelta(minutes=30)).isoformat()}
            def write():
                path.write_text(json.dumps(state));path.chmod(0o600)
            write()
            self.assertTrue(publisher.browser_recovery_priority(path=path,now=moment))
            self.assertFalse(publisher.browser_recovery_priority(path=path,now=moment+timedelta(minutes=9)))
            state["last_completed_at_utc"]=moment.isoformat();write()
            self.assertFalse(publisher.browser_recovery_priority(path=path,now=moment+timedelta(minutes=1)))

    def test_rate_limit_recovery_prioritizes_browser_for_one_hour(self):
        moment=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as work:
            path=Path(work)/"state.json"
            state={"schema":"jamaica.site-bot.v1",
                   "provider_hold_until_utc":moment.isoformat(),
                   "last_completed_at_utc":(moment+timedelta(minutes=3)).isoformat(),
                   "provider_last_hold":{"http_status":429,"stage":"API_FILES",
                       "observed_at_utc":(moment-timedelta(minutes=30)).isoformat()}}
            def write():
                path.write_text(json.dumps(state));path.chmod(0o600)
            write()
            self.assertTrue(publisher.provider_hold_active(path=path,now=moment-timedelta(seconds=1)))
            self.assertFalse(publisher.provider_hold_active(path=path,now=moment))
            self.assertTrue(publisher.browser_recovery_priority(path=path,now=moment+timedelta(minutes=5)))
            self.assertTrue(publisher.browser_recovery_priority(path=path,now=moment+timedelta(minutes=59)))
            self.assertFalse(publisher.browser_recovery_priority(path=path,now=moment+timedelta(minutes=60)))
            state["provider_last_hold"]["http_status"]=503;write()
            self.assertTrue(publisher.browser_recovery_priority(path=path,now=moment+timedelta(minutes=10)))
            state["provider_last_hold"]["http_status"]=401;write()
            self.assertFalse(publisher.browser_recovery_priority(path=path,now=moment+timedelta(minutes=10)))
            state["provider_last_hold"]["http_status"]=429
            state["provider_last_hold"]["observed_at_utc"]="invalid";write()
            self.assertTrue(publisher.browser_recovery_priority(path=path,now=moment))

    def test_v107_broad_rate_quarantine_boundary_and_no_browser_gap_change(self):
        moment=datetime.now(timezone.utc)
        with tempfile.TemporaryDirectory() as work:
            path=Path(work)/"state.json"
            state={"schema":"jamaica.site-bot.v1","provider_hold_until_utc":moment.isoformat(),
                   "provider_last_hold":{"http_status":429,"stage":"API_FILES",
                   "observed_at_utc":(moment-timedelta(minutes=30)).isoformat()}}
            def write():
                path.write_text(json.dumps(state));path.chmod(0o600)
            write()
            before=path.read_bytes()
            self.assertFalse(publisher.provider_hold_active(path=path,now=moment+timedelta(hours=2)))
            self.assertFalse(publisher.browser_recovery_priority(path=path,now=moment+timedelta(hours=2)))
            self.assertTrue(publisher.broad_scan_rate_quarantine(path=path,now=moment+timedelta(hours=2)))
            self.assertTrue(publisher.broad_scan_rate_quarantine(path=path,now=moment+timedelta(hours=24,seconds=-1)))
            self.assertFalse(publisher.broad_scan_rate_quarantine(path=path,now=moment+timedelta(hours=24)))
            self.assertEqual(path.read_bytes(),before)
            state["provider_last_hold"]["http_status"]=503;write()
            self.assertTrue(publisher.broad_scan_rate_quarantine(path=path,now=moment+timedelta(hours=2)))
            state["provider_last_hold"]["observed_at_utc"]="bad";write()
            self.assertTrue(publisher.broad_scan_rate_quarantine(path=path,now=moment+timedelta(days=2)))
            state["provider_last_hold"]["http_status"]=401;write()
            self.assertFalse(publisher.broad_scan_rate_quarantine(path=path,now=moment+timedelta(hours=2)))
            self.assertFalse(publisher.broad_scan_rate_quarantine(path=path.with_name("missing"),now=moment))

    def test_v107_quarantine_no_supplier_calls_even_when_scan_due(self):
        with patch.object(publisher,"broad_scan_rate_quarantine",return_value=True), \
             patch.object(publisher,"source_scan_due",return_value=True), \
             patch.object(publisher,"mark_source_attempt") as mark, \
             patch.object(publisher,"refresh_directory") as refresh, \
             patch.object(publisher,"refresh_source_feed") as scan:
            self.assertEqual(publisher.guarded_source_scan(),(None,None))
            mark.assert_not_called();refresh.assert_not_called();scan.assert_not_called()

    def test_v107_quarantine_rechecked_after_lock(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);root.chmod(0o700)
            state=root/"state.json";(root/"lock").touch(mode=0o600)
            with patch.object(publisher,"BOT_STATE",state), \
                 patch.object(publisher,"broad_scan_rate_quarantine",side_effect=[False,True]), \
                 patch.object(publisher,"source_scan_due",return_value=True), \
                 patch.object(publisher,"provider_hold_active",return_value=False), \
                 patch.object(publisher,"browser_recovery_priority",return_value=False), \
                 patch.object(publisher,"mark_source_attempt") as mark, \
                 patch.object(publisher,"refresh_source_feed") as scan:
                self.assertEqual(publisher.guarded_source_scan(),(None,None))
                mark.assert_not_called();scan.assert_not_called()

    def test_shared_scan_guard_serializes_without_blocking_publication(self):
        import fcntl
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);root.chmod(0o700)
            state=root/"state.json";lock=root/"lock";lock.touch(mode=0o600)
            site=root/"site";site.mkdir()
            (site/"destination-directory.json").write_text(json.dumps(directory()))
            with patch.object(publisher,"BOT_STATE",state),patch.object(publisher,"CHECKOUT",site), \
                 patch.object(publisher,"provider_hold_active",return_value=False), \
                 patch.object(publisher,"source_scan_due",return_value=True), \
                 patch.object(publisher,"browser_recovery_priority",return_value=False), \
                 patch.object(publisher,"mark_source_attempt",return_value=42) as mark, \
                 patch.object(publisher,"refresh_directory") as refresh_dir, \
                 patch.object(publisher,"refresh_source_feed",return_value=feed()) as scan:
                with lock.open("r+") as existing:
                    fcntl.flock(existing,fcntl.LOCK_EX|fcntl.LOCK_NB)
                    self.assertEqual(publisher.guarded_source_scan(),(None,None))
                    mark.assert_not_called();refresh_dir.assert_not_called();scan.assert_not_called()
                self.assertEqual(publisher.guarded_source_scan()[0],feed())
                scan.assert_called_once_with(directory(),probe_slot=42)
                with patch.object(publisher,"browser_recovery_priority",return_value=True):
                    self.assertEqual(publisher.guarded_source_scan(),(None,None))
                scan.assert_called_once()
                lock.chmod(0o644)
                self.assertEqual(publisher.guarded_source_scan(),(None,None))
                scan.assert_called_once()

    def test_optional_media_does_not_compete_with_live_tour_search(self):
        import fcntl
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);root.chmod(0o700)
            lock=root/"lock";lock.touch(mode=0o600)
            with patch.object(publisher,"BOT_STATE",root/"state.json"), \
                 patch.object(publisher,"provider_hold_active",return_value=False) as hold, \
                 patch.object(publisher,"browser_recovery_priority",return_value=False) as recovery, \
                 patch.object(publisher,"discover_hotel_media_daily") as media:
                with patch.dict(publisher.os.environ,{},clear=True):
                    publisher.guarded_optional_hotel_media()
                    media.assert_not_called()
                with patch.dict(publisher.os.environ,{"JAMAICA_ENABLE_OPTIONAL_BG_MEDIA_DISCOVERY":"yes"},clear=True):
                    hold.return_value=True
                    publisher.guarded_optional_hotel_media()
                    media.assert_not_called()
                    hold.return_value=False
                    recovery.return_value=True
                    publisher.guarded_optional_hotel_media()
                    media.assert_not_called()
                    recovery.return_value=False
                    with lock.open("r+") as existing:
                        fcntl.flock(existing,fcntl.LOCK_EX|fcntl.LOCK_NB)
                        publisher.guarded_optional_hotel_media()
                        media.assert_not_called()
                    hold.side_effect=[False,True]
                    publisher.guarded_optional_hotel_media()
                    media.assert_not_called()
                    hold.side_effect=None
                    publisher.guarded_optional_hotel_media()
                    media.assert_called_once()
                    lock.chmod(0o644)
                    publisher.guarded_optional_hotel_media()
                    media.assert_called_once()

    def test_projection_grace_waits_for_existing_browser_and_releases_lock(self):
        import fcntl
        import threading
        import time
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);root.chmod(0o700)
            lock=root/"lock";lock.touch(mode=0o600)
            with lock.open("r+") as existing:
                fcntl.flock(existing,fcntl.LOCK_EX|fcntl.LOCK_NB)
                self.assertEqual(publisher.wait_for_browser_projection(lock=lock,max_wait=0),
                                 "BROWSER_STILL_BUSY_USE_STRICT_PROJECTION")
                def release():
                    time.sleep(0.04)
                    fcntl.flock(existing,fcntl.LOCK_UN)
                t=threading.Thread(target=release)
                t.start()
                try:
                    self.assertEqual(publisher.wait_for_browser_projection(lock=lock,max_wait=1),
                                     "BROWSER_COMPLETED")
                finally:t.join()
                fcntl.flock(existing,fcntl.LOCK_EX|fcntl.LOCK_NB)
                fcntl.flock(existing,fcntl.LOCK_UN)
            self.assertEqual(publisher.wait_for_browser_projection(lock=lock,max_wait=0),"BROWSER_IDLE")
            lock.chmod(0o644)
            self.assertEqual(publisher.wait_for_browser_projection(lock=lock,max_wait=0),"LOCK_UNAVAILABLE")
            lock.unlink()
            self.assertEqual(publisher.wait_for_browser_projection(lock=lock,max_wait=0),"LOCK_UNAVAILABLE")
            with self.assertRaises(ValueError):publisher.wait_for_browser_projection(lock=lock,max_wait=46)

    def test_projection_does_not_renew_old_source_rows_or_timestamp(self):
        moment=datetime.now(timezone.utc)
        old=feed()
        old["refreshed_at_utc"]=(moment-timedelta(hours=1)).isoformat()
        old["countries_status"]=[{"country":"Турция","previews":1}]
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);path=root/"generated-tour-previews.json"
            path.write_text(json.dumps(old));path.chmod(0o600)
            before=path.read_bytes()
            with patch.object(publisher,"RUNROOT",root):
                new=publisher.projection_base(now=moment)
            self.assertEqual(new["previews"],[])
            self.assertEqual(new["indicative_two_adult_rub_count"],0)
            self.assertEqual(new["source_scope"]["source_scan_refreshed_at_utc"],old["refreshed_at_utc"])
            self.assertFalse(new["source_scope"]["source_scan_performed_this_cycle"])
            self.assertEqual(path.read_bytes(),before)
            self.assertEqual(publisher.validate(new,directory(),allow_empty=True),0)

    def test_hold_projection_without_any_supplier_request(self):
        from types import SimpleNamespace
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);site=root/"site";site.mkdir()
            (site/"destination-directory.json").write_text(json.dumps(directory()))
            def git_only(args,**kwargs):
                self.assertEqual(args[0],"git")
                return SimpleNamespace(stdout="",returncode=0)
            with patch.object(publisher,"RUNROOT",root), \
                 patch.object(publisher,"CHECKOUT",site), \
                 patch.object(publisher,"provider_hold_active",return_value=True), \
                 patch.object(publisher,"refresh_directory") as refresh_dir, \
                 patch.object(publisher,"refresh_source_feed") as scan, \
                 patch.object(publisher.visual,"read_private_receipts",return_value=None), \
                 patch.object(publisher.browser_price,"read_ledger",return_value=None), \
                 patch.object(publisher,"save_recent_source_cache") as save_cache, \
                 patch.object(publisher,"run",side_effect=git_only):
                publisher.publish({})
                refresh_dir.assert_not_called();scan.assert_not_called();save_cache.assert_not_called()
            out=json.loads((site/"tour-previews.json").read_text())
            self.assertEqual(out["previews"],[])
            self.assertEqual(out["total_published_previews"],0)
            self.assertEqual(json.loads((site/"tour-visual-evidence.json").read_text())["entries"],[])

    def test_visual_serializer_accepts_10000_proofs_and_rejects_stale(self):
        moment=datetime.now(timezone.utc)
        proof=publisher.visual.empty_public()
        proof["entries"]=[{"preview_id":"p_"+format(i,"024x"),
            "observed_at_utc":moment.isoformat(),"route_best_price_seen":True,
            "both_green_planes_seen":True} for i in range(10000)]
        encoded=publisher.encode_public_visual_feed(proof,now=moment)
        self.assertGreater(len(encoded),500_000)
        self.assertLess(len(encoded),publisher.MAX_PUBLIC_VISUAL_BYTES)
        self.assertEqual(len(json.loads(encoded)["entries"]),10000)
        with self.assertRaises(publisher.CatalogHold):
            publisher.encode_public_visual_feed(proof,now=moment+timedelta(minutes=16))

    def test_10000_exact_source_prices_proofs_and_shards_end_to_end(self):
        import hashlib
        from backend.test_bg_route_first_visual_gate import bundle
        moment=datetime.now(timezone.utc)
        d={"countries":[{"name":"Турция"}],"hotels":[{"id":"123456789","name":"TEST","country":"Турция"}]}
        base=feed()
        base.update(refreshed_at_utc=moment.isoformat(),previews=[])
        rows=[]; records=[]; prices=[]; evidence=[]
        for i in range(10000):
            row=dict(feed()["previews"][0])
            row.update(depart_date=(moment.date()+timedelta(days=10)).isoformat(),
                       room="DBL "+str(i),price_reference_rub=None,price_reference_party="UNVERIFIED")
            key="|".join((row["country"],row["hotel_id"],row["depart_date"],str(row["nights"]),row["room"]))
            row["id"]="p_"+hashlib.sha256(key.encode()).hexdigest()[:24]
            route,flight=bundle(row,now=moment)
            source=route["source_price_list_id"];when=flight["flight_checked_at_utc"]
            rows.append(row)
            records.append({"preview":row,"source_price_list_id":source,"observed_at_utc":when})
            prices.append({"preview_id":row["id"],"source_price_list_id":source,
                "browser_session_digest":route["browser_session_digest"],"observed_at_utc":when,
                "price_total_rub":99000+i})
            evidence.append({"preview_id":row["id"],"route":route,"flight":flight})
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            def save(name,doc):
                p=root/name;p.write_text(json.dumps(doc,ensure_ascii=False,separators=(",",":")));p.chmod(0o600);return p
            source_path=save("exact.json",{"schema":"jamaica.bg-site-exact-source.v1","records":records})
            receipt_path=save("proofs.json",{"schema":publisher.visual.PRIVATE_SCHEMA,"records":evidence})
            price_path=save("prices.json",{"schema":publisher.browser_price.SCHEMA,"records":prices})
            receipts=publisher.visual.read_private_receipts(receipt_path)
            ledger=publisher.browser_price.read_ledger(price_path)
            merged,n=publisher.merge_exact_browser_source(base,d,receipts,path=source_path,now=moment)
            self.assertEqual(n,10000)
            proof=publisher.visual.build_visual_feed(merged["previews"],receipts,now=moment)
            self.assertEqual(len(proof["entries"]),10000)
            publisher.encode_public_visual_feed(proof,now=moment)
            filtered=publisher.eligibility.select_public_source_rows(merged,proof,now=moment)
            priced=publisher.browser_price.apply(filtered,receipts,proof,ledger,now=moment)
            self.assertEqual(priced["indicative_two_adult_rub_count"],10000)
            root_feed,chunks=publisher.make_sharded_catalog(priced)
            self.assertEqual(root_feed["total_published_previews"],10000)
            self.assertEqual(len(root_feed["previews"]),8000)
            self.assertEqual(sum(len(c["previews"]) for c in chunks.values()),2000)
            self.assertEqual(publisher.validate(root_feed,d,allow_browser_prices=True),8000)
            self.assertEqual(publisher.visual.build_visual_feed(merged["previews"],receipts,now=moment+timedelta(minutes=16))["entries"],[])

    def test_private_source_refresh_preserves_previous_feed_until_validated(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            target=root/"generated-tour-previews.json"
            old=feed()
            target.write_text(json.dumps(old))
            target.chmod(0o600)
            previous=target.read_bytes()
            new=feed()
            new["previews"][0]["price_reference_rub"]=99000
            def export(args, **kwargs):
                self.assertEqual(args[args.index("--probe-slot")+1],"42")
                self.assertEqual(target.read_bytes(),previous)
                staging=Path(args[args.index("--output")+1])
                self.assertNotEqual(staging,target)
                staging.write_text(json.dumps(new))
                return publisher.subprocess.CompletedProcess(args,0,"","")
            with patch.object(publisher,"RUNROOT",root), \
                 patch.object(publisher,"run",side_effect=export), \
                 patch.object(publisher.identity,"verify_catalog_hotel_identity") as check:
                self.assertEqual(publisher.refresh_source_feed(directory(),probe_slot=42),new)
                check.assert_called_once_with(new["previews"],directory())
            self.assertEqual(json.loads(target.read_text()),new)
            self.assertEqual(target.stat().st_mode & 0o777,0o600)
            self.assertEqual(list(root.iterdir()),[target])

    def test_private_source_refresh_failure_preserves_previous_bytes(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work)
            target=root/"generated-tour-previews.json"
            target.write_text(json.dumps(feed()))
            previous=target.read_bytes()
            for mode in ("export_failure","missing","invalid"):
                def export(args, **kwargs):
                    self.assertEqual(target.read_bytes(),previous)
                    if mode=="export_failure":
                        raise publisher.CatalogHold("SOURCE_TEST_FAILURE")
                    if mode=="invalid":
                        staging=Path(args[args.index("--output")+1])
                        staging.write_text(json.dumps({**feed(),"bookable":True}))
                    return publisher.subprocess.CompletedProcess(args,0,"","")
                with patch.object(publisher,"RUNROOT",root), \
                     patch.object(publisher,"run",side_effect=export):
                    with self.assertRaises(publisher.CatalogHold):
                        publisher.refresh_source_feed(directory())
                self.assertEqual(target.read_bytes(),previous)
                self.assertEqual(list(root.iterdir()),[target])

    def test_shared_provider_hold_protocol(self):
        signal=publisher.parse_export_provider_hold("OTHER\nJAMAICA_BG_EXPORT_PROVIDER_HOLD=429:3600\n")
        self.assertEqual((signal.status,signal.seconds),(429,3600))
        for value in ("", "JAMAICA_BG_EXPORT_PROVIDER_HOLD=429:1799",
            "JAMAICA_BG_EXPORT_PROVIDER_HOLD=200:1800",
            "JAMAICA_BG_EXPORT_PROVIDER_HOLD=429:31536001",
            "JAMAICA_BG_EXPORT_PROVIDER_HOLD=429:1800\nJAMAICA_BG_EXPORT_PROVIDER_HOLD=429:1800",
            "JAMAICA_BG_EXPORT_PROVIDER_HOLD=429:1800 extra"):
            self.assertIsNone(publisher.parse_export_provider_hold(value))

    def test_shared_provider_hold_preserves_state_and_longer_pause(self):
        with tempfile.TemporaryDirectory() as work:
            state=Path(work)/"state.json"
            old={"schema":"jamaica.site-bot.v1","cycle":87,"v49_last_exact_api_attempt_utc":NOW.isoformat()}
            state.write_text(json.dumps(old));state.chmod(0o600)
            end=publisher.persist_source_provider_hold(publisher.SourceProviderHold(429,3600),path=state,now=NOW)
            result=json.loads(state.read_text())
            self.assertEqual(end,NOW+timedelta(hours=1))
            for key,value in old.items():self.assertEqual(result[key],value)
            self.assertEqual(result["provider_last_hold"]["source"],"PUBLISHER_BROAD_SCAN")
            self.assertTrue(publisher.provider_hold_active(path=state,now=NOW))
            before=state.read_bytes()
            self.assertEqual(publisher.persist_source_provider_hold(publisher.SourceProviderHold(503,1800),path=state,now=NOW),end)
            self.assertEqual(state.read_bytes(),before)
            self.assertEqual(state.stat().st_mode&0o777,0o600)
            self.assertEqual(list(Path(work).iterdir()),[state])

    def test_shared_provider_hold_invalid_state_rejected(self):
        with tempfile.TemporaryDirectory() as work:
            state=Path(work)/"state.json"
            state.write_text(json.dumps({"schema":"jamaica.site-bot.v1","provider_hold_until_utc":"invalid"}));state.chmod(0o600)
            before=state.read_bytes()
            with self.assertRaises(publisher.CatalogHold):
                publisher.persist_source_provider_hold(publisher.SourceProviderHold(429,1800),path=state,now=NOW)
            self.assertEqual(state.read_bytes(),before)

    def test_source_export_rate_limit_preserves_previous_feed(self):
        with tempfile.TemporaryDirectory() as work:
            root=Path(work);target=root/"generated-tour-previews.json"
            target.write_text(json.dumps(feed()));before=target.read_bytes()
            proc=publisher.subprocess.CompletedProcess(["export"],2,"JAMAICA_BG_EXPORT_PROVIDER_HOLD=429:3600\n","")
            with patch.object(publisher,"RUNROOT",root),patch.object(publisher,"run",return_value=proc):
                with self.assertRaises(publisher.SourceProviderHold) as raised:
                    publisher.refresh_source_feed(directory(),probe_slot=42)
                self.assertEqual((raised.exception.status,raised.exception.seconds),(429,3600))
            self.assertEqual(target.read_bytes(),before)
            self.assertEqual(list(root.iterdir()),[target])

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
