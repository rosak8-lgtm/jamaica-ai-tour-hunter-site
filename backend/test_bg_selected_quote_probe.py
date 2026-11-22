import json
import sys
import unittest
from datetime import datetime,timedelta,timezone
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import oracle_bg_selected_quote_probe as selected
import oracle_bg_preview_export as exporter
import oracle_bg_route_sync as bg

DAY=(datetime.now(timezone.utc)+timedelta(days=7)).strftime("%d.%m.%Y")
DATE=bg.date_iso(DAY).isoformat()
COUNTRY={"name":"Индонезия","id":"100410000051","has_tour_catalog":True,"origins":[bg.CITY_ID]}
HOTEL={"id":"102610001486","name":"Test reference hotel","country":"Индонезия","resort":"Бали"}
ROW={"id_hotel":HOTEL["id"],"tour_date":DAY,"duration":"7",
     "room":"STANDARD HB","town":"Бали",
     "prices":[{"amount":"1700","RUR":"115000","ag":"12+,12+"},
               {"amount":"1400","ag":"2-11,12+"}]}
P=exporter.safe_preview(ROW,COUNTRY["name"],{HOTEL["id"]:HOTEL})
URL=("https://export.bgoperator.ru/partners?action=price&tid=211&flt="
     +COUNTRY["id"]+"&flt2="+bg.CITY_ID+"&id_price=121132934133&data="+DAY+"&xml=11")

class Api:
    def __init__(self,match=True):self.match=match;self.calls=[]
    def get(self,url):
        self.calls.append(url)
        if "/yandex?" in url:
            return json.dumps({"entries":[{"date":DAY,"url":URL}]}).encode()
        if "/partners?" in url:
            return json.dumps({"entries":[ROW if self.match else {**ROW,"room":"OTHER"}]}).encode()
        raise AssertionError("Unapproved request")

