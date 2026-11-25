# Independent PEGAS site handoff V78

Status: **disabled by default; not production acceptance**.

The existing BG publication path is unchanged. No PEGAS supplier I/O is introduced by the site publisher. Do not use Telegram outputs, search-price snapshots, or synthetic fixtures as live evidence.

The authorized independent PEGAS browser producer must atomically write an owner-only regular file (0600), in the owner-only directory (0700):
`~/.local/share/jamaica-oracle-catalog/private-pegas-site/evidence.json`.

Top-level schema is `jamaica.pegas-private-handoff.v1`; the only other field is `pairs`, an array of [search, application] objects satisfying `backend/pegas_application_evidence.py` and `backend/pegas_public_projection.py`. The producer must independently establish the selected official hotel and flight availability filters, cheapest eligible selection, same-session exact itinerary and final in-application total including all mandatory fees. Two-adult party binding is mandatory for a public reference price. Vietnam 45/60-night exclusions remain. No submission or reservation. Never renew a timestamp from cached data.

Do not enable `JAMAICA_ENABLE_PEGAS_SITE_HANDOFF=yes` until real producer evidence and access scope have been reviewed, and owner approval obtained. Missing, invalid, conflicting or expired observations cannot create public cards. The publisher uses its existing Git publication route only. With the flag enabled, a changed sanitized projection is included in the next scheduled commit; the client independently rejects stale rows.

No customer contacts, credentials, browser session digests or private reservation IDs may be published. Booking and payment remain disabled. No service or timer changes are required by this code alone.

Offline acceptance: `python3 -B -m unittest backend.test_pegas_private_handoff backend.test_pegas_public_projection backend.test_pegas_application_evidence backend.test_oracle_site_publisher`.
Production acceptance remains dependent on the real independent browser producer and the existing provider hold policy.
