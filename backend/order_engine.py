"""JAMAICA checkout domain engine (no network or card processing).

Production requires concrete authorized supplier, acquiring, and durable repository
adapters. This module never creates a fake order or payment, and never runs on
GitHub Pages. It can be hosted behind an HTTPS API once adapters are installed.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import secrets
from typing import Any, Callable, Protocol
from urllib.parse import urlsplit

from backend.supplier_sale_policy import check_supplier_evidence, valid_offer_evidence


class CheckoutError(Exception):
    code = "CHECKOUT_FAILED"
    def __init__(self, detail: str = ""):
        super().__init__(detail or self.code)


class NotConfigured(CheckoutError):
    code = "NOT_CONFIGURED"


class NotAvailable(CheckoutError):
    code = "NOT_AVAILABLE"


class PriceChanged(CheckoutError):
    code = "PRICE_CHANGED"


class GatewayError(CheckoutError):
    code = "PAYMENT_GATEWAY_ERROR"


class BadOrder(CheckoutError):
    code = "BAD_ORDER"


@dataclass(frozen=True)
class Merchant:
    seller_legal_name: str
    registration_number: str
    terms_version: str
    payment_origin: str
    live_enabled: bool = False

    def assert_ready(self) -> None:
        if not self.live_enabled or min(len(self.seller_legal_name.strip()),
                                        len(self.registration_number.strip()),
                                        len(self.terms_version.strip())) < 3:
            raise NotConfigured("Merchant identity and approved contract required")
        u = urlsplit(self.payment_origin)
        if u.scheme != "https" or not u.netloc or u.username or u.password or u.path not in ("", "/"):
            raise NotConfigured("Approved HTTPS payment origin required")


class OfferRepo(Protocol):
    def get_offer(self, offer_id: str) -> dict[str, Any] | None: ...
    def create_order(self, order: dict[str, Any]) -> None: ...
    def get_order(self, order_id: str) -> dict[str, Any] | None: ...
    def update_order(self, order_id: str, patch: dict[str, Any]) -> None: ...


class SupplierAdapter(Protocol):
    def hold_and_requote(self, offer: dict[str, Any], idempotency_key: str) -> dict[str, Any]: ...
    def confirm_booking(self, hold_id: str, order_id: str) -> str: ...
    def release_hold(self, hold_id: str) -> None: ...


class PaymentAdapter(Protocol):
    def create_payment(self, order_id: str, amount_rub: int, idempotency_key: str) -> dict[str, str]: ...
    def get_authoritative_status(self, payment_id: str) -> str: ...
    def refund(self, payment_id: str, idempotency_key: str) -> None: ...


REQUIRED = ("quote_verified", "availability_verified", "flights_out_green",
            "flights_back_green", "price_scope_verified", "total_two_verified",
            "publish_approved")


def valid_offer(offer: dict[str, Any] | None, now: datetime) -> bool:
    if not isinstance(offer, dict) or any(offer.get(k) is not True for k in REQUIRED):
        return False
    if not valid_offer_evidence(offer):
        return False
    if (type(offer.get("total_rub")) is not int or offer["total_rub"] <= 0 or
            offer.get("adults") != 2 or offer.get("children") != 0):
        return False
    try:
        checked = datetime.fromisoformat(offer["quote_verified_at"].replace("Z", "+00:00"))
        expires = datetime.fromisoformat(offer["expires_at"].replace("Z", "+00:00"))
        if checked.tzinfo is None or expires.tzinfo is None:
            return False
        checked = checked.astimezone(timezone.utc)
        expires = expires.astimezone(timezone.utc)
        age = (now - checked).total_seconds()
        return -60 <= age < 20 * 60 and expires > now
    except (KeyError, TypeError, ValueError, AttributeError):
        return False


class OrderEngine:
    def __init__(self, merchant: Merchant, repo: OfferRepo, supplier: SupplierAdapter,
                 payment: PaymentAdapter, clock: Callable[[], datetime] | None = None):
        self.merchant = merchant
        self.repo = repo
        self.supplier = supplier
        self.payment = payment
        self.clock = clock or (lambda: datetime.now(timezone.utc))

    def prepare(self, *, offer_id: str, expected_total_rub: int,
                terms_version: str, terms_accepted: bool) -> dict[str, Any]:
        """Never charge for a tour until supplier has held inventory at the expected price."""
        self.merchant.assert_ready()
        if not terms_accepted or terms_version != self.merchant.terms_version:
            raise BadOrder("Buyer has not accepted the applicable terms")
        if not isinstance(offer_id, str) or not 8 <= len(offer_id) <= 100:
            raise BadOrder("Offer reference invalid")
        if type(expected_total_rub) is not int or expected_total_rub <= 0:
            raise BadOrder("Invalid expected price")
        offer = self.repo.get_offer(offer_id)
        if not valid_offer(offer, self.clock()):
            raise NotAvailable("No recent verified offer")
        if offer["total_rub"] != expected_total_rub:
            raise PriceChanged("Display price differs from trusted offer")
        # No passenger passports or card data enter this engine.
        order_id = secrets.token_urlsafe(22)
        status_token = secrets.token_urlsafe(32)
        hold_id = None
        try:
            held = self.supplier.hold_and_requote(offer, order_id)
            hold_id = held.get("hold_id")
            if not hold_id or held.get("inventory_confirmed") is not True:
                raise NotAvailable("Supplier has not confirmed inventory")
            if (held.get("flights_out_green") is not True or
                held.get("flights_back_green") is not True or
                not check_supplier_evidence({
                    **held,
                    "flight_out_available":held.get("flights_out_green"),
                    "flight_back_available":held.get("flights_back_green"),
                },offer.get("sale_policy"))):
                raise NotAvailable("Both flights and required supplier quality mark must be verified")
            if held.get("currency") != "RUB" or type(held.get("total_rub")) is not int:
                raise NotAvailable("Supplier returned invalid price/currency")
            if held["total_rub"] != expected_total_rub:
                raise PriceChanged("Supplier price changed before payment")
            # Durable repository must commit the pending order before PSP creation.
            self.repo.create_order({
                "id": order_id, "view_token": status_token, "offer_id": offer_id,
                "hold_id": hold_id, "total_rub": expected_total_rub,
                "status": "RESERVED", "payment_id": None,
            })
            p = self.payment.create_payment(order_id, expected_total_rub, order_id)
            url = p.get("payment_iframe_url", "")
            parsed = urlsplit(url)
            expected_origin = self.merchant.payment_origin.rstrip("/")
            origin = parsed.scheme + "://" + (parsed.netloc or "")
            if not p.get("payment_id") or parsed.scheme != "https" or origin != expected_origin:
                raise GatewayError("Payment provider URL not approved")
            self.repo.update_order(order_id, {"payment_id": p["payment_id"],
                                               "status": "PAYMENT_PENDING"})
            return {"status": "PAYMENT_READY", "order_id": order_id,
                    "status_token": status_token, "total_rub": expected_total_rub,
                    "payment_iframe_url": url}
        except Exception:
            if hold_id is not None:
                try:
                    self.supplier.release_hold(hold_id)
                except Exception:
                    # Production implementation must enqueue a durable release/reconciliation job.
                    pass
            raise

    def status(self, *, order_id: str, status_token: str) -> dict[str, str]:
        o = self.repo.get_order(order_id)
        if not o or not secrets.compare_digest(str(o.get("view_token", "")), status_token):
            raise BadOrder("Order not found")
        return {"status": o["status"]}

    def reconcile_payment(self, *, order_id: str) -> None:
        """Server-side reconciliation only, triggered after authenticated PSP notification.
        Provider status is independently fetched; browser returns are not proof of payment.
        """
        order = self.repo.get_order(order_id)
        if not order:
            raise BadOrder("Order not found")
        if order["status"] in ("PAID_BOOKED", "REFUND_REQUIRED"):
            return
        if order["status"] != "PAYMENT_PENDING" or not order.get("payment_id"):
            raise BadOrder("Order is not payable")
        provider_status = self.payment.get_authoritative_status(order["payment_id"])
        if provider_status != "PAID":
            if provider_status in ("FAILED", "EXPIRED"):
                self.repo.update_order(order_id, {"status": "FAILED"})
                self.supplier.release_hold(order["hold_id"])
            return
        try:
            supplier_booking_id = self.supplier.confirm_booking(order["hold_id"], order_id)
            if not supplier_booking_id:
                raise NotAvailable("Supplier booking not confirmed")
            self.repo.update_order(order_id, {
                "status": "PAID_BOOKED", "supplier_booking_id": supplier_booking_id
            })
        except Exception:
            # Do not mark success if money was paid but booking failed.
            self.repo.update_order(order_id, {"status": "REFUND_REQUIRED"})
            self.payment.refund(order["payment_id"], order_id)
            raise
