#!/usr/bin/env python3
"""
HDRI Maker - Surface Painter for HDR Environments
Entry point for the application.

A multi-language tool (Python + C++ + C#) for creating, painting,
and composing High Dynamic Range Images (HDRIs) for use in
Blender, Unity, Unreal Engine, and other 3D applications.

Usage:
    python main.py
"""

import sys
import os

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.app import run

if __name__ == "__main__":
    run()
