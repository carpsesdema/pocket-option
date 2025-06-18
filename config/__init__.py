"""
Configuration management package
Handles all application settings and persistence
"""

from .settings import config, ConfigManager, setup_logging

__all__ = ['config', 'ConfigManager', 'setup_logging']