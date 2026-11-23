import unittest
from datetime import datetime,timedelta,timezone
from backend.preview_quote_engine import PreviewQuoteEngine, NotAvailable, BadOrder
from backend.order_engine import valid_offer
from backend.test_bg_route_first_visual_gate import bundle

def now():return datetime.now(timezone.utc)
def preview():
    return {"id":"p_"+"a"*24,"hotel_id":"102610001486","hotel":"Demo hotel (CI)",
            "country":"Индонезия","origin":"Иркутск","room":"DBL HB",
            "depart_date":(now()+timedelta(days=7)).date().isoformat(),
            "nights":7,"bookable":False,"availability_verified":False,
            "quote_verified":False}
def supplier_quote(p,**patch):
    result={"source_preview_id":p["id"],"hotel_id":p["hotel_id"],
            "depart_date":p["depart_date"],"room":p["room"],"nights":p["nights"],
            "country":p["country"],"origin":p["origin"],
            "currency":"RUB","total_rub":100000,
            "flight_out_available":True,"flight_back_available":True,
            "flight_pair_evidence_verified":True,
            "best_price_required":True,"best_price_verified":True,
            "hotel_stop":False,"hotel_status":"IN_STOCK",
            "two_adults_price_verified":True,"supplier_quote_verified":True,
            "expires_at":(now()+timedelta(minutes=12)).isoformat()}
    route,flight=bundle(p)
    result["route_visual_evidence"]=route
    result["flight_visual_evidence"]=flight
    result.update(patch)
    return result
class Repo:
    def __init__(self):self.p=preview();self.private={}
    def get_preview(self,key):
        return self.p if key==self.p["id"] else None
    def save_verified_offer(self,offer):self.private[offer["id"]]=offer
class Supplier:
    def __init__(self,repo):self.repo=repo;self.calls=[];self.patches={}
    def check_preview(self,preview,adults,children):
        self.calls.append((preview["id"],adults,children))
        return supplier_quote(preview,**self.patches)
