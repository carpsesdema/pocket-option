"""
Crossover detection module for ZigZag Detector
Handles geometric intersection detection between lines
"""
import cv2
import numpy as np
import logging
import time
from typing import List, Tuple, Optional, Dict
from dataclasses import dataclass
from .color_detector import DetectedLine


@dataclass
class Crossover:
    """Represents a detected crossover between two lines"""
    intersection_point: Tuple[int, int]
    line1_name: str
    line2_name: str
    line1_confidence: float
    line2_confidence: float
    timestamp: float
    confidence: float
    angle: float  # Intersection angle in degrees

    @property
    def combined_confidence(self) -> float:
        """Combined confidence from both lines and intersection quality"""
        return (self.line1_confidence + self.line2_confidence + self.confidence) / 3.0


class CrossoverDetector:
    """Detects crossovers between ZigZag lines"""

    def __init__(self, config_manager):
        self.config = config_manager
        self.crossover_history = []
        self.recent_crossovers = []
        self.last_detection_time = 0

    def line_segment_intersection(self, p1: Tuple[int, int], p2: Tuple[int, int],
                                  p3: Tuple[int, int], p4: Tuple[int, int]) -> Optional[Tuple[float, float]]:
        """Calculate intersection point of two line segments"""
        try:
            x1, y1 = p1
            x2, y2 = p2
            x3, y3 = p3
            x4, y4 = p4

            # Calculate direction vectors
            dx1, dy1 = x2 - x1, y2 - y1
            dx2, dy2 = x4 - x3, y4 - y3

            # Calculate denominator
            denominator = dx1 * dy2 - dy1 * dx2

            # Check if lines are parallel
            if abs(denominator) < 1e-10:
                return None

            # Calculate parameters
            dx3, dy3 = x1 - x3, y1 - y3
            t1 = (dx2 * dy3 - dy2 * dx3) / denominator
            t2 = (dx1 * dy3 - dy1 * dx3) / denominator

            # Check if intersection is within both line segments
            if 0 <= t1 <= 1 and 0 <= t2 <= 1:
                # Calculate intersection point
                intersection_x = x1 + t1 * dx1
                intersection_y = y1 + t1 * dy1
                return (intersection_x, intersection_y)

            return None

        except Exception as e:
            logging.error(f"Line intersection calculation failed: {e}")
            return None

    def calculate_intersection_angle(self, p1: Tuple[int, int], p2: Tuple[int, int],
                                     p3: Tuple[int, int], p4: Tuple[int, int]) -> float:
        """Calculate angle between two line segments at intersection"""
        try:
            # Direction vectors
            v1 = np.array([p2[0] - p1[0], p2[1] - p1[1]])
            v2 = np.array([p4[0] - p3[0], p4[1] - p3[1]])

            # Normalize vectors
            v1_norm = v1 / np.linalg.norm(v1)
            v2_norm = v2 / np.linalg.norm(v2)

            # Calculate angle
            dot_product = np.clip(np.dot(v1_norm, v2_norm), -1.0, 1.0)
            angle_rad = np.arccos(dot_product)
            angle_deg = np.degrees(angle_rad)

            # Return acute angle
            return min(angle_deg, 180 - angle_deg)

        except Exception as e:
            logging.error(f"Angle calculation failed: {e}")
            return 0.0

    def find_line_intersections(self, line1: DetectedLine, line2: DetectedLine) -> List[Dict]:
        """Find all intersections between two lines"""
        intersections = []

        try:
            # Check each segment of line1 against each segment of line2
            for i in range(len(line1.points) - 1):
                for j in range(len(line2.points) - 1):
                    p1, p2 = line1.points[i], line1.points[i + 1]
                    p3, p4 = line2.points[j], line2.points[j + 1]

                    intersection = self.line_segment_intersection(p1, p2, p3, p4)

                    if intersection:
                        # Calculate intersection angle
                        angle = self.calculate_intersection_angle(p1, p2, p3, p4)

                        # Calculate confidence based on angle and line quality
                        angle_factor = min(angle / 45.0, 1.0)  # Better if closer to 45°
                        if angle < 10:  # Very shallow angles are less reliable
                            angle_factor *= 0.5

                        confidence = (line1.confidence + line2.confidence + angle_factor) / 3.0

                        intersections.append({
                            'point': (int(intersection[0]), int(intersection[1])),
                            'angle': angle,
                            'confidence': confidence,
                            'line1_segment': (i, p1, p2),
                            'line2_segment': (j, p3, p4)
                        })

        except Exception as e:
            logging.error(f"Failed to find intersections: {e}")

        return intersections

    def detect_crossovers(self, detected_lines: List[DetectedLine]) -> List[Crossover]:
        """Detect crossovers between all line pairs"""
        crossovers = []
        current_time = time.time()

        try:
            min_confidence = self.config.get('detection', 'confidence_threshold', 0.7)
            tolerance = self.config.get('detection', 'intersection_tolerance', 8)

            # Find different line types for crossover detection
            line_pairs = []
            for i, line1 in enumerate(detected_lines):
                for j, line2 in enumerate(detected_lines[i + 1:], i + 1):
                    if line1.color_name != line2.color_name:
                        line_pairs.append((line1, line2))

            # Process each line pair
            for line1, line2 in line_pairs:
                intersections = self.find_line_intersections(line1, line2)

                for intersection_data in intersections:
                    if intersection_data['confidence'] >= min_confidence:
                        crossover = Crossover(
                            intersection_point=intersection_data['point'],
                            line1_name=line1.color_name,
                            line2_name=line2.color_name,
                            line1_confidence=line1.confidence,
                            line2_confidence=line2.confidence,
                            timestamp=current_time,
                            confidence=intersection_data['confidence'],
                            angle=intersection_data['angle']
                        )

                        # Check if this is a new crossover
                        if self.is_new_crossover(crossover, tolerance):
                            crossovers.append(crossover)
                            self.crossover_history.append(crossover)

                            logging.info(f"Crossover detected: {line1.color_name} × {line2.color_name} "
                                         f"at {crossover.intersection_point}, "
                                         f"confidence: {crossover.combined_confidence:.2f}, "
                                         f"angle: {crossover.angle:.1f}°")

        except Exception as e:
            logging.error(f"Crossover detection failed: {e}")

        # Clean up old crossovers
        self.cleanup_old_crossovers()
        self.last_detection_time = current_time

        return crossovers

    def is_new_crossover(self, crossover: Crossover, tolerance: int) -> bool:
        """Check if crossover is new (not detected recently)"""
        try:
            current_time = crossover.timestamp
            debounce_time = self.config.get('detection', 'debounce_seconds', 60)

            for recent in self.recent_crossovers:
                # Check spatial distance
                distance = np.sqrt(
                    (crossover.intersection_point[0] - recent.intersection_point[0]) ** 2 +
                    (crossover.intersection_point[1] - recent.intersection_point[1]) ** 2
                )

                # Check temporal distance
                time_diff = current_time - recent.timestamp

                # Check if same line types are involved
                same_lines = ((crossover.line1_name == recent.line1_name and
                               crossover.line2_name == recent.line2_name) or
                              (crossover.line1_name == recent.line2_name and
                               crossover.line2_name == recent.line1_name))

                # Consider it duplicate if within tolerance and debounce time
                if distance < tolerance and time_diff < debounce_time and same_lines:
                    logging.debug(f"Crossover filtered as duplicate: distance={distance:.1f}, "
                                  f"time_diff={time_diff:.1f}s")
                    return False

            # Add to recent crossovers
            self.recent_crossovers.append(crossover)
            return True

        except Exception as e:
            logging.error(f"Failed to check crossover uniqueness: {e}")
            return True  # Default to allowing crossover

    def cleanup_old_crossovers(self):
        """Remove old crossovers from recent list"""
        try:
            current_time = time.time()
            retention_time = 3600  # Keep for 1 hour

            # Remove old crossovers from recent list
            self.recent_crossovers = [
                crossover for crossover in self.recent_crossovers
                if current_time - crossover.timestamp < retention_time
            ]

            # Limit history size
            max_history = 1000
            if len(self.crossover_history) > max_history:
                self.crossover_history = self.crossover_history[-max_history:]

        except Exception as e:
            logging.error(f"Failed to cleanup crossovers: {e}")

    def get_statistics(self) -> Dict:
        """Get detection statistics"""
        try:
            current_time = time.time()

            # Count crossovers in different time periods
            last_hour = sum(1 for c in self.crossover_history
                            if current_time - c.timestamp < 3600)
            last_day = sum(1 for c in self.crossover_history
                           if current_time - c.timestamp < 86400)

            # Average confidence
            if self.crossover_history:
                avg_confidence = np.mean([c.combined_confidence for c in self.crossover_history])
                avg_angle = np.mean([c.angle for c in self.crossover_history])
            else:
                avg_confidence = 0.0
                avg_angle = 0.0

            return {
                'total_crossovers': len(self.crossover_history),
                'recent_crossovers': len(self.recent_crossovers),
                'last_hour': last_hour,
                'last_day': last_day,
                'avg_confidence': avg_confidence,
                'avg_angle': avg_angle,
                'last_detection': self.last_detection_time
            }

        except Exception as e:
            logging.error(f"Failed to get statistics: {e}")
            return {}

    def validate_crossover(self, crossover: Crossover, image: np.ndarray = None) -> bool:
        """Additional validation for crossover quality"""
        try:
            # Basic confidence check
            if crossover.combined_confidence < self.config.get('detection', 'confidence_threshold', 0.7):
                return False

            # Angle check - avoid very shallow intersections
            if crossover.angle < 10:  # Less than 10 degrees
                logging.debug(f"Crossover rejected: angle too shallow ({crossover.angle:.1f}°)")
                return False

            # Confidence balance check - both lines should have reasonable confidence
            min_line_confidence = 0.5
            if (crossover.line1_confidence < min_line_confidence or
                    crossover.line2_confidence < min_line_confidence):
                logging.debug(f"Crossover rejected: low line confidence "
                              f"({crossover.line1_confidence:.2f}, {crossover.line2_confidence:.2f})")
                return False

            return True

        except Exception as e:
            logging.error(f"Crossover validation failed: {e}")
            return False


