# -*- coding: utf-8 -*-
"""Path helpers for the Local comic_text_detector runtime."""

from __future__ import annotations

from pathlib import Path
import sys


MODEL_FILE_NAME = "comic_text_detector.pt"
VENDOR_RELATIVE_DIR = Path("third_party") / "comic_text_detector"


def app_roots() -> list[Path]:
    roots: list[Path] = []
    if hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS))
    if getattr(sys, "frozen", False):
        roots.append(Path(sys.executable).resolve().parent)
    roots.append(Path(__file__).resolve().parents[3])
    # When this file is inside ysb/editions/local, parents[3] is project root in source.
    seen: set[Path] = set()
    unique: list[Path] = []
    for root in roots:
        try:
            key = root.resolve()
        except Exception:
            key = root
        if key not in seen:
            seen.add(key)
            unique.append(root)
    return unique


def default_comic_detector_vendor_dir() -> Path:
    for root in app_roots():
        candidate = root / VENDOR_RELATIVE_DIR
        if candidate.exists():
            return candidate
    return app_roots()[0] / VENDOR_RELATIVE_DIR


def default_comic_detector_model_path() -> Path:
    # Prefer the vendored model bundled with the user's detector ZIP.
    vendor_model = default_comic_detector_vendor_dir() / MODEL_FILE_NAME
    if vendor_model.exists():
        return vendor_model

    # Allow a manually managed model location later if the vendored model is removed.
    for root in app_roots():
        candidate = root / "local_models" / "comic_text_detector" / MODEL_FILE_NAME
        if candidate.exists():
            return candidate
    return vendor_model
