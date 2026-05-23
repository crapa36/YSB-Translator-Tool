# -*- coding: utf-8 -*-
"""Local edition configuration.

Heavy Local modules are still imported lazily by their adapters so the Lite
edition stays clean, but the supported Local OCR engine is PaddleOCR.
"""

EDITION_KEY = "local"
PREFERRED_OCR_ENGINE = "paddle"
ALLOW_LOCAL_ENGINES = True
FALLBACK_TO_API_OCR = True
VERSION_JSON_NAME = "version_local.json"

# Local text detection is separated from OCR.
PREFERRED_TEXT_DETECTOR = "comic_text_detector"
ALLOW_COMIC_TEXT_DETECTOR = True
