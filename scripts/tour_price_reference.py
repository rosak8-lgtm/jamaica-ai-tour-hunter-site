"""Strict, non-bookable reference price parser for supplier JSON lists.

It never constructs an order, fetches customer data, or performs exchange-rate
conversion. Operator quote/flight/availability checks are separately required.
"""
from __future__ import annotations
from decimal import Decimal, InvalidOperation
import re

def positive_rub(value):
    if isinstance(value,bool) or not isinstance(value,(str,int,float,Decimal)):
        return None
    try:
        v=Decimal(str(value).strip())
        if not v.is_finite() or v<=0 or v>100_000_000 or v!=v.to_integral_value():
            return None
        return int(v)
    except (ValueError,InvalidOperation):
        return None

def adult_pair(value):
    """Only clearly paired adult bands; do not guess from ambiguous strings."""
    if not isinstance(value,str):
        return False
    x=value.strip()
    # Source documents either comma ages or adjacent bracketed intervals.
    if re.fullmatch(r"(?:\[\d{1,2}-\d{1,3}\]){2}",x):
        parts=re.findall(r"\[(\d{1,2}-\d{1,3})\]",x)
    else:
        parts=[part.strip().strip("[]()") for part in x.split(",")]
    if len(parts)!=2:
        return False
    for p in parts:
        if p=="12+":continue
        m=re.fullmatch(r"(\d{1,2})-(\d{1,3})",p)
        if not m or int(m.group(1))<12 or int(m.group(2))<int(m.group(1)):
            return False
    return True

def indicative_two_adult_rub(prices,currency):
    """Return a listed total for 2 adults, NEVER an authoritative quote."""
    if not isinstance(currency,str) or currency.strip().upper() not in ("RUB","RUR","EUR","USD","CNY","THB","IDR","LKR","TRY","AED","VND"):
        return None
    if not isinstance(prices,list):
        return None
    values=[]
    rub=currency.strip().upper() in ("RUB","RUR")
    for p in prices:
        if not isinstance(p,dict) or p.get("isstop") or not adult_pair(p.get("ag")):
            continue
        # Docs: RUR is present when price list currency is not RUB.
        amount=positive_rub(p.get("amount") if rub else p.get("RUR"))
        if amount is not None:
            values.append(amount)
    return min(values) if values else None
