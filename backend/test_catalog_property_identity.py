"""No-network full hotel identity gate for all published JAMAICA tour cards."""
import unittest
from scripts import catalog_property_identity as identity


HOTEL_A="102612345678"
HOTEL_B="102687654321"
ROW={
    "id":"p_"+"a"*24,"hotel_id":HOTEL_A,
    "hotel":"SHIJIA BOUTIQUE HOTEL","country":"Китай","origin":"Иркутск",
    "depart_date":"2026-12-06","nights":4,"room":"STANDARD ROOM BB",
    "resort":"Пекин","price_reference_rub":91194,
    "bookable":False,"flight_verified":False,
}
DIRECTORY={"hotels":[
    {"id":HOTEL_A,"name":"SHIJIA BOUTIQUE HOTEL","country":"Китай"},
    {"id":HOTEL_B,"name":"BASAYA BEACH HOTEL & RESORT","country":"Таиланд"},
]}


class Tests(unittest.TestCase):
    def test_verified_identity_for_all_rows(self):
        first=dict(ROW)
        second={**ROW,"id":"p_"+"b"*24,
                "hotel_id":HOTEL_B,"hotel":"BASAYA BEACH HOTEL & RESORT",
                "country":"Таиланд"}
        report=identity.verify_catalog_hotel_identity([first,second],DIRECTORY)
        self.assertEqual(report["checked"],2)
        self.assertEqual(report["countries"],2)
        self.assertTrue(report["hotel_id_match"])
        self.assertTrue(report["hotel_name_match"])
        self.assertTrue(report["country_match"])

    def test_mismatched_shijia_photo_like_id_is_not_equivalent(self):
        # A city photo cannot prove any hotel identity. The source row
        # itself must exactly map to a provider hotel record before publish.
        changes=(
            {"hotel":"GRAND HYATT SHANGHAI"},
            {"hotel":"SHIJIA BOUTIQUE HOTEL 2"},
            {"hotel":"SHIJIA BOUTIQUE"},
            {"hotel_id":HOTEL_B},
            {"hotel_id":"999999999999"},
            {"country":"Таиланд"},
            {"country":"Китай "},
            {"origin":"Москва"},
            {"bookable":True},
            {"flight_verified":True},
            {"id":"p_"+"z"*24},
            {"id":None},
        )
        for change in changes:
            with self.subTest(change=change),self.assertRaises(
                identity.IdentityMismatch):
                identity.verify_catalog_hotel_identity([{**ROW,**change}],DIRECTORY)

    def test_no_silent_duplicate_or_missing_property(self):
        with self.assertRaises(identity.IdentityMismatch):
            identity.verify_catalog_hotel_identity([ROW,dict(ROW)],DIRECTORY)
        with self.assertRaises(identity.IdentityMismatch):
            identity.verify_catalog_hotel_identity([],DIRECTORY)
        with self.assertRaises(identity.IdentityMismatch):
            identity.verify_catalog_hotel_identity([ROW],{"hotels":[]})
        with self.assertRaises(identity.IdentityMismatch):
            identity.verify_catalog_hotel_identity([ROW],{"hotels":[
                DIRECTORY["hotels"][0],DIRECTORY["hotels"][0]
            ]})
        with self.assertRaises(identity.IdentityMismatch):
            identity.verify_catalog_hotel_identity([ROW],{"hotels":[
                {"id":HOTEL_A,"name":"OTHER HOTEL","country":"Китай"}
            ]})

    def test_html_and_long_directory_name_follow_exporter_normalization(self):
        self.assertEqual(identity.public_operator_name("  Шицзя   Бутик  "),
                         "Шицзя Бутик")
        self.assertEqual(identity.public_operator_name("Royal &amp; Spa"),
                         "Royal & Spa")
        self.assertEqual(identity.public_operator_name("<i>Named</i> Hotel"),
                         "Named Hotel")
        name="R"*120
        directory={"hotels":[{"id":HOTEL_A,"name":name,"country":"Китай"}]}
        res=identity.verify_catalog_hotel_identity(
            [{**ROW,"hotel":name[:110]}],directory)
        self.assertEqual(res["checked"],1)

    def test_60000_authentic_records_are_audited_without_sampled_skips(self):
        records=[{**ROW,"id":"p_"+format(i,"024x")} for i in range(60000)]
        report=identity.verify_catalog_hotel_identity(records,DIRECTORY)
        self.assertEqual(report["checked"],60000)
        records[-1]["hotel"]="Wrong hotel at last record"
        with self.assertRaises(identity.IdentityMismatch):
            identity.verify_catalog_hotel_identity(records,DIRECTORY)


if __name__=="__main__":
    unittest.main()
