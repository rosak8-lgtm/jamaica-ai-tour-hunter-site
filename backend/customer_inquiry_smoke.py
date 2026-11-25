"""Local acceptance with an actual fresh catalog row and synthetic contact.

No production database, no supplier calls, no public endpoint, no messages,
no booking. Test database and random secrets exist only during this run.
"""
import argparse
import json
import secrets
import tempfile
import threading
from datetime import datetime,timezone
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request,build_opener,ProxyHandler
from urllib.error import HTTPError
from backend.customer_inquiry_api import handler,ORIGIN,ROUTE
from backend.customer_inquiry_catalog import LocalCatalog,read
from backend.customer_inquiry_store import InquiryStore,ID
from backend.customer_inquiry_owner import summarize

def select_sample(root,resolver,now):
    for prefix,name,limit in (("p_","tour-previews.json",24*1024*1024),
                              ("pg_","application-reference.json",12*1024*1024)):
        try:
            feed,_=read(root/name,limit)
            rows=feed.get("previews")
            if not isinstance(rows,list) or len(rows)>8000:continue
            for row in rows[:8]:
                if not isinstance(row,dict):continue
                pid=row.get("id")
                if isinstance(pid,str) and pid.startswith(prefix) and ID.fullmatch(pid) and resolver(pid,now):
                    return pid
        except (OSError,ValueError,TypeError,AttributeError,RecursionError):
            continue
    return None

def smoke(root):
    root=Path(root)
    resolver=LocalCatalog(root)
    pid=select_sample(root,resolver,datetime.now(timezone.utc))
    result={"classification":"LOCAL_SYNTHETIC_INQUIRY_NOT_PRODUCTION",
            "sample_found":bool(pid),"public_endpoint_tested":False,
            "supplier_calls":0,"real_customer_contacts":0,"booking_created":False,
            "payment_created":False,"temporary_database_only":True}
    if pid is None:return {**result,"status":"HOLD_NO_FRESH_SAMPLE"}
    secret=secrets.token_hex(32)
    with tempfile.TemporaryDirectory(prefix="jamaica-inquiry-smoke-") as folder:
        db=Path(folder).resolve()/"smoke.sqlite"
        store=InquiryStore(db,secrets.token_bytes(32),"smoke-v1",resolver,retention_days=1)
        server=ThreadingHTTPServer(("127.0.0.1",0),handler(store,secret))
        thread=threading.Thread(target=server.serve_forever,daemon=True)
        thread.start()
        try:
            url="http://127.0.0.1:"+str(server.server_address[1])+ROUTE
            opener=build_opener(ProxyHandler({}))
            headers={"Origin":ORIGIN,"Content-Type":"application/json","X-Real-IP":"192.0.2.1",
                     "X-Jamaica-Proxy-Key":secret}
            body={"request_id":secrets.token_hex(16),"preview_id":pid,
                  "rooms":[{"adults":2,"child_ages":[6]},{"adults":1,"child_ages":[]}],
                  "contact":{"kind":"email","value":"synthetic@example.invalid"},
                  "consent":True,"policy_version":"smoke-v1"}
            def post(payload,head):
                req=Request(url,data=json.dumps(payload).encode(),headers=head,method="POST")
                try:
                    with opener.open(req,timeout=10) as response:
                        return response.status,json.load(response)
                except HTTPError as e:
                    with e:return e.code,json.load(e)
            denied,_=post(body,{k:v for k,v in headers.items() if k!="X-Jamaica-Proxy-Key"})
            bad_origin,_=post(body,{**headers,"Origin":"https://example.invalid"})
            missing_consent,_=post({**body,"consent":False},headers)
            status,receipt=post(body,headers)
            if status==409:return {**result,"status":"HOLD_SAMPLE_CHANGED_OR_EXPIRED"}
            if status!=202 or receipt.get("status")!="INQUIRY_RECEIVED":
                return {**result,"status":"FAIL_LOCAL_ACCEPTANCE"}
            retry_status,retry_receipt=post(body,headers)
            conflict,_=post({**body,"rooms":[{"adults":2,"child_ages":[]}]},headers)
            owner=summarize(db,1,datetime.now(timezone.utc))
            checks={"missing_proxy_secret_rejected":denied==403,
                    "wrong_origin_rejected":bad_origin==403,
                    "missing_consent_rejected":missing_consent==422,
                    "exact_tour_accepted":status==202,
                    "no_booking_or_payment":receipt.get("booked") is False and receipt.get("payment_required") is False,
                    "idempotency":retry_status==202 and retry_receipt==receipt,
                    "changed_body_conflict":conflict==409,
                    "exactly_one_private_record":owner["retained_count"]==1,
                    "owner_summary_no_contact":"synthetic@example.invalid" not in json.dumps(owner)}
            return {**result,"checks":checks,"status":"PASS_LOCAL_SYNTHETIC_INQUIRY" if all(checks.values()) else "FAIL_LOCAL_ACCEPTANCE"}
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=10)

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--catalog",required=True,type=Path)
    a=p.parse_args()
    try:result=smoke(a.catalog)
    except (OSError,ValueError,TypeError,KeyError,RuntimeError):
        raise SystemExit("JAMAICA_LOCAL_INQUIRY_SMOKE_HOLD")
    print(json.dumps(result,ensure_ascii=False,indent=2))
    return 0 if result["status"]=="PASS_LOCAL_SYNTHETIC_INQUIRY" else 2
if __name__=="__main__":raise SystemExit(main())
