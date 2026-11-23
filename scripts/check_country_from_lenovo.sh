#!/usr/bin/env bash
# Read-only on-demand tour/source check for ANY country actually represented
# in the full JAMAICA sharded feed. No booking, pricing quote or payment.
set -Eeuo pipefail
umask 077
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
COUNTRY="${1:-}"
ROOMS_FILE="${2:-}"
if [[ -z "$COUNTRY" || ${#COUNTRY} -gt 120 || "$COUNTRY" == -* ||
      "$COUNTRY" == *$'\n'* || "$COUNTRY" == *$'\r'* ]]; then
  echo "STOP_COUNTRY_NAME_REQUIRED"; exit 2
fi
[[ $# -le 2 ]] || { echo "STOP_TOO_MANY_ARGUMENTS"; exit 2; }
ID="$(python3 -B "$ROOT/scripts/local_selected_preview.py" \
    --root "$ROOT/tour-previews.json" --country "$COUNTRY")"
[[ "$ID" =~ ^p_[a-f0-9]{24}$ ]] || {
  echo "STOP_COUNTRY_HAS_NO_CURRENT_SOURCE_PREVIEW"; exit 2;
}
# The selected CLI revalidates every hashed shard before staging one row.
exec bash "$ROOT/scripts/check_selected_tour_from_lenovo.sh" "$ID" "$ROOMS_FILE"
