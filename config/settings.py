"""
Configuration management for ZigZag Detector
Handles all settings, defaults, and persistence
"""

import json
import os
import logging
from pathlib import Path
from typing import Dict, Any

# Default configuration
DEFAULT_CONFIG = {
    'window': {
        'auto_detect': True,
        'region': {'top': 100, 'left': 100, 'width': 1200, 'height': 800},
        'keywords': ['pocketoption', 'chrome', 'firefox', 'edge']
    },

    'capture': {
        'fps': 2,
        'image_scale': 1.0,
        'save_screenshots': False
    },

    'colors': {
        'zigzag_line1': {
            'name': 'Yellow/Green Line',
            'hue_min': 20, 'hue_max': 35,
            'sat_min': 100, 'sat_max': 255,
            'val_min': 100, 'val_max': 255,
            'enabled': True
        },
        'zigzag_line2': {
            'name': 'Purple Line',
            'hue_min': 120, 'hue_max': 150,
            'sat_min': 100, 'sat_max': 255,
            'val_min': 100, 'val_max': 255,
            'enabled': True
        }
    },

    'detection': {
        'min_line_length': 30,
        'confidence_threshold': 0.7,
        'intersection_tolerance': 8,
        'temporal_validation_frames': 2,
        'debounce_seconds': 60
    },

    'alerts': {
        'telegram_enabled': True,
        'telegram_token': '',
        'telegram_chat_id': '',
        'cooldown_seconds': 300,
        'sound_enabled': True,
        'popup_enabled': False,
        'log_file_enabled': True
    },

    'gui': {
        'theme': 'default',
        'always_on_top': False,
        'minimize_to_tray': True,
        'auto_start_detection': False
    }
}


class ConfigManager:
    """Manages application configuration"""

    def __init__(self, config_file='config.json'):
        self.config_file = Path(config_file)
        self.config = DEFAULT_CONFIG.copy()
        self.load_config()

    def load_config(self):
        """Load configuration from file"""
        try:
            if self.config_file.exists():
                with open(self.config_file, 'r') as f:
                    saved_config = json.load(f)
                    self._merge_config(saved_config)
                logging.info(f"Configuration loaded from {self.config_file}")
            else:
                logging.info("Using default configuration")
        except Exception as e:
            logging.error(f"Failed to load config: {e}")
            logging.info("Using default configuration")

    def save_config(self):
        """Save configuration to file"""
        try:
            # Create directory if it doesn't exist
            self.config_file.parent.mkdir(parents=True, exist_ok=True)

            with open(self.config_file, 'w') as f:
                json.dump(self.config, f, indent=2)
            logging.info(f"Configuration saved to {self.config_file}")
            return True
        except Exception as e:
            logging.error(f"Failed to save config: {e}")
            return False

    def _merge_config(self, saved_config):
        """Merge saved config with defaults, preserving structure"""

        def merge_dict(default, saved):
            for key, value in saved.items():
                if key in default:
                    if isinstance(default[key], dict) and isinstance(value, dict):
                        merge_dict(default[key], value)
                    else:
                        default[key] = value

        merge_dict(self.config, saved_config)

    def get(self, section, key=None, default=None):
        """Get configuration value"""
        try:
            if key is None:
                return self.config.get(section, default)
            return self.config.get(section, {}).get(key, default)
        except:
            return default

    def set(self, section, key, value):
        """Set configuration value"""
        if section not in self.config:
            self.config[section] = {}
        self.config[section][key] = value

    def get_color_config(self, line_name):
        """Get color configuration for a specific line"""
        return self.config['colors'].get(line_name, {})

    def set_color_config(self, line_name, color_config):
        """Set color configuration for a specific line"""
        if 'colors' not in self.config:
            self.config['colors'] = {}
        self.config['colors'][line_name] = color_config

    def reset_to_defaults(self):
        """Reset configuration to defaults"""
        self.config = DEFAULT_CONFIG.copy()
        logging.info("Configuration reset to defaults")

    def validate_config(self):
        """Validate configuration values"""
        errors = []

        # Validate color ranges
        for line_name, color_config in self.config['colors'].items():
            if color_config.get('enabled', False):
                for param in ['hue_min', 'hue_max', 'sat_min', 'sat_max', 'val_min', 'val_max']:
                    value = color_config.get(param)
                    if value is None or not (0 <= value <= 255):
                        errors.append(f"Invalid {param} for {line_name}: {value}")

        # Validate numeric ranges
        fps = self.config['capture'].get('fps', 1)
        if not (0.1 <= fps <= 10):
            errors.append(f"Invalid FPS: {fps}")

        confidence = self.config['detection'].get('confidence_threshold', 0.7)
        if not (0.0 <= confidence <= 1.0):
            errors.append(f"Invalid confidence threshold: {confidence}")

        return errors


def setup_logging():
    """Setup logging configuration"""
    # Create logs directory
    log_dir = Path('logs')
    log_dir.mkdir(exist_ok=True)

    # Configure logging
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_dir / 'zigzag_detector.log'),
            logging.StreamHandler()
        ]
    )

    # Reduce noise from some libraries
    logging.getLogger('PIL').setLevel(logging.WARNING)
    logging.getLogger('urllib3').setLevel(logging.WARNING)


# Global config instance
config = ConfigManager()