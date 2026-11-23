"""Read-only Lenovo browser bot source scanner must not print source secrets."""
import json
from pathlib import Path
import tempfile
import unittest
from scripts.audit_bot_route_first_from_lenovo import inspect_source,inspect_roots

class Tests(unittest.TestCase):
    def test_bot_script_function_report_includes_ordered_evidence_without_source(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"bg_browser_v148.py"
            secret="SUPER_SECRET_ACCOUNT_PASSWORD_123456789"
            p.write_text(
                "from playwright.sync_api import sync_playwright\n"
                "def choose_route(page):\n"
                "  page.get_by_text('ЛУЧШАЯ ЦЕНА').click()\n"
                "  password='"+secret+"'\n"
                "def check_two_green(page):\n"
                "  return page.locator('.both_green_flights_verified').count()\n",
                encoding="utf-8")
            report=inspect_source(p)
            self.assertTrue(report["best_price"])
            self.assertTrue(report["green_flights"])
            self.assertTrue(report["click"])
            self.assertTrue(report["browser"])
            self.assertEqual([f["name"] for f in report["functions"]],
                             ["choose_route","check_two_green"])
            self.assertNotIn(secret,json.dumps(report))
            self.assertNotIn("get_by_text",json.dumps(report))
            self.assertNotIn("password",json.dumps(report))

    def test_bot_scan_never_follows_symlink_or_other_directory(self):
        with tempfile.TemporaryDirectory() as tmp:
            home=Path(tmp)
            user=home/"JAMAICA_V167_BG_VERIFIABLE_FUNNEL_20261122"
            user.mkdir()
            src=user/"capture_bg_v148.js"
            src.write_text(
                "const x='ЛУЧШАЯ ЦЕНА';"
                "const g='both_green_flights_verified';"
                "page.locator(x).click();",encoding="utf-8")
            foreign=home/"some_private_credentials.py"
            foreign.write_text("def best_price(): return 'PASSWORD'",encoding="utf-8")
            alias=user/"alias.py"
            alias.symlink_to(foreign)
            found,scanned,truncated=inspect_roots(home)
            self.assertFalse(truncated)
            self.assertEqual(scanned,2)
            self.assertEqual(len(found),1)
            self.assertTrue(found[0]["file"].endswith("capture_bg_v148.js"))
            self.assertNotIn("some_private_credentials",str(found))
            self.assertNotIn("PASSWORD",str(found))

    def test_no_secrets_in_debug_even_on_irrelevant_browser_modules(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/"bot.py"
            p.write_text("token='PRIVATE_API_TOKEN_999'\n"
                         "def hello(): pass\n")
            self.assertIsNone(inspect_source(p))

if __name__=="__main__":
    unittest.main()
