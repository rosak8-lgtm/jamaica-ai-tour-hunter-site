#!/usr/bin/env bash
# One-time safe upgrade of the already-running Oracle JAMAICA publisher.
# After this, all future exporter changes are read from the server's Git clone.
# Lenovo only initiates this single SSH call; the 5-minute timer stays on Oracle.
set -Eeuo pipefail
umask 077
REMOTE="ubuntu@92.5.184.47"
KEY="$HOME/.ssh/jamaica-oracle.key"
[[ -r "$KEY" ]] || { echo "STOP_LENOVO_SSH_KEY_MISSING"; exit 2; }
ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes \
    -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY" "$REMOTE" 'bash -s' <<'SH'
set -Eeuo pipefail
umask 077
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP_NOT_ORACLE_UBUNTU"; exit 2; }
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
ROOT="$HOME/.local/share/jamaica-oracle-catalog/site"
SERVER="$HOME/.local/opt/jamaica-oracle-catalog"
KEY="$HOME/.ssh/jamaica_catalog_deploy_ed25519"
HOSTS="$HOME/.ssh/jamaica_catalog_known_hosts"
SERVICE="jamaica-oracle-catalog-5min.service"
TIMER="jamaica-oracle-catalog-5min.timer"
[[ -d "$ROOT/.git" && -r "$KEY" && -r "$HOSTS" ]] || {
  echo "STOP_ORACLE_PUBLISHER_NOT_INSTALLED"; exit 2; }
[[ "$(systemctl --user is-active "$TIMER")" == "active" ]] || {
  echo "STOP_ORACLE_TIMER_NOT_ACTIVE"; exit 2; }
export GIT_SSH_COMMAND="ssh -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOSTS -o ConnectTimeout=15 -i $KEY"
export GIT_TERMINAL_PROMPT=0

# Stop only the publisher's timer. Its already-running service must finish.
# A oneshot service is "activating", not "active", during execution.
systemctl --user stop "$TIMER"
timer_stopped=1
restore_timer(){
  if [[ "$timer_stopped" == 1 ]]; then
    systemctl --user start "$TIMER" || true
  fi
}
trap restore_timer EXIT
LOCK="$HOME/.cache/jamaica-oracle-catalog/refresh.lock"
[[ -d "$(dirname "$LOCK")" && ! -L "$LOCK" ]] || {
  echo "STOP_PUBLISHER_LOCK_UNSAFE"; exit 2; }
# Use the same lock as ExecStart, BEFORE modifying the dedicated checkout.
exec 9>"$LOCK"
flock -w 300 9 || { echo "STOP_ORACLE_IMPORT_STILL_RUNNING"; exit 2; }
state="$(systemctl --user show "$SERVICE" -p ActiveState --value)"
case "$state" in
  inactive|failed) ;;
  *) echo "STOP_ORACLE_IMPORT_NOT_IDLE=$state"; exit 2 ;;
esac

# Keep a rollback copy, and never move the private deploy key or credentials.
git -C "$ROOT" fetch --depth=1 origin main
git -C "$ROOT" checkout --force -B main origin/main
git -C "$ROOT" reset --hard origin/main
python3 -B -m py_compile "$ROOT/scripts/oracle_site_publisher.py" \
  "$ROOT/scripts/oracle_bg_preview_export.py" \
  "$ROOT/scripts/recent_preview_catalog.py" \
  "$ROOT/scripts/catalog_size_budget.py" \
  "$ROOT/scripts/bot_visual_sidecar.py" \
  "$ROOT/scripts/public_tour_eligibility.py" \
  "$ROOT/scripts/site_bot_price_overlay.py" \
  "$ROOT/scripts/catalog_property_identity.py" \
  "$ROOT/backend/bg_route_first_visual_gate.py"
[[ -f "$SERVER/oracle_site_publisher.py" ]] || {
  echo "STOP_PREVIOUS_PUBLISHER_MISSING"; exit 2; }
# Do not install a publisher that only prints old source-price-list tours.
grep -Fq 'eligibility.select_public_source_rows(new,visual_public)' \
 "$ROOT/scripts/oracle_site_publisher.py" || {
  echo "STOP_SOURCE_PUBLISHER_HAS_NO_BEST_PRICE_BOTH_GREEN_GATE"; exit 2; }
grep -Fq 'browser_price.apply(published' \
 "$ROOT/scripts/oracle_site_publisher.py" || {
  echo "STOP_SOURCE_PUBLISHER_HAS_NO_TRUSTED_DOM_PRICE_OVERLAY"; exit 2; }

