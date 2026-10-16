#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
overlay.py - Atalho universal para o overlay no Linux
"""
import os
import sys
from pathlib import Path

if __name__ == "__main__":
    script_linux = Path(__file__).resolve().parent / "overlay_linux.py"
    os.execv(sys.executable, [sys.executable, str(script_linux)] + sys.argv[1:])
