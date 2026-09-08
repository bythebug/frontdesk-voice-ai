"""Importing this package registers all tools on app.agent.tool_registry.registry."""

from app.tools import appointments, customers, knowledge, notifications

__all__ = ["appointments", "customers", "knowledge", "notifications"]
