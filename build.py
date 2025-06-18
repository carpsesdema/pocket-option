#!/usr/bin/env python3
"""
Build script for ZigZag Crossover Detector
Creates a standalone executable using PyInstaller
"""

import os
import sys
import subprocess
import shutil
from pathlib import Path


def check_requirements():
    """Check if all required packages are installed"""
    required_packages = [
        'pyinstaller',
        'opencv-python',
        'numpy',
        'pillow',
        'mss',
        'requests',
        'psutil'
    ]

    missing_packages = []

    for package in required_packages:
        try:
            __import__(package.replace('-', '_'))
        except ImportError:
            missing_packages.append(package)

    if missing_packages:
        print(f"❌ Missing required packages: {', '.join(missing_packages)}")
        print("📦 Install with: pip install -r requirements.txt")
        return False

    print("✅ All required packages found")
    return True


def clean_build_dirs():
    """Clean previous build directories"""
    dirs_to_clean = ['build', 'dist', '__pycache__']

    for dir_name in dirs_to_clean:
        if os.path.exists(dir_name):
            print(f"🧹 Cleaning {dir_name}/")
            shutil.rmtree(dir_name)


def create_spec_file():
    """Create PyInstaller spec file with optimized settings"""
    spec_content = '''
# -*- mode: python ; coding: utf-8 -*-

import sys
from pathlib import Path

# Add src directory to Python path
src_path = str(Path(__file__).parent / "src")
sys.path.insert(0, src_path)

a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('src', 'src'),
        ('config.json', '.'),
    ],
    hiddenimports=[
        'src.gui.main_window',
        'src.config.settings',
        'src.capture.window_capture',
        'src.detection.color_detector',
        'src.detection.crossover_detector',
        'src.alerts.telegram_alerter',
        'PIL._tkinter_finder',
        'pkg_resources.py2_warn',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'matplotlib',
        'scipy',
        'pandas',
        'pytest',
        'jupyter',
        'IPython',
    ],
    noarchive=False,
)

# Filter out unnecessary files
a.datas = [x for x in a.datas if not x[0].startswith('matplotlib')]
a.datas = [x for x in a.datas if not x[0].startswith('scipy')]

pyz = PYZ(a.pure, a.zipped_data, cipher=None)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='ZigZagDetector',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False,  # Set to True for debugging
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='icon.ico' if Path('icon.ico').exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.zipfiles,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='ZigZagDetector',
)
'''

    with open('ZigZagDetector.spec', 'w') as f:
        f.write(spec_content.strip())

    print("📝 Created ZigZagDetector.spec")


def build_executable():
    """Build the executable using PyInstaller"""
    print("🔨 Building executable...")

    # Run PyInstaller
    cmd = [
        sys.executable, '-m', 'PyInstaller',
        '--clean',
        '--noconfirm',
        'ZigZagDetector.spec'
    ]

    try:
        result = subprocess.run(cmd, check=True, capture_output=True, text=True)
        print("✅ Build completed successfully!")
        return True
    except subprocess.CalledProcessError as e:
        print(f"❌ Build failed: {e}")
        print(f"Error output: {e.stderr}")
        return False


def create_installer_files():
    """Create additional files for the installer"""
    dist_dir = Path("dist/ZigZagDetector")

    if not dist_dir.exists():
        print("❌ Distribution directory not found")
        return

    # Create README.txt for end users
    readme_content = """
ZigZag Crossover Detector v1.0
==============================

QUICK START:
1. Run ZigZagDetector.exe
2. Click "Auto Detect" to find PocketOption window
3. Configure Telegram settings (optional)
4. Click "Start Detection"

REQUIREMENTS:
- Windows 10/11
- PocketOption platform open in browser
- Internet connection for Telegram alerts

SUPPORT:
- Check the logs/ folder for troubleshooting
- Export your configuration for backup
- Contact support if you encounter issues

IMPORTANT:
- Make sure PocketOption ZigZag indicators are visible
- Test capture before starting detection
- Configure alert cooldown to avoid spam

For detailed instructions, see the user manual.
    """

    with open(dist_dir / "README.txt", 'w') as f:
        f.write(readme_content.strip())

    # Create default config file
    default_config = {
        "window": {
            "auto_detect": True,
            "keywords": ["pocketoption", "chrome", "firefox", "edge"]
        },
        "capture": {
            "fps": 2,
            "image_scale": 1.0
        },
        "colors": {
            "zigzag_line1": {
                "name": "Yellow/Green Line",
                "hue_min": 20, "hue_max": 35,
                "sat_min": 100, "sat_max": 255,
                "val_min": 100, "val_max": 255,
                "enabled": True
            },
            "zigzag_line2": {
                "name": "Purple Line",
                "hue_min": 120, "hue_max": 150,
                "sat_min": 100, "sat_max": 255,
                "val_min": 100, "val_max": 255,
                "enabled": True
            }
        },
        "detection": {
            "min_line_length": 30,
            "confidence_threshold": 0.7,
            "intersection_tolerance": 8,
            "debounce_seconds": 60
        },
        "alerts": {
            "telegram_enabled": True,
            "telegram_token": "",
            "telegram_chat_id": "",
            "cooldown_seconds": 300,
            "sound_enabled": True,
            "log_file_enabled": True
        }
    }

    import json
    with open(dist_dir / "config.json", 'w') as f:
        json.dump(default_config, f, indent=2)

    # Create logs directory
    (dist_dir / "logs").mkdir(exist_ok=True)

    print("📁 Created installer files")


