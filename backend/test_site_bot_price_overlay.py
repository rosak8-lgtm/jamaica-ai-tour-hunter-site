import json,os,tempfile
from pathlib import Path
from datetime import datetime,timedelta,timezone
import unittest
from scripts import site_bot_price_overlay as overlay

NOW=datetime(2026,11,23,18,0,tzinfo=timezone.utc)
PREVIEW="p_"+"a"*24
ID_PRICE="121132934133"
SESSION="e"*64
WHEN=(NOW-timedelta(seconds=30)).isoformat()
def base(amount=99999):
 return {"previews":[{"id":PREVIEW,"price_reference_rub":amount,
  "price_reference_party":"TWO_ADULTS","status":"REFERENCE_PRICE_LIST_ONLY",
  "bookable":False,"quote_verified":False}],
  "indicative_two_adult_rub_count":1}
def proof():
 return {"entries":[{"preview_id":PREVIEW,"observed_at_utc":WHEN,
  "route_best_price_seen":True,"both_green_planes_seen":True}]}
def private():
 return {"records":[{"preview_id":PREVIEW,
   "route":{"source_price_list_id":ID_PRICE,"browser_session_digest":SESSION},
   "flight":{"source_price_list_id":ID_PRICE,"browser_session_digest":SESSION,
             "flight_checked_at_utc":WHEN}}]}
def ledger():
 return {"schema":overlay.SCHEMA,"records":[{"preview_id":PREVIEW,
  "source_price_list_id":ID_PRICE,"browser_session_digest":SESSION,
  "observed_at_utc":WHEN,"price_total_rub":140000}]}

class Tests(unittest.TestCase):
 def test_true_selected_tour_updates_total_when_price_changes(self):
  b=base()
  p=overlay.apply(b,private(),proof(),ledger(),now=NOW)
  row=p["previews"][0]
  self.assertEqual(row["price_reference_rub"],140000)
  self.assertEqual(row["price_source"],"BG_EXACT_SELECTED_GREEN_BROWSER")
  self.assertEqual(row["price_observed_at_utc"],WHEN)
  self.assertEqual(p["indicative_two_adult_rub_count"],1)
  self.assertEqual(b["previews"][0]["price_reference_rub"],99999)
  changed=ledger();changed["records"][0]["price_total_rub"]=165500
  self.assertEqual(overlay.apply(b,private(),proof(),changed,now=NOW)
                   ["previews"][0]["price_reference_rub"],165500)
 def test_no_trusted_price_hides_stale_operator_xml_reference(self):
  for incoming in (None,{"schema":overlay.SCHEMA,"records":[]},
                   {"schema":overlay.SCHEMA,"records":[{"preview_id":PREVIEW}]}):
   with self.subTest(incoming=incoming):
    x=overlay.apply(base(),private(),proof(),incoming,now=NOW)
    self.assertIsNone(x["previews"][0]["price_reference_rub"])
    self.assertEqual(x["previews"][0]["price_reference_party"],"UNVERIFIED")
    self.assertEqual(x["indicative_two_adult_rub_count"],0)
 def test_wrong_price_list_or_session_timestamp_is_rejected(self):
  for change in (
    {"source_price_list_id":"121132934134"},
    {"browser_session_digest":"f"*64},
    {"observed_at_utc":(NOW-timedelta(minutes=16)).isoformat()},
    {"observed_at_utc":(NOW+timedelta(minutes=3)).isoformat()},
    {"price_total_rub":"140000"},
    {"price_total_rub":0},{"price_total_rub":10000001},
    {"preview_id":"p_"+"b"*24},
  ):
   with self.subTest(change=change):
    p=ledger();p["records"][0].update(change)
    self.assertIsNone(overlay.apply(base(),private(),proof(),p,now=NOW)
      ["previews"][0]["price_reference_rub"])
 def test_without_matching_official_visual_proof_cannot_price(self):
  for bad_public,bad_private in (({"entries":[]},private()),
    (proof(),{"records":[]}),
    (proof(),{"records":[{**private()["records"][0],
      "flight":{**private()["records"][0]["flight"],
       "flight_checked_at_utc":"2026-11-22T00:00:00Z"}}]})):
   self.assertIsNone(overlay.apply(base(),bad_private,bad_public,ledger(),
                            now=NOW)["previews"][0]["price_reference_rub"])
 def test_ledger_must_be_0600_owned_regular_file(self):
  with tempfile.TemporaryDirectory() as d:
   p=Path(d)/"ledger.json"
   p.write_text(json.dumps(ledger()))
   os.chmod(p,0o600)
   self.assertEqual(overlay.read_ledger(p)["schema"],overlay.SCHEMA)
   os.chmod(p,0o644)
   with self.assertRaises(ValueError):overlay.read_ledger(p)
   os.chmod(p,0o600)
   q=Path(d)/"link.json"
   q.symlink_to(p)
   with self.assertRaises(OSError):overlay.read_ledger(q)
 def test_no_ledger_does_not_block_search_only_countries(self):
  feed={"previews":[],"search_coverage":{
   "classification":"SOURCE_SCAN_ONLY_NOT_OFFERS","countries":[
    {"country":"Таиланд","source_rows_observed":700}]}}
  result=overlay.apply(feed,None,{"entries":[]},None,now=NOW)
  self.assertEqual(result["previews"],[])
  self.assertEqual(result["search_coverage"],feed["search_coverage"])
if __name__=="__main__":unittest.main()
