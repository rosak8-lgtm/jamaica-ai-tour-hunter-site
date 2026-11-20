#!/usr/bin/env bash
# Read-only status for the user-owned JAMAICA listing refresh timer.
set -Eeuo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
echo "=== JAMAICA 15 MINUTE IMPORT TIMER ==="
if command -v systemctl >/dev/null; then
 systemctl --user is-enabled jamaica-tour-catalog-refresh.timer || true
 systemctl --user is-active jamaica-tour-catalog-refresh.timer || true
 systemctl --user list-timers --all jamaica-tour-catalog-refresh.timer || true
 systemctl --user show jamaica-tour-catalog-refresh.service \
   -p Result -p ExecMainStatus -p ActiveState -p InactiveExitTimestamp \
   --no-pager || true
else
 echo "NO_SYSTEMD_CLIENT"
fi
echo "=== PRIVATE USER SERVICE MODE ==="
if command -v loginctl >/dev/null; then
 loginctl show-user "$(id -un)" -p Linger -p State --no-pager || true
fi
echo "=== LATEST LOCAL PUBLISHED PREVIEW SNAPSHOT ==="
python3 -B - "$ROOT/tour-previews.json" <<'PY'
import json,sys
from pathlib import Path
p=Path(sys.argv[1])
if not p.is_file():
 print("CATALOG_NOT_FOUND")
else:
 try:
  o=json.loads(p.read_text(encoding="utf-8"))
  rows=o.get("previews",[])
  print("REFRESHED_AT_UTC="+str(o.get("refreshed_at_utc")))
  print("TOUR_PREVIEWS="+str(len(rows)))
  print("COUNTRIES_WITH_PREVIEWS="+str(len({x.get("country") for x in rows if isinstance(x,dict)})))
  print("TWO_ADULT_PRICES="+str(sum(isinstance(x,dict) and type(x.get("price_reference_rub")) is int for x in rows)))
 except (ValueError,OSError) as e:print("CATALOG_READ_HOLD="+type(e).__name__)
PY
echo "=== LAST 15 SAFE TIMER JOURNAL LINES ==="
if command -v journalctl >/dev/null; then
 journalctl --user -u jamaica-tour-catalog-refresh.service --no-pager -n 15 \
   -o cat 2>/dev/null | grep -E 'JAMAICA_|COUNTRIES_|PREVIEW_COUNT=|INDICATIVE_|PUBLIC_PREVIEWS_|STOP_' || true
fi
