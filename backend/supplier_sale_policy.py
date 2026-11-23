"""JAMAICA private supplier selection and sale eligibility.

A published BG price reference and even two available flights in an xml=31
snapshot do NOT make a saleable offer. The best-price mark comes from BG's
separately verified route context; no field in the current JSON catalog
establishes that operator UI label. An authorized PRIVATE adapter must attest
that the exact selected BG source is labelled BEST PRICE.

No credentials, passenger data, booking or monetary side effects here.
No public catalogue field can authorize these attestations.
"""
from __future__ import annotations

BG_BEST_PRICE="BG_BEST_PRICE_TWO_FLIGHTS"
PEGAS="PEGAS_TWO_FLIGHTS"
POLICIES=frozenset((BG_BEST_PRICE,PEGAS))

def valid_policy(policy):
    return type(policy) is str and policy in POLICIES

def check_supplier_evidence(quote:dict|None,policy:str)->bool:
    """Fail closed before any contract, payment or booking operation."""
    if not isinstance(quote,dict) or not valid_policy(policy):
        return False
    if (quote.get("flight_out_available") is not True or
        quote.get("flight_back_available") is not True or
        quote.get("flight_pair_evidence_verified") is not True):
        return False
    if policy==BG_BEST_PRICE:
        return (quote.get("best_price_required") is True and
                quote.get("best_price_verified") is True)
    # A separate PEGAS adapter must check its flight and pricing rules.
    return quote.get("best_price_required") is False

def valid_offer_evidence(offer:dict|None)->bool:
    """The private stored offer must record which server-controlled policy passed."""
    if not isinstance(offer,dict):
        return False
    if (offer.get("flights_out_green") is not True or
        offer.get("flights_back_green") is not True or
        offer.get("flight_pair_evidence_verified") is not True):
        return False
    policy=offer.get("sale_policy")
    if not valid_policy(policy):
        return False
    if policy==BG_BEST_PRICE:
        return (offer.get("best_price_required") is True and
                offer.get("best_price_verified") is True)
    return offer.get("best_price_required") is False
