"""
Detection algorithms package
Contains color detection and crossover detection logic
"""

from .color_detector import ColorDetector, ColorCalibrator, DetectedLine
from .crossover_detector import CrossoverDetector, Crossover, CrossoverVisualizer

__all__ = [
    'ColorDetector', 'ColorCalibrator', 'DetectedLine',
    'CrossoverDetector', 'Crossover', 'CrossoverVisualizer'
]
