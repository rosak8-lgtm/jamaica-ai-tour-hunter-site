import unittest
import urllib.request
import xml.etree.ElementTree as ET

from backend.bg_read_only_price_client import (
  BGReadOnlyPriceClient,_NeverFollowRedirect,_safe_price_url,
  _require_read_only_xml,BadOrder,NotAvailable
)
from backend.test_bg_tour_api_xml import TOUR,PASSENGERS
from backend.bg_tour_api_xml import build_price_request,add_confirm_only_with_paid_gate

RESPONSE=b'<tours><tour clientTourId="order_abcdefghijklmnop"><sum><currency>RUR</currency><fullamount>125000</fullamount><comission>10000</comission><amount>115000</amount></sum></tour></tours>'

class Response:
 def __init__(self,data):self.status=200;self.data=data
 def read(self,n):return self.data[:n]
 def __enter__(self):return self
 def __exit__(self,*args):return False

class FakeOpener:
 def __init__(self):self.calls=[]
 def open(self,req,timeout):
  self.calls.append(req)
  if req.full_url=="https://login.bgoperator.ru/auth":
   return Response(b'OK')
  return Response(RESPONSE)

class Tests(unittest.TestCase):
 def test_private_login_then_price_only_readonly(self):
  opener=FakeOpener()
  client=BGReadOnlyPriceClient("agency_test","TEST_PASSWORD",opener=opener)
  result=client.price_only(TOUR,PASSENGERS)
  self.assertEqual(result["total_rub"],125000)
  self.assertFalse(result["bookable"])
  self.assertFalse(result["flight_verified"])
  self.assertFalse(result["hotel_verified"])
  self.assertEqual(len(opener.calls),2)
  login,quote=opener.calls
  self.assertEqual(login.full_url,"https://login.bgoperator.ru/auth")
  self.assertIn(b"login=agency_test",login.data)
  self.assertEqual(quote.get_method(),"POST")
  self.assertTrue(_safe_price_url(quote.full_url))
  self.assertNotIn(b"<confirm",quote.data)
  self.assertEqual(ET.fromstring(quote.data).find("tour/groups/group/persons/person/firstName").text,"IVAN")
  self.assertNotIn("TEST_PASSWORD",str(result))
  client.price_only(TOUR,PASSENGERS)
  self.assertEqual(len(opener.calls),3)
 def test_booking_xml_is_rejected_before_network(self):
  url,raw=build_price_request(TOUR,PASSENGERS)
  booking=add_confirm_only_with_paid_gate(raw,paid_and_verified=True,
     third_quote_exact=True,buyer_contract_signature_verified=True)
  with self.assertRaises(BadOrder):
   _require_read_only_xml(booking)
 def test_price_url_allowlist(self):
  expected=build_price_request(TOUR,PASSENGERS)[0]
  self.assertTrue(_safe_price_url(expected))
  for url in (
    "http://www.bgoperator.ru/zayavkaapi?prx=1&action=createtour",
    "https://evil.example/zayavkaapi?prx=1&action=createtour",
    "https://www.bgoperator.ru/zayavkaapi?action=createtour&prx=1",
    "https://www.bgoperator.ru/zayavkaapi?prx=1&action=confirm",
    "https://www.bgoperator.ru/zayavkaapi?prx=1&action=createtour&x=1",
  ):
   self.assertFalse(_safe_price_url(url),url)
 def test_redirects_never_followed(self):
  handler=_NeverFollowRedirect()
  with self.assertRaises(NotAvailable):
   handler.redirect_request(None,None,302,"redirect",{},"https://other.example")
 def test_mismatched_customer_response_cannot_give_sale_price(self):
  class Wrong(FakeOpener):
   def open(self,req,timeout):
    self.calls.append(req)
    if req.full_url.endswith("/auth"):return Response(b"OK")
    return Response(b'<tours><tour clientTourId="other"><sum><currency>RUR</currency><fullamount>100000</fullamount></sum></tour></tours>')
  with self.assertRaises(NotAvailable):
   BGReadOnlyPriceClient("login","password",opener=Wrong()).price_only(TOUR,PASSENGERS)
 def test_no_login_or_no_password_rejected(self):
  with self.assertRaises(BadOrder):
   BGReadOnlyPriceClient("","password")
  with self.assertRaises(BadOrder):
   BGReadOnlyPriceClient("user","")

if __name__=="__main__":
 unittest.main()
