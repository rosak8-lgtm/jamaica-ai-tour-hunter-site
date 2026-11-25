import unittest
from datetime import datetime,timedelta,timezone
from backend.pegas_application_evidence import validate_application_evidence

class Tests(unittest.TestCase):
    def setUp(self):
        self.now=datetime.now(timezone.utc)
        shared={"browser_session_digest":"a"*64,"party_digest":"b"*64,"selected_offer_id":"test-offer","origin_id":"test-origin","country_id":"test-country","hotel_id":"test-hotel","room_id":"test-room","departure_date":(self.now+timedelta(days=7)).date().isoformat(),"nights":7}
        self.s={**shared,"source":"PEGAS_OFFICIAL_BROWSER_PACKAGE_SEARCH","hotel_filter_verified":True,"flight_filter_verified":True,"cheapest_eligible_price_clicked":True,"clicked_at_utc":(self.now-timedelta(seconds=30)).isoformat()}
        self.a={**shared,"source":"PEGAS_OFFICIAL_BROWSER_OPEN_APPLICATION","hotel_available":True,"flights_available":True,"mandatory_fees_included":True,"final_price_observed":True,"currency":"RUB","total_rub":120000,"submitted":False,"booked":False,"observed_at_utc":self.now.isoformat()}
    def test_exact_application_no_bg_marker_required(self):
        self.assertTrue(validate_application_evidence(self.s,self.a,now=self.now))
    def test_filters_and_cheapest_click(self):
        for key in ("hotel_filter_verified","flight_filter_verified","cheapest_eligible_price_clicked"):
            self.assertFalse(validate_application_evidence({**self.s,key:False},self.a,now=self.now))
    def test_cross_scope(self):
        for key in ("hotel_id","origin_id","room_id","selected_offer_id","party_digest","browser_session_digest","departure_date","nights"):
            self.assertFalse(validate_application_evidence(self.s,{**self.a,key:"other"},now=self.now))
    def test_no_listing_or_incomplete_fees(self):
        for patch in ({"source":"PEGAS_OFFICIAL_BROWSER_PACKAGE_SEARCH"},{"mandatory_fees_included":False},{"final_price_observed":False},{"hotel_available":False},{"flights_available":False},{"total_rub":True},{"submitted":True},{"booked":True}):
            self.assertFalse(validate_application_evidence(self.s,{**self.a,**patch},now=self.now))
    def test_stale_and_reordered(self):
        self.assertFalse(validate_application_evidence(self.s,self.a,now=self.now+timedelta(minutes=16)))
        self.assertFalse(validate_application_evidence(self.s,{**self.a,"observed_at_utc":(self.now-timedelta(seconds=31)).isoformat()},now=self.now))

if __name__=="__main__":unittest.main()
