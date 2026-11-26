"""Read-only coverage planner. No supplier requests, no worker scheduling or offer creation."""
import argparse
from collections import Counter
from datetime import datetime, timezone
import json
import re
from pathlib import Path

PRIMARY=("Таиланд","Китай","Вьетнам")
MONTH=re.compile(r"20\d\d-(0[1-9]|1[0-2])\Z")
def valid_name(s):
    return isinstance(s,str) and 2<=len(s)<=80 and all(c.isalpha() or c in " -()" for c in s)

def plan(feed, *, now):
    if now.tzinfo is None:raise ValueError("AWARE_CLOCK_REQUIRED")
    if feed.get("schema")!="jamaica.tour-previews.v1":raise ValueError("CATALOG_SCHEMA")
    coverage=feed.get("search_coverage",{})
    if coverage.get("classification")!="SOURCE_SCAN_ONLY_NOT_OFFERS":raise ValueError("COVERAGE_SCHEMA")
    entries=coverage.get("countries")
    if not isinstance(entries,list) or len(entries)>120:raise ValueError("COVERAGE_SIZE")
    # The published per-country counters include shards. Root rows alone
    # cannot establish missing month coverage when shards are present.
    rows=feed.get("previews",[])
    if not isinstance(rows,list) or len(rows)>8000:raise ValueError("ROOT_SIZE")
    counts=Counter()
    for row in rows:
        if not isinstance(row,dict) or row.get("origin")!="Иркутск":continue
        country=row.get("country");day=row.get("depart_date")
        if valid_name(country) and isinstance(day,str) and len(day)==10 and MONTH.fullmatch(day[:7]):
            counts[country,day[:7]]+=1
    month=now.astimezone(timezone.utc).strftime("%Y-%m")
    incomplete=bool(feed.get("shards")) or feed.get("total_published_previews",len(rows))!=len(rows)
    published={}
    for s in feed.get("countries_status",[]):
        if isinstance(s,dict) and valid_name(s.get("country")) and type(s.get("previews")) is int and 0<=s["previews"]<=60000:
            published[s["country"]]=s["previews"]
    result=[];seen=set()
    for e in entries:
        if not isinstance(e,dict) or not valid_name(e.get("country")):raise ValueError("COUNTRY_NAME")
        country=e["country"]
        if country in seen:raise ValueError("DUPLICATE_COUNTRY")
        seen.add(country)
        n=e.get("source_rows_observed")
        if type(n) is not int or not 0<n<=60000:raise ValueError("SOURCE_COUNT")
        months=e.get("sampled_departure_months",[])
        if not isinstance(months,list) or len(months)>24 or any(not isinstance(m,str) or not MONTH.fullmatch(m) for m in months):raise ValueError("MONTH_SCHEMA")
        total=published.get(country)
        if not incomplete:total=sum(v for (c,m),v in counts.items() if c==country)
        observed=sorted(m for (c,m) in counts if c==country and m>=month)
        missing=None if incomplete else sorted(set(m for m in months if m>=month)-set(observed))
        result.append({"country":country,"source_rows_observed":n,"published_country_count":total,
                       "observed_root_months":observed,"missing_sampled_months":missing,
                       "role":"CORE_REFRESH" if country in PRIMARY else "EXPANSION"})
    result.sort(key=lambda e:(e["role"]!="CORE_REFRESH",e["published_country_count"]!=0,
                              -e["source_rows_observed"],e["country"]))
    return {"classification":"PUBLIC_SNAPSHOT_COVERAGE_NOT_SEARCH_EXECUTION",
            "catalog_timestamp":feed.get("refreshed_at_utc"),"shards_incomplete":incomplete,
            "countries":result}

# Shadow scheduling only: 15-minute proof lifetime, one authorized slot per
# three minutes. Do not infer that a source candidate is available to book.
PREFERRED_EXPANSION=("Египет","Индия","Индонезия","Объединенные Арабские Эмираты",
                     "Россия","Турция","Шри-Ланка","Сейшелы","Мальдивы")
