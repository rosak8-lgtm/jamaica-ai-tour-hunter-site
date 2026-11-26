"""V91 publisher bridge regression tests. All source evidence is synthetic."""
import copy
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from backend import test_bg_scoped_public_projection as fixture_module
from backend import test_oracle_site_publisher as publisher_tests
from scripts.bg_scoped_publisher_bridge import extend
from scripts.bot_visual_sidecar import empty_public

class Tests(unittest.TestCase):
    def setUp(self):
        fixture = fixture_module.Tests()
        fixture.setUp()
        self.now = fixture.now
        self.registry = fixture.reg
        self.staged = fixture.data
        self.directory = fixture.directory
        self.root = Path(self.enterContext(tempfile.TemporaryDirectory()))
        self.registry_path = self.root / "registry.json"
        self.staging = self.root / "private-bg-scoped-staging"
        self.staging.mkdir(mode=0o700)
        self.path = self.staging / (self.staged["origin_id"]+"-"+self.staged["country_id"]+".json")
        self.write(self.registry_path, self.registry)
        self.write(self.path, self.staged)
        self.legacy = publisher_tests.feed()
        self.visual = empty_public()
        self.visual["entries"] = [{"preview_id":self.legacy["previews"][0]["id"],
            "observed_at_utc":self.now.isoformat(), "route_best_price_seen":True,
            "both_green_planes_seen":True}]

    def write(self, path, obj):
        path.write_text(json.dumps(obj), encoding="utf-8")
        path.chmod(0o600)

    def run_bridge(self, now=None):
        return extend(self.legacy,self.visual,self.directory,self.registry_path,
                      self.staging,now=now or self.now)

    def assert_legacy(self, result):
        feed, visual, admitted, stats = result
        self.assertEqual(feed,self.legacy)
        self.assertEqual(visual,self.visual)
        self.assertEqual(admitted,{})
        self.assertEqual(stats["added"],0)

    def test_append_exact_pair_preserve_legacy(self):
        old=copy.deepcopy((self.legacy,self.visual))
        feed, visual, ids, stats = self.run_bridge()
        self.assertEqual(len(feed["previews"]),2)
        self.assertEqual(len(visual["entries"]),2)
        row=feed["previews"][1]; proof=visual["entries"][1]
        self.assertEqual(ids,{row["id"]:("Красноярск","Таиланд")})
        self.assertEqual(row["price_observed_at_utc"],proof["observed_at_utc"])
        self.assertEqual(row["id"],proof["preview_id"])
        self.assertEqual(stats["added"],1)
        self.assertEqual((self.legacy,self.visual),old)

    def test_missing_staging(self):
        self.path.unlink()
        self.staging.rmdir()
        self.assert_legacy(self.run_bridge())

    def test_bad_registry_permissions(self):
        self.registry_path.chmod(0o644)
        self.assert_legacy(self.run_bridge())

    def test_invalid_registry(self):
        self.registry["source"]="OTHER"
        self.write(self.registry_path,self.registry)
        self.assert_legacy(self.run_bridge())

    def test_symlink_ledger(self):
        target=self.root/"target.json"
        self.path.rename(target)
        self.path.symlink_to(target)
        self.assert_legacy(self.run_bridge())

    def test_hardlink_ledger(self):
        os.link(self.path,self.root/"hardlink")
        self.assert_legacy(self.run_bridge())

    def test_invalid_scope_filename(self):
        self.path.rename(self.staging/"100510397252-100410000051.json")
        self.assert_legacy(self.run_bridge())

    def test_bad_price_session(self):
        self.staged["records"][0]["price"]["browser_session_digest"]="b"*64
        self.write(self.path,self.staged)
        self.assert_legacy(self.run_bridge())

    def test_stale_and_reserve(self):
        self.assert_legacy(self.run_bridge(self.now+timedelta(seconds=875)))

    def test_collision_does_not_replace_legacy(self):
        ident=self.staged["records"][0]["preview"]["id"]
        self.legacy["previews"][0]["id"]=ident
        self.visual["entries"][0]["preview_id"]=ident
        self.assert_legacy(self.run_bridge())

    def test_corrupt_scope_does_not_interrupt_valid_scope(self):
        bad=self.staging/"100510397252-100410000051.json"
        bad.write_text("{broken")
        bad.chmod(0o600)
        feed, visual, ids, stats=self.run_bridge()
        self.assertEqual(len(ids),1)
        self.assertEqual(stats["rejected"],1)

    def test_final_publisher_requires_exact_admission(self):
        pub=publisher_tests.publisher
        feed, visual, ids, stats=self.run_bridge()
        directory={**self.directory,"countries":[{"name":"Таиланд"},{"name":"Турция"}]}
        clock=datetime.now(timezone.utc).isoformat()
        feed["refreshed_at_utc"]=clock
        feed["previews"][1]["price_observed_at_utc"]=clock
        with self.assertRaisesRegex(pub.CatalogHold,"FEED_WRONG_ORIGIN"):
            pub.validate(feed,directory,allow_browser_prices=True)
        with self.assertRaisesRegex(pub.CatalogHold,"FEED_WRONG_ORIGIN"):
            pub.validate(feed,directory,allow_browser_prices=True,scoped_ids={feed["previews"][1]["id"]:("Москва","Таиланд")})
        self.assertEqual(pub.validate(feed,directory,allow_browser_prices=True,scoped_ids=ids),2)

if __name__ == "__main__":
    unittest.main()
