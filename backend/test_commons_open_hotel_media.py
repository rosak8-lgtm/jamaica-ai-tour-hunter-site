"""Network-free regression for exact hotel Wikidata P18 and Commons commercial license."""
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from urllib.parse import urlparse,parse_qs

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location("commons_open_hotel_media",
       ROOT/"scripts"/"commons_open_hotel_media.py")
c=importlib.util.module_from_spec(spec)
spec.loader.exec_module(c)

HOTEL_ID="102623766108"
HOTEL_NAME="BASAYA BEACH HOTEL & RESORT"
QID="Q123456"
FILE="Basaya Beach Hotel - Verified Exterior.jpg"
DIRECTORY={"schema":"jamaica.destination-directory.v1",
    "hotels":[{"id":HOTEL_ID,"name":HOTEL_NAME,"country":"Таиланд"}]}
MAP={"schema":c.IDENTITY,"hotels":{HOTEL_ID:{
    "hotel_name":HOTEL_NAME,"country":"Таиланд",
    "wikidata_qid":QID,"wikidata_country_qid":"Q869",
    "identity_reviewed":True,
    "review_reference":"https://www.wikidata.org/wiki/Q123456",
    "reviewed_at":"2026-11-20"
}}}

def snak(value):
    return {"mainsnak":{"datavalue":{"value":value}}}
def wikidata(country="Q869",image=FILE):
    return {"entities":{QID:{"claims":{
      "P17":[snak({"id":country})],
      "P18":[snak(image)]}}}}
def commons(license="CC BY-SA 4.0",url="https://creativecommons.org/licenses/by-sa/4.0/"):
    return {"query":{"pages":{"17":{
      "title":"File:"+FILE,
      "imageinfo":[{"mime":"image/jpeg","extmetadata":{
        "Artist":{"value":"<a href=\"/wiki/User:Photographer\">Verified author</a>"},
        "LicenseShortName":{"value":license},
        "LicenseUrl":{"value":url}}}]}}}}
class Response:
 def __init__(self,data):
    self.data=json.dumps(data,ensure_ascii=False).encode();self.status=200
 def __enter__(self):return self
 def __exit__(self,*_):pass
 def read(self,maxsize):return self.data[:maxsize]
def transport_factory(wiki=None,media=None,calls=None):
    wiki=wikidata() if wiki is None else wiki
    media=commons() if media is None else media
    def transport(request):
        if calls is not None:calls.append(request.full_url)
        return Response(wiki if request.full_url.startswith(c.WD+"?") else media)
    return transport

class Tests(unittest.TestCase):
 def test_approved_property_and_license_no_binary_download(self):
    called=[]
    entries,stats=c.build(DIRECTORY,MAP,transport=transport_factory(calls=called))
    self.assertEqual(len(called),2)
    self.assertIn("wbgetentities",called[0])
    self.assertIn("imageinfo",called[1])
    self.assertEqual(stats["hotels"],1)
    self.assertEqual(stats["photos"],1)
    p=entries[HOTEL_ID]["photos"][0]
    self.assertEqual(p["license"],"CC BY-SA 4.0")
    self.assertEqual(p["author"],"Verified author")
    self.assertEqual(p["file"],FILE)
    self.assertIn("Special:FilePath/",p["src"])
    self.assertTrue(p["src"].startswith("https://commons.wikimedia.org/"))
    self.assertEqual(p["wikidata_qid"],QID)
    with tempfile.TemporaryDirectory() as d:
        self.assertEqual(c.stage(d,entries),1)
        index=json.loads((Path(d)/"hotel-open-media/index.json").read_text())
        self.assertEqual(index["total_hotels"],1)
        path=index["entries"][HOTEL_ID]
        part=json.loads((Path(d)/path).read_text())
        self.assertEqual(part["hotels"][HOTEL_ID]["photos"][0],p)
        self.assertEqual(index["schema"],"jamaica.hotel-open-media-index.v1")

 def test_wikidata_country_must_match_independently_reviewed_country(self):
    e,stats=c.build(DIRECTORY,MAP,
       transport=transport_factory(wiki=wikidata(country="Q148")))
    self.assertEqual(e,{})
    self.assertEqual(stats["country_rejected"],1)

 def test_noncommercial_image_license_is_disallowed(self):
    for license in ("CC BY-NC 4.0","CC BY-NC-SA 4.0","All rights reserved",
                    "GFDL","Flickr users only"):
        with self.subTest(license=license):
            e,stats=c.build(DIRECTORY,MAP,
                transport=transport_factory(media=commons(license=license)))
            self.assertEqual(e,{})
            self.assertEqual(stats["license_rejected"],1)

 def test_wrong_license_link_or_missing_author_is_rejected(self):
    e,_=c.build(DIRECTORY,MAP,
       transport=transport_factory(media=commons(url="https://phishing.example/license")))
    self.assertEqual(e,{})
    altered=commons()
    altered["query"]["pages"]["17"]["imageinfo"][0]["extmetadata"]["Artist"]={"value":""}
    e,_=c.build(DIRECTORY,MAP,transport=transport_factory(media=altered))
    self.assertEqual(e,{})

 def test_wikidata_verified_mapping_has_strict_exact_jamaica_identity(self):
    bads=[
     {"hotel_name":"Wrong Hotel"},{"country":"Китай"},
     {"wikidata_country_qid":"Q148"},{"identity_reviewed":False},
     {"review_reference":"https://"},{"reviewed_at":"2030-01-01"},
    ]
    for change in bads:
        with self.subTest(change=change),self.assertRaises(c.Hold):
            data={"schema":c.IDENTITY,
                "hotels":{HOTEL_ID:{**MAP["hotels"][HOTEL_ID],**change}}}
            c.check_identities(data,DIRECTORY)

 def test_no_unreviewed_extra_photos_or_embedded_web_search(self):
    for file in ("../other.jpg","https://evil.example/a.jpg",
                 "wrong.svg","IMG.jpg?bad=1"):
        with self.subTest(file=file):
            self.assertIsNone(c.safe_file(file))
    extra={**MAP["hotels"][HOTEL_ID],
      "additional_photos":[{"file":"Other Hotel.jpg",
        "kind":"hotel_exterior",
        "property_photo_reviewed":False,
        "review_reference":"https://commons.wikimedia.org/wiki/File:Other_Hotel.jpg"}]}
    with self.assertRaises(c.Hold):
        c.check_identities({"schema":c.IDENTITY,"hotels":{HOTEL_ID:extra}},DIRECTORY)

if __name__=="__main__":unittest.main()
