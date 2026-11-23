"""Only the already trusted BG Playwright browser may save exact proof."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from datetime import datetime,timedelta,timezone

from backend.test_bg_route_first_visual_gate import bundle,sample
from scripts import trusted_bot_receipt_sink as sink
from scripts import bot_visual_sidecar as visual


class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)/"private-bg-route-first-receipts.json"
        self.now=datetime.now(timezone.utc)
        self.preview={**sample(),"status":"REFERENCE_PRICE_LIST_ONLY"}

    def test_real_source_bound_pair_saved_owner_only(self):
        route,flight=bundle(self.preview,now=self.now)
        self.assertTrue(sink.save_from_trusted_browser(route,flight,self.preview,
                         path=self.path,now=self.now))
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)
        private=visual.read_private_receipts(self.path)
        self.assertEqual(private["schema"],visual.PRIVATE_SCHEMA)
        self.assertEqual(len(private["records"]),1)
        self.assertEqual(private["records"][0]["preview_id"],self.preview["id"])
        public=visual.build_visual_feed([self.preview],private,now=self.now)
        self.assertTrue(visual.validate_public_feed(public,now=self.now))
        self.assertEqual(len(public["entries"]),1)
        self.assertNotIn("browser_session_digest",str(public))
        self.assertNotIn("page_url",str(public))

    def test_missing_badge_either_plane_stop_sale_or_source_mismatch_rejected(self):
        r,f=bundle(self.preview,now=self.now)
        for bad_route,bad_flight in [
            ({**r,"badge_text":"ЛУЧШАЯ ЦЕНА!"},f),
            ({**r,"route_clicked":False},f),
            (r,{**f,"out_green":False}),
            (r,{**f,"back_green":False}),
            (r,{**f,"stop_sale":True}),
            (r,{**f,"source_preview_id":"p_"+"b"*24}),
            (r,{**f,"browser_session_digest":"b"*64}),
            (r,{**f,"hotel_id":"102999999999"}),
            (r,{**f,"nights":8}),
            (r,{**f,"room":"OTHER ROOM"}),
        ]:
            with self.subTest(bad_route=bad_route!=r,
                              bad_flight=bad_flight!=f):
                self.assertFalse(sink.save_from_trusted_browser(
                    bad_route,bad_flight,self.preview,path=self.path,now=self.now))
                self.assertFalse(self.path.exists())

    def test_no_guest_or_token_keys_allowed(self):
        r,f=bundle(self.preview,now=self.now)
        self.assertFalse(sink.save_from_trusted_browser(
            {**r,"password":"SECRET"},f,self.preview,path=self.path,now=self.now))
        self.assertFalse(sink.save_from_trusted_browser(
            r,{**f,"passport":"SECRET"},self.preview,path=self.path,now=self.now))
        self.assertFalse(self.path.exists())

    def test_future_or_stale_session_cannot_become_public(self):
        r,f=bundle(self.preview,now=self.now)
        self.assertFalse(sink.save_from_trusted_browser(
            r,f,self.preview,path=self.path,now=self.now+timedelta(minutes=20)))
        self.assertFalse(sink.save_from_trusted_browser(
            r,{**f,"flight_checked_at_utc":
                (self.now+timedelta(minutes=5)).isoformat()},
            self.preview,path=self.path,now=self.now))
        self.assertFalse(self.path.exists())

    def test_duplicate_replaces_old_and_rejects_insecure_directory(self):
        r,f=bundle(self.preview,now=self.now)
        self.assertTrue(sink.save_from_trusted_browser(
            r,f,self.preview,path=self.path,now=self.now))
        self.assertTrue(sink.save_from_trusted_browser(
            r,f,self.preview,path=self.path,now=self.now))
        self.assertEqual(len(visual.read_private_receipts(self.path)["records"]),1)
        os.chmod(self.tmp.name,0o755)
        with self.assertRaises(visual.VisualHold):
            sink.save_from_trusted_browser(
                r,f,self.preview,path=self.path,now=self.now)

    def test_do_not_replace_corrupt_private_receipt(self):
        self.path.write_text("CORRUPTED EVIDENCE",encoding="utf-8")
        os.chmod(self.path,0o600)
        r,f=bundle(self.preview,now=self.now)
        with self.assertRaises(visual.VisualHold):
            sink.save_from_trusted_browser(
                r,f,self.preview,path=self.path,now=self.now)
        self.assertEqual(self.path.read_text(),"CORRUPTED EVIDENCE")


if __name__=="__main__":
    unittest.main()
