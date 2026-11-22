import unittest

from backend.bg_price_age_scope import (
    parse_age_ranges, possible_group, exact_ages_match, candidate_report
)

PREVIEW={
 "id":"p_"+"a"*24,
 "hotel_id":"102616490643",
 "hotel":"SAMPLE HOTEL",
 "room":"STANDARD HB",
 "depart_date":"2026-12-11",
 "nights":7,
 "country":"Вьетнам",
 "origin":"Иркутск",
}

def row(room="STANDARD HB",id_ns="104623691678",prices=None,**updates):
    return {
      "id_hotel":PREVIEW["hotel_id"],
      "tour_date":"11.12.2026",
      "duration":"7","room":room,
      "id_ns":id_ns,
      "id_price":"121120516103","dt":"11.12.2026","o_duration":"7",
      "sr":"PRIVATE_PROVIDER_FLIGHT_TOKEN",
      "prices":prices if prices is not None else [
        {"ag":"[14-99][14-99][2-11][12-17]"}
      ],
      **updates
    }

class Tests(unittest.TestCase):
 def test_official_contiguous_and_comma_formats(self):
    self.assertEqual(parse_age_ranges("[14-99][14-99]"),((14,99),(14,99)))
    self.assertEqual(parse_age_ranges("12+,12+,2-11"),((12,120),(12,120),(2,11)))
    self.assertEqual(parse_age_ranges("[14-99], [14-99], [0-1]"),
                     ((14,99),(14,99),(0,1)))
    self.assertEqual(parse_age_ranges("0-0"),((0,0),))
    for bad in ("",None,False,[], "[14-99", "14-99]", "1-2;3-4",
                "[3-1]","-2","999+","nan","12+,","[14-99][abc]"):
        with self.subTest(bad=bad):
            self.assertIsNone(parse_age_ranges(bad))

 def test_unique_price_slots_and_noninferred_adult_dobs(self):
    self.assertTrue(possible_group(2,[6,12],"[14-99][14-99][2-11][12-17]"))
    self.assertTrue(possible_group(2,[6],"12+,2-11,12+"))
    self.assertFalse(possible_group(2,[6],"12+,2-11"))
    self.assertFalse(possible_group(2,[6],"12+,12+,12+"))
    self.assertFalse(possible_group(2,[6],"12+,2-11,2-11"))
    self.assertFalse(possible_group(2,[6],"2-11,2-11,2-11"))
    self.assertFalse(possible_group(1,[],"12+,12+"))
    self.assertFalse(possible_group(2,[6],"nonsense"))
    self.assertFalse(possible_group(True,[],"12+"))
    self.assertFalse(possible_group(2,[True],"12+,12+,0-1"))
    self.assertFalse(possible_group(2,[6,12],"[18-60][18-60][2-11]"))

 def test_unknown_adult_age_is_only_candidate_not_exact(self):
    self.assertTrue(possible_group(1,[6],"[20-40][2-11]"))
    self.assertFalse(exact_ages_match([60,6],"[20-40][2-11]"))
    self.assertTrue(exact_ages_match([32,6],"[20-40][2-11]"))
    self.assertFalse(exact_ages_match([32,6],"[20-40][14-99]"))
    self.assertFalse(exact_ages_match([32,6],"[20-40]"))
    self.assertFalse(exact_ages_match([True,6],"[20-40][2-11]"))

 def test_report_counts_for_two_rooms_without_false_quote(self):
    rooms=[{"adults":2,"child_ages":[6,12]},{"adults":1,"child_ages":[4]}]
    rows=[
      row(),
      row(room="FAMILY HB",id_ns="",prices=[{"ag":"12+,2-11","sr":"OK"}]),
      row(room="FAMILY HB",prices=[{"ag":"12+,2-11","isstop":["hotel"]}]),
      row(room="OTHER HB",prices=[{"ag":"12+,2-11","sr":"OK"}],stop=True),
      row(room="OTHER HB",prices=[{"ag":"12+,2-11","sr":"OK"}],
          id_hotel="100000000000")
    ]
    report=candidate_report(PREVIEW,rooms,rows)
    self.assertEqual(report["candidate_counts"],[1,1])
    self.assertEqual(report["source_metadata_counts"],[1,0])
    self.assertEqual(report["status"],"POTENTIAL_CANDIDATES_ONLY")
    for field in ("exact_supplier_quote","availability_verified",
                  "flight_verified","bookable"):
        self.assertIs(report[field],False)
    rendered=str(report)
    for secret in ("SAMPLE HOTEL","PRIVATE_PROVIDER_FLIGHT_TOKEN",
                   "104623691678","2026-12-11"):
        self.assertNotIn(secret,rendered)

 def test_row_level_source_and_shared_template_for_two_rooms(self):
     rooms=[{"adults":2,"child_ages":[6,12]},{"adults":1,"child_ages":[4]}]
     rows=[row(),row(room="FAMILY HB",id_ns="104623691679",
                     prices=[{"ag":"12+,2-11"}])]
     report=candidate_report(PREVIEW,rooms,rows)
     self.assertEqual(report["candidate_counts"],[1,1])
     self.assertEqual(report["source_metadata_counts"],[1,1])
     self.assertEqual(report["shared_source_candidate_count"],1)
     self.assertEqual(report["source_status"],"POTENTIAL_COMMON_PRICE_LIST_ONLY")
     self.assertFalse(report["exact_supplier_quote"])
     self.assertFalse(report["bookable"])
     for secret in ("121120516103","104623691679","PRIVATE_PROVIDER_FLIGHT_TOKEN"):
         self.assertNotIn(secret,str(report))

 def test_option_level_sr_is_not_official_source(self):
     rooms=[{"adults":2,"child_ages":[6,12]}]
     for changed in (
       {"sr":"","prices":[{"ag":"[14-99][14-99][2-11][12-17]","sr":"OPTION_ONLY"}]},
       {"id_ns":""},{"id_price":""},{"ic":"BROKEN"},
       {"dt":"not-a-date"},{"o_duration":"0"}
     ):
         with self.subTest(changed=tuple(changed.keys())):
             report=candidate_report(PREVIEW,rooms,[row(**changed)])
             self.assertEqual(report["candidate_counts"],[1])
             self.assertEqual(report["source_metadata_counts"],[0])
             self.assertEqual(report["shared_source_candidate_count"],0)
             self.assertFalse(report["bookable"])

 def test_different_template_ids_are_not_one_joint_source(self):
     rooms=[{"adults":2,"child_ages":[6,12]},{"adults":1,"child_ages":[4]}]
     second=row(room="FAMILY HB",id_ns="104623691679",
                id_price="121120516104",prices=[{"ag":"12+,2-11"}])
     report=candidate_report(PREVIEW,rooms,[row(),second])
     self.assertEqual(report["source_metadata_counts"],[1,1])
     self.assertEqual(report["shared_source_candidate_count"],0)
     self.assertEqual(report["source_status"],"MISSING_COMMON_PRICE_LIST_SOURCE")
     commission=candidate_report(PREVIEW,rooms,[
         row(ic="121132934133"),
         row(room="FAMILY HB",id_ns="104623691679",ic="121132934133",
             id_price="121120516104",prices=[{"ag":"12+,2-11"}])
     ])
     self.assertEqual(commission["shared_source_candidate_count"],1)
     self.assertFalse(commission["bookable"])

 def test_missing_one_room_is_hold_not_price(self):
    rooms=[{"adults":2,"child_ages":[6,12]},{"adults":1,"child_ages":[4]}]
    output=candidate_report(PREVIEW,rooms,[row()])
    self.assertEqual(output["candidate_counts"],[1,0])
    self.assertEqual(output["status"],"MISSING_GROUP_AGE_CANDIDATES")
    self.assertFalse(output["bookable"])

 def test_wrong_date_duration_hotel_and_room_cannot_become_source(self):
    party=[{"adults":2,"child_ages":[6,12]}]
    for wrong in (
      row(tour_date="12.12.2026"),
      row(duration="8"),
      row(id_hotel="999999999999"),
      row(room="OTHER HB"),
      row(isstop="1"),
    ):
        self.assertEqual(candidate_report(PREVIEW,party,[wrong])["candidate_counts"],[0])

 def test_unsupported_and_malformed_queries_fail_closed(self):
    for party in (
      [],
      [{"adults":True,"child_ages":[]}],
      [{"adults":2,"child_ages":[18]}],
      [{"adults":13,"child_ages":[]}],
      [{"adults":2,"child_ages":[0]*11}],
      [{"adults":2,"child_ages":[]}]*6,
    ):
      with self.subTest(party=party), self.assertRaises(ValueError):
        candidate_report(PREVIEW,party,[row()])
    with self.assertRaises(ValueError):
      candidate_report(PREVIEW,[{"adults":2,"child_ages":[]}], [{}]*10001)

if __name__=="__main__":
 unittest.main()
