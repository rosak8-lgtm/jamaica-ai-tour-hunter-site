import copy
import unittest
from datetime import datetime,timedelta,timezone
from backend.bg_route_first_visual_gate import route_first_pair_matches

def bundle(preview,now=None):
    now=now or datetime.now(timezone.utc)
    def dt(seconds):
        return (now-timedelta(seconds=seconds)).isoformat()
    shared={
        "source_price_list_id":"121132934133",
        "source_route_id":"100410000051",
        "browser_session_digest":"a"*64,
    }
    route={**shared,
        "source":"BG_OFFICIAL_BROWSER_ROUTE",
        "badge_text":"ЛУЧШАЯ ЦЕНА",
        "badge_scope":"SELECTED_ROUTE_ROW",
        "route_clicked":True,
        "page_url":"https://www.bgoperator.ru/price.shtml?flt=100410000051",
        "origin_city_id":"100510397223",
        "origin":preview["origin"],
        "country":preview["country"],
        "depart_date":preview["depart_date"],
        "badge_seen_at_utc":dt(60),
        "route_clicked_at_utc":dt(45),
    }
    flight={**shared,
        "source":"BG_OFFICIAL_BROWSER_SELECTED_DETAIL",
        "out_green":True,"back_green":True,
        "stop_sale":False,
        "origin":preview["origin"],
        "country":preview["country"],
        "depart_date":preview["depart_date"],
        "hotel_id":preview["hotel_id"],
        "room":preview["room"],
        "nights":preview["nights"],
        "source_preview_id":preview["id"],
        "flight_checked_at_utc":dt(20),
    }
    return route,flight

def sample():
    return {"id":"p_"+"e"*24,"country":"Таиланд","origin":"Иркутск",
            "hotel_id":"102610001486","room":"DBL HB","nights":7,
            "depart_date":"2026-12-12","bookable":False,
            "quote_verified":False}

class Tests(unittest.TestCase):
    def test_valid_official_route_first_two_green_candidate(self):
        p=sample();route,flight=bundle(p)
        self.assertTrue(route_first_pair_matches(route,flight,p))
    def test_empty_source_cannot_invent_badge_and_green(self):
        p=sample();route,flight=bundle(p)
        for a,b,c in ((None,flight,p),(route,None,p),
                      (route,flight,None)):
            self.assertFalse(route_first_pair_matches(a,b,c))
        self.assertFalse(route_first_pair_matches(
            route,flight,{**p,"bookable":True}))
    def test_route_badge_must_be_exact_in_selected_route_row(self):
        p=sample();route,flight=bundle(p)
        for key,value in (("badge_text","Лучшие предложения!"),
                          ("badge_text","ЛУЧШАЯ ЦЕНА НА 6 НОЧЕЙ!"),
                          ("badge_scope","PAGE_HEADER"),("route_clicked",False),
                          ("origin_city_id","MOSCOW"),("country","Вьетнам"),
                          ("depart_date","2027-01-01"),("page_url","http://www.bgoperator.ru/price.shtml"),
                          ("page_url","https://example.org/price.shtml"),
                          ("page_url","https://www.bgoperator.ru@attacker.example/price.shtml")):
            with self.subTest(key=key,value=value):
                self.assertFalse(route_first_pair_matches(
                    {**route,key:value},flight,p))
    def test_two_flights_must_match_exact_preview_and_same_source(self):
        p=sample();route,flight=bundle(p)
        for key,value in (("out_green",False),("back_green",False),
                          ("stop_sale",None),("source_price_list_id","121132934135"),
                          ("source_route_id","100410000052"),
                          ("browser_session_digest","b"*64),
                          ("origin","Москва"),("country","Вьетнам"),
                          ("depart_date","2026-12-13"),
                          ("hotel_id","100000999999"),("room","SOMETHING ELSE"),
                          ("nights",8),("source_preview_id","p_"+"d"*24)):
            with self.subTest(key=key):
                self.assertFalse(route_first_pair_matches(
                    route,{**flight,key:value},p))
    def test_click_must_precede_both_green_and_still_be_fresh(self):
        p=sample()
        at=datetime.now(timezone.utc)
        route,flight=bundle(p,now=at)
        self.assertFalse(route_first_pair_matches(
            {**route,"route_clicked_at_utc":
                (at+timedelta(minutes=1)).isoformat()},flight,p,now=at))
        self.assertFalse(route_first_pair_matches(
            route,{**flight,"flight_checked_at_utc":
                (at-timedelta(minutes=16)).isoformat()},p,now=at))
        self.assertFalse(route_first_pair_matches(
            route,flight,p,now=at+timedelta(minutes=17)))
        self.assertFalse(route_first_pair_matches(
            {**route,"badge_seen_at_utc":"2026-11-23T12:00:00"},
            flight,p,now=at))

if __name__=="__main__":unittest.main()
