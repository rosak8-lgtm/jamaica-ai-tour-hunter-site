import unittest
from datetime import datetime,timedelta,timezone
from backend.contract_first_order_engine import (
    ContractFirstEngine, quote_is_valid, contract_digest, BadOrder,
    NotAvailable, PriceChanged, Merchant
)

def offer():
    now=datetime.now(timezone.utc)
    return {"id":"tour_abcdefgh123","publish_approved":True,"quote_verified":True,
      "availability_verified":True,"flights_out_green":True,"flights_back_green":True,
      "price_scope_verified":True,"total_two_verified":True,
      "best_price_required":False,"total_rub":95000,
      "adults":2,"children":0,
      "origin":"Иркутск","destination":"Индонезия",
      "hotel":"CI Test Hotel","hotel_id":"102610001486","room":"DBL HB",
      "depart_date":(now+timedelta(days=7)).date().isoformat(),"nights":7,
      "quote_verified_at":(now-timedelta(minutes=1)).isoformat(),
      "expires_at":(now+timedelta(minutes=30)).isoformat()}
def quote(price=95000,status="IN_STOCK",**patch):
    o=offer()
    v={"offer_id":o["id"],"origin":o["origin"],"destination":o["destination"],
       "hotel_id":o["hotel_id"],"room":o["room"],"depart_date":o["depart_date"],
       "nights":o["nights"],"adults":o["adults"],"children":o["children"],
       "currency":"RUB","total_rub":price,"flight_out_available":True,
       "flight_back_available":True,"hotel_stop":False,"hotel_status":status,
       "two_adults_price_verified":True,"supplier_quote_verified":True,
       "expires_at":(datetime.now(timezone.utc)+timedelta(minutes=10)).isoformat()}
    v.update(patch)
    return v
class Repo:
    def __init__(self):
        self.offer=offer();self.orders={};self.transitions=[]
    def get_offer(self,key):
        return self.offer if key==self.offer["id"] else None
    def create_order(self,value):
        if value["id"] in self.orders:raise ValueError("duplicate")
        self.orders[value["id"]]=dict(value)
    def get_order(self,key):
        return self.orders.get(key)
    def transition(self,key,expected,new,updates):
        order=self.orders[key]
        if order["status"]!=expected:return False
        order.update(updates)
        order["status"]=new
        self.transitions.append((expected,new))
        return True
class Supplier:
    def __init__(self):
        self.checks=[];self.checks_by_stage={};self.bookings=[]
        self.booking_result={"status":"CONFIRMED","supplier_booking_id":"operator-123"}
        self.book_error=None
    def check(self,offer,stage):
        self.checks.append(stage)
        return self.checks_by_stage.get(stage,quote())
    def create_booking(self,order,key):
        self.bookings.append({"key":key,"order_status":order["status"]})
        if self.book_error:raise self.book_error
        return self.booking_result
    def lookup_booking(self,key):return None
class Signer:
    def __init__(self):self.requests=[];self.accept=False;self.invalid_digest=False
    def create_contract(self,*,order_id,content,digest_sha256):
        self.requests.append((order_id,content,digest_sha256))
        return {"contract_id":"contract-123","signing_url":"https://sign.example.test/contract-123"}
    def verified_signature(self,*,contract_id,digest_sha256):
        return {"verified":self.accept,
                "digest_sha256":"wrong" if self.invalid_digest else digest_sha256,
                "receipt_id":"receipt-123",
                "signed_at":datetime.now(timezone.utc).isoformat()}
class Payment:
    def __init__(self):
        self.created=[];self.status="PENDING";self.refunds=[]
        self.url="https://payments.example.test/secure/pay-123"
    def create_payment(self,order_id,amount_rub,idempotency_key):
        self.created.append((order_id,amount_rub,idempotency_key))
        return {"payment_id":"psp-payment-123","payment_iframe_url":self.url}
    def get_authoritative_status(self,id):return self.status
    def refund(self,id,key):self.refunds.append((id,key))
