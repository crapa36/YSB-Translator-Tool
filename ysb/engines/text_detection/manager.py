# -*- coding: utf-8 -*-
"""Text detection manager for Lite/Local editions."""

from __future__ import annotations

from .base import TextDetectionRequest, TextDetectionResult
from ysb.editions.current import is_local_edition


def default_text_detector_key() -> str:
    return "comic_text_detector" if is_local_edition() else "none"


def detect_with_default_engine(request: TextDetectionRequest) -> TextDetectionResult:
    if not is_local_edition():
        return TextDetectionResult(
            ok=False,
            engine="none",
            error="Text detection is not enabled for Lite edition.",
        )

    # Local-only import. Do not move to module top-level.
    from .comic_text_detector import ComicTextDetectorEngine

    return ComicTextDetectorEngine().detect(request)
