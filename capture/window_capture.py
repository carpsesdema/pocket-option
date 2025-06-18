"""
Window capture module for ZigZag Detector
Handles window detection and screen capture
"""

import cv2
import numpy as np
import mss
import win32gui
import win32con
import logging
from typing import Optional, Dict, List, Tuple
from dataclasses import dataclass


@dataclass
class WindowInfo:
    """Information about a detected window"""
    hwnd: int
    title: str
    rect: Tuple[int, int, int, int]  # left, top, right, bottom

    @property
    def region(self) -> Dict[str, int]:
        """Get region dict for mss"""
        return {
            'left': self.rect[0],
            'top': self.rect[1],
            'width': self.rect[2] - self.rect[0],
            'height': self.rect[3] - self.rect[1]
        }


class WindowCapture:
    """Handles window detection and screen capture"""

    def __init__(self):
        self.sct = mss.mss()
        self.target_window = None
        self.custom_region = None

    def find_windows(self, keywords: List[str] = None) -> List[WindowInfo]:
        """Find all windows matching keywords"""
        if keywords is None:
            keywords = ['pocketoption', 'chrome', 'firefox', 'edge']

        windows = []

        def enum_callback(hwnd, windows_list):
            if win32gui.IsWindowVisible(hwnd):
                try:
                    title = win32gui.GetWindowText(hwnd)
                    if title and any(keyword.lower() in title.lower() for keyword in keywords):
                        rect = win32gui.GetWindowRect(hwnd)
                        # Filter out tiny windows
                        if rect[2] - rect[0] > 200 and rect[3] - rect[1] > 200:
                            windows_list.append(WindowInfo(hwnd, title, rect))
                except:
                    pass  # Skip windows that cause errors

        win32gui.EnumWindows(enum_callback, windows)

        # Sort by area (largest first) and prefer PocketOption
        def sort_key(window):
            area = (window.rect[2] - window.rect[0]) * (window.rect[3] - window.rect[1])
            po_bonus = 1000000 if 'pocketoption' in window.title.lower() else 0
            return area + po_bonus

        windows.sort(key=sort_key, reverse=True)
        return windows

    def auto_detect_window(self) -> Optional[WindowInfo]:
        """Automatically detect PocketOption window"""
        windows = self.find_windows()

        if windows:
            self.target_window = windows[0]
            logging.info(f"Auto-detected window: {self.target_window.title}")
            return self.target_window

        logging.warning("No suitable windows found for auto-detection")
        return None

    def set_target_window(self, window_info: WindowInfo):
        """Set target window for capture"""
        self.target_window = window_info
        self.custom_region = None  # Clear custom region
        logging.info(f"Target window set: {window_info.title}")

    def set_custom_region(self, region: Dict[str, int]):
        """Set custom capture region"""
        self.custom_region = region
        self.target_window = None  # Clear window selection
        logging.info(f"Custom region set: {region}")

    def capture_screen(self) -> Optional[np.ndarray]:
        """Capture screen region"""
        try:
            # Determine region to capture
            if self.custom_region:
                region = self.custom_region
            elif self.target_window:
                # Update window position in case it moved
                try:
                    rect = win32gui.GetWindowRect(self.target_window.hwnd)
                    region = {
                        'left': rect[0],
                        'top': rect[1],
                        'width': rect[2] - rect[0],
                        'height': rect[3] - rect[1]
                    }
                except:
                    logging.error("Target window no longer exists")
                    return None
            else:
                logging.error("No capture region defined")
                return None

            # Validate region
            if region['width'] <= 0 or region['height'] <= 0:
                logging.error(f"Invalid capture region: {region}")
                return None

            # Capture screenshot
            screenshot = self.sct.grab(region)
            img = np.array(screenshot)

            # Convert BGRA to BGR
            if img.shape[2] == 4:
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            return img

        except Exception as e:
            logging.error(f"Screen capture failed: {e}")
            return None

    def get_capture_info(self) -> Dict:
        """Get information about current capture setup"""
        info = {
            'mode': 'none',
            'region': None,
            'window_title': None,
            'valid': False
        }

        if self.custom_region:
            info['mode'] = 'custom'
            info['region'] = self.custom_region
            info['valid'] = True
        elif self.target_window:
            try:
                # Check if window still exists
                rect = win32gui.GetWindowRect(self.target_window.hwnd)
                info['mode'] = 'window'
                info['region'] = {
                    'left': rect[0], 'top': rect[1],
                    'width': rect[2] - rect[0], 'height': rect[3] - rect[1]
                }
                info['window_title'] = self.target_window.title
                info['valid'] = True
            except:
                info['valid'] = False

        return info

    def test_capture(self) -> Tuple[bool, str]:
        """Test if capture is working"""
        try:
            img = self.capture_screen()
            if img is None:
                return False, "Failed to capture screen"

            if img.size == 0:
                return False, "Captured empty image"

            height, width = img.shape[:2]
            if width < 100 or height < 100:
                return False, f"Captured image too small: {width}x{height}"

            return True, f"Capture successful: {width}x{height}"

        except Exception as e:
            return False, f"Capture test failed: {e}"


class RegionSelector:
    """Interactive region selection tool"""

    def __init__(self):
        self.selecting = False
        self.start_point = None
        self.end_point = None
        self.selected_region = None

    def select_region(self) -> Optional[Dict[str, int]]:
        """Interactive region selection using full screen"""
        try:
            # Capture full screen
            with mss.mss() as sct:
                monitor = sct.monitors[0]  # All monitors
                screenshot = sct.grab(monitor)
                img = np.array(screenshot)
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2BGR)

            # Create window for selection
            cv2.namedWindow('Select Region', cv2.WINDOW_NORMAL)
            cv2.setWindowProperty('Select Region', cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

            # Mouse callback
            def mouse_callback(event, x, y, flags, param):
                if event == cv2.EVENT_LBUTTONDOWN:
                    self.selecting = True
                    self.start_point = (x, y)
                elif event == cv2.EVENT_MOUSEMOVE and self.selecting:
                    self.end_point = (x, y)
                elif event == cv2.EVENT_LBUTTONUP:
                    self.selecting = False
                    self.end_point = (x, y)

            cv2.setMouseCallback('Select Region', mouse_callback)

            display_img = img.copy()

            while True:
                # Draw selection rectangle
                if self.start_point and self.end_point:
                    cv2.rectangle(display_img, self.start_point, self.end_point, (0, 255, 0), 2)

                    # Show coordinates
                    text = f"Start: {self.start_point}, End: {self.end_point}"
                    cv2.putText(display_img, text, (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

                # Instructions
                cv2.putText(display_img, "Drag to select region, Press ENTER to confirm, ESC to cancel",
                            (10, img.shape[0] - 20), cv2.FONT_HERSHEY_SIMPLEX, 1, (255, 255, 255), 2)

                cv2.imshow('Select Region', display_img)

                key = cv2.waitKey(1) & 0xFF
                if key == 13:  # Enter
                    break
                elif key == 27:  # Escape
                    cv2.destroyAllWindows()
                    return None

                # Reset display image
                display_img = img.copy()

            cv2.destroyAllWindows()

            # Calculate selected region
            if self.start_point and self.end_point:
                x1, y1 = self.start_point
                x2, y2 = self.end_point

                # Ensure proper order
                left = min(x1, x2)
                top = min(y1, y2)
                right = max(x1, x2)
                bottom = max(y1, y2)

                region = {
                    'left': left,
                    'top': top,
                    'width': right - left,
                    'height': bottom - top
                }

                return region

            return None

        except Exception as e:
            logging.error(f"Region selection failed: {e}")
            return None