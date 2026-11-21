"""Tests of one HBX evaluation request, signed credentials and safe redaction."""
import importlib.util
import hashlib
import json
import unittest
from pathlib import Path
from urllib.request import Request

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("hbx_test_probe",ROOT/"scripts"/"hbx_test_probe.py")
probe=importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)

class FakeResponse:
    def __init__(self,body,status=200):
        self.data=body
        self.status=status
    def __enter__(self):return self
    def __exit__(self,*args):return None
    def read(self,size):return self.data[:size]

class Opener:
    def __init__(self,response):self.response=response;self.requests=[]
    def open(self,request,timeout):
        self.requests.append((request,timeout))
        return self.response

KEY="TEST_KEY_PLACEHOLDER"
SECRET="TEST_SECRET_PLACEHOLDER"
SAMPLE=json.dumps({"hotels":{"hotels":[
 {"code":123,"countryCode":"TH","images":[{"path":"00/some.jpg"}]},
 {"code":124,"images":[]}
]}}).encode()

class Tests(unittest.TestCase):
    def test_one_request_only_and_signed_headers(self):
        opener=Opener(FakeResponse(SAMPLE))
        result=probe.check(key=KEY,secret=SECRET,opener=opener,now=123456)
        self.assertEqual(result["hotels"],2)
        self.assertEqual(result["photo_paths"],1)
        self.assertEqual(result["hotels_with_photos"],1)
        self.assertEqual(result["distinct_paths"],1)
        self.assertEqual(result["main_photo_candidates"],0)
        self.assertEqual(result["country_counts"],{"TH":1})
        self.assertEqual(len(opener.requests),1)
        req,timeout=opener.requests[0]
        self.assertEqual(req.full_url,
                         "https://api.test.hotelbeds.com/hotel-content-api/1.0/hotels"
                         "?fields=all&language=ENG&from=1&to=10")
        self.assertEqual(req.get_header("Api-key"),KEY)
        self.assertEqual(req.get_header("X-signature"),
            hashlib.sha256((KEY+SECRET+"123456").encode()).hexdigest())
        self.assertEqual(timeout,20)
        self.assertNotIn(SECRET,repr(result))
        self.assertNotIn(KEY,repr(result))

    def test_cannot_work_without_secret(self):
        for key,secret in (("",SECRET),(KEY,""),("tiny",SECRET)):
            with self.assertRaises(probe.ProbeHold):
                probe.check(key=key,secret=secret,opener=Opener(FakeResponse(SAMPLE)))

    def test_response_bounded_and_not_mass_collection(self):
        with self.assertRaises(probe.ProbeHold):
            probe.parse_summary(b"x"*(probe.MAX_BYTES+1))
        fake=json.dumps({"hotels":{"hotels":[{}]*11}}).encode()
        with self.assertRaises(probe.ProbeHold):
            probe.parse_summary(fake)
        for raw in (b"<html>Forbidden</html>",b"[]",b'{"hotels":1}'):
            with self.assertRaises(probe.ProbeHold):
                probe.parse_summary(raw)

    def test_photographic_type_distribution_is_aggregate_only(self):
        sample={"hotels":{"hotels":[
            {"countryCode":"TH","images":[
                {"path":"00/foo.jpg","imageTypeCode":"GEN","visualOrder":0},
                {"path":"00/foo.jpg","type":{"code":"HAB"},"visualOrder":"15"},
                {"path":"00/rest.jpg","type":{"code":"RES"},"visualOrder":"5"}
            ]},
            {"countryCode":"CN","images":[]}
        ]}}
        result=probe.parse_summary(json.dumps(sample).encode())
        self.assertEqual(result["hotels"],2)
        self.assertEqual(result["photo_paths"],3)
        self.assertEqual(result["distinct_paths"],2)
        self.assertEqual(result["main_photo_candidates"],1)
        self.assertEqual(result["image_type_counts"],{"GEN":1,"HAB":1,"RES":1})
        self.assertEqual(result["country_counts"],{"TH":1,"CN":1})
        self.assertNotIn("foo.jpg",repr(result))
        self.assertNotIn("rest.jpg",repr(result))

    def test_image_details_never_returned_or_downloaded(self):
        result=probe.parse_summary(SAMPLE)
        self.assertEqual(sorted(result),sorted([
             "hotels","photo_paths","hotels_with_photos","distinct_paths",
             "main_photo_candidates","image_type_counts","country_counts"]))
        self.assertEqual(result["photo_paths"],1)
        source=(ROOT/"scripts"/"hbx_test_probe.py").read_text(encoding="utf-8")
        self.assertNotIn("hotelbeds.com/giata/",source)
        self.assertNotIn("bookings",probe.TEST_URL)
        self.assertNotIn("output-dir",source)

if __name__=="__main__":unittest.main()
