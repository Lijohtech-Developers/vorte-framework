"""Vorte Sockets Module - Room and Presence convenience wrappers."""

# Room and Presence classes are defined in manager.py
# This file provides import shortcuts for backward compatibility

from vorte.modules.sockets.manager import RoomManager, PresenceTracker

__all__ = ["RoomManager", "PresenceTracker"]
