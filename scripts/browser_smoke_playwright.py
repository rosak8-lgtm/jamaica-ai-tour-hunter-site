#!/usr/bin/env python3
"""JAMAICA real Chromium navigation smoke test; safe localhost only.

Requires Python Playwright and downloaded Chromium; no Node or public network.
GET-only static files; does not contact any supplier API or submit payments.
"""
from __future__ import annotations

import functools
from base64 import b64decode
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
                # Keep image-load tests deterministic: external photos stay on their
                # licensed origin in production, but CI serves only a valid pixel.
                pixel=b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/QRYAAAAASUVORK5CYII=")
                page.route("https://commons.wikimedia.org/wiki/Special:FilePath/**",
                  lambda route: route.fulfill(status=200,content_type="image/png",body=pixel))
                page.route("https://upload.wikimedia.org/**",
                  lambda route: route.fulfill(status=200,content_type="image/png",body=pixel))
                # Hotel photos must be identity verified: no unrelated country scenery.
                errors=[]
                page.on("pageerror",lambda e:errors.append(str(e)[:220]))
                page.goto(base,wait_until="domcontentloaded")
                png_favicon=page.request.get(base+"favicon.png?v=20261122b")
                ico_favicon=page.request.get(base+"favicon.ico?v=20261122b")
                ensure(png_favicon.status==200 and
                       png_favicon.body().startswith(bytes((137,80,78,71,13,10,26,10))),
                       "NEW_BRANDED_PNG_FAVICON_UNAVAILABLE")
                ensure(ico_favicon.status==200 and
                       ico_favicon.body().startswith(bytes((0,0,1,0,1,0))),
                       "CLASSIC_ICO_FAVICON_UNAVAILABLE")
                ensure(page.evaluate("""async ()=> {
                  const img=new Image();
                  img.src='./favicon.png?v=20261122b';
                  await img.decode();
                  return img.naturalWidth===64&&img.naturalHeight===64;
                }"""),"NEW_PARROT_FAVICON_IMAGE_DECODE_FAILED")
                print("BRANDED_PARROT_FAVICON_PNG_ICO_PASS")
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=25000)
                ensure(page.locator(".logo .bird img").count()==1 and
                       page.locator(".heroArt .mascotHero").count()==1,
                       "BRAND_MASCOT_MISSING")
                try:
                    page.wait_for_function(
                      "()=>[...document.querySelectorAll('.logo .bird img,.heroArt .mascotHero')]"+
                      ".every(img=>img.complete&&img.naturalWidth>0)",timeout=12000)
                except Exception:
                    debug=page.evaluate("""()=>
                     [...document.querySelectorAll('.logo .bird img,.heroArt .mascotHero')]
                       .map(img=>({src:img.src,currentSrc:img.currentSrc,
                                  naturalWidth:img.naturalWidth,complete:img.complete,
                                  type:img.parentElement?.tagName}))
                    """)
                    print("MASCOT_DECODE_DEBUG="+str(debug),flush=True)
                    raise
                ensure(page.evaluate("""()=>
                   document.querySelector('.heroArt .mascotHero').currentSrc.endsWith('jamaica-parrot-hero-v2.avif')&&
                   document.querySelector('.logo .bird img').currentSrc.endsWith('jamaica-parrot-logo-v2.avif')"""),
                   "REAL_PHOTOREALISTIC_MASCOT_FILES_NOT_USED_BY_BROWSER")
                ensure(page.locator("#catalogBreadth").count()==1,
                       "COUNTRY_BREADTH_SUMMARY_MISSING")
                # New branded search design must be a FUNCTIONAL, not decorative,
                # two-column filter + horizontal card travel shopping interface.
                ensure(page.locator(".resultsLayout").count()==1,
                       "PRO_SEARCH_RESULT_LAYOUT_MISSING")
                ensure(page.locator("#routes").count()==0 and
                       page.locator("#routeCards").count()==0 and
                       page.locator("#routeCountryChips").count()==0,
                       "NON_BOOKABLE_ROUTE_WALL_MUST_NOT_OCCUPY_CUSTOMER_PAGE")
                ensure(page.locator("#hotelDirectoryDisclosure").count()==1,
                       "OPTIONAL_HOTEL_REFERENCE_MISSING")
                ensure(page.locator("#hotelDirectoryDisclosure").get_attribute("open") is None,
                       "HOTEL_REFERENCE_MUST_BE_COLLAPSED_BY_DEFAULT")
                ensure(page.locator("#hotelGuideCards .destination").count()==0,
                       "HEAVY_HOTEL_DIRECTORY_SHOULD_BE_LOADED_ON_DEMAND")
                ensure(page.locator("#previewCards .tourResultCard").count()>0,
                       "HORIZONTAL_TOUR_RESULT_CARD_MISSING")
                ensure(page.locator("#filtersDisclosure").get_attribute("open") is not None,
                       "DESKTOP_FILTERS_NOT_OPEN")
                ensure(page.locator("#filterCountry option").count()>=3,
                       "COUNTRY_SIDEBAR_NOT_SOURCE_BACKED")
                ensure(page.locator("#filterResort").count()==1,
                       "REAL_RESORT_SIDEBAR_FILTER_MISSING")
                ensure(page.locator("#advancedFilters").count()==1,
                       "ADVANCED_BUDGET_HOTEL_FILTERS_MISSING")
                ensure(page.locator("#favoritesOnly").count()==1,
                       "BROWSER_SAVED_TOURS_CONTROL_MISSING")
                # A real filter changes the displayed catalog, not just its label.
                page.locator("#filterCountry").select_option("Турция")
                page.locator("#filterApply").click()
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=15000)
                filtered=page.locator("#previewCards article.offerCard h3").all_text_contents()
                ensure(filtered and all(x.startswith("Турция · ") for x in filtered),
                       "SIDEBAR_FILTER_NOT_CONNECTED_TO_PUBLIC_TOURS")
                ensure(page.locator("#otherCountries").is_visible(),
                       "OTHER_COUNTRIES_ACTION_MISSING")
                page.locator("#otherCountries").click()
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=12000)
                other_countries={name.split(" · ")[0] for name in
                   page.locator("#previewCards article.offerCard h3").all_text_contents()}
                ensure(len(other_countries)>=3,
                       "OTHER_COUNTRIES_DID_NOT_RESTORE_MIXED_RESULTS")
                page.locator("#filterReset").click()
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=15000)
                # Saved tours are local-only; they NEVER create a booking.
                page.locator("#previewCards .saveTour").first.click()
                page.locator("#favoritesOnly").check()
                ensure(page.locator("#previewCards article.offerCard").count()==1,
                       "LOCAL_FAVORITES_FILTER_NOT_FUNCTIONAL")
                ensure(page.locator("#previewCards .saveTour[aria-pressed='true']").count()==1,
                       "FAVORITE_SAVE_STATE_LOST")
                page.locator("#favoritesOnly").uncheck()
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=15000)
                ensure(page.locator("#previewCountryChips").count()==0,
                       "COUNTRY_BUTTON_WALL_DISPLACES_TOURS")
                ensure(page.locator("#sourceCountryPriority").count()==0,
                       "TECHNICAL_COUNTRY_POLLING_WALL_DISPLACES_TOURS")
                ensure(page.locator("#sourceDetails").is_visible(),
                       "SOURCE_TRANSPARENCY_DETAILS_NOT_PRESENT")
                ensure(not page.locator("#sourceDetails").get_attribute("open"),
                       "TECHNICAL_STATUS_MUST_BE_COLLAPSED_BY_DEFAULT")
                ensure(page.locator("#previewCards").bounding_box()["y"] <
                       page.locator("#sourceDetails").bounding_box()["y"],
                       "REAL_TOUR_CARDS_MUST_APPEAR_BEFORE_TECHNICAL_DETAILS")
                ensure(page.locator("#countryDatalist option").count()>=251,
                       "FULL_COUNTRY_SEARCH_MUST_STAY_AVAILABLE")
                page.locator("#hotelDirectoryDisclosure summary").click()
                page.locator("#hotelGuideCards .destination").first.wait_for(timeout=25000)
                ensure(page.locator("#hotelDirectoryDisclosure").get_attribute("open") is not None,
                       "HOTEL_DIRECTORY_DISCLOSURE_FAILED")
                page.locator("#hotelDirectoryDisclosure summary").click()
                ensure(page.locator('#nights option[value="8"]').count()==1,
                       "EIGHT_NIGHT_OPTION_MISSING")
                ensure(page.locator('#nights option[value="9"]').count()==1,
                       "NINE_NIGHT_OPTION_MISSING")
                ensure(page.locator('#nights option[value="11"]').count()==1,
                       "ELEVEN_NIGHT_OPTION_MISSING")
                ensure(page.locator('#nights option').count()==179,
                       "NOT_ALL_3_TO_180_NIGHTS_PRESENT")
                ensure(page.locator("#dateTo").count()==1,
                       "DATE_RANGE_UPPER_BOUND_MISSING")

                first30=page.locator("#previewCards article.offerCard h3").all_text_contents()
                shown={text.split(" · ")[0] for text in first30}
                ensure(len(shown)>=3,"FIRST_PAGE_DOES_NOT_SHOW_MULTIPLE_COUNTRIES")
                ensure(page.locator("#previewCards .previewMedia").count()>0,
                       "VISUAL_TOUR_CARD_MISSING")
                if counts.get("Таиланд",0)>0:
                    thai_cards=page.locator("#previewCards article.offerCard").filter(has_text="Таиланд ·")
                    ensure(thai_cards.count()>0,"THAILAND_CARD_MISSING")
                    # No exact facade for the displayed Thai property:
                    # destination photography is permitted ONLY when prominently
                    # labelled as NOT the chosen hotel, and with author/source.
                    thai_cards.first.locator(".destinationPhotoLabel").wait_for(timeout=14000)
                    ensure("не фото гостиницы" in thai_cards.first.locator(".destinationPhotoLabel").inner_text(),
                           "DESTINATION_IMAGE_NOT_CLEARED_AS_NOT_HOTEL")
                    ensure("не выбранной гостиницы" in thai_cards.first.locator(".previewMedia img").first.get_attribute("alt"),
                           "DESTINATION_ALT_MUST_NOT_CLAIM_HOTEL")
                    thai_cards.first.locator(".previewMedia img").first.scroll_into_view_if_needed()
                    page.wait_for_function(
                      "()=>[...document.querySelectorAll('#previewCards .previewMedia img')]"+
                      ".some(img=>img.complete&&img.naturalWidth>0)",timeout=14000)
                    ensure(thai_cards.first.locator(".mediaSourceCredit").count()==1,
                           "DESTINATION_PHOTO_AUTHOR_AND_LICENSE_MISSING")
                    ensure(thai_cards.first.locator(".previewPhotoMeta .mediaLicenseLink").count()==1,
                           "DESTINATION_LICENSE_LINK_MISSING")
                    clean_image=thai_cards.first.evaluate("""card => {
                      const frame=card.querySelector('.previewPhotoFrame');
                      const footer=card.querySelector('.previewPhotoMeta');
                      const photo=frame?.querySelector('img');
                      if(!frame||!footer||!photo)return false;
                      const imageRect=frame.getBoundingClientRect();
                      const footerRect=footer.getBoundingClientRect();
                      const label=card.querySelector('.destinationPhotoLabel');
                      return footerRect.top>=imageRect.bottom-1 &&
                        footerRect.height>0 &&
                        footer.contains(label) &&
                        getComputedStyle(footer).position!=='absolute' &&
                        getComputedStyle(label).position!=='absolute';
                    }""")
                    ensure(clean_image,"CAPTIONS_MUST_APPEAR_BELOW_NOT_ON_TOP_OF_PHOTO")
                if counts.get("Абхазия",0)>0:
                    abkh=page.locator("#previewCards article.offerCard").filter(has_text="Абхазия ·")
                    abkh.first.locator(".destinationPhotoLabel").wait_for(timeout=14000)
                    ensure(abkh.first.locator(".previewMedia img").count()==1,
                           "ABKHAZIA_PHOTO_NOT_SHOWN_IN_FIRST_RESULT")

                # Price sort must order known two-adult references, not departure dates.
                page.locator("#previewSort").select_option("price")
                texts=page.locator("#previewCards article.offerCard strong").all_text_contents()
                prices=[]
                for line in texts:
                    digits="".join(ch for ch in line.split(":")[-1] if ch.isdigit())
                    if digits:
                        prices.append(int(digits))
                ensure(prices==sorted(prices),"GLOBAL_PRICE_SORT_NOT_ASCENDING")
                # Multi-country default continues showing other countries on the first page.
                page.locator("#previewSort").select_option("balanced")
                shown_again={name.split(" · ")[0] for name in page.locator("#previewCards article.offerCard h3").all_text_contents()}
                ensure(len(shown_again)>=3,"PRICE_SORT_BROKE_COUNTRY_COVERAGE")
                if preview.get("truncated_to_public_limit") is True:
                    # Disclosure exists but is intentionally collapsed BELOW cards.
                    page.locator("#sourceDetails summary").click()
                    ensure(page.locator("#sourceDetails").get_attribute("open") is not None,
                           "SOURCE_TRANSPARENCY_CANNOT_BE_OPENED")
                    ensure("ВАЖНО" in page.locator("#previewCoverage").inner_text(),
                           "TRUNCATED_CATALOGUE_WARNING_NOT_AVAILABLE")
                    page.locator("#sourceDetails summary").click()

                turkey_dates=sorted({r["depart_date"] for r in rows if r["country"]=="Турция"})
                ensure(bool(turkey_dates),"NO_TURKEY_DATES_FOR_RANGE_TEST")
                page.locator("#dateFrom").fill(turkey_dates[0])
                page.locator("#dateTo").fill(turkey_dates[0])
                page.locator("#destination").fill("Турция")
                page.locator("#tourSearchForm button[type=submit]").click()
                page.locator("#previewCards article.offerCard").first.wait_for(timeout=15000)
                visible=page.locator("#previewCards article.offerCard h3").all_text_contents()
                ensure(visible and all(text.startswith("Турция · ") for text in visible),
                       "COUNTRY_FILTER_DID_NOT_REFRESH_PREVIEWS")
                ensure(page.locator("#previewCards article.offerCard").count()>0,
                       "EXACT_DATE_RANGE_EXCLUDED_SOURCE_RECORD")
                page.locator("#dateFrom").fill("")
                page.locator("#dateTo").fill("")
                page.locator("#tourSearchForm button[type=submit]").click()

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
                # The element exists before its async preview JSON resolves:
                # wait for the *country content*, not just element attachment.
                page.wait_for_function(
                   "()=>document.querySelector('#hotelTitle')?.textContent?.includes('Турция')",
                   timeout=20000)
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
                ensure(page.locator("#destinations").count()==0,
                       "ALL_COUNTRIES_WALL_SHOULD_NOT_BE_ON_HOMEPAGE")
                ensure(page.locator("#destinationGrid").count()==0,
                       "EMPTY_COUNTRY_CARDS_SHOULD_NOT_OCCUPY_PAGE")
                options=page.locator("#countryDatalist option")
                ensure(options.count()>=251,
                       "ALL_251_COUNTRIES_MUST_REMAIN_SEARCHABLE")
                page.locator("#destination").fill("Мальдивы")
                page.locator('#tourSearchForm button[type="submit"]').click()
                ensure(page.locator("#destination").input_value()=="Мальдивы",
                       "COUNTRY_SEARCH_FIELD_NOT_CONNECTED")
                heads=page.locator("#previewCards article.offerCard h3").all_text_contents()
                ensure(all(h.startswith("Мальдивы · ") for h in heads),
                       "COUNTRY_FILTER_MIXED_UNRELATED_TOURS")
                if not heads:
                    ensure("нет подходящих вариантов" in page.locator("#previewCards").inner_text(),
                           "UNAVAILABLE_COUNTRY_NOT_EXPLAINED")
                print("FULL_COUNTRY_DIRECTORY_SEARCH_IN_RESULTS=PASS")

                # Tour results are visible first; the old "0 confirmed bookings"
                # block cannot be mistaken for zero search matches.
                page.locator("#destination").fill("")
                page.locator('#tourSearchForm button[type="submit"]').click()
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

                # Supplier hotel descriptions remain, but historical views of a
                # neighborhood and country scenery are NOT actual hotel photos.
                page.goto(base+"hotel.html?id=102610001140",wait_until="domcontentloaded")
                page.wait_for_function(
                   "()=>document.getElementById('description').textContent.includes('Adriatic Palace Pattaya') && "+
                   "document.getElementById('curatedRooms').textContent.includes('Panorama')",
                   timeout=15000)
                ensure("Пратамнак" in page.locator("#description").inner_text(),
                       "ADRIATIC_HOTEL_DETAIL_STILL_GENERIC")
                page.wait_for_function(
                  "()=>document.querySelector('#gallery .hero')!==null",timeout=12000)
                ensure(page.locator("#gallery figure.photo").count()==0,
                       "HISTORIC_SCENERY_WAS_LABELED_AS_PROPERTY_PHOTO")
                ensure("Подтверждённые фотографии" in page.locator("#gallery").inner_text(),
                       "HONEST_HOTEL_MEDIA_PLACEHOLDER_MISSING")

                page.goto(base+"hotel.html?id=102623766108",wait_until="domcontentloaded")
                page.wait_for_function(
                  "()=>document.getElementById('description').textContent.toLowerCase().includes('basaya beach')",
                  timeout=15000)
                ensure("NEW STANDARD" in page.locator("#curatedRooms").inner_text(),
                       "BASAYA_VERIFIED_ROOM_INFO_MISSING")
                page.wait_for_function(
                  "()=>document.querySelector('#gallery .hero')!==null",timeout=12000)
                ensure(page.locator("#gallery img").count()==0,
                       "BASAYA_MUST_NOT_GET_UNRELATED_RESORT_PHOTO")
                print("BASAYA_AND_ADRIATIC_HOTEL_ONLY_PHOTO_POLICY_PASS")

                page.goto(base+"hotel.html?id=102667206879",wait_until="domcontentloaded")
                page.wait_for_function(
                  "()=>document.getElementById('description').textContent.includes('Asia International Hotel') && "+
                  "document.getElementById('gallery').querySelectorAll('figure.photo').length===3",
                  timeout=18000)
                ensure(page.locator("#gallery a").filter(has_text="CC BY-SA 4.0").count()==3,
                       "GUANGZHOU_LICENSED_FACADE_IMAGES_MISSING")
                # Never pass on empty FIGURE shells: pixels must actually load.
                ensure(page.locator("#gallery figure.photo img").count()==3,
                       "GUANGZHOU_ACTUAL_IMG_ELEMENTS_MISSING")
                page.locator("#gallery").scroll_into_view_if_needed()
                page.wait_for_function(
                  "()=>[...document.querySelectorAll('#gallery figure.photo img')]"+
                  ".every(img=>img.complete&&img.naturalWidth>0)",timeout=15000)
                ensure(page.locator('#gallery figure.photo img[src$="width=960"]').count()==3,
                       "WIKIMEDIA_STANDARD_HOTEL_THUMBNAIL_SIZE_MISSING")
                ensure("Вид из гостиницы" not in page.locator("#gallery").inner_text(),
                       "GUANGZHOU_PANORAMAS_MUST_NOT_BE_MISTAKEN_FOR_HOTEL_FACADE")

                # A request for a larger thumbnail may be rate-limited:
                # display the SAME hotel's verified photo at standard 500px.
                page.route("https://commons.wikimedia.org/wiki/Special:FilePath/**",
                  lambda route: route.abort("failed") if
                    route.request.url.endswith("width=960")
                    else route.fulfill(status=200,content_type="image/png",body=pixel))
                page.goto(base+"hotel.html?id=102667206879",wait_until="domcontentloaded")
                page.locator("#gallery").scroll_into_view_if_needed()
                page.wait_for_function(
                  "()=>[...document.querySelectorAll('#gallery figure.photo img')]"+
                  ".length===3&&[...document.querySelectorAll('#gallery figure.photo img')]"+
                  ".every(img=>img.complete&&img.naturalWidth>0&&img.src.endsWith('width=500'))",
                  timeout=18000)
                print("WIKIMEDIA_960_TO_500_HOTEL_IMAGE_RETRY_PASS")
                page.unroute("https://commons.wikimedia.org/wiki/Special:FilePath/**")

                # Check actual decoded photos for four additional, exactly
                # identified hotels in Thailand, Vietnam and China.
                for hid in ("102610001177","102610001141",
                            "102616490643","102667202290"):
                    page.goto(base+"hotel.html?id="+hid,wait_until="domcontentloaded")
                    page.locator("#gallery figure.photo img").first.wait_for(timeout=18000)
                    page.locator("#gallery").scroll_into_view_if_needed()
                    page.wait_for_function(
                       "()=>[...document.querySelectorAll('#gallery figure.photo img')]"+
                       ".some(img=>img.complete&&img.naturalWidth>0)",timeout=15000)
                    ensure(page.locator('#gallery a').filter(has_text="Оригинал").count()>=1,
                           "MISSING_ORIGINAL_LICENSE_CREDIT_"+hid)
                print("FOUR_EXTRA_EXACT_HOTEL_PHOTOS_DECODED_PASS")
                # The prior fallback test intentionally called unroute() on all
                # Commons handlers. Restore the deterministic licensed-photo
                # network fixture before checking public tour preview cards.
                page.route("https://commons.wikimedia.org/wiki/Special:FilePath/**",
                  lambda route: route.fulfill(
                     status=200,content_type="image/png",body=pixel))
                # Three of the real published preview hotels now have exact,
                # licensed Wikimedia photos (not only unrelated directory pages).
                from urllib.parse import urlencode
                for country,name,hid in (
                    ("Китай","BAIYUN HOTEL GUANGZHOU","102618075164"),
                    ("Китай","CHINA HOTEL GUANGZHOU","102624989868"),
                    ("Россия","КРАСНОЯРСК, гостиница","102625907920"),
                ):
                    page.goto(base+"?"+urlencode({"country":country,"hotel":name}),
                              wait_until="domcontentloaded")
                    page.locator("#previewCards .previewMedia img").first.wait_for(timeout=22000)
                    page.locator("#previewCards .previewMedia img").first.scroll_into_view_if_needed()
                    try:
                        page.wait_for_function(
                          "()=>[...document.querySelectorAll('#previewCards .previewMedia img')]"+
                          ".some(img=>img.complete&&img.naturalWidth>0)",timeout=20000)
                    except Exception:
                        details=page.evaluate("""() => ({
                         country:document.getElementById('destination').value,
                         hotel:document.getElementById('hotelSearch').value,
                         cardCount:document.querySelectorAll('#previewCards article').length,
                         cards:[...document.querySelectorAll('#previewCards article')].slice(0,2).map(c=>c.innerText.slice(0,140)),
                         imgs:[...document.querySelectorAll('#previewCards .previewMedia img')].slice(0,4).map(img=>({
                           src:img.src,complete:img.complete,width:img.naturalWidth
                         })),
                         placeholders:[...document.querySelectorAll('#previewCards .previewScenePlaceholder')].slice(0,2).map(e=>e.textContent),
                         notice:document.getElementById('previewCount')?.textContent
                        })""")
                        print("EXACT_HOTEL_PHOTO_DEBUG="+str((hid,details)),flush=True)
                        raise
                    ensure(page.locator("#previewCards .mediaSourceCredit").count()>=1,
                           "EXACT_PREVIEW_HOTEL_PHOTO_SOURCE_MISSING_"+hid)
                print("LIVE_PREVIEW_EXACT_HOTEL_PHOTOS_THREE_PROPERTIES_PASS")

                # When the actual hotel images fail, do not replace them
                # with photos of Guangzhou skyline or unrelated hotels.
                page.route("https://commons.wikimedia.org/wiki/Special:FilePath/**",
                  lambda route: route.abort("failed"))
                page.goto(base+"hotel.html?id=102667206879",wait_until="domcontentloaded")
                page.locator("#gallery").scroll_into_view_if_needed()
                page.wait_for_function(
                  "()=>document.querySelector('#gallery .hero')!==null",timeout=20000)
                ensure(page.locator("#gallery img").count()==0,
                       "BROKEN_HOTEL_PHOTOS_WERE_NOT_CLEARED")
                print("GUANGZHOU_HOTEL_EXTERIOR_ONLY_AND_FAIL_CLOSED_PASS")

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
                pixel=b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+/QRYAAAAASUVORK5CYII=")
                page.route("https://cdn.approved-hotel.example/photos/basaya/exterior.jpg",
                  lambda route: route.fulfill(status=200,content_type="image/png",body=pixel))
                page.goto(base+"hotel.html?id=102623766108",wait_until="domcontentloaded")
                page.locator('img[src="https://cdn.approved-hotel.example/photos/basaya/exterior.jpg"]').wait_for(timeout=12000)
                page.locator("#gallery").scroll_into_view_if_needed()
                page.wait_for_function(
                  "()=>[...document.querySelectorAll('#gallery figure.photo img')]"+
                  ".some(img=>img.complete&&img.naturalWidth>0)",timeout=12000)
                ensure("использовано с разрешения" in page.locator("#gallery").inner_text(),
                       "EXTERNAL_HOTEL_PHOTO_MISSING_RIGHTS_ATTRIBUTION")
                page.unroute("**/hotel-media-approved.json")
                print("EXTERNAL_HOTEL_CDN_IMAGE_URL_WITH_EXPLICIT_RIGHTS=PASS")

                # Licensed HBX content can be found via id -> shard lookup. The
                # site must NEVER guess a source photo using similar hotel names.
                media_entry={
                  "hotel_name":"BASAYA BEACH HOTEL & RESORT","country":"Таиланд",
                  "rights_verified":True,"commercial_publication_allowed":True,
                  "rights_verified_at":"2026-11-21",
                  "rights_expires_at":"2099-12-31",
                  "permission_reference":"TEST_REAL_HBX_LICENSE_REQUIRED",
                  "approved_image_hosts":["photos.hotelbeds.com"],
                  "approved_source_hosts":["photos.hotelbeds.com"],
                  "photos":[{
                    "src":"https://photos.hotelbeds.com/giata/bigger/00/004200/photo.jpg",
                    "source":"https://photos.hotelbeds.com/giata/00/004200/photo.jpg",
                    "license":"contract-authorized",
                    "alt":"Фото гостиницы BASAYA BEACH HOTEL & RESORT от правообладателя",
                    "credit":"HBX Group licensed property photographer",
                    "kind":"other"
                  }]
                }
                media_index={"schema":"jamaica.hotel-media-feed-index.v1",
                             "total_hotels":1,
                             "entries":{"102623766108":
                                        "hotel-media-feed/part-0001.json"}}
                media_part={"schema":"jamaica.hotel-media-feed-part.v1",
                            "hotels":{"102623766108":media_entry}}
                page.route("**/hotel-media-feed/index.json",
                  lambda route: route.fulfill(status=200,content_type="application/json",
                                             body=json.dumps(media_index)))
                page.route("**/hotel-media-feed/part-0001.json",
                  lambda route: route.fulfill(status=200,content_type="application/json",
                                             body=json.dumps(media_part,ensure_ascii=False)))
                page.route("https://photos.hotelbeds.com/giata/bigger/00/004200/photo.jpg",
                  lambda route: route.fulfill(status=200,content_type="image/png",body=pixel))
                page.goto(base+"hotel.html?id=102623766108",wait_until="domcontentloaded")
                page.locator('img[src="https://photos.hotelbeds.com/giata/bigger/00/004200/photo.jpg"]').wait_for(timeout=12000)
                ensure(page.locator("#gallery figure[data-photo-source=partner]").count()==1,
                       "LICENSED_HBX_SHARD_PHOTO_NOT_DISPLAYED")
                ensure("HBX Group" in page.locator("#gallery").inner_text(),
                       "LICENSED_HBX_PHOTO_CREDIT_MISSING")
                ensure("BASAYA BEACH HOTEL & RESORT" in page.locator("#name").inner_text(),
                       "HBX_PHOTO_WAS_ATTACHED_TO_WRONG_HOTEL")
                print("LICENSED_HBX_HOTEL_ID_MEDIA_SHARD_IN_BROWSER=PASS")
                # Open commercial license and verified identity: no HBX
                # credentials or photo files stored on Oracle.
                page.unroute("**/hotel-media-feed/index.json")
                page.unroute("**/hotel-media-feed/part-0001.json")
                name="BASAYA BEACH HOTEL & RESORT"
                filename="Basaya Beach Hotel - Verified Exterior.jpg"
                from urllib.parse import quote
                media_photo={
                 "file":filename,
                 "src":"https://commons.wikimedia.org/wiki/Special:FilePath/"+
                    quote(filename,safe="!'()*-._~")+"?width=500",
                 "source":"https://commons.wikimedia.org/wiki/File:"+
                    quote(filename.replace(" ","_"),safe="!'()*-._~"),
                 "license":"CC BY-SA 4.0",
                 "license_url":"https://creativecommons.org/licenses/by-sa/4.0/",
                 "author":"Verified photographer",
                 "alt":"Фотография конкретной гостиницы Basaya Beach Hotel & Resort",
                 "kind":"hotel_property","wikidata_qid":"Q123456"}
                open_media_index={
                  "schema":"jamaica.hotel-open-media-index.v1",
                  "total_hotels":1,
                  "entries":{"102623766108":"hotel-open-media/part-0001.json"}}
                open_media_part={
                  "schema":"jamaica.hotel-open-media-part.v1",
                  "hotels":{"102623766108":{
                    "hotel_name":name,"country":"Таиланд",
                    "wikidata_qid":"Q123456",
                    "identity_reviewed":True,
                    "identity_review_reference":"https://www.wikidata.org/wiki/Q123456",
                    "photos":[media_photo]}}}
                page.route("**/hotel-open-media/index.json",
                   lambda route:route.fulfill(status=200,content_type="application/json",
                       body=json.dumps(open_media_index,ensure_ascii=False)))
                page.route("**/hotel-open-media/part-0001.json",
                   lambda route:route.fulfill(status=200,content_type="application/json",
                       body=json.dumps(open_media_part,ensure_ascii=False)))
                page.route(media_photo["src"],
                   lambda route:route.fulfill(status=200,content_type="image/png",body=pixel))
                page.goto(base+"hotel.html?id=102623766108",wait_until="domcontentloaded")
                page.locator('#gallery figure[data-photo-source="commons-open"]').wait_for(timeout=12000)
                page.locator("#gallery").scroll_into_view_if_needed()
                page.wait_for_function(
                  "()=>[...document.querySelectorAll('#gallery figure[data-photo-source=commons-open] img')]"+
                  ".some(img=>img.complete&&img.naturalWidth>0)",timeout=12000)
                ensure(page.locator('#gallery a[href="https://creativecommons.org/licenses/by-sa/4.0/"]').count()==1,
                   "COMMERCIAL_CC_LICENSE_LINK_NOT_VISIBLE")
                ensure(page.locator('#gallery').inner_text().find("Verified photographer")>=0,
                   "COMMONS_PROPERTY_PHOTO_AUTHOR_MISSING")
                ensure(page.locator('#gallery img').count()==1,
                   "VERIFIED_WIKIDATA_COMMONS_PHOTO_NOT_SHOWN")
                print("COMMONS_EXACT_PROPERTY_COMMERCIAL_LICENSE_BROWSER_PASS")
                # Independent safe alternative: direct link to the VERIFIED
                # official hotel gallery, never copy its image bytes into JAMAICA.
                approved_link={"schema":"jamaica.hotel-official-sites.v1",
                  "hotels":{"102623766108":{
                  "hotel_name":"BASAYA BEACH HOTEL & RESORT",
                  "country":"Таиланд",
                  "identity_verified":True,
                  "identity_evidence_url":"https://hotel.example/official-details",
                  "official_site_url":"https://hotel.example/",
                  "gallery_url":"https://hotel.example/gallery",
                  "reviewed_at":"2026-11-21"}}}
                page.route("**/hotel-official-sites.json",
                  lambda route:route.fulfill(status=200,content_type="application/json",
                     body=json.dumps(approved_link,ensure_ascii=False)))
                page.goto(base+"hotel.html?id=102623766108",wait_until="domcontentloaded")
                page.locator('#officialGallery a[href="https://hotel.example/gallery"]').wait_for(timeout=12000)
                ensure(page.locator("#officialGallery").is_visible(),
                  "SAFE_OFFICIAL_HOTEL_GALLERY_LINK_MISSING")
                ensure(page.locator("#officialGallery img").count()==0,
                  "OFFICIAL_SITE_IMAGE_COPYING_NOT_ALLOWED")
                print("LINK_TO_REVIEWED_OFFICIAL_HOTEL_GALLERY_BROWSER_PASS")

                # Mobile variant: single-column offers and collapsed, usable
                # filter drawer with no horizontal page overflow.
                mobile=browser.new_page(viewport={"width":390,"height":844})
                try:
                    mobile.goto(base,wait_until="domcontentloaded")
                    mobile.locator("#previewCards article.offerCard").first.wait_for(timeout=25000)
                    ensure(mobile.locator("#filtersDisclosure").get_attribute("open") is None,
                           "MOBILE_FILTER_DRAWER_NOT_COLLAPSED")
                    mobile.locator("#filtersDisclosure summary").click()
                    ensure(mobile.locator("#filterCountry").is_visible(),
                           "MOBILE_FILTER_CONTROLS_NOT_ACCESSIBLE")
                    ensure(mobile.locator("#previewCards .tourResultCard").first.evaluate(
                        "(el)=>getComputedStyle(el).display")=="flex",
                        "MOBILE_CARDS_NOT_STACKED_VERTICALLY")
                    ensure(mobile.evaluate(
                        "()=>document.documentElement.scrollWidth<=window.innerWidth+2"),
                        "MOBILE_HORIZONTAL_OVERFLOW")
                    print("JAMAICA_PRO_SEARCH_MOBILE_FILTERS_PASS")
                finally:
                    mobile.close()


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
