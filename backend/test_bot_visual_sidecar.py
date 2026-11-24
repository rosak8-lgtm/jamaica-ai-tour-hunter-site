"""Route-first bot visual sidecar is safe and always nonbookable."""
import json
import os
from pathlib import Path
from datetime import datetime,timedelta,timezone
import tempfile
import unittest

from scripts.bot_visual_sidecar import (
    PRIVATE_SCHEMA, read_private_receipts, build_visual_feed,
    validate_public_feed, VisualHold,empty_public,
)
from backend.test_bg_route_first_visual_gate import sample,bundle

class Tests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.p={**sample(),"status":"REFERENCE_PRICE_LIST_ONLY"}
        self.route,self.flight=bundle(self.p,now=self.now)
        self.record={"preview_id":self.p["id"],
                     "route":self.route,"flight":self.flight}
    def input(self,rows=None):
        return {"schema":PRIVATE_SCHEMA,
                "records":[self.record] if rows is None else rows}

    def test_same_selected_hotel_date_route_and_two_flights_yields_visual_only(self):
        out=build_visual_feed([self.p],self.input(),now=self.now)
        self.assertTrue(validate_public_feed(out,now=self.now))
        self.assertEqual(len(out["entries"]),1)
        self.assertEqual(out["entries"][0]["preview_id"],self.p["id"])
        self.assertEqual(out["entries"][0]["route_best_price_seen"],True)
        self.assertEqual(out["entries"][0]["both_green_planes_seen"],True)
        self.assertIs(out["bookable"],False)
        self.assertIs(out["quote_verified"],False)
        self.assertIs(out["availability_verified"],False)
        self.assertNotIn("source_price_list_id",json.dumps(out))
        self.assertNotIn("browser_session_digest",json.dumps(out))
        self.assertNotIn("bgoperator.ru",json.dumps(out))
        self.assertNotIn("total_rub",json.dumps(out))

    def test_invalid_and_expired_receipts_are_never_published(self):
        for row in (
            {**self.record,"preview_id":"p_"+"a"*24},
            {**self.record,"flight":{**self.flight,"back_green":False}},
            {**self.record,"route":{**self.route,"route_clicked":False}},
            {**self.record,"flight":{**self.flight,
                                    "hotel_id":"1234567890"}},
            {**self.record,"flight":{**self.flight,
                 "flight_checked_at_utc":(self.now-timedelta(minutes=25)).isoformat()}},
        ):
            with self.subTest(row=row.get("preview_id")):
                out=build_visual_feed([self.p],self.input([row]),
                                      now=self.now)
                self.assertEqual(out["entries"],[])

    def test_previously_seen_not_rechecked_never_eligible(self):
        prior={**self.p,"status":"PREVIOUSLY_SEEN_NOT_RECHECKED",
               "price_reference_rub":None}
        self.assertEqual(build_visual_feed([prior],self.input(),
                                           now=self.now)["entries"],[])

    def test_duplicate_receipts_are_collapsed(self):
        result=build_visual_feed([self.p],self.input([self.record]*10),
                                 now=self.now)
        self.assertEqual(len(result["entries"]),1)
        self.assertEqual(result["entries"][0]["preview_id"],self.p["id"])

    def test_capacity_1000_and_expired_receipt_exclusion(self):
        from scripts.bot_visual_sidecar import MAX_PRIVATE_RECORDS, MAX_PUBLIC_RECORDS
        self.assertEqual(MAX_PRIVATE_RECORDS,1000)
        self.assertEqual(MAX_PUBLIC_RECORDS,1000)
        previews=[]; records=[]
        for i in range(1000):
            p={**self.p,"id":"p_"+format(i,"024x")}
            route,flight=bundle(p,now=self.now)
            previews.append(p)
            records.append({"preview_id":p["id"],"route":route,"flight":flight})
        out=build_visual_feed(previews,self.input(records),now=self.now)
        self.assertEqual(len(out["entries"]),1000)
        self.assertTrue(validate_public_feed(out,now=self.now))
        self.assertFalse(validate_public_feed({**out,"entries":out["entries"]+[out["entries"][0]]},now=self.now))
        self.assertEqual(build_visual_feed(previews,self.input(records),now=self.now+timedelta(minutes=16))["entries"],[])

    def test_empty_or_invalid_source_never_grants_visual_status(self):
        self.assertEqual(build_visual_feed([self.p],None,now=self.now),
                         empty_public())
        with self.assertRaises(VisualHold):
            build_visual_feed([self.p],{"schema":"bad","records":[]},
                              now=self.now)
        self.assertFalse(validate_public_feed({
            **empty_public(),"bookable":True},now=self.now))
        self.assertFalse(validate_public_feed({
            **empty_public(),"entries":[{
              "preview_id":self.p["id"],"observed_at_utc":self.now.isoformat(),
              "route_best_price_seen":True,"both_green_planes_seen":False
            }]},now=self.now))

    def test_owner_only_private_file_and_no_symlinks(self):
        with tempfile.TemporaryDirectory() as root:
            p=Path(root)/"bot.json"
            p.write_text(json.dumps(self.input()),encoding="utf8")
            os.chmod(p,0o600)
            self.assertEqual(read_private_receipts(p)["schema"],PRIVATE_SCHEMA)
            os.chmod(p,0o644)
            with self.assertRaises(VisualHold):read_private_receipts(p)
            os.chmod(p,0o600)
            link=Path(root)/"alias.json"
            link.symlink_to(p)
            with self.assertRaises(VisualHold):read_private_receipts(link)
            p.unlink()
            self.assertIsNone(read_private_receipts(p))

if __name__=="__main__":unittest.main()
