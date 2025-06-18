"""
Simplified PySide6 GUI for ZigZag Detector
Thread-safe screen capture with user-friendly interface
"""

import sys
import time
import logging
from datetime import datetime
from pathlib import Path
import cv2
import numpy as np

from PySide6.QtWidgets import *
from PySide6.QtCore import *
from PySide6.QtGui import *

from config.settings import config
from capture.window_capture import WindowCapture, RegionSelector
from detection.color_detector import ColorDetector, ColorCalibrator
from detection.crossover_detector import CrossoverDetector, CrossoverVisualizer
from alerts.telegram_alerter import AlertManager


class SimpleRegionSelector(QDialog):
    """Super simple click-drag region selector"""

    def __init__(self):
        super().__init__()
        self.selected_region = None
        self.start_point = None
        self.end_point = None
        self.dragging = False

    def select_region(self):
        """Show fullscreen selector and return selected region"""
        try:
            # Take screenshot of entire screen
            import mss
            with mss.mss() as sct:
                # Get primary monitor
                monitor = sct.monitors[1]  # Monitor 1 is usually primary
                screenshot = sct.grab(monitor)

                # Convert to QPixmap
                img_array = np.array(screenshot)
                img_array = cv2.cvtColor(img_array, cv2.COLOR_BGRA2RGB)
                h, w, ch = img_array.shape
                bytes_per_line = ch * w

                qt_image = QImage(img_array.data, w, h, bytes_per_line, QImage.Format_RGB888)
                self.screenshot_pixmap = QPixmap.fromImage(qt_image)

                # Setup fullscreen dialog
                self.setup_selector_ui()

                # Show dialog
                if self.exec() == QDialog.Accepted and self.selected_region:
                    return self.selected_region

        except Exception as e:
            QMessageBox.critical(None, "Screenshot Error",
                                 f"Could not take screenshot: {e}\n\n"
                                 "Try using the Window Settings tab instead.")

        return None

    def setup_selector_ui(self):
        """Setup the selector UI"""
        # Make dialog fullscreen
        self.setWindowState(Qt.WindowFullScreen)
        self.setWindowFlags(Qt.Window | Qt.FramelessWindowHint | Qt.WindowStaysOnTopHint)

        # Create layout
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)

        # Create label to show screenshot
        self.image_label = QLabel()
        self.image_label.setPixmap(self.screenshot_pixmap)
        self.image_label.setAlignment(Qt.AlignCenter)
        self.image_label.mousePressEvent = self.mouse_press
        self.image_label.mouseMoveEvent = self.mouse_move
        self.image_label.mouseReleaseEvent = self.mouse_release

        layout.addWidget(self.image_label)

        # Instructions overlay
        self.instructions = QLabel("""
        📊 SELECT YOUR CHART AREA

        🖱️ Click and drag to select the area where your chart is displayed
        ✅ Press ENTER when you're happy with the selection
        ❌ Press ESC to cancel
        """)

        self.instructions.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 0, 0, 180);
                color: white;
                font-size: 20px;
                font-weight: bold;
                padding: 30px;
                border-radius: 15px;
            }
        """)
        self.instructions.setAlignment(Qt.AlignCenter)
        self.instructions.setGeometry(50, 50, 400, 200)
        self.instructions.setParent(self.image_label)

        # Selection overlay
        self.selection_overlay = QLabel()
        self.selection_overlay.setStyleSheet("""
            QLabel {
                border: 3px solid #00ff00;
                background-color: rgba(0, 255, 0, 30);
            }
        """)
        self.selection_overlay.setParent(self.image_label)
        self.selection_overlay.hide()

    def keyPressEvent(self, event):
        """Handle key presses"""
        if event.key() == Qt.Key_Return or event.key() == Qt.Key_Enter:
            if self.selected_region:
                self.accept()
        elif event.key() == Qt.Key_Escape:
            self.reject()

    def mouse_press(self, event):
        """Start selection"""
        if event.button() == Qt.LeftButton:
            self.start_point = event.pos()
            self.dragging = True
            self.instructions.hide()

    def mouse_move(self, event):
        """Update selection rectangle"""
        if self.dragging and self.start_point:
            self.end_point = event.pos()
            self.update_selection()

    def mouse_release(self, event):
        """Finish selection"""
        if event.button() == Qt.LeftButton and self.dragging:
            self.end_point = event.pos()
            self.dragging = False
            self.finalize_selection()

    def update_selection(self):
        """Update the selection rectangle display"""
        if not self.start_point or not self.end_point:
            return

        # Calculate rectangle
        x1, y1 = self.start_point.x(), self.start_point.y()
        x2, y2 = self.end_point.x(), self.end_point.y()

        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        # Update overlay
        self.selection_overlay.setGeometry(left, top, width, height)
        self.selection_overlay.show()

    def finalize_selection(self):
        """Finalize the selection and calculate region"""
        if not self.start_point or not self.end_point:
            return

        # Calculate final rectangle
        x1, y1 = self.start_point.x(), self.start_point.y()
        x2, y2 = self.end_point.x(), self.end_point.y()

        left = min(x1, x2)
        top = min(y1, y2)
        width = abs(x2 - x1)
        height = abs(y2 - y1)

        # Minimum size check
        if width < 100 or height < 100:
            QMessageBox.warning(self, "Selection Too Small",
                                "Please select a larger area (at least 100x100 pixels)")
            return

        # Store the region
        self.selected_region = {
            'left': left,
            'top': top,
            'width': width,
            'height': height
        }

        # Show confirmation
        confirm_text = QLabel(f"""
        ✅ SELECTION COMPLETE

        📏 Size: {width} x {height} pixels
        📍 Position: ({left}, {top})

        Press ENTER to confirm, or drag again to reselect
        """)

        confirm_text.setStyleSheet("""
            QLabel {
                background-color: rgba(0, 120, 212, 200);
                color: white;
                font-size: 18px;
                font-weight: bold;
                padding: 20px;
                border-radius: 10px;
            }
        """)
        confirm_text.setAlignment(Qt.AlignCenter)
        confirm_text.setGeometry(left, top - 120, max(300, width), 100)
        confirm_text.setParent(self.image_label)
        confirm_text.show()


class DetectionWorker(QThread):
    """Worker thread for detection loop - THREAD-SAFE VERSION"""

    # Signals for thread-safe communication
    image_ready = Signal(np.ndarray)
    lines_detected = Signal(list)
    crossover_detected = Signal(object)
    error_occurred = Signal(str)
    status_update = Signal(str)
    capture_request = Signal()  # Signal to request capture from main thread

    def __init__(self, color_detector, crossover_detector, alert_manager):
        super().__init__()
        self.color_detector = color_detector
        self.crossover_detector = crossover_detector
        self.alert_manager = alert_manager

        self.running = False
        self.paused = False
        self.current_image = None
        self.image_lock = QMutex()

    def set_image(self, image):
        """Thread-safe way to set current image from main thread"""
        with QMutexLocker(self.image_lock):
            self.current_image = image.copy() if image is not None else None

    def run(self):
        """Main detection loop - runs in background thread"""
        self.running = True
        loop_count = 0

        while self.running:
            try:
                if self.paused:
                    self.msleep(100)
                    continue

                loop_count += 1

                # Request capture from main thread (thread-safe)
                self.capture_request.emit()

                # Wait a bit for image to be set
                self.msleep(100)

                # Get current image (thread-safe)
                image = None
                with QMutexLocker(self.image_lock):
                    if self.current_image is not None:
                        image = self.current_image.copy()

                if image is None:
                    self.status_update.emit(f"Waiting for image... (loop {loop_count})")
                    self.msleep(1000)
                    continue

                if image.size == 0:
                    self.error_occurred.emit("Empty image captured")
                    self.msleep(1000)
                    continue

                # Emit image for display
                self.image_ready.emit(image.copy())

                # Detect lines
                detected_lines = self.color_detector.detect_lines(image)
                self.lines_detected.emit(detected_lines)

                # Detect crossovers
                crossovers = self.crossover_detector.detect_crossovers(detected_lines)

                # Send alerts and emit signals for new crossovers
                for crossover in crossovers:
                    self.crossover_detected.emit(crossover)
                    try:
                        self.alert_manager.send_crossover_alert(crossover)
                    except Exception as e:
                        self.error_occurred.emit(f"Alert failed: {e}")

                self.status_update.emit(f"Scanning... Lines: {len(detected_lines)}, Crossovers: {len(crossovers)}")

                # Wait for next iteration
                fps = config.get('capture', 'fps', 2)
                sleep_ms = int(1000 / max(fps, 0.1))
                self.msleep(sleep_ms)

            except Exception as e:
                self.error_occurred.emit(f"Detection error: {e}")
                self.msleep(2000)

    def stop(self):
        """Stop the detection loop"""
        self.running = False
        self.wait(5000)  # Wait up to 5 seconds for thread to finish

    def pause(self):
        """Pause detection"""
        self.paused = True

    def resume(self):
        """Resume detection"""
        self.paused = False


class ImageDisplayWidget(QLabel):
    """Simplified image display widget"""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(800, 600)
        self.setAlignment(Qt.AlignCenter)
        self.setText("📸 Screen Preview\n\nWill show your chart when detection starts")
        self.setStyleSheet("""
            QLabel {
                border: 3px solid #0078d4;
                background-color: #1e1e1e;
                color: #ffffff;
                font-size: 18px;
                border-radius: 12px;
                padding: 20px;
            }
        """)

        self.current_pixmap = None

    def update_image(self, cv_image, detected_lines=None, crossovers=None):
        """Update the displayed image with detections"""
        try:
            # Create visualization
            vis_image = cv_image.copy()

            if detected_lines:
                vis_image = ColorDetector(config).visualize_detection(vis_image, detected_lines)

            if crossovers:
                vis_image = CrossoverVisualizer.draw_crossovers(vis_image, crossovers[-5:])

            # Convert BGR to RGB
            rgb_image = cv2.cvtColor(vis_image, cv2.COLOR_BGR2RGB)
            h, w, ch = rgb_image.shape
            bytes_per_line = ch * w

            # Create Qt image
            qt_image = QImage(rgb_image.data, w, h, bytes_per_line, QImage.Format_RGB888)

            # Scale to fit widget while maintaining aspect ratio
            pixmap = QPixmap.fromImage(qt_image)
            scaled_pixmap = pixmap.scaled(
                self.size(), Qt.KeepAspectRatio, Qt.SmoothTransformation
            )

            self.setPixmap(scaled_pixmap)
            self.current_pixmap = scaled_pixmap

        except Exception as e:
            logging.error(f"Image display error: {e}")
            self.setText(f"❌ Display error\nCheck the settings")


class ColorConfigWidget(QGroupBox):
    """Simplified color configuration widget"""

    def __init__(self, line_name, color_config):
        super().__init__(color_config.get('name', line_name))
        self.line_name = line_name
        self.color_config = color_config
        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Enable checkbox
        self.enabled_cb = QCheckBox("Enable This Line")
        self.enabled_cb.setChecked(self.color_config.get('enabled', True))
        self.enabled_cb.stateChanged.connect(self.on_enabled_changed)
        layout.addWidget(self.enabled_cb)

        # HSV sliders
        sliders_layout = QGridLayout()

        self.sliders = {}
        params = [
            ('hue_min', 'Color Min', 0, 179),
            ('hue_max', 'Color Max', 0, 179),
            ('sat_min', 'Brightness Min', 0, 255),
            ('sat_max', 'Brightness Max', 0, 255),
            ('val_min', 'Contrast Min', 0, 255),
            ('val_max', 'Contrast Max', 0, 255)
        ]

        for i, (param, label, min_val, max_val) in enumerate(params):
            row = i // 2
            col_offset = (i % 2) * 3

            # Label
            label_widget = QLabel(label)
            sliders_layout.addWidget(label_widget, row, col_offset)

            # Slider
            slider = QSlider(Qt.Horizontal)
            slider.setRange(min_val, max_val)
            slider.setValue(self.color_config.get(param, min_val))
            slider.valueChanged.connect(lambda v, p=param: self.on_slider_changed(p, v))
            sliders_layout.addWidget(slider, row, col_offset + 1)

            # Value label
            value_label = QLabel(str(slider.value()))
            sliders_layout.addWidget(value_label, row, col_offset + 2)

            self.sliders[param] = (slider, value_label)

        layout.addLayout(sliders_layout)

        # Reset button
        reset_btn = QPushButton("🔄 Reset to Default")
        reset_btn.clicked.connect(self.reset_config)
        layout.addWidget(reset_btn)

        self.setLayout(layout)

    def on_enabled_changed(self, state):
        enabled = state == Qt.Checked
        color_config = config.get_color_config(self.line_name)
        color_config['enabled'] = enabled
        config.set_color_config(self.line_name, color_config)

    def on_slider_changed(self, param, value):
        # Update value label
        _, value_label = self.sliders[param]
        value_label.setText(str(value))

        # Update config
        color_config = config.get_color_config(self.line_name)
        color_config[param] = value
        config.set_color_config(self.line_name, color_config)

    def reset_config(self):
        # Reset to default values for this line type
        if "line1" in self.line_name:
            defaults = {
                'hue_min': 20, 'hue_max': 35,
                'sat_min': 100, 'sat_max': 255,
                'val_min': 100, 'val_max': 255,
                'enabled': True
            }
        else:
            defaults = {
                'hue_min': 120, 'hue_max': 150,
                'sat_min': 100, 'sat_max': 255,
                'val_min': 100, 'val_max': 255,
                'enabled': True
            }

        config.set_color_config(self.line_name, defaults)

        # Update UI
        for param, (slider, value_label) in self.sliders.items():
            slider.setValue(defaults[param])
            value_label.setText(str(defaults[param]))

        self.enabled_cb.setChecked(defaults['enabled'])


class ZigZagDetectorApp(QMainWindow):
    """Simplified main application"""

    def __init__(self):
        super().__init__()

        # Initialize components
        self.window_capture = WindowCapture()
        self.color_detector = ColorDetector(config)
        self.crossover_detector = CrossoverDetector(config)
        self.alert_manager = AlertManager(config)

        # State
        self.detected_lines = []
        self.detected_crossovers = []
        self.start_time = time.time()
        self.is_detecting = False

        # Detection worker
        self.detection_worker = None

        self.setup_ui()
        self.setup_connections()
        self.load_settings()

        # Status timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)

        # Capture timer for thread-safe screen capture
        self.capture_timer = QTimer()
        self.capture_timer.timeout.connect(self.do_capture)

    def setup_ui(self):
        """Setup the simplified UI"""
        self.setWindowTitle("📈 ZigZag Crossover Detector - PocketOption Bot")
        self.setMinimumSize(1200, 800)

        # Apply simple, clean theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2d2d2d;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 2px solid #0078d4;
                background-color: #333;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #444;
                color: #ccc;
                padding: 12px 20px;
                margin: 2px;
                border-radius: 6px;
                font-size: 14px;
                font-weight: bold;
            }
            QTabBar::tab:selected {
                background-color: #0078d4;
                color: white;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 12px 20px;
                border-radius: 8px;
                font-weight: bold;
                font-size: 14px;
            }
            QPushButton:hover {
                background-color: #106ebe;
            }
            QPushButton:pressed {
                background-color: #005a9e;
            }
            QPushButton:disabled {
                background-color: #666;
                color: #999;
            }
            QGroupBox {
                font-weight: bold;
                border: 2px solid #0078d4;
                border-radius: 8px;
                margin: 15px 0px;
                padding-top: 15px;
                font-size: 16px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 15px;
                padding: 0 10px 0 10px;
                color: #0078d4;
            }
        """)

        # Central widget with tabs
        central_widget = QWidget()
        self.setCentralWidget(central_widget)

        layout = QVBoxLayout(central_widget)

        # Tab widget
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)

        # Create tabs
        self.setup_simple_main_tab()
        self.setup_capture_tab()
        self.setup_colors_tab()
        self.setup_detection_tab()
        self.setup_alerts_tab()
        self.setup_logs_tab()

        # Status bar
        self.statusBar().showMessage("🚀 Ready to start")
        self.uptime_label = QLabel("Not Running")
        self.stats_label = QLabel("Crossovers: 0")

        self.statusBar().addPermanentWidget(self.stats_label)
        self.statusBar().addPermanentWidget(self.uptime_label)

    def setup_simple_main_tab(self):
        """Setup super simple main tab"""
        main_widget = QWidget()
        self.tabs.addTab(main_widget, "🏠 START HERE")

        layout = QVBoxLayout(main_widget)

        # Big title
        title_label = QLabel("📈 ZigZag Crossover Bot")
        title_label.setAlignment(Qt.AlignCenter)
        title_label.setStyleSheet("""
            QLabel {
                font-size: 32px;
                font-weight: bold;
                color: #0078d4;
                padding: 20px;
            }
        """)
        layout.addWidget(title_label)

        # Step 1: Window Setup
        step1_group = QGroupBox("STEP 1: Find Your Trading Window")
        step1_layout = QVBoxLayout(step1_group)

        # Window status
        self.window_status_label = QLabel("❌ No window found yet")
        self.window_status_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                padding: 10px;
                border-radius: 6px;
                background-color: #444;
            }
        """)
        step1_layout.addWidget(self.window_status_label)

        # Big find window button
        self.find_window_btn = QPushButton("🔍 FIND POCKETOPTION WINDOW")
        self.find_window_btn.clicked.connect(self.auto_detect_window)
        self.find_window_btn.setStyleSheet("""
            QPushButton {
                font-size: 20px;
                padding: 20px;
                background-color: #28a745;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        step1_layout.addWidget(self.find_window_btn)

        layout.addWidget(step1_group)

        # Step 2: Telegram Setup
        step2_group = QGroupBox("STEP 2: Setup Alerts (Optional)")
        step2_layout = QVBoxLayout(step2_group)

        # Telegram status
        self.telegram_status_label = QLabel("📱 Configure in 'Alert Settings' tab if you want notifications")
        self.telegram_status_label.setStyleSheet("font-size: 16px; color: #ccc;")
        step2_layout.addWidget(self.telegram_status_label)

        layout.addWidget(step2_group)

        # Step 3: Start Detection
        step3_group = QGroupBox("STEP 3: Start Bot")
        step3_layout = QVBoxLayout(step3_group)

        # Detection status
        self.detection_status_label = QLabel("🤖 Ready to start scanning")
        self.detection_status_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                padding: 10px;
                border-radius: 6px;
                background-color: #444;
            }
        """)
        step3_layout.addWidget(self.detection_status_label)

        # Big start/stop button
        self.main_detection_btn = QPushButton("🚀 START BOT")
        self.main_detection_btn.clicked.connect(self.toggle_detection)
        self.main_detection_btn.setStyleSheet("""
            QPushButton {
                font-size: 24px;
                padding: 25px;
                background-color: #28a745;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        step3_layout.addWidget(self.main_detection_btn)

        layout.addWidget(step3_group)

        # Live view
        preview_group = QGroupBox("📺 Live View")
        preview_layout = QVBoxLayout(preview_group)

        self.image_display = ImageDisplayWidget()
        preview_layout.addWidget(self.image_display)

        # Simple stats
        stats_layout = QHBoxLayout()

        self.simple_lines_label = QLabel("Lines Found: 0")
        self.simple_lines_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        stats_layout.addWidget(self.simple_lines_label)

        self.simple_crossovers_label = QLabel("Crossovers Found: 0")
        self.simple_crossovers_label.setStyleSheet("font-size: 16px; font-weight: bold; color: #28a745;")
        stats_layout.addWidget(self.simple_crossovers_label)

        stats_layout.addStretch()
        preview_layout.addLayout(stats_layout)

        layout.addWidget(preview_group)

    def setup_capture_tab(self):
        """Setup capture configuration tab"""
        capture_widget = QWidget()
        self.tabs.addTab(capture_widget, "📸 Window Settings")

        layout = QVBoxLayout(capture_widget)

        # Instructions
        instructions = QLabel("""
        <h2>📸 Window Capture Settings</h2>
        <p>The bot needs to see your PocketOption chart to detect crossovers.</p>
        <p><b>Automatic:</b> Click "Find Windows" and select your browser with PocketOption</p>
        <p><b>Manual:</b> Set custom screen region coordinates below</p>
        """)
        instructions.setStyleSheet("background-color: #3a3a3a; padding: 15px; border-radius: 8px;")
        layout.addWidget(instructions)

        # Window selection
        window_group = QGroupBox("🪟 Automatic Window Detection")
        window_layout = QVBoxLayout(window_group)

        # Find windows button
        find_btn = QPushButton("🔄 Find All Windows")
        find_btn.clicked.connect(self.refresh_window_list)
        window_layout.addWidget(find_btn)

        # Window list
        self.window_list = QListWidget()
        self.window_list.setMaximumHeight(150)
        window_layout.addWidget(self.window_list)

        # Select button
        select_btn = QPushButton("✅ Use Selected Window")
        select_btn.clicked.connect(self.select_window_from_list)
        window_layout.addWidget(select_btn)

        layout.addWidget(window_group)

        # Manual region
        manual_group = QGroupBox("🎯 Manual Screen Region")
        manual_layout = QGridLayout(manual_group)

        # Coordinates
        manual_layout.addWidget(QLabel("Left:"), 0, 0)
        self.region_left = QSpinBox()
        self.region_left.setRange(0, 9999)
        self.region_left.setValue(100)
        manual_layout.addWidget(self.region_left, 0, 1)

        manual_layout.addWidget(QLabel("Top:"), 0, 2)
        self.region_top = QSpinBox()
        self.region_top.setRange(0, 9999)
        self.region_top.setValue(100)
        manual_layout.addWidget(self.region_top, 0, 3)

        manual_layout.addWidget(QLabel("Width:"), 1, 0)
        self.region_width = QSpinBox()
        self.region_width.setRange(100, 9999)
        self.region_width.setValue(1200)
        manual_layout.addWidget(self.region_width, 1, 1)

        manual_layout.addWidget(QLabel("Height:"), 1, 2)
        self.region_height = QSpinBox()
        self.region_height.setRange(100, 9999)
        self.region_height.setValue(800)
        manual_layout.addWidget(self.region_height, 1, 3)

        apply_btn = QPushButton("✅ Use These Coordinates")
        apply_btn.clicked.connect(self.apply_manual_region)
        manual_layout.addWidget(apply_btn, 0, 4, 2, 1)

        layout.addWidget(manual_group)

        # Speed setting
        speed_group = QGroupBox("⚙️ Scan Speed")
        speed_layout = QHBoxLayout(speed_group)

        speed_layout.addWidget(QLabel("Scans per second:"))
        self.fps_slider = QSlider(Qt.Horizontal)
        self.fps_slider.setRange(5, 50)  # 0.5 to 5.0 FPS
        self.fps_slider.setValue(int(config.get('capture', 'fps', 2) * 10))
        self.fps_slider.valueChanged.connect(self.on_fps_changed)
        speed_layout.addWidget(self.fps_slider)

        self.fps_label = QLabel(f"{config.get('capture', 'fps', 2):.1f}")
        speed_layout.addWidget(self.fps_label)

        layout.addWidget(speed_group)
        layout.addStretch()

    def setup_colors_tab(self):
        """Setup color configuration tab"""
        colors_widget = QWidget()
        self.tabs.addTab(colors_widget, "🎨 Line Colors")

        layout = QVBoxLayout(colors_widget)

        # Instructions
        instructions = QLabel("""
        <h2>🎨 ZigZag Line Detection</h2>
        <p>Adjust these settings so the bot can see your ZigZag lines clearly.</p>
        <p><b>Make sure:</b> Your ZigZag indicators are visible and have different colors</p>
        <p><b>Tip:</b> Use bright, contrasting colors for best detection</p>
        """)
        instructions.setStyleSheet("background-color: #3a3a3a; padding: 15px; border-radius: 8px;")
        layout.addWidget(instructions)

        # Create scroll area for color configs
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Color configuration widgets
        self.color_widgets = {}
        for line_name, color_config in config.config['colors'].items():
            color_widget = ColorConfigWidget(line_name, color_config)
            self.color_widgets[line_name] = color_widget
            scroll_layout.addWidget(color_widget)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

    def setup_detection_tab(self):
        """Setup detection settings tab"""
        detection_widget = QWidget()
        self.tabs.addTab(detection_widget, "🔍 Detection Settings")

        layout = QVBoxLayout(detection_widget)

        # Instructions
        instructions = QLabel("""
        <h2>🔍 Detection Settings</h2>
        <p>Fine-tune how sensitive the crossover detection is.</p>
        <p><b>Default settings work for most cases</b> - only change if needed.</p>
        """)
        instructions.setStyleSheet("background-color: #3a3a3a; padding: 15px; border-radius: 8px;")
        layout.addWidget(instructions)

        # Detection parameters
        params_group = QGroupBox("⚙️ Sensitivity Settings")
        params_layout = QVBoxLayout(params_group)

        # Min line length
        length_layout = QHBoxLayout()
        length_layout.addWidget(QLabel("Minimum Line Length (ignore small lines):"))
        self.min_length_slider = QSlider(Qt.Horizontal)
        self.min_length_slider.setRange(10, 100)
        self.min_length_slider.setValue(config.get('detection', 'min_line_length', 30))
        self.min_length_slider.valueChanged.connect(self.on_min_length_changed)
        length_layout.addWidget(self.min_length_slider)
        self.min_length_label = QLabel(str(self.min_length_slider.value()))
        length_layout.addWidget(self.min_length_label)
        params_layout.addLayout(length_layout)

        # Confidence threshold
        conf_layout = QHBoxLayout()
        conf_layout.addWidget(QLabel("Detection Confidence (higher = fewer false alerts):"))
        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(10, 100)
        self.confidence_slider.setValue(int(config.get('detection', 'confidence_threshold', 0.7) * 100))
        self.confidence_slider.valueChanged.connect(self.on_confidence_changed)
        conf_layout.addWidget(self.confidence_slider)
        self.confidence_label = QLabel(f"{self.confidence_slider.value()}%")
        conf_layout.addWidget(self.confidence_label)
        params_layout.addLayout(conf_layout)

        # Debounce time
        debounce_layout = QHBoxLayout()
        debounce_layout.addWidget(QLabel("Alert Cooldown (seconds between alerts):"))
        self.debounce_slider = QSlider(Qt.Horizontal)
        self.debounce_slider.setRange(10, 300)
        self.debounce_slider.setValue(config.get('detection', 'debounce_seconds', 60))
        self.debounce_slider.valueChanged.connect(self.on_debounce_changed)
        debounce_layout.addWidget(self.debounce_slider)
        self.debounce_label = QLabel(str(self.debounce_slider.value()))
        debounce_layout.addWidget(self.debounce_label)
        params_layout.addLayout(debounce_layout)

        layout.addWidget(params_group)
        layout.addStretch()

    def setup_alerts_tab(self):
        """Setup alerts configuration tab"""
        alerts_widget = QWidget()
        self.tabs.addTab(alerts_widget, "🔔 Alert Settings")

        layout = QVBoxLayout(alerts_widget)

        # Instructions
        instructions = QLabel("""
        <h2>📱 Telegram Alerts Setup</h2>
        <p><b>Step 1:</b> Create a bot by messaging @BotFather on Telegram</p>
        <p><b>Step 2:</b> Get your bot token and paste it below</p>
        <p><b>Step 3:</b> Get your chat ID and paste it below</p>
        <p><b>Step 4:</b> Test the connection</p>
        """)
        instructions.setStyleSheet("background-color: #3a3a3a; padding: 15px; border-radius: 8px;")
        layout.addWidget(instructions)

        # Telegram configuration
        telegram_group = QGroupBox("📱 Telegram Bot Configuration")
        telegram_layout = QVBoxLayout(telegram_group)

        # Enable checkbox
        self.telegram_enabled = QCheckBox("📲 Send Alerts to Telegram")
        self.telegram_enabled.setChecked(config.get('alerts', 'telegram_enabled', True))
        self.telegram_enabled.setStyleSheet("font-size: 16px; font-weight: bold;")
        telegram_layout.addWidget(self.telegram_enabled)

        # Token entry
        telegram_layout.addWidget(QLabel("Bot Token:"))
        self.token_input = QLineEdit()
        self.token_input.setText(config.get('alerts', 'telegram_token', ''))
        self.token_input.setPlaceholderText("Paste your bot token here...")
        telegram_layout.addWidget(self.token_input)

        # Chat ID entry
        telegram_layout.addWidget(QLabel("Chat ID:"))
        self.chat_id_input = QLineEdit()
        self.chat_id_input.setText(config.get('alerts', 'telegram_chat_id', ''))
        self.chat_id_input.setPlaceholderText("Paste your chat ID here...")
        telegram_layout.addWidget(self.chat_id_input)

        # Test button
        test_btn = QPushButton("🔗 Test Telegram Connection")
        test_btn.clicked.connect(self.test_telegram)
        telegram_layout.addWidget(test_btn)

        layout.addWidget(telegram_group)

        # Other settings
        other_group = QGroupBox("🔔 Other Alert Options")
        other_layout = QVBoxLayout(other_group)

        self.sound_enabled = QCheckBox("🔊 Play Sound When Crossover Found")
        self.sound_enabled.setChecked(config.get('alerts', 'sound_enabled', True))
        other_layout.addWidget(self.sound_enabled)

        self.log_enabled = QCheckBox("📝 Save Crossovers to Log File")
        self.log_enabled.setChecked(config.get('alerts', 'log_file_enabled', True))
        other_layout.addWidget(self.log_enabled)

        layout.addWidget(other_group)

        # Save button
        save_btn = QPushButton("💾 SAVE ALERT SETTINGS")
        save_btn.clicked.connect(self.save_alert_settings)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                font-size: 16px;
                padding: 15px;
            }
        """)
        layout.addWidget(save_btn)

        layout.addStretch()

    def setup_logs_tab(self):
        """Setup logs tab"""
        logs_widget = QWidget()
        self.tabs.addTab(logs_widget, "📝 Logs")

        layout = QVBoxLayout(logs_widget)

        # Log display
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: 'Consolas', 'Monaco', monospace;
                font-size: 12px;
                border: 2px solid #444;
                border-radius: 6px;
            }
        """)
        layout.addWidget(self.log_text)

        # Log controls
        controls = QHBoxLayout()

        clear_btn = QPushButton("🗑️ Clear Log")
        clear_btn.clicked.connect(self.clear_log)
        controls.addWidget(clear_btn)

        save_btn = QPushButton("💾 Save Log to File")
        save_btn.clicked.connect(self.save_log)
        controls.addWidget(save_btn)

        controls.addStretch()
        layout.addLayout(controls)

    def setup_connections(self):
        """Setup signal connections"""
        pass

    def load_settings(self):
        """Load settings into GUI"""
        try:
            self.fps_slider.setValue(int(config.get('capture', 'fps', 2) * 10))
            self.min_length_slider.setValue(config.get('detection', 'min_line_length', 30))
            self.confidence_slider.setValue(int(config.get('detection', 'confidence_threshold', 0.7) * 100))
            self.debounce_slider.setValue(config.get('detection', 'debounce_seconds', 60))

            self.telegram_enabled.setChecked(config.get('alerts', 'telegram_enabled', True))
            self.token_input.setText(config.get('alerts', 'telegram_token', ''))
            self.chat_id_input.setText(config.get('alerts', 'telegram_chat_id', ''))
            self.sound_enabled.setChecked(config.get('alerts', 'sound_enabled', True))
            self.log_enabled.setChecked(config.get('alerts', 'log_file_enabled', True))

        except Exception as e:
            logging.error(f"Failed to load settings: {e}")

    # THREAD-SAFE CAPTURE METHOD
    def do_capture(self):
        """Capture screen in main thread - THREAD SAFE"""
        try:
            if self.detection_worker and self.detection_worker.isRunning():
                image = self.window_capture.capture_screen()
                if image is not None:
                    self.detection_worker.set_image(image)
        except Exception as e:
            logging.error(f"Screen capture failed: {e}")

    # Event handlers
    def auto_detect_window(self):
        """Simple setup process - auto detect or manual selection"""
        self.log_message("🔍 Setting up chart monitoring...")

        # Try auto-detection first
        window = self.window_capture.auto_detect_window()
        if window:
            self.window_status_label.setText(f"✅ Found: {window.title}")
            self.window_status_label.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    padding: 10px;
                    border-radius: 6px;
                    background-color: #28a745;
                    color: white;
                }
            """)
            self.log_message(f"✅ Auto-detected: {window.title}")
            return

        # Auto-detection failed, offer simple choice
        reply = QMessageBox.question(self, "Setup Chart Area",
                                     "No PocketOption window found automatically.\n\n"
                                     "Would you like to manually select your chart area?",
                                     QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            self.open_region_selector()
        else:
            self.window_status_label.setText("❌ Setup not completed")
            self.window_status_label.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    padding: 10px;
                    border-radius: 6px;
                    background-color: #dc3545;
                    color: white;
                }
            """)

    def open_region_selector(self):
        """Open the simple region selector"""
        self.log_message("📱 Opening chart area selector...")

        selector = SimpleRegionSelector()
        region = selector.select_region()

        if region:
            self.window_capture.set_custom_region(region)
            self.window_status_label.setText(f"✅ Chart area selected ({region['width']}x{region['height']})")
            self.window_status_label.setStyleSheet("""
                QLabel {
                    font-size: 18px;
                    padding: 10px;
                    border-radius: 6px;
                    background-color: #28a745;
                    color: white;
                }
            """)
            self.log_message(f"✅ Chart area selected: {region['width']}x{region['height']}")
        else:
            self.log_message("❌ Chart area selection cancelled")

    def toggle_detection(self):
        """Start or stop detection"""
        if not self.is_detecting:
            self.start_detection()
        else:
            self.stop_detection()

    def start_detection(self):
        """Start detection"""
        if not self.validate_setup():
            return

        self.is_detecting = True

        # Create worker
        self.detection_worker = DetectionWorker(
            self.color_detector, self.crossover_detector, self.alert_manager
        )

        # Connect signals
        self.detection_worker.image_ready.connect(self.on_image_ready)
        self.detection_worker.lines_detected.connect(self.on_lines_detected)
        self.detection_worker.crossover_detected.connect(self.on_crossover_detected)
        self.detection_worker.error_occurred.connect(self.on_error_occurred)
        self.detection_worker.status_update.connect(self.on_status_update)
        self.detection_worker.capture_request.connect(self.do_capture)

        # Start worker and capture timer
        self.detection_worker.start()
        fps = config.get('capture', 'fps', 2)
        self.capture_timer.start(int(1000 / max(fps, 0.1)))

        # Update UI
        self.main_detection_btn.setText("⏹️ STOP BOT")
        self.main_detection_btn.setStyleSheet("""
            QPushButton {
                font-size: 24px;
                padding: 25px;
                background-color: #dc3545;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)

        self.detection_status_label.setText("🤖 Bot is running and scanning...")
        self.detection_status_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                padding: 10px;
                border-radius: 6px;
                background-color: #28a745;
                color: white;
            }
        """)

        self.statusBar().showMessage("🔍 Bot running - scanning for crossovers...")
        self.log_message("🚀 Detection started")

    def stop_detection(self):
        """Stop detection"""
        self.is_detecting = False

        # Stop capture timer
        self.capture_timer.stop()

        # Stop worker
        if self.detection_worker and self.detection_worker.isRunning():
            self.detection_worker.stop()

        # Update UI
        self.main_detection_btn.setText("🚀 START BOT")
        self.main_detection_btn.setStyleSheet("""
            QPushButton {
                font-size: 24px;
                padding: 25px;
                background-color: #28a745;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)

        self.detection_status_label.setText("🤖 Bot stopped")
        self.detection_status_label.setStyleSheet("""
            QLabel {
                font-size: 18px;
                padding: 10px;
                border-radius: 6px;
                background-color: #444;
            }
        """)

        self.statusBar().showMessage("⏹️ Bot stopped")
        self.log_message("⏹️ Detection stopped")

    def validate_setup(self):
        """Validate setup before starting"""
        # Check window/region
        capture_info = self.window_capture.get_capture_info()
        if not capture_info['valid']:
            QMessageBox.critical(self, "Setup Required",
                                 "❌ No window or screen region selected!\n\n"
                                 "Please click 'FIND POCKETOPTION WINDOW' first.")
            return False

        # Check colors
        enabled_colors = sum(1 for color_config in config.config['colors'].values()
                             if color_config.get('enabled', True))
        if enabled_colors < 2:
            QMessageBox.critical(self, "Color Setup Required",
                                 "❌ Need at least 2 line colors enabled!\n\n"
                                 "Go to 'Line Colors' tab and enable both lines.")
            return False

        return True

    # Signal handlers
    def on_image_ready(self, image):
        self.image_display.update_image(image, self.detected_lines, self.detected_crossovers)

    def on_lines_detected(self, lines):
        self.detected_lines = lines
        self.simple_lines_label.setText(f"Lines Found: {len(lines)}")

    def on_crossover_detected(self, crossover):
        self.detected_crossovers.append(crossover)
        total = len(self.detected_crossovers)
        self.simple_crossovers_label.setText(f"Crossovers Found: {total}")

        # Log with emoji
        self.log_message(f"🎯 CROSSOVER! {crossover.line1_name} × {crossover.line2_name}")

    def on_error_occurred(self, error_msg):
        self.log_message(f"❌ Error: {error_msg}")

    def on_status_update(self, status_msg):
        self.statusBar().showMessage(status_msg)

    # Settings change handlers
    def on_fps_changed(self, value):
        fps = value / 10.0
        self.fps_label.setText(f"{fps:.1f}")
        config.set('capture', 'fps', fps)

        # Update capture timer if running
        if self.capture_timer.isActive():
            self.capture_timer.setInterval(int(1000 / max(fps, 0.1)))

    def on_min_length_changed(self, value):
        self.min_length_label.setText(str(value))
        config.set('detection', 'min_line_length', value)

    def on_confidence_changed(self, value):
        self.confidence_label.setText(f"{value}%")
        config.set('detection', 'confidence_threshold', value / 100.0)

    def on_debounce_changed(self, value):
        self.debounce_label.setText(str(value))
        config.set('detection', 'debounce_seconds', value)

    # Utility methods
    def log_message(self, message):
        """Add message to log display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"
        self.log_text.append(log_entry)

        # Keep only last 500 lines
        if self.log_text.document().blockCount() > 500:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 50)
            cursor.removeSelectedText()

    def update_status(self):
        """Update status display"""
        if self.is_detecting:
            uptime_seconds = int(time.time() - self.start_time)
            hours = uptime_seconds // 3600
            minutes = (uptime_seconds % 3600) // 60
            self.uptime_label.setText(f"Running: {hours:02d}:{minutes:02d}")
        else:
            self.uptime_label.setText("Not Running")

    def refresh_window_list(self):
        """Refresh window list"""
        windows = self.window_capture.find_windows()
        self.window_list.clear()
        for window in windows:
            size_text = f"{window.rect[2] - window.rect[0]}x{window.rect[3] - window.rect[1]}"
            self.window_list.addItem(f"{window.title} ({size_text})")

    def select_window_from_list(self):
        """Select window from list"""
        current_row = self.window_list.currentRow()
        if current_row >= 0:
            windows = self.window_capture.find_windows()
            if current_row < len(windows):
                selected_window = windows[current_row]
                self.window_capture.set_target_window(selected_window)
                self.window_status_label.setText(f"✅ Selected: {selected_window.title}")

    def apply_manual_region(self):
        """Apply manual region"""
        region = {
            'left': self.region_left.value(),
            'top': self.region_top.value(),
            'width': self.region_width.value(),
            'height': self.region_height.value()
        }
        self.window_capture.set_custom_region(region)
        self.window_status_label.setText(f"✅ Custom region: {region['width']}x{region['height']}")

    def test_telegram(self):
        """Test Telegram connection"""
        config.set('alerts', 'telegram_token', self.token_input.text())
        config.set('alerts', 'telegram_chat_id', self.chat_id_input.text())

        success, message = self.alert_manager.telegram.test_connection()
        if success:
            QMessageBox.information(self, "Telegram Test", f"✅ {message}")
            self.log_message(f"✅ Telegram: {message}")
        else:
            QMessageBox.critical(self, "Telegram Test", f"❌ {message}")
            self.log_message(f"❌ Telegram: {message}")

    def save_alert_settings(self):
        """Save alert settings"""
        try:
            config.set('alerts', 'telegram_enabled', self.telegram_enabled.isChecked())
            config.set('alerts', 'telegram_token', self.token_input.text())
            config.set('alerts', 'telegram_chat_id', self.chat_id_input.text())
            config.set('alerts', 'sound_enabled', self.sound_enabled.isChecked())
            config.set('alerts', 'log_file_enabled', self.log_enabled.isChecked())

            config.save_config()
            QMessageBox.information(self, "Settings Saved", "✅ Alert settings saved!")
            self.log_message("💾 Alert settings saved")

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"❌ Failed to save: {e}")

    def clear_log(self):
        """Clear log"""
        self.log_text.clear()
        self.log_message("📝 Log cleared")

    def save_log(self):
        """Save log to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Log", f"zigzag_log_{int(time.time())}.txt",
            "Text Files (*.txt)"
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.log_text.toPlainText())
                QMessageBox.information(self, "Log Saved", f"✅ Log saved to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"❌ Failed to save: {e}")

    def closeEvent(self, event):
        """Handle app closing"""
        try:
            if self.is_detecting:
                self.stop_detection()
            self.alert_manager.telegram.stop_worker()
            config.save_config()
            self.log_message("👋 App shutting down...")
            event.accept()
        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
            event.accept()

    def run(self):
        """Run the application"""
        self.show()
        self.log_message("🎯 ZigZag Bot started - Welcome!")
        self.log_message("📋 Click 'FIND POCKETOPTION WINDOW' to begin")


def create_app():
    """Create QApplication"""
    app = QApplication(sys.argv)
    app.setApplicationName("ZigZag Crossover Detector")
    app.setApplicationVersion("2.0")
    return app