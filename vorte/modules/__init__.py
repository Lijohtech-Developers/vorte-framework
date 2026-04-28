"""Vorte Modules Package - All 22 built-in modules."""

from vorte.modules.auth import AuthModule
from vorte.modules.database import DatabaseModule
from vorte.modules.ai import AIModule
from vorte.modules.agents import AgentsModule
from vorte.modules.cache import CacheModule
from vorte.modules.queue import QueueModule
from vorte.modules.search import SearchModule
from vorte.modules.storage import StorageModule
from vorte.modules.mailer import MailerModule
from vorte.modules.notifications import NotificationsModule
from vorte.modules.mpesa import MpesaModule
from vorte.modules.payments import PaymentsModule
from vorte.modules.tenancy import MultiTenancyModule
from vorte.modules.i18n import I18nModule
from vorte.modules.security import SecurityModule
from vorte.modules.webhooks import WebhooksModule
from vorte.modules.features import FeaturesModule
from vorte.modules.graphql import GraphQLModule
from vorte.modules.logging import LoggingModule
from vorte.modules.sockets import SocketModule
from vorte.modules.dashboard import DashboardModule

__all__ = [
    "AuthModule",
    "DatabaseModule",
    "AIModule",
    "AgentsModule",
    "CacheModule",
    "QueueModule",
    "SearchModule",
    "StorageModule",
    "MailerModule",
    "NotificationsModule",
    "MpesaModule",
    "PaymentsModule",
    "MultiTenancyModule",
    "I18nModule",
    "SecurityModule",
    "WebhooksModule",
    "FeaturesModule",
    "GraphQLModule",
    "LoggingModule",
    "SocketModule",
    "DashboardModule",
]
