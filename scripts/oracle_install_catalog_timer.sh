#!/usr/bin/env bash
# Run ON ORACLE ubuntu. Installs a permanently running five-minute timer.
# This file is public-safe: no API tokens, logins or passwords in unit files.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")" && pwd)"
HOME_DIR="$HOME"
SERVICE_NAME="jamaica-oracle-catalog-5min"
KEY="$HOME/.ssh/jamaica_catalog_deploy_ed25519"
HOSTS="$HOME/.ssh/jamaica_catalog_known_hosts"
GITHUB_FINGERPRINT='SHA256:+DiY3wvvV6TuJJhbpZisF/zLDA0zPMSvHdkr4UvCOqU'
REPO='git@github.com:rosak8-lgtm/jamaica-ai-tour-hunter-site.git'

[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP_EXPECTED_ORACLE_UBUNTU"; exit 2; }
for cmd in python3 git ssh ssh-keygen ssh-keyscan flock systemctl loginctl; do
 command -v "$cmd" >/dev/null || { echo "STOP_REQUIRED_COMMAND=$cmd"; exit 2; }
done
[[ -r "$KEY" && -r "$KEY.pub" ]] || { echo "STOP_SERVER_DEPLOY_KEY_MISSING"; exit 2; }
[[ -r "$ROOT/oracle_site_publisher.py" && -r "$ROOT/oracle_bg_preview_export.py" ]] || {
 echo "STOP_SERVER_PUBLISHER_FILES_MISSING"; exit 2; }

mkdir -p "$HOME/.ssh" "$HOME/.cache/jamaica-oracle-catalog" "$HOME/.config/systemd/user"
chmod 700 "$HOME/.ssh" "$HOME/.cache/jamaica-oracle-catalog"

# Independently pin actual Github.com Ed25519 host key to official fingerprint.
TEMP="$(mktemp)"
cleanup(){ rm -f "$TEMP"; }
trap cleanup EXIT
ssh-keyscan -T 15 -t ed25519 github.com > "$TEMP" 2>/dev/null
if ! ssh-keygen -lf "$TEMP" -E sha256 2>/dev/null | grep -Fq "$GITHUB_FINGERPRINT"; then
 echo "STOP_GITHUB_SSH_FINGERPRINT_MISMATCH"
 exit 2
fi
cp -f "$TEMP" "$HOSTS"
chmod 600 "$HOSTS" "$KEY"
if [[ "$(stat -c '%a' "$KEY")" != "600" ]]; then
 echo "STOP_DEPLOY_KEY_PERMISSIONS"; exit 2
fi

# Test write-enabled repository access without any token, then enable schedule.
export GIT_SSH_COMMAND="ssh -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOSTS -i $KEY -o ConnectTimeout=15"
git ls-remote --exit-code "$REPO" HEAD >/dev/null || {
 echo "STOP_GITHUB_DEPLOY_KEY_NOT_AUTHORIZED"; exit 2; }

# Linger is mandatory: importing must continue with Lenovo off and without SSH login.
if [[ "$(loginctl show-user "$(id -un)" -p Linger --value)" != "yes" ]]; then
 if command -v sudo >/dev/null && sudo -n loginctl enable-linger "$(id -un)"; then
   echo "JAMAICA_ORACLE_LINGER_ENABLED=YES"
 else
   echo "STOP_ORACLE_USER_LINGER_DISABLED_REQUIRES_ADMIN"
   exit 2
 fi
fi
[[ "$(loginctl show-user "$(id -un)" -p Linger --value)" == "yes" ]] || {
 echo "STOP_ORACLE_USER_LINGER_NOT_CONFIRMED"; exit 2; }

export XDG_RUNTIME_DIR="/run/user/$(id -u)"
[[ -d "$XDG_RUNTIME_DIR" ]] || { echo "STOP_ORACLE_USER_RUNTIME_UNAVAILABLE"; exit 2; }

SERVICE="$HOME/.config/systemd/user/$SERVICE_NAME.service"
TIMER="$HOME/.config/systemd/user/$SERVICE_NAME.timer"
cat > "$SERVICE" <<EOF
[Unit]
Description=JAMAICA server-only verified-price-list import and Github Pages catalog publisher
After=network-online.target
Wants=network-online.target

[Service]
Type=oneshot
WorkingDirectory=$ROOT
Environment=PYTHONDONTWRITEBYTECODE=1
ExecStart=/usr/bin/flock -n $HOME/.cache/jamaica-oracle-catalog/refresh.lock /usr/bin/python3 -B $ROOT/oracle_site_publisher.py
TimeoutStartSec=4min 45s
NoNewPrivileges=true
EOF
cat > "$TIMER" <<EOF
[Unit]
Description=JAMAICA Oracle independent tour price-list update every five minutes

[Timer]
OnCalendar=*-*-* *:00/5:00
AccuracySec=30s
Persistent=true
Unit=$SERVICE_NAME.service

[Install]
WantedBy=timers.target
EOF
chmod 600 "$SERVICE" "$TIMER"
systemctl --user daemon-reload
systemctl --user enable --now "$SERVICE_NAME.timer"

# First full run: confirms authorized GETs, source checks, and Git push.
systemctl --user start "$SERVICE_NAME.service"
result="$(systemctl --user show "$SERVICE_NAME.service" -p Result --value)"
[[ "$result" == "success" ]] || {
 echo "STOP_ORACLE_FIRST_IMPORT_FAILED_REVIEW_STATUS"; exit 2; }
[[ "$(systemctl --user is-active "$SERVICE_NAME.timer")" == "active" ]] || {
 echo "STOP_ORACLE_TIMER_NOT_ACTIVE"; exit 2; }

echo "JAMAICA_ORACLE_IMPORT_INTERVAL_MINUTES=5"
echo "JAMAICA_ORACLE_TIMER_ACTIVE=active"
echo "JAMAICA_ORACLE_LINGER=yes"
echo "JAMAICA_LENOVO_DEPENDENCY=NONE_AFTER_THIS_INSTALL"
systemctl --user list-timers --all "$SERVICE_NAME.timer" --no-pager
systemctl --user show "$SERVICE_NAME.service" \
 -p Result -p ExecMainStatus -p ActiveEnterTimestamp --no-pager
echo "JAMAICA_ORACLE_5MIN_INSTALL_COMPLETE"
