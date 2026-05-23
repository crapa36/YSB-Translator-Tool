# -*- coding: utf-8 -*-
"""Local dependency checker.

PaddleOCR is run through an external worker in the Local package, not imported
inside the frozen EXE.  Therefore the runtime check accepts either an importable
source-environment paddleocr module or the packaged worker + portable Python
runtime pair.
"""

from __future__ import annotations

import importlib.util
import os
import sys
from pathlib import Path


def module_available(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return Path.cwd()


def external_paddleocr_worker_status() -> tuple[bool, str]:
    root = _app_root()
    worker = root / "local_runtime" / "paddle_ocr_worker.py"
    env_python = os.environ.get("YSB_PADDLEOCR_PYTHON")
    python_candidates = []
    if env_python:
        python_candidates.append(Path(env_python).expanduser())
    python_candidates.extend([
        root / "local_runtime" / "python" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "Scripts" / "python.exe",
        root / "local_runtime" / "ocr_venv" / "bin" / "python",
        root / ".venv" / "Scripts" / "python.exe",
        root / ".venv" / "bin" / "python",
    ])
    if not worker.exists():
        return False, f"External PaddleOCR worker not found: {worker}"
    for py in python_candidates:
        if py.exists():
            return True, f"External PaddleOCR worker ready: {py}"
    return False, "External PaddleOCR Python runtime not found. local_runtime/python/python.exe를 확인해 주세요."


def paddleocr_available() -> bool:
    ok, _ = external_paddleocr_worker_status()
    if ok:
        return True
    return module_available("paddleocr")


def comic_text_detector_required_modules() -> list[str]:
    return ["torch", "torchvision", "cv2", "numpy", "pyclipper", "shapely", "tqdm", "PIL", "yaml"]


def comic_text_detector_runtime_status() -> tuple[bool, list[str]]:
    missing: list[str] = []
    for module_name in comic_text_detector_required_modules():
        if not module_available(module_name):
            missing.append(module_name)
    return len(missing) == 0, missing
