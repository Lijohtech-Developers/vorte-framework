"""
Vorte Notifications Module — Notifier & Channels
=================================================
Multi-channel notification system with topic/user targeting.

Usage::

    notifier = Notifier(channels=["email", "slack"])
    await notifier.user("user_123").push(title="New Message", body="You have a new message")
    await notifier.topic("billing").push(title="Invoice Due", body="Your invoice is due")
"""

from __future__ import annotations

import asyncio
import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Callable, Dict, List, Optional, Set

logger = logging.getLogger("vorte.modules.notifications")


class NotificationChannel(str, Enum):
    """Supported notification channels."""
    PUSH = "push"
    EMAIL = "email"
    SMS = "sms"
    SLACK = "slack"


@dataclass
class NotificationMessage:
    """Represents a notification to be sent."""
    title: str = ""
    body: str = ""
    data: Dict[str, Any] = field(default_factory=dict)
    channel: Optional[NotificationChannel] = None
    priority: str = "normal"  # low, normal, high
    image_url: str = ""
    action_url: str = ""


# ---------------------------------------------------------------------------
# Channel adapters
# ---------------------------------------------------------------------------

class ChannelAdapter(abc.ABC if "abc" in dir() else object):
    """Base class for notification channel adapters."""

    async def send(self, recipient: str, message: NotificationMessage) -> Dict[str, Any]:
        return {"status": "ok"}

    async def send_batch(self, recipients: List[str], message: NotificationMessage) -> List[Dict[str, Any]]:
        results = []
        for r in recipients:
            results.append(await self.send(r, message))
        return results


# Import abc properly
import abc


class ChannelAdapterBase(abc.ABC):
    """Base class for notification channel adapters."""

    @abc.abstractmethod
    async def send(self, recipient: str, message: NotificationMessage) -> Dict[str, Any]:
        """Send a notification to a single recipient."""

    async def send_batch(self, recipients: List[str], message: NotificationMessage) -> List[Dict[str, Any]]:
        results = []
        for r in recipients:
            results.append(await self.send(r, message))
        return results


