# src/capture/__init__.py
"""
Screen capture and window detection package
Handles window finding and screen capture operations
"""

from .window_capture import WindowCapture, RegionSelector, WindowInfo

__all__ = ['WindowCapture', 'RegionSelector', 'WindowInfo']

