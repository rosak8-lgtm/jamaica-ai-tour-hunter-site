"""JAMAICA contract-first order orchestration. No real external connections.

STRICT order: supplier quote #1 (read-only) -> contract -> trusted e-sign evidence
-> supplier quote #2 (read-only) -> PSP payment -> independent paid verification
-> supplier quote #3 (read-only) -> CREATE BOOKING -> notifications.

All adapters are contracts to be implemented/authorized on the private server.
Never use this module from static GitHub Pages, and never enable checkout before
supplier/PSP/signature adapters + DB compare-and-set + legal terms are production-ready.
"""
from __future__ import annotations

import hashlib
import json
import secrets
from datetime import datetime, timezone, timedelta
from typing import Protocol, Any
from urllib.parse import urlsplit

from backend.order_engine import (BadOrder, NotAvailable, NotConfigured,
                                  PriceChanged, GatewayError, Merchant, valid_offer)

ALLOWED_HOTEL = ("IN_STOCK", "ON_REQUEST")
SUCCESS = ("CONFIRMED", "ON_REQUEST")
FINISHED = ("BOOKED", "SUPPLIER_ON_REQUEST", "REFUND_REQUIRED",
            "REFUND_PENDING", "REFUNDED", "CANCELLED")

class StrictRepo(Protocol):
    def get_offer(self, offer_id:str)->dict[str,Any]|None: ...
    def create_order(self, item:dict[str,Any])->None: ...
    def get_order(self, order_id:str)->dict[str,Any]|None: ...
    def transition(self, order_id:str, expected_status:str,
                   new_status:str, updates:dict[str,Any])->bool: ...
    # Must implement the transition as ONE durable database compare-and-set.

class QuoteSupplier(Protocol):
    def check(self, offer:dict[str,Any], stage:str)->dict[str,Any]: ...
    # READ ONLY. This method must NEVER reserve or create a booking.
    def create_booking(self, order:dict[str,Any], idempotency_key:str)->dict[str,Any]: ...
    # The ONLY method with supplier booking side effects. Requires paid evidence.
    # Returns {"status":"CONFIRMED"|"ON_REQUEST","supplier_booking_id":...}.
    def lookup_booking(self, idempotency_key:str)->dict[str,Any]|None: ...

class ContractSigner(Protocol):
    def create_contract(self, *, order_id:str, content:dict[str,Any],
                        digest_sha256:str)->dict[str,str]: ...
    # Return independently verifiable contract_id and secure signing URL.
    def verified_signature(self, *, contract_id:str, digest_sha256:str)->dict[str,Any]: ...
    # Trusted provider-side verification, never a client-supplied checkbox.

class CheckoutPSP(Protocol):
    def create_payment(self, order_id:str, amount_rub:int, idempotency_key:str)->dict[str,str]: ...
    def get_authoritative_status(self, payment_id:str)->str: ...
    def refund(self, payment_id:str, idempotency_key:str)->None: ...

class Outbox(Protocol):
    def enqueue_once(self, key:str, event:dict[str,Any])->None: ...
    # Transactionally durable outbox; consumer sends Telegram/email later.

def quote_is_valid(check:dict[str,Any]|None, price:int, *, allow_on_request:bool)->bool:
    if not isinstance(check,dict):
        return False
    if check.get("currency")!="RUB" or type(check.get("total_rub")) is not int:
        return False
    if check["total_rub"]!=price or price<=0:
        return False
    if check.get("flight_out_available") is not True or check.get("flight_back_available") is not True:
        return False
    if check.get("hotel_stop") is not False:
        return False
    status=check.get("hotel_status")
    if status not in ALLOWED_HOTEL or (status=="ON_REQUEST" and not allow_on_request):
        return False
    if check.get("two_adults_price_verified") is not True:
        return False
    if check.get("supplier_quote_verified") is not True:
        return False
    if check.get("best_price_required") is True and check.get("best_price_verified") is not True:
        return False
    try:
        expires=datetime.fromisoformat(check["expires_at"].replace("Z","+00:00"))
        if expires.tzinfo is None or expires<=datetime.now(timezone.utc):
            return False
    except (KeyError,ValueError,TypeError,AttributeError):
        return False
    return True

