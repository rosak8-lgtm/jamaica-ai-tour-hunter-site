"""All private source crosswalk fixtures are artificial (no live API/PII)."""
import unittest

from backend.bg_private_source_crosswalk import private_source_candidates

P={
    "id":"p_"+"f"*24,"hotel_id":"102616490643",
    "room":"STANDARD HB","depart_date":"2026-12-11",
    "nights":7,"country":"Вьетнам","origin":"Иркутск"
}
ROOMS=[{"adults":2,"child_ages":[6,12]},
       {"adults":1,"child_ages":[4]}]


def price_row(room="STANDARD HB", ns="104623691678", ag=None, **other):
    return {
      "id_hotel":P["hotel_id"],"tour_date":"11.12.2026",
      "duration":"7","dt":"11.12.2026","o_duration":"7",
      "room":room,"id_ns":ns,"sr":"PRIVATE_SYNTHETIC_FLIGHT_SR",
      "id_price":"121120516103",
      "_jamaica_private_prx":"104499999900000025",
      "prices":[{"ag":ag if ag is not None else
                 "[14-99][14-99][2-11][12-17]"}],
      **other
    }


class Tests(unittest.TestCase):
    def test_builds_exact_two_room_candidates_from_same_private_source(self):
        rows=[price_row(),price_row(room="FAMILY HB",ns="104623691679",
                                    ag="12+,2-11")]
        plans=private_source_candidates(P,ROOMS,rows)
        self.assertEqual(len(plans),1)
        p=plans[0]
        self.assertEqual(len(p.groups),2)
        self.assertEqual(p.groups[0][0].roommeal_id,"104623691678")
        self.assertEqual(p.groups[1][0].roommeal_id,"104623691679")
        self.assertEqual(p.groups[1][0].age_marker,"12+,2-11")
        self.assertEqual(p.template_id,"121120516103")
        self.assertIsNone(p.commission_id)
        for key in ("quote_verified","availability_verified",
                    "flight_verified","bookable"):
            self.assertIs(getattr(p,key),False)
        self.assertEqual(p.status,"POTENTIAL_ONLY_NOT_QUOTED")
        self.assertNotIn("104499999900000025",repr(plans))
        self.assertNotIn("PRIVATE_SYNTHETIC",repr(p.groups[0][0]))

    def test_different_prx_never_builds_grouped_plan(self):
        rows=[price_row(),price_row(room="FAMILY HB",ns="104623691679",
                       ag="12+,2-11",
                       _jamaica_private_prx="104499999900000026")]
        self.assertEqual(private_source_candidates(P,ROOMS,rows),())

    def test_missing_room_or_incompatible_ages_is_hold(self):
        self.assertEqual(private_source_candidates(P,ROOMS,[price_row()]),())
        self.assertEqual(private_source_candidates(P,ROOMS,[
            price_row(),price_row(room="FAMILY HB",ns="104623691679",
                                  ag="12+,12+")]),())

    def test_fail_closed_split_stay_stop_and_wrong_room(self):
        rows=[price_row(),price_row(room="FAMILY HB",ns="104623691679",
                                    ag="12+,2-11")]
        for key,value in (("id_ns_b","104625776787"),("o_duration","6"),
                          ("dt","16.12.2026"),("stop","1"),("isstop","1")):
            bad=[rows[0],{**rows[1],key:value}]
            with self.subTest(key=key):
                self.assertEqual(private_source_candidates(P,ROOMS,bad),())
        with self.assertRaises(ValueError):
            private_source_candidates(P,ROOMS,rows,max_plans=0)
        with self.assertRaises(ValueError):
            private_source_candidates(P,ROOMS,rows,max_plans=True)

    def test_next_day_primary_accommodation_is_source_bound(self):
        rows=[price_row(dt="12.12.2026"),
              price_row(room="FAMILY HB",ns="104623691679",
                        ag="12+,2-11",dt="12.12.2026")]
        plans=private_source_candidates(P,ROOMS,rows)
        self.assertEqual(len(plans),1)
        self.assertEqual(plans[0].groups[0][0].start_date,"2026-12-12")
        self.assertEqual(plans[0].groups[1][0].start_date,"2026-12-12")
        self.assertFalse(plans[0].quote_verified)
        self.assertFalse(plans[0].bookable)
        # Both rooms must be tied to the same accommodation start date.
        rows[1]["dt"]="13.12.2026"
        self.assertEqual(private_source_candidates(P,ROOMS,rows),())

    def test_commission_id_never_becomes_template(self):
        p=private_source_candidates(P,ROOMS,[
            price_row(ic="121132934133"),
            price_row(room="FAMILY HB",ns="104623691679",ag="12+,2-11",
                      ic="121132934133")])[0]
        self.assertEqual(p.commission_id,"121132934133")
        self.assertIsNone(p.template_id)
        self.assertFalse(p.bookable)

    def test_first_room_pinned_and_no_reused_tariff_age_slot(self):
        rows=[price_row(room="OTHER HB"),
              price_row(room="FAMILY HB",ns="104623691679",ag="12+,2-11")]
        self.assertEqual(private_source_candidates(P,ROOMS,rows),())
        rows[0]["room"]="STANDARD HB"
        rows[0]["prices"]=[{"ag":"14+,2-11"}]
        self.assertEqual(private_source_candidates(P,ROOMS,rows),())


if __name__=="__main__":
    unittest.main()
