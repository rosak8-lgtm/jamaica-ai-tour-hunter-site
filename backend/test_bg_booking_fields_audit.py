import json
import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import oracle_bg_booking_fields_audit as audit
import oracle_bg_preview_export as preview

DAY=(datetime.now(timezone.utc)+timedelta(days=7)).strftime("%d.%m.%Y")
HOTEL={"id":"102610001486","name":"CI Hotel","country":"Индонезия","resort":"Бали"}
ROW={"id_hotel":HOTEL["id"],"tour_date":DAY,"dt":DAY,"duration":"7",
     "o_duration":"7","room":"DBL HB","town":"Бали",
     "id_price":"121132934133","id_ns":"104623691678",
     "sr":"PRIVATE-FLIGHT-TOKEN",
     "prices":[{"amount":"1700","RUR":"115000","ag":"12+,12+"}]}
SELECTED=preview.safe_preview(ROW,"Индонезия",{HOTEL["id"]:HOTEL},"EUR")
PAYLOAD={"cur":"EUR","prx":"PRIVATE-PRX","entries":[ROW]}
LISTING={"id_price":"121132934133"}

class BookingAuditTests(unittest.TestCase):
    def test_all_quote_prerequisites_present_but_no_booking_claim(self):
        result=audit.assess_row(ROW,PAYLOAD,LISTING,SELECTED,{HOTEL["id"]:HOTEL})
        self.assertTrue(all(result.values()))
        self.assertEqual(set(result),set(audit.SAFE_FLAGS))
        self.assertNotIn("PRIVATE",str(result))
        self.assertNotIn("115000",str(result))
        self.assertNotIn("102610001486",str(result))
    def test_missing_prx_and_flights_cannot_claim_readiness(self):
        row={**ROW,"sr":""}
        payload={"cur":"EUR","entries":[row]}
        result=audit.assess_row(row,payload,LISTING,SELECTED,{HOTEL["id"]:HOTEL})
        self.assertFalse(result["operator_prx"])
        self.assertFalse(result["flight_selection_reference"])
        self.assertTrue(result["two_adult_price_option"])
    def test_wrong_room_cannot_match_preview(self):
        row={**ROW,"room":"SGL HB"}
        result=audit.assess_row(row,PAYLOAD,LISTING,SELECTED,{HOTEL["id"]:HOTEL})
        self.assertIsNone(result)
    def test_child_only_price_does_not_count(self):
        row={**ROW,"prices":[{"amount":"800","RUR":"81000","ag":"2-11,12+"}]}
        result=audit.assess_row(row,PAYLOAD,LISTING,SELECTED,{HOTEL["id"]:HOTEL})
        self.assertFalse(result["two_adult_price_option"])
    def test_booking_fields_not_exposed(self):
        row={**ROW,"id_ns":"invalid","id_price":"invalid"}
        result=audit.assess_row(row,PAYLOAD,{"id_price":"invalid"},SELECTED,{HOTEL["id"]:HOTEL})
        self.assertFalse(result["template_id"])
        self.assertFalse(result["roommeal_id"])

if __name__=="__main__":unittest.main()