class Outbox:
    def __init__(self):self.events={}
    def enqueue_once(self,key,event):self.events.setdefault(key,event)
class Tests(unittest.TestCase):
    def setUp(self):
        self.repo=Repo();self.supplier=Supplier();self.signer=Signer()
        self.psp=Payment();self.outbox=Outbox()
        merchant=Merchant("JAMAICA test seller legal","REG-TEST-0001",
                          "contract_v1","https://payments.example.test",True)
        self.engine=ContractFirstEngine(merchant,self.repo,self.supplier,
                                        self.signer,self.psp,self.outbox)
    def create(self,on_request=False):
        return self.engine.draft_contract(offer_id="tour_abcdefgh123",
                 expected_total_rub=95000,buyer_id="customer-12345678",
                 terms_version="contract_v1",terms_accepted=True,
                 on_request_accepted=on_request)
    def signed(self,on_request=False):
        result=self.create(on_request)
        self.signer.accept=True
        self.engine.verify_contract_signature(result["order_id"])
        return result["order_id"]
    def paid(self,on_request=False):
        id=self.signed(on_request)
        self.engine.initiate_payment(id)
        self.psp.status="PAID"
        return id
    def test_contract_requires_terms_acceptance(self):
        with self.assertRaises(BadOrder):
            self.engine.draft_contract(
                offer_id="tour_abcdefgh123",expected_total_rub=95000,
                buyer_id="customer-12345678",terms_version="contract_v1",
                terms_accepted=False)
        self.assertEqual(self.supplier.checks,[])
        self.assertEqual(self.psp.created,[])
    def test_only_first_readonly_quote_before_contract(self):
        p=self.create()
        self.assertEqual(p["status"],"AWAITING_SIGNATURE")
        self.assertEqual(self.supplier.checks,["BEFORE_CONTRACT"])
        self.assertEqual(len(self.signer.requests),1)
        self.assertEqual(self.psp.created,[])
        self.assertEqual(self.supplier.bookings,[])
        self.assertEqual(self.outbox.events,{})
    def test_untrusted_signature_does_not_unlock_payment(self):
        p=self.create()
        with self.assertRaises(NotAvailable):
            self.engine.verify_contract_signature(p["order_id"])
        with self.assertRaises(BadOrder):
            self.engine.initiate_payment(p["order_id"])
        self.signer.accept=True
        self.signer.invalid_digest=True
        with self.assertRaises(NotAvailable):
            self.engine.verify_contract_signature(p["order_id"])
        self.assertEqual(self.psp.created,[])
    def test_second_quote_only_after_signed_contract(self):
        id=self.signed()
        p=self.engine.initiate_payment(id)
        self.assertEqual(p["status"],"PAYMENT_READY")
        self.assertEqual(self.supplier.checks,["BEFORE_CONTRACT","AFTER_SIGNATURE_BEFORE_PAYMENT"])
        self.assertEqual(len(self.psp.created),1)
        self.assertEqual(self.supplier.bookings,[])
    def test_first_quote_for_another_hotel_never_creates_contract(self):
        self.supplier.checks_by_stage["BEFORE_CONTRACT"]=quote(hotel_id="DIFFERENT_HOTEL")
        with self.assertRaises(NotAvailable):
            self.create()
        self.assertEqual(self.repo.orders,{})
        self.assertEqual(self.psp.created,[])
    def test_second_quote_wrong_room_blocks_payment(self):
        id=self.signed()
        self.supplier.checks_by_stage["AFTER_SIGNATURE_BEFORE_PAYMENT"]=quote(room="SGL BB")
        with self.assertRaises(NotAvailable):
            self.engine.initiate_payment(id)
        self.assertEqual(self.psp.created,[])
    def test_third_quote_wrong_departure_or_adults_blocks_booking(self):
        for field,value in (("depart_date","2031-01-01"),("adults",1)):
            instance=Tests()
            instance.setUp()
            oid=instance.paid()
            instance.supplier.checks_by_stage["AFTER_PAYMENT_BEFORE_BOOKING"]=quote(**{field:value})
            self.assertEqual(instance.engine.reconcile_payment_and_book(oid),"REFUND_REQUIRED")
            self.assertEqual(instance.supplier.bookings,[])
            self.assertEqual(len(instance.psp.refunds),1)
    def test_price_changed_before_payment_blocks_psp(self):
        id=self.signed()
        self.supplier.checks_by_stage["AFTER_SIGNATURE_BEFORE_PAYMENT"]=quote(price=96000)
        with self.assertRaises(PriceChanged):
            self.engine.initiate_payment(id)
        self.assertEqual(self.psp.created,[])
    def test_unpaid_webhook_never_books(self):
        id=self.signed()
        self.engine.initiate_payment(id)
        result=self.engine.reconcile_payment_and_book(id)
        self.assertEqual(result,"PAYMENT_PENDING")
        self.assertEqual(self.supplier.checks,["BEFORE_CONTRACT","AFTER_SIGNATURE_BEFORE_PAYMENT"])
        self.assertFalse(self.supplier.bookings)
    def test_book_only_after_payment_and_third_quote(self):
        id=self.paid()
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"BOOKED")
        self.assertEqual(self.supplier.checks,[
          "BEFORE_CONTRACT","AFTER_SIGNATURE_BEFORE_PAYMENT","AFTER_PAYMENT_BEFORE_BOOKING"])
        self.assertEqual(len(self.supplier.bookings),1)
        self.assertEqual(self.supplier.bookings[0]["order_status"],"BOOKING_IN_PROGRESS")
        self.assertEqual(list(self.outbox.events.values())[0]["type"],"TOUR_BOOKED")
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"BOOKED")
        self.assertEqual(len(self.supplier.bookings),1)
    def test_after_payment_price_change_refund_no_booking(self):
        id=self.paid()
        self.supplier.checks_by_stage["AFTER_PAYMENT_BEFORE_BOOKING"]=quote(price=97000)
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"REFUND_REQUIRED")
        self.assertEqual(self.supplier.bookings,[])
        self.assertEqual(len(self.psp.refunds),1)
        self.assertIn("REFUND_REQUIRED",[e["type"] for e in self.outbox.events.values()])
    def test_after_payment_flight_unavailable_refund(self):
        id=self.paid()
        self.supplier.checks_by_stage["AFTER_PAYMENT_BEFORE_BOOKING"]=quote(flight_back_available=False)
        self.engine.reconcile_payment_and_book(id)
        self.assertEqual(self.supplier.bookings,[])
        self.assertEqual(len(self.psp.refunds),1)
    def test_hotel_stop_blocks_payment_or_booking(self):
        id=self.signed()
        self.supplier.checks_by_stage["AFTER_SIGNATURE_BEFORE_PAYMENT"]=quote(hotel_stop=True)
        with self.assertRaises(NotAvailable):self.engine.initiate_payment(id)
        self.assertEqual(self.psp.created,[])
        self.assertEqual(self.supplier.bookings,[])
    def test_on_request_requires_explicit_acceptance(self):
        self.supplier.checks_by_stage["BEFORE_CONTRACT"]=quote(status="ON_REQUEST")
        with self.assertRaises(NotAvailable):self.create(on_request=False)
        result=self.create(on_request=True)
        self.supplier.checks_by_stage["AFTER_SIGNATURE_BEFORE_PAYMENT"]=quote(status="ON_REQUEST")
        self.supplier.checks_by_stage["AFTER_PAYMENT_BEFORE_BOOKING"]=quote(status="ON_REQUEST")
        self.signer.accept=True
        id=result["order_id"]
        self.engine.verify_contract_signature(id)
        self.engine.initiate_payment(id)
        self.psp.status="PAID"
        self.supplier.booking_result={"status":"ON_REQUEST","supplier_booking_id":"operator-456"}
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"SUPPLIER_ON_REQUEST")
        self.assertEqual(list(self.outbox.events.values())[0]["type"],"TOUR_REQUESTED_WAITING_HOTEL")
    def test_supplier_rejection_initiates_refund(self):
        id=self.paid()
        self.supplier.book_error=NotAvailable("HOTEL_STOP")
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"REFUND_REQUIRED")
        self.assertEqual(len(self.psp.refunds),1)
    def test_ambiguous_supplier_timeout_requires_reconciliation_not_refund(self):
        id=self.paid()
        self.supplier.book_error=TimeoutError("unknown if supplier accepted request")
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"BOOKING_RECONCILIATION_REQUIRED")
        self.assertEqual(self.repo.orders[id]["status"],"BOOKING_RECONCILIATION_REQUIRED")
        self.assertEqual(self.psp.refunds,[])
        self.assertEqual(len(self.supplier.bookings),1)
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"BOOKING_RECONCILIATION_REQUIRED")
        self.assertEqual(len(self.supplier.bookings),1)
    def test_notification_failure_cannot_refund_successful_booking(self):
        class BrokenOutbox:
            def enqueue_once(self,key,event):
                raise RuntimeError("telegram temporarily unavailable")
        self.engine.outbox=BrokenOutbox()
        id=self.paid()
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"BOOKED")
        self.assertEqual(self.repo.orders[id]["status"],"BOOKED")
        self.assertEqual(self.psp.refunds,[])
    def test_signature_requires_provider_receipt_not_just_signed_flag(self):
        id=self.create()["order_id"]
        self.signer.accept=True
        original=self.signer.verified_signature
        def invalid(**kw):
            d=original(**kw)
            d["receipt_id"]=None
            return d
        self.signer.verified_signature=invalid
        with self.assertRaises(NotAvailable):
            self.engine.verify_contract_signature(id)
        self.assertEqual(self.repo.orders[id]["status"],"AWAITING_SIGNATURE")
    def test_prebooking_check_is_required_even_when_payment_paid(self):
        id=self.paid()
        self.supplier.checks_by_stage["AFTER_PAYMENT_BEFORE_BOOKING"]=quote(hotel_stop=True)
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"REFUND_REQUIRED")
        self.assertEqual(self.supplier.bookings,[])
    def test_ambiguous_booking_read_only_lookup_confirms_without_second_booking(self):
        id=self.paid()
        self.supplier.book_error=TimeoutError("unknown")
        self.engine.reconcile_payment_and_book(id)
        def found(key):
            self.assertEqual(key,id)
            return {"status":"CONFIRMED","supplier_booking_id":"operator-123"}
        self.supplier.lookup_booking=found
        self.assertEqual(self.engine.reconcile_supplier_status(id),"BOOKED")
        self.assertEqual(len(self.supplier.bookings),1)
        self.assertEqual(list(self.outbox.events.values())[0]["type"],"TOUR_BOOKED")
    def test_supplier_on_request_stays_pending_until_confirmed(self):
        id=self.signed(on_request=True)
        self.engine.initiate_payment(id)
        self.psp.status="PAID"
        self.supplier.booking_result={"status":"ON_REQUEST","supplier_booking_id":"operator-789"}
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"SUPPLIER_ON_REQUEST")
        self.supplier.lookup_booking=lambda key:{"status":"ON_REQUEST","supplier_booking_id":"operator-789"}
        self.assertEqual(self.engine.reconcile_supplier_status(id),"SUPPLIER_ON_REQUEST")
        self.supplier.lookup_booking=lambda key:{"status":"CONFIRMED","supplier_booking_id":"operator-789"}
        self.assertEqual(self.engine.reconcile_supplier_status(id),"BOOKED")
        self.assertEqual(len(self.supplier.bookings),1)
        self.assertEqual(len(self.outbox.events),2)
    def test_supplier_on_request_rejection_issues_refund(self):
        id=self.signed(on_request=True)
        self.engine.initiate_payment(id)
        self.psp.status="PAID"
        self.supplier.booking_result={"status":"ON_REQUEST","supplier_booking_id":"operator-789"}
        self.engine.reconcile_payment_and_book(id)
        self.supplier.lookup_booking=lambda key:{"status":"REJECTED","definitive":True}
        self.assertEqual(self.engine.reconcile_supplier_status(id),"REFUND_REQUIRED")
        self.assertEqual(len(self.psp.refunds),1)
    def test_supplier_timeout_lookup_does_not_refund_or_rebook(self):
        id=self.paid()
        self.supplier.book_error=TimeoutError("unknown")
        self.engine.reconcile_payment_and_book(id)
        self.supplier.lookup_booking=lambda key:(_ for _ in ()).throw(TimeoutError())
        self.assertEqual(self.engine.reconcile_supplier_status(id),"BOOKING_RECONCILIATION_REQUIRED")
        self.assertEqual(self.psp.refunds,[])
        self.assertEqual(len(self.supplier.bookings),1)
    def test_operator_submission_requires_later_confirmation(self):
        oid=self.paid()
        self.supplier.booking_result={"status":"SUBMITTED","supplier_booking_id":"application-321"}
        self.assertEqual(self.engine.reconcile_payment_and_book(oid),"SUPPLIER_SUBMITTED")
        self.assertEqual(len(self.supplier.bookings),1)
        self.assertEqual(self.engine.reconcile_payment_and_book(oid),"SUPPLIER_SUBMITTED")
        self.assertEqual(len(self.supplier.bookings),1)
        self.assertEqual(list(self.outbox.events.values())[0]["type"],"TOUR_SUBMITTED_WAITING_OPERATOR")
        self.supplier.lookup_booking=lambda key:{"status":"CONFIRMED","supplier_booking_id":"application-321"}
        self.assertEqual(self.engine.reconcile_supplier_status(oid),"BOOKED")
        self.assertEqual(len(self.outbox.events),2)
        self.assertEqual(len(self.supplier.bookings),1)
    def test_operator_submission_rejected_then_refund(self):
        oid=self.paid()
        self.supplier.booking_result={"status":"SUBMITTED","supplier_booking_id":"application-321"}
        self.engine.reconcile_payment_and_book(oid)
        self.supplier.lookup_booking=lambda key:{"status":"REJECTED","definitive":True}
        self.assertEqual(self.engine.reconcile_supplier_status(oid),"REFUND_REQUIRED")
        self.assertEqual(len(self.psp.refunds),1)
    def test_contract_digest_is_stable_and_tamper_evident(self):
        a={"buyer_id":"customer_1","total_rub":100}
        self.assertEqual(contract_digest(a),contract_digest(dict(reversed(list(a.items())))))
        self.assertNotEqual(contract_digest(a),contract_digest({**a,"total_rub":101}))
    def test_account_status_uses_secret_token(self):
        result=self.create()
        self.assertEqual(self.engine.status(result["order_id"],result["status_token"])["status"],
                         "AWAITING_SIGNATURE")
        with self.assertRaises(BadOrder):
            self.engine.status(result["order_id"],"wrong")
    def test_booking_prepayment_is_never_scheduled(self):
        id=self.signed()
        self.engine.initiate_payment(id)
        self.psp.status="FAILED"
        self.assertEqual(self.engine.reconcile_payment_and_book(id),"PAYMENT_FAILED")
        self.assertEqual(self.supplier.bookings,[])
    def test_reject_zero_price_or_unverified_hotel(self):
        self.assertFalse(quote_is_valid(quote(price=0),95000,allow_on_request=True))
        self.assertFalse(quote_is_valid(quote(hotel_status="BLOCKED"),95000,allow_on_request=True))
        self.assertFalse(quote_is_valid(quote(status="ON_REQUEST"),95000,allow_on_request=False))

if __name__=="__main__":
    unittest.main()
