import json
import os
import tempfile
import threading
import unittest
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.error import HTTPError
from urllib.request import Request,urlopen

from backend.hotel_reviews_store import HotelReviews,ReviewError
from backend.hotel_reviews_api import make_handler,ALLOWED_ORIGIN

HOTEL="102610001486"
NAME="Путешественник"
TEXT="Мы действительно проживали в гостинице, понравилось расположение и чистота номера."
def review(**updates):
    data={"hotel_id":HOTEL,"display_name":NAME,"rating":4,"text":TEXT,
          "visit_month":"2025-11","consent":True,"website":""}
    data.update(updates)
    return data

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root=Path(self.tmp.name)
        self.catalog=root/"destination-directory.json"
        self.catalog.write_text(json.dumps({
          "schema":"jamaica.destination-directory.v1",
          "hotels":[{"id":HOTEL,"name":"Test Actual Hotel","country":"Таиланд"}],
          "countries":[{"name":"Таиланд"}]}),encoding="utf-8")
        self.db=root/"reviews.sqlite"
        self.store=HotelReviews(self.db,self.catalog,"0123456789abcdef"*4)
    def test_private_database_permissions(self):
        self.assertEqual(self.db.stat().st_mode&0o077,0)
    def test_review_stays_pending_until_operator_moderation(self):
        result=self.store.submit(review(),"203.0.113.12")
        self.assertEqual(result["status"],"PENDING_MODERATION")
        self.assertEqual(self.store.public(HOTEL),[])
        pending=self.store.pending()
        self.assertEqual(len(pending),1)
        self.assertTrue(self.store.moderate(pending[0]["id"],True))
        got=self.store.public(HOTEL)
        self.assertEqual(len(got),1)
        self.assertEqual(got[0]["rating"],4)
        self.assertFalse(got[0]["stay_verified"])
        self.assertEqual(got[0]["display_name"],NAME)
        self.assertNotIn("actor_digest",got[0])
    def test_owner_can_reject_review(self):
        self.store.submit(review(),"203.0.113.15")
        pending=self.store.pending()[0]["id"]
        self.assertTrue(self.store.moderate(pending,False))
        self.assertEqual(self.store.public(HOTEL),[])
        self.assertFalse(self.store.moderate(pending,True))
    def test_unknown_hotel_cannot_receive_fabricated_reviews(self):
        with self.assertRaises(ReviewError):
            self.store.submit(review(hotel_id="100000000000"),"203.0.113.15")
        with self.assertRaises(ReviewError):
            self.store.public("100000000000")
    def test_spam_prevented_for_actor_every_day(self):
        for _ in range(3):
            self.store.submit(review(),"203.0.113.25")
        with self.assertRaises(ReviewError):
            self.store.submit(review(),"203.0.113.25")
        self.store.submit(review(),"203.0.113.26")
    def test_reject_unconsented_html_links_or_honeypot(self):
        for change in (
            {"consent":False},{"website":"spam.example"},
            {"text":"<script>alert(1)</script>"*4},
            {"text":"https://malware.example "+"word "*20},
            {"rating":True},{"rating":0},{"rating":6},
            {"visit_month":"2999-01"},
            {"display_name":"A"},
        ):
            with self.assertRaises(ReviewError):
                self.store.submit(review(**change),"203.0.113.30")
        self.assertEqual(self.store.pending(),[])
    def test_ip_does_not_appear_in_disk_record(self):
        self.store.submit(review(),"203.0.113.141")
        with self.store._db() as db:
            item=db.execute("SELECT * FROM hotel_reviews").fetchone()
        self.assertNotIn("203.0.113.141",str(dict(item)))
        self.assertNotIn("203.0.113.141",str(self.store.public(HOTEL)))
    def test_rest_api_cors_submission_and_moderated_read(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.store))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        route=f"http://127.0.0.1:{server.server_port}/v1/hotels/{HOTEL}/reviews"
        req=Request(route,data=json.dumps(review()).encode("utf-8"),method="POST",
                    headers={"Origin":ALLOWED_ORIGIN,"Content-Type":"application/json",
                             "X-Real-IP":"203.0.113.66"})
        with urlopen(req,timeout=3) as response:
            self.assertEqual(response.status,202)
            self.assertEqual(response.headers["Access-Control-Allow-Origin"],ALLOWED_ORIGIN)
        with urlopen(Request(route,headers={"Origin":ALLOWED_ORIGIN}),timeout=3) as resp:
            data=json.load(resp)
            self.assertEqual(data["reviews"],[])
        id_=self.store.pending()[0]["id"]
        self.store.moderate(id_,True)
        with urlopen(route,timeout=3) as resp:
            self.assertEqual(len(json.load(resp)["reviews"]),1)
    def test_rest_api_does_not_accept_foreign_origin(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),make_handler(self.store))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        self.addCleanup(server.server_close)
        self.addCleanup(server.shutdown)
        route=f"http://127.0.0.1:{server.server_port}/v1/hotels/{HOTEL}/reviews"
        req=Request(route,data=json.dumps(review()).encode(),method="POST",
                    headers={"Origin":"https://evil.example","Content-Type":"application/json"})
        with self.assertRaises(HTTPError) as exception:
            urlopen(req,timeout=3)
        self.assertEqual(exception.exception.code,403)
        self.assertEqual(len(self.store.pending()),0)

if __name__=="__main__": unittest.main()
