"""No-network tests: HBX image link adapter must never invent rights or hotel IDs."""
import importlib.util
import json
import tempfile
import unittest
from datetime import date
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
spec=importlib.util.spec_from_file_location(
 "hbx_licensed_hotel_photos",ROOT/"scripts"/"hbx_licensed_hotel_photos.py")
hbx=importlib.util.module_from_spec(spec)
spec.loader.exec_module(hbx)

TODAY=date(2026,11,21)
HOTEL_ID="102623766108"
COUNTRY="Таиланд"
NAME="BASAYA BEACH HOTEL & RESORT"
GRANT={"schema":"jamaica.hbx-license-grant.v1",
       "provider":"HBX Group",
       "commercial_publication_allowed":True,
       "direct_external_image_display_allowed":True,
       "publication_site":"https://rosak8-lgtm.github.io/jamaica-ai-tour-hunter-site/",
       "public_permission_reference":"CONTRACT_LICENSED_SAMPLE_REFERENCE",
       "attribution_text":"HBX Group licensed hotel photo",
       "license_verified_at":"2026-11-20",
       "rights_expires_at":"2027-11-20"}
CROSSWALK={"schema":"jamaica.hbx-crosswalk.v1","mappings":[{
 "jamaica_hotel_id":HOTEL_ID,"hotel_name":NAME,"country":COUNTRY,
 "hbx_code":32123,"hbx_verified_name":"Basaya Beach Hotel and Resort",
 "hbx_country_code":"TH",
 "identity_evidence_reference":"PROPERTY_MAPPING_PROOF_SAMPLE"}]}
DIRECTORY={"schema":"jamaica.destination-directory.v1",
          "hotels":[{"id":HOTEL_ID,"name":NAME,"country":COUNTRY}]}
IMAGE="00/004200/004200a_hb_ro_006.jpg"
HOTEL={"code":32123,"name":{"content":"Basaya Beach Hotel and Resort"},
       "countryCode":"TH","images":[{"path":IMAGE,"imageTypeCode":"GEN"}]}

class Tests(unittest.TestCase):
 def test_exact_id_country_name_and_rights_publish_external_urls(self):
    result,stats=hbx.build(GRANT,CROSSWALK,DIRECTORY,[{"hotels":[HOTEL]}],today=TODAY)
    self.assertEqual(stats["published_hotel_ids"],1)
    entry=result[HOTEL_ID]
    self.assertEqual(entry["hotel_name"],NAME)
    self.assertTrue(entry["rights_verified"])
    self.assertEqual(entry["photos"][0]["src"],
       "https://photos.hotelbeds.com/giata/bigger/"+IMAGE)
    self.assertEqual(entry["photos"][0]["source"],
       "https://photos.hotelbeds.com/giata/"+IMAGE)
    self.assertEqual(entry["photos"][0]["license"],"contract-authorized")
    self.assertEqual(entry["photos"][0]["kind"],"other")
    with tempfile.TemporaryDirectory() as temp:
        num=hbx.write_feed(temp,result)
        self.assertEqual(num,1)
        idx=json.loads((Path(temp)/"hotel-media-feed/index.json").read_text())
        self.assertEqual(idx["total_hotels"],1)
        self.assertEqual(idx["entries"][HOTEL_ID],"hotel-media-feed/part-0001.json")
        part=json.loads((Path(temp)/idx["entries"][HOTEL_ID]).read_text())
        self.assertEqual(part["hotels"][HOTEL_ID],entry)
        serial=json.dumps([idx,part])
        self.assertNotIn("HBX_API_SECRET",serial)
        self.assertNotIn("HBX_API_KEY",serial)

 def test_evaluation_key_is_never_accepted_for_production(self):
    for env in (
      {"HBX_API_KEY":"abc-production-key","HBX_API_SECRET":"abc-production-secret",
       "HBX_API_ENV":"TEST","HBX_LIVE_CONTENT_RIGHTS_CONFIRMED":"yes"},
      {"HBX_API_KEY":"abc-production-key","HBX_API_SECRET":"abc-production-secret",
       "HBX_API_ENV":"PRODUCTION","HBX_LIVE_CONTENT_RIGHTS_CONFIRMED":"no"},
      {"HBX_API_KEY":"abc-production-key","HBX_API_SECRET":"abc-production-secret",
       "HBX_API_ENV":"EVALUATION","HBX_LIVE_CONTENT_RIGHTS_CONFIRMED":"yes"},
      {},
    ):
        with self.assertRaises(hbx.MediaHold):
            hbx.require_production_environment(env)
    hbx.require_production_environment({
      "HBX_API_KEY":"abc-production-key","HBX_API_SECRET":"abc-production-secret",
      "HBX_API_ENV":"PRODUCTION","HBX_LIVE_CONTENT_RIGHTS_CONFIRMED":"yes"})

 def test_no_publication_rights_fails_closed(self):
    for key,value in (
        ("commercial_publication_allowed",False),
        ("direct_external_image_display_allowed",False),
        ("public_permission_reference",""),
        ("provider","not-hbx"),
        ("publication_site","https://wrong.example/"),
        ("rights_expires_at","2026-11-20"),
    ):
        grant=dict(GRANT);grant[key]=value
        with self.subTest(key=key), self.assertRaises(hbx.MediaHold):
            hbx.build(grant,CROSSWALK,DIRECTORY,[{"hotels":[HOTEL]}],today=TODAY)

 def test_identity_must_be_verified_independently(self):
    for changed in (
        {"name":"Similar Beach Hotel"},
        {"countryCode":"CN"},
        {"code":99999},
    ):
        item={**HOTEL,**changed}
        media,stats=hbx.build(GRANT,CROSSWALK,DIRECTORY,
                              [{"hotels":[item]}],today=TODAY)
        self.assertEqual(stats["published_hotel_ids"],0)
        self.assertEqual(media,{})

 def test_crosswalk_ambiguous_or_mismatched_is_rejected(self):
    for changed in (
        {"hotel_name":"Another Hotel"},
        {"country":"Китай"},
        {"hbx_country_code":"XXQ"},
        {"identity_evidence_reference":""},
    ):
        cross={"schema":CROSSWALK["schema"],
               "mappings":[{**CROSSWALK["mappings"][0],**changed}]}
        with self.subTest(change=changed),self.assertRaises(hbx.MediaHold):
            hbx.verified_map(cross,DIRECTORY)
    cross={"schema":CROSSWALK["schema"],
           "mappings":[CROSSWALK["mappings"][0]]*2}
    with self.assertRaises(hbx.MediaHold):
        hbx.verified_map(cross,DIRECTORY)

 def test_image_path_not_from_external_host_or_injection(self):
    bad=["../../foo.jpg","https://evil.example/photo.jpg",
         "//evil.example/cover.jpg","evil.jpg?cookie=secret",
         "cover.svg","/absolute.jpg","wrong%2Fpath.jpg"]
    fake={**HOTEL,"images":[{"path":x} for x in bad]}
    media,_=hbx.build(GRANT,CROSSWALK,DIRECTORY,
       [{"hotels":[fake]}],today=TODAY)
    self.assertEqual(media,{})

 def test_no_late_unmapped_country_picture(self):
    wrong={**HOTEL,"code":1234,"images":[{"path":IMAGE}]}
    media,_=hbx.build(GRANT,CROSSWALK,DIRECTORY,[{"hotels":[wrong]}],today=TODAY)
    self.assertFalse(media)

if __name__=="__main__":unittest.main()
