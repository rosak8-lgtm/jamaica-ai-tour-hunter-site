"""Local-only aggregate diagnostics. No network, writes, or raw receipt output."""
from collections import Counter
from datetime import datetime,timezone
import json
import oracle_site_publisher as pub

def report(receipts,exact,now):
    counts=Counter()
    fresh={}
    for item in (receipts or {}).get("records",[]):
        if not isinstance(item,dict) or not isinstance(item.get("flight"),dict):
            counts["invalid"]+=1
            continue
        f=item["flight"]
        t=pub.timestamp(f.get("flight_checked_at_utc"))
        if t is None:
            counts["invalid"]+=1
            continue
        age=(now-t).total_seconds()
        if age < -30:counts["future"]+=1
        elif age > 900:counts["expired"]+=1
        else:
            counts["fresh"]+=1
            if age>=600:counts["expires_within_5m"]+=1
            if isinstance(item.get("preview_id"),str):
                fresh[item["preview_id"]]=item
    exact_ids=set()
    matches=0
    for x in (exact or {}).get("records",[]):
        if not isinstance(x,dict) or not isinstance(x.get("preview"),dict):continue
        uid=x["preview"].get("id")
        if not isinstance(uid,str):continue
        exact_ids.add(uid)
        p=fresh.get(uid)
        if p and isinstance(p.get("route"),dict) and x.get("source_price_list_id")==p["route"].get("source_price_list_id") and x.get("observed_at_utc")==p["flight"].get("flight_checked_at_utc"):
            matches+=1
    return {"receipt_fresh":counts["fresh"],"receipt_expired":counts["expired"],
            "receipt_future":counts["future"],"receipt_invalid_timestamp":counts["invalid"],
            "receipt_expires_within_5m":counts["expires_within_5m"],
            "exact_ids":len(exact_ids),"fresh_ids_missing_exact":len(set(fresh)-exact_ids),
            "exact_timestamp_and_list_matches":matches}

def main():
    now=datetime.now(timezone.utc)
    root=pub.RUNROOT
    def load(name,path,limit,schema):
        try:
            d=pub.read_owner_json(path,limit)
            if d.get("schema")!=schema:raise ValueError("SCHEMA")
            print(name+"_STATE=OK")
            return d
        except FileNotFoundError:print(name+"_STATE=ABSENT")
        except (OSError,ValueError,TypeError):print(name+"_STATE=INVALID")
        return None
    receipts=load("RECEIPTS",pub.PRIVATE_BOT_VISUAL_RECEIPTS,40_000_000,"jamaica.bg-bot-private-receipts.v1")
    exact=load("EXACT_SOURCE",root/"private-site-exact-source.json",20_000_000,"jamaica.bg-site-exact-source.v1")
    for name,data in (("RECEIPTS",receipts),("EXACT_SOURCE",exact)):
        if data is not None and (not isinstance(data.get("records"),list) or len(data["records"])>10000):
            print(name+"_RECORDS=INVALID")
            return 2
    state=load("BOT",pub.BOT_STATE,100_000,"jamaica.site-bot.v1")
    if state is not None:
        for key in ("last_completed_at_utc","provider_hold_until_utc"):
            value=pub.timestamp(state.get(key))
            print(key.upper()+"="+(value.isoformat() if value else "ABSENT_OR_INVALID"))
    print("PROVIDER_HOLD_ACTIVE="+str(pub.provider_hold_active(now=now)))
    print("SOURCE_SCAN_DUE="+str(pub.source_scan_due(now=now)))
    print("PROOF_HEALTH="+json.dumps(report(receipts,exact,now),sort_keys=True))
    try:
        directory=json.loads((pub.CHECKOUT/"destination-directory.json").read_text(encoding="utf-8"))
        base=pub.projection_base(now=now)
        projected,n=pub.merge_exact_browser_source(base,directory,receipts,now=now)
        print("EXACT_STRICT_ACCEPTED="+str(n))
        print("VISUAL_STRICT_ACCEPTED="+str(len(pub.visual.build_visual_feed(projected["previews"],receipts,now=now)["entries"])))
    except (OSError,ValueError,TypeError,KeyError,pub.CatalogHold):
        print("STRICT_PROJECTION_DIAGNOSTIC=HOLD")
        return 2
    return 0
if __name__=="__main__":raise SystemExit(main())
