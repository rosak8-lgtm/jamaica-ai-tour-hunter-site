"""Regression coverage for RUB price lists, without declaring a verified quote."""
import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent.parent/"scripts"))
import oracle_bg_selected_quote_probe as s

class TestRubList(unittest.TestCase):
    def setUp(self):
        self.preview={"id":"p_"+"1"*24}
        self.hotel={}
    def test_rub_amount_is_ruble_reference_for_two_adults(self):
        self.assertTrue(s.rub_option_amount({"amount":"52067"},"RUB"))
        self.assertTrue(s.rub_option_amount({"amount":"52067"},"RUR"))
    def test_other_currency_requires_explicit_rur(self):
        self.assertFalse(s.rub_option_amount({"amount":"999"},"USD"))
        self.assertTrue(s.rub_option_amount({"amount":"999","RUR":"72100"},"USD"))
    def test_unknown_currency_without_rur_blocked(self):
        self.assertFalse(s.rub_option_amount({"amount":"999"},None))
        self.assertFalse(s.rub_option_amount({"amount":"999"},"???"))
    def test_bad_amount_blocked(self):
        for v in ["NaN","Infinity",True,0,[],{}]:
            self.assertFalse(s.rub_option_amount({"amount":v},"RUB"))
if __name__=="__main__":unittest.main()
