"""Private loopback inquiry HTTP API; NOT a deployed public sales endpoint.

Use a trusted TLS reverse proxy with request limits and a server-side secret
header. Proxy must overwrite X-Jamaica-Proxy-Key and X-Real-IP, never relay
client values. Deploy only after privacy/legal approval and hosting review.
"""
import argparse
import hmac
import ipaddress
import json
import os
import sqlite3
from http.server import BaseHTTPRequestHandler,ThreadingHTTPServer
from backend.customer_inquiry_catalog import LocalCatalog
from backend.customer_inquiry_store import InquiryStore,InquiryError

ORIGIN="https://rosak8-lgtm.github.io"
ROUTE="/v1/customer-inquiries"
MAX_BODY=4096

def handler(store,proxy_secret):
    if not isinstance(proxy_secret,str) or len(proxy_secret)<32 or not proxy_secret.isascii():
        raise ValueError("PROXY_SECRET_REQUIRED")
    class Handler(BaseHTTPRequestHandler):
        server_version="Jamaica"
        sys_version=""
        def setup(self):
            super().setup();self.connection.settimeout(8)
        def log_message(self,*args):pass
        def trusted(self):
            supplied=self.headers.get("X-Jamaica-Proxy-Key","")
            return (self.client_address[0]=="127.0.0.1" and supplied.isascii() and
                    hmac.compare_digest(supplied,proxy_secret) and self.headers.get("Origin")==ORIGIN)
        def answer(self,status,data=None):
            raw=b"" if data is None else json.dumps(data,separators=(",",":")).encode()
            self.send_response(status)
            self.send_header("Content-Type","application/json")
            self.send_header("Content-Length",str(len(raw)))
            self.send_header("Cache-Control","no-store")
            self.send_header("X-Content-Type-Options","nosniff")
            self.send_header("Connection","close")
            if self.trusted():
                self.send_header("Access-Control-Allow-Origin",ORIGIN)
                self.send_header("Access-Control-Allow-Methods","POST, OPTIONS")
                self.send_header("Access-Control-Allow-Headers","Content-Type")
                self.send_header("Vary","Origin")
            self.end_headers()
            if raw:self.wfile.write(raw)
            self.close_connection=True
        def do_OPTIONS(self):
            if self.path!=ROUTE or not self.trusted():self.answer(403,{"error":"FORBIDDEN"});return
            self.answer(204)
        def do_POST(self):
            if self.path!=ROUTE or not self.trusted():self.answer(403,{"error":"FORBIDDEN"});return
            if self.headers.get("Transfer-Encoding") or self.headers.get("Content-Type","").split(";")[0].lower()!="application/json":
                self.answer(415,{"error":"JSON_REQUIRED"});return
            sizes=self.headers.get_all("Content-Length") or []
            if len(sizes)!=1 or not sizes[0].isdigit() or len(sizes[0])>5 or not 1<=int(sizes[0])<=MAX_BODY:
                self.answer(413,{"error":"INVALID_LENGTH"});return
            try:
                actor=str(ipaddress.ip_address(self.headers.get("X-Real-IP","")))
                raw=self.rfile.read(int(sizes[0]))
                if len(raw)!=int(sizes[0]):raise ValueError("INVALID_LENGTH")
                body=json.loads(raw)
                result=store.submit(body,actor)
            except InquiryError as e:
                code=str(e)
                statuses={"RATE_LIMIT":429,"REQUEST_CONFLICT":409,"TOUR_NOT_CURRENT":409}
                self.answer(statuses.get(code,422),{"error":code});return
            except (ValueError,UnicodeError,RecursionError,TimeoutError):
                self.answer(422,{"error":"INVALID_REQUEST"});return
            except (sqlite3.Error,OSError):
                self.answer(503,{"error":"TEMPORARILY_UNAVAILABLE"});return
            self.answer(202,result)
    return Handler

def main():
    p=argparse.ArgumentParser()
    p.add_argument("--db",required=True)
    p.add_argument("--catalog",required=True)
    p.add_argument("--policy-version",required=True)
    p.add_argument("--retention-days",type=int,required=True)
    p.add_argument("--port",type=int,default=18779)
    p.add_argument("--purge-only",action="store_true")
    args=p.parse_args()
    if os.getenv("JAMAICA_INQUIRY_LEGAL_APPROVED")!="yes":raise SystemExit("LEGAL_APPROVAL_REQUIRED")
    if not 1024<=args.port<=65535:raise SystemExit("INVALID_PORT")
    os.umask(0o077)
    secret=os.environ.get("JAMAICA_INQUIRY_HASH_SECRET","").encode()
    store=InquiryStore(args.db,secret,args.policy_version,LocalCatalog(args.catalog),retention_days=args.retention_days)
    if args.purge_only:
        print("JAMAICA_INQUIRIES_PURGED="+str(store.purge()));return
    server=ThreadingHTTPServer(("127.0.0.1",args.port),handler(store,os.environ.get("JAMAICA_INQUIRY_PROXY_SECRET","")))
    print("JAMAICA_INQUIRY_PRIVATE_LISTENER_READY",flush=True)
    server.serve_forever()

if __name__=="__main__":main()
