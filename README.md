ZigZag Crossover Detector
A professional-grade real-time detection system for ZigZag indicator crossovers on PocketOption trading platform with instant Telegram alerts.

🚀 Features
Real-time Detection: Monitors ZigZag indicators continuously
Advanced Color Detection: HSV-based line extraction with confidence scoring
Geometric Crossover Analysis: Precise intersection detection with angle validation
Telegram Alerts: Instant notifications with rich formatting
User-Friendly GUI: Comprehensive configuration interface
Professional Logging: Detailed logs and diagnostics
Modular Architecture: Clean, maintainable codebase
📁 Project Structure
zigzag-detector/
├── main.py                 # Application entry point
├── requirements.txt        # Python dependencies
├── build.py               # Executable build script
├── setup.py               # Package installation
├── README.md              # This file
├── config.json            # Configuration file (auto-generated)
├── logs/                  # Application logs
└── src/
    ├── __init__.py
    ├── config/
    │   ├── __init__.py
    │   └── settings.py     # Configuration management
    ├── capture/
    │   ├── __init__.py
    │   └── window_capture.py  # Screen capture & window detection
    ├── detection/
    │   ├── __init__.py
    │   ├── color_detector.py      # Color-based line detection
    │   └── crossover_detector.py  # Crossover analysis
    ├── alerts/
    │   ├── __init__.py
    │   └── telegram_alerter.py   # Alert system
    └── gui/
        ├── __init__.py
        └── main_window.py        # Main application GUI
🔧 Installation
Option 1: Use Pre-built Executable (Recommended for Clients)
Download the latest release
Run install.bat as administrator
Launch from desktop shortcut
Option 2: Install from Source (Developers)
bash
# Clone the repository
git clone https://github.com/yourusername/zigzag-detector.git
cd zigzag-detector

# Install dependencies
pip install -r requirements.txt

# Run the application
python main.py
Option 3: Install as Package
bash
pip install -e .
zigzag-detector
🎯 Quick Start Guide
1. Initial Setup
Launch Application: Run ZigZagDetector.exe or python main.py
Window Detection: Click "Auto Detect" to find PocketOption browser
Test Capture: Verify screen capture is working
Configure Colors: Use "Calibrate Colors" for automatic setup
2. Telegram Setup (Optional but Recommended)
Create Bot: Message @BotFather on Telegram, use /newbot
Get Token: Copy the bot token from BotFather
Get Chat ID:
Send a message to your bot
Visit: https://api.telegram.org/bot<TOKEN>/getUpdates
Find "chat":{"id": in the response
Configure: Enter token and chat ID in the "Alert Settings" tab
Test: Click "Send Test Alert" to verify
3. Start Detection
Validate Setup: Ensure window is detected and colors are calibrated
Adjust Settings: Configure detection parameters if needed
Start Detection: Click "Start Detection" to begin monitoring
Monitor: Watch the live preview and check logs for crossovers
⚙️ Configuration
Color Detection Settings
HSV Ranges: Hue, Saturation, Value ranges for line colors
Confidence Threshold: Minimum confidence for line detection
Minimum Line Length: Filter out noise and short segments
Crossover Detection Settings
Intersection Tolerance: Pixel tolerance for crossover detection
Angle Threshold: Minimum intersection angle (avoids shallow crossings)
Debounce Time: Cooldown between duplicate crossover alerts
Alert Settings
Telegram: Bot token, chat ID, message cooldown
Sound Alerts: System beep notifications
File Logging: Crossover logs for analysis
📊 Monitoring & Diagnostics
Live Statistics
Lines detected per frame
Total crossovers detected
Detection confidence averages
System uptime and performance
Logs & Diagnostics
Application Log: Real-time activity log
System Info: Hardware and software details
Configuration Export/Import: Backup and restore settings
Log Files: Persistent logging in logs/ directory
🏗️ Building Executable
To create a standalone executable for distribution:

bash
# Install build dependencies
pip install pyinstaller

# Run build script
python build.py
The executable will be created in dist/ZigZagDetector/

Build Features
Single Directory: All files in one folder
Optimized Size: Excludes unnecessary packages
Auto-Installer: Includes installation script
Default Config: Pre-configured settings
🛠️ Development
Architecture Overview
The application follows a modular architecture with clear separation of concerns:

Config: Centralized configuration management with validation
Capture: Window detection and screen capture abstraction
Detection: Color detection and geometric crossover analysis
Alerts: Multi-channel alert system (Telegram, sound, logs)
GUI: User-friendly interface with comprehensive controls
Key Design Patterns
Observer Pattern: Real-time updates between components
Strategy Pattern: Configurable detection algorithms
Factory Pattern: Dynamic color detector creation
Singleton Pattern: Global configuration management
Testing
bash
# Run unit tests
python -m pytest tests/

# Run integration tests  
python -m pytest tests/integration/

# Test color detection
python -m src.detection.color_detector --test

# Test crossover detection
python -m src.detection.crossover_detector --test
🎨 Customization
Adding New Color Detectors
python
# In src/detection/color_detector.py
def add_custom_line(self, name, hsv_ranges):
    config.set_color_config(name, {
        'name': name,
        'hue_min': hsv_ranges['hue'][0],
        'hue_max': hsv_ranges['hue'][1],
        # ... other parameters
        'enabled': True
    })
Custom Alert Channels
python
# In src/alerts/telegram_alerter.py
class CustomAlerter:
    def send_alert(self, crossover):
        # Implement custom alert logic
        pass
🐛 Troubleshooting
Common Issues
Window Detection Fails

Ensure PocketOption is open and visible
Try manual region selection
Check if browser is in fullscreen mode
Color Detection Issues

Use the color calibration tool
Adjust HSV ranges manually
Ensure ZigZag indicators are visible and contrasting
Telegram Alerts Not Working

Verify bot token and chat ID
Check internet connection
Ensure you sent at least one message to the bot first
Performance Issues

Reduce capture FPS
Close unnecessary applications
Check system resources in Task Manager
Debug Mode
Enable console output for debugging:

bash
python main.py --debug
📝 License
This project is licensed under the MIT License - see the LICENSE file for details.

🤝 Contributing
Fork the repository
Create a feature branch (git checkout -b feature/amazing-feature)
Commit your changes (git commit -m 'Add some amazing feature')
Push to the branch (git push origin feature/amazing-feature)
Open a Pull Request
📞 Support
Issues: GitHub Issues
Documentation: Wiki
Email: support@example.com
⚠️ Disclaimer
This software is for educational and research purposes. Trading involves risk and this tool does not guarantee profitable trades. Always use proper risk management and consider your financial situation before trading.

