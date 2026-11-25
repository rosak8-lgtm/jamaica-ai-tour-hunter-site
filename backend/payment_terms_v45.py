"""Private payment arithmetic, no network or booking authority.
Call only with independently verified supplier terms and PSP records.
All amounts are integer kopecks, never binary floats.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

def amount(value, zero=False):
    if type(value) is not int or not (0 if zero else 1)<=value<=10**12:
        raise ValueError("INVALID_AMOUNT")
    return value

def instant(value):
    if not isinstance(value,str):raise ValueError("TIMESTAMP_REQUIRED")
    t=datetime.fromisoformat(value.replace("Z","+00:00"))
    if t.tzinfo is None:raise ValueError("TIMEZONE_REQUIRED")
    return t.astimezone(timezone.utc)

@dataclass(frozen=True)
class Terms:
    total:int
    minimum:int
    partial:bool
    below_minimum:bool
    due:str
    expires:str
    balance_rule:str
    currency:str
    offer_id:str
    quote_id:str

def verified_terms(quote,offer_id,now):
    if now.tzinfo is None:raise ValueError("CLOCK_REQUIRED")
    if not isinstance(quote,dict) or quote.get("supplier_quote_verified") is not True or quote.get("payment_terms_verified") is not True or quote.get("offer_id")!=offer_id:
        raise ValueError("VERIFIED_TERMS_REQUIRED")
    p=quote.get("payment_terms")
    if not isinstance(p,dict) or p.get("currency")!="RUB":raise ValueError("TERMS_REQUIRED")
    total=amount(p.get("total_kopecks"));minimum=amount(p.get("minimum_kopecks"))
    if type(quote.get("total_rub")) is not int or total!=quote["total_rub"]*100:raise ValueError("QUOTE_TOTAL")
    partial=p.get("allows_partial");below=p.get("allows_below_minimum")
    if type(partial) is not bool or type(below) is not bool or minimum>total or (not partial and (minimum!=total or below)):
        raise ValueError("DEPOSIT_TERMS")
    due=p.get("full_payment_due_utc");expires=quote.get("expires_at")
    if now>=instant(due) or now>=instant(expires):raise ValueError("EXPIRED_TERMS")
    rule=p.get("balance_rule");currency=p.get("tour_currency")
    if rule not in ("FIXED_RUB","SUPPLIER_RATE_ON_BALANCE_PAYMENT") or not isinstance(currency,str) or len(currency)!=3 or not currency.isascii() or not currency.isalpha() or currency!=currency.upper() or (rule=="FIXED_RUB" and currency!="RUB"):
        raise ValueError("BALANCE_RULE")
    qid=quote.get("quote_id")
    if not isinstance(qid,str) or not 1<=len(qid)<=128:raise ValueError("QUOTE_ID")
    return Terms(total,minimum,partial,below,due,expires,rule,currency,offer_id,qid)

def plan(terms,mode,*,now,paid=0,custom=None):
    if now.tzinfo is None or now>=instant(terms.expires) or now>=instant(terms.due):raise ValueError("REQUOTE_REQUIRED")
    paid=amount(paid,True)
    if paid and terms.balance_rule!="FIXED_RUB":raise ValueError("SUPPLIER_BALANCE_REQUOTE_REQUIRED")
    remaining=terms.total-paid;minimum=max(0,terms.minimum-paid)
    if mode=="FULL":value=remaining
    elif mode=="DEPOSIT" and terms.partial and minimum:value=minimum
    elif mode=="CUSTOM" and terms.partial:value=amount(custom)
    else:raise ValueError("MODE_UNAVAILABLE")
    if not 0<value<=remaining or (value<minimum and not terms.below_minimum):raise ValueError("AMOUNT_OUTSIDE_TERMS")
    return {"amount_kopecks":value,"remaining_to_minimum_after_payment":max(0,minimum-value),"remaining_total_after_payment":remaining-value}

def reconcile(terms,order_id,receipts):
    """Only trusted PSP-adapter input. No booking even when threshold reached."""
    if not isinstance(receipts,(list,tuple)) or len(receipts)>1000:raise ValueError("RECEIPTS")
    seen={};review=False
    for r in receipts:
        if not isinstance(r,dict) or r.get("verified_by_psp") is not True or r.get("order_id")!=order_id or r.get("currency")!="RUB":raise ValueError("UNVERIFIED_PAYMENT")
        pid=r.get("payment_id");status=r.get("status")
        if not isinstance(pid,str) or not 1<=len(pid)<=128 or status not in ("PAID","PENDING","FAILED","REFUNDED","REVERSED"):raise ValueError("PAYMENT_ID_OR_STATUS")
        entry=(status,amount(r.get("principal_kopecks")),amount(r.get("processor_fee_kopecks",0),True))
        if pid in seen and seen[pid]!=entry:raise ValueError("CONFLICTING_RECEIPTS")
        seen[pid]=entry
        if status in ("REFUNDED","REVERSED"):review=True
    paid=sum(v[1] for v in seen.values() if v[0]=="PAID")
    review=review or paid>terms.total
    return {"paid_kopecks":paid,"remaining_to_minimum":max(0,terms.minimum-paid),
            "remaining_total_at_signed_price":max(0,terms.total-paid),
            "review_required":review,"minimum_reached":paid>=terms.minimum and not review,
            "booking_authorized":False,"balance_requote_required":terms.balance_rule!="FIXED_RUB" and 0<paid<terms.total}
