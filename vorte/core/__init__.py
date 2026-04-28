"""Vorte core package."""
from vorte.core.app import Vorte
from vorte.core.config import Settings, settings
from vorte.core.module import Module, ModuleRegistry, ModuleMeta, ModulePriority
from vorte.core.response import VorteResponse, VorteJSONResponse, success_response, error_response
from vorte.core.router import VorteAPIRouter, router, VersioningMiddleware
from vorte.core.di import Container, Depends, inject

__all__ = [
    "Vorte",
    "Settings",
    "settings",
    "Module",
    "ModuleRegistry",
    "ModuleMeta",
    "ModulePriority",
    "VorteResponse",
    "VorteJSONResponse",
    "success_response",
    "error_response",
    "VorteAPIRouter",
    "router",
    "VersioningMiddleware",
    "Container",
    "Depends",
    "inject",
]
