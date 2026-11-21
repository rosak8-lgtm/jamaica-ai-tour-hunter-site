#!/usr/bin/env bash
# One-time secure launch of PRIVATE hotel review API on Oracle (no user login exposed).
# Lenovo is only a transport for this single administrative SSH call.
# The website review form must remain disabled until a trusted public HTTPS URL exists.
set -Eeuo pipefail
umask 077

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
KEY="$HOME/.ssh/jamaica-oracle.key"
REMOTE="ubuntu@92.5.184.47"
test -r "$KEY" || { echo "STOP_ORACLE_SSH_KEY_MISSING"; exit 2; }

ssh -F /dev/null -o BatchMode=yes -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes -o ConnectTimeout=15 -i "$KEY" \
    "$REMOTE" 'bash -s' <<'REMOTE_SH'
set -Eeuo pipefail
umask 077
[[ "$(id -un)" == "ubuntu" ]] || { echo "STOP_NOT_ORACLE_UBUNTU"; exit 2; }
ROOT="$HOME/.local/share/jamaica-oracle-catalog/site"
KEY="$HOME/.ssh/jamaica_catalog_deploy_ed25519"
HOSTS="$HOME/.ssh/jamaica_catalog_known_hosts"
[[ -d "$ROOT/.git" && -r "$KEY" && -r "$HOSTS" ]] || {
 echo "STOP_ORACLE_CATALOG_NOT_INITIALIZED"; exit 2; }
export GIT_SSH_COMMAND="ssh -F /dev/null -o IdentitiesOnly=yes -o BatchMode=yes -o StrictHostKeyChecking=yes -o UserKnownHostsFile=$HOSTS -o ConnectTimeout=15 -i $KEY"
git -C "$ROOT" fetch --depth=1 origin main
git -C "$ROOT" checkout --force -B main origin/main
bash "$ROOT/scripts/oracle_install_hotel_reviews.sh"
echo "JAMAICA_ORACLE_PRIVATE_HOTEL_REVIEWS_INSTALLED=YES"
REMOTE_SH
echo "JAMAICA_REVIEW_API_PRIVATE_BACKEND_READY"
echo "PUBLIC_REVIEW_FORM=BLOCKED_UNTIL_HTTPS_PROXY"
