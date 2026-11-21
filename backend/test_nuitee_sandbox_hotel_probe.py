"""Network-free security tests for Nuitee sandbox photo-coverage discovery."""
import importlib.util
import json
import unittest
from pathlib import Path
from urllib import error
root=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("nuitee",root/"scripts/nuitee_sandbox_hotel_probe.py")
nuitee=importlib.util.module_from_spec(spec)
spec.loader.exec_module(nuitee)

class Response:
 def __init__(self,raw,status=200):self.raw=raw;self.status=status
 def __enter__(self):return self
 def __exit__(self,*args):pass
 def read(self,n):return self.raw[:n]

class Opener:
 def __init__(self,response):self.response=response;self.calls=0;self.request=None
 def open(self,request,timeout):
    self.calls+=1;self.request=request
    assert timeout==20
    return self.response

class Tests(unittest.TestCase):
 def test_exactly_one_sandbox_metadata_get_and_redaction(self):
    fixture={"data":[
      {"id":"example-a","name":"Example hotel","country":"th",
       "main_photo":"https://static.cupid.travel/hotels/1.jpg",
       "hotelImages":[{"url":"https://static.cupid.travel/hotels/1.jpg"},
                      {"url":"https://static.cupid.travel/hotels/2.jpg"}]},
      {"id":"example-b","name":"Other hotel","country":"th",
       "thumbnail":"https://static.cupid.travel/hotels/3.jpg"}]}
    opener=Opener(Response(json.dumps(fixture).encode()))
    key="ONLY_LOCAL_TEST_SECRET_NO_SEND"
    stats=nuitee.check(key,opener=opener)
    self.assertEqual(opener.calls,1)
    self.assertEqual(opener.request.get_header("X-api-key"),key)
    self.assertEqual(opener.request.get_method(),"GET")
    self.assertIn("countryCode=TH",opener.request.full_url)
    self.assertIn("cityName=Pattaya",opener.request.full_url)
    self.assertEqual(stats["sample_hotels"],2)
    self.assertEqual(stats["main_photos"],2)
    self.assertEqual(stats["image_entries"],2)
    self.assertEqual(stats["unique_image_urls"],3)
    self.assertEqual(stats["countries"],["TH"])
    self.assertNotIn(key,str(stats))
    self.assertNotIn("example-a",str(stats))
 def test_malicious_query_and_malformed_response_fail_closed(self):
    for country in ("US","../etc","CN;DELETE",None):
      with self.assertRaises(nuitee.ProbeHold):
        nuitee.request_for("EXAMPLE_KEY_SANDBOX",country=country)
    for raw in (b"[]",b"{}",b'{"data":{}}',b"not-json",
      json.dumps({"data":[{}]*11}).encode(),b"x"*(nuitee.MAX_BYTES+1)):
      with self.assertRaises(nuitee.ProbeHold):
        nuitee.parse_summary(raw)
 def test_country_mode_exact_and_no_photo_urls_emitted(self):
    req=nuitee.request_for("EXAMPLE_KEY_SANDBOX",country="VN")
    self.assertIn("Nha+Trang",req.full_url)
    s=(root/"scripts/nuitee_sandbox_hotel_probe.py").read_text()
    self.assertNotIn("hotel-media-feed/index.json",s)
    self.assertNotIn("book(",s)
    self.assertNotIn("git push",s)
    self.assertNotIn("open(NUITEE",s)

if __name__=="__main__":unittest.main()
