"""Private Oracle HTTP review API for the JAMAICA hotel directory.

Run behind a trusted HTTPS reverse proxy as an unprivileged service:
    python3 -B -m backend.hotel_reviews_api --db PRIVATE.sqlite \
      --directory destination-directory.json --port 18778

Only bind 127.0.0.1. Reverse proxy must set X-Real-IP from TCP peer and
restrict allowed request origins. Never expose the admin moderation interface
to the public internet; moderation is done with the private CLI.
"""
from __future__ import annotations
import argparse
import ipaddress
import json
import os
import re
import sys
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit

from backend.hotel_reviews_store import HotelReviews,ReviewError

ALLOWED_ORIGIN="https://rosak8-lgtm.github.io"
ROUTE=re.compile(r"^/v1/hotels/(\d{7,20})/reviews$")
MAX_BODY=4096

def make_handler(store):
    class ReviewHandler(BaseHTTPRequestHandler):
        server_version="JamaicaHotelReviews/1.0"
        sys_version=""
        def log_message(self,fmt,*args):
            # Don't log submitted review, IP, URLs or query strings.
            pass
        def _cors(self):
            origin=self.headers.get("Origin","")
            if origin==ALLOWED_ORIGIN:
                self.send_header("Access-Control-Allow-Origin",ALLOWED_ORIGIN)
                self.send_header("Vary","Origin")
                self.send_header("Access-Control-Allow-Methods","GET, POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers","Content-Type")
                self.send_header("Access-Control-Max-Age","300")
        def answer(self,status,data):
            raw=json.dumps(data,ensure_ascii=False,separators=(",",":")).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type","application/json; charset=utf-8")
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self._cors()
            self.send_header("Content-Length",str(len(raw)))
            self.end_headers()
            self.wfile.write(raw)
        def _path(self):
            url=urlsplit(self.path)
            if url.query or url.fragment:
                return None
            return ROUTE.fullmatch(url.path)
        def _source_ip(self):
            remote=self.client_address[0]
            # Only trust the reverse proxy's real-IP header from localhost.
            if remote in ("127.0.0.1","::1"):
                forwarded=self.headers.get("X-Real-IP","").strip()
                try:
                    return str(ipaddress.ip_address(forwarded))
                except ValueError:
                    return remote
            return remote
        def do_OPTIONS(self):
            if not self._path() or self.headers.get("Origin")!=ALLOWED_ORIGIN:
                self.answer(403,{"error":"FORBIDDEN"});return
            self.send_response(204)
            self._cors()
            self.send_header("Content-Length","0")
            self.end_headers()
        def do_GET(self):
            m=self._path()
            if not m:
                self.answer(404,{"error":"NOT_FOUND"});return
            origin=self.headers.get("Origin")
            if origin and origin!=ALLOWED_ORIGIN:
                self.answer(403,{"error":"ORIGIN_NOT_ALLOWED"});return
            try:
                rows=store.public(m.group(1))
                self.answer(200,{"schema":"jamaica.hotel-reviews.v1",
                                 "hotel_id":m.group(1),"reviews":rows})
            except ReviewError:
                self.answer(404,{"error":"HOTEL_NOT_FOUND"})
        def do_POST(self):
            m=self._path()
            if not m:
                self.answer(404,{"error":"NOT_FOUND"});return
            if self.headers.get("Origin")!=ALLOWED_ORIGIN:
                self.answer(403,{"error":"ORIGIN_NOT_ALLOWED"});return
            if self.headers.get("Content-Type","").split(";")[0].lower()!="application/json":
                self.answer(415,{"error":"JSON_REQUIRED"});return
            length=self.headers.get("Content-Length","")
            if not length.isdecimal() or not 1<=int(length)<=MAX_BODY:
                self.answer(413,{"error":"REVIEW_TOO_LARGE"});return
            try:
                body=json.loads(self.rfile.read(int(length)))
                if not isinstance(body,dict) or body.get("hotel_id")!=m.group(1):
                    raise ReviewError("HOTEL_ID_MISMATCH")
                result=store.submit(body,self._source_ip())
            except (ReviewError,UnicodeDecodeError,ValueError):
                self.answer(422,{"error":"INVALID_REVIEW_OR_RATE_LIMIT"});return
            self.answer(202,result)
    return ReviewHandler

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--db",required=True)
    parser.add_argument("--directory",required=True)
    parser.add_argument("--port",type=int,default=18778)
    args=parser.parse_args()
    secret=os.getenv("JAMAICA_REVIEW_HASH_SECRET","")
    if not 1024<=args.port<=65535:
        raise SystemExit("INVALID_LISTEN_PORT")
    store=HotelReviews(Path(args.db),Path(args.directory),secret)
    server=ThreadingHTTPServer(("127.0.0.1",args.port),make_handler(store))
    print("JAMAICA_HOTEL_REVIEWS_PRIVATE_LISTENER=127.0.0.1:"+str(args.port),flush=True)
    server.serve_forever(poll_interval=.5)

if __name__=="__main__":main()