class Tests(unittest.TestCase):
    def setUp(self):
        self.repo=Repo();self.supplier=Supplier(self.repo)
        self.engine=PreviewQuoteEngine(self.repo,self.supplier)
    def test_exact_preview_to_private_authoritative_offer(self):
        result=self.engine.get_authoritative_quote(self.repo.p["id"],buyer_id="customer-12345678",adults=2,children=0)
        self.assertEqual(result["status"],"QUOTE_READY")
        self.assertFalse(result["booked"])
        self.assertTrue(result["contract_required"])
        self.assertEqual(result["total_rub"],100000)
        offer=self.repo.private[result["offer_id"]]
        self.assertTrue(valid_offer(offer,now()))
        self.assertEqual(offer["sale_policy"],"BG_BEST_PRICE_TWO_FLIGHTS")
        self.assertTrue(offer["flight_pair_evidence_verified"])
        self.assertTrue(offer["best_price_required"])
        self.assertTrue(offer["best_price_verified"])
        self.assertEqual(len(self.supplier.calls),1)
        self.assertEqual(offer["buyer_id"],"customer-12345678")
    def test_incorrect_hotel_never_generates_private_offer(self):
        self.supplier.patches={"hotel_id":"another-hotel"}
        with self.assertRaises(NotAvailable):
            self.engine.get_authoritative_quote(self.repo.p["id"],buyer_id="customer-12345678",adults=2,children=0)
        self.assertEqual(self.repo.private,{})
    def test_no_seats_or_stop_prevents_contract(self):
        for patches in ({"flight_back_available":False},{"hotel_stop":True},
                        {"total_rub":0},{"supplier_quote_verified":False}):
            self.supplier.patches=patches
            with self.assertRaises(NotAvailable):
                self.engine.get_authoritative_quote(self.repo.p["id"],buyer_id="customer-12345678",adults=2,children=0)
        self.assertEqual(self.repo.private,{})
    def test_bg_requires_both_actual_green_flight_checks_and_best_price(self):
        for patches in (
            {"flight_out_available":False},
            {"flight_back_available":False},
            {"flight_pair_evidence_verified":False},
            {"flight_pair_evidence_verified":None},
            {"best_price_required":False,"best_price_verified":True},
            {"best_price_required":None,"best_price_verified":True},
            {"best_price_required":True,"best_price_verified":False},
            {"best_price_required":True,"best_price_verified":None},
        ):
            with self.subTest(patches=patches):
                self.supplier.patches=patches
                with self.assertRaises(NotAvailable):
                    self.engine.get_authoritative_quote(self.repo.p["id"],
                        buyer_id="customer-12345678",adults=2,children=0)
                self.assertEqual(self.repo.private,{})

    def test_exact_route_first_browser_capture_is_mandatory_for_bg(self):
        p=self.repo.p
        good=supplier_quote(p)
        for changes in (
            {"route_visual_evidence":None},
            {"flight_visual_evidence":None},
            {"route_visual_evidence":{
                **good["route_visual_evidence"],"badge_scope":"UNRELATED_HEADING"}},
            {"route_visual_evidence":{
                **good["route_visual_evidence"],"route_clicked":False}},
            {"flight_visual_evidence":{
                **good["flight_visual_evidence"],"source_price_list_id":"121132934134"}},
            {"flight_visual_evidence":{
                **good["flight_visual_evidence"],"out_green":False}},
            {"flight_visual_evidence":{
                **good["flight_visual_evidence"],"back_green":False}},
        ):
            with self.subTest(changes=list(changes.keys())):
                self.supplier.patches=changes
                with self.assertRaises(NotAvailable):
                    self.engine.get_authoritative_quote(p["id"],
                        buyer_id="customer-12345678",adults=2,children=0)
                self.assertEqual(self.repo.private,{})

    def test_on_request_requires_consent(self):
        self.supplier.patches={"hotel_status":"ON_REQUEST"}
        with self.assertRaises(NotAvailable):
            self.engine.get_authoritative_quote(self.repo.p["id"],buyer_id="customer-12345678",adults=2,children=0)
        result=self.engine.get_authoritative_quote(self.repo.p["id"],buyer_id="customer-12345678",adults=2,children=0,
                                                    on_request_accepted=True)
        self.assertEqual(result["hotel_status"],"ON_REQUEST")
    def test_other_party_needs_real_quote_not_divided_by_two(self):
        with self.assertRaises(NotAvailable):
            self.engine.get_authoritative_quote(self.repo.p["id"],buyer_id="customer-12345678",adults=1,children=0)
        self.assertEqual(self.supplier.calls,[])
    def test_original_source_stays_unbookable(self):
        result=self.engine.get_authoritative_quote(self.repo.p["id"],buyer_id="customer-12345678",adults=2,children=0)
        self.assertFalse(self.repo.p["bookable"])
        self.assertNotIn("payment_id",self.repo.private[result["offer_id"]])
    def test_authenticated_buyer_must_exist(self):
        with self.assertRaises(BadOrder):
            self.engine.get_authoritative_quote(self.repo.p["id"],
              buyer_id="",adults=2,children=0)
        self.assertEqual(self.supplier.calls,[])
        self.assertEqual(self.repo.private,{})
    def test_expired_departure_blocked(self):
        self.repo.p["depart_date"]=(now()-timedelta(days=2)).date().isoformat()
        with self.assertRaises(NotAvailable):
            self.engine.get_authoritative_quote(self.repo.p["id"],buyer_id="customer-12345678",adults=2,children=0)
        self.assertEqual(self.supplier.calls,[])
    def test_reject_unsupported_identifier(self):
        with self.assertRaises(BadOrder):
            self.engine.get_authoritative_quote("wrong",buyer_id="customer-12345678",adults=2,children=0)
if __name__=="__main__":unittest.main()
