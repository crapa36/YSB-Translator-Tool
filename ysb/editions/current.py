# -*- coding: utf-8 -*-
"""Current YSB Tool edition selector.

This module is intentionally tiny and dependency-free.
It must be safe to import from common modules before the UI starts.

Edition selection order:
1. Entry point calls set_current_edition("lite"/"local").
2. YSB_TOOL_EDITION environment variable.
3. Default: lite.
"""

from __future__ import annotations

from dataclasses import dataclass
import os

from ysb.version_info import (
    APP_VERSION,
    LITE_APP_NAME_EN,
    LITE_APP_NAME_KO,
    LITE_MAIN_EXE_NAME,
    LOCAL_APP_NAME_EN,
    LOCAL_APP_NAME_KO,
    LOCAL_MAIN_EXE_NAME,
    UPDATE_IGNORE_KEY_LITE,
    UPDATE_IGNORE_KEY_LOCAL,
    VERSION_JSON_URL_LITE,
    VERSION_JSON_URL_LOCAL,
)


@dataclass(frozen=True)
class EditionInfo:
    key: str
    label: str
    app_version: str
    app_name_ko: str
    app_name_en: str
    main_exe_name: str
    version_json_url: str
    update_ignore_key: str
    onefile: bool


_EDITION_TABLE: dict[str, EditionInfo] = {
    "lite": EditionInfo(
        key="lite",
        label="Lite",
        app_version=APP_VERSION,
        app_name_ko=LITE_APP_NAME_KO,
        app_name_en=LITE_APP_NAME_EN,
        main_exe_name=LITE_MAIN_EXE_NAME,
        version_json_url=VERSION_JSON_URL_LITE,
        update_ignore_key=UPDATE_IGNORE_KEY_LITE,
        onefile=True,
    ),
    "local": EditionInfo(
        key="local",
        label="Local",
        app_version=APP_VERSION,
        app_name_ko=LOCAL_APP_NAME_KO,
        app_name_en=LOCAL_APP_NAME_EN,
        main_exe_name=LOCAL_MAIN_EXE_NAME,
        version_json_url=VERSION_JSON_URL_LOCAL,
        update_ignore_key=UPDATE_IGNORE_KEY_LOCAL,
        onefile=False,
    ),
}

_ENV_KEY = "YSB_TOOL_EDITION"
_CURRENT_EDITION: str | None = None


def normalize_edition(value: str | None) -> str:
    text = str(value or "").strip().lower()
    if text in _EDITION_TABLE:
        return text
    return "lite"


def set_current_edition(value: str | None) -> EditionInfo:
    global _CURRENT_EDITION
    key = normalize_edition(value)
    _CURRENT_EDITION = key
    os.environ[_ENV_KEY] = key
    return _EDITION_TABLE[key]


def get_current_edition_key() -> str:
    if _CURRENT_EDITION:
        return _CURRENT_EDITION
    return normalize_edition(os.environ.get(_ENV_KEY))


def get_current_edition() -> EditionInfo:
    return _EDITION_TABLE[get_current_edition_key()]


def is_lite_edition() -> bool:
    return get_current_edition_key() == "lite"


def is_local_edition() -> bool:
    return get_current_edition_key() == "local"