class Tests(unittest.TestCase):
    def setup_data(self):
        return {"schema":"jamaica.destination-directory.v1",
                "countries":[COUNTRY],"hotels":[HOTEL]},{
                "schema":"jamaica.tour-previews.v1","bookable":False,
                "previews":[P]}
    def test_matching_price_reference_is_not_verified_quote(self):
        d,feed=self.setup_data()
        a=Api()
        result=selected.inspect_selected(d,feed,P["id"],a)
        self.assertEqual(result["matched_rows"],1)
        self.assertEqual(result["price_options"],2)
        self.assertEqual(result["rub_price_fields"],1)
        self.assertEqual(result["two_adults_age_markers"],1)
        self.assertIs(result["bookable"],False)
        self.assertIs(result["quote_verified"],False)
        self.assertIs(result["availability_verified"],False)
        self.assertNotIn("115000",str(result))
        self.assertNotIn("121132934133",str(result))
        self.assertEqual(len(a.calls),2)
    def test_exact_selected_family_rooms_are_checked_against_age_buckets(self):
        d,feed=self.setup_data()
        rooms=[{"adults":2,"child_ages":[]},{"adults":1,"child_ages":[6]}]
        api=Api()
        r=selected.inspect_selected(d,feed,P["id"],api,selected_rooms=rooms)
        self.assertEqual(r["group_status"],"POTENTIAL_CANDIDATES_ONLY")
        self.assertEqual(r["group_count"],2)
        self.assertEqual(r["group_age_candidate_counts"],[1,1])
        self.assertEqual(r["group_source_metadata_counts"],[0,0])
        self.assertFalse(r["quote_verified"])
        self.assertFalse(r["availability_verified"])
        self.assertFalse(r["bookable"])
        self.assertEqual(len(api.calls),2)
        self.assertNotIn("115000",str(r))
        self.assertNotIn("121132934133",str(r))

    def test_no_compatible_child_age_blocks_family_candidate(self):
        d,feed=self.setup_data()
        r=selected.inspect_selected(d,feed,P["id"],Api(),
            selected_rooms=[{"adults":2,"child_ages":[]},
                            {"adults":1,"child_ages":[0]}])
        self.assertEqual(r["group_age_candidate_counts"],[1,0])
        self.assertEqual(r["group_status"],"MISSING_GROUP_AGE_CANDIDATES")
        self.assertFalse(r["bookable"])

    def test_invalid_party_is_rejected_before_credentialled_network(self):
        d,feed=self.setup_data()
        api=Api()
        with self.assertRaises(bg.SyncHold):
            selected.inspect_selected(d,feed,P["id"],api,
                selected_rooms=[{"adults":0,"child_ages":[]}])
        self.assertEqual(api.calls,[])

    def test_invalid_price_amounts_are_not_eligible(self):
        for value in (None,"",0,-50,"NaN","Infinity",[],["500"],{},True,"not a price"):
            self.assertFalse(selected.valid_positive_amount(value),repr(value))
        for value in ("1","1000.50",100,1.25):
            self.assertTrue(selected.valid_positive_amount(value),repr(value))
    def test_only_numeric_rub_amount_is_counted(self):
        corrupted={**ROW,"prices":[{"RUR":["90000"],"amount":"1000","ag":"12+,12+"}]}
        result=selected.inspect_match([corrupted],P,{HOTEL["id"]:HOTEL})
        self.assertEqual(result["two_adults_with_rub"],0)
        self.assertEqual(result["two_adults_amount_only"],1)
    def test_range_encoded_adults(self):
        self.assertTrue(selected.adult_pair_marker("12+,12+"))
        self.assertTrue(selected.adult_pair_marker("12-99,12-99"))
        self.assertTrue(selected.adult_pair_marker("[14-99],[14-99]"))
        self.assertFalse(selected.adult_pair_marker("2-11,12+"))
        self.assertFalse(selected.adult_pair_marker("18+,2-11"))
        self.assertFalse(selected.adult_pair_marker("12+,12+,12+"))
        self.assertFalse(selected.adult_pair_marker("any"))
    def test_non_rub_amount_only_is_not_a_sale_price(self):
        row={**ROW,"prices":[{"amount":"1000","ag":"12+,12+"}]}
        result=selected.inspect_match([row],P,{HOTEL["id"]:HOTEL})
        self.assertEqual(result["two_adults_amount_only"],1)
        self.assertEqual(result["two_adults_with_rub"],0)
    def test_age_buckets_are_aggregate_only(self):
        row={**ROW,"prices":[{"amount":"100","RUR":"9000","ag":"SECRET"},
                              {"amount":"100","RUR":"9000","ag":"12-99,12-99"}]}
        result=selected.inspect_match([row],P,{HOTEL["id"]:HOTEL})
        self.assertEqual(result["age_value_present"],2)
        self.assertEqual(result["age_marker_unrecognized"],1)
        self.assertEqual(result["two_adults_with_rub"],1)
        self.assertNotIn("SECRET",str(result))
    def test_adult_rub_requires_both_on_same_price_option(self):
        conflicting={**ROW,"prices":[
          {"RUR":"95000","ag":"2-11,12+","amount":"1000"},
          {"ag":"12+,12+","amount":"1100"}
        ]}
        result=selected.inspect_match([conflicting],P,{HOTEL["id"]:HOTEL})
        self.assertEqual(result["rub_price_fields"],1)
        self.assertEqual(result["two_adults_age_markers"],1)
        self.assertEqual(result["two_adults_with_rub"],0)
    def test_same_option_has_two_adults_and_rub(self):
        result=selected.inspect_match([ROW],P,{HOTEL["id"]:HOTEL})
        self.assertEqual(result["two_adults_with_rub"],1)
    def test_avoid_false_matches(self):
        d,feed=self.setup_data()
        result=selected.inspect_selected(d,feed,P["id"],Api(match=False))
        self.assertEqual(result["status"],"NO_CURRENT_MATCH")
        self.assertEqual(result["price_options"],0)
    def test_fail_if_preview_not_in_public_feed(self):
        d,feed=self.setup_data()
        with self.assertRaises(bg.SyncHold):
            selected.inspect_selected(d,feed,"p_"+"f"*24,Api())
    def test_reject_preview_claiming_bookable(self):
        d,feed=self.setup_data()
        feed["previews"][0]={**P,"bookable":True}
        with self.assertRaises(bg.SyncHold):
            selected.inspect_selected(d,feed,P["id"],Api())
    def test_blocked_price_options_are_not_counted(self):
        blocked={**ROW,"prices":[{"amount":"120","isstop":["avia_to"]}]}
        result=selected.inspect_match([blocked],P,{HOTEL["id"]:HOTEL})
        # preview exporter deliberately blocks only rows without any
        # unblocked price options; a stopped row cannot become a quote.
        self.assertEqual(result["price_options"],0)
if __name__=="__main__":
    unittest.main()