class CrossoverVisualizer:
    """Visualizes crossovers on images"""

    @staticmethod
    def draw_crossovers(image: np.ndarray, crossovers: List[Crossover],
                        recent_only: bool = True) -> np.ndarray:
        """Draw crossovers on image"""
        try:
            vis_image = image.copy()
            current_time = time.time()

            for crossover in crossovers:
                # Skip old crossovers if recent_only is True
                if recent_only and current_time - crossover.timestamp > 300:  # 5 minutes
                    continue

                x, y = crossover.intersection_point

                # Color based on confidence
                if crossover.combined_confidence > 0.8:
                    color = (0, 255, 0)  # Green for high confidence
                elif crossover.combined_confidence > 0.6:
                    color = (0, 255, 255)  # Yellow for medium confidence
                else:
                    color = (0, 0, 255)  # Red for low confidence

                # Draw crossover marker
                cv2.circle(vis_image, (x, y), 8, color, 2)
                cv2.circle(vis_image, (x, y), 3, (255, 255, 255), -1)

                # Draw confidence and angle text
                text = f"{crossover.combined_confidence:.2f} ({crossover.angle:.0f}°)"
                text_size = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 0.4, 1)[0]
                text_x = max(0, min(x - text_size[0] // 2, vis_image.shape[1] - text_size[0]))
                text_y = max(text_size[1], y - 15)

                # Text background
                cv2.rectangle(vis_image, (text_x - 2, text_y - text_size[1] - 2),
                              (text_x + text_size[0] + 2, text_y + 2), (0, 0, 0), -1)

                cv2.putText(vis_image, text, (text_x, text_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.4, color, 1)

                # Age indicator
                age_minutes = (current_time - crossover.timestamp) / 60
                if age_minutes < 1:
                    age_text = "NEW"
                    age_color = (0, 255, 0)
                else:
                    age_text = f"{age_minutes:.0f}m"
                    age_color = (128, 128, 128)

                cv2.putText(vis_image, age_text, (x + 15, y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, age_color, 1)

            return vis_image

        except Exception as e:
            logging.error(f"Crossover visualization failed: {e}")
            return image