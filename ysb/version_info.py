# -*- coding: utf-8 -*-
"""Central version/brand metadata for YSB Translator Tool.

Edit this file first when releasing a new version.
The app UI, edition metadata, launcher candidates, and PyInstaller build names
read from this single source of truth.
"""

from __future__ import annotations

# ---------------------------------------------------------------------------
# Release version
# ---------------------------------------------------------------------------
# Change these numbers only, then rebuild.
VERSION_MAJOR = 2
VERSION_MINOR = 3
VERSION_PATCH = 0
VERSION_BUILD = 0

VERSION_TEXT = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}"
APP_VERSION = f"v{VERSION_TEXT}"
WINDOWS_VERSION_STRING = f"{VERSION_MAJOR}.{VERSION_MINOR}.{VERSION_PATCH}.{VERSION_BUILD}"
WINDOWS_VERSION_TUPLE = (VERSION_MAJOR, VERSION_MINOR, VERSION_PATCH, VERSION_BUILD)

# ---------------------------------------------------------------------------
# Product / company metadata
# ---------------------------------------------------------------------------
COMPANY_NAME = "Zerostress8"
PRODUCT_NAME = "YSB Translator Tool"
APP_FAMILY_ID = "ZEROSTRESS8_YSB_TRANSLATOR_TOOL"

APP_TITLE_KO = "역식붕이 툴"
APP_TITLE_EN = "YSB Tool"
APP_TITLE_FULL = "YSB Translator Tool / 역식붕이 툴"

SUPPORT_EMAIL = "ysbtool.support@gmail.com"
COPYRIGHT_TEXT = "© 2026 amule949"

# ---------------------------------------------------------------------------
# Edition names shown in the app and used by the build tool
# ---------------------------------------------------------------------------
LITE_EDITION_LABEL = "Lite"
LOCAL_EDITION_LABEL = "Local"

LITE_APP_NAME_KO = f"{APP_TITLE_KO} {LITE_EDITION_LABEL}"
LOCAL_APP_NAME_KO = f"{APP_TITLE_KO} {LOCAL_EDITION_LABEL}"
LITE_APP_NAME_EN = f"{APP_TITLE_EN} {LITE_EDITION_LABEL}"
LOCAL_APP_NAME_EN = f"{APP_TITLE_EN} {LOCAL_EDITION_LABEL}"

LITE_MAIN_EXE_NAME = f"{LITE_APP_NAME_KO} {APP_VERSION}"
LOCAL_MAIN_EXE_NAME = f"{LOCAL_APP_NAME_KO} {APP_VERSION}"
LAUNCHER_EXE_NAME = "YSB_Launcher"

# Build output folders. The build scripts intentionally leave only these
# *_package folders in dist/ so the final runnable output is not ambiguous.
LITE_PACKAGE_FOLDER_NAME = f"{LITE_MAIN_EXE_NAME}_package"
LOCAL_PACKAGE_FOLDER_NAME = f"{LOCAL_MAIN_EXE_NAME}_package"

# Legacy zip names are kept for compatibility with older scripts/docs, but the
# v2.1.0 build output policy no longer creates ZIP files by default.
LITE_PACKAGE_ZIP_NAME = f"YSB_Tool_Lite_{APP_VERSION}.zip"
LOCAL_PACKAGE_ZIP_NAME = f"YSB_Tool_Local_{APP_VERSION}.zip"
BUILD_LOG_FILE_NAME = f"build_log_{APP_VERSION}.txt"

VERSION_JSON_URL_LITE = "https://ysb-tool.com/version.json"
VERSION_JSON_URL_LOCAL = "https://ysb-tool.com/version_local.json"

UPDATE_IGNORE_KEY_LITE = "ignored_update_version_lite"
UPDATE_IGNORE_KEY_LOCAL = "ignored_update_version_local"

YSB_ROLE_MAIN = "YSB_MAIN"
YSB_ROLE_LAUNCHER = "YSB_LAUNCHER"


def app_name_ko(edition: str) -> str:
    return LOCAL_APP_NAME_KO if str(edition).lower() == "local" else LITE_APP_NAME_KO


def app_name_en(edition: str) -> str:
    return LOCAL_APP_NAME_EN if str(edition).lower() == "local" else LITE_APP_NAME_EN


def main_exe_name(edition: str) -> str:
    return LOCAL_MAIN_EXE_NAME if str(edition).lower() == "local" else LITE_MAIN_EXE_NAME


def package_folder_name(edition: str) -> str:
    return LOCAL_PACKAGE_FOLDER_NAME if str(edition).lower() == "local" else LITE_PACKAGE_FOLDER_NAME


def package_zip_name(edition: str) -> str:
    return LOCAL_PACKAGE_ZIP_NAME if str(edition).lower() == "local" else LITE_PACKAGE_ZIP_NAME


def windows_original_filename(edition: str) -> str:
    return "YSB_Tool_Local.exe" if str(edition).lower() == "local" else "YSB_Tool_Lite.exe"


def main_exe_candidates() -> list[str]:
    """Candidate main executable names for the shared launcher."""
    return [
        f"{LITE_MAIN_EXE_NAME}.exe",
        f"{LOCAL_MAIN_EXE_NAME}.exe",
        f"YSB_Tool_Lite_{APP_VERSION}.exe",
        f"YSB_Tool_Local_{APP_VERSION}.exe",
        "역식붕이 툴 v2.0.1.exe",
        "역식붕이 툴 v1.8.1.exe",
        "역식붕이 툴.exe",
        "YSB_Tool_v2.0.1.exe",
        "YSB_Tool_v1.8.1.exe",
        "YSB_Tool.exe",
    ]
