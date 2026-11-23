"""V183 AST contract inspection cannot run bot or expose secrets."""
import tempfile
from pathlib import Path
import json
import unittest
from scripts.inspect_v183_bot_contract_from_lenovo import inspect

class Tests(unittest.TestCase):
    def test_only_source_key_names_are_returned(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"JAMAICA_V183_DUAL_TELEGRAM_DELIVERY_20261123"
            root.mkdir()
            secret="BOT_SUPPLIER_PASSWORD_PRIVATE_34567890123456789"
            (root/"bg_browser_v148.py").write_text(
                "def send_best_observed(page):\n"
                "  PASSWORD='"+secret+"'\n"
                "  page.locator('ЛУЧШАЯ ЦЕНА').click()\n"
                "  return {'best_price': True, 'country':'Таиланд', "
                "'token':PASSWORD, 'both_green':True}\n",
                encoding="utf8")
            res=inspect(Path(d))
            self.assertEqual(len(res),1)
            serialized=json.dumps(res,ensure_ascii=False)
            self.assertNotIn(secret,serialized)
            self.assertNotIn("PASSWORD",serialized)
            self.assertNotIn("ЛУЧШАЯ ЦЕНА",serialized)
            self.assertEqual(res[0]["contract"][0]["safe_result_keys"],
                             ["best_price","both_green","country"])
            self.assertIn("click",res[0]["contract"][0]["safe_calls"])
    def test_symlinked_source_is_not_followed(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/"JAMAICA_V183_DUAL_TELEGRAM_DELIVERY_20261123"
            root.mkdir()
            hidden=Path(d)/"supplier_secret.py"
            hidden.write_text("def best_price():return 'PASSWORD'\n")
            (root/"bg_browser_v148.py").symlink_to(hidden)
            self.assertEqual(inspect(Path(d)),[])

if __name__=="__main__":unittest.main()
