"""One-click sharded tour selection is offline, source-backed and private."""
import hashlib
import json
import os
from datetime import date
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from scripts import local_selected_preview as selector

TODAY=date(2026,11,23)

def row(i,country="Таиланд",*,old=False,departure="2026-12-11"):
    return {
        "id":"p_"+format(i,"024x"),
        "hotel_id":"102610001486","hotel":"SYNTHETIC HOTEL",
        "country":country,"origin":"Иркутск","resort":"Sample resort",
        "room":"STANDARD HB","depart_date":departure,"nights":7,
        "status":"PREVIOUSLY_SEEN_NOT_RECHECKED" if old else
                 "REFERENCE_PRICE_LIST_ONLY",
        "price_reference_rub":None if old else 99000,
        "price_reference_party":"UNVERIFIED" if old else "TWO_ADULTS",
        "bookable":False,"quote_verified":False,
        "availability_verified":False,"flight_verified":False,
    }

def write_catalog(folder,root_rows,parts):
    root={"schema":"jamaica.tour-previews.v1",
          "refreshed_at_utc":"2026-11-23T01:20:00+00:00",
          "bookable":False,"quote_verified":False,
          "availability_verified":False,
          "previews":root_rows,"shards":[],
          "total_published_previews":len(root_rows)+sum(map(len,parts))}
    (folder/"tour-previews-shards").mkdir()
    for i,rows in enumerate(parts,1):
        path="tour-previews-shards/part-"+str(i).zfill(3)+".json"
        digest=hashlib.sha256(json.dumps(rows,sort_keys=True,
            ensure_ascii=False,separators=(",",":")).encode("utf-8")).hexdigest()
        root["shards"].append({"path":path,"count":len(rows),"sha256":digest})
        shard={"schema":"jamaica.tour-preview-shard.v1",
             "refreshed_at_utc":root["refreshed_at_utc"],
             "bookable":False,"quote_verified":False,
             "availability_verified":False,
             "previews":rows}
        (folder/path).write_text(json.dumps(shard,ensure_ascii=False),encoding="utf-8")
    p=folder/"tour-previews.json"
    p.write_text(json.dumps(root,ensure_ascii=False),encoding="utf-8")
    return p

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder=Path(self.tmp.name)

    def test_can_select_exact_tour_only_found_in_second_shard(self):
        full=write_catalog(self.folder,[row(1)],[ [row(2,"Турция")],
            [row(3,"Китай"),row(4,"Вьетнам")] ])
        id_,feed=selector.selected(full,preview_id=row(4)["id"],today=TODAY)
        self.assertEqual(id_,row(4)["id"])
        self.assertEqual(len(feed["previews"]),1)
        self.assertEqual(feed["previews"][0]["country"],"Вьетнам")
        self.assertFalse(feed["bookable"])
        self.assertFalse(feed["quote_verified"])
        self.assertNotIn("shards",feed)
        self.assertNotIn("source_scope",feed)
        output=self.folder/"private-temp.json"
        selector.save_private_feed(output,feed)
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        self.assertEqual(json.loads(output.read_text())["previews"][0]["id"],id_)
        with self.assertRaises(ValueError):
            selector.save_private_feed(output,feed)

    def test_prefer_actual_current_source_and_requested_country(self):
        full=write_catalog(self.folder,[row(1,"Китай",old=True)],
            [[row(2,"Индонезия"),row(3,"Китай")]])
        id_,_ =selector.selected(full,country="Китай",today=TODAY)
        self.assertEqual(id_,row(3)["id"])
        id_,_ =selector.selected(full,today=TODAY)
        self.assertEqual(id_,row(3)["id"])
        with self.assertRaises(ValueError):
            selector.selected(full,country="Неизвестная",today=TODAY)

    def test_expired_and_nonfuture_previews_are_not_eligible(self):
        full=write_catalog(self.folder,[row(1,departure="2026-11-22")],
            [[row(2,departure="2026-11-23")]])
        with self.assertRaises(ValueError):
            selector.selected(full,today=TODAY)

    def test_corrupted_shard_sha_blocks_even_a_root_selection(self):
        full=write_catalog(self.folder,[row(1)],[[row(2)]])
        shard=self.folder/"tour-previews-shards/part-001.json"
        data=json.loads(shard.read_text())
        data["previews"][0]["hotel"]="ATTACK"
        shard.write_text(json.dumps(data),encoding="utf-8")
        with self.assertRaises(ValueError):
            selector.selected(full,preview_id=row(1)["id"],today=TODAY)

    def test_duplicates_and_symlinks_are_rejected(self):
        full=write_catalog(self.folder,[row(1)],[[row(1)]])
        with self.assertRaises(ValueError):
            selector.selected(full,today=TODAY)
        shard=self.folder/"tour-previews-shards/part-001.json"
        shard.unlink()
        original=self.folder/"external.json"
        original.write_text('{"safe":false}')
        shard.symlink_to(original)
        with self.assertRaises(ValueError):
            selector.selected(full,today=TODAY)

    def test_wrong_inventory_and_private_fields_fail_closed(self):
        full=write_catalog(self.folder,[row(1)],[[row(2)]])
        root=json.loads(full.read_text())
        root["shards"][0]["path"]="../other.json"
        full.write_text(json.dumps(root),encoding="utf-8")
        with self.assertRaises(ValueError):
            selector.selected(full,today=TODAY)

    def test_public_stale_rows_can_never_retain_old_price(self):
        bad={**row(1,old=True),"price_reference_rub":88000}
        full=write_catalog(self.folder,[bad],[])
        with self.assertRaises(ValueError):
            selector.selected(full,today=TODAY)

    def test_private_supplier_metadata_cannot_enter_staged_feed(self):
        injected={**row(1),"prx":"PRIVATE_OPERATOR_SOURCE"}
        full=write_catalog(self.folder,[injected],[])
        with self.assertRaises(ValueError):
            selector.selected(full,today=TODAY)

    def test_cli_prints_only_public_id_and_creates_owner_only_feed(self):
        full=write_catalog(self.folder,[row(1,"Индонезия")],
            [[row(2,"Китай")]])
        output=self.folder/"selected.json"
        tool=Path(__file__).resolve().parent.parent/"scripts/local_selected_preview.py"
        result=subprocess.run([sys.executable,"-B",str(tool),
            "--root",str(full),"--country","Китай","--output",str(output)],
            capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(result.stdout.strip(),row(2)["id"])
        self.assertEqual(output.stat().st_mode&0o777,0o600)
        self.assertEqual(len(json.loads(output.read_text())["previews"]),1)

if __name__=="__main__":
    unittest.main()
