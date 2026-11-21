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

 def test_main_image_and_balanced_galleries_from_real_hbx_types(self):
    # HBX's visualOrder=0 is the main property image, NOT the first API row.
    imgs=[]
    for i in range(24):
        type_code="HAB" if i<12 else "RES" if i<16 else "GEN"
        photo={"path":f"00/004200/example_{i:03d}.jpg",
            "visualOrder":30+i,
            "order":i,
            "imageTypeCode":type_code}
        if type_code=="HAB":photo["roomCode"]="ROO.ST"
        imgs.append(photo)
    imgs[23]["visualOrder"]=0
    enhanced={**HOTEL,"images":imgs}
    result,_=hbx.build(GRANT,CROSSWALK,DIRECTORY,
        [{"hotels":[enhanced]}],today=TODAY)
    photos=result[HOTEL_ID]["photos"]
    self.assertEqual(len(photos),12)
    self.assertEqual(photos[0]["supplier_visual_order"],0)
    self.assertTrue(photos[0]["src"].endswith("example_023.jpg"))
    self.assertEqual(photos[0]["kind"],"other")
    self.assertEqual(photos[0]["image_type_code"],"GEN")
    self.assertEqual(sum(p["kind"]=="room" for p in photos),4)
    self.assertEqual(sum(p["kind"]=="restaurant" for p in photos),2)
    self.assertEqual(sum(p["kind"]=="other" for p in photos),6)
    self.assertTrue(all(p["source"].startswith("https://photos.hotelbeds.com/giata/")
        and p["src"].startswith("https://photos.hotelbeds.com/giata/bigger/")
        for p in photos))
    rooms=[p for p in photos if p["kind"]=="room"]
    self.assertTrue(all(p["supplier_room_code"]=="ROO.ST" for p in rooms))
    self.assertTrue(all("не гарантия выбранной категории" in p["alt"]
         for p in rooms))

 def test_main_image_zero_and_missing_image_order_safety(self):
    self.assertEqual(hbx.supplier_photo_order(0),0)
    self.assertEqual(hbx.supplier_photo_order("0"),0)
    self.assertGreater(hbx.supplier_photo_order(None),100000)
    self.assertGreater(hbx.supplier_photo_order("bad"),100000)
    self.assertEqual(hbx.supplier_photo_kind({"type":{"code":"HAB"}}),"room")
    self.assertEqual(hbx.supplier_photo_kind({"imageTypeCode":"RES"}),"restaurant")
    self.assertEqual(hbx.supplier_photo_kind({"imageTypeCode":"GEN"}),"other")
    self.assertEqual(hbx.supplier_photo_kind({"imageTypeCode":"DEP"}),"other")

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
