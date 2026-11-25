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

def main():
    p=argparse.ArgumentParser();p.add_argument("catalog",type=Path);args=p.parse_args()
    with args.catalog.open(encoding="utf-8") as f:feed=json.load(f)
    print(json.dumps(plan(feed,now=datetime.now(timezone.utc)),ensure_ascii=False,indent=2))
if __name__=="__main__":main()
