"""
Main GUI window for ZigZag Detector
User-friendly interface with comprehensive configuration
"""

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading
import time
import logging
from datetime import datetime
import cv2
import numpy as np
from PIL import Image, ImageTk
import webbrowser
import os

from ..config.settings import config
from ..capture.window_capture import WindowCapture, RegionSelector
from ..detection.color_detector import ColorDetector, ColorCalibrator
from ..detection.crossover_detector import CrossoverDetector, CrossoverVisualizer
from ..alerts.telegram_alerter import AlertManager


class ZigZagDetectorApp:
    """Main application GUI"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("ZigZag Crossover Detector v1.0")
        self.root.geometry("1400x900")

        # Initialize components
        self.window_capture = WindowCapture()
        self.color_detector = ColorDetector(config)
        self.crossover_detector = CrossoverDetector(config)
        self.alert_manager = AlertManager(config)

        # State variables
        self.detection_running = False
        self.detection_thread = None
        self.current_image = None
        self.detected_lines = []
        self.detected_crossovers = []
        self.start_time = time.time()

        # Setup GUI
        self.setup_gui()
        self.load_settings()

        # Start alert manager
        self.alert_manager.telegram.start_worker()

        # Bind close event
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)

    def setup_gui(self):
        """Setup the main GUI layout"""
        # Create notebook for tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Create tabs
        self.setup_main_tab()
        self.setup_capture_tab()
        self.setup_colors_tab()
        self.setup_detection_tab()
        self.setup_alerts_tab()
        self.setup_logs_tab()

        # Status bar
        self.status_frame = ttk.Frame(self.root)
        self.status_frame.pack(fill=tk.X, padx=10, pady=(0, 10))

        self.status_label = ttk.Label(self.status_frame, text="Ready")
        self.status_label.pack(side=tk.LEFT)

        self.uptime_label = ttk.Label(self.status_frame, text="Uptime: 0:00:00")
        self.uptime_label.pack(side=tk.RIGHT)

        # Start uptime counter
        self.update_uptime()

    def setup_main_tab(self):
        """Setup main control tab"""
        main_frame = ttk.Frame(self.notebook)
        self.notebook.add(main_frame, text="Main Control")

        # Quick setup frame
        setup_frame = ttk.LabelFrame(main_frame, text="Quick Setup")
        setup_frame.pack(fill=tk.X, padx=10, pady=10)

        # Step 1: Window Detection
        step1_frame = ttk.Frame(setup_frame)
        step1_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(step1_frame, text="1. Detect PocketOption Window:",
                  font=('Arial', 10, 'bold')).pack(side=tk.LEFT)

        ttk.Button(step1_frame, text="Auto Detect",
                   command=self.auto_detect_window).pack(side=tk.LEFT, padx=5)
        ttk.Button(step1_frame, text="Manual Select",
                   command=self.manual_select_region).pack(side=tk.LEFT, padx=5)

        self.window_status_label = ttk.Label(step1_frame, text="No window selected",
                                             foreground="red")
        self.window_status_label.pack(side=tk.LEFT, padx=10)

        # Step 2: Test Capture
        step2_frame = ttk.Frame(setup_frame)
        step2_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(step2_frame, text="2. Test Screen Capture:",
                  font=('Arial', 10, 'bold')).pack(side=tk.LEFT)

        ttk.Button(step2_frame, text="Test Capture",
                   command=self.test_capture).pack(side=tk.LEFT, padx=5)
        ttk.Button(step2_frame, text="Calibrate Colors",
                   command=self.calibrate_colors).pack(side=tk.LEFT, padx=5)

        # Step 3: Telegram Setup
        step3_frame = ttk.Frame(setup_frame)
        step3_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(step3_frame, text="3. Setup Telegram Alerts:",
                  font=('Arial', 10, 'bold')).pack(side=tk.LEFT)

        ttk.Button(step3_frame, text="Test Connection",
                   command=self.test_telegram).pack(side=tk.LEFT, padx=5)
        ttk.Button(step3_frame, text="Send Test Alert",
                   command=self.send_test_alert).pack(side=tk.LEFT, padx=5)

        # Step 4: Start Detection
        step4_frame = ttk.Frame(setup_frame)
        step4_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(step4_frame, text="4. Start Detection:",
                  font=('Arial', 10, 'bold')).pack(side=tk.LEFT)

        self.detection_button = ttk.Button(step4_frame, text="Start Detection",
                                           command=self.toggle_detection)
        self.detection_button.pack(side=tk.LEFT, padx=5)

        # Statistics frame
        stats_frame = ttk.LabelFrame(main_frame, text="Real-time Statistics")
        stats_frame.pack(fill=tk.X, padx=10, pady=10)

        # Stats grid
        stats_grid = ttk.Frame(stats_frame)
        stats_grid.pack(fill=tk.X, padx=5, pady=5)

        # Left column
        left_stats = ttk.Frame(stats_grid)
        left_stats.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.lines_detected_label = ttk.Label(left_stats, text="Lines Detected: 0")
        self.lines_detected_label.pack(anchor=tk.W)

        self.crossovers_total_label = ttk.Label(left_stats, text="Total Crossovers: 0")
        self.crossovers_total_label.pack(anchor=tk.W)

        self.crossovers_hour_label = ttk.Label(left_stats, text="Last Hour: 0")
        self.crossovers_hour_label.pack(anchor=tk.W)

        # Right column
        right_stats = ttk.Frame(stats_grid)
        right_stats.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)

        self.last_detection_label = ttk.Label(right_stats, text="Last Detection: Never")
        self.last_detection_label.pack(anchor=tk.W)

        self.avg_confidence_label = ttk.Label(right_stats, text="Avg Confidence: 0%")
        self.avg_confidence_label.pack(anchor=tk.W)

        self.alerts_sent_label = ttk.Label(right_stats, text="Alerts Sent: 0")
        self.alerts_sent_label.pack(anchor=tk.W)

        # Live preview frame
        preview_frame = ttk.LabelFrame(main_frame, text="Live Preview")
        preview_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Canvas for image display
        self.canvas = tk.Canvas(preview_frame, bg='black', width=800, height=400)

        # Scrollbars
        h_scroll = ttk.Scrollbar(preview_frame, orient=tk.HORIZONTAL, command=self.canvas.xview)
        v_scroll = ttk.Scrollbar(preview_frame, orient=tk.VERTICAL, command=self.canvas.yview)

        self.canvas.configure(xscrollcommand=h_scroll.set, yscrollcommand=v_scroll.set)

        # Grid layout
        self.canvas.grid(row=0, column=0, sticky="nsew")
        h_scroll.grid(row=1, column=0, sticky="ew")
        v_scroll.grid(row=0, column=1, sticky="ns")

        preview_frame.grid_rowconfigure(0, weight=1)
        preview_frame.grid_columnconfigure(0, weight=1)

        # Update statistics periodically
        self.update_statistics()

    def setup_capture_tab(self):
        """Setup capture configuration tab"""
        capture_frame = ttk.Frame(self.notebook)
        self.notebook.add(capture_frame, text="Capture Setup")

        # Window selection frame
        window_frame = ttk.LabelFrame(capture_frame, text="Window Selection")
        window_frame.pack(fill=tk.X, padx=10, pady=10)

        # Auto detection
        auto_frame = ttk.Frame(window_frame)
        auto_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(auto_frame, text="Find Windows",
                   command=self.refresh_window_list).pack(side=tk.LEFT)

        self.window_listbox = tk.Listbox(auto_frame, height=5)
        self.window_listbox.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=10)

        ttk.Button(auto_frame, text="Select Window",
                   command=self.select_window_from_list).pack(side=tk.RIGHT)

        # Manual region frame
        manual_frame = ttk.LabelFrame(capture_frame, text="Manual Region Selection")
        manual_frame.pack(fill=tk.X, padx=10, pady=10)

        # Region coordinates
        coords_frame = ttk.Frame(manual_frame)
        coords_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(coords_frame, text="Left:").grid(row=0, column=0, padx=5)
        self.region_left = tk.IntVar(value=100)
        ttk.Entry(coords_frame, textvariable=self.region_left, width=10).grid(row=0, column=1, padx=5)

        ttk.Label(coords_frame, text="Top:").grid(row=0, column=2, padx=5)
        self.region_top = tk.IntVar(value=100)
        ttk.Entry(coords_frame, textvariable=self.region_top, width=10).grid(row=0, column=3, padx=5)

        ttk.Label(coords_frame, text="Width:").grid(row=1, column=0, padx=5)
        self.region_width = tk.IntVar(value=1200)
        ttk.Entry(coords_frame, textvariable=self.region_width, width=10).grid(row=1, column=1, padx=5)

        ttk.Label(coords_frame, text="Height:").grid(row=1, column=2, padx=5)
        self.region_height = tk.IntVar(value=800)
        ttk.Entry(coords_frame, textvariable=self.region_height, width=10).grid(row=1, column=3, padx=5)

        ttk.Button(coords_frame, text="Apply Region",
                   command=self.apply_manual_region).grid(row=0, column=4, rowspan=2, padx=10)

        # Capture settings frame
        settings_frame = ttk.LabelFrame(capture_frame, text="Capture Settings")
        settings_frame.pack(fill=tk.X, padx=10, pady=10)

        # FPS setting
        fps_frame = ttk.Frame(settings_frame)
        fps_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(fps_frame, text="Capture FPS:").pack(side=tk.LEFT)
        self.fps_var = tk.DoubleVar(value=config.get('capture', 'fps', 2))
        fps_scale = ttk.Scale(fps_frame, from_=0.5, to=5.0, variable=self.fps_var,
                              orient=tk.HORIZONTAL, length=200)
        fps_scale.pack(side=tk.LEFT, padx=10)
        self.fps_label = ttk.Label(fps_frame, text="2.0")
        self.fps_label.pack(side=tk.LEFT, padx=5)

        def update_fps_label(value):
            self.fps_label.config(text=f"{float(value):.1f}")
            config.set('capture', 'fps', float(value))

        fps_scale.configure(command=update_fps_label)

    def setup_colors_tab(self):
        """Setup color configuration tab"""
        colors_frame = ttk.Frame(self.notebook)
        self.notebook.add(colors_frame, text="Color Setup")

        # Instructions
        inst_frame = ttk.LabelFrame(colors_frame, text="Instructions")
        inst_frame.pack(fill=tk.X, padx=10, pady=10)

        instructions = [
            "1. Make sure your ZigZag indicators are visible on the chart",
            "2. Use 'Calibrate Colors' to automatically detect color ranges",
            "3. Or manually adjust the HSV sliders below",
            "4. Test detection to verify colors are working"
        ]

        for instruction in instructions:
            ttk.Label(inst_frame, text=instruction).pack(anchor=tk.W, padx=5, pady=2)

        # Color configuration for each line
        self.color_frames = {}

        for line_name, color_config in config.config['colors'].items():
            self.setup_color_frame(colors_frame, line_name, color_config)

    def setup_color_frame(self, parent, line_name, color_config):
        """Setup color configuration frame for a line"""
        frame = ttk.LabelFrame(parent, text=color_config.get('name', line_name))
        frame.pack(fill=tk.X, padx=10, pady=5)

        # Enable checkbox
        enabled_var = tk.BoolVar(value=color_config.get('enabled', True))
        ttk.Checkbutton(frame, text="Enable Detection",
                        variable=enabled_var).pack(anchor=tk.W, padx=5, pady=5)

        # HSV sliders
        sliders_frame = ttk.Frame(frame)
        sliders_frame.pack(fill=tk.X, padx=5, pady=5)

        # Store variables
        vars_dict = {}

        # Create sliders for each HSV parameter
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
            col = (i % 2) * 3

            ttk.Label(sliders_frame, text=label).grid(row=row, column=col, padx=5, sticky=tk.W)

            var = tk.IntVar(value=color_config.get(param, min_val))
            vars_dict[param] = var

            scale = ttk.Scale(sliders_frame, from_=min_val, to=max_val,
                              variable=var, orient=tk.HORIZONTAL, length=150)
            scale.grid(row=row, column=col + 1, padx=5)

            value_label = ttk.Label(sliders_frame, text=str(var.get()))
            value_label.grid(row=row, column=col + 2, padx=5)

            # Update callback
            def update_value(value, label_widget=value_label, param_name=param,
                             line_name=line_name, var=var):
                label_widget.config(text=str(int(float(value))))
                config.set_color_config(line_name, {
                    **config.get_color_config(line_name),
                    param_name: int(float(value))
                })

            scale.configure(command=update_value)

        # Buttons
        buttons_frame = ttk.Frame(frame)
        buttons_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(buttons_frame, text="Calibrate",
                   command=lambda: self.calibrate_single_color(line_name)).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Test Detection",
                   command=lambda: self.test_color_detection(line_name)).pack(side=tk.LEFT, padx=5)
        ttk.Button(buttons_frame, text="Reset",
                   command=lambda: self.reset_color_config(line_name)).pack(side=tk.RIGHT, padx=5)

        # Store references
        self.color_frames[line_name] = {
            'frame': frame,
            'enabled': enabled_var,
            'vars': vars_dict
        }

    def setup_detection_tab(self):
        """Setup detection configuration tab"""
        detection_frame = ttk.Frame(self.notebook)
        self.notebook.add(detection_frame, text="Detection Settings")

        # Detection parameters
        params_frame = ttk.LabelFrame(detection_frame, text="Detection Parameters")
        params_frame.pack(fill=tk.X, padx=10, pady=10)

        # Min line length
        length_frame = ttk.Frame(params_frame)
        length_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(length_frame, text="Minimum Line Length:").pack(side=tk.LEFT)
        self.min_length_var = tk.IntVar(value=config.get('detection', 'min_line_length', 30))
        ttk.Scale(length_frame, from_=10, to=100, variable=self.min_length_var,
                  orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=10)
        self.min_length_label = ttk.Label(length_frame, text=str(self.min_length_var.get()))
        self.min_length_label.pack(side=tk.LEFT)

        # Confidence threshold
        conf_frame = ttk.Frame(params_frame)
        conf_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(conf_frame, text="Confidence Threshold:").pack(side=tk.LEFT)
        self.confidence_var = tk.DoubleVar(value=config.get('detection', 'confidence_threshold', 0.7))
        ttk.Scale(conf_frame, from_=0.1, to=1.0, variable=self.confidence_var,
                  orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=10)
        self.confidence_label = ttk.Label(conf_frame, text=f"{self.confidence_var.get():.2f}")
        self.confidence_label.pack(side=tk.LEFT)

        # Intersection tolerance
        tolerance_frame = ttk.Frame(params_frame)
        tolerance_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(tolerance_frame, text="Intersection Tolerance:").pack(side=tk.LEFT)
        self.tolerance_var = tk.IntVar(value=config.get('detection', 'intersection_tolerance', 8))
        ttk.Scale(tolerance_frame, from_=1, to=20, variable=self.tolerance_var,
                  orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=10)
        self.tolerance_label = ttk.Label(tolerance_frame, text=str(self.tolerance_var.get()))
        self.tolerance_label.pack(side=tk.LEFT)

        # Debounce time
        debounce_frame = ttk.Frame(params_frame)
        debounce_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(debounce_frame, text="Debounce Time (seconds):").pack(side=tk.LEFT)
        self.debounce_var = tk.IntVar(value=config.get('detection', 'debounce_seconds', 60))
        ttk.Scale(debounce_frame, from_=10, to=300, variable=self.debounce_var,
                  orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=10)
        self.debounce_label = ttk.Label(debounce_frame, text=str(self.debounce_var.get()))
        self.debounce_label.pack(side=tk.LEFT)

        # Update callbacks
        def update_min_length(value):
            self.min_length_label.config(text=str(int(float(value))))
            config.set('detection', 'min_line_length', int(float(value)))

        def update_confidence(value):
            self.confidence_label.config(text=f"{float(value):.2f}")
            config.set('detection', 'confidence_threshold', float(value))

        def update_tolerance(value):
            self.tolerance_label.config(text=str(int(float(value))))
            config.set('detection', 'intersection_tolerance', int(float(value)))

        def update_debounce(value):
            self.debounce_label.config(text=str(int(float(value))))
            config.set('detection', 'debounce_seconds', int(float(value)))

        # Bind callbacks
        length_frame.children['!scale'].configure(command=update_min_length)
        conf_frame.children['!scale'].configure(command=update_confidence)
        tolerance_frame.children['!scale'].configure(command=update_tolerance)
        debounce_frame.children['!scale'].configure(command=update_debounce)

    def setup_alerts_tab(self):
        """Setup alerts configuration tab"""
        alerts_frame = ttk.Frame(self.notebook)
        self.notebook.add(alerts_frame, text="Alert Settings")

        # Telegram configuration
        telegram_frame = ttk.LabelFrame(alerts_frame, text="Telegram Configuration")
        telegram_frame.pack(fill=tk.X, padx=10, pady=10)

        # Enable checkbox
        self.telegram_enabled = tk.BoolVar(value=config.get('alerts', 'telegram_enabled', True))
        ttk.Checkbutton(telegram_frame, text="Enable Telegram Alerts",
                        variable=self.telegram_enabled).pack(anchor=tk.W, padx=5, pady=5)

        # Token entry
        token_frame = ttk.Frame(telegram_frame)
        token_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(token_frame, text="Bot Token:").pack(side=tk.LEFT)
        self.token_var = tk.StringVar(value=config.get('alerts', 'telegram_token', ''))
        ttk.Entry(token_frame, textvariable=self.token_var, show="*", width=40).pack(side=tk.LEFT, padx=5)
        ttk.Button(token_frame, text="Help", command=self.show_telegram_help).pack(side=tk.LEFT, padx=5)

        # Chat ID entry
        chat_frame = ttk.Frame(telegram_frame)
        chat_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(chat_frame, text="Chat ID:").pack(side=tk.LEFT)
        self.chat_id_var = tk.StringVar(value=config.get('alerts', 'telegram_chat_id', ''))
        ttk.Entry(chat_frame, textvariable=self.chat_id_var, width=20).pack(side=tk.LEFT, padx=5)

        # Test buttons
        test_frame = ttk.Frame(telegram_frame)
        test_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Button(test_frame, text="Test Connection",
                   command=self.test_telegram).pack(side=tk.LEFT, padx=5)
        ttk.Button(test_frame, text="Send Test Alert",
                   command=self.send_test_alert).pack(side=tk.LEFT, padx=5)

        # Cooldown setting
        cooldown_frame = ttk.Frame(telegram_frame)
        cooldown_frame.pack(fill=tk.X, padx=5, pady=5)

        ttk.Label(cooldown_frame, text="Alert Cooldown (seconds):").pack(side=tk.LEFT)
        self.cooldown_var = tk.IntVar(value=config.get('alerts', 'cooldown_seconds', 300))
        ttk.Scale(cooldown_frame, from_=60, to=3600, variable=self.cooldown_var,
                  orient=tk.HORIZONTAL, length=200).pack(side=tk.LEFT, padx=10)
        self.cooldown_label = ttk.Label(cooldown_frame, text=str(self.cooldown_var.get()))
        self.cooldown_label.pack(side=tk.LEFT)

        # Other alerts
        other_frame = ttk.LabelFrame(alerts_frame, text="Other Alert Options")
        other_frame.pack(fill=tk.X, padx=10, pady=10)

        self.sound_enabled = tk.BoolVar(value=config.get('alerts', 'sound_enabled', True))
        ttk.Checkbutton(other_frame, text="Sound Alerts",
                        variable=self.sound_enabled).pack(anchor=tk.W, padx=5, pady=2)

        self.popup_enabled = tk.BoolVar(value=config.get('alerts', 'popup_enabled', False))
        ttk.Checkbutton(other_frame, text="Popup Alerts",
                        variable=self.popup_enabled).pack(anchor=tk.W, padx=5, pady=2)

        self.log_enabled = tk.BoolVar(value=config.get('alerts', 'log_file_enabled', True))
        ttk.Checkbutton(other_frame, text="Log to File",
                        variable=self.log_enabled).pack(anchor=tk.W, padx=5, pady=2)

        # Save button
        ttk.Button(alerts_frame, text="Save Alert Settings",
                   command=self.save_alert_settings).pack(pady=10)

    def setup_logs_tab(self):
        """Setup logs and diagnostics tab"""
        logs_frame = ttk.Frame(self.notebook)
        self.notebook.add(logs_frame, text="Logs & Diagnostics")

        # Log display
        log_display_frame = ttk.LabelFrame(logs_frame, text="Application Log")
        log_display_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        # Log text widget with scrollbar
        self.log_text = tk.Text(log_display_frame, wrap=tk.WORD, height=20)
        log_scrollbar = ttk.Scrollbar(log_display_frame, orient=tk.VERTICAL,
                                      command=self.log_text.yview)
        self.log_text.configure(yscrollcommand=log_scrollbar.set)

        self.log_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=5, pady=5)
        log_scrollbar.pack(side=tk.RIGHT, fill=tk.Y, pady=5)

        # Log controls
        log_controls = ttk.Frame(logs_frame)
        log_controls.pack(fill=tk.X, padx=10, pady=5)

        ttk.Button(log_controls, text="Clear Log",
                   command=self.clear_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(log_controls, text="Save Log",
                   command=self.save_log).pack(side=tk.LEFT, padx=5)
        ttk.Button(log_controls, text="Open Log Folder",
                   command=self.open_log_folder).pack(side=tk.LEFT, padx=5)

        # Diagnostics
        diag_frame = ttk.LabelFrame(logs_frame, text="Diagnostics")
        diag_frame.pack(fill=tk.X, padx=10, pady=10)

        ttk.Button(diag_frame, text="System Info",
                   command=self.show_system_info).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(diag_frame, text="Export Config",
                   command=self.export_config).pack(side=tk.LEFT, padx=5, pady=5)
        ttk.Button(diag_frame, text="Import Config",
                   command=self.import_config).pack(side=tk.LEFT, padx=5, pady=5)

        # Start log monitoring
        self.setup_log_monitoring()

    # Event handlers and utility methods

    def auto_detect_window(self):
        """Auto-detect PocketOption window"""
        window = self.window_capture.auto_detect_window()
        if window:
            self.window_status_label.config(text=f"✓ {window.title}", foreground="green")
            self.log_message(f"Window detected: {window.title}")
        else:
            self.window_status_label.config(text="✗ No window found", foreground="red")
            messagebox.showwarning("Detection Failed",
                                   "Could not auto-detect PocketOption window.\n"
                                   "Please use manual selection.")

    def manual_select_region(self):
        """Manual region selection"""
        self.log_message("Starting manual region selection...")
        selector = RegionSelector()
        region = selector.select_region()

        if region:
            self.window_capture.set_custom_region(region)
            self.window_status_label.config(
                text=f"✓ Custom region: {region['width']}x{region['height']}",
                foreground="green"
            )
            self.log_message(f"Custom region selected: {region}")
        else:
            self.log_message("Region selection cancelled")

    def test_capture(self):
        """Test screen capture"""
        success, message = self.window_capture.test_capture()
        if success:
            messagebox.showinfo("Capture Test", f"✓ {message}")
            self.log_message(f"Capture test successful: {message}")
        else:
            messagebox.showerror("Capture Test", f"✗ {message}")
            self.log_message(f"Capture test failed: {message}")

    def test_telegram(self):
        """Test Telegram connection"""
        # Update config with current values
        config.set('alerts', 'telegram_token', self.token_var.get())
        config.set('alerts', 'telegram_chat_id', self.chat_id_var.get())

        success, message = self.alert_manager.telegram.test_connection()
        if success:
            messagebox.showinfo("Telegram Test", f"✓ {message}")
            self.log_message(f"Telegram test successful: {message}")
        else:
            messagebox.showerror("Telegram Test", f"✗ {message}")
            self.log_message(f"Telegram test failed: {message}")

    def send_test_alert(self):
        """Send test alert"""
        # Create dummy crossover for testing
        from ..detection.crossover_detector import Crossover

        test_crossover = Crossover(
            intersection_point=(400, 300),
            line1_name="zigzag_line1",
            line2_name="zigzag_line2",
            line1_confidence=0.9,
            line2_confidence=0.8,
            timestamp=time.time(),
            confidence=0.85,
            angle=45.0
        )

        # Update config
        self.save_alert_settings()

        # Send test alert
        results = self.alert_manager.send_crossover_alert(test_crossover)

        if results.get('telegram', False):
            messagebox.showinfo("Test Alert", "✓ Test alert sent successfully!")
            self.log_message("Test alert sent successfully")
        else:
            messagebox.showerror("Test Alert", "✗ Failed to send test alert")
            self.log_message("Test alert failed")

    def toggle_detection(self):
        """Start/stop detection"""
        if not self.detection_running:
            # Validate setup before starting
            if not self.validate_setup():
                return

            self.detection_running = True
            self.detection_button.config(text="Stop Detection", style="Accent.TButton")
            self.status_label.config(text="Detection running...")

            # Start detection thread
            self.detection_thread = threading.Thread(target=self.detection_loop, daemon=True)
            self.detection_thread.start()

            self.log_message("🚀 Detection started")
        else:
            self.detection_running = False
            self.detection_button.config(text="Start Detection")
            self.status_label.config(text="Detection stopped")
            self.log_message("⏹️ Detection stopped")

    def validate_setup(self):
        """Validate setup before starting detection"""
        # Check window/region
        capture_info = self.window_capture.get_capture_info()
        if not capture_info['valid']:
            messagebox.showerror("Setup Error", "No valid capture region configured.\n"
                                                "Please detect a window or select a region.")
            return False

        # Check colors
        enabled_colors = sum(1 for color_config in config.config['colors'].values()
                             if color_config.get('enabled', True))
        if enabled_colors < 2:
            messagebox.showerror("Setup Error", "At least 2 color lines must be enabled for crossover detection.")
            return False

        # Test capture
        success, message = self.window_capture.test_capture()
        if not success:
            messagebox.showerror("Setup Error", f"Capture test failed: {message}")
            return False

        return True

    def detection_loop(self):
        """Main detection loop"""
        while self.detection_running:
            try:
                # Capture screen
                image = self.window_capture.capture_screen()
                if image is None:
                    time.sleep(1)
                    continue

                self.current_image = image

                # Detect lines
                detected_lines = self.color_detector.detect_lines(image)
                self.detected_lines = detected_lines

                # Detect crossovers
                crossovers = self.crossover_detector.detect_crossovers(detected_lines)
                self.detected_crossovers.extend(crossovers)

                # Send alerts for new crossovers
                for crossover in crossovers:
                    self.alert_manager.send_crossover_alert(crossover)

                # Update GUI (in main thread)
                self.root.after(0, self.update_display)

                # Wait for next iteration
                time.sleep(1.0 / config.get('capture', 'fps', 2))

            except Exception as e:
                logging.error(f"Detection loop error: {e}")
                time.sleep(1)

    def update_display(self):
        """Update the live display"""
        if self.current_image is not None:
            try:
                # Create visualization
                vis_image = self.color_detector.visualize_detection(
                    self.current_image, self.detected_lines)

                vis_image = CrossoverVisualizer.draw_crossovers(
                    vis_image, self.detected_crossovers[-10:])  # Show last 10

                # Convert to PhotoImage
                height, width = vis_image.shape[:2]
                vis_image_rgb = cv2.cvtColor(vis_image, cv2.COLOR_BGR2RGB)
                pil_image = Image.fromarray(vis_image_rgb)

                # Scale if needed
                max_width, max_height = 800, 400
                if width > max_width or height > max_height:
                    ratio = min(max_width / width, max_height / height)
                    new_width = int(width * ratio)
                    new_height = int(height * ratio)
                    pil_image = pil_image.resize((new_width, new_height), Image.Resampling.LANCZOS)

                photo = ImageTk.PhotoImage(pil_image)

                # Update canvas
                self.canvas.delete("all")
                self.canvas.create_image(0, 0, anchor=tk.NW, image=photo)
                self.canvas.configure(scrollregion=self.canvas.bbox("all"))

                # Keep reference to prevent garbage collection
                self.canvas.image = photo

            except Exception as e:
                logging.error(f"Display update error: {e}")

    def update_statistics(self):
        """Update statistics display"""
        try:
            # Get statistics
            crossover_stats = self.crossover_detector.get_statistics()
            alert_stats = self.alert_manager.get_statistics()

            # Update labels
            self.lines_detected_label.config(text=f"Lines Detected: {len(self.detected_lines)}")

            total_crossovers = crossover_stats.get('total_crossovers', 0)
            self.crossovers_total_label.config(text=f"Total Crossovers: {total_crossovers}")

            last_hour = crossover_stats.get('last_hour', 0)
            self.crossovers_hour_label.config(text=f"Last Hour: {last_hour}")

            last_detection = crossover_stats.get('last_detection', 0)
            if last_detection > 0:
                time_str = datetime.fromtimestamp(last_detection).strftime("%H:%M:%S")
                self.last_detection_label.config(text=f"Last Detection: {time_str}")

            avg_confidence = crossover_stats.get('avg_confidence', 0)
            self.avg_confidence_label.config(text=f"Avg Confidence: {avg_confidence:.0%}")

            alerts_sent = alert_stats.get('last_day', 0)
            self.alerts_sent_label.config(text=f"Alerts Sent: {alerts_sent}")

        except Exception as e:
            logging.error(f"Statistics update error: {e}")

        # Schedule next update
        self.root.after(5000, self.update_statistics)  # Update every 5 seconds

    def update_uptime(self):
        """Update uptime display"""
        try:
            uptime_seconds = int(time.time() - self.start_time)
            hours = uptime_seconds // 3600
            minutes = (uptime_seconds % 3600) // 60
            seconds = uptime_seconds % 60

            uptime_str = f"Uptime: {hours:02d}:{minutes:02d}:{seconds:02d}"
            self.uptime_label.config(text=uptime_str)

        except Exception as e:
            logging.error(f"Uptime update error: {e}")

        # Schedule next update
        self.root.after(1000, self.update_uptime)  # Update every second

    def load_settings(self):
        """Load settings into GUI"""
        try:
            # Update GUI controls with current config values
            self.fps_var.set(config.get('capture', 'fps', 2))
            self.min_length_var.set(config.get('detection', 'min_line_length', 30))
            self.confidence_var.set(config.get('detection', 'confidence_threshold', 0.7))
            self.tolerance_var.set(config.get('detection', 'intersection_tolerance', 8))
            self.debounce_var.set(config.get('detection', 'debounce_seconds', 60))

            self.telegram_enabled.set(config.get('alerts', 'telegram_enabled', True))
            self.token_var.set(config.get('alerts', 'telegram_token', ''))
            self.chat_id_var.set(config.get('alerts', 'telegram_chat_id', ''))
            self.cooldown_var.set(config.get('alerts', 'cooldown_seconds', 300))
            self.sound_enabled.set(config.get('alerts', 'sound_enabled', True))
            self.popup_enabled.set(config.get('alerts', 'popup_enabled', False))
            self.log_enabled.set(config.get('alerts', 'log_file_enabled', True))

        except Exception as e:
            logging.error(f"Failed to load settings: {e}")

    def save_alert_settings(self):
        """Save alert settings to config"""
        try:
            config.set('alerts', 'telegram_enabled', self.telegram_enabled.get())
            config.set('alerts', 'telegram_token', self.token_var.get())
            config.set('alerts', 'telegram_chat_id', self.chat_id_var.get())
            config.set('alerts', 'cooldown_seconds', self.cooldown_var.get())
            config.set('alerts', 'sound_enabled', self.sound_enabled.get())
            config.set('alerts', 'popup_enabled', self.popup_enabled.get())
            config.set('alerts', 'log_file_enabled', self.log_enabled.get())

            config.save_config()
            self.log_message("Alert settings saved")

        except Exception as e:
            logging.error(f"Failed to save alert settings: {e}")

    def log_message(self, message):
        """Add message to log display"""
        try:
            timestamp = datetime.now().strftime("%H:%M:%S")
            log_entry = f"[{timestamp}] {message}\n"

            self.log_text.insert(tk.END, log_entry)
            self.log_text.see(tk.END)

            # Keep only last 1000 lines
            lines = self.log_text.get("1.0", tk.END).split('\n')
            if len(lines) > 1000:
                self.log_text.delete("1.0", f"{len(lines) - 1000}.0")

        except Exception as e:
            logging.error(f"Log display error: {e}")

    def setup_log_monitoring(self):
        """Setup log file monitoring"""
        # This would monitor the log file and update the display
        # For now, we'll just update periodically
        pass

    def on_closing(self):
        """Handle application closing"""
        try:
            # Stop detection
            self.detection_running = False

            # Stop alert manager
            self.alert_manager.telegram.stop_worker()

            # Save configuration
            config.save_config()

            # Close application
            self.root.destroy()

        except Exception as e:
            logging.error(f"Error during shutdown: {e}")
            self.root.destroy()

    def run(self):
        """Start the application"""
        self.log_message("🎯 ZigZag Crossover Detector v1.0 started")
        self.log_message("📋 Follow the Quick Setup steps to get started")
        self.root.mainloop()

# Additional helper methods would go here...
# (calibrate_colors, show_telegram_help, export_config, etc.)