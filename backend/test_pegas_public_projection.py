import unittest
from datetime import timedelta
from backend import pegas_public_projection as p
from backend.test_pegas_application_evidence import Tests as EvidenceFixture

class Tests(unittest.TestCase):
    def setUp(self):
        fixture=EvidenceFixture()
        fixture.setUp()
        self.now=fixture.now
        labels={"origin":"Иркутск","country":"Таиланд","hotel":"TEST HOTEL","room":"DBL","resort":"TEST RESORT","party_digest":p.PARTY_DIGEST}
        self.s={**fixture.s,**labels}
        self.a={**fixture.a,**labels}
    def project(self,s=None,a=None,now=None):
        return p.project_one(s if s is not None else self.s,a if a is not None else self.a,now=now or self.now)
    def test_real_shape_and_no_private_fields(self):
        row=self.project()
        self.assertTrue(row["id"].startswith("pg_"))
        self.assertEqual(row["price_reference_rub"],120000)
        self.assertEqual(row["price_reference_party"],"TWO_ADULTS")
        for key in ("bookable","quote_verified","availability_verified","flight_verified"):
            self.assertIs(row[key],False)
        for key in ("browser_session_digest","party_digest","selected_offer_id","origin_id","hotel_id"):
            self.assertNotIn(key,row)
        self.assertNotIn("route_best_price_seen",row["evidence"])
    def test_price_and_identity_fail_closed(self):
        for patch in ({"mandatory_fees_included":False},{"hotel":"OTHER"},{"hotel_available":False},{"submitted":True},{"total_rub":0}):
            self.assertIsNone(self.project(a={**self.a,**patch}))
        self.assertIsNone(self.project(s={**self.s,"party_digest":"b"*64},a={**self.a,"party_digest":"b"*64}))
        self.assertIsNone(self.project(now=self.now+timedelta(minutes=16)))
    def test_vietnam_exclusions_and_city_distinct(self):
        for n in (45,60):
            self.assertIsNone(self.project(s={**self.s,"country":"Вьетнам","nights":n},a={**self.a,"country":"Вьетнам","nights":n}))
        other={"origin_id":"other-city","origin":"Москва"}
        self.assertNotEqual(self.project()["id"],self.project(s={**self.s,**other},a={**self.a,**other})["id"])
    def test_duplicate_and_conflict(self):
        catalog=p.build_catalog([(self.s,self.a),(self.s,self.a)],now=self.now)
        self.assertEqual(len(catalog["previews"]),1)
        self.assertFalse(catalog["bookable"])
        self.assertEqual(p.build_catalog([(self.s,self.a),(self.s,{**self.a,"total_rub":1}),(self.s,self.a)],now=self.now)["previews"],[])
    def test_invalid_labels_and_empty_input(self):
        self.assertIsNone(self.project(s={**self.s,"hotel":"<script>"},a={**self.a,"hotel":"<script>"}))
        self.assertEqual(p.build_catalog([],now=self.now)["previews"],[])
        with self.assertRaises(ValueError):p.build_catalog([None]*(p.MAX_ROWS+1),now=self.now)

if __name__=="__main__":unittest.main()