BACKUP="$(mktemp "$SERVER/oracle_site_publisher.py.old.XXXXXX")"
cp "$SERVER/oracle_site_publisher.py" "$BACKUP"
TMP="$(mktemp "$SERVER/oracle_site_publisher.py.new.XXXXXX")"
cp "$ROOT/scripts/oracle_site_publisher.py" "$TMP"
chmod 600 "$TMP"
mv -f "$TMP" "$SERVER/oracle_site_publisher.py"

echo "JAMAICA_ORACLE_PUBLISHER_SHA256=$(sha256sum "$SERVER/oracle_site_publisher.py" | cut -d" " -f1)"
cmp -s "$ROOT/scripts/oracle_site_publisher.py" "$SERVER/oracle_site_publisher.py" || { echo "STOP_PUBLISHER_COPY_MISMATCH"; exit 2; }
# The service itself acquires this lock; release before starting it.
flock -u 9
exec 9>&-
echo "=== VERIFY FIRST FULL SOURCE-BASED SCAN ON ORACLE ==="
if ! systemctl --user start "$SERVICE"; then
  cp "$BACKUP" "$SERVER/oracle_site_publisher.py"
  echo "STOP_ORACLE_NEW_PUBLISHER_FAILED_ROLLED_BACK"
  exit 2
fi
result="$(systemctl --user show "$SERVICE" -p Result --value)"
if [[ "$result" != "success" ]]; then
  cp "$BACKUP" "$SERVER/oracle_site_publisher.py"
  echo "STOP_ORACLE_NEW_PUBLISHER_NOT_SUCCESSFUL_ROLLED_BACK"
  exit 2
fi
# Confirm the actually running service wrote strict projection, NOT just
# the executable path. A success status without source-proof filtering
# must not be reported as a successful deployment.
if ! python3 -B - "$ROOT" <<'PY'
import json,sys
from pathlib import Path
base=Path(sys.argv[1])
try:
    catalog=json.loads((base/"tour-previews.json").read_text(encoding="utf-8"))
    visual=json.loads((base/"tour-visual-evidence.json").read_text(encoding="utf-8"))
    assert catalog["schema"]=="jamaica.tour-previews.v1"
    assert catalog["publication_rule"]=="BG_ROUTE_FIRST_BEST_PRICE_BOTH_GREEN_V1"
    assert visual["schema"]=="jamaica.visual-selection.v1"
    evidence={e["preview_id"] for e in visual["entries"]
              if e.get("route_best_price_seen") is True and
                 e.get("both_green_planes_seen") is True}
    assert catalog.get("total_published_previews",0)<=len(evidence)
    for item in catalog.get("previews",[]):
        assert item["id"] in evidence
    for entry in catalog.get("shards",[]):
        path=base/entry["path"]
        assert path.resolve().is_relative_to(base.resolve())
        shard=json.loads(path.read_text(encoding="utf-8"))
        assert all(row["id"] in evidence for row in shard["previews"])
    print("JAMAICA_SERVER_STRICT_VISUAL_PROJECTION_VERIFIED=YES")
except (OSError,ValueError,AssertionError,KeyError,TypeError):
    raise SystemExit(2)
PY
then
  cp "$BACKUP" "$SERVER/oracle_site_publisher.py"
  echo "STOP_ORACLE_STRICT_VISUAL_PROJECTION_NOT_PROVEN_ROLLED_BACK"
  exit 2
fi
rm -f "$BACKUP"
systemctl --user start "$TIMER"
timer_stopped=0
[[ "$(systemctl --user is-active "$TIMER")" == "active" ]] || {
  echo "STOP_ORACLE_TIMER_RESTART_FAILED"; exit 2; }
[[ "$(loginctl show-user "$(id -un)" -p Linger --value)" == "yes" ]] || {
  echo "STOP_ORACLE_LINGER_UNAVAILABLE"; exit 2; }
echo "JAMAICA_ORACLE_FIVE_MINUTE_TIMER=active"
echo "JAMAICA_ORACLE_STRICT_PUBLISHER_RUN=PASS"
echo "JAMAICA_ORACLE_CODE_UPDATES=FROM_SERVER_GITHUB_CLONE"
echo "JAMAICA_LENOVO_RECURRING_DEPENDENCY=NONE"
systemctl --user list-timers --all "$TIMER" --no-pager
journalctl --user -u "$SERVICE" -n 35 --no-pager -o cat 2>/dev/null |
 grep -E 'JAMAICA_|COUNTRIES_WITH_|PREVIEW_COUNT=|INDICATIVE_|PUBLIC_PREVIEWS_TRUNCATED' || true
SH
echo "JAMAICA_ORACLE_EXPANDED_COUNTRY_SCAN_UPGRADE_COMPLETE"
