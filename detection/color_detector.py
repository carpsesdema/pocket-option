"""
Color detection module for ZigZag Detector
Handles color-based line extraction from captured images
"""

import cv2
import numpy as np
import logging
from typing import List, Tuple, Dict, Optional
from dataclasses import dataclass
import time


@dataclass
class DetectedLine:
    """Represents a detected ZigZag line"""
    points: List[Tuple[int, int]]
    color_name: str
    confidence: float
    timestamp: float
    length: float

    def __post_init__(self):
        """Calculate line length after initialization"""
        if len(self.points) > 1:
            total_length = 0
            for i in range(len(self.points) - 1):
                p1, p2 = self.points[i], self.points[i + 1]
                total_length += np.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)
            self.length = total_length
        else:
            self.length = 0


class ColorDetector:
    """Detects and extracts colored lines from images"""

    def __init__(self, config_manager):
        self.config = config_manager
        self.debug_mode = False
        self.last_detection_time = 0

    def set_debug_mode(self, enabled: bool):
        """Enable/disable debug mode for visualization"""
        self.debug_mode = enabled

    def create_color_mask(self, image: np.ndarray, color_config: Dict) -> np.ndarray:
        """Create binary mask for specific color range"""
        try:
            # Convert to HSV
            hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

            # Extract color range
            lower = np.array([
                color_config['hue_min'],
                color_config['sat_min'],
                color_config['val_min']
            ])
            upper = np.array([
                color_config['hue_max'],
                color_config['sat_max'],
                color_config['val_max']
            ])

            # Create mask
            mask = cv2.inRange(hsv, lower, upper)

            # Apply morphological operations to clean up the mask
            kernel = np.ones((3, 3), np.uint8)
            mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
            mask = cv2.morphologyEx(mask, cv2.MORPH_CLOSE, kernel)

            return mask

        except Exception as e:
            logging.error(f"Failed to create color mask: {e}")
            return np.zeros(image.shape[:2], dtype=np.uint8)

    def extract_line_points(self, mask: np.ndarray, min_length: int = 30) -> List[Tuple[int, int]]:
        """Extract ordered points from line mask"""
        try:
            # Find contours
            contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

            if not contours:
                return []

            # Get the longest contour (main line)
            longest_contour = max(contours, key=cv2.contourArea)

            # Check minimum area/length
            if cv2.contourArea(longest_contour) < min_length:
                return []

            # Simplify contour to reduce noise
            epsilon = 0.01 * cv2.arcLength(longest_contour, False)
            simplified = cv2.approxPolyDP(longest_contour, epsilon, False)

            # Extract points and sort by x-coordinate
            points = [tuple(point[0]) for point in simplified]
            points = sorted(points, key=lambda p: p[0])

            # Remove duplicate points
            unique_points = []
            for point in points:
                if not unique_points or np.sqrt((point[0] - unique_points[-1][0]) ** 2 +
                                                (point[1] - unique_points[-1][1]) ** 2) > 5:
                    unique_points.append(point)

            return unique_points

        except Exception as e:
            logging.error(f"Failed to extract line points: {e}")
            return []

    def calculate_line_confidence(self, points: List[Tuple[int, int]], mask: np.ndarray) -> float:
        """Calculate confidence score for detected line"""
        try:
            if len(points) < 2:
                return 0.0

            # Base confidence on number of points and line length
            num_points = len(points)

            # Calculate total line length
            total_length = 0
            for i in range(len(points) - 1):
                p1, p2 = points[i], points[i + 1]
                total_length += np.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2)

            # Confidence factors
            length_factor = min(total_length / 200.0, 1.0)  # Normalize to 200 pixels
            points_factor = min(num_points / 20.0, 1.0)  # Normalize to 20 points

            # Check mask density along the line
            mask_hits = 0
            total_checks = 0

            for i in range(len(points) - 1):
                p1, p2 = points[i], points[i + 1]
                # Sample points along the line segment
                steps = max(int(np.sqrt((p2[0] - p1[0]) ** 2 + (p2[1] - p1[1]) ** 2) / 5), 1)
                for j in range(steps):
                    t = j / steps
                    x = int(p1[0] + t * (p2[0] - p1[0]))
                    y = int(p1[1] + t * (p2[1] - p1[1]))

                    if 0 <= y < mask.shape[0] and 0 <= x < mask.shape[1]:
                        total_checks += 1
                        if mask[y, x] > 0:
                            mask_hits += 1

            mask_factor = mask_hits / max(total_checks, 1)

            # Combined confidence
            confidence = (length_factor + points_factor + mask_factor) / 3.0

            return min(max(confidence, 0.0), 1.0)

        except Exception as e:
            logging.error(f"Failed to calculate confidence: {e}")
            return 0.0

    def detect_lines(self, image: np.ndarray) -> List[DetectedLine]:
        """Detect all configured ZigZag lines in image"""
        detected_lines = []
        current_time = time.time()

        try:
            min_length = self.config.get('detection', 'min_line_length', 30)

            # Process each configured color
            for line_name, color_config in self.config.config['colors'].items():
                if not color_config.get('enabled', True):
                    continue

                # Create color mask
                mask = self.create_color_mask(image, color_config)

                # Extract line points
                points = self.extract_line_points(mask, min_length)

                if points:
                    # Calculate confidence
                    confidence = self.calculate_line_confidence(points, mask)

                    # Create detected line object
                    line = DetectedLine(
                        points=points,
                        color_name=line_name,
                        confidence=confidence,
                        timestamp=current_time
                    )

                    detected_lines.append(line)

                    logging.debug(f"Detected {line_name}: {len(points)} points, "
                                  f"confidence: {confidence:.2f}, length: {line.length:.1f}")

        except Exception as e:
            logging.error(f"Line detection failed: {e}")

        self.last_detection_time = current_time
        return detected_lines

    def visualize_detection(self, image: np.ndarray, lines: List[DetectedLine]) -> np.ndarray:
        """Create visualization of detected lines"""
        try:
            vis_image = image.copy()

            # Color mapping for visualization
            color_map = {
                'zigzag_line1': (0, 255, 255),  # Yellow
                'zigzag_line2': (255, 0, 255),  # Magenta
            }

            for line in lines:
                color = color_map.get(line.color_name, (255, 255, 255))

                # Draw line segments
                for i in range(len(line.points) - 1):
                    cv2.line(vis_image, line.points[i], line.points[i + 1], color, 3)

                # Draw points
                for point in line.points:
                    cv2.circle(vis_image, point, 4, color, -1)

                # Add confidence text
                if line.points:
                    text_pos = (line.points[0][0], line.points[0][1] - 10)
                    cv2.putText(vis_image, f"{line.color_name}: {line.confidence:.2f}",
                                text_pos, cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)

            return vis_image

        except Exception as e:
            logging.error(f"Visualization failed: {e}")
            return image


