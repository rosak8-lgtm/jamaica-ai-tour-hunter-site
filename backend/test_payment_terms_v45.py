import unittest
from datetime import datetime,timedelta,timezone
from backend.payment_terms_v45 import verified_terms,plan,reconcile

class Tests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        self.q={"offer_id":"o1","quote_id":"q1","supplier_quote_verified":True,
                "payment_terms_verified":True,"total_rub":100000,
                "expires_at":(self.now+timedelta(minutes=10)).isoformat(),
                "payment_terms":{"currency":"RUB","total_kopecks":10000000,"minimum_kopecks":3000000,
                 "allows_partial":True,"allows_below_minimum":True,
                 "full_payment_due_utc":(self.now+timedelta(days=7)).isoformat(),
                 "balance_rule":"FIXED_RUB","tour_currency":"RUB"}}
    def terms(self):return verified_terms(self.q,"o1",self.now)
    def receipt(self,pid,principal,**extra):
        return {"order_id":"ord1","payment_id":pid,"principal_kopecks":principal,
                "processor_fee_kopecks":10000,"currency":"RUB","status":"PAID","verified_by_psp":True,**extra}
    def test_full_deposit_custom(self):
        t=self.terms()
        self.assertEqual(plan(t,"FULL",now=self.now)["amount_kopecks"],10000000)
        self.assertEqual(plan(t,"DEPOSIT",now=self.now)["amount_kopecks"],3000000)
        self.assertEqual(plan(t,"CUSTOM",now=self.now,custom=1000000)["remaining_to_minimum_after_payment"],2000000)
    def test_full_only_and_minimum_policy(self):
        self.q["payment_terms"].update(allows_partial=False,allows_below_minimum=False,minimum_kopecks=10000000)
        with self.assertRaises(ValueError):plan(self.terms(),"CUSTOM",now=self.now,custom=100)
        self.q["payment_terms"].update(allows_partial=True,minimum_kopecks=3000000)
        with self.assertRaises(ValueError):plan(self.terms(),"CUSTOM",now=self.now,custom=100)
    def test_missing_or_mismatched_terms(self):
        with self.assertRaises(ValueError):verified_terms(self.q,"different",self.now)
        self.q["payment_terms_verified"]=False
        with self.assertRaises(ValueError):self.terms()
    def test_expired_and_invalid_amount(self):
        with self.assertRaises(ValueError):plan(self.terms(),"FULL",now=self.now+timedelta(minutes=11))
        for a in (0,-1,True,10000001,1.5):
            with self.assertRaises(ValueError):plan(self.terms(),"CUSTOM",now=self.now,custom=a)
    def test_duplicate_receipts_fee_and_threshold(self):
        a=self.receipt("p1",1000000)
        r=reconcile(self.terms(),"ord1",[a,a])
        self.assertEqual(r["paid_kopecks"],1000000)
        self.assertEqual(r["remaining_to_minimum"],2000000)
        self.assertFalse(r["minimum_reached"])
        r=reconcile(self.terms(),"ord1",[a,self.receipt("p2",2000000)])
        self.assertTrue(r["minimum_reached"])
        self.assertFalse(r["booking_authorized"])
    def test_conflicts_refund_wrong_order(self):
        a=self.receipt("p1",3000000)
        with self.assertRaises(ValueError):reconcile(self.terms(),"ord1",[a,{**a,"principal_kopecks":1}])
        with self.assertRaises(ValueError):reconcile(self.terms(),"other",[a])
        with self.assertRaises(ValueError):reconcile(self.terms(),"ord1",[{**a,"verified_by_psp":False}])
        r=reconcile(self.terms(),"ord1",[a,self.receipt("p2",1,status="REFUNDED")])
        self.assertTrue(r["review_required"])
        self.assertFalse(r["minimum_reached"])
    def test_fx_requote_required(self):
        self.q["payment_terms"].update(balance_rule="SUPPLIER_RATE_ON_BALANCE_PAYMENT",tour_currency="USD")
        t=self.terms()
        with self.assertRaises(ValueError):plan(t,"FULL",now=self.now,paid=3000000)
        self.assertTrue(reconcile(t,"ord1",[self.receipt("p1",3000000)])["balance_requote_required"])

if __name__=="__main__":unittest.main()
