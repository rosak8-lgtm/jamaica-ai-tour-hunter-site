import json
import unittest
from datetime import timedelta
from backend.customer_inquiry_smoke import smoke
from backend import test_customer_inquiry as fixture_module

class Tests(unittest.TestCase):
    def setUp(self):
        self.fixture=fixture_module.Tests()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)

    def test_real_resolver_and_temporary_loopback_chain(self):
        root=self.fixture.root
        existing=(root/"inquiries.sqlite").read_bytes()
        result=smoke(root)
        self.assertEqual(result["status"],"PASS_LOCAL_SYNTHETIC_INQUIRY")
        self.assertTrue(all(result["checks"].values()))
        self.assertEqual(existing,(root/"inquiries.sqlite").read_bytes())
        self.assertEqual(result["real_customer_contacts"],0)
        self.assertFalse(result["public_endpoint_tested"])
        self.assertNotIn("synthetic@example.invalid",json.dumps(result))

    def test_stale_sample_never_submitted(self):
        self.fixture.proofs["entries"][0]["observed_at_utc"]=(self.fixture.now-timedelta(minutes=16)).isoformat()
        self.fixture.write()
        result=smoke(self.fixture.root)
        self.assertEqual(result["status"],"HOLD_NO_FRESH_SAMPLE")
        self.assertFalse(result["sample_found"])
        self.assertNotIn("checks",result)

if __name__=="__main__":unittest.main()
