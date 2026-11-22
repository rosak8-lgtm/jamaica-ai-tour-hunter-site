#!/usr/bin/env bash
# ONE TIME ONLY from Lenovo: bootstrap Oracle SSH deploy key and 5-minute timer.
# After success, turn off the old Lenovo timer. Oracle is then independent.
# Never copies gh auth token, BG passwords, private keys, or personal info.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
REPO="rosak8-lgtm/jamaica-ai-tour-hunter-site"
REMOTE="ubuntu@92.5.184.47"
KEY="$HOME/.ssh/jamaica-oracle.key"
SERVER_DIR="/home/ubuntu/.local/opt/jamaica-oracle-catalog"
DEPLOY_PRIVATE="/home/ubuntu/.ssh/jamaica_catalog_deploy_ed25519"

test -r "$KEY" || { echo "STOP_ORACLE_ACCESS_MISSING"; exit 2; }
for cmd in ssh scp gh; do
 command -v "$cmd" >/dev/null || { echo "STOP_REQUIRED_COMMAND=$cmd"; exit 2; }
done
[[ "$(gh api user --jq .login)" == "rosak8-lgtm" ]] || {
 echo "STOP_GITHUB_USER_MISMATCH"; exit 2; }

for name in oracle_site_publisher.py oracle_bg_preview_export.py \
 oracle_bg_price_detail_probe.py oracle_bg_route_sync.py \
 tour_price_reference.py sync_destination_directory.py \
 recent_preview_catalog.py catalog_size_budget.py \
 oracle_install_catalog_timer.sh; do
 test -r "$ROOT/scripts/$name" || { echo "STOP_REQUIRED_SCRIPT_MISSING=$name"; exit 2; }
done

SSH=(ssh -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes \
     -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")
SCP=(scp -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes \
     -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY")

echo "=== CREATE A REPOSITORY-ONLY DEPLOY KEY ON ORACLE ==="
PUBLIC_KEY="$("${SSH[@]}" "$REMOTE" 'bash -s' <<'REMOTE_SH'
set -Eeuo pipefail
umask 077
KEY="$HOME/.ssh/jamaica_catalog_deploy_ed25519"
mkdir -p "$HOME/.ssh"
chmod 700 "$HOME/.ssh"
if [[ ! -e "$KEY" && ! -e "$KEY.pub" ]]; then
  ssh-keygen -q -t ed25519 -N "" -C "jamaica-oracle-catalog-only" -f "$KEY"
fi
test -r "$KEY" && test -r "$KEY.pub"
chmod 600 "$KEY"
cat "$KEY.pub"
REMOTE_SH
)"
[[ "$PUBLIC_KEY" =~ ^ssh-ed25519\  ]] || {
 echo "STOP_ORACLE_PUBLIC_DEPLOY_KEY_INVALID"; exit 2; }
echo "JAMAICA_ORACLE_DEPLOY_KEY_GENERATED=YES"

echo "=== AUTHORIZE ORACLE KEY ONLY FOR THE JAMAICA REPOSITORY ==="
PUBLIC_KEY_MATERIAL="$(printf '%s\n' "$PUBLIC_KEY" | awk '{print $2}')"
if gh api "repos/$REPO/keys" --jq '.[].key' 2>/dev/null |
   awk '{print $2}' | grep -Fxq "$PUBLIC_KEY_MATERIAL"; then
 echo "JAMAICA_REPOSITORY_DEPLOY_KEY=EXISTS"
else
 if gh api -X POST "repos/$REPO/keys" \
    -f title="JAMAICA Oracle catalog 5-minute autonomous publisher" \
    -f key="$PUBLIC_KEY" -F read_only=false --jq '.id' >/dev/null; then
   echo "JAMAICA_REPOSITORY_DEPLOY_KEY=REGISTERED_WITH_WRITE"
 else
   echo "STOP_DEPLOY_KEY_INSTALL_GITHUB_ADMIN_PERMISSION_REQUIRED"
   echo "Add this PUBLIC key in the Jamaica GitHub repository Settings > Deploy keys, enable write access:"
   printf '%s\n' "$PUBLIC_KEY"
   echo "Then rerun the installer. Private key remains exclusively on Oracle."
   exit 2
 fi
fi

echo "=== COPY ONLY PUBLIC-SAFE SERVER SOFTWARE TO ORACLE ==="
"${SSH[@]}" "$REMOTE" "umask 077; mkdir -p '$SERVER_DIR'; chmod 700 '$SERVER_DIR'"
for name in oracle_site_publisher.py oracle_bg_preview_export.py \
 oracle_bg_price_detail_probe.py oracle_bg_route_sync.py \
 tour_price_reference.py sync_destination_directory.py \
 recent_preview_catalog.py catalog_size_budget.py \
 oracle_install_catalog_timer.sh; do
 "${SCP[@]}" "$ROOT/scripts/$name" "$REMOTE:$SERVER_DIR/$name"
done

echo "=== START AND VERIFY ORACLE FIVE-MINUTE SERVER-ONLY IMPORT ==="
"${SSH[@]}" "$REMOTE" "bash '$SERVER_DIR/oracle_install_catalog_timer.sh'"

echo "=== DISABLE OLD LENOVO TIMER AFTER ORACLE SUCCESS ==="
if systemctl --user is-enabled jamaica-tour-catalog-refresh.timer >/dev/null 2>&1 ||
   systemctl --user is-active jamaica-tour-catalog-refresh.timer >/dev/null 2>&1; then
  systemctl --user disable --now jamaica-tour-catalog-refresh.timer
  echo "JAMAICA_LENOVO_15MIN_TIMER=DISABLED"
else
  echo "JAMAICA_LENOVO_15MIN_TIMER=NOT_RUNNING"
fi

echo "=== FINAL SERVER TIMER HEALTH ==="
"${SSH[@]}" "$REMOTE" 'bash -s' <<'STATUS_SH'
set -Eeuo pipefail
export XDG_RUNTIME_DIR="/run/user/$(id -u)"
systemctl --user is-active jamaica-oracle-catalog-5min.timer
systemctl --user list-timers --all jamaica-oracle-catalog-5min.timer --no-pager
systemctl --user show jamaica-oracle-catalog-5min.service \
 -p Result -p ExecMainStatus -p ActiveState --no-pager
loginctl show-user "$(id -un)" -p Linger --no-pager
STATUS_SH
echo "JAMAICA_ORACLE_INDEPENDENT_5MIN_PUBLISHER_COMPLETE"
