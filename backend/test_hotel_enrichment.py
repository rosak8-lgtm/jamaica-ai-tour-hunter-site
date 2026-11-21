import json
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent
HOTEL="102610001140"

class Tests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data=json.loads((ROOT/"hotel-enrichment.json").read_text(encoding="utf-8"))
        cls.page=(ROOT/"hotel.html").read_text(encoding="utf-8")
        cls.hotel=cls.data["hotels"][HOTEL]
    def test_enrichment_schema_and_real_source(self):
        self.assertEqual(self.data["schema"],"jamaica.hotel-enrichment.v1")
        self.assertEqual(self.hotel["name"],"ADRIATIC PALACE PATTAYA")
        self.assertEqual(self.hotel["country"],"Таиланд")
        self.assertEqual(self.hotel["source_checked_at"],"2026-11-21")
        self.assertGreater(len(self.hotel["editorial_description"]),100)
        self.assertTrue(all(s["url"].startswith("https://www.bgoperator.ru/price.shtml?")
                            for s in self.hotel["sources"]))
    def test_rooms_facts_from_published_hotel(self):
        self.assertEqual(self.hotel["rooms_total"],"402")
        self.assertEqual(self.hotel["year_built"],"1997")
        joined=" ".join(self.hotel["room_categories"])
        for needle in ("Superior","Deluxe","Panorama","Excellency","One Bedroom Suite"):
            self.assertIn(needle.lower(),joined.lower())
        for key in ("amenities","meals","room_features","guest_notes"):
            self.assertGreater(len(self.hotel[key]),0)
    def test_licensed_2010_photos_must_not_be_called_facade(self):
        self.assertGreaterEqual(len(self.hotel["photos"]),2)
        for image in self.hotel["photos"]:
            self.assertEqual(image["license"],"CC BY-SA 3.0")
            self.assertEqual(image["author"],"KAlexey")
            self.assertEqual(image["kind"],"historical_view_not_property_facade")
            self.assertEqual(image["source"],
                             "https://commons.wikimedia.org/wiki/File:"+image["file"])
            self.assertTrue(image["file"].endswith(".jpg"))
            self.assertIn("2010",image["title"])
    def test_page_fails_closed_if_enrichment_wrong_hotel(self):
        self.assertIn('entry.name!==hotel.name||entry.country!==hotel.country',self.page)
        self.assertIn('entry.source_checked_at',self.page)
        self.assertIn('p.kind==="historical_view_not_property_facade"',self.page)
    def test_page_description_precedes_gallery(self):
        self.assertLess(self.page.index('id="hotelDescriptionSection"'),self.page.index('id="gallery"'))
        for id_ in ("enrichedFeatures","curatedRooms","facts","rooms","gallery","reviewForm"):
            self.assertIn('id="'+id_+'"',self.page)
    def test_reviews_and_sales_remain_fail_closed(self):
        review=json.loads((ROOT/"hotel-reviews-config.json").read_text(encoding="utf-8"))
        purchase=json.loads((ROOT/"checkout-config.json").read_text(encoding="utf-8"))
        self.assertFalse(review["enabled"])
        self.assertFalse(purchase["payments_enabled"])
        self.assertFalse(purchase["live_booking_enabled"])
if __name__=="__main__":unittest.main()
