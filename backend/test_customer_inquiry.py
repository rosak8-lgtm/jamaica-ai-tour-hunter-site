import json
import os
import tempfile
import unittest
import threading
from datetime import datetime,timedelta,timezone
from pathlib import Path
from http.server import ThreadingHTTPServer
from urllib.request import Request,urlopen
from urllib.error import HTTPError
from backend.customer_inquiry_store import InquiryStore,InquiryError
from backend.customer_inquiry_catalog import LocalCatalog
from backend.customer_inquiry_api import handler,ORIGIN,ROUTE
from backend.customer_inquiry_owner import summarize,inspect_ticket

class Tests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        self.root=Path(self.tmp.name).resolve()
        self.now=datetime.now(timezone.utc)
        self.stamp=self.now.isoformat()
        self.pid="p_"+"a"*24
        self.row={"id":self.pid,"origin":"Иркутск","country":"Китай","hotel":"TEST","room":"DBL","depart_date":(self.now+timedelta(days=7)).date().isoformat(),"nights":7,"status":"REFERENCE_PRICE_LIST_ONLY","price_source":"BG_EXACT_SELECTED_GREEN_BROWSER","price_reference_party":"TWO_ADULTS","price_reference_rub":100000,"price_observed_at_utc":self.stamp,"bookable":False,"quote_verified":False,"availability_verified":False,"flight_verified":False}
        self.proof={"preview_id":self.pid,"route_best_price_seen":True,"both_green_planes_seen":True,"observed_at_utc":self.stamp}
        self.feed={"schema":"jamaica.tour-previews.v1","bookable":False,"quote_verified":False,"availability_verified":False,"total_published_previews":1,"previews":[self.row]}
        self.proofs={"schema":"jamaica.visual-selection.v1","bookable":False,"quote_verified":False,"availability_verified":False,"entries":[self.proof]}
        self.write()
        self.store=InquiryStore(self.root/"inquiries.sqlite",b"x"*32,"test-v1",LocalCatalog(self.root))
        self.body={"request_id":"a"*32,"preview_id":self.pid,"rooms":[{"adults":2,"child_ages":[6]}],"contact":{"kind":"email","value":"test@example.com"},"consent":True,"policy_version":"test-v1"}
    def tearDown(self):self.tmp.cleanup()
    def write_private_json(self,name,value):
        path=self.root/name
        fd=os.open(path,os.O_WRONLY|os.O_CREAT|os.O_TRUNC|os.O_NOFOLLOW,0o600)
        with os.fdopen(fd,"w",encoding="utf-8") as stream:
            os.fchmod(stream.fileno(),0o600)
            json.dump(value,stream)
    def write(self):
        for name,value in (("tour-previews.json",self.feed),("tour-visual-evidence.json",self.proofs)):
            self.write_private_json(name,value)
    def test_receive_once_and_no_booking(self):
        a=self.store.submit(self.body,"actor",self.now)
        self.assertEqual(a,self.store.submit(self.body,"actor",self.now))
        self.assertEqual(a["status"],"INQUIRY_RECEIVED")
        self.assertFalse(a["booked"]);self.assertFalse(a["payment_required"])
        with self.store.db() as db:self.assertEqual(db.execute("SELECT COUNT(*) FROM inquiries").fetchone()[0],1)
        with self.assertRaises(InquiryError):self.store.submit({**self.body,"rooms":[{"adults":3,"child_ages":[]}]},"actor",self.now)
    def test_stale_missing_mismatched(self):
        for patch in ({"both_green_planes_seen":False},{"observed_at_utc":(self.now-timedelta(minutes=16)).isoformat()},{"observed_at_utc":(self.now-timedelta(seconds=1)).isoformat()}):
            self.proofs["entries"]=[{**self.proof,**patch}];self.write()
            with self.assertRaises(InquiryError):self.store.submit(self.body,"actor",self.now)
        self.proofs["entries"]=[];self.write()
        with self.assertRaises(InquiryError):self.store.submit(self.body,"actor",self.now)
    def test_invalid_and_no_extra_data(self):
        for patch in ({"consent":False},{"policy_version":"wrong"},{"passport":"1234"},{"rooms":[{"adults":True,"child_ages":[]}]},{"contact":{"kind":"email","value":"x\ny@example.com"}}):
            with self.assertRaises(InquiryError):self.store.submit({**self.body,**patch},"actor",self.now)
    def test_rate_limit_and_retention(self):
        for i in range(5):self.store.submit({**self.body,"request_id":format(i,"032x")},"actor",self.now)
        with self.assertRaises(InquiryError):self.store.submit({**self.body,"request_id":"f"*32},"actor",self.now)
        self.assertEqual(self.store.purge(self.now+timedelta(days=31)),5)
    def test_private_modes(self):
        self.assertEqual((self.root/"inquiries.sqlite").stat().st_mode&0o777,0o600)
        (self.root/"inquiries.sqlite").chmod(0o644)
        with self.assertRaises(InquiryError):InquiryStore(self.root/"inquiries.sqlite",b"x"*32,"test-v1",LocalCatalog(self.root))
    def test_group_writable_catalog_rejected(self):
        path=self.root/"tour-previews.json"
        path.chmod(0o664)
        with self.assertRaisesRegex(InquiryError,"TOUR_NOT_CURRENT"):
            self.store.submit(self.body,"actor",self.now)
        self.write()
        self.assertEqual(path.stat().st_mode&0o777,0o600)
        self.assertEqual(self.store.submit(self.body,"actor",self.now)["status"],"INQUIRY_RECEIVED")
    def test_second_source(self):
        pid="pg_"+"b"*24
        row={**self.row,"id":pid,"status":"PEGAS_APPLICATION_PRICE_REFERENCE_ONLY","price_source":"PEGAS_OPEN_APPLICATION_MANDATORY_FEES_INCLUDED","evidence":{"hotel_filter_verified":True,"flight_filter_verified":True,"cheapest_eligible_price_clicked":True,"final_price_observed":True,"mandatory_fees_included":True,"observed_at_utc":self.stamp}}
        feed={"schema":"jamaica.pegas-reference-catalog.v1","bookable":False,"quote_verified":False,"refreshed_at_utc":self.stamp,"previews":[row]}
        self.write_private_json("application-reference.json",feed)
        self.assertEqual(self.store.submit({**self.body,"preview_id":pid},"actor",self.now)["status"],"INQUIRY_RECEIVED")
        row["evidence"]["mandatory_fees_included"]=False
        self.write_private_json("application-reference.json",feed)
        with self.assertRaises(InquiryError):self.store.submit({**self.body,"request_id":"b"*32,"preview_id":pid},"actor",self.now)
    def test_owner_summary_and_explicit_ticket(self):
        receipt=self.store.submit(self.body,"actor",self.now)
        path=self.root/"inquiries.sqlite"
        report=summarize(path,30,self.now)
        self.assertEqual(report["retained_count"],1)
        self.assertEqual(report["entries"][0]["ticket"],receipt["ticket"])
        self.assertNotIn("test@example.com",json.dumps(report))
        self.assertNotIn("contact",report["entries"][0])
        detail=inspect_ticket(path,30,self.now,receipt["ticket"])
        self.assertEqual(detail["contact"]["value"],"test@example.com")
        self.assertEqual(detail["rooms"],self.body["rooms"])
        self.assertEqual(detail["itinerary"]["id"],self.pid)
    def test_owner_retention_and_file_permissions(self):
        receipt=self.store.submit(self.body,"actor",self.now)
        path=self.root/"inquiries.sqlite"
        later=self.now+timedelta(days=31)
        self.assertEqual(summarize(path,30,later)["retained_count"],0)
        with self.assertRaises(InquiryError):inspect_ticket(path,30,later,receipt["ticket"])
        with self.assertRaises(InquiryError):inspect_ticket(path,30,self.now,"bad-ticket")
        path.chmod(0o644)
        with self.assertRaises(InquiryError):summarize(path,30,self.now)
    def test_owner_rejects_symlink(self):
        path=self.root/"alias.sqlite"
        path.symlink_to(self.root/"inquiries.sqlite")
        with self.assertRaises(InquiryError):summarize(path,30,self.now)
    def test_http_loopback(self):
        server=ThreadingHTTPServer(("127.0.0.1",0),handler(self.store,"s"*32))
        th=threading.Thread(target=server.serve_forever,daemon=True);th.start()
        try:
            url="http://127.0.0.1:"+str(server.server_address[1])+ROUTE
            headers={"Origin":ORIGIN,"Content-Type":"application/json","X-Real-IP":"192.0.2.1"}
            data=json.dumps(self.body).encode()
            with self.assertRaises(HTTPError) as e:urlopen(Request(url,data=data,headers=headers),timeout=5)
            self.assertEqual(e.exception.code,403)
            headers["X-Jamaica-Proxy-Key"]="s"*32
            with urlopen(Request(url,data=data,headers=headers),timeout=5) as r:
                self.assertEqual(r.status,202)
                result=json.load(r)
                self.assertEqual(set(result),{"status","ticket","booked","payment_required"})
                self.assertFalse(result["booked"])
                self.assertEqual(r.headers["Cache-Control"],"no-store")
            with self.assertRaises(HTTPError) as e:urlopen(Request(url,data=data,headers={**headers,"Origin":"https://example.com"}),timeout=5)
            self.assertEqual(e.exception.code,403)
        finally:server.shutdown();server.server_close();th.join()

if __name__=="__main__":unittest.main()
