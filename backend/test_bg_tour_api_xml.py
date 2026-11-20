import unittest
import xml.etree.ElementTree as ET

from backend.bg_tour_api_xml import (
  build_price_request, add_confirm_only_with_paid_gate, parse_price_response,
  parse_created_application, BadOrder, NotAvailable, url_for_prx
)

TOUR={
 "client_tour_id":"order_abcdefghijklmnop","prx":"TEST_PRX+123/==",
 "country_id":"100410504525","template_id":"121178311485",
 "roommeal_id":"104623691678","duration_nights":7,
 "start_date":"2026-12-11","sr":"TEST_FLIGHT_SR_123",
}
PASSENGERS=[{
 "birthday":"1990-06-15","first_name":"IVAN","last_name":"TESTOV",
 "citizenship":"100410000050","passport_series":"AA","passport_number":"12345678",
 "passport_expires":"2031-11-11","gender":"m"},
 {
 "birthday":"1992-03-14","first_name":"ANNA","last_name":"TESTOVA",
 "citizenship":"100410000050","passport_series":"BB","passport_number":"87654321",
 "passport_expires":"2032-11-11","gender":"f"}
]

class Tests(unittest.TestCase):
 def setUp(self):
  self.url,self.xml=build_price_request(TOUR,PASSENGERS)
 def test_price_request_readonly_and_all_passengers(self):
  self.assertEqual(self.url,
     "https://www.bgoperator.ru/zayavkaapi?prx=TEST_PRX%2B123%2F%3D%3D&action=createtour")
  root=ET.fromstring(self.xml)
  self.assertEqual(root.tag,"tours")
  item=root.find("tour")
  self.assertEqual(item.get("clientTourId"),TOUR["client_tour_id"])
  self.assertIsNone(item.find("confirm"))
  self.assertEqual(item.findtext("countryId"),TOUR["country_id"])
  self.assertEqual(item.findtext("templateId"),TOUR["template_id"])
  self.assertEqual(item.findtext("groups/group/startDate"),"11.12.2026")
  self.assertEqual(item.find("groups/group/roommeal").get("duration"),"7")
  self.assertEqual(len(item.findall("groups/group/persons/person")),2)
 def test_customer_identity_optional_private_gais_ep_fields(self):
  customer={
    "first_name":"IVAN","last_name":"IVANOV","middle_name":"IVANOVICH",
    "address":"MOSCOW, 14 TEST STREET","citizenship":"100410000050",
    "passport_series":"AA","passport_number":"12345678",
    "phone":"+79990000000","email":"ivan@example.org"
  }
  _,data=build_price_request(TOUR,PASSENGERS,customer)
  root=ET.fromstring(data)
  self.assertEqual(root.findtext("tour/customerFirstName"),"IVAN")
  self.assertEqual(root.findtext("tour/customerAddress"),"MOSCOW, 14 TEST STREET")
  self.assertEqual(root.findtext("tour/customerCitizen"),"100410000050")
  self.assertEqual(root.findtext("tour/customerEmail"),"ivan@example.org")
  self.assertIsNone(root.find("tour/confirm"))
  self.assertEqual(len(root.findall("tour/groups/group/persons/person")),2)
 def test_reject_invalid_gais_ep_customer(self):
  base={"first_name":"IVAN","last_name":"TESTOV","address":"TEST ADDRESS 21",
        "citizenship":"100410000050","passport_series":"AA",
        "passport_number":"12345678"}
  for wrong in (
     {**base,"citizenship":"bad"},
     {**base,"address":"<script>alert(1)</script>"},
     {**base,"email":"not-email"},
  ):
   with self.assertRaises(BadOrder):
    build_price_request(TOUR,PASSENGERS,wrong)
 def test_passenger_middle_name_and_absent_middle_name(self):
  people=[dict(p) for p in PASSENGERS]
  people[0]["middle_name"]="IVANOVICH"
  people[1]["no_middle_name"]=True
  _,data=build_price_request(TOUR,people)
  root=ET.fromstring(data)
  person=root.findall("tour/groups/group/persons/person")
  self.assertEqual(person[0].findtext("middleName"),"IVANOVICH")
  self.assertEqual(person[1].findtext("notHaveMiddleName"),"1")
 def test_private_confirm_needs_all_three_independent_gates(self):
  for flags in (
   {"paid_and_verified":False,"third_quote_exact":True,"buyer_contract_signature_verified":True},
   {"paid_and_verified":True,"third_quote_exact":False,"buyer_contract_signature_verified":True},
   {"paid_and_verified":True,"third_quote_exact":True,"buyer_contract_signature_verified":False},
  ):
   with self.assertRaises(BadOrder):
    add_confirm_only_with_paid_gate(self.xml,**flags)
  self.assertNotIn(b"<confirm",self.xml)
  confirmed=add_confirm_only_with_paid_gate(self.xml,paid_and_verified=True,
     third_quote_exact=True,buyer_contract_signature_verified=True)
  self.assertIsNotNone(ET.fromstring(confirmed).find("tour/confirm"))
  with self.assertRaises(BadOrder):
   add_confirm_only_with_paid_gate(confirmed,paid_and_verified=True,
     third_quote_exact=True,buyer_contract_signature_verified=True)
 def test_retains_optional_commission_id_without_template(self):
  d={**TOUR,"commission_id":"123456789","template_id":None}
  _,xml=build_price_request(d,PASSENGERS)
  node=ET.fromstring(xml)
  self.assertIsNone(node.find("tour/templateId"))
  self.assertEqual(node.findtext("tour/comissionId"),"123456789")
 def test_net_amount_is_never_sold_as_gross_price(self):
  response=b"""<tours><tour clientTourId="order_abcdefghijklmnop">
    <sum><currency>USD</currency><fullamount>1500</fullamount><amount>1350</amount></sum>
    <sum><currency>RUR</currency><fullamount>74563.0</fullamount>
         <comission>7438.0</comission><amount>67125.0</amount></sum>
    </tour></tours>"""
  got=parse_price_response(response,TOUR["client_tour_id"])
  self.assertEqual(got["total_rub"],74563)
  self.assertNotIn("67125",str(got))
 def test_missing_ruble_or_mismatched_tour_rejected(self):
  usd=b'<tours><tour clientTourId="order_abcdefghijklmnop"><sum><currency>USD</currency><fullamount>123.0</fullamount></sum></tour></tours>'
  with self.assertRaises(NotAvailable):
   parse_price_response(usd,TOUR["client_tour_id"])
  rub=b'<tours><tour clientTourId="OTHER"><sum><currency>RUR</currency><fullamount>12345</fullamount></sum></tour></tours>'
  with self.assertRaises(NotAvailable):
   parse_price_response(rub,TOUR["client_tour_id"])
 def test_application_response_is_submitted_not_confirmed(self):
  raw=b'<tours><tour clientTourId="order_abcdefghijklmnop"><id>104400000842366804</id><number>214150198</number></tour></tours>'
  result=parse_created_application(raw,TOUR["client_tour_id"])
  self.assertEqual(result["status"],"SUBMITTED")
  self.assertFalse(result["hotel_confirmed"])
  self.assertFalse(result["flight_confirmed"])
  self.assertNotIn("CONFIRMED",str(result))
 def test_external_entities_and_doctype_rejected(self):
  hostile=b'<!DOCTYPE tours [<!ENTITY e SYSTEM "file:///etc/passwd">]><tours/>'
  with self.assertRaises(NotAvailable):
   parse_price_response(hostile,TOUR["client_tour_id"])
 def test_bad_operator_data_never_creates_bookable_xml(self):
  for bad in (
   {**TOUR,"sr":"\nNOT_A_SECRET"},
   {**TOUR,"template_id":None},
   {**TOUR,"commission_id":"11111111"},
   {**TOUR,"roommeal_id":"abc"},
  ):
   with self.assertRaises(BadOrder):
    build_price_request(bad,PASSENGERS)
 def test_passengers_not_printed_or_logged_by_module(self):
  self.assertEqual(url_for_prx("TEST_PRX+123/=="),self.url)
  self.assertNotIn("IVAN",self.url)
  self.assertNotIn("12345678",self.url)

if __name__=="__main__":unittest.main()
