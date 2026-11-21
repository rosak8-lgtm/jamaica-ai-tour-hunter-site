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
        self.assertIn('historical_view_not_property_facade:"Исторический вид из гостиницы"',self.page)
    def test_page_description_precedes_gallery(self):
        self.assertLess(self.page.index('id="hotelDescriptionSection"'),self.page.index('id="gallery"'))
        for id_ in ("enrichedFeatures","curatedRooms","facts","rooms","gallery","reviewForm"):
            self.assertIn('id="'+id_+'"',self.page)
    def test_basaya_source_backed_room_and_facility_details(self):
        basaya=self.data["hotels"]["102623766108"]
        self.assertEqual(basaya["name"],"BASAYA BEACH HOTEL & RESORT")
        self.assertEqual(basaya["rooms_total"],"110")
        self.assertEqual(basaya["renovation_year"],"2023")
        self.assertEqual(basaya["country"],"Таиланд")
        for name in ("STANDARD ROOM","DELUXE ROOM","NEW STANDARD WITH BALCONY"):
            self.assertIn(name," ".join(basaya["room_categories"]))
        self.assertEqual(basaya["photos"],[])
        self.assertEqual(len(basaya["sources"]),1)
    def test_guangzhou_hotel_with_three_commercially_reusable_external_photos(self):
        china=self.data["hotels"]["102667206879"]
        self.assertEqual(china["name"],"ASIA INTERNATIONAL HOTEL GUANGDONG (广东亚洲国际大酒店)")
        self.assertEqual(china["country"],"Китай")
        self.assertEqual(china["resort"],"Гуанчжоу")
        self.assertIn("Юэсю",china["editorial_description"])
        self.assertEqual(len(china["photos"]),6)
        self.assertEqual([p["kind"] for p in china["photos"]].count("hotel_exterior"),3)
        self.assertEqual([p["kind"] for p in china["photos"]].count("view_from_hotel"),3)
        self.assertIn("НЕ являются фотографиями номеров",china["photo_note"])
        for photo in china["photos"]:
            self.assertEqual(photo["author"],"中少")
            self.assertEqual(photo["license"],"CC BY-SA 4.0")
            self.assertEqual(photo["license_url"],
                "https://creativecommons.org/licenses/by-sa/4.0/")
            self.assertIn(photo["kind"],("hotel_exterior","view_from_hotel"))
            if photo["kind"]=="view_from_hotel":
                self.assertIn("45F Revolving Restaurant",photo["file"])
                self.assertIn("Гуанчжоу",photo["title"])
            self.assertEqual(photo["source"],
                "https://commons.wikimedia.org/wiki/File:"+photo["file"].replace(" ","_"))
        self.assertIn("CC BY-SA 4.0",self.page)
        self.assertIn("encodeURIComponent(photo.file)",self.page)
    def test_external_approved_hotel_photos_use_remote_https_link_only(self):
        self.assertIn("function strictExternalPhotoUrl(",self.page)
        self.assertIn("entry.approved_image_hosts",self.page)
        self.assertIn("entry.rights_verified_at",self.page)
        self.assertIn('p.license!=="contract-authorized"',self.page)
        self.assertIn('img.loading="lazy"',self.page)
        self.assertIn("loadPhotos(true)",self.page)

    def test_fallback_after_broken_remote_commons_images(self):
        self.assertIn('figure.dataset.photoSource=hotelPhoto?',self.page)
        self.assertIn('img.addEventListener("error",()=>{',self.page)
        self.assertIn('if(hotelPhoto)loadDestinationPhotos(place);',self.page)
        self.assertIn('else showPhotoPlaceholder();',self.page)
        self.assertIn('img.decoding="async"',self.page)
        self.assertIn('img.referrerPolicy="no-referrer"',self.page)

    def test_city_scenery_fallback_is_not_a_hotel_photo(self):
        self.assertIn('"Гуанчжоу":"Guangzhou"',self.page)
        self.assertIn('"Шанхай":"Shanghai"',self.page)
        self.assertIn('"Пекин":"Beijing"',self.page)
        self.assertIn('const isCity=new Set(',self.page)
        self.assertIn('" skyline filetype:bitmap"',self.page)
        self.assertIn('hotelPhoto:false,place',self.page)
        self.assertIn('НЕ фотография гостиницы',self.page)

    def test_unlicensed_hotel_photos_never_claimed_to_be_resort_photos(self):
        self.assertIn("async function loadRightsApprovedHotelPhotos()",self.page)
        self.assertIn('entry.commercial_publication_allowed!==true',self.page)
        self.assertIn('hotel-media-approved.json',self.page)
        self.assertIn("Курорт "+'"',self.page)
        self.assertIn("НЕ фотография гостиницы",self.page)
        self.assertIn("paintCommonsPhotos(",self.page)
        self.assertIn("hotel.resort||hotel.country",self.page)
    def test_reviews_and_sales_remain_fail_closed(self):
        review=json.loads((ROOT/"hotel-reviews-config.json").read_text(encoding="utf-8"))
        purchase=json.loads((ROOT/"checkout-config.json").read_text(encoding="utf-8"))
        self.assertFalse(review["enabled"])
        self.assertFalse(purchase["payments_enabled"])
        self.assertFalse(purchase["live_booking_enabled"])
if __name__=="__main__":unittest.main()
