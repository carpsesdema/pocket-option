#!/usr/bin/env python3
"""
ZigZag Crossover Detector - Main Application
Entry point for the ZigZag detection system
"""

import sys
import os
import logging
from pathlib import Path

# Add src directory to path
sys.path.append(os.path.join(os.path.dirname(__file__), 'src'))

from gui.main_window import ZigZagDetectorApp
from config.settings import setup_logging


def main():
    """Main application entry point"""
    try:
        # Setup logging
        setup_logging()

        # Create and run application
        app = ZigZagDetectorApp()
        app.run()

    except Exception as e:
        logging.error(f"Application startup failed: {e}")
        print(f"Error: {e}")
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()