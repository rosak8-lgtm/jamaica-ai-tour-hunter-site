"""Authorized READ-ONLY official tour retail price client.

Private backend ONLY. This module has exactly one externally callable supplier
operation: obtaining a retail quote via a <tour> XML WITHOUT <confirm/>.
No method here can create, confirm, cancel or update a booking.

Credentials injected from a PRIVATE secret provider; never put them in
GitHub/pages, log request URL (it contains prx), log passengers or persist XML.
Requires verified buyer/consent and supplier API permission before production.
"""
from __future__ import annotations

import http.cookiejar
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET

from backend.bg_tour_api_xml import build_price_request, parse_price_response
from backend.order_engine import BadOrder, NotAvailable

LOGIN_URL="https://login.bgoperator.ru/auth"
PRICE_SCHEME="https"
PRICE_HOST="www.bgoperator.ru"
PRICE_PATH="/zayavkaapi"
MAX_RESPONSE=65536

class _NeverFollowRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self,request,fp,code,msg,headers,newurl):
        # Even on login, follow no redirects: protects credentials and prx.
        raise NotAvailable("Operator API redirect blocked")

def _default_opener():
    return urllib.request.build_opener(
        urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()),
        _NeverFollowRedirect())

def _safe_price_url(url:str)->bool:
    try:
        p=urllib.parse.urlsplit(url)
        q=urllib.parse.parse_qsl(p.query,keep_blank_values=True)
        return (p.scheme==PRICE_SCHEME and p.netloc==PRICE_HOST and
                p.path==PRICE_PATH and not p.fragment and
                len(q)==2 and q[0][0]=="prx" and q[0][1] and
                q[1]==("action","createtour"))
    except (ValueError,TypeError):
        return False

def _require_read_only_xml(data:bytes):
    if not isinstance(data,bytes) or len(data)>MAX_RESPONSE or not data:
        raise BadOrder("Invalid private price request size")
    if b"<!DOCTYPE" in data.upper() or b"<!ENTITY" in data.upper():
        raise BadOrder("DTD/ENTITY forbidden")
    try:
        root=ET.fromstring(data)
    except ET.ParseError as exc:
        raise BadOrder("Invalid price request XML") from exc
    if root.tag!="tours" or len(root)!=1 or root[0].tag!="tour":
        raise BadOrder("Exactly one pricing inquiry is allowed")
    if root.find(".//confirm") is not None:
        raise BadOrder("Booking confirmation forbidden in price-only client")

class BGReadOnlyPriceClient:
    def __init__(self,login:str,password:str,*,opener=None):
        if (not isinstance(login,str) or not login or len(login)>256 or
            not isinstance(password,str) or not password or len(password)>512):
            raise BadOrder("Private operator credentials required")
        self._login=login
        self._password=password
        self._opener=opener if opener is not None else _default_opener()
        self._authenticated=False

    def _open(self,request:urllib.request.Request)->bytes:
        # Never return exception details containing login/password/prx or passenger data.
        try:
            with self._opener.open(request,timeout=25) as response:
                if response.status!=200:
                    raise NotAvailable("Operator API did not accept the request")
                data=response.read(MAX_RESPONSE+1)
                if len(data)>MAX_RESPONSE:
                    raise NotAvailable("Operator response too large")
                return data
        except NotAvailable:
            raise
        except (OSError,urllib.error.HTTPError,urllib.error.URLError,
                TimeoutError,ValueError) as exc:
            raise NotAvailable("Authorized operator API unavailable") from None

    def _authenticate(self):
        login_body=urllib.parse.urlencode({"login":self._login,
                                           "pwd":self._password}).encode("utf-8")
        request=urllib.request.Request(
            LOGIN_URL,data=login_body,
            headers={"Content-Type":"application/x-www-form-urlencoded",
                     "Accept":"text/html,application/json"},
            method="POST")
        self._open(request)
        self._authenticated=True

    def price_only(self,tour:dict,passengers:list[dict])->dict:
        """Read-only cost inquiry. Caller MUST authenticate/authorize buyer."""
        url,body=build_price_request(tour,passengers)
        if not _safe_price_url(url):
            raise BadOrder("Operator API URL is not allowlisted")
        _require_read_only_xml(body)
        if not self._authenticated:
            self._authenticate()
        request=urllib.request.Request(
            url,data=body,
            headers={"Content-Type":"application/xml; charset=utf-8",
                     "Accept":"application/xml"},
            method="POST")
        raw=self._open(request)
        result=parse_price_response(raw,tour["client_tour_id"])
        # Authoritative PRICE only: this does not prove seats, hotel quota or
        # finalized accommodation and must NEVER be advertised as bookable.
        result["flight_verified"]=False
        result["hotel_verified"]=False
        result["bookable"]=False
        return result
