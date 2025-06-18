"""
Modern PySide6 GUI for ZigZag Detector
Clean, professional interface with proper threading
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


class DetectionWorker(QThread):
    """Worker thread for detection loop - PROPER Qt threading"""

    # Signals for thread-safe communication
    image_ready = Signal(np.ndarray)
    lines_detected = Signal(list)
    crossover_detected = Signal(object)
    error_occurred = Signal(str)
    status_update = Signal(str)

    def __init__(self, window_capture, color_detector, crossover_detector, alert_manager):
        super().__init__()
        self.window_capture = window_capture
        self.color_detector = color_detector
        self.crossover_detector = crossover_detector
        self.alert_manager = alert_manager

        self.running = False
        self.paused = False

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

                # Capture screen
                image = self.window_capture.capture_screen()
                if image is None:
                    self.status_update.emit(f"No image captured (loop {loop_count})")
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

                self.status_update.emit(f"Loop {loop_count}: {len(detected_lines)} lines, {len(crossovers)} crossovers")

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
    """Custom widget for displaying OpenCV images with zoom/pan"""

    def __init__(self):
        super().__init__()
        self.setMinimumSize(800, 600)
        self.setStyleSheet("border: 2px solid #333; background-color: #222;")
        self.setAlignment(Qt.AlignCenter)
        self.setText("📸 No image captured yet\n\nClick 'Start Detection' to begin")
        self.setStyleSheet("""
            QLabel {
                border: 2px solid #444;
                background-color: #2b2b2b;
                color: #ccc;
                font-size: 14px;
                border-radius: 8px;
            }
        """)

        self.current_pixmap = None
        self.scale_factor = 1.0

    def update_image(self, cv_image, detected_lines=None, crossovers=None):
        """Update the displayed image with detections"""
        try:
            # Create visualization
            vis_image = cv_image.copy()

            if detected_lines:
                vis_image = ColorDetector(config).visualize_detection(vis_image, detected_lines)

            if crossovers:
                vis_image = CrossoverVisualizer.draw_crossovers(vis_image, crossovers[-10:])

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
            self.setText(f"❌ Display error: {str(e)[:50]}...")

    def wheelEvent(self, event):
        """Handle mouse wheel for zooming"""
        if self.current_pixmap:
            # Zoom in/out
            delta = event.angleDelta().y()
            if delta > 0:
                self.scale_factor *= 1.1
            else:
                self.scale_factor /= 1.1

            # Limit zoom range
            self.scale_factor = max(0.1, min(self.scale_factor, 5.0))

            # Apply zoom
            if self.current_pixmap:
                new_size = self.current_pixmap.size() * self.scale_factor
                scaled = self.current_pixmap.scaled(new_size, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                self.setPixmap(scaled)


class ColorConfigWidget(QGroupBox):
    """Widget for configuring a single color line"""

    def __init__(self, line_name, color_config):
        super().__init__(color_config.get('name', line_name))
        self.line_name = line_name
        self.color_config = color_config

        self.setup_ui()

    def setup_ui(self):
        layout = QVBoxLayout()

        # Enable checkbox
        self.enabled_cb = QCheckBox("Enable Detection")
        self.enabled_cb.setChecked(self.color_config.get('enabled', True))
        self.enabled_cb.stateChanged.connect(self.on_enabled_changed)
        layout.addWidget(self.enabled_cb)

        # HSV sliders
        sliders_layout = QGridLayout()

        self.sliders = {}
        params = [
            ('hue_min', 'Hue Min', 0, 179),
            ('hue_max', 'Hue Max', 0, 179),
            ('sat_min', 'Sat Min', 0, 255),
            ('sat_max', 'Sat Max', 0, 255),
            ('val_min', 'Val Min', 0, 255),
            ('val_max', 'Val Max', 0, 255)
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

        # Buttons
        buttons_layout = QHBoxLayout()

        calibrate_btn = QPushButton("🎨 Calibrate")
        calibrate_btn.clicked.connect(self.calibrate_color)
        buttons_layout.addWidget(calibrate_btn)

        test_btn = QPushButton("🧪 Test")
        test_btn.clicked.connect(self.test_detection)
        buttons_layout.addWidget(test_btn)

        reset_btn = QPushButton("🔄 Reset")
        reset_btn.clicked.connect(self.reset_config)
        buttons_layout.addWidget(reset_btn)

        layout.addLayout(buttons_layout)
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

    def calibrate_color(self):
        QMessageBox.information(self, "Calibration", "Color calibration feature coming soon!")

    def test_detection(self):
        QMessageBox.information(self, "Test", "Color test feature coming soon!")

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
    """Modern PySide6 main application"""

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

        # Detection worker
        self.detection_worker = None

        self.setup_ui()
        self.setup_connections()
        self.load_settings()

        # Status timer
        self.status_timer = QTimer()
        self.status_timer.timeout.connect(self.update_status)
        self.status_timer.start(1000)  # Update every second

    def setup_ui(self):
        """Setup the modern UI"""
        self.setWindowTitle("🎯 ZigZag Crossover Detector v2.0")
        self.setMinimumSize(1400, 900)

        # Apply modern dark theme
        self.setStyleSheet("""
            QMainWindow {
                background-color: #2b2b2b;
                color: #ffffff;
            }
            QTabWidget::pane {
                border: 2px solid #444;
                background-color: #333;
                border-radius: 8px;
            }
            QTabBar::tab {
                background-color: #444;
                color: #ccc;
                padding: 8px 16px;
                margin: 2px;
                border-radius: 6px;
            }
            QTabBar::tab:selected {
                background-color: #0078d4;
                color: white;
            }
            QTabBar::tab:hover {
                background-color: #555;
            }
            QPushButton {
                background-color: #0078d4;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: bold;
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
                border: 2px solid #555;
                border-radius: 8px;
                margin: 10px 0px;
                padding-top: 10px;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 10px;
                padding: 0 10px 0 10px;
                color: #0078d4;
            }
            QLabel {
                color: #ccc;
            }
            QSlider::groove:horizontal {
                border: 1px solid #999;
                height: 8px;
                background: #555;
                border-radius: 4px;
            }
            QSlider::handle:horizontal {
                background: #0078d4;
                border: 1px solid #0078d4;
                width: 18px;
                border-radius: 9px;
                margin: -2px 0;
            }
            QCheckBox {
                color: #ccc;
            }
            QCheckBox::indicator:checked {
                background-color: #0078d4;
                border: 2px solid #0078d4;
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
        self.setup_main_tab()
        self.setup_capture_tab()
        self.setup_colors_tab()
        self.setup_detection_tab()
        self.setup_alerts_tab()
        self.setup_logs_tab()

        # Status bar
        self.statusBar().showMessage("🚀 Ready to detect crossovers")

        # Create status widgets
        self.uptime_label = QLabel("Uptime: 00:00:00")
        self.stats_label = QLabel("Lines: 0 | Crossovers: 0")

        self.statusBar().addPermanentWidget(self.stats_label)
        self.statusBar().addPermanentWidget(self.uptime_label)

    def setup_main_tab(self):
        """Setup main control tab"""
        main_widget = QWidget()
        self.tabs.addTab(main_widget, "🎯 Main Control")

        layout = QVBoxLayout(main_widget)

        # Quick setup section
        setup_group = QGroupBox("🚀 Quick Setup")
        setup_layout = QVBoxLayout(setup_group)

        # Step 1: Window Detection
        step1_layout = QHBoxLayout()
        step1_layout.addWidget(QLabel("1. Detect PocketOption Window:"))

        self.auto_detect_btn = QPushButton("🔍 Auto Detect")
        self.auto_detect_btn.clicked.connect(self.auto_detect_window)
        step1_layout.addWidget(self.auto_detect_btn)

        self.manual_select_btn = QPushButton("🖱️ Manual Select")
        self.manual_select_btn.clicked.connect(self.manual_select_region)
        step1_layout.addWidget(self.manual_select_btn)

        self.window_status_label = QLabel("❌ No window selected")
        self.window_status_label.setStyleSheet("color: #ff6b6b;")
        step1_layout.addWidget(self.window_status_label)
        step1_layout.addStretch()

        setup_layout.addLayout(step1_layout)

        # Step 2: Test Capture
        step2_layout = QHBoxLayout()
        step2_layout.addWidget(QLabel("2. Test Screen Capture:"))

        self.test_capture_btn = QPushButton("📸 Test Capture")
        self.test_capture_btn.clicked.connect(self.test_capture)
        step2_layout.addWidget(self.test_capture_btn)

        self.calibrate_colors_btn = QPushButton("🎨 Calibrate Colors")
        self.calibrate_colors_btn.clicked.connect(self.calibrate_colors)
        step2_layout.addWidget(self.calibrate_colors_btn)
        step2_layout.addStretch()

        setup_layout.addLayout(step2_layout)

        # Step 3: Telegram Setup
        step3_layout = QHBoxLayout()
        step3_layout.addWidget(QLabel("3. Setup Telegram Alerts:"))

        self.test_telegram_btn = QPushButton("📱 Test Connection")
        self.test_telegram_btn.clicked.connect(self.test_telegram)
        step3_layout.addWidget(self.test_telegram_btn)

        self.send_test_alert_btn = QPushButton("🔔 Send Test Alert")
        self.send_test_alert_btn.clicked.connect(self.send_test_alert)
        step3_layout.addWidget(self.send_test_alert_btn)
        step3_layout.addStretch()

        setup_layout.addLayout(step3_layout)

        # Step 4: Start Detection
        step4_layout = QHBoxLayout()
        step4_layout.addWidget(QLabel("4. Start Detection:"))

        self.detection_btn = QPushButton("🚀 Start Detection")
        self.detection_btn.clicked.connect(self.toggle_detection)
        self.detection_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                font-size: 16px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #218838;
            }
        """)
        step4_layout.addWidget(self.detection_btn)
        step4_layout.addStretch()

        setup_layout.addLayout(step4_layout)
        setup_group.setLayout(setup_layout)
        layout.addWidget(setup_group)

        # Statistics section
        stats_group = QGroupBox("📊 Real-time Statistics")
        stats_layout = QGridLayout(stats_group)

        # Create stat labels
        self.lines_detected_label = QLabel("Lines Detected: 0")
        self.crossovers_total_label = QLabel("Total Crossovers: 0")
        self.crossovers_hour_label = QLabel("Last Hour: 0")
        self.last_detection_label = QLabel("Last Detection: Never")
        self.avg_confidence_label = QLabel("Avg Confidence: 0%")
        self.alerts_sent_label = QLabel("Alerts Sent: 0")

        # Add to grid
        stats_layout.addWidget(self.lines_detected_label, 0, 0)
        stats_layout.addWidget(self.crossovers_total_label, 0, 1)
        stats_layout.addWidget(self.crossovers_hour_label, 1, 0)
        stats_layout.addWidget(self.last_detection_label, 1, 1)
        stats_layout.addWidget(self.avg_confidence_label, 2, 0)
        stats_layout.addWidget(self.alerts_sent_label, 2, 1)

        layout.addWidget(stats_group)

        # Live preview section
        preview_group = QGroupBox("📺 Live Preview")
        preview_layout = QVBoxLayout(preview_group)

        # Image display widget
        self.image_display = ImageDisplayWidget()
        preview_layout.addWidget(self.image_display)

        # Preview controls
        controls_layout = QHBoxLayout()

        self.pause_btn = QPushButton("⏸️ Pause")
        self.pause_btn.clicked.connect(self.pause_detection)
        self.pause_btn.setEnabled(False)
        controls_layout.addWidget(self.pause_btn)

        self.save_screenshot_btn = QPushButton("📷 Save Screenshot")
        self.save_screenshot_btn.clicked.connect(self.save_screenshot)
        controls_layout.addWidget(self.save_screenshot_btn)

        controls_layout.addStretch()

        # Zoom controls
        zoom_out_btn = QPushButton("🔍➖")
        zoom_out_btn.clicked.connect(lambda: self.image_display.wheelEvent(
            type('MockEvent', (), {'angleDelta': lambda: type('MockDelta', (), {'y': lambda: -120})()})()))
        controls_layout.addWidget(zoom_out_btn)

        zoom_in_btn = QPushButton("🔍➕")
        zoom_in_btn.clicked.connect(lambda: self.image_display.wheelEvent(
            type('MockEvent', (), {'angleDelta': lambda: type('MockDelta', (), {'y': lambda: 120})()})()))
        controls_layout.addWidget(zoom_in_btn)

        preview_layout.addLayout(controls_layout)
        layout.addWidget(preview_group)

    def setup_capture_tab(self):
        """Setup capture configuration tab"""
        capture_widget = QWidget()
        self.tabs.addTab(capture_widget, "📸 Capture Setup")

        layout = QVBoxLayout(capture_widget)

        # Window selection
        window_group = QGroupBox("🪟 Window Selection")
        window_layout = QVBoxLayout(window_group)

        # Auto detection
        auto_layout = QHBoxLayout()
        refresh_btn = QPushButton("🔄 Find Windows")
        refresh_btn.clicked.connect(self.refresh_window_list)
        auto_layout.addWidget(refresh_btn)

        self.window_list = QListWidget()
        self.window_list.setMaximumHeight(120)
        auto_layout.addWidget(self.window_list)

        select_window_btn = QPushButton("✅ Select Window")
        select_window_btn.clicked.connect(self.select_window_from_list)
        auto_layout.addWidget(select_window_btn)

        window_layout.addLayout(auto_layout)

        # Manual region
        manual_group = QGroupBox("🎯 Manual Region Selection")
        manual_layout = QGridLayout(manual_group)

        # Region coordinates
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

        apply_region_btn = QPushButton("✅ Apply Region")
        apply_region_btn.clicked.connect(self.apply_manual_region)
        manual_layout.addWidget(apply_region_btn, 0, 4, 2, 1)

        window_layout.addWidget(manual_group)
        layout.addWidget(window_group)

        # Capture settings
        settings_group = QGroupBox("⚙️ Capture Settings")
        settings_layout = QVBoxLayout(settings_group)

        # FPS setting
        fps_layout = QHBoxLayout()
        fps_layout.addWidget(QLabel("Capture FPS:"))

        self.fps_slider = QSlider(Qt.Horizontal)
        self.fps_slider.setRange(1, 50)  # 0.1 to 5.0 FPS (slider * 0.1)
        self.fps_slider.setValue(int(config.get('capture', 'fps', 2) * 10))
        self.fps_slider.valueChanged.connect(self.on_fps_changed)
        fps_layout.addWidget(self.fps_slider)

        self.fps_label = QLabel(f"{config.get('capture', 'fps', 2):.1f}")
        fps_layout.addWidget(self.fps_label)

        settings_layout.addLayout(fps_layout)
        layout.addWidget(settings_group)

        layout.addStretch()

    def setup_colors_tab(self):
        """Setup color configuration tab"""
        colors_widget = QWidget()
        self.tabs.addTab(colors_widget, "🎨 Color Setup")

        # Create scroll area for color configs
        scroll = QScrollArea()
        scroll_widget = QWidget()
        scroll_layout = QVBoxLayout(scroll_widget)

        # Instructions
        instructions = QLabel("""
        <h3>🎨 Color Configuration Instructions</h3>
        <ul>
        <li>📊 Make sure your ZigZag indicators are visible on the chart</li>
        <li>🎯 Use 'Calibrate' to automatically detect color ranges</li>
        <li>⚙️ Or manually adjust the HSV sliders below</li>
        <li>🧪 Test detection to verify colors are working</li>
        </ul>
        """)
        instructions.setStyleSheet("background-color: #3a3a3a; padding: 15px; border-radius: 8px;")
        scroll_layout.addWidget(instructions)

        # Color configuration widgets
        self.color_widgets = {}
        for line_name, color_config in config.config['colors'].items():
            color_widget = ColorConfigWidget(line_name, color_config)
            self.color_widgets[line_name] = color_widget
            scroll_layout.addWidget(color_widget)

        scroll_layout.addStretch()
        scroll.setWidget(scroll_widget)
        scroll.setWidgetResizable(True)

        layout = QVBoxLayout(colors_widget)
        layout.addWidget(scroll)

    def setup_detection_tab(self):
        """Setup detection configuration tab"""
        detection_widget = QWidget()
        self.tabs.addTab(detection_widget, "🔍 Detection Settings")

        layout = QVBoxLayout(detection_widget)

        # Detection parameters
        params_group = QGroupBox("⚙️ Detection Parameters")
        params_layout = QVBoxLayout(params_group)

        # Min line length
        length_layout = QHBoxLayout()
        length_layout.addWidget(QLabel("Minimum Line Length:"))

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
        conf_layout.addWidget(QLabel("Confidence Threshold:"))

        self.confidence_slider = QSlider(Qt.Horizontal)
        self.confidence_slider.setRange(10, 100)  # 0.1 to 1.0 (slider / 100)
        self.confidence_slider.setValue(int(config.get('detection', 'confidence_threshold', 0.7) * 100))
        self.confidence_slider.valueChanged.connect(self.on_confidence_changed)
        conf_layout.addWidget(self.confidence_slider)

        self.confidence_label = QLabel(f"{self.confidence_slider.value() / 100:.2f}")
        conf_layout.addWidget(self.confidence_label)

        params_layout.addLayout(conf_layout)

        # Intersection tolerance
        tolerance_layout = QHBoxLayout()
        tolerance_layout.addWidget(QLabel("Intersection Tolerance:"))

        self.tolerance_slider = QSlider(Qt.Horizontal)
        self.tolerance_slider.setRange(1, 20)
        self.tolerance_slider.setValue(config.get('detection', 'intersection_tolerance', 8))
        self.tolerance_slider.valueChanged.connect(self.on_tolerance_changed)
        tolerance_layout.addWidget(self.tolerance_slider)

        self.tolerance_label = QLabel(str(self.tolerance_slider.value()))
        tolerance_layout.addWidget(self.tolerance_label)

        params_layout.addLayout(tolerance_layout)

        # Debounce time
        debounce_layout = QHBoxLayout()
        debounce_layout.addWidget(QLabel("Debounce Time (seconds):"))

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

        # Telegram configuration
        telegram_group = QGroupBox("📱 Telegram Configuration")
        telegram_layout = QVBoxLayout(telegram_group)

        # Enable checkbox
        self.telegram_enabled = QCheckBox("Enable Telegram Alerts")
        self.telegram_enabled.setChecked(config.get('alerts', 'telegram_enabled', True))
        telegram_layout.addWidget(self.telegram_enabled)

        # Token entry
        token_layout = QHBoxLayout()
        token_layout.addWidget(QLabel("Bot Token:"))
        self.token_input = QLineEdit()
        self.token_input.setEchoMode(QLineEdit.Password)
        self.token_input.setText(config.get('alerts', 'telegram_token', ''))
        self.token_input.setPlaceholderText("Enter your Telegram bot token...")
        token_layout.addWidget(self.token_input)

        help_btn = QPushButton("❓ Help")
        help_btn.clicked.connect(self.show_telegram_help)
        token_layout.addWidget(help_btn)

        telegram_layout.addLayout(token_layout)

        # Chat ID entry
        chat_layout = QHBoxLayout()
        chat_layout.addWidget(QLabel("Chat ID:"))
        self.chat_id_input = QLineEdit()
        self.chat_id_input.setText(config.get('alerts', 'telegram_chat_id', ''))
        self.chat_id_input.setPlaceholderText("Enter your chat ID...")
        chat_layout.addWidget(self.chat_id_input)
        telegram_layout.addLayout(chat_layout)

        # Test buttons
        test_layout = QHBoxLayout()
        test_conn_btn = QPushButton("🔗 Test Connection")
        test_conn_btn.clicked.connect(self.test_telegram)
        test_layout.addWidget(test_conn_btn)

        send_test_btn = QPushButton("💬 Send Test Alert")
        send_test_btn.clicked.connect(self.send_test_alert)
        test_layout.addWidget(send_test_btn)
        test_layout.addStretch()

        telegram_layout.addLayout(test_layout)

        # Cooldown setting
        cooldown_layout = QHBoxLayout()
        cooldown_layout.addWidget(QLabel("Alert Cooldown (seconds):"))

        self.cooldown_slider = QSlider(Qt.Horizontal)
        self.cooldown_slider.setRange(60, 3600)
        self.cooldown_slider.setValue(config.get('alerts', 'cooldown_seconds', 300))
        self.cooldown_slider.valueChanged.connect(self.on_cooldown_changed)
        cooldown_layout.addWidget(self.cooldown_slider)

        self.cooldown_label = QLabel(str(self.cooldown_slider.value()))
        cooldown_layout.addWidget(self.cooldown_label)

        telegram_layout.addLayout(cooldown_layout)
        layout.addWidget(telegram_group)

        # Other alerts
        other_group = QGroupBox("🔔 Other Alert Options")
        other_layout = QVBoxLayout(other_group)

        self.sound_enabled = QCheckBox("🔊 Sound Alerts")
        self.sound_enabled.setChecked(config.get('alerts', 'sound_enabled', True))
        other_layout.addWidget(self.sound_enabled)

        self.popup_enabled = QCheckBox("🪟 Popup Alerts")
        self.popup_enabled.setChecked(config.get('alerts', 'popup_enabled', False))
        other_layout.addWidget(self.popup_enabled)

        self.log_enabled = QCheckBox("📝 Log to File")
        self.log_enabled.setChecked(config.get('alerts', 'log_file_enabled', True))
        other_layout.addWidget(self.log_enabled)

        layout.addWidget(other_group)

        # Save button
        save_btn = QPushButton("💾 Save Alert Settings")
        save_btn.clicked.connect(self.save_alert_settings)
        save_btn.setStyleSheet("""
            QPushButton {
                background-color: #28a745;
                font-size: 14px;
                padding: 10px 20px;
            }
        """)
        layout.addWidget(save_btn)

        layout.addStretch()

    def setup_logs_tab(self):
        """Setup logs and diagnostics tab"""
        logs_widget = QWidget()
        self.tabs.addTab(logs_widget, "📝 Logs & Diagnostics")

        layout = QVBoxLayout(logs_widget)

        # Log display
        log_group = QGroupBox("📄 Application Log")
        log_layout = QVBoxLayout(log_group)

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
        log_layout.addWidget(self.log_text)

        # Log controls
        log_controls = QHBoxLayout()

        clear_log_btn = QPushButton("🗑️ Clear Log")
        clear_log_btn.clicked.connect(self.clear_log)
        log_controls.addWidget(clear_log_btn)

        save_log_btn = QPushButton("💾 Save Log")
        save_log_btn.clicked.connect(self.save_log)
        log_controls.addWidget(save_log_btn)

        open_folder_btn = QPushButton("📁 Open Log Folder")
        open_folder_btn.clicked.connect(self.open_log_folder)
        log_controls.addWidget(open_folder_btn)

        log_controls.addStretch()
        log_layout.addLayout(log_controls)
        layout.addWidget(log_group)

        # Diagnostics
        diag_group = QGroupBox("🔧 Diagnostics")
        diag_layout = QHBoxLayout(diag_group)

        system_info_btn = QPushButton("💻 System Info")
        system_info_btn.clicked.connect(self.show_system_info)
        diag_layout.addWidget(system_info_btn)

        export_config_btn = QPushButton("📤 Export Config")
        export_config_btn.clicked.connect(self.export_config)
        diag_layout.addWidget(export_config_btn)

        import_config_btn = QPushButton("📥 Import Config")
        import_config_btn.clicked.connect(self.import_config)
        diag_layout.addWidget(import_config_btn)

        diag_layout.addStretch()
        layout.addWidget(diag_group)

    def setup_connections(self):
        """Setup signal connections"""
        pass  # Connections are set up in individual methods

    def load_settings(self):
        """Load settings into GUI"""
        try:
            # Update controls with current config values
            self.fps_slider.setValue(int(config.get('capture', 'fps', 2) * 10))
            self.min_length_slider.setValue(config.get('detection', 'min_line_length', 30))
            self.confidence_slider.setValue(int(config.get('detection', 'confidence_threshold', 0.7) * 100))
            self.tolerance_slider.setValue(config.get('detection', 'intersection_tolerance', 8))
            self.debounce_slider.setValue(config.get('detection', 'debounce_seconds', 60))

            self.telegram_enabled.setChecked(config.get('alerts', 'telegram_enabled', True))
            self.token_input.setText(config.get('alerts', 'telegram_token', ''))
            self.chat_id_input.setText(config.get('alerts', 'telegram_chat_id', ''))
            self.cooldown_slider.setValue(config.get('alerts', 'cooldown_seconds', 300))

            self.sound_enabled.setChecked(config.get('alerts', 'sound_enabled', True))
            self.popup_enabled.setChecked(config.get('alerts', 'popup_enabled', False))
            self.log_enabled.setChecked(config.get('alerts', 'log_file_enabled', True))

        except Exception as e:
            logging.error(f"Failed to load settings: {e}")

    # Event handlers (implement the methods referenced in the UI setup)
    def auto_detect_window(self):
        window = self.window_capture.auto_detect_window()
        if window:
            self.window_status_label.setText(f"✅ {window.title}")
            self.window_status_label.setStyleSheet("color: #51cf66;")
            self.log_message(f"Window detected: {window.title}")
        else:
            self.window_status_label.setText("❌ No window found")
            self.window_status_label.setStyleSheet("color: #ff6b6b;")
            QMessageBox.warning(self, "Detection Failed",
                                "Could not auto-detect PocketOption window.\n"
                                "Please use manual selection.")

    def manual_select_region(self):
        self.log_message("Starting manual region selection...")
        # Implementation for region selection
        QMessageBox.information(self, "Manual Selection", "Manual region selection will be implemented!")

    def test_capture(self):
        success, message = self.window_capture.test_capture()
        if success:
            QMessageBox.information(self, "Capture Test", f"✅ {message}")
            self.log_message(f"Capture test successful: {message}")
        else:
            QMessageBox.critical(self, "Capture Test", f"❌ {message}")
            self.log_message(f"Capture test failed: {message}")

    def calibrate_colors(self):
        QMessageBox.information(self, "Color Calibration", "Color calibration wizard will be implemented!")

    def test_telegram(self):
        # Update config with current values
        config.set('alerts', 'telegram_token', self.token_input.text())
        config.set('alerts', 'telegram_chat_id', self.chat_id_input.text())

        success, message = self.alert_manager.telegram.test_connection()
        if success:
            QMessageBox.information(self, "Telegram Test", f"✅ {message}")
            self.log_message(f"Telegram test successful: {message}")
        else:
            QMessageBox.critical(self, "Telegram Test", f"❌ {message}")
            self.log_message(f"Telegram test failed: {message}")

    def send_test_alert(self):
        QMessageBox.information(self, "Test Alert", "Test alert functionality will be implemented!")

    def toggle_detection(self):
        if self.detection_worker is None or not self.detection_worker.isRunning():
            self.start_detection()
        else:
            self.stop_detection()

    def start_detection(self):
        """Start detection in worker thread"""
        if not self.validate_setup():
            return

        # Create and start worker
        self.detection_worker = DetectionWorker(
            self.window_capture, self.color_detector,
            self.crossover_detector, self.alert_manager
        )

        # Connect signals
        self.detection_worker.image_ready.connect(self.on_image_ready)
        self.detection_worker.lines_detected.connect(self.on_lines_detected)
        self.detection_worker.crossover_detected.connect(self.on_crossover_detected)
        self.detection_worker.error_occurred.connect(self.on_error_occurred)
        self.detection_worker.status_update.connect(self.on_status_update)

        self.detection_worker.start()

        # Update UI
        self.detection_btn.setText("⏹️ Stop Detection")
        self.detection_btn.setStyleSheet("""
            QPushButton {
                background-color: #dc3545;
                font-size: 16px;
                padding: 12px 24px;
            }
            QPushButton:hover {
                background-color: #c82333;
            }
        """)
        self.pause_btn.setEnabled(True)

        self.statusBar().showMessage("🔍 Detection running...")
        self.log_message("🚀 Detection started")

    def stop_detection(self):
        """Stop detection worker"""
        if self.detection_worker and self.detection_worker.isRunning():
            self.detection_worker.stop()

            # Update UI
            self.detection_btn.setText("🚀 Start Detection")
            self.detection_btn.setStyleSheet("""
                QPushButton {
                    background-color: #28a745;
                    font-size: 16px;
                    padding: 12px 24px;
                }
                QPushButton:hover {
                    background-color: #218838;
                }
            """)
            self.pause_btn.setEnabled(False)

            self.statusBar().showMessage("⏹️ Detection stopped")
            self.log_message("⏹️ Detection stopped")

    def pause_detection(self):
        """Pause/resume detection"""
        if self.detection_worker and self.detection_worker.isRunning():
            if self.detection_worker.paused:
                self.detection_worker.resume()
                self.pause_btn.setText("⏸️ Pause")
                self.statusBar().showMessage("🔍 Detection resumed")
            else:
                self.detection_worker.pause()
                self.pause_btn.setText("▶️ Resume")
                self.statusBar().showMessage("⏸️ Detection paused")

    def validate_setup(self):
        """Validate setup before starting detection"""
        # Check window/region
        capture_info = self.window_capture.get_capture_info()
        if not capture_info['valid']:
            QMessageBox.critical(self, "Setup Error",
                                 "No valid capture region configured.\n"
                                 "Please detect a window or select a region.")
            return False

        # Check colors
        enabled_colors = sum(1 for color_config in config.config['colors'].values()
                             if color_config.get('enabled', True))
        if enabled_colors < 2:
            QMessageBox.critical(self, "Setup Error",
                                 "At least 2 color lines must be enabled for crossover detection.")
            return False

        return True

    # Signal handlers
    def on_image_ready(self, image):
        """Handle new image from detection worker"""
        self.image_display.update_image(image, self.detected_lines, self.detected_crossovers)

    def on_lines_detected(self, lines):
        """Handle lines detection result"""
        self.detected_lines = lines
        self.lines_detected_label.setText(f"Lines Detected: {len(lines)}")

    def on_crossover_detected(self, crossover):
        """Handle crossover detection"""
        self.detected_crossovers.append(crossover)

        # Update stats
        total = len(self.detected_crossovers)
        self.crossovers_total_label.setText(f"Total Crossovers: {total}")

        # Update last detection time
        time_str = datetime.fromtimestamp(crossover.timestamp).strftime("%H:%M:%S")
        self.last_detection_label.setText(f"Last Detection: {time_str}")

        self.log_message(f"🎯 Crossover detected: {crossover.line1_name} × {crossover.line2_name}")

    def on_error_occurred(self, error_msg):
        """Handle error from detection worker"""
        self.log_message(f"❌ Error: {error_msg}")

    def on_status_update(self, status_msg):
        """Handle status update from detection worker"""
        self.statusBar().showMessage(status_msg)

    # Slider change handlers
    def on_fps_changed(self, value):
        fps = value / 10.0
        self.fps_label.setText(f"{fps:.1f}")
        config.set('capture', 'fps', fps)

    def on_min_length_changed(self, value):
        self.min_length_label.setText(str(value))
        config.set('detection', 'min_line_length', value)

    def on_confidence_changed(self, value):
        confidence = value / 100.0
        self.confidence_label.setText(f"{confidence:.2f}")
        config.set('detection', 'confidence_threshold', confidence)

    def on_tolerance_changed(self, value):
        self.tolerance_label.setText(str(value))
        config.set('detection', 'intersection_tolerance', value)

    def on_debounce_changed(self, value):
        self.debounce_label.setText(str(value))
        config.set('detection', 'debounce_seconds', value)

    def on_cooldown_changed(self, value):
        self.cooldown_label.setText(str(value))
        config.set('alerts', 'cooldown_seconds', value)

    # Utility methods
    def log_message(self, message):
        """Add message to log display"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_entry = f"[{timestamp}] {message}"

        self.log_text.append(log_entry)

        # Keep only last 1000 lines
        if self.log_text.document().blockCount() > 1000:
            cursor = self.log_text.textCursor()
            cursor.movePosition(QTextCursor.Start)
            cursor.movePosition(QTextCursor.Down, QTextCursor.KeepAnchor, 100)
            cursor.removeSelectedText()

    def update_status(self):
        """Update uptime and stats"""
        # Update uptime
        uptime_seconds = int(time.time() - self.start_time)
        hours = uptime_seconds // 3600
        minutes = (uptime_seconds % 3600) // 60
        seconds = uptime_seconds % 60

        self.uptime_label.setText(f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}")

        # Update stats
        if self.detected_crossovers:
            current_time = time.time()
            recent_crossovers = sum(1 for c in self.detected_crossovers
                                    if current_time - c.timestamp < 3600)
            self.crossovers_hour_label.setText(f"Last Hour: {recent_crossovers}")

    def save_alert_settings(self):
        """Save alert settings to config"""
        try:
            config.set('alerts', 'telegram_enabled', self.telegram_enabled.isChecked())
            config.set('alerts', 'telegram_token', self.token_input.text())
            config.set('alerts', 'telegram_chat_id', self.chat_id_input.text())
            config.set('alerts', 'cooldown_seconds', self.cooldown_slider.value())
            config.set('alerts', 'sound_enabled', self.sound_enabled.isChecked())
            config.set('alerts', 'popup_enabled', self.popup_enabled.isChecked())
            config.set('alerts', 'log_file_enabled', self.log_enabled.isChecked())

            config.save_config()
            QMessageBox.information(self, "Settings Saved", "✅ Alert settings saved successfully!")
            self.log_message("💾 Alert settings saved")

        except Exception as e:
            QMessageBox.critical(self, "Save Error", f"❌ Failed to save settings: {e}")

    def refresh_window_list(self):
        """Refresh the window list"""
        windows = self.window_capture.find_windows()
        self.window_list.clear()
        for window in windows:
            self.window_list.addItem(
                f"{window.title} ({window.rect[2] - window.rect[0]}x{window.rect[3] - window.rect[1]})")

    def select_window_from_list(self):
        """Select window from list"""
        current_row = self.window_list.currentRow()
        if current_row >= 0:
            windows = self.window_capture.find_windows()
            if current_row < len(windows):
                selected_window = windows[current_row]
                self.window_capture.set_target_window(selected_window)
                self.window_status_label.setText(f"✅ {selected_window.title}")
                self.window_status_label.setStyleSheet("color: #51cf66;")
                self.log_message(f"Window selected: {selected_window.title}")

    def apply_manual_region(self):
        """Apply manual region coordinates"""
        region = {
            'left': self.region_left.value(),
            'top': self.region_top.value(),
            'width': self.region_width.value(),
            'height': self.region_height.value()
        }

        self.window_capture.set_custom_region(region)
        self.window_status_label.setText(f"✅ Custom region: {region['width']}x{region['height']}")
        self.window_status_label.setStyleSheet("color: #51cf66;")
        self.log_message(f"Custom region applied: {region}")

    def save_screenshot(self):
        """Save current screenshot"""
        if hasattr(self.image_display, 'current_pixmap') and self.image_display.current_pixmap:
            filename, _ = QFileDialog.getSaveFileName(
                self, "Save Screenshot", f"zigzag_screenshot_{int(time.time())}.png",
                "PNG Files (*.png);;JPEG Files (*.jpg)"
            )
            if filename:
                self.image_display.current_pixmap.save(filename)
                QMessageBox.information(self, "Screenshot Saved", f"✅ Screenshot saved to:\n{filename}")
        else:
            QMessageBox.warning(self, "No Image", "No image to save. Start detection first.")

    def show_telegram_help(self):
        """Show Telegram setup help"""
        help_text = """
        <h3>🤖 Telegram Bot Setup Guide</h3>

        <p><b>Step 1: Create a Bot</b></p>
        <ol>
        <li>Open Telegram and search for <code>@BotFather</code></li>
        <li>Send <code>/newbot</code> command</li>
        <li>Follow the instructions to create your bot</li>
        <li>Copy the bot token (looks like: <code>123456:ABC-DEF1234ghIkl-zyx57W2v1u123ew11</code>)</li>
        </ol>

        <p><b>Step 2: Get Your Chat ID</b></p>
        <ol>
        <li>Send a message to your bot</li>
        <li>Visit: <code>https://api.telegram.org/bot&lt;YOUR_BOT_TOKEN&gt;/getUpdates</code></li>
        <li>Find your chat ID in the response (usually a number like <code>123456789</code>)</li>
        </ol>

        <p><b>Step 3: Test Connection</b></p>
        <ol>
        <li>Enter your bot token and chat ID above</li>
        <li>Click 'Test Connection' to verify setup</li>
        <li>Send a test alert to confirm everything works</li>
        </ol>
        """

        QMessageBox.information(self, "Telegram Setup Help", help_text)

    def clear_log(self):
        """Clear the log display"""
        self.log_text.clear()
        self.log_message("📝 Log cleared")

    def save_log(self):
        """Save log to file"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Save Log", f"zigzag_log_{int(time.time())}.txt",
            "Text Files (*.txt);;All Files (*)"
        )
        if filename:
            try:
                with open(filename, 'w') as f:
                    f.write(self.log_text.toPlainText())
                QMessageBox.information(self, "Log Saved", f"✅ Log saved to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Save Error", f"❌ Failed to save log: {e}")

    def open_log_folder(self):
        """Open log folder in file explorer"""
        import os
        import subprocess

        log_dir = Path("logs")
        if log_dir.exists():
            if sys.platform == "win32":
                os.startfile(log_dir)
            elif sys.platform == "darwin":
                subprocess.run(["open", log_dir])
            else:
                subprocess.run(["xdg-open", log_dir])
        else:
            QMessageBox.warning(self, "Folder Not Found", "Logs folder does not exist yet.")

    def show_system_info(self):
        """Show system information dialog"""
        import platform

        info = f"""
        <h3>💻 System Information</h3>
        <table>
        <tr><td><b>OS:</b></td><td>{platform.system()} {platform.release()}</td></tr>
        <tr><td><b>Python:</b></td><td>{sys.version.split()[0]}</td></tr>
        <tr><td><b>PySide6:</b></td><td>{PySide6.__version__}</td></tr>
        <tr><td><b>Working Dir:</b></td><td>{Path.cwd()}</td></tr>
        <tr><td><b>Config File:</b></td><td>{Path('config.json').absolute()}</td></tr>
        </table>
        """

        QMessageBox.information(self, "System Information", info)

    def export_config(self):
        """Export configuration"""
        filename, _ = QFileDialog.getSaveFileName(
            self, "Export Configuration", f"zigzag_config_{int(time.time())}.json",
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                import shutil
                shutil.copy("config.json", filename)
                QMessageBox.information(self, "Config Exported", f"✅ Configuration exported to:\n{filename}")
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"❌ Failed to export config: {e}")

    def import_config(self):
        """Import configuration"""
        filename, _ = QFileDialog.getOpenFileName(
            self, "Import Configuration", "",
            "JSON Files (*.json);;All Files (*)"
        )
        if filename:
            try:
                import shutil
                shutil.copy(filename, "config.json")
                QMessageBox.information(self, "Config Imported",
                                        "✅ Configuration imported successfully!\n"
                                        "Please restart the application to apply changes.")
            except Exception as e:
                QMessageBox.critical(self, "Import Error", f"❌ Failed to import config: {e}")

    def closeEvent(self, event):
        """Handle application closing"""
        try:
            # Stop detection worker
            if self.detection_worker and self.detection_worker.isRunning():
                self.detection_worker.stop()

            # Stop alert manager
            self.alert_manager.telegram.stop_worker()

            # Save configuration
            config.save_config()

            self.log_message("👋 Application shutting down...")
            event.accept()

        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
            event.accept()

    def run(self):
        """Run the application"""
        self.show()
        self.log_message("🎯 ZigZag Crossover Detector v2.0 started")
        self.log_message("📋 Follow the Quick Setup steps to get started")


def create_app():
    """Create and configure the QApplication"""
    app = QApplication(sys.argv)
    app.setApplicationName("ZigZag Crossover Detector")
    app.setApplicationVersion("2.0")
    app.setOrganizationName("Trading Tools")

    # Set application icon if available
    icon_path = Path("icon.ico")
    if icon_path.exists():
        app.setWindowIcon(QIcon(str(icon_path)))

    return app