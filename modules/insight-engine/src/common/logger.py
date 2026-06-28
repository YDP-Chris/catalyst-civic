#!/usr/bin/env python
"""Minimal stdout logger with timestamps, matching the pipeline log style."""
from __future__ import annotations

from datetime import datetime


def log(message: str, level: str = "INFO") -> None:
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{timestamp}] [{level}] {message}", flush=True)
