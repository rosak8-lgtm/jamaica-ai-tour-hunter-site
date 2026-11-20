import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
from flight_availability_evidence import economy_q_available,flight_pair_evidence

def make(q0="a0",q1="90"):
    return {"tourComposition":[
       {"type":"flight","n":0,"id":"103151365832;","q":q0},
       {"type":"accomodation","n":2,"q":"0"},
       {"type":"flight","n":1,"id":"103173777714;","q":q1}],
       "isstop":False}

class Tests(unittest.TestCase):
    def test_two_green_economy_flights(self):
        for out,ret in (("a0","90"),("11","r0"),("a4","a0")):
            result=flight_pair_evidence(make(out,ret))
            self.assertTrue(result["both_green"])
            self.assertEqual(result["status"],"BOTH_AVAILABLE_AT_SNAPSHOT")
    def test_zero_request_or_no_seats_is_not_green(self):
        for q in ("00","0a","c0","cc","0",""):
            self.assertFalse(economy_q_available(q))
            self.assertFalse(flight_pair_evidence(make(q,"a0"))["both_green"])
    def test_must_check_both_outbound_and_return(self):
        r=flight_pair_evidence(make("a0","00"))
        self.assertTrue(r["out_green"])
        self.assertFalse(r["back_green"])
        self.assertFalse(r["both_green"])
    def test_missing_or_duplicate_direction_must_fail_closed(self):
        x=make()
        del x["tourComposition"][2]
        self.assertEqual(flight_pair_evidence(x)["status"],"UNVERIFIED")
        y=make()
        y["tourComposition"].append(y["tourComposition"][0].copy())
        self.assertEqual(flight_pair_evidence(y)["status"],"UNVERIFIED")
    def test_stop_sale_overrides_green_both(self):
        x=make()
        x["isstop"]=["avia_to"]
        r=flight_pair_evidence(x)
        self.assertFalse(r["both_green"])
        self.assertEqual(r["status"],"STOP_SALE")
    def test_html_flight_icons_not_implicitly_evidence(self):
        x={"flights":'<span class="green-plane">green</span>',
           "tourComposition":[]}
        self.assertFalse(flight_pair_evidence(x)["both_green"])
    def test_malformed_business_class_indicator_not_accepted(self):
        self.assertFalse(economy_q_available("a?"))
    def test_regular_flight_q_not_booking_confirmation(self):
        r=flight_pair_evidence(make("r0","r0"))
        self.assertTrue(r["both_green"])
        self.assertNotIn("bookable",r)
if __name__=="__main__":unittest.main()
