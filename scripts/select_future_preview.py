#!/usr/bin/env python3
"""Choose a future, real supplier-derived preview for a read-only price test.

Default is a non-domestic option starting at least tomorrow; no price or
bookability inference. Explicit user-selected IDs are not overridden.
"""
from __future__ import annotations
import argparse
import json
import re
from datetime import date, timedelta, datetime, timezone
from pathlib import Path

ID=re.compile(r"^p_[a-f0-9]{24}$")
NON_DOMESTIC_PRIORITY=("Индонезия","Турция","Шри-Ланка","Таиланд")

def choose(feed, today=None, preferred_country=None):
    today=today or datetime.now(timezone.utc).date()
    earliest=today+timedelta(days=1)
    if feed.get("schema")!="jamaica.tour-previews.v1" or feed.get("bookable") is not False:
        raise ValueError("INVALID_PREVIEW_FEED")
    rows=feed.get("previews",[])
    if not isinstance(rows,list):
        raise ValueError("INVALID_PREVIEW_ROWS")
    candidates=[]
    for row in rows:
        if not isinstance(row,dict):
            continue
        try:
            day=date.fromisoformat(str(row.get("depart_date","")))
        except ValueError:
            continue
        if day<earliest or day>today+timedelta(days=180):
            continue
        if (not ID.fullmatch(str(row.get("id",""))) or
            row.get("bookable") is not False or
            row.get("quote_verified") is not False or
            row.get("availability_verified") is not False or
            row.get("flight_verified") is not False or
            row.get("origin")!="Иркутск"):
            continue
        country=row.get("country","")
        if preferred_country and country!=preferred_country:
            continue
        priority=(NON_DOMESTIC_PRIORITY.index(country) if country in NON_DOMESTIC_PRIORITY
                  else 10 if country!="Россия" else 20)
        candidates.append((priority,day,str(row["id"])))
    if not candidates:
        raise ValueError("NO_FUTURE_PREVIEW_MATCH")
    return sorted(candidates)[0][2]

def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--feed",required=True)
    parser.add_argument("--country",default="")
    args=parser.parse_args()
    feed=json.loads(Path(args.feed).read_text(encoding="utf-8"))
    print(choose(feed,preferred_country=args.country or None))

if __name__=="__main__":
    main()
