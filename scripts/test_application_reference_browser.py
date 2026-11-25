"""Browser regression with an intercepted synthetic feed, never published."""
import functools
import json
import threading
from datetime import datetime,timedelta,timezone
from http.server import ThreadingHTTPServer,SimpleHTTPRequestHandler
from playwright.sync_api import sync_playwright

class Quiet(SimpleHTTPRequestHandler):
    def log_message(self,*args):pass

def main():
    now=datetime.now(timezone.utc)
    stamp=now.isoformat()
    row={"id":"pg_"+"a"*24,"status":"PEGAS_APPLICATION_PRICE_REFERENCE_ONLY",
         "origin":"Иркутск","country":"Турция","hotel":"V53 TEST HOTEL","room":"DBL",
         "resort":"TEST RESORT","depart_date":(now+timedelta(days=7)).date().isoformat(),
         "nights":7,"price_reference_rub":120000,"price_reference_party":"TWO_ADULTS",
         "price_source":"PEGAS_OPEN_APPLICATION_MANDATORY_FEES_INCLUDED","price_observed_at_utc":stamp,
         "evidence":{"hotel_filter_verified":True,"flight_filter_verified":True,
           "cheapest_eligible_price_clicked":True,"final_price_observed":True,
           "mandatory_fees_included":True,"observed_at_utc":stamp},
         "bookable":False,"quote_verified":False,"availability_verified":False,"flight_verified":False}
    feed={"schema":"jamaica.pegas-reference-catalog.v1","refreshed_at_utc":stamp,
          "bookable":False,"quote_verified":False,"previews":[row]}
    server=ThreadingHTTPServer(("127.0.0.1",0),Quiet)
    threading.Thread(target=server.serve_forever,daemon=True).start()
    base="http://127.0.0.1:"+str(server.server_address[1])+"/"
    try:
        with sync_playwright() as p:
            browser=p.chromium.launch()
            page=browser.new_page()
            page.route("**/application-reference.json",lambda route:route.fulfill(status=200,content_type="application/json",body=json.dumps(feed)))
            page.goto(base,wait_until="domcontentloaded")
            page.locator("#departure").select_option("Иркутск")
            page.locator("#destination").fill("Турция")
            page.locator("#tourSearchForm button[type=submit]").click()
            card=page.locator("#previewCards [data-preview-id='"+row["id"]+"']")
            card.wait_for(timeout=25000)
            assert card.get_attribute("data-visual-verified")=="APPLICATION_PRICE_AND_FILTERS"
            assert "ЛУЧШАЯ ЦЕНА" not in card.inner_text()
            link=card.locator('a[href^="application-detail.html?id="]').first
            link.click()
            page.wait_for_url("**/application-detail.html?id=*")
            page.locator("#details").wait_for(state="visible")
            assert "120" in page.locator("#price").inner_text()
            assert "двух взрослых" in page.locator("#price").inner_text()
            page.goto(base+"application-detail.html?id="+row["id"]+"&adults=2&kids=1&rooms=2%3A6")
            page.locator("#details").wait_for(state="visible")
            assert page.locator("#price").inner_text()=="Требуется отдельный расчёт"
            feed["previews"]=[]
            page.reload()
            page.wait_for_function("document.getElementById('heading').textContent.includes('недоступен')")
            assert page.locator("#details").is_hidden()
            browser.close()
    finally:server.shutdown();server.server_close()
    print("JAMAICA_V53_SECOND_SOURCE_BROWSER_PASS")

if __name__=="__main__":main()
