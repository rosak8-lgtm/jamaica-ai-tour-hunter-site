"""Offline recent-source catalog coverage: no real tours, PII or network."""
import unittest
from datetime import datetime, timedelta, timezone

from scripts.recent_preview_catalog import CACHE_SCHEMA, HISTORICAL_STATUS, combine

NOW=datetime(2026,11,22,20,0,tzinfo=timezone.utc)

def preview(key,country="Турция",price=88000):
    return {
      "id":"p_"+key*24,"hotel_id":"102616490643","hotel":"TEST HOTEL",
      "country":country,"origin":"Иркутск","resort":"Тест",
      "room":"STANDARD","depart_date":"2026-12-12","nights":7,
      "status":"REFERENCE_PRICE_LIST_ONLY",
      "price_reference_rub":price,"price_reference_party":"TWO_ADULTS",
      "quote_verified":False,"availability_verified":False,
      "flight_verified":False,"bookable":False
    }

def feed(rows):
    return {"schema":"jamaica.tour-previews.v1",
            "previews":rows,"total_candidate_previews":len(rows),
            "truncated_to_public_limit":False,
            "indicative_two_adult_rub_count":len(rows),
            "source_scope":{"source_tour_countries":91}}


class Tests(unittest.TestCase):
    def test_other_source_countries_survive_rotation_but_old_price_removed(self):
        f1,h1=combine(feed([preview("a","Таиланд")]),None,now=NOW)
        self.assertEqual(len(f1["previews"]),1)
        f2,h2=combine(feed([preview("b","Вьетнам",45000)]),h1,
                      now=NOW+timedelta(minutes=5))
        self.assertEqual({r["country"] for r in f2["previews"]},
                         {"Вьетнам","Таиланд"})
        old=next(r for r in f2["previews"] if r["country"]=="Таиланд")
        self.assertEqual(old["status"],HISTORICAL_STATUS)
        self.assertIsNone(old["price_reference_rub"])
        self.assertEqual(old["price_reference_party"],"UNVERIFIED")
        self.assertFalse(old["bookable"])
        self.assertEqual(f2["indicative_two_adult_rub_count"],1)
        self.assertEqual(f2["source_scope"]["last_24h_unrechecked_previews"],1)
        self.assertEqual(f2["source_scope"]["last_24h_unrechecked_countries"],1)
        self.assertEqual(f2["source_scope"]["source_tour_countries"],91)
        # Repeated unobserved cycles must not refresh its last-seen timestamp.
        f3,_=combine(feed([preview("c","Индонезия",76000)]),h2,
                     now=NOW+timedelta(hours=24,minutes=1))
        self.assertEqual({r["country"] for r in f3["previews"]},
                         {"Индонезия","Вьетнам"})
        self.assertNotIn("Таиланд",{r["country"] for r in f3["previews"]})

    def test_reobserved_previous_price_is_current_and_overrides_history(self):
        _,cache=combine(feed([preview("a","Таиланд",88000)]),None,now=NOW)
        refreshed,h=combine(feed([preview("a","Таиланд",79000)]),cache,
                            now=NOW+timedelta(minutes=5))
        self.assertEqual(len(refreshed["previews"]),1)
        self.assertEqual(refreshed["previews"][0]["price_reference_rub"],79000)
        self.assertEqual(refreshed["previews"][0]["status"],"REFERENCE_PRICE_LIST_ONLY")
        self.assertEqual(len(h["entries"]),1)

    def test_strict_capacity_favors_live_while_keeping_countries(self):
        initial,cache=combine(feed([preview("a","Таиланд"),
                                    preview("b","Китай")]),None,now=NOW)
        new,h=combine(feed([preview("c","Вьетнам")]),cache,
                      now=NOW+timedelta(minutes=5),max_rows=2)
        self.assertEqual(len(new["previews"]),2)
        self.assertEqual(new["previews"][0]["country"],"Вьетнам")
        self.assertTrue(new["truncated_to_public_limit"])
        self.assertEqual(len(h["entries"]),2)

    def test_expired_past_flights_cannot_reappear_in_catalog(self):
        _,cache=combine(feed([preview("a","Таиланд")]),None,now=NOW)
        cache["entries"][0]["row"]["depart_date"]="2026-11-21"
        next_feed,_=combine(feed([preview("b","Китай")]),cache,
                            now=NOW+timedelta(minutes=5))
        self.assertEqual(len(next_feed["previews"]),1)

    def test_invalid_cache_fails_closed(self):
        _,cache=combine(feed([preview("a")]),None,now=NOW)
        for invalid in (
            {"schema":"wrong","entries":[]},
            {"schema":CACHE_SCHEMA,"entries":[{"foo":True}]},
            {"schema":CACHE_SCHEMA,"entries":[
                cache["entries"][0],cache["entries"][0]]},
            {"schema":CACHE_SCHEMA,"entries":[{
                "row":preview("b"),"last_seen_at_utc":"nope"}]},
            {"schema":CACHE_SCHEMA,"entries":[{
                "row":preview("b"),"last_seen_at_utc":
                (NOW+timedelta(hours=1)).isoformat()}]},
        ):
            with self.subTest(invalid=repr(invalid)[:60]),self.assertRaises(ValueError):
                combine(feed([preview("c")]),invalid,now=NOW+timedelta(minutes=5))
        with self.assertRaises(ValueError):
            combine(feed([preview("a"),preview("a")]),None,now=NOW)

    def test_history_is_never_trusted_as_price_or_booking(self):
        _,cache=combine(feed([preview("a")]),None,now=NOW)
        cache["entries"][0]["row"].update({
            "price_reference_rub":99000,
            "quote_verified":False,
            "availability_verified":False,
            "flight_verified":False,
            "bookable":False,
        })
        f,_=combine(feed([preview("b")]),cache,
                    now=NOW+timedelta(minutes=5))
        prior=next(x for x in f["previews"] if x["id"]==preview("a")["id"])
        for name in ("bookable","quote_verified","availability_verified","flight_verified"):
            self.assertIs(prior[name],False)
        self.assertIsNone(prior["price_reference_rub"])


if __name__=="__main__":
    unittest.main()
