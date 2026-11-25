#!/usr/bin/env bash
# Read-only Oracle proof-pipeline diagnosis from Lenovo. Never log raw receipts.
set -Eeuo pipefail
umask 077
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
[[ -r "$KEY" ]] || { echo "JAMAICA_DIAG_HOLD=LENOVO_ORACLE_KEY_UNAVAILABLE"; exit 2; }
ssh -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes \
 -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY" "$REMOTE" 'bash -s' <<'REMOTE_SH'
set -Eeuo pipefail
umask 077
[[ "$(id -un)" == "ubuntu" ]] || { echo "JAMAICA_DIAG_HOLD=WRONG_REMOTE_USER"; exit 2; }
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
ROOT="$HOME/.local/share/jamaica-oracle-catalog"
CLONE="$ROOT/site"
BIN="$HOME/.local/opt/jamaica-oracle-catalog"
CATALOG="jamaica-oracle-catalog-5min"
BOT="jamaica-website-bg-bot-v1"
echo "JAMAICA_VISUAL_PIPELINE_READ_ONLY_DIAGNOSTIC_V60"
for svc in "$CATALOG.timer" "$BOT.timer"; do
 state="$(systemctl --user is-active "$svc" 2>/dev/null || true)"
 printf 'TIMER_%s=%s\n' "$svc" "$state"
done
for svc in "$CATALOG.service" "$BOT.service"; do
 result="$(systemctl --user show "$svc" -p Result --value 2>/dev/null || true)"
 printf 'SERVICE_RESULT_%s=%s\n' "$svc" "$result"
done
if [[ -d "$CLONE/.git" ]]; then
 printf 'CATALOG_GIT_HEAD=%s\n' "$(git -C "$CLONE" rev-parse --short HEAD 2>/dev/null || echo unavailable)"
fi
if [[ -r "$BIN/oracle_site_publisher.py" && -r "$CLONE/scripts/oracle_site_publisher.py" ]]; then
 if cmp -s "$BIN/oracle_site_publisher.py" "$CLONE/scripts/oracle_site_publisher.py"; then
  echo "CATALOG_EXECUTABLE_EQUALS_GITHUB_CHECKOUT=YES"
 else
  echo "CATALOG_EXECUTABLE_EQUALS_GITHUB_CHECKOUT=NO"
 fi
 if grep -Fq 'eligibility.select_public_source_rows' "$BIN/oracle_site_publisher.py"; then
  echo "CATALOG_EXECUTABLE_STRICT_PUBLICATION_GATE=YES"
 else
  echo "CATALOG_EXECUTABLE_STRICT_PUBLICATION_GATE=NO"
 fi
else
 echo "CATALOG_EXECUTABLE_STATUS=MISSING"
fi
python3 -B - "$ROOT" <<'PY'
import json,os,stat,sys
from pathlib import Path
root=Path(sys.argv[1])
def inspect(path,maximum):
 try:
  info=path.lstat()
  if not stat.S_ISREG(info.st_mode) or info.st_size>maximum:
   return None,"NOT_REGULAR_OR_OVERSIZED"
  if info.st_uid!=os.geteuid():
   return None,"OWNER_MISMATCH"
  return json.loads(path.read_text(encoding="utf-8")),"OK"
 except FileNotFoundError:
  return None,"ABSENT"
 except (OSError,ValueError,UnicodeError):
  return None,"INVALID_OR_UNREADABLE"
private=root/"private-bg-route-first-receipts.json"
p,state=inspect(private,40_000_000)
if state=="OK" and stat.S_IMODE(private.stat().st_mode)&0o077:
 p,state=None,"INSECURE_PERMISSIONS"
print("PRIVATE_BG_RECEIPTS_STATE="+state)
records=p.get("records") if isinstance(p,dict) and p.get("schema")=="jamaica.bg-bot-private-receipts.v1" else None
print("PRIVATE_BG_RECEIPTS_COUNT="+str(len(records)) if isinstance(records,list) else "PRIVATE_BG_RECEIPTS_COUNT=0_OR_INVALID")
v,vstatus=inspect(root/"site/tour-visual-evidence.json",2_500_000)
print("PUBLIC_VISUAL_FEED_STATE="+vstatus)
print("PUBLIC_VISUAL_MATCHES="+str(len(v["entries"])) if isinstance(v,dict) and isinstance(v.get("entries"),list) else "PUBLIC_VISUAL_MATCHES=UNKNOWN")
c,cstatus=inspect(root/"site/tour-previews.json",45_000_000)
print("PUBLIC_CATALOG_FEED_STATE="+cstatus)
if isinstance(c,dict):
 print("PUBLIC_STRICT_PROJECTION_ENABLED="+("YES" if c.get("publication_rule")=="BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1" else "NO"))
 print("PUBLIC_FAST_ROOT_CARD_COUNT="+str(len(c["previews"])) if isinstance(c.get("previews"),list) else "PUBLIC_FAST_ROOT_CARD_COUNT=UNKNOWN")
 print("PUBLIC_TOTAL_CARD_COUNT="+str(c.get("total_published_previews","UNKNOWN")))
else:
 print("PUBLIC_STRICT_PROJECTION_ENABLED=UNKNOWN")
PY
echo "=== SAFE CATALOG PUBLISHER EVENTS ==="
journalctl --user -u "$CATALOG.service" --no-pager -o cat -n 160 2>/dev/null |
 grep -E '^JAMAICA_(VISUAL_ROUTE_FIRST_MATCHES|PUBLIC_VISUALLY_VERIFIED_TOURS|PUBLIC_HIDDEN_UNVERIFIED|ORACLE_5MIN_IMPORT_(PASS|HOLD)|BOT_VISUAL_STATUS|ORACLE_PUBLISH)=' |
 tail -n 25 || true
echo "JAMAICA_VISUAL_DIAGNOSTIC_COMPLETE=YES"
REMOTE_SH
