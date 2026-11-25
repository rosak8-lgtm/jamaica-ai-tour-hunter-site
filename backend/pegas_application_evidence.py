"""Private normalized PEGAS evidence contract; not a raw supplier parser.

Only a trusted authorized browser adapter can supply observations. Never
treat a listing price, BG badge, or checkbox alone as an application price.
This function has no network, booking, or publishing side effects.
"""
from datetime import datetime, timedelta, timezone
import re

def _instant(value):
    try:
        t=datetime.fromisoformat(value.replace("Z","+00:00"))
        return t.astimezone(timezone.utc) if t.tzinfo else None
    except (ValueError,TypeError,AttributeError):
        return None

def validate_application_evidence(search,application,*,now):
    if not isinstance(now,datetime) or now.tzinfo is None:return False
    if not isinstance(search,dict) or not isinstance(application,dict):return False
    if search.get("source")!="PEGAS_OFFICIAL_BROWSER_PACKAGE_SEARCH" or application.get("source")!="PEGAS_OFFICIAL_BROWSER_OPEN_APPLICATION":return False
    if search.get("hotel_filter_verified") is not True or search.get("flight_filter_verified") is not True:return False
    if search.get("cheapest_eligible_price_clicked") is not True:return False
    for key in ("browser_session_digest","selected_offer_id","origin_id","country_id","hotel_id","room_id","departure_date","nights","party_digest"):
        if key not in search or search[key]!=application.get(key):return False
        v=search[key]
        if key=="nights":
            if type(v) is not int or not 3<=v<=180:return False
        elif not isinstance(v,str) or not 1<=len(v)<=128:return False
    for key in ("browser_session_digest","party_digest"):
        if not re.fullmatch("[a-f0-9]{64}",search[key]):return False
    try:
        day=datetime.strptime(search["departure_date"],"%Y-%m-%d").date()
        if day<now.astimezone(timezone.utc).date():return False
    except (ValueError,TypeError):return False
    if application.get("hotel_available") is not True or application.get("flights_available") is not True:return False
    if application.get("mandatory_fees_included") is not True or application.get("final_price_observed") is not True or application.get("currency")!="RUB":return False
    if type(application.get("total_rub")) is not int or not 0<application["total_rub"]<=10_000_000:return False
    if application.get("submitted") is not False or application.get("booked") is not False:return False
    listed=_instant(search.get("clicked_at_utc"));observed=_instant(application.get("observed_at_utc"))
    if listed is None or observed is None:return False
    return listed<=observed<=now+timedelta(seconds=30) and observed-listed<=timedelta(minutes=10) and now-observed<=timedelta(minutes=15)
