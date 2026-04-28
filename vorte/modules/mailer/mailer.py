"""
Vorte Mailer Module — Mailer, Drivers & Fluent API
====================================================
Supports SMTP, SendGrid, Resend, and AWS SES with Jinja2 template rendering.

Usage (fluent API)::

    await mailer \
        .to("user@example.com") \
        .subject("Welcome!") \
        .template("welcome", {"name": "Alice"}) \
        .send()

Usage (direct)::

    msg = MailMessage(to="user@example.com", subject="Hello", html="<b>Hi</b>")
    await mailer.send(msg)
"""

from __future__ import annotations

import abc
import asyncio
import json
import logging
import smtplib
from dataclasses import dataclass, field
from email.message import EmailMessage
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

logger = logging.getLogger("vorte.modules.mailer")


# ---------------------------------------------------------------------------
# MailMessage
# ---------------------------------------------------------------------------

@dataclass
class Attachment:
    """Email attachment."""
    filename: str
    content: bytes
    content_type: str = "application/octet-stream"
    disposition: str = "attachment"


@dataclass
class MailMessage:
    """Represents an email message."""
    to: Union[str, List[str]] = ""
    cc: List[str] = field(default_factory=list)
    bcc: List[str] = field(default_factory=list)
    from_address: str = ""
    from_name: str = ""
    reply_to: str = ""
    subject: str = ""
    text: str = ""
    html: str = ""
    attachments: List[Attachment] = field(default_factory=list)
    headers: Dict[str, str] = field(default_factory=dict)
    tags: List[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Abstract driver
# ---------------------------------------------------------------------------

class MailDriver(abc.ABC):
    """Interface every mail driver must implement."""

    @abc.abstractmethod
    async def send(self, message: MailMessage) -> Dict[str, Any]:
        """Send an email and return a result dict."""

    async def close(self) -> None:
        """Close any open connections."""


# ---------------------------------------------------------------------------
# SMTP Driver
# ---------------------------------------------------------------------------

class SmtpDriver(MailDriver):
    """Send emails via SMTP."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 587,
        username: str = "",
        password: str = "",
        use_tls: bool = True,
        use_ssl: bool = False,
    ) -> None:
        self._host = host
        self._port = port
        self._username = username
        self._password = password
        self._use_tls = use_tls
        self._use_ssl = use_ssl

    def _build_message(self, message: MailMessage) -> EmailMessage:
        if message.html:
            msg = MIMEMultipart("alternative")
            msg.attach(MIMEText(message.text or "", "plain"))
            msg.attach(MIMEText(message.html, "html"))
        else:
            msg = EmailMessage()
            msg.set_content(message.text or "")

        if isinstance(message.to, str):
            msg["To"] = message.to
        else:
            msg["To"] = ", ".join(message.to)

        from_hdr = message.from_name and f"{message.from_name} <{message.from_address}>" or message.from_address
        msg["From"] = from_hdr
        msg["Subject"] = message.subject
        if message.reply_to:
            msg["Reply-To"] = message.reply_to
        for k, v in message.headers.items():
            msg[k] = v

        for att in message.attachments:
            msg.add_attachment(att.content, maintype=att.content_type.split("/")[0],
                               subtype=att.content_type.split("/")[1], filename=att.filename)

        return msg

    async def send(self, message: MailMessage) -> Dict[str, Any]:
        msg = self._build_message(message)
        recipients = [message.to] if isinstance(message.to, str) else message.to

        def _send() -> None:
            if self._use_ssl:
                server = smtplib.SMTP_SSL(self._host, self._port)
            else:
                server = smtplib.SMTP(self._host, self._port)
            if self._use_tls and not self._use_ssl:
                server.starttls()
            if self._username:
                server.login(self._username, self._password)
            server.send_message(msg, to_addrs=recipients)
            server.quit()

        try:
            await asyncio.to_thread(_send)
            return {"status": "sent", "recipients": recipients}
        except Exception as exc:
            logger.error("SMTP send failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


# ---------------------------------------------------------------------------
# SendGrid Driver
# ---------------------------------------------------------------------------

class SendGridDriver(MailDriver):
    """Send emails via the SendGrid API."""

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            from sendgrid import SendGridAPIClient
            self._client = SendGridAPIClient(self._api_key)
        except ImportError:
            raise RuntimeError("sendgrid package required.  pip install sendgrid")
        return self._client

    async def send(self, message: MailMessage) -> Dict[str, Any]:
        client = self._get_client()
        recipients = [message.to] if isinstance(message.to, str) else message.to
        mail = {
            "from": {"email": message.from_address, "name": message.from_name},
            "subject": message.subject,
            "personalizations": [{"to": [{"email": r} for r in recipients]}],
        }
        if message.text:
            mail["content"] = [{"type": "text/plain", "value": message.text}]
        if message.html:
            mail.setdefault("content", []).append({"type": "text/html", "value": message.html})
        try:
            resp = await asyncio.to_thread(client.send, mail)
            return {"status": "sent", "message_id": resp.headers.get("X-Message-Id", "")}
        except Exception as exc:
            logger.error("SendGrid send failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


# ---------------------------------------------------------------------------
# Resend Driver
# ---------------------------------------------------------------------------

class ResendDriver(MailDriver):
    """Send emails via the Resend API."""

    def __init__(self, api_key: str = "") -> None:
        self._api_key = api_key

    async def send(self, message: MailMessage) -> Dict[str, Any]:
        try:
            import httpx
        except ImportError:
            raise RuntimeError("httpx package required.  pip install httpx")

        recipients = [message.to] if isinstance(message.to, str) else message.to
        payload: Dict[str, Any] = {
            "from": f"{message.from_name} <{message.from_address}>" if message.from_name else message.from_address,
            "to": recipients,
            "subject": message.subject,
        }
        if message.html:
            payload["html"] = message.html
        if message.text:
            payload["text"] = message.text

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                "https://api.resend.com/emails",
                json=payload,
                headers={"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"},
            )
            if resp.status_code in (200, 201):
                return {"status": "sent", "data": resp.json()}
            return {"status": "failed", "error": resp.text}


# ---------------------------------------------------------------------------
# AWS SES Driver
# ---------------------------------------------------------------------------

class SesDriver(MailDriver):
    """Send emails via AWS Simple Email Service."""

    def __init__(self, region: str = "us-east-1", access_key: str = "", secret_key: str = "") -> None:
        self._region = region
        self._access_key = access_key
        self._secret_key = secret_key
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is not None:
            return self._client
        try:
            import boto3
            kwargs: Dict[str, Any] = {"region_name": self._region}
            if self._access_key:
                kwargs["aws_access_key_id"] = self._access_key
                kwargs["aws_secret_access_key"] = self._secret_key
            self._client = boto3.client("ses", **kwargs)
        except ImportError:
            raise RuntimeError("boto3 package required.  pip install boto3")
        return self._client

    async def send(self, message: MailMessage) -> Dict[str, Any]:
        client = self._get_client()
        recipients = [message.to] if isinstance(message.to, str) else message.to
        params: Dict[str, Any] = {
            "Source": message.from_address,
            "Destination": {"ToAddresses": recipients},
            "Message": {
                "Subject": {"Data": message.subject},
                "Body": {},
            },
        }
        if message.text:
            params["Message"]["Body"]["Text"] = {"Data": message.text}
        if message.html:
            params["Message"]["Body"]["Html"] = {"Data": message.html}

        try:
            resp = await asyncio.to_thread(client.send_email, **params)
            return {"status": "sent", "message_id": resp["MessageId"]}
        except Exception as exc:
            logger.error("SES send failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


# ---------------------------------------------------------------------------
# Mailer (unified)
# ---------------------------------------------------------------------------

class Mailer:
    """
    Unified mailer with a fluent builder API and pluggable drivers.

    Usage::

        mailer = Mailer(driver="smtp", host="smtp.gmail.com", port=587, ...)
        result = await mailer.to("user@example.com").subject("Hi").text("Hello").send()
    """

    DRIVER_MAP = {
        "smtp": SmtpDriver,
        "sendgrid": SendGridDriver,
        "resend": ResendDriver,
        "ses": SesDriver,
    }

    def __init__(
        self,
        driver: str = "smtp",
        host: str = "localhost",
        port: int = 587,
        username: str = "",
        password: str = "",
        from_address: str = "noreply@vorte.dev",
        from_name: str = "Vorte App",
        api_key: str = "",
        region: str = "us-east-1",
        templates_dir: str = "templates/emails",
        access_key: str = "",
        secret_key: str = "",
    ) -> None:
        self._from_address = from_address
        self._from_name = from_name
        self._templates_dir = Path(templates_dir)
        self._driver_name = driver

        if driver == "smtp":
            self._driver: MailDriver = SmtpDriver(host=host, port=port, username=username, password=password)
        elif driver == "sendgrid":
            self._driver = SendGridDriver(api_key=api_key)
        elif driver == "resend":
            self._driver = ResendDriver(api_key=api_key)
        elif driver == "ses":
            self._driver = SesDriver(region=region, access_key=access_key or api_key, secret_key=secret_key)
        else:
            self._driver = SmtpDriver(host=host, port=port, username=username, password=password)

    # -- fluent builder methods --

    def to(self, address: Union[str, List[str]]) -> "MailBuilder":
        return MailBuilder(mailer=self)._to(address)

    def subject(self, subject: str) -> "MailBuilder":
        return MailBuilder(mailer=self)._subject(subject)

    def text(self, body: str) -> "MailBuilder":
        return MailBuilder(mailer=self)._text(body)

    def html(self, body: str) -> "MailBuilder":
        return MailBuilder(mailer=self)._html(body)

    def template(self, name: str, data: Optional[Dict[str, Any]] = None) -> "MailBuilder":
        return MailBuilder(mailer=self)._template(name, data or {})

    # -- direct send --

    async def send(self, message: MailMessage) -> Dict[str, Any]:
        """Send a fully-formed MailMessage."""
        if not message.from_address:
            message.from_address = self._from_address
        if not message.from_name:
            message.from_name = self._from_name
        return await self._driver.send(message)

    # -- template rendering --

    def render_template(self, name: str, data: Optional[Dict[str, Any]] = None) -> str:
        """Render a Jinja2 email template."""
        data = data or {}
        template_path = self._templates_dir / f"{name}.html"
        if not template_path.exists():
            raise FileNotFoundError(f"Email template not found: {template_path}")

        try:
            from jinja2 import Environment, FileSystemLoader
        except ImportError:
            raise RuntimeError("jinja2 package required.  pip install jinja2")

        env = Environment(loader=FileSystemLoader(str(self._templates_dir)))
        tmpl = env.get_template(f"{name}.html")
        return tmpl.render(**data)


class MailBuilder:
    """
    Fluent email builder.

    Usage::

        result = await mailer.to("user@example.com").subject("Welcome").template("welcome", {"name": "Alice"}).send()
    """

    def __init__(self, mailer: Mailer) -> None:
        self._mailer = mailer
        self._message = MailMessage()

    def _to(self, address: Union[str, List[str]]) -> "MailBuilder":
        self._message.to = address
        return self

    def _subject(self, subject: str) -> "MailBuilder":
        self._message.subject = subject
        return self

    def _text(self, body: str) -> "MailBuilder":
        self._message.text = body
        return self

    def _html(self, body: str) -> "MailBuilder":
        self._message.html = body
        return self

    def _template(self, name: str, data: Dict[str, Any]) -> "MailBuilder":
        self._message.html = self._mailer.render_template(name, data)
        return self

    def cc(self, *addresses: str) -> "MailBuilder":
        self._message.cc.extend(addresses)
        return self

    def bcc(self, *addresses: str) -> "MailBuilder":
        self._message.bcc.extend(addresses)
        return self

    def reply_to(self, address: str) -> "MailBuilder":
        self._message.reply_to = address
        return self

    def attach(self, filename: str, content: bytes, content_type: str = "application/octet-stream") -> "MailBuilder":
        self._message.attachments.append(Attachment(filename=filename, content=content, content_type=content_type))
        return self

    def header(self, key: str, value: str) -> "MailBuilder":
        self._message.headers[key] = value
        return self

    def tag(self, *tags: str) -> "MailBuilder":
        self._message.tags.extend(tags)
        return self

    async def send(self) -> Dict[str, Any]:
        """Send the built email."""
        return await self._mailer.send(self._message)
