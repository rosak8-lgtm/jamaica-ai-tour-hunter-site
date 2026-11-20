#!/usr/bin/env python3
"""JAMAICA real Chromium navigation smoke test; safe localhost only.

Requires Python Playwright and downloaded Chromium; no Node or public network.
GET-only static files; does not contact any supplier API or submit payments.
"""
from __future__ import annotations

import functools
import http.server
import json
import threading
from pathlib import Path

ROOT=Path(__file__).resolve().parent.parent

class QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self,*args,**kwargs):
        pass

def ensure(cond,message):
    if not cond:raise AssertionError(message)

def main():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("JAMAICA_BROWSER_SMOKE_SKIP=PYTHON_PLAYWRIGHT_NOT_INSTALLED")
        return 3
    preview=json.loads((ROOT/"tour-previews.json").read_text(encoding="utf-8"))
    rows=preview.get("previews",[])
    ensure(isinstance(rows,list) and len(rows)>0,"EMPTY_PREVIEWS")
    counts={}
    for row in rows:
        counts[row["country"]]=counts.get(row["country"],0)+1
    ensure(len(counts)>=3,"NOT_ENOUGH_COUNTRIES")
    if "Турция" not in counts:
        print("JAMAICA_BROWSER_SMOKE_HOLD=NO_TURKEY_IN_FEED")
        return 2

    handler=functools.partial(QuietHandler,directory=str(ROOT))
    server=http.server.ThreadingHTTPServer(("127.0.0.1",0),handler)
    thread=threading.Thread(target=server.serve_forever,daemon=True)
    thread.start()
    base="http://127.0.0.1:"+str(server.server_port)+"/"
    try:
        with sync_playwright() as playwright:
            try:
                browser=playwright.chromium.launch(headless=True,args=["--no-sandbox"])
            except Exception as exc:
                print("JAMAICA_BROWSER_SMOKE_HOLD=CHROMIUM_NOT_AVAILABLE")
                return 2
            try:
                page=browser.new_page(viewport={"width":1365,"height":900})
                errors=[]
                page.on("pageerror",lambda e:errors.append(str(e)[:220]))
                page.goto(base,wait_until="domcontentloaded")
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=25000)
                first30=page.locator("#previewCards article.offerCard h3").all_text_contents()
                shown={text.split(" · ")[0] for text in first30}
                ensure(len(shown)>=3,"FIRST_PAGE_DOES_NOT_SHOW_MULTIPLE_COUNTRIES")
                page.locator("#destination").fill("Турция")
                page.locator("#tourSearchForm button[type=submit]").click()
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=15000)
                visible=page.locator("#previewCards article.offerCard h3").all_text_contents()
                ensure(visible and all(text.startswith("Турция · ") for text in visible),
                       "COUNTRY_FILTER_DID_NOT_REFRESH_PREVIEWS")
                link=page.locator('#previewCards article.offerCard a[href^="preview.html?id="]').first
                href=link.get_attribute("href")
                ensure(href and href.startswith("preview.html?id=p_"),"NO_SELECTED_TOUR_LINK")
                link.click()
                page.wait_for_url("**/preview.html?id=*",timeout=20000)
                page.locator("#facts .fact").first.wait_for(timeout=15000)
                heading=page.locator("#heading").inner_text()
                ensure("Турция" in heading,"SELECTED_COUNTRY_LOST_IN_DETAILS")
                booking=page.locator("#bookingStatus").inner_text().lower()
                ensure(any(term in booking for term in ("оплат","подтверд","расчёт","договор")),
                       "BOOKING_SAFETY_MESSAGE_NOT_VISIBLE")
                ensure("тур забронирован" not in booking,
                       "UNVERIFIED_TOUR_CLAIMS_BOOKED")
                quote_link=page.locator("#quoteLink")
                ensure(quote_link.count()==1 and
                       (quote_link.get_attribute("href") or "").startswith("quote.html?preview=p_"),
                       "NO_QUOTE_AND_CONTRACT_HANDOFF")
                ensure(not page.locator("#providerFrame").count(),"UNAPPROVED_PAYMENT_IFRAME")
                quote_link.click()
                page.wait_for_url("**/quote.html?preview=*",timeout=20000)
                page.locator("#hotelTitle").wait_for(timeout=15000)
                ensure("Турция" in page.locator("#hotelTitle").inner_text(),
                       "SELECTED_COUNTRY_LOST_ON_QUOTE_PAGE")
                ensure(page.locator("#checkQuote").is_disabled(),
                       "UNCONFIGURED_REAL_PAYMENT_WAS_UNEXPECTEDLY_ENABLED")
                ensure("недоступ" in page.locator("#quoteNotice").inner_text().lower(),
                       "UNCONFIGURED_QUOTE_SAFETY_GATE_NOT_VISIBLE")
                page.goto(base+"account.html",wait_until="domcontentloaded")
                page.locator("#orderMessage").wait_for(timeout=15000)
                page.wait_for_function(
                    "()=>document.getElementById('orderMessage').textContent.includes('недоступны')",
                    timeout=10000
                )
                ensure(not page.locator("#payment iframe:visible").count(),
                       "UNCONFIGURED_ACCOUNT_PAYMENT_ENABLED")
                ensure(not errors,"BROWSER_SCRIPT_ERRORS: "+"; ".join(errors[:3]))
                print("JAMAICA_CHROMIUM_CUSTOMER_JOURNEY_PASS")
                print("SELECTED_TOUR_TO_QUOTE=PASS")
                print("UNCONFIGURED_ACCOUNT_PAYMENT=BLOCKED")
                print("DIFFERENT_COUNTRIES_ON_FIRST_PAGE="+str(len(shown)))
                print("FILTERED_COUNTRY=Турция")
                print("DETAILED_TOUR_LINK=PASS")
                print("PAYMENT_PROTECTED=YES")
                return 0
            finally:
                browser.close()
    finally:
        server.shutdown()
        server.server_close()

if __name__=="__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print("JAMAICA_BROWSER_SMOKE_HOLD="+type(exc).__name__+":"+str(exc)[:180])
        raise SystemExit(2)
