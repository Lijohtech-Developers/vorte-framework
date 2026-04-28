"""
Vorte M-Pesa Module — Events
==============================
Event data classes for M-Pesa payment lifecycle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, Optional


@dataclass
class MpesaEvent:
    """Base M-Pesa event."""
    event_type: str = ""
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    raw: Dict[str, Any] = field(default_factory=dict)


@dataclass
class MpesaPaymentReceived(MpesaEvent):
    """Fired when a successful M-Pesa payment is received."""
    transaction_id: str = ""
    phone_number: str = ""
    amount: float = 0.0
    reference: str = ""
    shortcode: str = ""

    @classmethod
    def from_callback(cls, data: Dict[str, Any]) -> "MpesaPaymentReceived":
        """Parse from a Daraja STK Push callback."""
        stk = data.get("Body", {}).get("stkCallback", {})
        metadata = {}
        for item in stk.get("CallbackMetadata", {}).get("Item", []):
            metadata[item.get("Name", "")] = item.get("Value")
        return cls(
            event_type="mpesa.payment.received",
            transaction_id=str(metadata.get("MpesaReceiptNumber", "")),
            phone_number=str(metadata.get("PhoneNumber", "")),
            amount=float(metadata.get("Amount", 0)),
            reference=str(metadata.get("BillRefNumber", stk.get("CheckoutRequestID", ""))),
            shortcode=str(metadata.get("BusinessShortCode", "")),
            raw=data,
        )


@dataclass
class MpesaPaymentFailed(MpesaEvent):
    """Fired when an M-Pesa payment fails."""
    transaction_id: str = ""
    error_code: str = ""
    error_message: str = ""
    checkout_request_id: str = ""

    @classmethod
    def from_callback(cls, data: Dict[str, Any]) -> "MpesaPaymentFailed":
        stk = data.get("Body", {}).get("stkCallback", {})
        result_desc = stk.get("ResultDesc", "")
        return cls(
            event_type="mpesa.payment.failed",
            error_code=str(stk.get("ResultCode", "")),
            error_message=result_desc,
            checkout_request_id=stk.get("CheckoutRequestID", ""),
            raw=data,
        )


@dataclass
class MpesaPaymentTimeout(MpesaEvent):
    """Fired when an M-Pesa payment times out."""
    transaction_id: str = ""
    reason: str = "timeout"
    raw: Dict[str, Any] = field(default_factory=dict)
