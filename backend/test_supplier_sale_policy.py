"""BG best-price and both-flight-sale gates: fail closed on missing evidence."""
import unittest
from backend.supplier_sale_policy import (
    BG_BEST_PRICE, PEGAS, POLICIES, check_supplier_evidence,
    valid_offer_evidence, valid_policy,
)

def trusted():
    return {
        "flight_out_available":True,"flight_back_available":True,
        "flight_pair_evidence_verified":True,
        "best_price_required":True,"best_price_verified":True,
    }
def offer():
    return {
        "flights_out_green":True,"flights_back_green":True,
        "flight_pair_evidence_verified":True,"sale_policy":BG_BEST_PRICE,
        "best_price_required":True,"best_price_verified":True,
    }

class Tests(unittest.TestCase):
    def test_bg_supplier_best_price_and_both_legs_required(self):
        self.assertTrue(check_supplier_evidence(trusted(),BG_BEST_PRICE))
        for key,value in [
            ("flight_out_available",False),
            ("flight_back_available",False),
            ("flight_pair_evidence_verified",False),
            ("best_price_required",False),
            ("best_price_verified",False),
            ("best_price_verified",None),
        ]:
            with self.subTest(flag=key):
                self.assertFalse(check_supplier_evidence(
                    {**trusted(),key:value},BG_BEST_PRICE))
        self.assertFalse(check_supplier_evidence(None,BG_BEST_PRICE))

    def test_bg_source_can_never_disable_best_price_requirement(self):
        self.assertFalse(check_supplier_evidence(
            {**trusted(),"best_price_required":False},BG_BEST_PRICE))
        self.assertFalse(valid_offer_evidence(
            {**offer(),"best_price_required":False}))
        self.assertFalse(valid_offer_evidence(
            {**offer(),"best_price_verified":False}))

    def test_both_green_must_be_independently_verified_for_stored_offer(self):
        self.assertTrue(valid_offer_evidence(offer()))
        for key in ("flights_out_green","flights_back_green",
                    "flight_pair_evidence_verified"):
            with self.subTest(key=key):
                self.assertFalse(valid_offer_evidence(
                    {**offer(),key:False}))

    def test_missing_policy_never_treated_as_pegas(self):
        for candidate in ("",None,"BG","PEGAS","BG_BEST_PRICE",
                          "FAKE","bg_best_price_two_flights",True):
            self.assertFalse(valid_policy(candidate))
            self.assertFalse(valid_offer_evidence(
                {**offer(),"sale_policy":candidate}))
        self.assertEqual(POLICIES,{BG_BEST_PRICE,PEGAS})

    def test_pegas_still_requires_both_green_but_not_bg_marker(self):
        independent={**trusted(),"best_price_required":False,
                     "best_price_verified":False}
        self.assertTrue(check_supplier_evidence(independent,PEGAS))
        self.assertTrue(valid_offer_evidence({
            **offer(),"sale_policy":PEGAS,
            "best_price_required":False,"best_price_verified":False}))
        self.assertFalse(check_supplier_evidence({
            **independent,"flight_back_available":None},PEGAS))
        self.assertFalse(check_supplier_evidence({
            **trusted(),"best_price_required":True},PEGAS))

    def test_missing_or_wrong_boolean_is_never_marked_verified(self):
        for value in ("true",1,0,None,[],{}):
            with self.subTest(value=value):
                self.assertFalse(check_supplier_evidence({
                    **trusted(),"best_price_verified":value},BG_BEST_PRICE))
                self.assertFalse(valid_offer_evidence({
                    **offer(),"flight_pair_evidence_verified":value}))

if __name__=="__main__":
    unittest.main()
