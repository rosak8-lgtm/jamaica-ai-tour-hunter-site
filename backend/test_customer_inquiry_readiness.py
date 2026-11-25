import json
import tempfile
import unittest
from datetime import datetime,timezone,timedelta
from pathlib import Path
from backend.customer_inquiry_readiness import report,config_status,https_url

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root=Path(self.tmp.name).resolve()
        self.now=datetime.now(timezone.utc)
        self.config={"schema":"jamaica.inquiry-config.v1","enabled":True,
          "privacy_approved":True,"controller_name":"TEST ONLY",
          "policy_version":"test-v1","privacy_url":"https://example.invalid/privacy",
          "endpoint":"https://example.invalid/v1/customer-inquiries"}
        self.env={"JAMAICA_INQUIRY_LEGAL_APPROVED":"yes",
          "JAMAICA_INQUIRY_HASH_SECRET":"testhash"*8,
          "JAMAICA_INQUIRY_PROXY_SECRET":"testproxy"*8}
    def write(self,name,obj):
        p=self.root/name
        p.write_text(json.dumps(obj),encoding="utf-8")
        p.chmod(0o600)
    def test_disabled_and_missing_config(self):
        r=report(self.root,now=self.now,env={})
        self.assertFalse(r["config_checks_pass"])
        self.assertIn("CLIENT_ENABLED",r["missing"])
        self.assertFalse(r["public_endpoint_tested"])
        self.assertFalse(r["booking_enabled_by_this_check"])
    def test_complete_fixture_is_not_production_acceptance(self):
        self.write("inquiry-config.json",self.config)
        r=report(self.root,now=self.now,env=self.env)
        self.assertTrue(r["config_checks_pass"])
        self.assertFalse(r["legal_compliance_verified"])
        self.assertFalse(r["catalog"]["BG_EXACT_SAMPLE_RESOLVED"])
        self.assertNotIn(self.env["JAMAICA_INQUIRY_HASH_SECRET"],json.dumps(r))
        self.assertNotIn(self.env["JAMAICA_INQUIRY_PROXY_SECRET"],json.dumps(r))
    def test_endpoint_checks(self):
        for url in ("http://example.invalid/v1/customer-inquiries",
                    "https://x:y@example.invalid/v1/customer-inquiries",
                    "https://example.invalid/v1/customer-inquiries?secret=1",
                    "https://example.invalid/other"):
            self.assertFalse(https_url(url,"/v1/customer-inquiries"))
        self.assertFalse(config_status({**self.config,"privacy_approved":False},self.env)["PRIVACY_APPROVAL_RECORDED"])
    def test_pegas_sample_exact_then_expired(self):
        stamp=self.now.isoformat()
        row={"id":"pg_"+"a"*24,"origin":"Иркутск","country":"Таиланд",
             "hotel":"TEST","room":"DBL","resort":"TEST",
             "depart_date":(self.now+timedelta(days=7)).date().isoformat(),"nights":7,
             "status":"PEGAS_APPLICATION_PRICE_REFERENCE_ONLY",
             "price_source":"PEGAS_OPEN_APPLICATION_MANDATORY_FEES_INCLUDED",
             "price_reference_party":"TWO_ADULTS","price_reference_rub":100000,
             "price_observed_at_utc":stamp,
             "bookable":False,"quote_verified":False,"availability_verified":False,"flight_verified":False,
             "evidence":{**dict.fromkeys(("hotel_filter_verified","flight_filter_verified",
                "cheapest_eligible_price_clicked","final_price_observed","mandatory_fees_included"),True),
                "observed_at_utc":stamp}}
        self.write("application-reference.json",{"schema":"jamaica.pegas-reference-catalog.v1",
            "bookable":False,"quote_verified":False,"refreshed_at_utc":stamp,"previews":[row]})
        self.assertTrue(report(self.root,now=self.now,env={})["catalog"]["PEGAS_EXACT_SAMPLE_RESOLVED"])
        self.assertFalse(report(self.root,now=self.now+timedelta(minutes=16),env={})["catalog"]["PEGAS_EXACT_SAMPLE_RESOLVED"])

if __name__=="__main__":unittest.main()
