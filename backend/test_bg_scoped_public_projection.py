"""Synthetic regression tests; no live supplier interaction."""
import copy
import unittest
from datetime import datetime,timedelta,timezone
from urllib.parse import urlencode
from scripts.bg_scoped_public_projection import project
from scripts.bg_scoped_evidence import SCHEMA,validated_registry_scope
from backend.test_bg_route_first_visual_gate import sample,bundle

class Tests(unittest.TestCase):
    def setUp(self):
        self.now=datetime(2026,11,26,15,15,tzinfo=timezone.utc)
        oid="100510397251";cid="100410000051"
        self.reg={"schema":"jamaica.origin-registry.v1","classification":"SEARCH_SCOPE_ONLY_NOT_OFFERS",
                  "source":"BG_FLTX","observed_at_utc":self.now.isoformat(),
                  "cities":{oid:"Красноярск"},"countries":{cid:"Таиланд"},
                  "pairs":[{"origin_id":oid,"country_id":cid,"origin":"Красноярск","country":"Таиланд","transport_indicator":3}]}
        scope=validated_registry_scope(self.reg,oid,cid,self.now)
        p={**sample(),"origin":scope.origin}
        p["id"]=scope.preview_id(p["hotel_id"],p["depart_date"],p["nights"],p["room"])
        r,f=bundle(p,self.now)
        r.update(origin_city_id=oid,page_url="https://www.bgoperator.ru/price.shtml?"+urlencode(
            {"flt":cid,"flt2":oid,"action":"price","id_price":r["source_price_list_id"],"data":"12.12.2026"}))
        f["origin_city_id"]=oid
        price={"preview_id":p["id"],"source_price_list_id":r["source_price_list_id"],"browser_session_digest":r["browser_session_digest"],
            "observed_at_utc":f["flight_checked_at_utc"],"price_total_rub":100000}
        self.data={"schema":SCHEMA,"classification":"PRIVATE_ONLY_NOT_PUBLIC_OFFERS","origin_id":oid,"country_id":cid,
                   "records":[{"preview":p,"route":r,"flight":f,"price":price}]}
        self.directory={"hotels":[{"id":p["hotel_id"],"name":"Test Hotel","country":"Таиланд","resort":"Test Resort"}]}
    def run_projection(self,now=None):
        return project(self.data,self.reg,self.directory,now=now or self.now)
    def test_exact_projection_and_no_private_fields(self):
        rows,proofs=self.run_projection()
        self.assertEqual(len(rows),1);self.assertEqual(len(proofs),1)
        row=rows[0];proof=proofs[0]
        self.assertEqual(row["origin"],"Красноярск")
        self.assertEqual(row["price_reference_rub"],100000)
        self.assertEqual(row["price_observed_at_utc"],proof["observed_at_utc"])
        self.assertEqual(row["id"],proof["preview_id"])
        self.assertTrue(proof["route_best_price_seen"] and proof["both_green_planes_seen"])
        for flag in ("bookable","quote_verified","availability_verified","flight_verified"):
            self.assertIs(row[flag],False)
        for field in ("source_price_list_id","browser_session_digest","page_url","origin_city_id"):
            self.assertNotIn(field,row);self.assertNotIn(field,proof)
    def test_stale(self):
        self.assertEqual(self.run_projection(self.now+timedelta(minutes=16)),([],[]))
        with self.assertRaises(ValueError):self.run_projection(self.now+timedelta(days=2))
    def test_cross_scope_price_and_flight(self):
        for key,field,value in (("route","origin_city_id","100510397223"),("flight","back_green",False),
             ("price","browser_session_digest","b"*64),("preview","id",sample()["id"])):
            original=copy.deepcopy(self.data)
            self.data["records"][0][key][field]=value
            self.assertEqual(self.run_projection(),([],[]))
            self.data=original
    def test_wrong_hotel_country(self):
        self.directory["hotels"][0]["country"]="Китай"
        self.assertEqual(self.run_projection(),([],[]))
    def test_duplicate_rejected(self):
        self.data["records"].append(copy.deepcopy(self.data["records"][0]))
        with self.assertRaises(ValueError):self.run_projection()
    def test_empty_and_immutable(self):
        before=copy.deepcopy(self.data)
        self.run_projection()
        self.assertEqual(self.data,before)
        self.data["records"]=[]
        self.assertEqual(self.run_projection(),([],[]))
    def test_wrong_registry(self):
        self.reg["pairs"]=[]
        with self.assertRaises(ValueError):self.run_projection()
if __name__=="__main__":unittest.main()
