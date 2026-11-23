import unittest
from datetime import datetime, timedelta, timezone
from backend.order_engine import (
    Merchant, OrderEngine, NotConfigured, PriceChanged, NotAvailable,
    GatewayError, BadOrder, valid_offer
)

NOW=datetime(2026,11,20,10,0,tzinfo=timezone.utc)
def offer(**patch):
    value={
        "id":"tour_abcdefgh123","publish_approved":True,"quote_verified":True,
        "availability_verified":True,"flights_out_green":True,"flights_back_green":True,
        "price_scope_verified":True,"total_two_verified":True,
        "sale_policy":"BG_BEST_PRICE_TWO_FLIGHTS",
        "flight_pair_evidence_verified":True,
        "best_price_required":True,"best_price_verified":True,
        "total_rub":95000,"adults":2,"children":0,"currency":"RUB",
        "quote_verified_at":(NOW-timedelta(minutes=2)).isoformat(),
        "expires_at":(NOW+timedelta(minutes=7)).isoformat()
    }
    value.update(patch)
    return value
class Repo:
    def __init__(self, offer):self.offer=offer;self.orders={}
    def get_offer(self, id):return self.offer if self.offer["id"]==id else None
    def create_order(self, order):self.orders[order["id"]]=dict(order)
    def get_order(self, id):return self.orders.get(id)
    def update_order(self, id, patch):self.orders[id].update(patch)
class Supplier:
    def __init__(self):self.hold_calls=0;self.release_calls=0;self.confirm_calls=0;self.price=95000;self.available=True;self.fail_confirm=False
    def hold_and_requote(self, offer, key):
        self.hold_calls+=1
        return {"hold_id":"hold_abcdefgh","inventory_confirmed":self.available,
                "flights_out_green":True,"flights_back_green":True,
                "flight_pair_evidence_verified":True,
                "best_price_required":True,"best_price_verified":True,
                "currency":"RUB","total_rub":self.price}
    def confirm_booking(self, hold_id, order_id):
        self.confirm_calls+=1
        if self.fail_confirm:raise RuntimeError("SUPPLIER_UNAVAILABLE")
        return "booking_12345678"
    def release_hold(self, hold_id):self.release_calls+=1
class PSP:
    def __init__(self):self.calls=0;self.status="NOT_PAID";self.refund_calls=0;self.url="https://payments.example.test/embed/abc123"
    def create_payment(self, order_id, amount_rub, key):
        self.calls+=1
        return {"payment_id":"payment_12345678","payment_iframe_url":self.url}
    def get_authoritative_status(self,payment_id):return self.status
    def refund(self,payment_id,key):self.refund_calls+=1
class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.repo=Repo(offer());self.supplier=Supplier();self.psp=PSP()
        self.merchant=Merchant("JAMAICA Test Legal Seller","TEST_REG_12345","terms_2026_v1","https://payments.example.test",True)
        self.engine=OrderEngine(self.merchant,self.repo,self.supplier,self.psp,clock=lambda:NOW)
    def prepare(self):
        return self.engine.prepare(offer_id="tour_abcdefgh123",expected_total_rub=95000,terms_version="terms_2026_v1",terms_accepted=True)
    def test_live_payment_requires_merchant_terms(self):
        self.engine.merchant=Merchant("","","","",False)
        with self.assertRaises(NotConfigured):self.prepare()
        self.assertEqual(self.supplier.hold_calls,0)
        self.assertEqual(self.psp.calls,0)
    def test_offer_must_be_verified_and_fresh(self):
        self.repo.offer=offer(quote_verified=False)
        with self.assertRaises(NotAvailable):self.prepare()
        self.repo.offer=offer(expires_at=(NOW-timedelta(minutes=1)).isoformat())
        with self.assertRaises(NotAvailable):self.prepare()
        self.assertEqual(self.psp.calls,0)
    def test_price_change_stops_payment_releases_hold(self):
        self.supplier.price=98000
        with self.assertRaises(PriceChanged):self.prepare()
        self.assertEqual(self.psp.calls,0)
        self.assertEqual(self.supplier.release_calls,1)
    def test_unconfirmed_inventory_stops_payment(self):
        self.supplier.available=False
        with self.assertRaises(NotAvailable):self.prepare()
        self.assertEqual(self.psp.calls,0)
    def test_bg_missing_best_price_or_one_flight_blocks_legacy_payment(self):
        for change in (
            {"best_price_required":False},
            {"best_price_verified":False},
            {"flight_pair_evidence_verified":False},
            {"flights_back_green":False},
        ):
            class ChangedSupplier(Supplier):
                def hold_and_requote(inner,offer,key):
                    return {**super().hold_and_requote(offer,key),**change}
            with self.subTest(change=change):
                self.supplier=ChangedSupplier()
                self.engine.supplier=self.supplier
                with self.assertRaises(NotAvailable):
                    self.prepare()
                self.assertEqual(self.psp.calls,0)

    def test_exact_price_and_verified_flights_lead_to_payment_intent(self):
        p=self.prepare()
        self.assertEqual(p["status"],"PAYMENT_READY")
        self.assertEqual(p["total_rub"],95000)
        self.assertTrue(p["payment_iframe_url"].startswith("https://payments.example.test/"))
        self.assertEqual(self.engine.status(order_id=p["order_id"],status_token=p["status_token"])["status"],"PAYMENT_PENDING")
        with self.assertRaises(BadOrder):self.engine.status(order_id=p["order_id"],status_token="wrong")
    def test_wrong_psp_origin_rejected(self):
        self.psp.url="https://another-gateway.example.com/widget"
        with self.assertRaises(GatewayError):self.prepare()
    def test_browser_return_does_not_claim_success(self):
        p=self.prepare()
        self.engine.reconcile_payment(order_id=p["order_id"])
        self.assertEqual(self.engine.status(order_id=p["order_id"],status_token=p["status_token"])["status"],"PAYMENT_PENDING")
        self.assertEqual(self.supplier.confirm_calls,0)
    def test_paid_and_supplier_confirmed_only_success(self):
        p=self.prepare()
        self.psp.status="PAID"
        self.engine.reconcile_payment(order_id=p["order_id"])
        self.engine.reconcile_payment(order_id=p["order_id"])
        self.assertEqual(self.supplier.confirm_calls,1)
        self.assertEqual(self.engine.status(order_id=p["order_id"],status_token=p["status_token"])["status"],"PAID_BOOKED")
    def test_paid_but_booking_failed_initiates_refund(self):
        p=self.prepare();self.psp.status="PAID";self.supplier.fail_confirm=True
        with self.assertRaises(RuntimeError):self.engine.reconcile_payment(order_id=p["order_id"])
        self.assertEqual(self.psp.refund_calls,1)
        self.assertEqual(self.repo.orders[p["order_id"]]["status"],"REFUND_REQUIRED")
    def test_bad_terms_and_expected_price_rejected(self):
        with self.assertRaises(BadOrder):self.engine.prepare(offer_id="tour_abcdefgh123",expected_total_rub=95000,terms_version="terms_2026_v1",terms_accepted=False)
        with self.assertRaises(PriceChanged):self.engine.prepare(offer_id="tour_abcdefgh123",expected_total_rub=95001,terms_version="terms_2026_v1",terms_accepted=True)
        self.assertEqual(self.psp.calls,0)
    def test_marker_if_required(self):
        self.repo.offer=offer(best_price_verified=False)
        self.assertFalse(valid_offer(self.repo.offer,NOW))
        with self.assertRaises(NotAvailable):self.prepare()

if __name__=="__main__":unittest.main()
