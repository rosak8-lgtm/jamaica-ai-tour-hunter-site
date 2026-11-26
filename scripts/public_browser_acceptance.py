"""Read-only real GitHub Pages browser acceptance. No synthetic tours or form submissions."""
import json
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright, TimeoutError as BrowserTimeout

BASE="https://rosak8-lgtm.github.io/jamaica-ai-tour-hunter-site/"
HOST=urlsplit(BASE).netloc

def main():
    result={"classification":"PUBLIC_BROWSER_READ_ONLY","synthetic_catalog":False,
            "booking_actions":0,"customer_requests":0,"ip_geo_tested":False}
    errors=[]; responses={}
    with sync_playwright() as p:
        browser=p.chromium.launch(headless=True)
        page=browser.new_page(viewport={"width":1440,"height":900})
        # Do not transmit a customer's IP to external geo or hotel services.
        page.route("**/*",lambda route: route.continue_() if
                   urlsplit(route.request.url).netloc==HOST and
                   route.request.method in ("GET","HEAD") else route.abort())
        page.on("pageerror",lambda e:errors.append(type(e).__name__))
        def response(r):
            path=urlsplit(r.url).path
            for name in ("tour-previews.json","tour-visual-evidence.json","application-reference.json"):
                if path.endswith("/"+name):
                    responses[name]=r.status
        page.on("response",response)
        try:
            r=page.goto(BASE,wait_until="domcontentloaded",timeout=30000)
            result["document_http"]=r.status if r else None
            page.locator("#departure").select_option("Иркутск",timeout=15000)
            try:
                page.wait_for_function("""()=>document.querySelector('#previewCards article.offerCard') ||
                    (document.querySelector('#searchResultsCount')?.textContent||'').includes('найдено')""",timeout=25000)
            except BrowserTimeout:pass
            page.locator("#destination").fill("")
            page.locator("#dateFrom").fill("")
            page.locator("#dateTo").fill("")
            page.locator("#tourSearchForm button[type=submit]").click()
            try:page.locator("#previewCards article.offerCard").first.wait_for(timeout=15000)
            except BrowserTimeout:pass
            result["origin"]=page.locator("#departure").input_value()
            result["visible_cards"]=page.locator("#previewCards article.offerCard").count()
            result["result_label"]=page.locator("#searchResultsCount").inner_text()[:120]
            result["country_shortcuts"]=page.locator("#quickCountries .quickCountryChip:not(.quickCountryMore)").all_text_contents()[:20]
            result["status"]="VISIBLE_VERIFIED_CARDS" if result["visible_cards"]>0 else "HOLD_NO_VISIBLE_CARDS"
        except Exception as exc:
            result["status"]="HOLD_PUBLIC_BROWSER"
            result["error_type"]=type(exc).__name__
        finally:
            result["feed_http"]=responses
            result["page_error_count"]=len(errors)
            browser.close()
    print("JAMAICA_PUBLIC_BROWSER_RESULT="+json.dumps(result,ensure_ascii=False))
    return 0

if __name__=="__main__":raise SystemExit(main())
