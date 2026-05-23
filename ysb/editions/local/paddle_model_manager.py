# -*- coding: utf-8 -*-
"""PaddleOCR model path helpers.

The regular Local build keeps only the supported PaddleOCR path for OCR text
recognition. Experimental OCR model folders are not part of this manager.
"""

from __future__ import annotations

from pathlib import Path


def default_local_models_dir(app_root: Path) -> Path:
    return Path(app_root) / "local_models"