class EmailNotificationAdapter(ChannelAdapterBase):
    """Send notifications via email (uses the Mailer module)."""

    async def send(self, recipient: str, message: NotificationMessage) -> Dict[str, Any]:
        try:
            from vorte.modules.mailer.mailer import MailMessage
            from vorte.core.di import _global_container
            mailer = _global_container.resolve("Mailer") if _global_container.has("Mailer") else None
            if mailer:
                msg = MailMessage(
                    to=recipient,
                    subject=message.title,
                    html=f"<h2>{message.title}</h2><p>{message.body}</p>",
                    text=f"{message.title}\n\n{message.body}",
                )
                return await mailer.send(msg)
            return {"status": "skipped", "reason": "Mailer not configured"}
        except Exception as exc:
            logger.error("Email notification failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


class PushNotificationAdapter(ChannelAdapterBase):
    """Send push notifications via Firebase Cloud Messaging."""

    def __init__(self, server_key: str = "") -> None:
        self._server_key = server_key

    async def send(self, recipient: str, message: NotificationMessage) -> Dict[str, Any]:
        if not self._server_key:
            return {"status": "skipped", "reason": "FCM server key not configured"}
        try:
            import httpx
            payload = {
                "to": recipient,
                "notification": {"title": message.title, "body": message.body},
                "data": message.data,
                "priority": message.priority,
            }
            if message.image_url:
                payload["notification"]["image"] = message.image_url
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    "https://fcm.googleapis.com/fcm/send",
                    json=payload,
                    headers={"Authorization": f"key={self._server_key}", "Content-Type": "application/json"},
                )
                return resp.json()
        except Exception as exc:
            logger.error("Push notification failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


class SmsNotificationAdapter(ChannelAdapterBase):
    """Send SMS notifications via Twilio."""

    def __init__(self, account_sid: str = "", auth_token: str = "", from_number: str = "") -> None:
        self._account_sid = account_sid
        self._auth_token = auth_token
        self._from_number = from_number

    async def send(self, recipient: str, message: NotificationMessage) -> Dict[str, Any]:
        if not self._account_sid:
            return {"status": "skipped", "reason": "Twilio not configured"}
        try:
            import httpx
            url = f"https://api.twilio.com/2010-04-01/Accounts/{self._account_sid}/Messages.json"
            payload = {"To": recipient, "From": self._from_number, "Body": f"{message.title}\n{message.body}"}
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    url,
                    data=payload,
                    auth=(self._account_sid, self._auth_token),
                )
                return {"status": "sent" if resp.status_code in (200, 201) else "failed", "code": resp.status_code}
        except Exception as exc:
            logger.error("SMS notification failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


class SlackNotificationAdapter(ChannelAdapterBase):
    """Send notifications to Slack channels or users."""

    def __init__(self, webhook_url: str = "", bot_token: str = "") -> None:
        self._webhook_url = webhook_url
        self._bot_token = bot_token

    async def send(self, recipient: str, message: NotificationMessage) -> Dict[str, Any]:
        try:
            import httpx
            if self._webhook_url:
                payload = {
                    "text": f"*{message.title}*\n{message.body}",
                    "blocks": [
                        {"type": "section", "text": {"type": "mrkdwn", "text": f"*{message.title}*\n{message.body}"}},
                    ],
                }
                if message.action_url:
                    payload["blocks"].append({
                        "type": "actions",
                        "elements": [{"type": "button", "text": {"type": "plain_text", "text": "View"}, "url": message.action_url}],
                    })
                async with httpx.AsyncClient() as client:
                    resp = await client.post(self._webhook_url, json=payload)
                    return {"status": "sent" if resp.status_code == 200 else "failed"}
            return {"status": "skipped", "reason": "Slack webhook not configured"}
        except Exception as exc:
            logger.error("Slack notification failed: %s", exc)
            return {"status": "failed", "error": str(exc)}


# ---------------------------------------------------------------------------
# Notifier
# ---------------------------------------------------------------------------

class Notifier:
    """
    Central notification dispatcher.

    Usage::

        notifier = Notifier(channels=["email", "push"])
        await notifier.user("user@example.com").push(title="Hi", body="Hello!")
        await notifier.topic("alerts").broadcast(title="System Alert", body="...")
    """

    def __init__(
        self,
        channels: Optional[List[str]] = None,
        fcm_server_key: str = "",
        twilio_account_sid: str = "",
        twilio_auth_token: str = "",
        twilio_from_number: str = "",
        slack_webhook_url: str = "",
        slack_bot_token: str = "",
    ) -> None:
        self._channels: Dict[str, ChannelAdapterBase] = {}
        channel_list = [c.lower() for c in (channels or [])]

        if "email" in channel_list:
            self._channels["email"] = EmailNotificationAdapter()
        if "push" in channel_list:
            self._channels["push"] = PushNotificationAdapter(server_key=fcm_server_key)
        if "sms" in channel_list:
            self._channels["sms"] = SmsNotificationAdapter(
                account_sid=twilio_account_sid, auth_token=twilio_auth_token, from_number=twilio_from_number
            )
        if "slack" in channel_list:
            self._channels["slack"] = SlackNotificationAdapter(webhook_url=slack_webhook_url, bot_token=slack_bot_token)

        self._topics: Dict[str, Set[str]] = {}  # topic -> set of recipients
        self._subscribers: Dict[str, Set[str]] = {}  # user_id -> set of topics

    # -- user targeting --

    def user(self, recipient: str) -> "NotificationBuilder":
        """Target a specific user."""
        return NotificationBuilder(notifier=self, recipients=[recipient])

    def users(self, recipients: List[str]) -> "NotificationBuilder":
        """Target multiple users."""
        return NotificationBuilder(notifier=self, recipients=recipients)

    # -- topic targeting --

    def topic(self, topic_name: str) -> "TopicBuilder":
        """Target a topic (broadcasts to all subscribers)."""
        return TopicBuilder(notifier=self, topic=topic_name)

    def subscribe(self, user_id: str, topic: str) -> None:
        """Subscribe a user to a topic."""
        self._topics.setdefault(topic, set()).add(user_id)
        self._subscribers.setdefault(user_id, set()).add(topic)

    def unsubscribe(self, user_id: str, topic: str) -> None:
        """Unsubscribe a user from a topic."""
        self._topics.get(topic, set()).discard(user_id)
        self._subscribers.get(user_id, set()).discard(topic)

    def get_subscribers(self, topic: str) -> List[str]:
        """Get all subscribers for a topic."""
        return list(self._topics.get(topic, set()))

    # -- direct send --

    async def send(self, recipient: str, message: NotificationMessage,
                   channels: Optional[List[str]] = None) -> Dict[str, Any]:
        """Send a notification to a recipient on specified channels."""
        results: Dict[str, Dict[str, Any]] = {}
        target_channels = channels or list(self._channels.keys())
        for ch in target_channels:
            adapter = self._channels.get(ch)
            if adapter:
                results[ch] = await adapter.send(recipient, message)
        return {"recipient": recipient, "results": results}

    async def broadcast(self, message: NotificationMessage, recipients: List[str],
                        channels: Optional[List[str]] = None) -> List[Dict[str, Any]]:
        """Broadcast a notification to multiple recipients."""
        return [await self.send(r, message, channels) for r in recipients]


class NotificationBuilder:
    """Fluent builder for user-targeted notifications."""

    def __init__(self, notifier: Notifier, recipients: List[str]) -> None:
        self._notifier = notifier
        self._recipients = recipients
        self._channels: Optional[List[str]] = None
        self._message = NotificationMessage()

    def push(self, title: str, body: str, **kwargs: Any) -> "NotificationBuilder":
        self._message = NotificationMessage(title=title, body=body, **kwargs)
        return self

    def via(self, *channels: str) -> "NotificationBuilder":
        self._channels = list(channels)
        return self

    async def send(self) -> List[Dict[str, Any]]:
        return await self._notifier.broadcast(self._message, self._recipients, self._channels)


class TopicBuilder:
    """Fluent builder for topic-based notifications."""

    def __init__(self, notifier: Notifier, topic: str) -> None:
        self._notifier = notifier
        self._topic = topic
        self._channels: Optional[List[str]] = None
        self._message = NotificationMessage()

    def push(self, title: str, body: str, **kwargs: Any) -> "TopicBuilder":
        self._message = NotificationMessage(title=title, body=body, **kwargs)
        return self

    def via(self, *channels: str) -> "TopicBuilder":
        self._channels = list(channels)
        return self

    async def broadcast(self) -> List[Dict[str, Any]]:
        """Send to all topic subscribers."""
        recipients = self._notifier.get_subscribers(self._topic)
        return await self._notifier.broadcast(self._message, recipients, self._channels)
