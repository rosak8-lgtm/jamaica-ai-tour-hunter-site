"""Offline fixture tests only: no real supplier data or publication."""
import json
import tempfile
import unittest
from pathlib import Path
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode
from scripts import bg_scoped_evidence as s
from backend.test_bg_route_first_visual_gate import bundle,sample

class Tests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.origin="100510999999";self.country="100410000051"
        self.reg={"schema":"jamaica.origin-registry.v1","classification":"SEARCH_SCOPE_ONLY_NOT_OFFERS",
                  "source":"BG_FLTX","observed_at_utc":self.now.isoformat(),
                  "cities":{self.origin:"Тестовый город"},"countries":{self.country:"Таиланд"},
                  "pairs":[{"origin_id":self.origin,"country_id":self.country,"origin":"Тестовый город",
                            "country":"Таиланд","transport_indicator":2}]}
        self.scope=s.validated_registry_scope(self.reg,self.origin,self.country,self.now)
        self.preview={**sample(),"origin":self.scope.origin}
        p=self.preview
        p["id"]=self.scope.preview_id(p["hotel_id"],p["depart_date"],p["nights"],p["room"])
        self.r,self.f=bundle(p,now=self.now)
        self.r.update(origin_city_id=self.origin,page_url="https://www.bgoperator.ru/price.shtml?"+urlencode(
            {"flt":self.country,"flt2":self.origin,"action":"price","id_price":self.r["source_price_list_id"],"data":"12.12.2026"}))
        self.f["origin_city_id"]=self.origin
        self.price={"preview_id":p["id"],"source_price_list_id":self.r["source_price_list_id"],
                    "browser_session_digest":self.r["browser_session_digest"],
                    "observed_at_utc":self.f["flight_checked_at_utc"],"price_total_rub":100000}
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name)/"private-bg-scoped-staging";self.root.mkdir(mode=0o700)
        self.path=self.root/(self.origin+"-"+self.country+".json")

    def save(self,pairs=None,now=None):
        return s.save_staged_batch(self.root,self.reg,self.origin,self.country,
                                   pairs if pairs is not None else [(self.r,self.f,self.preview,self.price)],
                                   now=now or self.now)
    def test_exact_scoped_batch_and_price(self):
        self.assertEqual(self.save(),[self.preview["id"]])
        self.assertEqual(self.path.stat().st_mode&0o777,0o600)
        d=json.loads(self.path.read_text())
        self.assertEqual(d["classification"],"PRIVATE_ONLY_NOT_PUBLIC_OFFERS")
        self.assertEqual(d["records"][0]["price"]["price_total_rub"],100000)
        self.assertEqual(self.save(),[self.preview["id"]])
        self.assertEqual(len(json.loads(self.path.read_text())["records"]),1)
    def test_wrong_scope_or_price_rejected(self):
        for r,f,p,price in [
            ({**self.r,"origin_city_id":"100510397223"},self.f,self.preview,self.price),
            (self.r,{**self.f,"back_green":False},self.preview,self.price),
            (self.r,self.f,{**self.preview,"id":sample()["id"]},self.price),
            (self.r,self.f,self.preview,{**self.price,"browser_session_digest":"b"*64}),
            (self.r,self.f,self.preview,{**self.price,"observed_at_utc":self.now.isoformat()}),
            (self.r,self.f,self.preview,{**self.price,"price_total_rub":True}),
            (self.r,self.f,self.preview,{**self.price,"extra":"secret"})]:
            self.assertEqual(self.save([(r,f,p,price)]),[])
        self.assertFalse(self.path.exists())
    def test_expired_evidence_and_registry(self):
        self.assertEqual(self.save(now=self.now+timedelta(minutes=16)),[])
        with self.assertRaises(ValueError):
            self.save(now=self.now+timedelta(days=2))
    def test_no_unapproved_origin(self):
        with self.assertRaises(ValueError):
            s.validated_registry_scope(self.reg,"100510397223",self.country,self.now)
    def test_unsafe_or_corrupt_ledger(self):
        self.save()
        self.path.write_text("corrupt")
        with self.assertRaises(ValueError):self.save()
        self.assertEqual(self.path.read_text(),"corrupt")
        self.root.chmod(0o755)
        with self.assertRaises(ValueError):self.save()
    def test_no_legacy_writes(self):
        legacy=self.root.parent/"private-bg-route-first-receipts.json";legacy.write_text("original")
        self.save()
        self.assertEqual(legacy.read_text(),"original")

if __name__=="__main__":unittest.main()
