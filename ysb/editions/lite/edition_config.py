# -*- coding: utf-8 -*-
"""Lite edition configuration.

No new feature is enabled here yet. This file exists so future Lite-only
settings can be added without touching common modules.
"""

EDITION_KEY = "lite"
PREFERRED_OCR_ENGINE = "api"
ALLOW_LOCAL_ENGINES = False
VERSION_JSON_NAME = "version.json"

# Lite keeps text detection disabled unless a future API detector is added.
PREFERRED_TEXT_DETECTOR = "none"
ALLOW_COMIC_TEXT_DETECTOR = False
