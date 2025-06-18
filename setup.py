#!/usr/bin/env python3
"""
Setup script for ZigZag Crossover Detector
Installs the package and its dependencies
"""

from setuptools import setup, find_packages
import os
from pathlib import Path

# Read the README file
this_directory = Path(__file__).parent
long_description = (this_directory / "README.md").read_text() if (this_directory / "README.md").exists() else ""

# Read requirements
requirements = []
if os.path.exists("requirements.txt"):
    with open("requirements.txt", "r") as f:
        requirements = [line.strip() for line in f if line.strip() and not line.startswith("#")]

setup(
    name="zigzag-crossover-detector",
    version="1.0.0",
    author="Trading Tools Developer",
    author_email="support@example.com",
    description="Professional ZigZag crossover detection system for trading platforms",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/yourusername/zigzag-detector",

    packages=find_packages(),
    package_data={
        "": ["*.json", "*.txt", "*.md"],
    },
    include_package_data=True,

    install_requires=requirements,

    entry_points={
        "console_scripts": [
            "zigzag-detector=main:main",
        ],
    },

    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Financial and Insurance Industry",
        "Topic :: Office/Business :: Financial :: Investment",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Operating System :: Microsoft :: Windows",
    ],

    python_requires=">=3.8",

    keywords="trading, zigzag, crossover, detection, pocketoption, alerts, telegram",

    project_urls={
        "Bug Reports": "https://github.com/yourusername/zigzag-detector/issues",
        "Documentation": "https://github.com/yourusername/zigzag-detector/wiki",
        "Source": "https://github.com/yourusername/zigzag-detector",
    },
)