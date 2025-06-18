"""
ZigZag Crossover Detector
A professional trading tool for detecting ZigZag indicator crossovers

Author: Trading Tools Developer
Version: 1.0.0
"""

__version__ = "1.0.0"
__author__ = "Trading Tools Developer"
__description__ = "Professional ZigZag crossover detection system for PocketOption"

# Import main components for easy access
from .config.settings import config
from .gui.main_window import ZigZagDetectorApp

__all__ = ['config', 'ZigZagDetectorApp']