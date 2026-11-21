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

                # The traveler party from search must NEVER silently become 2 adults.
                page.goto(base,wait_until="domcontentloaded")
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=25000)
                page.locator("#destination").fill("Турция")
                page.locator("#adults").fill("1")
                page.locator("#kids").fill("1")
                page.locator("#tourSearchForm button[type=submit]").click()
                custom=page.locator('#previewCards article.offerCard a[href^="preview.html?id="]').first
                custom.wait_for(timeout=15000)
                ensure("&adults=1&kids=1" in custom.get_attribute("href"),
                       "TRAVELER_COUNT_LOST_FROM_SEARCH")
                custom.click()
                page.wait_for_url("**/preview.html?id=*",timeout=20000)
                page.locator("#facts .fact").first.wait_for(timeout=15000)
                ensure("1 взрослый, 1 ребёнок" in page.locator("#facts").inner_text(),
                       "TRAVELER_COUNT_LOST_ON_DETAILS")
                ensure("Ориентир по прайс-листу на 2 взрослых" not in
                       page.locator("#facts").inner_text(),
                       "PAIR_PRICE_MISREPRESENTED_FOR_FAMILY")
                q=page.locator("#quoteLink").get_attribute("href")
                ensure("&adults=1&kids=1" in q,
                       "TRAVELER_COUNT_LOST_TO_QUOTATION")
                page.locator("#quoteLink").click()
                page.wait_for_url("**/quote.html?preview=*",timeout=20000)
                page.wait_for_function(
                    "()=>document.getElementById('quoteNotice').textContent.includes('Для выбранного состава')",
                    timeout=12000)
                ensure(page.locator("#checkQuote").is_disabled(),
                       "UNSUPPORTED_TRAVELERS_ENTERED_TWO_ADULT_CHECKOUT")
                print("CUSTOM_TRAVELER_PARTY_1_ADULT_1_CHILD_PROTECTED=YES")

                # All reference destinations remain selectable even when the
                # official supplier publishes no validated Irkutsk tour.
                page.goto(base,wait_until="domcontentloaded")
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=25000)
                selector=page.locator("#allCountrySelector")
                ensure(selector.locator("option").count()>=251,
                       "FULL_DESTINATION_DIRECTORY_NOT_IN_TOUR_RESULTS")
                selector.select_option("Мальдивы")
                ensure(page.locator("#destination").input_value()=="Мальдивы",
                       "COUNTRY_DIRECTORY_FILTER_NOT_CONNECTED")
                heads=page.locator("#previewCards article.offerCard h3").all_text_contents()
                ensure(all(h.startswith("Мальдивы · ") for h in heads),
                       "COUNTRY_FILTER_MIXED_UNRELATED_TOURS")
                if not heads:
                    ensure("нет подтверждённых" in page.locator("#previewCards").inner_text(),
                           "UNAVAILABLE_COUNTRY_NOT_EXPLAINED")
                print("FULL_COUNTRY_DIRECTORY_SEARCH_IN_RESULTS=PASS")

                # Tour results are visible first; the old "0 confirmed bookings"
                # block cannot be mistaken for zero search matches.
                page.locator("#allCountrySelector").select_option("")
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=20000)
                ensure(page.locator("#searchResultsCount").is_visible(),
                       "MAIN_RESULTS_COUNT_NOT_VISIBLE")
                ensure(page.locator("#confirmedSection").is_hidden(),
                       "EMPTY_VERIFIED_BOOKINGS_MISLEAD_CUSTOMER")
                link=page.locator('#previewCards article.offerCard a[href^="hotel.html?id="]').first
                ensure(link.count()>0,"REAL_TOUR_MUST_LINK_TO_HOTEL_DESCRIPTION")
                link.click()
                page.wait_for_url("**/hotel.html?id=*",timeout=20000)
                page.wait_for_function(
                  "()=>document.getElementById('name').textContent.length>2 && "+
                  "!document.getElementById('name').textContent.includes('Загружаем')",
                  timeout=15000)
                ensure(page.locator("#facts .fact").count()>=3,
                       "HOTEL_DESCRIPTION_FACTS_NOT_LOADED")
                ensure(page.locator("#gallery").count()==1,
                       "HOTEL_PHOTO_GALLERY_MISSING")
                ensure(page.locator("#reviewForm").count()==1,
                       "HOTEL_REVIEW_FORM_MISSING")
                ensure(page.locator("#reviewSubmit").is_disabled(),
                       "REVIEW_SUBMISSION_ENABLED_WITHOUT_HTTPS_BACKEND")
                print("REAL_TOUR_TO_HOTEL_PHOTOS_DESCRIPTION_REVIEWS=PASS")

                # Regression: the hotel shown in a real customer screenshot
                # must display its VERIFIED supplier facts and attributed
                # historical views, not only a placeholder or name.
                page.goto(base+"hotel.html?id=102610001140",wait_until="domcontentloaded")
                page.wait_for_function(
                   "()=>document.getElementById('description').textContent.includes('Adriatic Palace Pattaya') && "+
                   "document.getElementById('curatedRooms').textContent.includes('Panorama')",
                   timeout=15000)
                ensure("Пратамнак" in page.locator("#description").inner_text(),
                       "ADRIATIC_HOTEL_DETAIL_STILL_GENERIC")
                ensure(page.locator("#facts .fact").count()>=6,
                       "ADRIATIC_HOTEL_MISSING_VERIFIED_FEATURES")
                page.locator("#gallery figure.photo").first.wait_for(timeout=12000)
                ensure(page.locator("#gallery figure.photo").count()>=2,
                       "ADRIATIC_LICENSED_HISTORICAL_PHOTOS_MISSING")
                ensure("2010" in page.locator("#photoStatus").inner_text(),
                       "ADRIATIC_HISTORICAL_PHOTO_NOT_EXPLAINED")
                ensure("CC BY-SA 3.0" in page.locator("#gallery").inner_text(),
                       "ADRIATIC_PHOTO_CREDITS_MISSING")
                print("ADRIATIC_PATTAYA_VERIFIED_DESCRIPTION_AND_LICENSED_VIEWS=PASS")

                # Basaya has verified supplier facts but no permitted hotel
                # photography. Mock an explicitly licensed *resort* photo:
                # it must never be labeled as a photo of Basaya itself.
                image_result={"query":{"pages":{"1":{
                  "title":"File:Pattaya Beach licensed landscape.jpg",
                  "imageinfo":[{
                    "thumburl":"https://upload.wikimedia.org/wikipedia/commons/thumb/b/bb/Pattaya_Beach.jpg/640px-Pattaya_Beach.jpg",
                    "descriptionurl":"https://commons.wikimedia.org/wiki/File:Pattaya_Beach_licensed_landscape.jpg",
                    "extmetadata":{"LicenseShortName":{"value":"CC BY-SA 3.0"},
                                   "Artist":{"value":"CC Test Photographer"}}}
                  ]}}}}
                page.route("https://commons.wikimedia.org/w/api.php?*",
                  lambda route: route.fulfill(status=200,content_type="application/json",
                                              body=json.dumps(image_result)))
                page.goto(base+"hotel.html?id=102623766108",wait_until="domcontentloaded")
                page.locator("#facts .fact").first.wait_for(timeout=15000)
                page.wait_for_timeout(1600)
                debug=page.evaluate("""() => ({
                    title: document.getElementById('name')?.textContent,
                    desc: document.getElementById('description')?.textContent.slice(0,220),
                    rooms: document.getElementById('curatedRooms')?.textContent.slice(0,220),
                    photos: document.getElementById('photoStatus')?.textContent.slice(0,300),
                    gallery: document.getElementById('gallery')?.textContent.slice(0,240)
                })""")
                print("BASAYA_BROWSER_DIAGNOSTIC="+json.dumps(debug,ensure_ascii=False))
                ensure("basaya beach" in str(debug["desc"]).lower() and
                       "NEW STANDARD" in str(debug["rooms"]),
                       "BASAYA_SOURCE_DETAIL_MISSING")
                ensure("НЕ" in str(debug["photos"]),
                       "BASAYA_RESORT_FALLBACK_MISSING")
                ensure(page.locator("#facts .fact").count()>=6,
                       "BASAYA_HOTEL_DESCRIPTION_NOT_ENRICHED")
                ensure("НЕ фотография гостиницы" in page.locator("#gallery").inner_text(),
                       "RESORT_PHOTO_MUST_NOT_PRETEND_TO_BE_A_BASAYA_HOTEL_PHOTO")
                ensure("CC BY-SA 3.0" in page.locator("#gallery").inner_text(),
                       "LICENSED_RESORT_PHOTO_CREDIT_MISSING")
                print("BASAYA_HOTEL_DESCRIPTION_AND_HONEST_LICENSED_RESORT_PHOTOS=PASS")

                # The Guangzhou hotel has three externally hosted original
                # CC BY-SA 4.0 hotel photographs, verified on Commons.
                page.goto(base+"hotel.html?id=102667206879",wait_until="domcontentloaded")
                page.wait_for_function(
                  "()=>document.getElementById('description').textContent.includes('Asia International Hotel') && "+
                  "document.getElementById('gallery').querySelectorAll('figure.photo').length===3",
                  timeout=18000)
                ensure("Гуанчжоу" in page.locator("#location").inner_text(),
                       "GUANGZHOU_HOTEL_ID_NOT_MATCHED")
                ensure(page.locator("#gallery a").filter(has_text="CC BY-SA 4.0").count()==3,
                       "GUANGZHOU_THREE_LICENSE_CREDITS_MISSING")
                ensure(page.locator("#gallery img").count()==3,
                       "GUANGZHOU_HOTEL_GALLERY_MISSING")
                print("GUANGZHOU_HOTEL_THREE_COMMONS_CC4_DIRECT_EXTERNAL_PHOTOS=PASS")

                # Confirm a commercially authorized external hotel's image
                # can be displayed by URL without downloading to Oracle.
                # CI data is synthetic and never enters production JSON.
                mock_manifest={
                  "schema":"jamaica.hotel-media-approved.v1",
                  "hotels":{"102623766108":{
                    "hotel_name":"BASAYA BEACH HOTEL & RESORT","country":"Таиланд",
                    "rights_verified":True,"commercial_publication_allowed":True,
                    "rights_verified_at":"2026-11-21",
                    "permission_reference":"TEST_SIGNED_GRANT_ONLY",
                    "approved_image_hosts":["cdn.approved-hotel.example"],
                    "approved_source_hosts":["www.approved-hotel.example"],
                    "photos":[{
                      "src":"https://cdn.approved-hotel.example/photos/basaya/exterior.jpg",
                      "source":"https://www.approved-hotel.example/basaya/gallery",
                      "license":"contract-authorized",
                      "alt":"Внешний вид BASAYA BEACH HOTEL & RESORT",
                      "credit":"Тестовый разрешённый правообладатель",
                      "kind":"exterior"
                    }]
                  }}
                }
                page.route("**/hotel-media-approved.json",
                  lambda route: route.fulfill(status=200,content_type="application/json",
                    body=json.dumps(mock_manifest,ensure_ascii=False)))
                page.goto(base+"hotel.html?id=102623766108",wait_until="domcontentloaded")
                page.locator('img[src="https://cdn.approved-hotel.example/photos/basaya/exterior.jpg"]').wait_for(timeout=12000)
                ensure("использовано с разрешения" in page.locator("#gallery").inner_text(),
                       "EXTERNAL_HOTEL_PHOTO_MISSING_RIGHTS_ATTRIBUTION")
                page.unroute("**/hotel-media-approved.json")
                print("EXTERNAL_HOTEL_CDN_IMAGE_URL_WITH_EXPLICIT_RIGHTS=PASS")
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
