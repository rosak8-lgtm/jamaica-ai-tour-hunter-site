"""Stage-1 supplier quoting for selected PUBLIC Jamaica preview cards.

Converts unbookable hotel/date/room metadata into a PRIVATE verified quote
only via a fresh authorized supplier READ-ONLY operation. Never fabricates a
bookable offer and NEVER creates supplier orders or payment intents.
"""
from __future__ import annotations
import secrets
from datetime import datetime, timezone, timedelta
from typing import Protocol, Any

from backend.order_engine import BadOrder, NotAvailable
from backend.contract_first_order_engine import quote_is_valid
from backend.supplier_sale_policy import (
    BG_BEST_PRICE, valid_policy, check_supplier_evidence
)

class PreviewQuoteRepository(Protocol):
    def get_preview(self,preview_id:str)->dict[str,Any]|None: ...
    def save_verified_offer(self,offer:dict[str,Any])->None: ...
    # save in private durable DB, not a public GitHub JSON feed.

class PreviewSupplier(Protocol):
    def check_preview(self,preview:dict[str,Any],adults:int,children:int)->dict[str,Any]: ...
    # Must execute read-only official quote; must not create/hold a booking.

def _source_matches(p:dict[str,Any],check:dict[str,Any])->bool:
    return (check.get("source_preview_id")==p.get("id") and
            str(check.get("hotel_id"))==str(p.get("hotel_id")) and
            check.get("depart_date")==p.get("depart_date") and
            check.get("room")==p.get("room") and
            type(check.get("nights")) is int and check["nights"]==p.get("nights") and
            check.get("country")==p.get("country") and
            check.get("origin")==p.get("origin"))

class PreviewQuoteEngine:
    def __init__(self,repo:PreviewQuoteRepository,supplier:PreviewSupplier,clock=None,
                 *,sale_policy:str=BG_BEST_PRICE):
        if not valid_policy(sale_policy):
            raise ValueError("Only explicit trusted supplier sale policies allowed")
        # Set by deployment configuration, NEVER by the browser or by public
        # catalog content. Current authenticated catalog supplier is BG.
        self.sale_policy=sale_policy
        self.repo,self.supplier=repo,supplier
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def get_authoritative_quote(self,preview_id:str,*,buyer_id:str,
                                adults:int,children:int,
                                on_request_accepted:bool=False)->dict[str,Any]:
        if not isinstance(preview_id,str) or len(preview_id)!=26 or not preview_id.startswith("p_"):
            raise BadOrder("Selected tour ID invalid")
        if not isinstance(buyer_id,str) or not 8<=len(buyer_id)<=128:
            raise BadOrder("Authenticated buyer required; never trust buyer_id from browser")
        if type(adults) is not int or type(children) is not int or adults!=2 or children!=0:
            raise NotAvailable("Other party compositions need separate supplier adapter")
        p=self.repo.get_preview(preview_id)
        if not isinstance(p,dict) or p.get("id")!=preview_id or p.get("bookable") is not False:
            raise NotAvailable("Published preliminary tour not found")
        try:
            from datetime import date
            departure=date.fromisoformat(p["depart_date"])
        except (TypeError,ValueError,KeyError):
            raise NotAvailable("Invalid departure date")
        if not self.clock().date()<departure<=self.clock().date()+timedelta(days=180):
            raise NotAvailable("Tour is no longer within search window")
        quoted=self.supplier.check_preview(p,adults,children)
        if not isinstance(quoted,dict) or not _source_matches(p,quoted):
            raise NotAvailable("Supplier response is for another hotel/date/room")
        price=quoted.get("total_rub")
        if (type(price) is not int or price<=0 or
            not check_supplier_evidence(quoted,self.sale_policy) or
            not quote_is_valid(
                quoted,price,allow_on_request=on_request_accepted,
                sale_policy=self.sale_policy)):
            raise NotAvailable("Fresh verified price, seats or hotel status missing")
        offer_id="tour_"+secrets.token_urlsafe(18)
        now=self.clock().astimezone(timezone.utc)
        expires=datetime.fromisoformat(quoted["expires_at"].replace("Z","+00:00"))
        expires=min(expires,now+timedelta(minutes=10))
        # Source/party/flight facts are from a trusted supplier adapter, NEVER browser.
        offer={
            "id":offer_id,"buyer_id":buyer_id,"source_preview_id":preview_id,
            "origin":p["origin"],"destination":p["country"],
            "hotel":p["hotel"],"room":p["room"],"hotel_id":p["hotel_id"],
            "depart_date":p["depart_date"],"nights":p["nights"],
            "adults":2,"children":0,"currency":"RUB","total_rub":price,
            "quote_verified":True,"availability_verified":True,
            "flights_out_green":True,"flights_back_green":True,
            "flight_pair_evidence_verified":True,
            "price_scope_verified":True,"total_two_verified":True,
            "publish_approved":True,
            "sale_policy":self.sale_policy,
            "best_price_required":self.sale_policy==BG_BEST_PRICE,
            "best_price_verified":quoted.get("best_price_verified") is True,
            "hotel_status":quoted["hotel_status"],
            "hotel_on_request_accepted":bool(on_request_accepted),
            "quote_verified_at":now.isoformat(),
            "expires_at":expires.astimezone(timezone.utc).isoformat(),
        }
        self.repo.save_verified_offer(offer)
        return {
            "status":"QUOTE_READY","offer_id":offer_id,
            "source_preview_id":preview_id,"total_rub":price,"currency":"RUB",
            "expires_at":offer["expires_at"],
            "hotel_status":quoted["hotel_status"],
            "contract_required":True,"booked":False,
        }
