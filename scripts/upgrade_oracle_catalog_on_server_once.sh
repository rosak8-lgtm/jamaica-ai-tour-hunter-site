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

# Keep a rollback copy, and never move the private deploy key or credentials.
git -C "$ROOT" fetch --depth=1 origin main
git -C "$ROOT" checkout --force -B main origin/main
git -C "$ROOT" reset --hard origin/main
python3 -B -m py_compile "$ROOT/scripts/oracle_site_publisher.py" \
  "$ROOT/scripts/oracle_bg_preview_export.py"
[[ -f "$SERVER/oracle_site_publisher.py" ]] || {
  echo "STOP_PREVIOUS_PUBLISHER_MISSING"; exit 2; }

# Pause new timer ticks but do not interrupt a running import.
systemctl --user stop "$TIMER"
timer_stopped=1
restore_timer(){
  if [[ "$timer_stopped" == 1 ]]; then
    systemctl --user start "$TIMER" || true
  fi
}
trap restore_timer EXIT
# Wait for a run already in progress; never kill a publication mid-push.
for i in $(seq 1 100); do
  [[ "$(systemctl --user is-active "$SERVICE")" != "active" ]] && break
  sleep 3
done
[[ "$(systemctl --user is-active "$SERVICE")" != "active" ]] || {
 echo "STOP_ORACLE_IMPORT_STILL_RUNNING"; exit 2; }

BACKUP="$(mktemp "$SERVER/oracle_site_publisher.py.old.XXXXXX")"
cp "$SERVER/oracle_site_publisher.py" "$BACKUP"
TMP="$(mktemp "$SERVER/oracle_site_publisher.py.new.XXXXXX")"
cp "$ROOT/scripts/oracle_site_publisher.py" "$TMP"
chmod 600 "$TMP"
mv -f "$TMP" "$SERVER/oracle_site_publisher.py"

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
rm -f "$BACKUP"
systemctl --user start "$TIMER"
timer_stopped=0
[[ "$(systemctl --user is-active "$TIMER")" == "active" ]] || {
  echo "STOP_ORACLE_TIMER_RESTART_FAILED"; exit 2; }
[[ "$(loginctl show-user "$(id -un)" -p Linger --value)" == "yes" ]] || {
  echo "STOP_ORACLE_LINGER_UNAVAILABLE"; exit 2; }
echo "JAMAICA_ORACLE_FIVE_MINUTE_TIMER=active"
echo "JAMAICA_ORACLE_NEW_SOURCE_SCAN=PASS"
echo "JAMAICA_ORACLE_CODE_UPDATES=FROM_SERVER_GITHUB_CLONE"
echo "JAMAICA_LENOVO_RECURRING_DEPENDENCY=NONE"
systemctl --user list-timers --all "$TIMER" --no-pager
journalctl --user -u "$SERVICE" -n 35 --no-pager -o cat 2>/dev/null |
 grep -E 'JAMAICA_|COUNTRIES_WITH_|PREVIEW_COUNT=|INDICATIVE_|PUBLIC_PREVIEWS_TRUNCATED' || true
SH
echo "JAMAICA_ORACLE_EXPANDED_COUNTRY_SCAN_UPGRADE_COMPLETE"
