import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import tour_price_reference as price
class TestIndicativeRubleReference(unittest.TestCase):
 def test_non_rub_currency_uses_rur_for_two_adults(self):
  source=[{"ag":"12+,12+","amount":"1400","RUR":"115000"}]
  self.assertEqual(price.indicative_two_adult_rub(source,"EUR"),115000)
  self.assertEqual(price.indicative_two_adult_rub(source,"RUB"),1400)
 def test_native_ruble_amount(self):
  self.assertEqual(price.indicative_two_adult_rub([{"ag":"12+,12+","amount":"55000"}],"RUB"),55000)
 def test_bracket_pair(self):
  self.assertTrue(price.adult_pair("[14-99][14-99]"))
  self.assertTrue(price.adult_pair("12-99,12-99"))
  self.assertFalse(price.adult_pair("2-11,12+"))
  self.assertFalse(price.adult_pair("12+,2-11"))
 def test_no_guesses_on_missing_currency(self):
  self.assertIsNone(price.indicative_two_adult_rub([{"ag":"12+,12+","RUR":"78000"}],None))
  self.assertIsNone(price.indicative_two_adult_rub([{"ag":"12+,12+","amount":"78000"}],"UNKNOWN"))
 def test_reject_invalid_price(self):
  for bad in (None,"","0","-1","NaN","Infinity","1.5",[],{},True):
   self.assertIsNone(price.positive_rub(bad))
 def test_price_stops_and_children(self):
  rows=[{"ag":"12+,12+","RUR":"12000","isstop":["avia_to"]},
        {"ag":"2-11,12+","RUR":"10000"}]
  self.assertIsNone(price.indicative_two_adult_rub(rows,"EUR"))
 def test_minimum_same_party(self):
  rows=[{"ag":"12+,12+","RUR":"80000"},{"ag":"12+,12+","RUR":"70000"}]
  self.assertEqual(price.indicative_two_adult_rub(rows,"EUR"),70000)
 def test_no_flight_booking_claims_from_quoted_price(self):
  # The parser exposes a reference price ONLY.
  self.assertEqual(price.indicative_two_adult_rub([{"ag":"12+,12+","amount":"30000"}],"RUB"),30000)
if __name__=="__main__":unittest.main()
