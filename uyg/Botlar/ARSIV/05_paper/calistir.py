#!/usr/bin/env python3
"""Arsiv calistirici: kanonik botu (uyg/Botlar/bot_paper.py) calistirir.
Kullanim: quantlab/.venv/bin/python uyg/Botlar/ARSIV/05_paper/calistir.py"""
import runpy
import sys
from pathlib import Path

BOTLAR = Path(__file__).resolve().parents[1].parent   # .../uyg/Botlar
sys.path.insert(0, str(BOTLAR))
runpy.run_path(str(BOTLAR / "bot_paper.py"), run_name="__main__")