def contract_digest(content:dict[str,Any])->str:
    return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(",",":"),
                                      ensure_ascii=False).encode()).hexdigest()

def secure_https(url:str,origin:str|None=None)->bool:
    if not isinstance(url,str):
        return False
    try:
        parsed=urlsplit(url)
        if (parsed.scheme!="https" or not parsed.hostname or
            parsed.username or parsed.password or parsed.fragment):
            return False
        if origin and parsed.scheme+"://"+parsed.netloc!=origin.rstrip("/"):
            return False
        return True
    except ValueError:
        return False

class ContractFirstEngine:
    def __init__(self, merchant:Merchant, repo:StrictRepo, supplier:QuoteSupplier,
                 signer:ContractSigner, payment:CheckoutPSP, outbox:Outbox):
        self.merchant,self.repo,self.supplier=merchant,repo,supplier
        self.signer,self.payment,self.outbox=signer,payment,outbox

    def _ready(self):
        self.merchant.assert_ready()

    def _check(self, offer, stage, price, allow_on_request):
        quote=self.supplier.check(offer, stage)
        if not isinstance(quote,dict):
            raise NotAvailable("Supplier did not return an authoritative quote")
        if not quote_is_valid(quote,price,allow_on_request=allow_on_request):
            if quote.get("currency")=="RUB" and quote.get("total_rub")!=price:
                raise PriceChanged("Supplier price changed; new contract consent required")
            raise NotAvailable("Flight, hotel or supplier quote not verified")
        return quote

    def draft_contract(self, *, offer_id:str, expected_total_rub:int,
                       buyer_id:str, terms_version:str,
                       on_request_accepted:bool=False)->dict[str,Any]:
        """Stage #1: read-only supplier verification and legal contract creation.
        NO payment, reservation, booking or notification is sent.
        """
        self._ready()
        if not isinstance(offer_id,str) or not 8<=len(offer_id)<=100:
            raise BadOrder("Invalid offer reference")
        if type(expected_total_rub) is not int or expected_total_rub<=0:
            raise BadOrder("Invalid expected total")
        if not isinstance(buyer_id,str) or not 8<=len(buyer_id)<=128:
            raise BadOrder("Authenticated customer account required")
        if terms_version!=self.merchant.terms_version:
            raise BadOrder("Wrong contract terms")
        offer=self.repo.get_offer(offer_id)
        if not valid_offer(offer,datetime.now(timezone.utc)):
            raise NotAvailable("First supplier verified offer required")
        if offer["total_rub"]!=expected_total_rub:
            raise PriceChanged("Displayed price changed")
        check=self._check(offer,"BEFORE_CONTRACT",expected_total_rub,on_request_accepted)
        order_id=secrets.token_urlsafe(22)
        token=secrets.token_urlsafe(32)
        contents={
            "order_id":order_id,"offer_id":offer_id,"buyer_id":buyer_id,
            "merchant_legal_name":self.merchant.seller_legal_name,
            "merchant_registration":self.merchant.registration_number,
            "terms_version":terms_version,
            "total_rub":expected_total_rub,"currency":"RUB",
            "hotel_status_at_draft":check["hotel_status"],
            "hotel_on_request_accepted":bool(on_request_accepted),
            "contract_kind":"tourism_service_agreement",
        }
        digest=contract_digest(contents)
        self.repo.create_order({
            "id":order_id,"view_token_hash":hashlib.sha256(token.encode()).hexdigest(),
            "buyer_id":buyer_id,"offer_id":offer_id,
            "signed_total_rub":expected_total_rub,
            "hotel_on_request_accepted":bool(on_request_accepted),
            "status":"CONTRACT_CREATING",
            "contract_digest":digest,"contract_content":contents,
            "contract_id":None,"payment_id":None,
        })
        try:
            signing=self.signer.create_contract(order_id=order_id,content=contents,
                                                digest_sha256=digest)
            if not isinstance(signing,dict) or not signing.get("contract_id") or not secure_https(signing.get("signing_url")):
                raise NotConfigured("Real verifiable e-sign provider required")
            if not self.repo.transition(order_id,"CONTRACT_CREATING","AWAITING_SIGNATURE",
                                        {"contract_id":signing["contract_id"]}):
                raise BadOrder("Contract state already changed")
            return {"order_id":order_id,"status":"AWAITING_SIGNATURE",
                    "signing_url":signing["signing_url"],"status_token":token}
        except Exception:
            self.repo.transition(order_id,"CONTRACT_CREATING","CONTRACT_FAILED",{})
            raise

    def verify_contract_signature(self,order_id:str)->dict[str,Any]:
        """Stage signature: verified with provider; browser clicks prove nothing."""
        order=self._order(order_id)
        if order["status"]=="CONTRACT_SIGNED":
            return {"status":"CONTRACT_SIGNED"}
        if order["status"]!="AWAITING_SIGNATURE":
            raise BadOrder("No contract pending signature")
        receipt=self.signer.verified_signature(contract_id=order["contract_id"],
                                               digest_sha256=order["contract_digest"])
        if not isinstance(receipt,dict) or receipt.get("verified") is not True or receipt.get("digest_sha256")!=order["contract_digest"] or not receipt.get("signed_at"):
            raise NotAvailable("Trusted electronic signature not verified")
        if not self.repo.transition(order_id,"AWAITING_SIGNATURE","CONTRACT_SIGNED",
                                    {"signed_at":receipt["signed_at"],"signature_receipt_id":receipt.get("receipt_id")}):
            raise BadOrder("Signature already processed")
        return {"status":"CONTRACT_SIGNED"}

    def initiate_payment(self, order_id:str)->dict[str,Any]:
        """Stage #2: only verified signed contract can trigger second quote + PSP."""
        self._ready()
        order=self._order(order_id)
        if order["status"]!="CONTRACT_SIGNED":
            raise BadOrder("Verified contract signature required before payment")
        offer=self.repo.get_offer(order["offer_id"])
        self._check(offer,"AFTER_SIGNATURE_BEFORE_PAYMENT",order["signed_total_rub"],
                    order["hotel_on_request_accepted"])
        if not self.repo.transition(order_id,"CONTRACT_SIGNED","PAYMENT_CREATING",{}):
            raise BadOrder("Payment already initiated")
        try:
            payment=self.payment.create_payment(order_id,order["signed_total_rub"],order_id)
            if not isinstance(payment,dict) or not payment.get("payment_id") or not secure_https(payment.get("payment_iframe_url"),self.merchant.payment_origin):
                raise GatewayError("Unapproved PSP payment URL")
            if not self.repo.transition(order_id,"PAYMENT_CREATING","PAYMENT_PENDING",
                                        {"payment_id":payment["payment_id"]}):
                raise BadOrder("Payment transition failed")
            return {"status":"PAYMENT_READY","payment_iframe_url":payment["payment_iframe_url"],
                    "total_rub":order["signed_total_rub"],"order_id":order_id}
        except Exception:
            # Actual PSP creation may have succeeded. Do not retry blindly.
            self.repo.transition(order_id,"PAYMENT_CREATING","PAYMENT_REVIEW_REQUIRED",{})
            raise

    def reconcile_payment_and_book(self,order_id:str)->str:
        """Stage #3: independent PSP verification -> quote again -> supplier booking.
        Requires durable, atomic CAS and idempotent supplier request by order_id.
        """
        order=self._order(order_id)
        if order["status"] in FINISHED:
            return order["status"]
        if order["status"] not in ("PAYMENT_PENDING","PAID_RECHECK_REQUIRED"):
            raise BadOrder("No payable order in this status")
        if not order.get("signed_at") or not order.get("signature_receipt_id"):
            raise BadOrder("Signed contract evidence missing")
        if not order.get("payment_id"):
            raise BadOrder("Payment not created")
        status=self.payment.get_authoritative_status(order["payment_id"])
        if status!="PAID":
            if status in ("FAILED","EXPIRED") and order["status"]=="PAYMENT_PENDING":
                self.repo.transition(order_id,"PAYMENT_PENDING","PAYMENT_FAILED",{})
            return "PAYMENT_PENDING" if status not in ("FAILED","EXPIRED") else "PAYMENT_FAILED"
        if order["status"]=="PAYMENT_PENDING":
            if not self.repo.transition(order_id,"PAYMENT_PENDING","PAID_RECHECK_REQUIRED",
                                        {"paid_verified_at":datetime.now(timezone.utc).isoformat()}):
                return "CONCURRENT_RECONCILIATION"
        offer=self.repo.get_offer(order["offer_id"])
        try:
            quote=self._check(offer,"AFTER_PAYMENT_BEFORE_BOOKING",
                              order["signed_total_rub"],order["hotel_on_request_accepted"])
        except (PriceChanged,NotAvailable):
            self._flag_refund(order_id,"PAID_RECHECK_REQUIRED","POST_PAYMENT_RECHECK_FAILED")
            return "REFUND_REQUIRED"
        if not self.repo.transition(order_id,"PAID_RECHECK_REQUIRED","BOOKING_IN_PROGRESS",
                                    {"final_hotel_status":quote["hotel_status"]}):
            return "CONCURRENT_RECONCILIATION"
        # The very first call to supplier CREATE BOOKING. Never before payment!
        try:
            result=self.supplier.create_booking(self._order(order_id),order_id)
            if not isinstance(result,dict) or result.get("status") not in SUCCESS or not result.get("supplier_booking_id"):
                raise NotAvailable("Supplier did not confirm creation of an order")
            state="BOOKED" if result["status"]=="CONFIRMED" else "SUPPLIER_ON_REQUEST"
            if not self.repo.transition(order_id,"BOOKING_IN_PROGRESS",state,
                                        {"supplier_booking_id":result["supplier_booking_id"]}):
                # Supplier may have booked; human recovery required, NEVER retry blindly.
                return "BOOKING_RECONCILIATION_REQUIRED"
            event=("TOUR_BOOKED" if state=="BOOKED" else "TOUR_REQUESTED_WAITING_HOTEL")
            self.outbox.enqueue_once(order_id+":"+event,{
                "type":event,"order_id":order_id,"supplier_booking_id":result["supplier_booking_id"]})
            return state
        except Exception:
            self._flag_refund(order_id,"BOOKING_IN_PROGRESS","SUPPLIER_BOOKING_FAILED")
            return "REFUND_REQUIRED"

    def _flag_refund(self,order_id:str,expected:str,reason:str):
        if not self.repo.transition(order_id,expected,"REFUND_REQUIRED",{"failure_reason":reason}):
            raise BadOrder("Concurrent order change needs manual reconciliation")
        order=self._order(order_id)
        self.outbox.enqueue_once(order_id+":REFUND_REQUIRED",{
            "type":"REFUND_REQUIRED","order_id":order_id,"reason":reason})
        # Persist the intent BEFORE calling PSP. A refund request failure is a human incident.
        try:
            self.payment.refund(order["payment_id"],order_id+":refund")
            self.repo.transition(order_id,"REFUND_REQUIRED","REFUND_PENDING",{})
        except Exception:
            pass

    def _order(self,order_id:str)->dict[str,Any]:
        order=self.repo.get_order(order_id)
        if not isinstance(order,dict):
            raise BadOrder("Order not found")
        return order

    def status(self,order_id:str,status_token:str)->dict[str,str]:
        order=self._order(order_id)
        provided=hashlib.sha256(status_token.encode()).hexdigest() if isinstance(status_token,str) else ""
        if not secrets.compare_digest(provided,order.get("view_token_hash","")):
            raise BadOrder("Unauthorized order status")
        return {"status":order["status"],"order_id":order_id}