def create_installer_script():
    """Create a simple installer script"""
    installer_content = '''
@echo off
echo ZigZag Crossover Detector - Installation
echo =======================================

echo.
echo Checking system requirements...

:: Check if Windows
if not "%OS%"=="Windows_NT" (
    echo Error: This software requires Windows
    pause
    exit /b 1
)

:: Create application directory
set "INSTALL_DIR=%PROGRAMFILES%\\ZigZagDetector"
echo Installing to: %INSTALL_DIR%

if not exist "%INSTALL_DIR%" (
    mkdir "%INSTALL_DIR%"
)

:: Copy files
echo Copying files...
xcopy /E /I /Y "ZigZagDetector\\*" "%INSTALL_DIR%\\"

:: Create desktop shortcut
echo Creating desktop shortcut...
set "SHORTCUT=%USERPROFILE%\\Desktop\\ZigZag Detector.lnk"
powershell "$s=(New-Object -COM WScript.Shell).CreateShortcut('%SHORTCUT%'); $s.TargetPath='%INSTALL_DIR%\\ZigZagDetector.exe'; $s.Save()"

:: Create start menu entry
set "STARTMENU=%APPDATA%\\Microsoft\\Windows\\Start Menu\\Programs"
set "STARTSHORTCUT=%STARTMENU%\\ZigZag Detector.lnk"
powershell "$s=(New-Object -COM WScript.Shell).CreateShortcut('%STARTSHORTCUT%'); $s.TargetPath='%INSTALL_DIR%\\ZigZagDetector.exe'; $s.Save()"

echo.
echo Installation completed successfully!
echo.
echo You can now run ZigZag Detector from:
echo - Desktop shortcut
echo - Start menu
echo - %INSTALL_DIR%\\ZigZagDetector.exe
echo.
pause
    '''

    with open('dist/install.bat', 'w') as f:
        f.write(installer_content.strip())

    print("📦 Created installer script")


def main():
    """Main build process"""
    print("🚀 ZigZag Crossover Detector - Build Script")
    print("=" * 50)

    # Check if we're in the right directory
    if not os.path.exists('main.py'):
        print("❌ main.py not found. Run this script from the project root directory.")
        return False

    # Check requirements
    if not check_requirements():
        return False

    # Clean previous builds
    clean_build_dirs()

    # Create spec file
    create_spec_file()

    # Build executable
    if not build_executable():
        return False

    # Create additional files
    create_installer_files()
    create_installer_script()

    print("\n🎉 Build completed successfully!")
    print(f"📁 Executable location: dist/ZigZagDetector/ZigZagDetector.exe")
    print(f"📦 Installer script: dist/install.bat")
    print(f"📊 Total size: {get_folder_size('dist/ZigZagDetector'):.1f} MB")

    return True


def get_folder_size(folder_path):
    """Get folder size in MB"""
    total_size = 0
    for dirpath, dirnames, filenames in os.walk(folder_path):
        for f in filenames:
            fp = os.path.join(dirpath, f)
            if os.path.exists(fp):
                total_size += os.path.getsize(fp)
    return total_size / (1024 * 1024)  # Convert to MB


if __name__ == "__main__":
    success = main()
    if not success:
        sys.exit(1)