class ColorCalibrator:
    """Helper class for calibrating color detection"""

    def __init__(self):
        self.calibration_points = []
        self.current_image = None

    def start_calibration(self, image: np.ndarray, color_name: str):
        """Start interactive color calibration"""
        self.current_image = image.copy()
        self.calibration_points = []

        # Convert to HSV for analysis
        hsv_image = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

        def mouse_callback(event, x, y, flags, param):
            if event == cv2.EVENT_LBUTTONDOWN:
                if 0 <= y < hsv_image.shape[0] and 0 <= x < hsv_image.shape[1]:
                    hsv_value = hsv_image[y, x]
                    self.calibration_points.append((x, y, hsv_value))

                    # Draw point on image
                    cv2.circle(self.current_image, (x, y), 5, (0, 255, 0), -1)
                    cv2.putText(self.current_image, f"H:{hsv_value[0]} S:{hsv_value[1]} V:{hsv_value[2]}",
                                (x + 10, y), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 255, 0), 1)

        cv2.namedWindow(f'Calibrate {color_name}', cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(f'Calibrate {color_name}', mouse_callback)

        instructions = [
            "Click on the line color you want to detect",
            "Press ENTER when done, ESC to cancel"
        ]

        while True:
            display_image = self.current_image.copy()

            # Add instructions
            for i, instruction in enumerate(instructions):
                cv2.putText(display_image, instruction, (10, 30 + i * 25),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

            cv2.imshow(f'Calibrate {color_name}', display_image)

            key = cv2.waitKey(1) & 0xFF
            if key == 13:  # Enter
                break
            elif key == 27:  # Escape
                cv2.destroyAllWindows()
                return None

        cv2.destroyAllWindows()

        # Calculate color range from calibration points
        if self.calibration_points:
            return self.calculate_color_range()

        return None

    def calculate_color_range(self) -> Optional[Dict]:
        """Calculate optimal color range from calibration points"""
        if not self.calibration_points:
            return None

        try:
            # Extract HSV values
            hsv_values = np.array([point[2] for point in self.calibration_points])

            # Calculate statistics
            mean_hsv = np.mean(hsv_values, axis=0)
            std_hsv = np.std(hsv_values, axis=0)

            # Calculate range with some tolerance
            tolerance_factor = 2.0  # Adjust as needed

            hue_min = max(0, int(mean_hsv[0] - tolerance_factor * std_hsv[0]))
            hue_max = min(179, int(mean_hsv[0] + tolerance_factor * std_hsv[0]))

            sat_min = max(0, int(mean_hsv[1] - tolerance_factor * std_hsv[1]))
            sat_max = min(255, int(mean_hsv[1] + tolerance_factor * std_hsv[1]))

            val_min = max(0, int(mean_hsv[2] - tolerance_factor * std_hsv[2]))
            val_max = min(255, int(mean_hsv[2] + tolerance_factor * std_hsv[2]))

            # Ensure minimum ranges
            if hue_max - hue_min < 10:
                hue_min = max(0, hue_min - 5)
                hue_max = min(179, hue_max + 5)

            if sat_max - sat_min < 50:
                sat_min = max(0, sat_min - 25)
                sat_max = min(255, sat_max + 25)

            if val_max - val_min < 50:
                val_min = max(0, val_min - 25)
                val_max = min(255, val_max + 25)

            color_range = {
                'hue_min': hue_min,
                'hue_max': hue_max,
                'sat_min': sat_min,
                'sat_max': sat_max,
                'val_min': val_min,
                'val_max': val_max
            }

            logging.info(f"Calculated color range: {color_range}")
            return color_range

        except Exception as e:
            logging.error(f"Failed to calculate color range: {e}")
            return None