#!/usr/bin/env bash
# Validate Jamaica on Lenovo even if Node.js is not installed.
# Always run Python customer flow checks; JS VM checks run in CI or if node exists.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
python3 -B scripts/local_site_qa.py
python3 -B scripts/site_no_node_qa.py
if command -v node >/dev/null 2>&1; then
  node scripts/test-site.mjs
  echo "JAMAICA_JS_VM_TESTS_PASS=YES"
else
  echo "JAMAICA_JS_VM_TESTS_SKIPPED=NODE_NOT_INSTALLED_ON_LENOVO"
  echo "JAMAICA_JS_VM_TESTS_RUN_BY=GITHUB_ACTIONS"
fi
if python3 -c 'import playwright.sync_api' >/dev/null 2>&1; then
  python3 -B scripts/browser_smoke_playwright.py
else
  echo "JAMAICA_BROWSER_SMOKE_SKIPPED=PYTHON_PLAYWRIGHT_NOT_INSTALLED"
fi
echo "JAMAICA_LENOVO_PREFLIGHT_COMPLETE"
