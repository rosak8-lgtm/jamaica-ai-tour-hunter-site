"""Private hotelPic candidate extraction, exact hotelId and no publication."""
import sys
import json
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import oracle_bg_hotel_media_candidates as m
import oracle_bg_route_sync as bg

class FakeApi:
    def __init__(self,payload):
        self.payload=json.dumps(payload).encode()
        self.urls=[]
    def get(self,url):
        self.urls.append(url)
        return self.payload

class Tests(unittest.TestCase):
    def setUp(self):
        self.catalog={
          "schema":"jamaica.destination-directory.v1",
          "hotels":[{"id":"102623766108","name":"BASAYA BEACH HOTEL & RESORT",
                     "country":"Таиланд","resort":"Паттайя"},
                    {"id":"102610001140","name":"ADRIATIC PALACE PATTAYA",
                     "country":"Таиланд","resort":"Паттайя"}]}
        self.picture="http://www.bgoperator.ru/pr_img/sm1240100354/20140405/2803980246/5091069817120126.png"
    def test_exact_id_picture_candidate_not_public_licensed_photo(self):
        api=FakeApi([{"hotelId":"102623766108","hotelPic":self.picture}])
        obj=m.build_private(self.catalog,api)
        self.assertFalse(obj["publication_authorized"])
        self.assertEqual(obj["hotel_count"],1)
        record=obj["candidates"][0]
        self.assertEqual(record["hotel_id"],"102623766108")
        self.assertEqual(record["hotel_name"],"BASAYA BEACH HOTEL & RESORT")
        self.assertEqual(record["rights_status"],"NOT_VERIFIED_NO_PUBLICATION")
        self.assertTrue(record["candidate_urls"][0].startswith("https://www.bgoperator.ru/pr_img/"))
        self.assertIn("100510397223",api.urls[0])
        self.assertNotIn("license",record)
        self.assertNotIn("approved",record)
    def test_wrong_hotel_id_is_not_mapped_by_name(self):
        rows=[
          {"hotelId":"100000000000","hotelName":"BASAYA BEACH HOTEL & RESORT",
           "hotelPic":self.picture},
          {"hotelId":"102610001140","hotelName":"BASAYA BEACH HOTEL & RESORT",
           "hotelPic":self.picture}
        ]
        matches=m.parse_candidates(json.dumps(rows).encode(),self.catalog["hotels"])
        self.assertEqual([x["hotel_id"] for x in matches],["102610001140"])
        # The identity is the supplier's explicit hotel ID, never fuzzy name.
    def test_url_security(self):
        for value in (
          "https://evil.example/pr_img/a.jpg",
          "http://www.bgoperator.ru.evil.example/pr_img/foo.jpg",
          "file:///etc/passwd",
          "https://www.bgoperator.ru/pr_img/../../secrets.jpg",
          "https://www.bgoperator.ru/pr_img/a.jpg?token=secret",
          "https://username:password@www.bgoperator.ru/pr_img/okay.jpg",
          "https://www.bgoperator.ru/private/photo.jpg",
          "https://www.bgoperator.ru:444/pr_img/a.jpg",
        ):
            self.assertIsNone(m.safe_operator_image(value),value)
    def test_list_max_is_bounded(self):
        with self.assertRaises(bg.SyncHold):
            m.parse_candidates(b"["*5500000,self.catalog["hotels"])
    def test_invalid_json_is_rejected_without_partial_publication(self):
        for source in (b"var priceList = [];",b"{\"entries\":[]}"):
            with self.assertRaises(bg.SyncHold):
                m.parse_candidates(source,self.catalog["hotels"])
    def test_duplicate_images_deduped(self):
        record={"hotelId":"102623766108","hotelPic":self.picture}
        rows=m.parse_candidates(json.dumps([record,record]).encode(),self.catalog["hotels"])
        self.assertEqual(len(rows),1)
        self.assertEqual(len(rows[0]["candidate_urls"]),1)
    def test_discovery_is_private_and_only_daily(self):
        publisher=(Path(__file__).resolve().parent.parent/"scripts"/"oracle_site_publisher.py").read_text()
        self.assertIn("def discover_hotel_media_daily():",publisher)
        self.assertIn("24*3600",publisher)
        self.assertIn("private-hotel-media-candidates.json",publisher)
        self.assertNotIn("hotel-media-approved.json",publisher)
    def test_empty_public_approved_list(self):
        path=Path(__file__).resolve().parent.parent/"hotel-media-approved.json"
        data=json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(data["schema"],"jamaica.hotel-media-approved.v1")
        self.assertEqual(data["hotels"],{})

if __name__=="__main__":unittest.main()