def expiry_plan(feed,visual,*,now):
    base=plan(feed,now=now)
    if base["shards_incomplete"]:
        return {"classification":"SHADOW_ONLY","execution_allowed":False,
                "status":"HOLD_INCOMPLETE_ROOT","slots":[]}
    if visual.get("schema")!="jamaica.visual-selection.v1" or any(
        visual.get(k) is not False for k in ("bookable","quote_verified","availability_verified")):
        raise ValueError("VISUAL_SCHEMA")
    entries=visual.get("entries")
    if not isinstance(entries,list) or len(entries)>10000:raise ValueError("VISUAL_SIZE")
    proofs={}
    for p in entries:
        if not isinstance(p,dict) or not isinstance(p.get("preview_id"),str) or p["preview_id"] in proofs:
            raise ValueError("VISUAL_ID")
        proofs[p["preview_id"]]=p
    fresh=Counter(); expiring=Counter(); scopes=Counter(); expiring_scopes=Counter(); ids=set()
    for row in feed["previews"]:
        if not isinstance(row,dict) or row.get("origin")!="Иркутск":continue
        pid=row.get("id")
        if not isinstance(pid,str) or not re.fullmatch(r"p_[a-f0-9]{24}",pid) or pid in ids:
            raise ValueError("CATALOG_ID")
        ids.add(pid)
        p=proofs.get(pid,{})
        stamp=p.get("observed_at_utc")
        if (p.get("route_best_price_seen") is not True or p.get("both_green_planes_seen") is not True
            or not isinstance(stamp,str) or stamp!=row.get("price_observed_at_utc")
            or row.get("price_source")!="BG_EXACT_SELECTED_GREEN_BROWSER"):continue
        try:
            t=datetime.fromisoformat(stamp.replace("Z","+00:00"))
            d=datetime.strptime(row["depart_date"],"%Y-%m-%d").date()
            if t.tzinfo is None or d<=now.astimezone(timezone.utc).date():continue
            age=(now-t).total_seconds()
        except (ValueError,TypeError,KeyError):continue
        if not -30<=age<=900:continue
        c=row.get("country")
        if not valid_name(c):continue
        fresh[c]+=1
        scopes[c,row["depart_date"][:7]]+=1
        if age>=600:
            expiring[c]+=1
            expiring_scopes[c,row["depart_date"][:7]]+=1
    countries={x["country"]:x for x in base["countries"]}
    # A published month with expired proofs is missing for current search.
    month_now=now.astimezone(timezone.utc).strftime("%Y-%m")
    fresh_missing={e["country"]:sorted({m for m in e["sampled_departure_months"]
        if m>=month_now and not scopes[e["country"],m]})
        for e in feed["search_coverage"]["countries"]}
    slots=[]
    # One refresh recommendation for each observed core country; prioritize
    # missing/expiring evidence, then use remaining slots for breadth.
    core=sorted((c for c in PRIMARY if c in countries),
        key=lambda c:(fresh[c]>0,-expiring[c],fresh[c],PRIMARY.index(c)))
    used=set()
    for c in core:
        # If there is already evidence, renew its biggest expiring scope.
        observed=sorted((m for cc,m in scopes if cc==c),
                        key=lambda m:(-expiring_scopes[c,m],-scopes[c,m],m))
        missing=fresh_missing[c]
        month=(observed or missing or [None])[0]
        if month:
            slots.append({"country":c,"month":month,"reason":"CORE_REFRESH",
                          "fresh_rows":fresh[c],"expiring_within_5m":expiring[c]})
            used.add((c,month))
    # Reserve at least one expansion slot when a supported extra country
    # exists, rather than spending all capacity on core-country dates.
    extras=sorted((c for c in countries if c not in PRIMARY),
        key=lambda c:(fresh[c]>0,PREFERRED_EXPANSION.index(c) if c in PREFERRED_EXPANSION else len(PREFERRED_EXPANSION),c))
    def append_missing(options,reason):
        for c in options:
            for m in fresh_missing[c]:
                if (c,m) not in used:
                    slots.append({"country":c,"month":m,"reason":reason,
                                  "fresh_rows":fresh[c],"expiring_within_5m":expiring[c]})
                    used.add((c,m));return
    if len(slots)<5:append_missing(extras,"EXPANSION")
    if len(slots)<5:append_missing(core,"MISSING_CORE_MONTH")
    while len(slots)<5:
        before=len(slots);append_missing(extras,"EXPANSION")
        if len(slots)==before:break
    for i,s in enumerate(slots):s["earliest_offset_seconds"]=180*i
    return {"classification":"SHADOW_ONLY","execution_allowed":False,"status":"PLAN_READY",
            "proof_ttl_seconds":900,"minimum_gap_seconds":180,
            "slots":slots,"fresh_rows_by_country":dict(fresh),
            "expiring_rows_by_country":dict(expiring)}

def main():
    p=argparse.ArgumentParser();p.add_argument("catalog",type=Path);p.add_argument("--visual",type=Path);args=p.parse_args()
    with args.catalog.open(encoding="utf-8") as f:feed=json.load(f)
    now=datetime.now(timezone.utc)
    if args.visual:
        with args.visual.open(encoding="utf-8") as f:visual=json.load(f)
        result=expiry_plan(feed,visual,now=now)
    else:result=plan(feed,now=now)
    print(json.dumps(result,ensure_ascii=False,indent=2))
if __name__=="__main__":main()
