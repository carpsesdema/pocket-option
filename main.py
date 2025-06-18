#!/usr/bin/env python3
"""
ZigZag Crossover Detector - PySide6 Version
Entry point for the ZigZag detection system
"""

import sys
import os
import logging
from pathlib import Path

from gui.main_window import ZigZagDetectorApp, create_app
from config.settings import setup_logging


def main():
    """Main application entry point"""
    try:
        # Setup logging
        setup_logging()

        # Create QApplication
        app = create_app()

        # Create and run application
        main_window = ZigZagDetectorApp()
        main_window.run()

        # Start event loop
        sys.exit(app.exec())

    except ImportError as e:
        logging.error(f"Application startup failed: {e}")
        print(f"Error: {e}")
        print("Make sure PySide6 is installed: pip install PySide6")
        input("Press Enter to exit...")
    except Exception as e:
        logging.error(f"Application startup failed: {e}")
        print(f"Error: {e}")
        input("Press Enter to exit...")


if __name__ == "__main__":
    main()