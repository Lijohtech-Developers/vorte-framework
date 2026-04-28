"""
Vorte M-Pesa Module — M-Pesa Client
=====================================
Safaricom Daraja API client for M-Pesa integrations.

Usage::

    client = MpesaClient(
        environment="sandbox",
        consumer_key="xxx",
        consumer_secret="yyy",
        shortcode="174379",
        passkey="zzz",
        callback_url="https://example.com/api/mpesa/callback/stk",
    )

    # STK Push
    result = await client.stk_push(
        phone_number="254708374149",
        amount=1,
        reference="ORDER_123",
        description="Payment for Order 123",
    )

    # C2B Register URL
    result = await client.register_c2b_url(
        confirmation_url="https://example.com/api/mpesa/callback/c2b",
        validation_url="https://example.com/api/mpesa/callback/c2b",
    )
"""

from __future__ import annotations

import asyncio
import base64
import hashlib
import json
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

logger = logging.getLogger("vorte.modules.mpesa")

_BASE_URLS = {
    "sandbox": "https://sandbox.safaricom.co.ke",
    "production": "https://api.safaricom.co.ke",
}


class MpesaClient:
    """
    Safaricom Daraja API client.

    Provides methods for STK Push, C2B, B2C, B2B, Account Balance,
    Transaction Status, Reversal, and QR Code.
    """

    def __init__(
        self,
        environment: str = "sandbox",
        consumer_key: str = "",
        consumer_secret: str = "",
        shortcode: str = "",
        passkey: str = "",
        callback_url: str = "",
        b2c_security_credential: str = "",
        initiator_name: str = "apitest",
    ) -> None:
        self._environment = environment
        self._consumer_key = consumer_key
        self._consumer_secret = consumer_secret
        self._shortcode = shortcode
        self._passkey = passkey
        self._callback_url = callback_url.rstrip("/")
        self._b2c_credential = b2c_security_credential
        self._initiator_name = initiator_name
        self._base_url = _BASE_URLS.get(environment, _BASE_URLS["sandbox"])
        self._access_token: Optional[str] = None
        self._token_expiry: float = 0

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    async def get_access_token(self) -> str:
        """Obtain or return cached OAuth access token."""
        if self._access_token and time.time() < self._token_expiry:
            return self._access_token

        import httpx
        url = f"{self._base_url}/oauth/v1/generate?grant_type=client_credentials"
        credentials = base64.b64encode(f"{self._consumer_key}:{self._consumer_secret}".encode()).decode()

        async with httpx.AsyncClient() as client:
            resp = await client.get(url, headers={"Authorization": f"Basic {credentials}"})
            resp.raise_for_status()
            data = resp.json()
            self._access_token = data["access_token"]
            self._token_expiry = time.time() + data.get("expires_in", 3600) - 60
            return self._access_token

    def _headers(self) -> Dict[str, str]:
        return {"Authorization": f"Bearer {self._access_token}", "Content-Type": "application/json"}

    # ------------------------------------------------------------------
    # STK Push (Lipa Na M-Pesa Online)
    # ------------------------------------------------------------------

    def _generate_stk_password(self) -> str:
        """Generate the base64-encoded password for STK Push."""
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        raw = f"{self._shortcode}{self._passkey}{timestamp}"
        password = base64.b64encode(raw.encode()).decode()
        return password, timestamp

    async def stk_push(
        self,
        phone_number: str,
        amount: float,
        reference: str = "",
        description: str = "Payment",
        account_ref: str = "Account",
    ) -> Dict[str, Any]:
        """Initiate an STK Push (Lipa Na M-Pesa Online)."""
        await self.get_access_token()
        password, timestamp = self._generate_stk_password()

        # Normalize phone number (strip leading 0 or +, prepend 254)
        phone = phone_number.strip().replace("+", "").replace(" ", "")
        if phone.startswith("0"):
            phone = "254" + phone[1:]
        if not phone.startswith("254"):
            phone = "254" + phone

        import httpx
        url = f"{self._base_url}/mpesa/stkpush/v1/processrequest"
        payload = {
            "BusinessShortCode": self._shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "TransactionType": "CustomerPayBillOnline",
            "Amount": int(amount),
            "PartyA": phone,
            "PartyB": self._shortcode,
            "PhoneNumber": phone,
            "CallBackURL": f"{self._callback_url}/stk",
            "AccountReference": account_ref[:12],
            "TransactionDesc": description[:13],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    async def stk_query(self, checkout_request_id: str) -> Dict[str, Any]:
        """Query the status of an STK Push request."""
        await self.get_access_token()
        password, timestamp = self._generate_stk_password()

        import httpx
        url = f"{self._base_url}/mpesa/stkpushquery/v1/query"
        payload = {
            "BusinessShortCode": self._shortcode,
            "Password": password,
            "Timestamp": timestamp,
            "CheckoutRequestID": checkout_request_id,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    # ------------------------------------------------------------------
    # C2B
    # ------------------------------------------------------------------

    async def register_c2b_url(
        self,
        response_type: str = "Completed",
        confirmation_url: str = "",
        validation_url: str = "",
        short_code: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Register C2B confirmation and validation URLs."""
        await self.get_access_token()
        code = short_code or self._shortcode
        confirm = confirmation_url or f"{self._callback_url}/c2b"
        valid = validation_url or f"{self._callback_url}/c2b"

        import httpx
        url = f"{self._base_url}/mpesa/c2b/v1/registerurl"
        payload = {
            "ShortCode": code,
            "ResponseType": response_type,
            "ConfirmationURL": confirm,
            "ValidationURL": valid,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    async def simulate_c2b(self, phone_number: str, amount: float, short_code: Optional[str] = None,
                           bill_ref: str = "") -> Dict[str, Any]:
        """Simulate a C2B transaction (sandbox only)."""
        await self.get_access_token()
        code = short_code or self._shortcode
        phone = phone_number.strip().replace("+", "").replace(" ", "")
        if phone.startswith("0"):
            phone = "254" + phone[1:]

        import httpx
        url = f"{self._base_url}/mpesa/c2b/v1/simulate"
        payload = {
            "ShortCode": code,
            "CommandID": "CustomerPayBillOnline",
            "Amount": int(amount),
            "Msisdn": phone,
            "BillRefNumber": bill_ref,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    # ------------------------------------------------------------------
    # B2C
    # ------------------------------------------------------------------

    async def b2c(
        self,
        phone_number: str,
        amount: float,
        remarks: str = "B2C Payment",
        command_id: str = "BusinessPayment",
        occasion: str = "",
    ) -> Dict[str, Any]:
        """Initiate a B2C transaction."""
        await self.get_access_token()
        phone = phone_number.strip().replace("+", "").replace(" ", "")
        if phone.startswith("0"):
            phone = "254" + phone[1:]

        import httpx
        url = f"{self._base_url}/mpesa/b2c/v3/paymentrequest"
        payload = {
            "OriginatorConversationID": f"B2C_{int(time.time())}",
            "InitiatorName": self._initiator_name,
            "SecurityCredential": self._b2c_credential,
            "CommandID": command_id,
            "Amount": int(amount),
            "PartyA": self._shortcode,
            "PartyB": phone,
            "Remarks": remarks[:100],
            "QueueTimeOutURL": f"{self._callback_url}/b2c/timeout",
            "ResultURL": f"{self._callback_url}/b2c/result",
            "Occasion": occasion[:100],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    # ------------------------------------------------------------------
    # B2B
    # ------------------------------------------------------------------

    async def b2b(
        self,
        short_code: str,
        amount: float,
        remarks: str = "B2B Payment",
        command_id: str = "B2BTransfer",
        account_ref: str = "",
    ) -> Dict[str, Any]:
        """Initiate a B2B transaction."""
        await self.get_access_token()

        import httpx
        url = f"{self._base_url}/mpesa/b2b/v1/paymentrequest"
        payload = {
            "Initiator": self._initiator_name,
            "SecurityCredential": self._b2c_credential,
            "CommandID": command_id,
            "Amount": int(amount),
            "PartyA": self._shortcode,
            "PartyB": short_code,
            "Remarks": remarks[:100],
            "AccountReference": account_ref,
            "QueueTimeOutURL": f"{self._callback_url}/b2b/timeout",
            "ResultURL": f"{self._callback_url}/b2b/result",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    # ------------------------------------------------------------------
    # Account Balance
    # ------------------------------------------------------------------

    async def account_balance(self, remarks: str = "Balance Query") -> Dict[str, Any]:
        """Query the account balance."""
        await self.get_access_token()

        import httpx
        url = f"{self._base_url}/mpesa/accountbalance/v1/query"
        payload = {
            "Initiator": self._initiator_name,
            "SecurityCredential": self._b2c_credential,
            "CommandID": "AccountBalance",
            "PartyA": self._shortcode,
            "IdentifierType": "4",
            "Remarks": remarks[:100],
            "QueueTimeOutURL": f"{self._callback_url}/balance/timeout",
            "ResultURL": f"{self._callback_url}/balance/result",
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    # ------------------------------------------------------------------
    # Transaction Status
    # ------------------------------------------------------------------

    async def transaction_status(
        self,
        transaction_id: str,
        remarks: str = "Transaction Status",
        occasion: str = "",
    ) -> Dict[str, Any]:
        """Query the status of a transaction."""
        await self.get_access_token()

        import httpx
        url = f"{self._base_url}/mpesa/transactionstatus/v1/query"
        payload = {
            "Initiator": self._initiator_name,
            "SecurityCredential": self._b2c_credential,
            "CommandID": "TransactionStatusQuery",
            "TransactionID": transaction_id,
            "OriginatorConversationID": f"TXQ_{int(time.time())}",
            "PartyA": self._shortcode,
            "IdentifierType": "4",
            "ResultURL": f"{self._callback_url}/txstatus/result",
            "QueueTimeOutURL": f"{self._callback_url}/txstatus/timeout",
            "Remarks": remarks[:100],
            "Occasion": occasion[:100],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    # ------------------------------------------------------------------
    # Reversal
    # ------------------------------------------------------------------

    async def reverse(
        self,
        transaction_id: str,
        amount: float,
        remarks: str = "Reversal",
        occasion: str = "",
    ) -> Dict[str, Any]:
        """Reverse an M-Pesa transaction."""
        await self.get_access_token()

        import httpx
        url = f"{self._base_url}/mpesa/reversal/v1/request"
        payload = {
            "Initiator": self._initiator_name,
            "SecurityCredential": self._b2c_credential,
            "CommandID": "TransactionReversal",
            "TransactionID": transaction_id,
            "Amount": int(amount),
            "ReceiverParty": self._shortcode,
            "RecieverIdentifierType": "11",
            "ResultURL": f"{self._callback_url}/reversal/result",
            "QueueTimeOutURL": f"{self._callback_url}/reversal/timeout",
            "Remarks": remarks[:100],
            "Occasion": occasion[:100],
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()

    # ------------------------------------------------------------------
    # QR Code
    # ------------------------------------------------------------------

    async def generate_qr(
        self,
        amount: float,
        ref: str = "",
        cpi: str = "174379",
        size: int = 300,
    ) -> Dict[str, Any]:
        """Generate a dynamic M-Pesa QR code."""
        await self.get_access_token()

        import httpx
        url = f"{self._base_url}/mpesa/qrcode/v1/generate"
        payload = {
            "MerchantName": "Vorte Merchant",
            "RefNo": ref[:12],
            "Amount": int(amount),
            "TrxCode": "BG",
            "CPI": cpi,
            "Size": size,
        }

        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(url, json=payload, headers=self._headers())
            return resp.json()
