"""Staged crosswalk candidates are private, conservative and never auto-approved."""
import importlib.util
import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(ROOT/"scripts"))
spec=importlib.util.spec_from_file_location(
 "hbx_crosswalk_candidates",ROOT/"scripts"/"hbx_crosswalk_candidates.py")
staged=importlib.util.module_from_spec(spec)
spec.loader.exec_module(staged)

def bg(hid,name,country="Таиланд",resort="Паттайя"):
    return {"id":hid,"name":name,"country":country,"resort":resort}

def hbx(code,name,country="TH"):
    return {"code":code,"name":{"content":name},"countryCode":country,
       "city":{"content":"Pattaya"},
       "images":[{"path":"00/004200/004200a_hb_ro_006.jpg"}]}

DIRECTORY={"schema":"jamaica.destination-directory.v1",
           "hotels":[
              bg("102623766108","BASAYA BEACH HOTEL & RESORT"),
              bg("102667206879","ASIA INTERNATIONAL HOTEL GUANGDONG","Китай","Гуанчжоу"),
              bg("102345678901","DUPLICATE HOTEL","Таиланд","Пхукет"),
              bg("102345678902","DUPLICATE HOTEL","Таиланд","Самуи")]}

class Tests(unittest.TestCase):
    def test_unique_exact_normalized_country_candidate(self):
        raw=[{"hotels":[hbx(100,"basaya beach hotel & resort"),
                        hbx(101,"Asia International Hotel Guangdong","CN"),
                        hbx(102,"duplicate hotel")]}]
        data=staged.build_candidates(DIRECTORY,raw)
        self.assertEqual(data["candidate_count"],2)
        self.assertEqual(data["publication_authorized"],False)
        self.assertTrue(all(not x["publication_authorized"] for x in data["candidates"]))
        self.assertTrue(all(x["identity_evidence_reference"] is None for x in data["candidates"]))
        self.assertEqual({x["jamaica_hotel_id"] for x in data["candidates"]},
                         {"102623766108","102667206879"})
        self.assertEqual(data["candidates"][0]["hbx_image_paths"],1)

    def test_country_mismatch_and_similarity_are_not_sufficient(self):
        bad=[{"hotels":[hbx(100,"Basaya Beach Hotel and Spa","TH"),
                        hbx(101,"ASIA INTERNATIONAL HOTEL GUANGDONG","TH"),
                        hbx(102,"Koh Samui Beach Hotel","CN")]}]
        data=staged.build_candidates(DIRECTORY,bad)
        self.assertEqual(data["candidate_count"],0)

    def test_ambiguous_provider_names_are_excluded(self):
        raw=[{"hotels":[hbx(100,"BASAYA BEACH HOTEL & RESORT"),
                        hbx(101,"BASAYA BEACH HOTEL & RESORT")]}]
        data=staged.build_candidates(DIRECTORY,raw)
        self.assertEqual(data["candidate_count"],0)

    def test_staging_only_private_0600_file(self):
        data=staged.build_candidates(DIRECTORY,
            [{"hotels":[hbx(100,"BASAYA BEACH HOTEL & RESORT")]}])
        with tempfile.TemporaryDirectory() as td:
            p=Path(td)/"private_candidates.json"
            staged.write_private(p,data)
            self.assertEqual(p.stat().st_mode & 0o777,0o600)
            saved=json.loads(p.read_text())
            self.assertEqual(saved["schema"],"jamaica.private.hbx-crosswalk-candidates.v1")
            self.assertNotEqual(saved["schema"],"jamaica.hbx-crosswalk.v1")
            self.assertFalse(saved["publication_authorized"])
            with self.assertRaises(staged.MediaHold):
                staged.write_private(Path(td)/"crosswalk.json",data)

    def test_unknown_country_not_guessed(self):
        source={"schema":DIRECTORY["schema"],
            "hotels":[bg("102345678932","SOME HOTEL","Неизвестная страна")]}
        data=staged.build_candidates(source,[{"hotels":[hbx(100,"SOME HOTEL","ZZ")]}])
        self.assertEqual(data["candidate_count"],0)

if __name__=="__main__": unittest.main()
