# src/alerts/__init__.py
"""
Alert system package
Handles Telegram alerts and other notification methods
"""

from .telegram_alerter import TelegramAlerter, AlertManager

__all__ = ['TelegramAlerter', 'AlertManager']