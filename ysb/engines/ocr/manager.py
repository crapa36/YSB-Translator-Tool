# -*- coding: utf-8 -*-
"""OCR engine manager placeholder for future Lite/Local switching."""

from __future__ import annotations

from ysb.editions.current import is_local_edition


def default_ocr_engine_key() -> str:
    return "paddle" if is_local_edition() else "api"
