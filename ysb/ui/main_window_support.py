import sys
import os
import math
import shutil
import uuid
from pathlib import Path
from collections import OrderedDict
from ysb.core.text_style_limits import clamp_text_line_spacing, clamp_text_letter_spacing, clamp_text_char_scale, positive_scale_factor, qt_font_stretch_value, text_line_height_from_percent

# Source tree root. main_window.py lives at ysb/ui/main_window.py.
APP_ROOT = Path(__file__).resolve().parents[2]

import copy
import json
import re
import time
import subprocess
import zipfile
import tempfile
import io
import base64
import hashlib
import hmac
import threading
import webbrowser
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime, timezone

import cv2
import numpy as np
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from ysb.engine.manga_engine import MangaProcessEngine, Config
from ysb.core.project_store import ProjectStore, PROJECT_FILENAME, YSB_EXTENSION, package_project, append_project_json_to_package, extract_ysb_package, read_ysb_manifest, safe_project_name, clean_workspace_name, unique_dir, unique_dir_with_code_suffix
from ysb.settings.api_settings import ApiSettingsStore, ApiSettingsDialog, apply_settings_to_config


def ysb_apply_readable_bold_to_font(font, enabled):
    """Apply a moderate text bold weight used by the YSB canvas/editor."""
    try:
        if enabled:
            font.setWeight(QFont.Weight.DemiBold)
        else:
            font.setWeight(QFont.Weight.Normal)
    except Exception:
        try:
            font.setBold(bool(enabled))
        except Exception:
            pass
    return font


def ysb_combo_diag_log(source, message):
    """Compatibility no-op. Combo popup diagnostics are disabled in normal builds."""
    return


class StableComboBox(QComboBox):
    """Plain combo box used by the compact right panel.

    Diagnostics and popup event filters were removed because they can make the native
    popup redraw path look like a double-open flash on Windows/Qt.
    """

    pass


from ysb.settings.shortcut_settings import ShortcutSettingsStore, ShortcutSettingsDialog, MacroSettingsDialog, TEXT_SYMBOLS, shortcut_label_map, ConfirmingKeySequenceEdit, sequence_without_confirm_keys, key_sequence_from_text, key_sequence_to_portable, key_event_matches_sequence
from ysb.ui.viewer import MuleImageViewer
from ysb.engine.graphics_items import TypesettingItem, build_typesetting_text_path
from ysb.ui.delegates import MultilineDelegate
from ysb.services.workers import UniversalBatchWorker, AnalysisWorker, InpaintWorker, TranslationWorker, QuickOCRWorker
from ysb.core.cache_utils import get_cache_dir, get_cache_file
from ysb.editions.current import get_current_edition
from ysb.ui.launcher import LauncherWidget, RecentProjectStore
from ysb.core.workspace_manager import get_workspace_root, temp_dir, workspaces_dir, default_package_dir, schedule_workspace_root_change, load_workspace_config, set_workspace_root, default_workspace_root, APP_FOLDER_NAME, configured_workspace_root_raw, configured_workspace_root_exists, app_config_dir


def resource_path(relative_path):
    """
    일반 실행 / PyInstaller --onedir / PyInstaller --onefile 모두에서
    포함 리소스 파일 경로를 안정적으로 찾는다.

    v2.0.1 리팩토링 이후 아이콘/스플래시/로고는 assets/ 아래에서 관리한다.
    기존 코드가 resource_path("ysb_icon.ico"), resource_path("ysb_splash.png")처럼
    루트 기준 이름을 넘겨도 assets/의 정식 파일을 먼저 찾도록 보정한다.
    """
    rel = str(relative_path).replace("\\", "/").lstrip("/")

    aliases = {
        "ysb_icon.ico": ["assets/YSB_icon.ico", "assets/ysb_icon.ico", "YSB_icon.ico", "ysb_icon.ico"],
        "YSB_icon.ico": ["assets/YSB_icon.ico", "assets/ysb_icon.ico", "YSB_icon.ico", "ysb_icon.ico"],
        "ysbt_file_icon.ico": ["assets/ysbt_file_icon.ico", "ysbt_file_icon.ico"],
        "YSBT_file_icon.ico": ["assets/ysbt_file_icon.ico", "ysbt_file_icon.ico"],
        "ysb_launcher_icon.ico": ["assets/ysb_launcher_icon.ico", "ysb_launcher_icon.ico"],
        "YSB_launcher_icon.ico": ["assets/ysb_launcher_icon.ico", "ysb_launcher_icon.ico"],
        "ysb_splash.png": ["assets/ysb_splash.png", "ysb_splash.png"],
        "ysb_splash_boot.png": ["assets/ysb_splash_boot.png", "ysb_splash_boot.png"],
        "ysb_logo.png": ["assets/ysb_logo.png", "ysb_logo.png"],
    }
    candidates = []
    candidates.extend(aliases.get(rel, []))
    candidates.append(rel)
    if not rel.startswith("assets/"):
        candidates.append(f"assets/{rel}")

    seen = set()
    unique_candidates = []
    for item in candidates:
        if item not in seen:
            seen.add(item)
            unique_candidates.append(item)

    roots = []
    if hasattr(sys, "_MEIPASS"):
        roots.append(Path(sys._MEIPASS))
    roots.append(APP_ROOT)

    for root in roots:
        for item in unique_candidates:
            p = root / item
            if p.exists():
                return str(p)

    # 마지막 fallback: 기존 호출과 호환되도록 프로젝트 루트 기준 경로를 반환한다.
    return str(APP_ROOT / rel)


def close_pyinstaller_boot_splash():
    """
    PyInstaller --splash로 뜬 부트로더 스플래시를 닫는다.
    이 화면은 EXE 압축 해제 중에 먼저 뜨고,
    파이썬 코드가 시작되면 여기서 닫은 뒤 Qt 진행바 스플래시로 넘긴다.
    """
    try:
        import pyi_splash
        lang = "ko"
        try:
            p = get_cache_file("app_options.json")
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    lang = str(json.load(f).get("ui_language", "ko")).lower()
        except Exception:
            lang = "ko"
        pyi_splash.update_text("Preparing main window..." if lang.startswith("en") else "메인 로딩 화면 준비 중...")
        pyi_splash.close()
    except Exception:
        pass


APP_OPTIONS_FILE_NAME = "app_options.json"


class CloudOAuthCancelled(Exception):
    """사용자가 OAuth 로그인을 취소했거나 브라우저 인증이 완료되지 않은 경우."""
    pass


def app_options_file():
    return get_cache_file(APP_OPTIONS_FILE_NAME)
TRANSLATION_PROMPT_KEY = "translation_prompt"
TRANSLATION_GLOSSARY_TEXT_KEY = "translation_glossary_text"
TRANSLATION_GLOSSARY_PATH_KEY = "translation_glossary_path"
UI_THEME_KEY = "ui_theme"
THEME_DARK = "dark"
THEME_LIGHT = "light"
UI_LANGUAGE_KEY = "ui_language"
LANG_KO = "ko"
LANG_EN = "en"
ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY = "analysis_text_mask_expand_ratio"
ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY = "analysis_paint_mask_expand_ratio"
ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY = "analysis_text_mask_min_expand_px"
ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY = "analysis_paint_mask_min_expand_px"
DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO = 0.20
DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO = 0.10
DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX = 5
DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX = 1
LOG_PANEL_COLLAPSED_KEY = "log_panel_collapsed"
# 기본값: 배포판 첫 실행 시 작업 로그창은 접힌 상태로 시작한다.
# 사용자가 로그 열기/숨기기를 누르면 app_options.json에 저장된 상태를 우선한다.
DEFAULT_LOG_PANEL_COLLAPSED = True
SHOW_PATHS_IN_LOG_KEY = "show_paths_in_log"
SHOW_CACHE_PATHS_IN_SETTINGS_KEY = "show_cache_paths_in_settings"
OPERATION_MODE_KEY = "operation_mode"
OPERATION_MODE_PAINT = "paint"
OPERATION_MODE_CAD = "cad"
DEFAULT_OPERATION_MODE = OPERATION_MODE_PAINT


def normalize_operation_mode(value):
    """Normalize the global canvas interaction preset.

    paint: left-drag panning + Ctrl/Alt wheel zoom + hold-drag areas.
    cad: middle-button panning + plain wheel zoom + click-click areas.
    """
    v = str(value or DEFAULT_OPERATION_MODE).strip().lower()
    aliases = {
        "paint": OPERATION_MODE_PAINT,
        "painting": OPERATION_MODE_PAINT,
        "painter": OPERATION_MODE_PAINT,
        "그림판": OPERATION_MODE_PAINT,
        "그림판 방식": OPERATION_MODE_PAINT,
        "cad": OPERATION_MODE_CAD,
        "캐드": OPERATION_MODE_CAD,
        "cad 방식": OPERATION_MODE_CAD,
        "캐드 방식": OPERATION_MODE_CAD,
    }
    return aliases.get(v, DEFAULT_OPERATION_MODE)


def operation_mode_label(value, lang=None):
    mode = normalize_operation_mode(value)
    if str(lang or "").lower().startswith("en"):
        return "CAD mode" if mode == OPERATION_MODE_CAD else "Paint mode"
    return "CAD 방식" if mode == OPERATION_MODE_CAD else "그림판 방식"


PAGE_DISPLAY_MODE_ORIGINAL = "original_name"
PAGE_DISPLAY_MODE_PAGE_ORIGINAL = "1p_original_name"
PAGE_DISPLAY_MODE_PAGE_NUMBER = "page001"
PAGE_DISPLAY_MODE_OPTIONS = (
    PAGE_DISPLAY_MODE_ORIGINAL,
    PAGE_DISPLAY_MODE_PAGE_ORIGINAL,
    PAGE_DISPLAY_MODE_PAGE_NUMBER,
)
PAGE_TAB_DISPLAY_MODE_KEY = "page_tab_display_name_mode"
OUTPUT_DISPLAY_MODE_KEY = "output_display_name_mode"
OUTPUT_IMAGE_FORMAT_KEY = "output_image_format"
CLEAN_IMAGE_FORMAT_KEY = "clean_image_format"
OUTPUT_IMAGE_QUALITY_KEY = "output_image_quality"
CLEAN_IMAGE_QUALITY_KEY = "clean_image_quality"
OUTPUT_TEXT_RENDER_QUALITY_KEY = "output_text_render_quality"
OUTPUT_IMAGE_FORMAT_OPTIONS = ("png", "jpg", "webp")
OUTPUT_TEXT_RENDER_QUALITY_OPTIONS = ("normal", "2x", "3x", "4x")
DEFAULT_OUTPUT_IMAGE_FORMAT = "png"
DEFAULT_OUTPUT_IMAGE_QUALITY = 95
DEFAULT_OUTPUT_TEXT_RENDER_QUALITY = "2x"
LAST_PROJECT_CREATE_DIR_KEY = "last_project_create_dir"
DEFAULT_PAGE_DISPLAY_MODE = PAGE_DISPLAY_MODE_PAGE_ORIGINAL
IMAGE_DROP_EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")


def normalize_page_display_mode(value):
    value = str(value or DEFAULT_PAGE_DISPLAY_MODE).strip()
    if value in PAGE_DISPLAY_MODE_OPTIONS:
        return value
    return DEFAULT_PAGE_DISPLAY_MODE


def normalize_output_image_format(value):
    value = str(value or DEFAULT_OUTPUT_IMAGE_FORMAT).strip().lower().lstrip(".")
    aliases = {
        "jpeg": "jpg",
        "jpe": "jpg",
        "wep": "webp",
        "wbp": "webp",
    }
    value = aliases.get(value, value)
    if value in OUTPUT_IMAGE_FORMAT_OPTIONS:
        return value
    return DEFAULT_OUTPUT_IMAGE_FORMAT


def normalize_output_image_quality(value, default_value=DEFAULT_OUTPUT_IMAGE_QUALITY):
    try:
        v = int(value)
    except Exception:
        v = int(default_value)
    return max(1, min(100, v))

def normalize_output_text_render_quality(value):
    value = str(value or DEFAULT_OUTPUT_TEXT_RENDER_QUALITY).strip().lower()
    aliases = {
        "default": "normal",
        "basic": "normal",
        "1x": "normal",
        "standard": "normal",
        "high": "2x",
        "best": "3x",
        "ultra": "4x",
        "ssaa2": "2x",
        "ssaa3": "3x",
        "ssaa4": "4x",
    }
    value = aliases.get(value, value)
    if value in OUTPUT_TEXT_RENDER_QUALITY_OPTIONS:
        return value
    return DEFAULT_OUTPUT_TEXT_RENDER_QUALITY


def output_text_render_scale(value):
    value = normalize_output_text_render_quality(value)
    if value == "4x":
        return 4.0
    if value == "3x":
        return 3.0
    if value == "2x":
        return 2.0
    return 1.0


def output_image_extension(fmt):
    fmt = normalize_output_image_format(fmt)
    if fmt == "jpg":
        return ".jpg"
    if fmt == "webp":
        return ".webp"
    return ".png"


def qt_image_format_name(fmt):
    fmt = normalize_output_image_format(fmt)
    if fmt == "jpg":
        return "JPG"
    if fmt == "webp":
        return "WEBP"
    return "PNG"


def pil_image_format_name(fmt):
    fmt = normalize_output_image_format(fmt)
    if fmt == "jpg":
        return "JPEG"
    if fmt == "webp":
        return "WEBP"
    return "PNG"


def safe_page_file_stem(value, fallback="page"):
    stem = Path(str(value or fallback)).stem.strip() or fallback
    # Windows 파일명 금지 문자와 제어 문자를 안전하게 치환한다.
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" .")
    return stem or fallback

PATH_LIKE_RE = re.compile(r'(?:[A-Za-z]:[\\/][^\s,，;；\]\)\}]+|\\\\[^\s,，;；\]\)\}]+|/(?:mnt|home|Users|tmp|var|etc|opt|Volumes|private)/[^\s,，;；\]\)\}]+)')

def _looks_like_path_start(text):
    return bool(PATH_LIKE_RE.match(str(text or "").strip()))

def hide_paths_in_log_text(text, hidden_label="[경로 숨김]"):
    """로그 경로 표시 OFF일 때 로컬 파일/폴더 경로를 숨긴다.
    - `완료: C:/...`처럼 경로가 본문 뒤에 붙은 경우는 결과 문구만 남긴다.
    - `5개 / C:/...`처럼 보조 경로가 붙은 경우는 보조 경로만 제거한다.
    - 예외적인 경로 조각은 마지막 안전장치로 [경로 숨김]으로 치환한다.
    """
    hidden_label = str(hidden_label or "[경로 숨김]")
    out_lines = []
    for raw_line in str(text or "").splitlines() or [str(text or "")]:
        line = raw_line
        # 대표 패턴: "저장 완료: C:\..." / "Cache path: /home/..."
        m = re.search(r'[:：]\s*(?=' + PATH_LIKE_RE.pattern + r')', line)
        if m:
            line = line[:m.start()].rstrip()
        else:
            # 대표 패턴: "완료: 12개 / C:\..."
            line = re.sub(r'\s*/\s*' + PATH_LIKE_RE.pattern, '', line)
            # 문장 안에 남은 경로 조각은 숨김 표기로 치환한다.
            line = PATH_LIKE_RE.sub(hidden_label, line)
        line = re.sub(r'\s*[:：/\-]+\s*$', '', line).rstrip()
        out_lines.append(line)
    return "\n".join(out_lines)

# UI/log/message translation table is centralized in lang_text.py.
# Add new user-visible Korean/English strings there, not directly in this file.
from ysb.i18n.lang_text import UI_KO_EN, UI_EN_KO

def normalize_ui_language(value):
    value = str(value or LANG_KO).lower()
    if value in (LANG_KO, "korean", "한국어"):
        return LANG_KO
    if value in (LANG_EN, "english", "en-us", "en_us"):
        return LANG_EN
    return LANG_KO


def current_ui_language():
    return normalize_ui_language(load_app_options().get(UI_LANGUAGE_KEY, LANG_KO))


def translate_ui_text(text, lang=None):
    lang = normalize_ui_language(lang or current_ui_language())
    text = str(text)
    if lang == LANG_EN:
        return UI_KO_EN.get(text, text)
    return UI_EN_KO.get(text, text)


def _replace_dynamic_ui_piece(s, src, dst):
    """Replace UI glossary fragments without corrupting technical words.

    Dynamic message translation is intentionally partial, but short English UI
    keys such as "To" must not rewrite words like "Torch" in error details.
    For ASCII word-like keys, replace only whole tokens.  Longer Korean or
    phrase keys keep the existing substring behavior.
    """
    src = str(src or "")
    if not src:
        return s
    if re.fullmatch(r"[A-Za-z0-9_]+", src):
        return re.sub(r"(?<![A-Za-z0-9_])" + re.escape(src) + r"(?![A-Za-z0-9_])", str(dst), s)
    return s.replace(src, str(dst))


def translate_ui_dynamic_text(text, lang=None):
    """고정 문구가 문장/로그 안에 섞여 있을 때 부분 치환한다.
    사용자 원문/번역문에는 사용하지 않고, UI/알림/로그용으로만 사용한다.
    """
    lang = normalize_ui_language(lang or current_ui_language())
    s = str(text)
    if lang == LANG_EN:
        for ko, en in sorted(UI_KO_EN.items(), key=lambda kv: len(kv[0]), reverse=True):
            s = _replace_dynamic_ui_piece(s, ko, en)
        s = re.sub(r"(\d+)개", r"\1 items", s)
        s = re.sub(r"총\s*(\d+)페이지", r"total \1 page(s)", s)
        s = re.sub(r"(\d+)페이지", r"\1 page(s)", s)
        s = re.sub(r"^(.+?)을\(를\) total (\d+) page\(s\)에 실행합니다\.?$", r"Run \1 on total \2 page(s)?", s)
        s = re.sub(r"^(.+?)을\(를\) (\d+) page\(s\)에 실행합니다\.?$", r"Run \1 on total \2 page(s)?", s)
        s = s.replace(" page(s)에", " page(s)")
        s = s.replace(" pages에", " pages")
        s = s.replace("을(를)", "")
        # Korean grammar fragments left after partial replacement.
        s = s.replace("현재 page(s)", "current page")
        s = s.replace("current page(s)", "current page")
        s = re.sub(r"(current page)\s+(\d+) items", r"\1 \2 items", s)
        s = re.sub(r"(\d+) page\(s\) 기준으로 생성합니다\.?", r"total \1 page(s)?", s)
        s = re.sub(r"Create text extraction TXT files for\s+(\d+) page\(s\).*", r"Create text extraction TXT files for total \1 page(s)?", s)
        s = re.sub(r"Run (.+?) on\s+(\d+) page\(s\).*", r"Run \1 on total \2 page(s)?", s)
        s = re.sub(r"(Batch [A-Za-z ]+)을\(를\) total (\d+) page\(s\)에 실행합니다\.?", r"Run \1 on total \2 page(s)?", s)
        s = re.sub(r"(Batch [A-Za-z ]+)을\(를\) (\d+) page\(s\)에 실행합니다\.?", r"Run \1 on total \2 page(s)?", s)
        s = re.sub(r": (\d+) page\(s\) / (\d+) items", r": \1 page(s) / \2 items", s)
        # Mixed Korean/English fragments caused by partial dictionary replacement.
        cleanup_pairs = {
            "API 설정 캐시 Save complete": "API settings cache saved",
            "API 설정 캐시 Save 완료": "API settings cache saved",
            "API 설정 캐시 저장 완료": "API settings cache saved",
            "CLOVA OCR로 re-analyzing selected area": "Re-analyzing selected area with CLOVA OCR",
            "CLOVA OCR로 재분석": "Re-analyzing with CLOVA OCR",
            "Google Vision OCR로 재분석": "Re-analyzing with Google Vision OCR",
            "Google Vision OCR로 re-analyzing selected area": "Re-analyzing selected area with Google Vision OCR",
            "Google Vision OCR로 re-analyzing selected area...": "Re-analyzing selected area with Google Vision OCR...",
            "CLOVA OCR로 re-analyzing selected area": "Re-analyzing selected area with CLOVA OCR",
            "CLOVA OCR로 re-analyzing selected area...": "Re-analyzing selected area with CLOVA OCR...",
            "분석 result applied": "analysis result applied",
            "분석 결과 반영 complete": "analysis result applied",
            "analysis 결과 반영 complete": "analysis result applied",
            "Text mask Auto Save": "Text mask auto-saved",
            "Painting mask Auto Save": "Painting mask auto-saved",
            "인페인팅 result를 Original tab의 작업중 기준 이미지로 가져왔습니다.": "Inpaint result has been imported as the working source image for the Original tab.",
            "원본 tab의 기준 이미지를 실제 Original로 되돌렸습니다.": "The Original tab base image has been restored to the real original image.",
            "현재 프로젝트": "current project",
            "Text Move됨": "Text moved",
            "Text Move applied": "Text move applied",
            "Text Transform Mode ON": "Text transform mode ON",
            "Text Transform Mode OFF": "Text transform mode OFF",
            "Text Transform Mode 종료": "Text transform mode ended",
            "Text Transform 적용": "Text transform applied",
            "Text 영역/비율 조정 Undo": "Text area/scale undo",
            "새 Text 영역 생성 대기": "Waiting for new text area",
            "새 Text 추가 complete": "New text added",
            "새 Text 입력 Canceled": "New text input canceled",
            "Text 직접 Edit 시작": "Direct text edit started",
            "Text 직접 수정 complete": "Direct text edit complete",
            "Text 직접 수정 변화 없음": "No direct text edit changes",
            "Text 직접 수정 Canceled": "Direct text edit canceled",
            "Text 붙여넣기 위치 지정": "Set paste text position",
            "붙여넣기 위치 지정": "Set paste text position",
            "Paste Text complete": "Paste text complete",
            "Select 해제": "Selection cleared",
            "실행 Canceled할 내역이 없습니다.": "There is no action to undo.",
            "실행 Canceled": "Action canceled",
            "최종 페인팅 실행 Canceled": "Final paint action canceled",
            "Move 모드": "Move Mode",
            "Text Move 모드": "Text Move Mode",
            "Magic Wand Select 되돌림": "Magic Wand selection undone",
            "Magic Wand Select 추가": "Magic Wand selection added",
            "Magic Wand 영역 확장": "Magic Wand selection expanded",
            "도구: Brush": "Tool: Brush",
            "도구: Eraser": "Tool: Eraser",
            "도구: Move": "Tool: Move",
            "Tool: 이동": "Tool: Move",
            "최종 페인팅 Auto Save": "Final paint auto-saved",
            "Text mask Auto Save": "Text mask auto-saved",
            "Painting mask Auto Save": "Painting mask auto-saved",
        }
        for a, b in cleanup_pairs.items():
            s = s.replace(a, b)
        s = re.sub(r"현재 page\(s\)\s*(\d+) items", r"current page \1 items", s)
        s = s.replace("Select 해제", "Selection cleared")
        s = s.replace("실행 Canceled할 내역이 없습니다.", "There is no action to undo.")
        s = s.replace("실행 Canceled", "Action canceled")
        s = s.replace("Move 모드", "Move Mode")
        return s
    # 한국어 모드로 돌아갈 때 이미 영어로 바뀐 일부 고정 문구를 복구한다.
    for en, ko in sorted(UI_EN_KO.items(), key=lambda kv: len(kv[0]), reverse=True):
        s = _replace_dynamic_ui_piece(s, en, ko)
    return s



def read_text_file_for_cache(path):
    """TXT 단어장/참고자료를 가능한 한 안전하게 읽는다."""
    encodings = ("utf-8-sig", "utf-8", "cp949", "euc-kr")
    last_error = None
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc) as f:
                return f.read()
        except UnicodeDecodeError as e:
            last_error = e
        except Exception:
            raise
    # 그래도 실패하면 치환 문자로라도 읽는다.
    try:
        with open(path, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception:
        if last_error:
            raise last_error
        raise


def load_app_options():
    try:
        p = app_options_file()
        if p.exists():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_app_options(options):
    try:
        p = app_options_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(dict(options or {}), f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def clamp_analysis_mask_ratio(value, default_value):
    """분석 마스크 확장 비율을 안전 범위로 보정한다.
    0.00은 확장 없음, 2.00은 매우 강한 확장이다.
    """
    try:
        v = float(value)
    except Exception:
        v = float(default_value)
    if v < 0.0:
        v = 0.0
    if v > 2.0:
        v = 2.0
    return round(v, 3)


def clamp_analysis_mask_min_px(value, default_value):
    """분석 마스크 최소 확장 크기를 px 단위로 보정한다.
    0px은 최소 확장 강제를 끈 상태다.
    """
    try:
        v = int(round(float(value)))
    except Exception:
        v = int(default_value)
    if v < 0:
        v = 0
    if v > 100:
        v = 100
    return v


CURRENT_EDITION = get_current_edition()
APP_EDITION = CURRENT_EDITION.key
APP_EDITION_LABEL = CURRENT_EDITION.label
APP_VERSION = CURRENT_EDITION.app_version
APP_NAME_KO = CURRENT_EDITION.app_name_ko
APP_NAME_EN = CURRENT_EDITION.app_name_en
YSB_TOOL_SITE_URL = "https://ysb-tool.com/"
YSB_TOOL_MANUAL_URL = "https://ysb-tool.com/#manual"
YSB_TOOL_SUPPORT_URL = "https://ysb-tool.com/support/"
YSB_TOOL_BUG_REPORT_URL = "https://github.com/amule949/YSB-Translator-Tool/issues/new"
YSB_TOOL_DOWNLOAD_PAGE_URL = "https://ysb-tool.com/#download"
YSB_TOOL_VERSION_JSON_URL = CURRENT_EDITION.version_json_url
UPDATE_IGNORED_VERSION_KEY = CURRENT_EDITION.update_ignore_key


def _ysb_version_display(value):
    """Normalize remote version text to a compact v2.0.1 style label."""
    text = str(value or "").strip()
    if not text:
        return ""
    match = re.search(r"v?\d+(?:\.\d+){1,3}", text, re.IGNORECASE)
    if match:
        version = match.group(0)
        return version if version.lower().startswith("v") else "v" + version
    return text


def fetch_ysb_version_info(current_version=None, timeout=6):
    """Fetch and normalize ysb-tool.com/version.json.

    Used by the background startup check. Network failures are raised so
    startup checks can silently ignore them.
    """
    version = str(current_version or APP_VERSION)
    req = urllib.request.Request(
        YSB_TOOL_VERSION_JSON_URL,
        headers={"User-Agent": f"YSB-Tool/{version} VersionCheck"},
    )
    with urllib.request.urlopen(req, timeout=timeout) as response:
        raw = response.read(1024 * 1024).decode("utf-8", errors="replace")
    info = json.loads(raw)
    if not isinstance(info, dict):
        raise ValueError("version.json root must be an object")
    latest_version_raw = str(info.get("latest_version") or info.get("version") or "").strip()
    if not latest_version_raw:
        raise ValueError("version.json에 latest_version 값이 없습니다.")
    latest_version = _ysb_version_display(latest_version_raw)
    display_name = _ysb_version_display(info.get("display_name") or latest_version_raw)
    info["latest_version"] = latest_version
    info["display_name"] = display_name or latest_version
    info["download_page_url"] = str(info.get("download_page_url") or YSB_TOOL_DOWNLOAD_PAGE_URL).strip() or YSB_TOOL_DOWNLOAD_PAGE_URL
    info["download_url"] = str(info.get("download_url") or "").strip()
    return info


class VersionCheckThread(QThread):
    version_info_ready = pyqtSignal(dict)
    version_check_failed = pyqtSignal(str)

    def __init__(self, current_version=None, timeout=5, parent=None):
        super().__init__(parent)
        self.current_version = str(current_version or APP_VERSION)
        self.timeout = timeout

    def run(self):
        try:
            info = fetch_ysb_version_info(self.current_version, timeout=self.timeout)
            self.version_info_ready.emit(info)
        except Exception as e:
            self.version_check_failed.emit(str(e))


def _ysb_version_tuple(value):
    """Return a comparable version tuple from strings like v2.0.1 or 2.0.1."""
    nums = re.findall(r"\d+", str(value or ""))
    if not nums:
        return (0,)
    return tuple(int(x) for x in nums[:4])


class UpdateAvailableDialog(QDialog):
    """Startup update notification dialog.

    This appears only when the remote latest version is newer than the current
    app version, and it can suppress the same latest version via app cache.
    """

    def __init__(self, parent=None, current_version=None, version_info=None):
        super().__init__(parent)
        self.parent_window = parent
        self.current_version = str(current_version or APP_VERSION)
        self.version_info = dict(version_info or {})
        self.open_download_requested = False
        self._build_ui()

    def _tr(self, text):
        parent = self.parent_window
        try:
            return parent.tr_ui(text) if parent is not None and hasattr(parent, "tr_ui") else text
        except Exception:
            return text

    def _build_ui(self):
        self.setWindowTitle(self._tr("업데이트 알림"))
        self.setMinimumWidth(480)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(18, 18, 18, 18)
        layout.setSpacing(12)

        title = QLabel(self._tr("새 버전을 사용할 수 있습니다."))
        f = title.font()
        f.setPointSize(max(11, f.pointSize() + 2))
        f.setBold(True)
        title.setFont(f)
        layout.addWidget(title)

        msg = QLabel(self._tr("다운로드 페이지에서 최신 버전을 받을 수 있습니다."))
        msg.setWordWrap(True)
        layout.addWidget(msg)

        latest_version = str(self.version_info.get("latest_version") or "").strip()
        latest_display = str(self.version_info.get("display_name") or latest_version).strip() or latest_version

        form = QFormLayout()
        form.addRow(self._tr("현재 버전"), QLabel(self.current_version))
        form.addRow(self._tr("최신 버전"), QLabel(latest_display))
        layout.addLayout(form)

        bottom = QHBoxLayout()
        self.ignore_checkbox = QCheckBox(self._tr("이번 버전은 다시 알리지 않음"))
        bottom.addWidget(self.ignore_checkbox)
        bottom.addStretch(1)

        download_button = QPushButton(self._tr("다운로드 페이지로 이동"))
        download_button.clicked.connect(self._download)
        close_button = QPushButton(self._tr("닫기"))
        close_button.clicked.connect(self.accept)
        bottom.addWidget(download_button)
        bottom.addWidget(close_button)
        layout.addLayout(bottom)

    def ignore_this_version(self):
        try:
            return bool(self.ignore_checkbox.isChecked())
        except Exception:
            return False

    def _download(self):
        self.open_download_requested = True
        self.accept()


YSBT_EXTENSION = ".ysbt"
YSBT_PROG_ID = "YSBTranslator.YSBTProject"
LEGACY_YSB_EXTENSION = ".ysb"
LEGACY_YSB_PROG_ID = "YSBTranslator.Project"

DARK_MESSAGEBOX_QSS = """
QMessageBox,
QMessageBox QWidget {
    background-color:#252328;
    color:#F4EEF2;
}
QMessageBox QLabel {
    background-color:#252328;
    color:#F4EEF2;
    line-height:1.35em;
}
QMessageBox QLabel,
QMessageBox QFrame {
    border:0px;
}
QMessageBox QTextEdit,
QMessageBox QPlainTextEdit,
QMessageBox QScrollArea {
    background-color:#211F23;
    color:#F4EEF2;
    border:1px solid #3A363B;
    selection-background-color:#5B3136;
    selection-color:#ffffff;
}
QMessageBox QPushButton {
    background-color:#322E34;
    color:#F4EEF2;
    border:1px solid #615A60;
    border-radius:0px;
    padding:4px 10px;
    min-width:56px;
    min-height:22px;
}
QMessageBox QPushButton:hover { background-color:#3a404b; border-color:#7B7078; }
QMessageBox QPushButton:pressed { background-color:#302C31; }
QMessageBox QPushButton:disabled { background-color:#252932; color:#827A80; border-color:#343a45; }
QMessageBox QToolTip { background-color:#242329; color:#ffffff; border:1px solid #555056; border-radius:0px; padding:5px; }
"""

LIGHT_MESSAGEBOX_QSS = """
QMessageBox,
QMessageBox QWidget {
    background-color:#F5EFF3;
    color:#111827;
}
QMessageBox QLabel {
    background-color:#F5EFF3;
    color:#111827;
    line-height:1.35em;
}
QMessageBox QLabel,
QMessageBox QFrame {
    border:0px;
}
QMessageBox QTextEdit,
QMessageBox QPlainTextEdit,
QMessageBox QScrollArea {
    background-color:#ffffff;
    color:#111827;
    border:1px solid #D1C9CE;
    selection-background-color:#F5E8EA;
    selection-color:#111827;
}
QMessageBox QPushButton {
    background-color:#ffffff;
    color:#111827;
    border:1px solid #D1C9CE;
    border-radius:0px;
    padding:4px 10px;
    min-width:56px;
    min-height:22px;
}
QMessageBox QPushButton:hover { background-color:#FBF5F6; border-color:#D7A3A9; }
QMessageBox QPushButton:pressed { background-color:#F5E8EA; }
QMessageBox QPushButton:disabled { background-color:#F0EAED; color:#A29A9F; border-color:#E0DADF; }
QMessageBox QToolTip { background-color:#ffffff; color:#111827; border:1px solid #D1C9CE; border-radius:0px; padding:5px; }
"""


def _parent_prefers_light_theme(parent=None):
    try:
        if parent is not None and hasattr(parent, "is_light_theme"):
            return bool(parent.is_light_theme())
    except Exception:
        pass
    try:
        theme = getattr(parent, "ui_theme", "") if parent is not None else ""
        return str(theme or "").lower() == "light"
    except Exception:
        return False


def dialog_palette(light=False):
    pal = QPalette()
    if light:
        pal.setColor(QPalette.ColorRole.Window, QColor("#F5EFF3"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#111827"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#F8F3F5"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#111827"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#ffffff"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#111827"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#F5E8EA"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#111827"))
    else:
        pal.setColor(QPalette.ColorRole.Window, QColor("#252328"))
        pal.setColor(QPalette.ColorRole.WindowText, QColor("#F4EEF2"))
        pal.setColor(QPalette.ColorRole.Base, QColor("#211F23"))
        pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#252328"))
        pal.setColor(QPalette.ColorRole.Text, QColor("#F4EEF2"))
        pal.setColor(QPalette.ColorRole.Button, QColor("#322E34"))
        pal.setColor(QPalette.ColorRole.ButtonText, QColor("#F4EEF2"))
        pal.setColor(QPalette.ColorRole.Highlight, QColor("#5B3136"))
        pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
    return pal


def apply_message_box_palette(msg, light=False):
    """현재 테마에 맞춰 QMessageBox의 글자/배경 대비를 고정한다."""
    try:
        msg.setStyleSheet(LIGHT_MESSAGEBOX_QSS if light else DARK_MESSAGEBOX_QSS)
    except Exception:
        pass
    try:
        pal = dialog_palette(light)
        msg.setPalette(pal)
        for child in msg.findChildren(QWidget):
            child.setAutoFillBackground(True)
            child.setPalette(pal)
    except Exception:
        pass


def progress_dialog_qss(light=False):
    if light:
        return """
            QProgressDialog, QProgressDialog QWidget { background:#F5EFF3; color:#111827; }
            QProgressDialog QLabel { background:#F5EFF3; color:#111827; line-height:1.35em; }
            QProgressBar { background:#E7E2E5; color:#111827; border:1px solid #D1C9CE; border-radius:0px; height:16px; text-align:center; }
            QProgressBar::chunk { background:#8A4A52; border-radius:0px; }
            QPushButton { background:#ffffff; color:#111827; border:1px solid #D1C9CE; border-radius:0px; padding:5px 14px; min-width:72px; }
            QPushButton:hover { background:#FBF5F6; border-color:#D7A3A9; }
            QPushButton:pressed { background:#F5E8EA; }
        """
    return """
        QProgressDialog, QProgressDialog QWidget { background:#252328; color:#F4EEF2; }
        QProgressDialog QLabel { background:#252328; color:#F4EEF2; line-height:1.35em; }
        QProgressBar { background:#111827; color:#ffffff; border:1px solid #555056; border-radius:0px; height:16px; text-align:center; }
        QProgressBar::chunk { background:#8A4A52; border-radius:0px; }
        QPushButton { background:#373136; color:#F4EEF2; border:1px solid #615A60; border-radius:0px; padding:5px 14px; min-width:72px; }
        QPushButton:hover { background:#443A40; border-color:#7B7078; }
        QPushButton:pressed { background:#302C31; }
    """


def apply_progress_dialog_theme(dlg, light=False):
    """QProgressDialog도 현재 테마의 대비를 따르게 한다."""
    try:
        dlg.setStyleSheet(progress_dialog_qss(light))
    except Exception:
        pass
    try:
        pal = dialog_palette(light)
        dlg.setPalette(pal)
        for child in dlg.findChildren(QWidget):
            child.setAutoFillBackground(True)
            child.setPalette(pal)
    except Exception:
        pass


def _messagebox_ui_language(parent=None):
    lang = None
    for attr in ("ui_language", "_ui_language"):
        try:
            value = getattr(parent, attr, None)
            if value:
                lang = value
                break
        except Exception:
            pass
    return normalize_ui_language(lang or current_ui_language())


def styled_question(parent, title, text, buttons=None, defaultButton=None, default_yes=True):
    buttons = buttons or (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
    defaultButton = defaultButton or QMessageBox.StandardButton.Yes
    if buttons != (QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No):
        msg = QMessageBox(parent)
        msg.setIcon(QMessageBox.Icon.Question)
        msg.setWindowTitle(title)
        msg.setText(text)
        msg.setStandardButtons(buttons)
        try:
            msg.setDefaultButton(QMessageBox.StandardButton.Yes if default_yes and (buttons & QMessageBox.StandardButton.Yes) else defaultButton)
        except Exception:
            pass
        apply_message_box_palette(msg, _parent_prefers_light_theme(parent))
        force_message_box_front(msg)
        return msg.exec()

    lang = _messagebox_ui_language(parent)
    confirm_text = translate_ui_text("확인(Y)", lang)
    cancel_text = translate_ui_text("취소(N)", lang)
    confirm_tip = translate_ui_text("Enter 또는 Y 키로 확인합니다.", lang)
    cancel_tip = translate_ui_text("N 키로 취소합니다.", lang)

    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setWindowTitle(title)
    msg.setText(text)
    apply_message_box_palette(msg, _parent_prefers_light_theme(parent))

    yes_button = msg.addButton(confirm_text, QMessageBox.ButtonRole.YesRole)
    no_button = msg.addButton(cancel_text, QMessageBox.ButtonRole.NoRole)
    yes_button.setShortcut(QKeySequence("Y"))
    no_button.setShortcut(QKeySequence("N"))
    yes_button.setToolTip(confirm_tip)
    no_button.setToolTip(cancel_tip)
    msg.setDefaultButton(yes_button)
    msg.setEscapeButton(no_button)

    try:
        yes_button.setAutoDefault(True)
        no_button.setAutoDefault(False)
    except Exception:
        pass

    force_message_box_front(msg)
    result = msg.exec()
    clicked = msg.clickedButton()
    if clicked is yes_button:
        return QMessageBox.StandardButton.Yes
    if clicked is no_button:
        return QMessageBox.StandardButton.No
    return QMessageBox.StandardButton.Yes if result == int(QDialog.DialogCode.Accepted) else QMessageBox.StandardButton.No


def apply_message_box_dark_palette(msg):
    """호환용: 기존 호출은 다크 팔레트로 처리한다."""
    apply_message_box_palette(msg, light=False)


def force_message_box_front(msg):
    """알림/확인창이 메인 창이나 스플래시 뒤에 가려지지 않게 앞으로 올린다."""
    try:
        msg.setWindowModality(Qt.WindowModality.ApplicationModal)
    except Exception:
        pass
    try:
        msg.setWindowFlag(Qt.WindowType.WindowStaysOnTopHint, True)
    except Exception:
        pass
    try:
        msg.show()
        msg.raise_()
        msg.activateWindow()
        QApplication.processEvents()
    except Exception:
        pass


def workspace_restart_confirmation(parent, current_path, target_path, lang=None):
    """작업 폴더 위치 변경 시 재기동 여부를 묻는다.

    확인하면 변경을 예약하고 재기동한다. 취소하면 변경하지 않고 이전 설정값으로 되돌린다.
    Y/N 단축키와 Enter 기본값을 지원한다.
    """
    lang = normalize_ui_language(lang or _messagebox_ui_language(parent))
    title = translate_ui_text("작업 폴더 위치 변경", lang)
    restart_message_key = "폴더 위치 변경으로 프로그램을 재기동합니다.\n취소할 시 이전 설정한 폴더 위치값으로 원복합니다."
    restart_message = translate_ui_text(restart_message_key, lang)
    current_label = translate_ui_text("현재 위치", lang)
    target_label = translate_ui_text("변경 위치", lang)
    text = (
        f"{restart_message}\n\n"
        f"{current_label}:\n{current_path}\n\n"
        f"{target_label}:\n{target_path}"
    )
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setWindowTitle(title)
    msg.setText(text)
    apply_message_box_dark_palette(msg)
    yes_button = msg.addButton(translate_ui_text("재기동(Y)", lang), QMessageBox.ButtonRole.YesRole)
    no_button = msg.addButton(translate_ui_text("취소(N)", lang), QMessageBox.ButtonRole.NoRole)
    yes_button.setShortcut(QKeySequence("Y"))
    no_button.setShortcut(QKeySequence("N"))
    yes_button.setToolTip(translate_ui_text("Enter 또는 Y 키로 재기동합니다.", lang))
    no_button.setToolTip(translate_ui_text("N 키로 취소하고 이전 설정값으로 되돌립니다.", lang))
    msg.setDefaultButton(yes_button)
    msg.setEscapeButton(no_button)
    try:
        yes_button.setAutoDefault(True)
        no_button.setAutoDefault(False)
    except Exception:
        pass
    msg.exec()
    return msg.clickedButton() is yes_button


def _restart_python_executable():
    """재기동에 사용할 Python 실행 파일을 고른다.

    콘솔 창이 잠깐 떴다가 사라지는 현상을 줄이기 위해 Windows에서는
    같은 폴더의 pythonw.exe가 있으면 우선 사용한다.
    """
    exe = Path(sys.executable)
    if is_windows() and exe.name.lower() == "python.exe":
        pythonw = exe.with_name("pythonw.exe")
        if pythonw.exists():
            return str(pythonw)
    return str(exe)


def restart_application_detached():
    """현재 프로세스를 종료하고 새 프로세스를 독립 재실행한다.

    v2.0.1:
    - 가능하면 공식 YSB_Launcher.exe를 통해 재기동한다.
      그러면 위치 변경 후 재기동 중에도 런처 진행률 화면이 표시된다.
    - 런처가 없으면 기존처럼 메인 EXE를 직접 재실행한다.
    """
    app = QApplication.instance()
    try:
        current_pid = os.getpid()

        if getattr(sys, "frozen", False):
            app_dir = str(Path(sys.executable).resolve().parent)
            opener_path = None
            try:
                opener_path = get_file_opener_path()
            except Exception:
                opener_path = None

            if opener_path and Path(opener_path).exists():
                launch_program = str(Path(opener_path).resolve())
                launch_args = ["--restart-main", str(current_pid)]
                app_dir = str(Path(opener_path).resolve().parent)
            else:
                launch_program = str(Path(sys.executable).resolve())
                launch_args = []
        else:
            launch_program = _restart_python_executable()
            launch_args = [str(APP_ROOT / "main.py")]
            app_dir = str(APP_ROOT)

        env = os.environ.copy()

        if getattr(sys, "frozen", False):
            env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"

        for key in (
            "QT_PLUGIN_PATH",
            "QT_QPA_PLATFORM_PLUGIN_PATH",
            "QT_QPA_FONTDIR",
            "QT_DEBUG_PLUGINS",
        ):
            env.pop(key, None)

        if is_windows() and getattr(sys, "frozen", False):
            try:
                import ctypes
                ctypes.windll.kernel32.SetDllDirectoryW(None)
            except Exception:
                pass

        stdout_target = subprocess.DEVNULL
        stderr_target = subprocess.DEVNULL
        log_handles = []
        if is_windows():
            try:
                restart_dir = app_config_dir() / "restart_logs"
                restart_dir.mkdir(parents=True, exist_ok=True)
                stdout_target = open(restart_dir / "restart_stdout.log", "a", encoding="utf-8", errors="replace")
                stderr_target = open(restart_dir / "restart_stderr.log", "a", encoding="utf-8", errors="replace")
                log_handles.extend([stdout_target, stderr_target])
            except Exception:
                stdout_target = subprocess.DEVNULL
                stderr_target = subprocess.DEVNULL

        creationflags = 0
        if is_windows():
            for flag_name in ("CREATE_NO_WINDOW", "DETACHED_PROCESS", "CREATE_NEW_PROCESS_GROUP"):
                creationflags |= int(getattr(subprocess, flag_name, 0))

        subprocess.Popen(
            [launch_program] + list(launch_args),
            cwd=app_dir,
            stdin=subprocess.DEVNULL,
            stdout=stdout_target,
            stderr=stderr_target,
            close_fds=False,
            creationflags=creationflags,
            env=env,
        )

        for h in log_handles:
            try:
                h.close()
            except Exception:
                pass

    except Exception:
        return False

    try:
        if app:
            app.quit()
    except Exception:
        pass
    return True


QMessageBox.question = staticmethod(styled_question)

def is_windows():
    return sys.platform.startswith("win")


def get_executable_for_association() -> str:
    """파일 연결에 사용할 실제 실행 파일 경로를 돌려준다."""
    return sys.executable if getattr(sys, "frozen", False) else sys.executable


def get_association_command() -> str:
    """.ysbt 더블클릭 시 Windows가 실행할 명령어.

    v2.0.1 launcher policy:
    - YSB_Launcher.exe가 있으면 파일 연결은 공식 런처를 우선 사용한다.
    - 런처가 없으면 기존처럼 메인 EXE 또는 main.py로 fallback한다.
    """
    opener = get_file_opener_path()
    if opener is not None:
        if getattr(sys, "frozen", False):
            return f'"{opener}" "%1"'
        return f'"{sys.executable}" "{opener}" "%1"'
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" "%1"'
    script = os.path.abspath(sys.argv[0])
    return f'"{sys.executable}" "{script}" "%1"'


def _stable_ysbt_icon_path() -> str | None:
    """Windows 파일 연결용 .ysbt 아이콘을 안정적인 로컬 경로에 준비한다.

    PyInstaller onefile의 _MEIPASS 경로는 실행 종료 후 사라질 수 있으므로
    DefaultIcon에는 캐시 폴더로 복사한 .ico를 우선 등록한다.
    """
    try:
        src = resource_path("ysbt_file_icon.ico")
        if not os.path.exists(src):
            return None
        dst_dir = get_cache_dir() / "assets"
        dst_dir.mkdir(parents=True, exist_ok=True)
        dst = dst_dir / "ysbt_file_icon.ico"
        try:
            if (
                (not dst.exists())
                or os.path.getsize(src) != os.path.getsize(dst)
                or int(os.path.getmtime(src)) > int(os.path.getmtime(dst))
            ):
                shutil.copy2(src, dst)
        except Exception:
            if not dst.exists():
                return None
        return str(dst)
    except Exception:
        return None


def get_association_icon() -> str:
    """파일 탐색기에 표시할 .ysbt 전용 아이콘 위치."""
    ico = _stable_ysbt_icon_path()
    if ico and os.path.exists(ico):
        return f'"{ico}",0'

    ico = resource_path("ysbt_file_icon.ico")
    if os.path.exists(ico):
        return f'"{ico}",0'

    opener = get_file_opener_path()
    if getattr(sys, "frozen", False):
        if opener and os.path.exists(opener):
            return f'"{opener}",0'
        return f'"{sys.executable}",0'

    ico = resource_path("ysb_icon.ico")
    if os.path.exists(ico):
        return f'"{ico}",0'
    return f'"{sys.executable}",0'


def get_ysbt_file_association_prog_id() -> str | None:
    """현재 사용자 계정에 등록된 .ysbt의 ProgID를 반환한다."""
    if not is_windows():
        return None
    try:
        import winreg
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.ysbt") as k:
            value, _ = winreg.QueryValueEx(k, "")
        return value
    except Exception:
        return None


def is_ysbt_file_association_ours() -> bool:
    """.ysbt가 이 프로그램 계열의 ProgID에 연결되어 있는지 확인한다.

    실행 파일 경로가 현재 EXE와 달라도, 같은 YSBTranslator.YSBTProject 등록이면
    사용자 입장에서는 이미 .ysbt 연결이 켜진 상태로 본다.
    """
    return get_ysbt_file_association_prog_id() == YSBT_PROG_ID


def get_registered_ysbt_file_association_command() -> str | None:
    """레지스트리에 등록된 .ysbt 열기 명령을 가져온다.

    이 값이 현재 실행 중인 프로그램의 명령과 다르면, 보통 구버전 EXE나
    다른 위치의 포터블 EXE가 .ysbt에 연결된 상태라고 보면 된다.
    """
    if not is_windows():
        return None
    try:
        import winreg
        if not is_ysbt_file_association_ours():
            return None
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{YSBT_PROG_ID}\shell\open\command") as k:
            command, _ = winreg.QueryValueEx(k, "")
        return str(command)
    except Exception:
        return None


def get_registered_ysbt_file_association_icon() -> str | None:
    """레지스트리에 등록된 .ysbt DefaultIcon 값을 가져온다."""
    if not is_windows():
        return None
    try:
        import winreg
        if not is_ysbt_file_association_ours():
            return None
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{YSBT_PROG_ID}\DefaultIcon") as k:
            icon, _ = winreg.QueryValueEx(k, "")
        return str(icon)
    except Exception:
        return None


def _normalize_registry_value(value: str | None) -> str:
    return str(value or "").strip().strip('"').replace("/", "\\").lower()


def is_ysbt_file_association_icon_current() -> bool:
    registered = _normalize_registry_value(get_registered_ysbt_file_association_icon())
    current = _normalize_registry_value(get_association_icon())
    return bool(registered and current and registered == current)


def is_ysbt_file_association_registered_to_other_ysb() -> bool:
    """.ysbt가 역식붕이 툴 계열이지만 현재 실행 프로그램과 다른 명령을 가리키는지 확인한다.

    Windows가 버전 번호를 아는 것은 아니므로, 여기서 말하는 구버전 감지는
    실제로는 "등록된 실행 명령이 현재 실행 중인 프로그램과 다름"을 뜻한다.
    """
    if not is_ysbt_file_association_ours():
        return False
    registered = (get_registered_ysbt_file_association_command() or "").strip().lower()
    current = get_association_command().strip().lower()
    if bool(registered and registered != current):
        return True
    return not is_ysbt_file_association_icon_current()


def is_ysbt_file_association_registered() -> bool:
    """현재 사용자 계정의 .ysbt 연결이 현재 실행 중인 역식붕이 툴을 가리키는지 확인한다."""
    registered = get_registered_ysbt_file_association_command()
    if not registered:
        return False
    return registered.strip().lower() == get_association_command().strip().lower() and is_ysbt_file_association_icon_current()


def register_ysbt_file_association_raw():
    """메시지 없이 .ysbt 연결을 등록한다. Windows 전용."""
    if not is_windows():
        raise RuntimeError(".ysbt 확장자 연결 등록은 Windows에서만 지원합니다.")
    import winreg
    import ctypes
    command = get_association_command()
    icon = get_association_icon()
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, r"Software\Classes\.ysbt") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, YSBT_PROG_ID)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{YSBT_PROG_ID}") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, "YSBT Project File")
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{YSBT_PROG_ID}\DefaultIcon") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, icon)
    with winreg.CreateKey(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{YSBT_PROG_ID}\shell\open\command") as k:
        winreg.SetValueEx(k, "", 0, winreg.REG_SZ, command)
    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
        ctypes.windll.shell32.SHChangeNotify(0x00002000, 0x0000, None, None)
    except Exception:
        pass


def unregister_ysbt_file_association_raw(include_legacy=True):
    """메시지 없이 우리 툴이 등록한 확장자 연결을 제거한다. 다른 앱 연결은 건드리지 않는다."""
    if not is_windows():
        raise RuntimeError("확장자 연결 해제는 Windows에서만 지원합니다.")
    import winreg
    import ctypes

    def reg_get_default(subkey):
        try:
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, subkey) as k:
                value, _ = winreg.QueryValueEx(k, "")
            return value
        except Exception:
            return None

    def delete_tree(root, subkey):
        try:
            with winreg.OpenKey(root, subkey, 0, winreg.KEY_READ | winreg.KEY_WRITE) as k:
                while True:
                    try:
                        child = winreg.EnumKey(k, 0)
                    except OSError:
                        break
                    delete_tree(root, subkey + "\\" + child)
            winreg.DeleteKey(root, subkey)
            return True
        except FileNotFoundError:
            return False
        except OSError:
            return False

    removed = []
    if reg_get_default(r"Software\Classes\.ysbt") == YSBT_PROG_ID:
        if delete_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\.ysbt"):
            removed.append(".ysbt")
    if delete_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{YSBT_PROG_ID}"):
        removed.append(YSBT_PROG_ID)

    if include_legacy:
        if reg_get_default(r"Software\Classes\.ysb") == LEGACY_YSB_PROG_ID:
            if delete_tree(winreg.HKEY_CURRENT_USER, r"Software\Classes\.ysb"):
                removed.append(".ysb legacy")
        if delete_tree(winreg.HKEY_CURRENT_USER, rf"Software\Classes\{LEGACY_YSB_PROG_ID}"):
            removed.append(f"{LEGACY_YSB_PROG_ID} legacy")

    try:
        ctypes.windll.shell32.SHChangeNotify(0x08000000, 0x0000, None, None)
    except Exception:
        pass
    return removed


def is_workspace_root_configured() -> bool:
    cfg = load_workspace_config()
    return bool(cfg.get("workspace_root"))


def workspace_root_needs_setup() -> tuple[bool, str, str]:
    """첫 기동 설정창이 필요한지 검사한다. 이 함수는 작업 폴더를 새로 만들지 않는다.

    return: (needs_setup, message, message_kind)
    - message_kind = "info"    : 첫 설정처럼 정상 안내
    - message_kind = "warning" : 저장된 설정이 있지만 실제 폴더를 찾지 못한 상태
    """
    cfg = load_workspace_config()
    root_text = cfg.get("workspace_root")
    if not root_text:
        return True, "처음 실행입니다.\n작업 폴더 위치를 확인해 주세요.", "info"
    try:
        root = Path(root_text)
    except Exception:
        return True, "저장된 작업 폴더 경로를 읽을 수 없습니다.\n작업 폴더 위치를 다시 지정해 주세요.", "warning"
    if not root.exists() or not root.is_dir():
        return True, "저장된 작업 폴더를 찾을 수 없습니다.\n작업 폴더 위치를 다시 지정해 주세요.", "warning"
    return False, "", "info"


def normalize_workspace_root_from_user(path_text: str) -> Path:
    p = Path((path_text or "").strip()).expanduser()
    if not str(p):
        p = default_workspace_root()
    if p.name.lower() != APP_FOLDER_NAME.lower():
        p = p / APP_FOLDER_NAME
    return p


class WorkspaceSetupDialog(QDialog):
    """첫 실행/옵션 공용 작업 폴더 설정 창."""
    def __init__(self, parent=None, *, first_run=False, reason_text="", reason_kind="info"):
        super().__init__(parent)
        self.first_run = bool(first_run)
        self.reason_text = reason_text or ""
        self.reason_kind = reason_kind or "info"
        self.ui_language = current_ui_language()
        self.setWindowTitle(translate_ui_text("작업 폴더 설정", self.ui_language))
        self.resize(700, 280)
        self.setStyleSheet("""
            QDialog, QWidget { background-color: #1f1f22; color: #f2f2f2; }
            QLabel { color: #f2f2f2; }
            QLineEdit { background-color: #2A282D; color: #f2f2f2; border: 1px solid #555b66; padding: 4px; }
            QPushButton { background-color: #343841; color: #f2f2f2; border: 1px solid #555b66; padding: 5px 12px; }
            QPushButton:hover { background-color: #434957; }
            QCheckBox { color: #f2f2f2; }
        """)
        self.saved_workspace_root = None
        # 체크박스 초기값은 "현재 EXE와 완전히 일치"가 아니라
        # ".ysbt가 이 프로그램 계열에 등록되어 있는가"를 기준으로 한다.
        # 그래야 구버전/다른 위치 EXE로 등록된 상태에서도 체크 해제 후 저장하면 해제된다.
        self.extension_registered_before = is_ysbt_file_association_ours()

        cfg = load_workspace_config()
        default_path = Path(cfg.get("pending_workspace_root") or cfg.get("workspace_root") or default_workspace_root())

        layout = QVBoxLayout(self)

        self.title_label = QLabel(translate_ui_text("역식붕이 툴 작업 폴더 설정", self.ui_language))
        self.title_label.setStyleSheet("font-size: 16px; font-weight: bold;")
        layout.addWidget(self.title_label)

        if self.reason_text:
            reason = QLabel(translate_ui_text(self.reason_text, self.ui_language))
            self.reason_label = reason
            reason.setWordWrap(True)
            if self.reason_kind == "warning":
                reason.setStyleSheet("color: #ffcc66; font-weight: bold;")
            else:
                reason.setStyleSheet("color: #d8d8d8;")
            layout.addWidget(reason)

        row = QHBoxLayout()
        self.lbl_workspace_path = QLabel(translate_ui_text("작업 폴더 위치", self.ui_language))
        row.addWidget(self.lbl_workspace_path)
        self.ed_path = QLineEdit(str(default_path))
        row.addWidget(self.ed_path, 1)
        self.btn_browse = QPushButton(translate_ui_text("찾아보기", self.ui_language))
        self.btn_browse.clicked.connect(self.browse_folder)
        row.addWidget(self.btn_browse)
        self.btn_reset_default = QPushButton(translate_ui_text("기본값으로\n변경", self.ui_language))
        self.btn_reset_default.setToolTip(translate_ui_text("Windows 실제 문서 폴더 아래 YSB_Translator로 되돌립니다.", self.ui_language))
        self.btn_reset_default.clicked.connect(self.reset_to_default_workspace)
        row.addWidget(self.btn_reset_default)
        layout.addLayout(row)

        option_row = QHBoxLayout()
        self.lbl_language = QLabel("Language")
        self.cb_language = QComboBox(self)
        self.cb_language.addItem(translate_ui_text("한국어", self.ui_language), LANG_KO)
        self.cb_language.addItem("English", LANG_EN)
        self.cb_language.setCurrentIndex(1 if self.ui_language == LANG_EN else 0)
        self.cb_language.currentIndexChanged.connect(self.on_language_changed)
        option_row.addWidget(self.lbl_language)
        option_row.addWidget(self.cb_language)
        option_row.addSpacing(18)
        self.chk_association = QCheckBox(translate_ui_text(".ysbt 확장자 연결 등록", self.ui_language))
        self.chk_association.setChecked(self.extension_registered_before)
        if not is_windows():
            self.chk_association.setChecked(False)
            self.chk_association.setEnabled(False)
            self.chk_association.setToolTip("File association is only supported on Windows." if self.ui_language == LANG_EN else "확장자 연결은 Windows에서만 지원합니다.")
        option_row.addWidget(self.chk_association)
        option_row.addStretch(1)
        layout.addLayout(option_row)

        self.desc_label = QLabel(self.workspace_desc_text())
        self.desc_label.setWordWrap(True)
        self.desc_label.setStyleSheet("color: #d8d8d8;")
        layout.addWidget(self.desc_label)

        btns = QHBoxLayout()
        btns.addStretch(1)
        self.btn_ok = QPushButton(translate_ui_text("확인", self.ui_language))
        self.btn_close = QPushButton(translate_ui_text("닫기", self.ui_language))
        self.btn_ok.clicked.connect(self.accept_with_save)
        self.btn_close.clicked.connect(self.reject)
        btns.addWidget(self.btn_ok)
        btns.addWidget(self.btn_close)
        layout.addLayout(btns)


    def workspace_desc_text(self):
        if self.ui_language == LANG_EN:
            return (
                "The workspace folder stores cache, temporary work, and actual project workspace folders.\n"
                "The default is the YSB_Translator folder under the actual Windows Documents known folder. If the selected folder is not YSB_Translator, the program creates and uses a YSB_Translator folder inside it. Use Restore Default to return to that actual Documents location.\n\n"
                "Registering the .ysbt association lets you open .ysbt project files by double-clicking them. This setting applies only to the current Windows user account and can be removed from Options.\n"
                "The workspace folder setting is saved in workspace_config.json under the Windows user settings folder."
            )
        return (
            "작업 폴더는 캐시, 임시 작업, 실제 프로젝트 작업 폴더를 저장하는 기준 위치입니다.\n"
            "기본값은 Windows의 실제 문서 폴더 아래 YSB_Translator 폴더입니다. 선택한 폴더가 YSB_Translator가 아니면 그 안에 YSB_Translator 폴더를 만들어 사용합니다. 기본값으로 변경을 누르면 이 실제 문서 위치로 되돌립니다.\n\n"
            ".ysbt 확장자 연결을 등록하면 .ysbt 프로젝트 파일을 더블클릭했을 때 역식붕이 툴로 바로 열 수 있습니다. 이 설정은 현재 Windows 사용자 계정에만 적용되며, 옵션에서 해제할 수 있습니다.\n"
            "작업 폴더 위치 설정은 Windows 사용자 설정 폴더의 workspace_config.json에 저장됩니다."
        )

    def on_language_changed(self):
        self.ui_language = normalize_ui_language(self.cb_language.currentData())
        self.setWindowTitle(translate_ui_text("작업 폴더 설정", self.ui_language))
        self.title_label.setText(translate_ui_text("역식붕이 툴 작업 폴더 설정", self.ui_language))
        if hasattr(self, "reason_label"):
            self.reason_label.setText(translate_ui_text(self.reason_text, self.ui_language))
        self.lbl_workspace_path.setText(translate_ui_text("작업 폴더 위치", self.ui_language))
        self.btn_browse.setText(translate_ui_text("찾아보기", self.ui_language))
        self.btn_reset_default.setText(translate_ui_text("기본값으로\n변경", self.ui_language))
        self.btn_reset_default.setToolTip(translate_ui_text("Windows 실제 문서 폴더 아래 YSB_Translator로 되돌립니다.", self.ui_language))
        self.lbl_language.setText("Language")
        self.cb_language.blockSignals(True)
        self.cb_language.setItemText(0, translate_ui_text("한국어", self.ui_language))
        self.cb_language.setItemText(1, "English")
        self.cb_language.blockSignals(False)
        self.chk_association.setText(translate_ui_text(".ysbt 확장자 연결 등록", self.ui_language))
        if not is_windows():
            self.chk_association.setToolTip("File association is only supported on Windows." if self.ui_language == LANG_EN else "확장자 연결은 Windows에서만 지원합니다.")
        self.desc_label.setText(self.workspace_desc_text())
        self.btn_ok.setText(translate_ui_text("확인", self.ui_language))
        self.btn_close.setText(translate_ui_text("닫기", self.ui_language))

    def reset_to_default_workspace(self):
        """작업 폴더 입력칸을 실제 Windows 문서 폴더 기준 기본값으로 되돌린다.

        이 버튼은 즉시 저장하지 않는다. 확인을 눌러야 기존 저장 규칙에 따라
        실제 저장/이동 예약이 진행된다.
        """
        self.ed_path.setText(str(default_workspace_root()))

    def browse_folder(self):
        current = self.ed_path.text().strip() or str(default_workspace_root())
        selected = QFileDialog.getExistingDirectory(self, "Select Workspace Folder" if self.ui_language == LANG_EN else "작업 폴더 위치 선택", current)
        if selected:
            target = normalize_workspace_root_from_user(selected)
            self.ed_path.setText(str(target))

    def _handle_association_choice(self):
        if not is_windows():
            return True

        want_registered = self.chk_association.isChecked()
        current_exe_registered = is_ysbt_file_association_registered()
        our_association_exists = is_ysbt_file_association_ours()

        if want_registered:
            # 체크박스가 켜져 있으면 추가 확인 없이 현재 실행 파일 기준으로 등록/갱신한다.
            # 이미 구버전/다른 위치 EXE로 연결되어 있어도 현재 실행 중인 프로그램으로 덮어쓴다.
            if not current_exe_registered:
                try:
                    register_ysbt_file_association_raw()
                    self.extension_registered_before = True
                except Exception as e:
                    QMessageBox.critical(self, translate_ui_text("등록 실패", self.ui_language), f"{translate_ui_text('.ysbt 확장자 연결 등록에 실패했습니다.', self.ui_language)}\n{e}")
                    return False
            return True

        # 체크박스가 꺼져 있고 .ysbt가 이 프로그램 계열에 등록되어 있으면 해제한다.
        # 첫 기동에서는 해제 후에도 등록 여부를 한 번 더 물어본다.
        if our_association_exists:
            try:
                unregister_ysbt_file_association_raw(include_legacy=False)
                self.extension_registered_before = False
                current_exe_registered = False
            except Exception as e:
                QMessageBox.critical(self, translate_ui_text("해제 실패", self.ui_language), f"{translate_ui_text('.ysbt 확장자 연결 해제에 실패했습니다.', self.ui_language)}\n{e}")
                return False
            if not self.first_run:
                return True

        # 첫 기동이고 체크가 꺼져 있으면, 등록할지 한 번만 물어본다.
        # 사용자가 체크를 해제한 상태라도 첫 실행에서는 더블클릭 열기 기능을 놓치지 않도록 다시 확인한다.
        if self.first_run and not current_exe_registered:
            ans = styled_question(
                self,
                translate_ui_text(".ysbt 확장자 연결", self.ui_language),
                translate_ui_text(".ysbt 확장자 연결이 등록되어 있지 않습니다.\n등록하지 않아도 프로그램 사용은 가능하지만, .ysbt 파일을 더블클릭해서 바로 열 수는 없습니다.\n\n지금 등록할까요?", self.ui_language),
                default_yes=False,
            )
            if ans == QMessageBox.StandardButton.Yes:
                try:
                    register_ysbt_file_association_raw()
                    self.chk_association.setChecked(True)
                    self.extension_registered_before = True
                except Exception as e:
                    QMessageBox.critical(self, translate_ui_text("등록 실패", self.ui_language), f"{translate_ui_text('.ysbt 확장자 연결 등록에 실패했습니다.', self.ui_language)}\n{e}")
                    return False
        return True

    def accept_with_save(self):
        try:
            target = normalize_workspace_root_from_user(self.ed_path.text())
        except Exception:
            QMessageBox.warning(self, "Path Error" if self.ui_language == LANG_EN else "경로 오류", "The workspace folder path is invalid." if self.ui_language == LANG_EN else "작업 폴더 경로가 올바르지 않습니다.")
            return

        # 첫 실행/복구 설정창에서는 기존 작업 폴더가 깨져 있을 수 있다.
        # 이때 get_workspace_root()를 먼저 호출하면 깨진 경로에 cache/temp를 만들려다가
        # WinError 5가 날 수 있으므로, 기존 설정값은 읽기만 하고 폴더를 만들지 않는다.
        try:
            cfg_root_text = load_workspace_config().get("workspace_root")
            current = Path(cfg_root_text).resolve() if cfg_root_text else default_workspace_root().resolve()
            target_resolved = target.resolve()
        except Exception:
            current = Path(str(default_workspace_root()))
            target_resolved = target

        restart_needed = (not self.first_run) and (current != target_resolved)
        if restart_needed:
            if not workspace_restart_confirmation(self, current, target, self.ui_language):
                self.ed_path.setText(str(current))
                return

        if not self._handle_association_choice():
            return

        selected_language = normalize_ui_language(getattr(self, "ui_language", LANG_KO))

        def save_selected_language():
            # 언어 설정은 작업 폴더가 정상 확정된 뒤 저장한다.
            # 저장 실패는 치명 오류로 보지 않는다. 다음 실행에서 기본 언어로만 돌아갈 수 있다.
            try:
                opts = load_app_options()
                opts[UI_LANGUAGE_KEY] = selected_language
                save_app_options(opts)
            except Exception:
                pass

        try:
            if self.first_run:
                set_workspace_root(target)
                save_selected_language()
                self.saved_workspace_root = str(target)
                QMessageBox.information(self, translate_ui_text("설정 완료", self.ui_language), f"{translate_ui_text('작업 폴더를 설정했습니다.', self.ui_language)}\n\n{target}")
            else:
                if restart_needed:
                    schedule_workspace_root_change(target)
                    save_selected_language()
                    self.saved_workspace_root = str(target)
                    self.accept()
                    restart_application_detached()
                    return
                else:
                    # 경로가 같으면 구조만 보장한다.
                    set_workspace_root(target)
                    save_selected_language()
                    self.saved_workspace_root = str(target)
                    QMessageBox.information(self, translate_ui_text("설정 완료", self.ui_language), translate_ui_text("작업 폴더 설정을 저장했습니다.", self.ui_language))
        except Exception as e:
            QMessageBox.critical(self, translate_ui_text("저장 실패", self.ui_language), f"{translate_ui_text('작업 폴더 설정을 저장하지 못했습니다.', self.ui_language)}\n{e}")
            return
        self.accept()


def run_initial_workspace_setup_if_needed() -> bool:
    """작업 폴더가 없거나 저장된 폴더를 찾을 수 없으면 설정창을 띄운다."""
    needs_setup, reason, reason_kind = workspace_root_needs_setup()
    if not needs_setup:
        return True
    dlg = WorkspaceSetupDialog(first_run=True, reason_text=reason, reason_kind=reason_kind)
    return dlg.exec() == QDialog.DialogCode.Accepted


def wait_for_launcher_closed_if_needed(timeout_sec=8.0):
    """런처가 100%를 찍고 닫힌 뒤에만 메인 스플래시를 띄우게 대기한다.

    런처를 거쳐 실행된 경우에만 YSB_LAUNCHER_SESSION_ID가 들어온다.
    메인을 직접 실행한 경우에는 바로 통과한다.
    """
    session_id = os.environ.get("YSB_LAUNCHER_SESSION_ID", "")
    if not session_id:
        return

    path = ysb_launcher_closed_signal_path()
    start = time.time()
    while time.time() - start < timeout_sec:
        try:
            if path.exists():
                data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
                if str(data.get("session_id") or "") == str(session_id):
                    return
        except Exception:
            pass
        QApplication.processEvents()
        time.sleep(0.05)



def is_launcher_splash_owner() -> bool:
    """이번 실행의 스플래시 소유자가 런처인지 확인한다.

    기준은 "런처 파일이 존재하는가"가 아니라 "런처가 이번 메인 실행을 시작했는가"다.
    따라서 YSB_LAUNCHER_SESSION_ID가 있으면 런처 모드로 인정한다.
    YSB_SPLASH_OWNER=launcher는 보조 표시값으로만 사용한다.
    """
    return bool(os.environ.get("YSB_LAUNCHER_SESSION_ID", ""))


def write_launcher_mode_debug(stage: str):
    """런처 진행률 연동 문제를 확인하기 위한 작은 디버그 로그."""
    try:
        path = app_config_dir() / "runtime" / "launcher_mode_debug.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "stage": str(stage),
            "pid": os.getpid(),
            "YSB_LAUNCHER_SESSION_ID": os.environ.get("YSB_LAUNCHER_SESSION_ID", ""),
            "YSB_SPLASH_OWNER": os.environ.get("YSB_SPLASH_OWNER", ""),
            "is_launcher_splash_owner": is_launcher_splash_owner(),
            "time_epoch": time.time(),
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def report_launcher_progress(progress: int, message: str, done: bool = False):
    """런처 소유 스플래시에 표시할 메인 초기화 진행률을 기록한다."""
    if not is_launcher_splash_owner():
        return
    try:
        path = ysb_launcher_progress_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "session_id": os.environ.get("YSB_LAUNCHER_SESSION_ID", ""),
            "pid": os.getpid(),
            "progress": max(0, min(100, int(progress or 0))),
            "message": str(message or ""),
            "done": bool(done),
            "time_epoch": time.time(),
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "source": "main",
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass




def prompt_update_ysbt_file_association_if_needed(parent=None) -> None:
    """.ysbt가 다른 위치의 역식붕이 툴에 연결되어 있으면 현재 프로그램으로 갱신할지 묻는다.

    Windows는 EXE의 버전을 자동으로 비교하지 않는다. 따라서 이 검사는
    "레지스트리에 등록된 열기 명령"과 "현재 실행 중인 프로그램 명령"을 비교한다.
    둘이 다르면 구버전/다른 위치 포터블 EXE로 등록되어 있을 가능성이 높다.
    """
    if not is_windows():
        return
    if launcher_association_preflight_recent():
        return
    if not is_ysbt_file_association_registered_to_other_ysb():
        return

    lang = normalize_ui_language(getattr(parent, "ui_language", None) or current_ui_language())
    registered = get_registered_ysbt_file_association_command() or ("Unknown" if lang == LANG_EN else "알 수 없음")
    current = get_association_command()

    if lang == LANG_EN:
        title = "Refresh .ysbt Association"
        message = (
            ".ysbt is currently associated with YSB Tool in another location.\n"
            "This can happen after replacing the portable EXE with a new version, or after testing another EXE in a different folder.\n\n"
            f"Current registered command:\n{registered}\n\n"
            "Register the file association to the currently running program?\n\n"
            "Press [Yes] to update only the .ysbt file association. Project files will not be changed."
        )
    else:
        title = ".ysbt 확장자 연결 갱신"
        message = (
            "현재 .ysbt 확장자가 다른 위치의 역식붕이 툴에 연결되어 있습니다.\n"
            "포터블 EXE를 새 버전으로 교체했거나, 다른 폴더의 EXE로 테스트한 경우에 생길 수 있습니다.\n\n"
            f"현재 등록된 실행 명령:\n{registered}\n\n"
            "현재 실행 중인 프로그램으로 다시 등록할까요?\n\n"
            "[예]를 누르면 .ysbt 파일 연결만 현재 프로그램 경로로 덮어씁니다. 프로젝트 파일은 변경되지 않습니다."
        )

    ans = styled_question(parent, title, message, default_yes=True)
    if ans == QMessageBox.StandardButton.Yes:
        try:
            register_ysbt_file_association_raw()
        except Exception as e:
            if lang == LANG_EN:
                QMessageBox.critical(parent, "Registration Failed", f"Failed to refresh the .ysbt file association.\n{e}")
            else:
                QMessageBox.critical(parent, "등록 실패", f".ysbt 확장자 연결 갱신에 실패했습니다.\n{e}")


# =========================================================
# 빠른 .ysbt 더블클릭 전달 런처 / 큐
# =========================================================
FILE_OPENER_EXE_NAME = "YSB_Launcher.exe"
OPEN_QUEUE_FILE_NAME = "open_queue.jsonl"
RUNTIME_INFO_FILE_NAME = "main_instance.json"
ASSOCIATION_PREFLIGHT_FILE_NAME = "association_preflight.json"
STARTUP_SIGNAL_FILE_NAME = "main_startup_signal.json"
LAUNCHER_CLOSED_SIGNAL_FILE_NAME = "launcher_closed_signal.json"
LAUNCHER_PROGRESS_FILE_NAME = "launcher_progress.json"

YSB_COMPANY_NAME = "Zerostress8"
YSB_PRODUCT_NAME = "YSB Translator Tool"
YSB_APP_FAMILY_ID = "ZEROSTRESS8_YSB_TRANSLATOR_TOOL"
YSB_ROLE_MAIN = "YSB_MAIN"
YSB_ROLE_LAUNCHER = "YSB_LAUNCHER"
YSB_ROLE_OPENER = YSB_ROLE_LAUNCHER


def ysb_runtime_dir() -> Path:
    return app_config_dir() / "runtime"


def ysb_open_queue_path() -> Path:
    return app_config_dir() / OPEN_QUEUE_FILE_NAME


def ysb_main_runtime_info_path() -> Path:
    return ysb_runtime_dir() / RUNTIME_INFO_FILE_NAME




def ysb_startup_signal_path() -> Path:
    return app_config_dir() / "runtime" / STARTUP_SIGNAL_FILE_NAME


def ysb_launcher_closed_signal_path() -> Path:
    return app_config_dir() / "runtime" / LAUNCHER_CLOSED_SIGNAL_FILE_NAME


def ysb_launcher_progress_path() -> Path:
    return app_config_dir() / "runtime" / LAUNCHER_PROGRESS_FILE_NAME


def ysb_association_preflight_path() -> Path:
    return app_config_dir() / ASSOCIATION_PREFLIGHT_FILE_NAME


def write_main_startup_signal():
    """런처가 메인 Python 코드 시작을 감지해 자신의 스플래시를 닫을 수 있게 신호를 남긴다."""
    try:
        path = ysb_startup_signal_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "pid": os.getpid(),
            "exe": str(Path(sys.executable).resolve()),
            "time_epoch": time.time(),
            "time": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
            "source": "main",
            "edition": APP_EDITION,
            "launcher_session_id": os.environ.get("YSB_LAUNCHER_SESSION_ID", ""),
        }
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(path)
    except Exception:
        pass


def launcher_association_preflight_recent(max_age_sec=180) -> bool:
    """런처가 같은 실행 흐름에서 확장자 갱신 알림을 이미 처리했는지 확인한다.

    런처에서 사용자가 예/아니오를 선택한 경우, 메인에서 같은 알림을 다시 띄우지 않는다.
    failed 상태는 메인에서 다시 처리할 수 있게 False로 본다.
    """
    try:
        path = ysb_association_preflight_path()
        if not path.exists():
            return False
        data = json.loads(path.read_text(encoding="utf-8", errors="replace"))
        status = str(data.get("status") or "")
        t = float(data.get("time") or 0)
        if time.time() - t > max_age_sec:
            return False
        return status in {"already_current", "checked_no_action", "registered", "declined"}
    except Exception:
        return False



def read_windows_exe_version_strings(exe_path: Path) -> dict:
    """EXE의 Windows 버전 리소스 문자열을 읽는다.

    PyInstaller onefile 내부 압축을 풀지 않아도 읽을 수 있는 PE 리소스 정보다.
    """
    if not is_windows():
        return {}
    try:
        exe_text = str(Path(exe_path))
        version = ctypes.windll.version
        handle = ctypes.c_uint(0)
        size = version.GetFileVersionInfoSizeW(exe_text, ctypes.byref(handle))
        if not size:
            return {}

        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(exe_text, 0, size, buffer):
            return {}

        translations = []
        trans_ptr = ctypes.c_void_p()
        trans_len = ctypes.c_uint(0)
        if version.VerQueryValueW(buffer, r"\VarFileInfo\Translation", ctypes.byref(trans_ptr), ctypes.byref(trans_len)):
            count = int(trans_len.value // 4)
            arr_type = ctypes.c_ushort * (count * 2)
            arr = arr_type.from_address(trans_ptr.value)
            for i in range(count):
                translations.append((arr[i * 2], arr[i * 2 + 1]))

        if not translations:
            translations = [
                (0x0409, 0x04B0),
                (0x0409, 0x04E4),
                (0x0412, 0x04B0),
                (0x0000, 0x04B0),
            ]

        keys = [
            "CompanyName",
            "ProductName",
            "FileDescription",
            "InternalName",
            "OriginalFilename",
            "ProductVersion",
            "FileVersion",
            "YSBAppFamilyId",
            "YSBAppRole",
        ]
        out = {}
        for lang, codepage in translations:
            base = rf"\StringFileInfo\{lang:04x}{codepage:04x}"
            for key in keys:
                if key in out:
                    continue
                ptr = ctypes.c_void_p()
                length = ctypes.c_uint(0)
                query = base + "\\" + key
                if version.VerQueryValueW(buffer, query, ctypes.byref(ptr), ctypes.byref(length)) and ptr.value:
                    try:
                        out[key] = ctypes.wstring_at(ptr.value)
                    except Exception:
                        pass
            if out:
                break
        return out
    except Exception:
        return {}


def is_ysb_launcher_exe_by_metadata(exe_path: Path) -> bool:
    info = read_windows_exe_version_strings(exe_path)
    if not info:
        return False

    company = str(info.get("CompanyName", "")).strip()
    product = str(info.get("ProductName", "")).strip()
    family = str(info.get("YSBAppFamilyId", "")).strip()
    role = str(info.get("YSBAppRole", "")).strip()
    internal = str(info.get("InternalName", "")).strip()

    family_ok = (
        company == YSB_COMPANY_NAME
        and (
            family == YSB_APP_FAMILY_ID
            or product == YSB_PRODUCT_NAME
        )
    )
    role_ok = (role == YSB_ROLE_LAUNCHER or internal == YSB_ROLE_LAUNCHER)
    return bool(family_ok and role_ok)


def get_file_opener_path() -> Path | None:
    """.ysbt 더블클릭 전용 공식 런처 경로를 반환한다.

    1순위는 EXE 버전 리소스 메타데이터다.
    - CompanyName: Zerostress8
    - ProductName: YSB Translator Tool
    - InternalName 또는 YSBAppRole: YSB_LAUNCHER

    v2.0.1부터 구형 YSB_FileOpener / YSBT Luncher 이름은 탐색하지 않는다.
    """
    try:
        search_dirs = []
        if getattr(sys, "frozen", False):
            here = Path(sys.executable).resolve().parent
            self_exe = Path(sys.executable).resolve()
        else:
            here = APP_ROOT
            self_exe = None

        search_dirs.append(here)
        try:
            search_dirs.append(here.parent)
        except Exception:
            pass

        for folder in ("YSB", "YSB Tool", "YSB Translator", "YSB TRANSLATE", "YSB_Translator", "app", "program"):
            search_dirs.append(here / folder)
            try:
                search_dirs.append(here.parent / folder)
            except Exception:
                pass

        seen = set()
        resolved_dirs = []
        for d in search_dirs:
            try:
                rd = d.resolve()
                if rd in seen:
                    continue
                seen.add(rd)
                resolved_dirs.append(rd)
            except Exception:
                continue

        # 1. EXE 내부 메타데이터로 진짜 런처 식별
        metadata_candidates = []
        for rd in resolved_dirs:
            try:
                if not rd.exists() or not rd.is_dir():
                    continue
                for candidate in rd.glob("*.exe"):
                    try:
                        if self_exe is not None and candidate.resolve() == self_exe:
                            continue
                    except Exception:
                        pass
                    if is_ysb_launcher_exe_by_metadata(candidate):
                        try:
                            metadata_candidates.append((candidate.stat().st_size, candidate))
                        except Exception:
                            metadata_candidates.append((0, candidate))
            except Exception:
                continue

        if metadata_candidates:
            metadata_candidates.sort(key=lambda x: x[0])
            return metadata_candidates[0][1]

        # 2. 기본 이름 후보
        for rd in resolved_dirs:
            for launcher_name in (FILE_OPENER_EXE_NAME,):
                candidate = rd / launcher_name
                if candidate.exists():
                    return candidate

        if not getattr(sys, "frozen", False):
            candidate = APP_ROOT / "ysb_launcher.py"
            if candidate.exists():
                return candidate
            return None
    except Exception:
        pass
    return None

# =========================================================
# 단일 실행 / .ysbt 더블클릭 전달
# =========================================================
SINGLE_INSTANCE_SERVER_NAME = f"YSBTranslator_{APP_EDITION}_v21_single_instance"


def _single_instance_payload_from_args(args):
    """두 번째 실행 프로세스가 기존 프로세스에 넘길 메시지를 만든다."""
    args = list(args or [])
    open_path = ""
    for arg in args:
        if not arg:
            continue
        lower = str(arg).lower()
        if lower.endswith(YSBT_EXTENSION) or os.path.basename(str(arg)).lower() == PROJECT_FILENAME:
            open_path = os.path.abspath(str(arg))
            break
    if open_path:
        return {"command": "open", "path": open_path}
    return {"command": "activate"}


def notify_running_instance(args, timeout_ms=700):
    """이미 실행 중인 역식붕이 툴이 있으면 메시지를 보내고 True를 반환한다."""
    socket = QLocalSocket()
    socket.connectToServer(SINGLE_INSTANCE_SERVER_NAME, QIODevice.OpenModeFlag.WriteOnly)
    if not socket.waitForConnected(timeout_ms):
        return False
    try:
        payload = _single_instance_payload_from_args(args)
        data = (json.dumps(payload, ensure_ascii=False) + "\n").encode("utf-8")
        socket.write(data)
        socket.flush()
        socket.waitForBytesWritten(timeout_ms)
    finally:
        socket.disconnectFromServer()
    return True


class SingleInstanceServer(QObject):
    """한 개의 프로세스만 실행하고, 두 번째 실행 요청을 첫 프로세스로 전달한다."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.server = QLocalServer(self)
        self.server.newConnection.connect(self._on_new_connection)
        self.main_window = None
        self.pending_payloads = []
        self.sockets = []

    def start(self):
        if self.server.listen(SINGLE_INSTANCE_SERVER_NAME):
            return True
        # 이전 비정상 종료로 서버명이 남아 있으면 정리 후 재시도한다.
        try:
            QLocalServer.removeServer(SINGLE_INSTANCE_SERVER_NAME)
        except Exception:
            pass
        return self.server.listen(SINGLE_INSTANCE_SERVER_NAME)

    def set_main_window(self, window):
        self.main_window = window
        for payload in list(self.pending_payloads):
            self._dispatch_payload(payload)
        self.pending_payloads.clear()

    def _on_new_connection(self):
        while self.server.hasPendingConnections():
            sock = self.server.nextPendingConnection()
            if sock is None:
                continue
            sock.setParent(self)
            self.sockets.append(sock)
            sock.readyRead.connect(lambda s=sock: self._read_socket(s))
            sock.disconnected.connect(lambda s=sock: self._cleanup_socket(s))
            QTimer.singleShot(0, lambda s=sock: self._read_socket(s))

    def _cleanup_socket(self, sock):
        try:
            if sock in self.sockets:
                self.sockets.remove(sock)
            sock.deleteLater()
        except Exception:
            pass

    def _read_socket(self, sock):
        try:
            data = bytes(sock.readAll()).decode("utf-8", errors="replace").strip()
            if not data:
                return
            for line in data.splitlines():
                try:
                    payload = json.loads(line)
                except Exception:
                    payload = {"command": "activate"}
                self._dispatch_payload(payload)
        finally:
            try:
                sock.disconnectFromServer()
            except Exception:
                pass

    def _dispatch_payload(self, payload):
        if self.main_window is None:
            self.pending_payloads.append(payload)
            return
        try:
            self.main_window.handle_single_instance_payload(payload)
        except Exception as e:
            print(f"Single instance dispatch error: {e}")


class YSBSplashScreen(QWidget):
    """
    로고 하단에 진행바를 직접 그리는 스플래시 화면.

    기존 QSplashScreen.drawContents 방식은 환경에 따라 오버레이가 안 보일 수 있어서,
    QWidget.paintEvent에서 배경 이미지와 진행률을 직접 그리는 방식으로 바꾼다.
    """
    def __init__(self, pixmap):
        super().__init__(None, Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._pixmap = pixmap
        self._progress = 0
        self._message = "로딩 중..."
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick_progress)
        self.resize(self._pixmap.size())

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick_progress(self):
        # 실제 로딩이 끝나기 전엔 90%까지만 자동 진행
        if self._progress < 90:
            self._progress += 1
            self.repaint()

    def set_progress(self, value, message=None):
        self._progress = max(0, min(100, int(value)))
        if message is not None:
            self._message = str(message)
        self.repaint()
        QApplication.processEvents()

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 배경 로고 이미지
        painter.drawPixmap(0, 0, self._pixmap)

        margin_x = 36
        bar_h = 18
        y = self.height() - 42
        bar_rect = QRect(margin_x, y, self.width() - margin_x * 2, bar_h)

        # 진행바 배경
        painter.setPen(QPen(QColor(35, 35, 35, 230), 1))
        painter.setBrush(QColor(18, 18, 18, 220))
        painter.drawRoundedRect(bar_rect, 8, 8)

        # 진행 채움
        fill_w = int((bar_rect.width() - 4) * (self._progress / 100.0))
        if fill_w > 0:
            fill_rect = QRect(bar_rect.x() + 2, bar_rect.y() + 2, fill_w, bar_rect.height() - 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 40, 40, 245))
            painter.drawRoundedRect(fill_rect, 6, 6)

        # 메시지 / 퍼센트
        text_rect = QRect(margin_x, y - 26, self.width() - margin_x * 2, 22)
        painter.setPen(QColor(250, 250, 250))
        font = QFont("맑은 고딕", 10)
        font.setBold(True)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._message)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{self._progress}%")
        painter.end()

    def finish(self, widget):
        try:
            self.hide()
        except Exception:
            pass


def make_splash_screen():
    """
    앱 초기화 중 표시할 500x500 스플래시 화면.
    PyInstaller --onefile 압축 해제 시간은 파이썬 코드 실행 전이라 표시되지 않고,
    QApplication 생성 이후 초기화 구간부터 표시된다.
    """
    pix = QPixmap(resource_path("ysb_splash.png"))
    if pix.isNull():
        return None

    pix = pix.scaled(
        500,
        500,
        Qt.AspectRatioMode.KeepAspectRatio,
        Qt.TransformationMode.SmoothTransformation,
    )

    splash = YSBSplashScreen(pix)
    splash.resize(pix.size())

    screen = QApplication.primaryScreen()
    if screen:
        geo = screen.availableGeometry()
        splash.move(geo.center() - splash.rect().center())

    splash.show()
    QApplication.processEvents()
    splash.start()
    splash.set_progress(35, translate_ui_text("압축 해제 완료 · 인터페이스 로딩 중..."))
    return splash



class _InlinePlainTextEditWidget(QPlainTextEdit):
    """QGraphicsProxyWidget 안에서 실제 입력만 담당하는 가벼운 plain text 편집기."""

    def __init__(self, owner):
        super().__init__()
        self.owner = owner
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabChangesFocus(False)
        self.setAcceptDrops(True)
        try:
            self.setFrameShape(QFrame.Shape.NoFrame)
        except Exception:
            pass
        try:
            self.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
            self.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            pass
        try:
            self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, True)
            self.setAutoFillBackground(False)
            self.viewport().setAutoFillBackground(False)
        except Exception:
            pass
        try:
            self.document().setDocumentMargin(0)
        except Exception:
            pass
        try:
            self.textChanged.connect(lambda: self.owner._schedule_adjust_to_contents(reason='text_changed'))
        except Exception:
            pass

    def keyPressEvent(self, event):
        owner = getattr(self, 'owner', None)
        if owner is not None and owner._is_alt_modifier_guard_event(event):
            event.accept()
            return

        try:
            key = event.key()
            mods = event.modifiers()
        except Exception:
            key = None
            mods = Qt.KeyboardModifier.NoModifier

        if owner is not None:
            if key == Qt.Key.Key_Escape:
                owner.main_window.finish_inline_text_edit(commit=False)
                event.accept()
                return
            if (
                key in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and mods & Qt.KeyboardModifier.ControlModifier
            ):
                try:
                    owner._inline_trace('INLINE_EDITOR_CTRL_ENTER_COMMIT_REQUEST')
                except Exception:
                    pass
                owner.main_window.finish_inline_text_edit(commit=True, commit_reason='ctrl_enter')
                event.accept()
                return
            if mods & Qt.KeyboardModifier.ControlModifier:
                if key == Qt.Key.Key_Z and (mods & Qt.KeyboardModifier.ShiftModifier):
                    owner.perform_inline_local_redo()
                    event.accept()
                    return
                if key == Qt.Key.Key_Z:
                    owner.perform_inline_local_undo()
                    event.accept()
                    return
                if key == Qt.Key.Key_Y:
                    owner.perform_inline_local_redo()
                    event.accept()
                    return
                # QGraphicsProxyWidget 안의 QPlainTextEdit가 OS 클립보드만 갱신하고
                # 메인 창의 텍스트박스 붙여넣기 버퍼는 갱신하지 못하면, 편집기 밖 Ctrl+V가
                # 예전 텍스트박스 복사본을 붙여넣거나 아무 것도 붙여넣지 못한다.
                # 내부 글자 복사/잘라내기도 YSB plain-text clipboard로 승격한다.
                if key in (Qt.Key.Key_C, Qt.Key.Key_X):
                    if owner.copy_widget_selection_to_plain_clipboard(cut=(key == Qt.Key.Key_X)):
                        event.accept()
                        return
            if owner._handle_inline_text_input_shortcut(event):
                return

        super().keyPressEvent(event)
        if owner is not None:
            owner._schedule_adjust_to_contents(reason='key')

    def inputMethodEvent(self, event):
        super().inputMethodEvent(event)
        owner = getattr(self, 'owner', None)
        if owner is not None:
            owner._schedule_adjust_to_contents(reason='ime')

    def keyReleaseEvent(self, event):
        owner = getattr(self, 'owner', None)
        if owner is not None and owner._is_alt_modifier_guard_event(event):
            event.accept()
            return
        super().keyReleaseEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        owner = getattr(self, 'owner', None)
        if owner is not None:
            owner._handle_child_focus_out()

    def dropEvent(self, event):
        super().dropEvent(event)
        owner = getattr(self, 'owner', None)
        if owner is not None:
            owner._schedule_adjust_to_contents(reason='drop')


class _InlineCursorProxy:
    """전용 인라인 편집기의 외부 호환용 가벼운 커서 객체."""

    def __init__(self, editor, position=None, anchor=None):
        self.editor = editor
        try:
            length = len(editor.toPlainText())
        except Exception:
            length = 0
        self._position = max(0, min(length, int(position if position is not None else getattr(editor, '_v_caret_index', length))))
        self._anchor = self._position if anchor is None else max(0, min(length, int(anchor)))

    def clearSelection(self):
        self._anchor = self._position

    def hasSelection(self):
        return self._anchor != self._position

    def selectionStart(self):
        return min(self._anchor, self._position)

    def selectionEnd(self):
        return max(self._anchor, self._position)

    def selectedText(self):
        try:
            text = self.editor.toPlainText()
            return text[self.selectionStart():self.selectionEnd()]
        except Exception:
            return ''

    def position(self):
        return self._position

    def anchor(self):
        return self._anchor

    def setPosition(self, pos, mode=None):
        try:
            length = len(self.editor.toPlainText())
        except Exception:
            length = 0
        pos = max(0, min(length, int(pos)))
        extend = False
        try:
            extend = mode == QTextCursor.MoveMode.KeepAnchor
        except Exception:
            extend = False
        if not extend:
            self._anchor = pos
        self._position = pos

    def select(self, selection_type):
        try:
            if selection_type == QTextCursor.SelectionType.Document:
                self._anchor = 0
                self._position = len(self.editor.toPlainText())
        except Exception:
            pass

    def movePosition(self, operation, mode=QTextCursor.MoveMode.MoveAnchor, n=1):
        try:
            n = max(1, int(n or 1))
        except Exception:
            n = 1
        pos = self._position
        text = self.editor.toPlainText()
        for _ in range(n):
            if operation == QTextCursor.MoveOperation.Start:
                pos = 0
            elif operation == QTextCursor.MoveOperation.End:
                pos = len(text)
            elif operation == QTextCursor.MoveOperation.Left:
                pos = max(0, pos - 1)
            elif operation == QTextCursor.MoveOperation.Right:
                pos = min(len(text), pos + 1)
            elif operation == QTextCursor.MoveOperation.Up:
                pos = max(0, pos - 1)
            elif operation == QTextCursor.MoveOperation.Down:
                pos = min(len(text), pos + 1)
            else:
                break
        self.setPosition(pos, mode)
        return True

    def insertText(self, value):
        self.editor._replace_vertical_selection(str(value or ''))
        self._position = getattr(self.editor, '_v_caret_index', self._position)
        self._anchor = self._position


class InlineTextEditItem(QGraphicsObject):
    """최종 화면에서 더블클릭으로 직접 수정하는 YSB 전용 인라인 편집기.

    세로쓰기는 항상 YSB 직접 편집기를 사용한다. 설정에서 가로쓰기 직접 편집기를
    켜면 가로쓰기 역시 QPlainTextEdit 대신 QGraphicsItem이 직접 글자 배치/커서/클릭
    위치를 계산한다. 텍스트 입력/커서/선택은 편집기에서 처리하고, 이펙트/변형/최종
    조판은 기존 TypesettingItem 렌더 경로를 그대로 사용한다.
    """

    def __init__(self, main_window, target_item, scene_rect):
        super().__init__()
        self.main_window = main_window
        self.target_item = target_item
        self._closing = False
        self._adjusting = False
        self._inline_adjust_queued = False
        self._edit = None
        self._edit_proxy = None
        self._bounds = QRectF(0, 0, 1, 1)
        # 편집 종료 직후 QGraphicsView가 마지막 caret 프레임을 한 번 더 그리는 경우가 있다.
        # cleanup 단계에서 이 플래그를 켜면, scene에서 제거되기 전이라도 paint()가 즉시 no-op이 된다.
        self._inline_paint_suppressed = False
        self._vertical_layout_cache = None
        self._vertical_drag_selecting = False
        self._v_preedit_text = ''
        # IME preedit can replace an active selection before commitString arrives.
        # Keep a small state flag so the later commit is treated as the same edit
        # instead of a second unrelated undo step.
        self._v_ime_selection_preedit_active = False
        self._v_cursor_visible = True
        # Direct inline editor vertical navigation must follow the visual caret
        # coordinate, not the raw character offset.  Center/right aligned lines
        # have different visual starts, so Up/Down in horizontal writing keeps
        # a desired X, and Left/Right in vertical writing keeps a desired Y.
        self._v_desired_caret_x = None
        self._v_desired_caret_y = None

        d = target_item.data
        self.original_text = str(d.get('translated_text', '') or '')
        self.align = (d.get('align') or 'center').lower()
        if self.align not in ('left', 'center', 'right'):
            self.align = 'center'

        self.anchor_y = float(scene_rect.y())
        if self.align == 'right':
            self.anchor_x = float(scene_rect.right())
        elif self.align == 'center':
            self.anchor_x = float(scene_rect.center().x())
        else:
            self.anchor_x = float(scene_rect.x())

        self.setZValue(5000)
        self.letter_spacing = clamp_text_letter_spacing(d.get('letter_spacing', 0), 0)
        self.line_spacing_pct = clamp_text_line_spacing(d.get('line_spacing', 100), 100)
        self.char_width_pct = clamp_text_char_scale(d.get('char_width', 100), 100)
        self.char_height_pct = clamp_text_char_scale(d.get('char_height', 100), 100)
        self.writing_direction = self._normalize_inline_writing_direction(d.get('writing_direction', 'horizontal'))
        try:
            self._inline_edit_scene_rect = QRectF(scene_rect)
        except Exception:
            self._inline_edit_scene_rect = QRectF(0, 0, 1, 1)
        self._inline_fixed_edit_bounds = QRectF(
            0, 0,
            max(1.0, float(self._inline_edit_scene_rect.width())),
            max(1.0, float(self._inline_edit_scene_rect.height())),
        )

        font = QFont(d.get('font_family') or main_window.cb_font.currentFont().family())
        font.setPixelSize(int(d.get('font_size', main_window.sb_font_size.value()) or main_window.sb_font_size.value()))
        ysb_apply_readable_bold_to_font(font, bool(d.get('bold', False)))
        font.setItalic(bool(d.get('italic', False)))
        self._base_font = QFont(font)
        self._apply_inline_font_metrics(font)
        self._inline_font = QFont(font)

        color = QColor(str(d.get('text_color') or '#000000'))
        if not color.isValid():
            color = QColor('#000000')
        self._inline_text_color = QColor(color)
        stroke_color = QColor(str(d.get('stroke_color') or '#FFFFFF'))
        if not stroke_color.isValid():
            stroke_color = QColor('#FFFFFF')
        self._inline_stroke_color = QColor(stroke_color)
        self._inline_stroke_width = self._style_int(d.get('stroke_width', 0), 0, 0, 200)
        self._inline_double_stroke_enabled = bool(d.get('double_stroke_enabled', False))
        self._inline_double_stroke_color = QColor(str(d.get('double_stroke_color') or '#000000'))
        if not self._inline_double_stroke_color.isValid():
            self._inline_double_stroke_color = QColor('#000000')
        self._inline_double_stroke_width = self._style_int(d.get('double_stroke_width', 0), 0, 0, 200)
        self.inline_edit_bg_color = self._make_inline_edit_background_color(color)
        self.inline_edit_border_color = self._make_inline_edit_border_color(self.inline_edit_bg_color)

        try:
            use_direct_horizontal = bool(getattr(main_window, 'use_direct_inline_text_editor_horizontal', True))
        except Exception:
            use_direct_horizontal = True
        self._inline_direct_editor = bool(self._is_vertical_writing() or use_direct_horizontal)
        # 호환을 위해 기존 변수명은 유지하지만, 이제 True는 'YSB 직접 편집기 사용'을 뜻한다.
        self._vertical_editor = self._inline_direct_editor
        if self._vertical_editor:
            self._v_text = self.original_text
            self._v_caret_index = len(self._v_text)
            self._v_selection_anchor = self._v_caret_index
            self._v_undo_stack = []
            self._v_redo_stack = []
            self._v_document = QTextDocument()
            self._v_document.setPlainText(self._v_text)
            self.setAcceptedMouseButtons(Qt.MouseButton.LeftButton | Qt.MouseButton.RightButton)
            self.setAcceptHoverEvents(True)
            # 직접 편집기 내부에서는 도구/이동 커서보다 텍스트 삽입 커서가 우선이다.
            # QGraphicsView/아이템 커서 override가 남아 있으면 사용자가 에디터 내부를
            # 클릭해도 커서를 옮길 수 있는 상태인지 알아보기 어렵다.
            try:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            except Exception:
                pass
            try:
                self._blink_timer = QTimer(self)
                self._blink_timer.timeout.connect(self._toggle_vertical_cursor_visible)
                self._blink_timer.start(530)
            except Exception:
                self._blink_timer = None
        else:
            self._edit = _InlinePlainTextEditWidget(self)
            try:
                self._edit.setCursor(Qt.CursorShape.IBeamCursor)
                self.setCursor(Qt.CursorShape.IBeamCursor)
            except Exception:
                pass
            self._apply_widget_style()
            self._edit.setUndoRedoEnabled(False)
            self._edit.setPlainText(self.original_text)
            self.apply_text_alignment()
            self._edit.setUndoRedoEnabled(True)
            try:
                self._edit.document().clearUndoRedoStacks(QTextDocument.Stacks.UndoAndRedoStacks)
            except Exception:
                pass
            self._edit_proxy = QGraphicsProxyWidget(self)
            self._edit_proxy.setWidget(self._edit)
            self._edit_proxy.setPos(0, 0)

        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        if self._vertical_editor:
            try:
                self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemAcceptsInputMethod, True)
            except Exception:
                pass
        # QGraphicsObject/QGraphicsItem에는 QWidget의 setFocusPolicy()가 없다.
        # 여기서 AttributeError가 나면 에디터 생성 자체가 중단되어 가로/세로 모두
        # 편집기가 뜨지 않는다. 포커스 가능 여부는 ItemIsFocusable 플래그와
        # setFocus() 호출로 처리한다.
        self._schedule_adjust_to_contents(reason='init')

    _FONT_METRICS_CACHE = {}

    @staticmethod
    def _style_int(value, default, min_value=None, max_value=None):
        try:
            out = int(value if value is not None else default)
        except Exception:
            out = int(default)
        if min_value is not None:
            out = max(int(min_value), out)
        if max_value is not None:
            out = min(int(max_value), out)
        return out

    @classmethod
    def _cached_font_metrics(cls, font):
        """QFontMetrics 생성 비용을 줄이기 위한 편집기 전용 캐시.

        첫 직접 편집기 오픈 때 같은 폰트/크기/자간/폭 조합의 metrics를 반복 생성하면
        짧은 멈칫거림이 생길 수 있다. QFontMetrics는 읽기 전용으로만 쓰므로 같은 폰트
        키에서는 재사용한다.
        """
        try:
            f = QFont(font)
        except Exception:
            f = QFont()
        try:
            key = f.toString()
        except Exception:
            key = str(f.family())
        cache = getattr(cls, '_FONT_METRICS_CACHE', None)
        if cache is None:
            cls._FONT_METRICS_CACHE = {}
            cache = cls._FONT_METRICS_CACHE
        fm = cache.get(key)
        if fm is None:
            try:
                # 너무 오래 켜둔 세션에서도 무한히 늘지 않게 간단히 상한을 둔다.
                if len(cache) > 64:
                    cache.clear()
            except Exception:
                pass
            fm = QFontMetrics(f)
            cache[key] = fm
        return fm

    @staticmethod
    def _normalize_inline_writing_direction(value):
        text = str(value or 'horizontal').strip().lower()
        if text in ('vertical', 'v', '세로', '세로쓰기'):
            return 'vertical'
        return 'horizontal'

    def _is_vertical_writing(self):
        return self._normalize_inline_writing_direction(getattr(self, 'writing_direction', 'horizontal')) == 'vertical'

    def _apply_inline_font_metrics(self, font):
        try:
            spacing_type = QFont.SpacingType.AbsoluteSpacing
        except AttributeError:
            spacing_type = getattr(QFont, 'AbsoluteSpacing', None)
        try:
            font.setLetterSpacing(spacing_type, float(getattr(self, 'letter_spacing', 0) or 0))
        except Exception:
            pass
        try:
            font.setStretch(qt_font_stretch_value(getattr(self, 'char_width_pct', 100), 100))
        except Exception:
            pass

    @staticmethod
    def _color_luma(color):
        try:
            return (0.299 * color.red()) + (0.587 * color.green()) + (0.114 * color.blue())
        except Exception:
            return 0.0

    @classmethod
    def _make_inline_edit_background_color(cls, text_color):
        try:
            color = QColor(text_color)
            if not color.isValid():
                color = QColor('#000000')
        except Exception:
            color = QColor('#000000')
        complement = QColor(255 - color.red(), 255 - color.green(), 255 - color.blue(), 190)
        text_luma = cls._color_luma(color)
        bg_luma = cls._color_luma(complement)
        if abs(text_luma - bg_luma) < 95:
            if text_luma >= 128:
                return QColor(18, 18, 18, 190)
            return QColor(255, 255, 255, 190)
        complement.setAlpha(190)
        return complement

    @classmethod
    def _make_inline_edit_border_color(cls, bg_color):
        try:
            color = QColor(bg_color)
            if not color.isValid():
                color = QColor(80, 80, 80)
        except Exception:
            color = QColor(80, 80, 80)
        if cls._color_luma(color) >= 128:
            border = color.darker(145)
        else:
            border = color.lighter(170)
        border.setAlpha(230)
        return border

    def _inline_trace(self, event, **fields):
        """Inline editor trace for selection/preview mismatch debugging."""
        try:
            main = getattr(self, 'main_window', None)
            if main is None or not hasattr(main, 'audit_boundary_event'):
                return
            item = getattr(self, 'target_item', None)
            data = getattr(item, 'data', {}) if item is not None else {}
            main.audit_boundary_event(
                event,
                text_id=data.get('id') if isinstance(data, dict) else None,
                editor_text_len=len(str(self.toPlainText() or '')),
                writing_direction=getattr(self, 'writing_direction', None),
                editor_pos=f"[{float(self.pos().x()):.2f}, {float(self.pos().y()):.2f}]",
                editor_bounds=f"[{float(self.boundingRect().x()):.2f}, {float(self.boundingRect().y()):.2f}, {float(self.boundingRect().width()):.2f}, {float(self.boundingRect().height()):.2f}]",
                **fields,
            )
        except Exception:
            pass

    def _apply_widget_style(self):
        if self._edit is None:
            return
        try:
            self._edit.setFont(QFont(getattr(self, '_inline_font', QFont())))
        except Exception:
            pass
        try:
            pal = self._edit.palette()
            pal.setColor(QPalette.ColorRole.Text, QColor(getattr(self, '_inline_text_color', QColor('#000000'))))
            pal.setColor(QPalette.ColorRole.Base, QColor(0, 0, 0, 0))
            self._edit.setPalette(pal)
            self._edit.viewport().setPalette(pal)
        except Exception:
            pass
        try:
            color = QColor(getattr(self, '_inline_text_color', QColor('#000000')))
            self._edit.setStyleSheet(
                "QPlainTextEdit {"
                "background: transparent;"
                "border: 0px;"
                "padding: 3px 4px;"
                f"color: rgba({color.red()}, {color.green()}, {color.blue()}, {color.alpha()});"
                "selection-background-color: rgba(80, 160, 255, 120);"
                "}"
            )
        except Exception:
            pass

    def _apply_inline_block_format(self, block_format):
        try:
            line_height_type = QTextBlockFormat.LineHeightTypes.ProportionalHeight
        except AttributeError:
            line_height_type = getattr(QTextBlockFormat, 'ProportionalHeight', None)
        if line_height_type is None:
            return
        try:
            block_format.setLineHeight(float(getattr(self, 'line_spacing_pct', 100) or 100), line_height_type)
        except TypeError:
            try:
                block_format.setLineHeight(float(getattr(self, 'line_spacing_pct', 100) or 100), int(line_height_type.value))
            except Exception:
                pass
        except Exception:
            pass

    def apply_text_alignment(self):
        if self._vertical_editor:
            self.invalidate_vertical_layout()
            self.update()
            return
        try:
            cursor = QTextCursor(self._edit.document())
            cursor.select(QTextCursor.SelectionType.Document)
            block_format = QTextBlockFormat()
            if self.align == 'right':
                block_format.setAlignment(Qt.AlignmentFlag.AlignRight)
            elif self.align == 'center':
                block_format.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                block_format.setAlignment(Qt.AlignmentFlag.AlignLeft)
            self._apply_inline_block_format(block_format)
            cursor.mergeBlockFormat(block_format)
        except Exception:
            pass

    def boundingRect(self):
        try:
            return QRectF(self._bounds)
        except Exception:
            return QRectF(0, 0, 1, 1)

    def shape(self):
        path = QPainterPath()
        path.addRect(self.boundingRect().adjusted(-3, -3, 3, 3))
        return path

    def invalidate_vertical_layout(self):
        self._vertical_layout_cache = None

    def _horizontal_content_rect_fast(self):
        try:
            font = QFont(getattr(self, '_inline_font', QFont()))
        except Exception:
            font = QFont()
        fm = self._cached_font_metrics(font)
        try:
            text = str(self.toPlainText() or '')
        except Exception:
            text = ''
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        if not lines:
            lines = ['']
        max_w = 30.0
        for line in lines:
            try:
                max_w = max(max_w, float(fm.horizontalAdvance(str(line))))
            except Exception:
                pass
        try:
            line_spacing_pct = clamp_text_line_spacing(getattr(self, 'line_spacing_pct', 100), 100)
        except Exception:
            line_spacing_pct = 100
        try:
            _avg_w, tight_line_h = self._horizontal_tight_line_metrics_for_direct_editor(font, fm, 1.0, max(0.10, float(getattr(self, 'char_height_pct', 100) or 100) / 100.0))
        except Exception:
            tight_line_h = float(fm.lineSpacing())
        line_h = max(1.0, abs(text_line_height_from_percent(float(tight_line_h), line_spacing_pct)))
        h = max(line_h, line_h * max(1, len(lines)))
        return QRectF(0, 0, max_w, h)

    def _content_path_rect(self):
        if self._vertical_editor:
            layout = self._layout_vertical_text()
            return QRectF(layout.get('content_rect', QRectF(0, 0, 1, 1)))
        return QRectF(self._horizontal_content_rect_fast())

    def adjusted_scene_rect(self):
        if self._vertical_editor:
            try:
                layout = self._layout_vertical_text()
                content = QRectF(layout.get('content_rect', QRectF()))
                if content.width() > 1 and content.height() > 1:
                    return self.mapToScene(content).boundingRect()
            except Exception:
                pass
            try:
                return QRectF(getattr(self, '_inline_edit_scene_rect', QRectF(0, 0, 1, 1)))
            except Exception:
                return QRectF(0, 0, 1, 1)
        rect = self._content_path_rect()
        w = max(1.0, float(rect.width()))
        h = max(1.0, float(rect.height()))
        anchor_x = float(getattr(self, 'anchor_x', 0.0))
        if getattr(self, 'align', 'center') == 'right':
            x = anchor_x - w
        elif getattr(self, 'align', 'center') == 'left':
            x = anchor_x
        else:
            x = anchor_x - w / 2.0
        y = float(getattr(self, 'anchor_y', 0.0))
        return QRectF(x, y, w, h)

    def _schedule_adjust_to_contents(self, reason='edit'):
        try:
            self.adjust_to_contents()
        except Exception:
            pass
        try:
            if getattr(self, '_inline_adjust_queued', False):
                return
            self._inline_adjust_queued = True
            QTimer.singleShot(0, self._run_queued_adjust_to_contents)
        except Exception:
            pass

    def _run_queued_adjust_to_contents(self):
        try:
            self._inline_adjust_queued = False
            self.adjust_to_contents()
        except Exception:
            try:
                self._inline_adjust_queued = False
            except Exception:
                pass

    def prepareGeometryChangeSafe(self):
        try:
            self.prepareGeometryChange()
        except Exception:
            pass

    def resize(self, width, height):
        width = max(1.0, float(width))
        height = max(1.0, float(height))
        if abs(self._bounds.width() - width) > 0.5 or abs(self._bounds.height() - height) > 0.5:
            self.prepareGeometryChangeSafe()
            self._bounds = QRectF(0, 0, width, height)
            self.invalidate_vertical_layout()

    def adjust_to_contents(self):
        if self._adjusting:
            return
        self._adjusting = True
        try:
            if self._vertical_editor:
                # YSB 직접 편집기는 최초 edit_rect에 고정하지 않는다.
                # 입력/삭제로 글자 수가 바뀌면 편집 박스도 즉시 커지고 줄어야 한다.
                width, height = self._direct_editor_desired_local_size()
                width = max(18.0, float(width))
                height = max(18.0, float(height))
                try:
                    base_rect = QRectF(getattr(self, '_inline_edit_scene_rect', QRectF(0, 0, width, height)))
                except Exception:
                    base_rect = QRectF(self.pos().x(), self.pos().y(), width, height)

                if self._is_vertical_writing():
                    # 세로쓰기 align은 left/center/right 값을 위/가운데/아래로 해석한다.
                    # x 중심은 기존 텍스트 위치에 고정하고, y 기준점만 정렬값에 맞춘다.
                    x = float(base_rect.center().x()) - width / 2.0
                    if self.align == 'left':      # 위 정렬
                        y = float(base_rect.top())
                    elif self.align == 'right':   # 아래 정렬
                        y = float(base_rect.bottom()) - height
                    else:                         # 가운데 정렬
                        y = float(base_rect.center().y()) - height / 2.0
                else:
                    # 가로쓰기 direct editor는 기존 가로 정렬 기준을 유지한다.
                    if self.align == 'right':
                        x = float(getattr(self, 'anchor_x', base_rect.right())) - width
                    elif self.align == 'center':
                        x = float(getattr(self, 'anchor_x', base_rect.center().x())) - width / 2.0
                    else:
                        x = float(getattr(self, 'anchor_x', base_rect.left()))
                    y = float(getattr(self, 'anchor_y', base_rect.top()))

                old_pos = QPointF(self.pos())
                old_bounds = QRectF(self.boundingRect())
                self._inline_fixed_edit_bounds = QRectF(0, 0, width, height)
                self.setPos(x, y)
                self.resize(width, height)
                self.invalidate_vertical_layout()
                self.update()
                try:
                    if (abs(old_bounds.width() - width) > 0.5 or abs(old_bounds.height() - height) > 0.5
                            or abs(old_pos.x() - x) > 0.5 or abs(old_pos.y() - y) > 0.5):
                        self._inline_trace('INLINE_EDITOR_RESIZE', reason='adjust_to_contents', width=round(float(width), 2), height=round(float(height), 2), x=round(float(x), 2), y=round(float(y), 2))
                except Exception:
                    pass
                return

            rect = self._horizontal_content_rect_fast()
            width = max(30.0, float(rect.width())) + 12.0
            height = max(20.0, float(rect.height())) + 8.0
            if self.align == 'right':
                x = self.anchor_x - width
            elif self.align == 'center':
                x = self.anchor_x - width / 2.0
            else:
                x = self.anchor_x
            self.setPos(x, self.anchor_y)
            self.resize(width, height)
            if self._edit_proxy is not None:
                self._edit_proxy.resize(width, height)
            try:
                self._edit.setFixedSize(max(1, int(math.ceil(width))), max(1, int(math.ceil(height))))
            except Exception:
                pass
            self.apply_text_alignment()
            self.update()
        finally:
            self._adjusting = False

    def _split_vertical_lines(self, text):
        text = str(text or '')
        parts = text.split('\n')
        starts = []
        pos = 0
        for i, part in enumerate(parts):
            starts.append(pos)
            pos += len(part)
            if i < len(parts) - 1:
                pos += 1
        if not parts:
            parts = ['']
            starts = [0]
        return parts, starts

    def _plain_text_with_preedit_for_measurement(self):
        """Return visible text including the current IME preedit string.

        Korean IME composition can show a live 초성/중성 before it is committed.
        The direct editor used to resize only from committed text, so the translucent
        editor background and hit area lagged one input behind until the caret moved.
        Measurement must therefore include the preedit text at the caret position,
        while the stored document text remains unchanged until commit.
        """
        try:
            text = str(self.toPlainText() or '')
        except Exception:
            text = ''
        try:
            preedit = str(getattr(self, '_v_preedit_text', '') or '')
        except Exception:
            preedit = ''
        if not preedit:
            return text
        try:
            pos = int(getattr(self, '_v_caret_index', len(text)) or 0)
        except Exception:
            pos = len(text)
        pos = max(0, min(len(text), pos))
        return text[:pos] + preedit + text[pos:]


    def _inline_display_text_with_preedit(self):
        """Return committed text plus live IME preedit inserted at the caret.

        Important: this string is for *layout/paint/hit-test only*.  It must not be
        written back to the document until the IME sends commitString().  The older
        implementation measured the preedit text but painted it as an overlay at the
        caret, so inserting a Korean 초성 in the middle of a line drew it over the next
        committed glyph instead of pushing that glyph away.  All direct-editor layout
        must therefore be based on this display text.
        """
        try:
            text = str(self.toPlainText() or '')
        except Exception:
            text = ''
        try:
            preedit = str(getattr(self, '_v_preedit_text', '') or '')
        except Exception:
            preedit = ''
        try:
            caret = int(getattr(self, '_v_caret_index', len(text)) or 0)
        except Exception:
            caret = len(text)
        caret = max(0, min(len(text), caret))
        if not preedit:
            return text, text, '', caret, 0
        display = text[:caret] + preedit + text[caret:]
        return display, text, preedit, caret, len(preedit)

    def _display_index_for_logical_caret(self, logical_pos, caret=None, preedit_len=None):
        """Map a committed-text caret offset to display-text offset.

        Offsets after the live IME preedit are shifted by preedit_len because display
        layout includes the not-yet-committed glyphs.  Offsets before/at the insertion
        caret are unchanged.
        """
        try:
            pos = int(logical_pos or 0)
        except Exception:
            pos = 0
        try:
            if caret is None:
                caret = int(getattr(self, '_v_caret_index', 0) or 0)
        except Exception:
            caret = 0
        try:
            if preedit_len is None:
                preedit_len = len(str(getattr(self, '_v_preedit_text', '') or ''))
        except Exception:
            preedit_len = 0
        if preedit_len and pos > int(caret):
            return pos + int(preedit_len)
        return pos

    def _logical_index_for_display_char(self, display_index, caret=None, preedit_len=None):
        """Map a display-text character index to committed-text character index.

        Returns a negative index for live preedit glyphs so selection and commit logic
        never treat them as real document characters.
        """
        try:
            d = int(display_index or 0)
        except Exception:
            d = 0
        try:
            if caret is None:
                caret = int(getattr(self, '_v_caret_index', 0) or 0)
        except Exception:
            caret = 0
        try:
            if preedit_len is None:
                preedit_len = len(str(getattr(self, '_v_preedit_text', '') or ''))
        except Exception:
            preedit_len = 0
        if preedit_len and int(caret) <= d < int(caret) + int(preedit_len):
            return -100000 - (d - int(caret))
        if preedit_len and d >= int(caret) + int(preedit_len):
            return d - int(preedit_len)
        return d

    def _horizontal_tight_line_metrics_for_direct_editor(self, font, fm, sx=1.0, sy=1.0):
        """Return a visual line height based on real glyph ink, not font line metrics.

        Some comic/display fonts carry very large ascent/descent/lineSpacing values.
        If the inline editor uses those metrics as the background/selection height,
        the translucent editor box can become much taller than the visible text.
        Use QPainterPath glyph bounds as the base and only keep a small safety margin.
        """
        try:
            sx = max(0.10, float(sx or 1.0))
        except Exception:
            sx = 1.0
        try:
            sy = max(0.10, float(sy or 1.0))
        except Exception:
            sy = 1.0
        heights = []
        widths = []
        try:
            # Include Korean, CJK, latin ascenders/descenders and punctuation-ish shapes.
            for ch in "가나다라마바사아자차카타파하漢あアイMgypq0123":
                path = QPainterPath()
                path.addText(QPointF(0, 0), font, ch)
                br = path.boundingRect()
                if not br.isNull() and br.width() > 0 and br.height() > 0:
                    widths.append(float(br.width()) * sx)
                    heights.append(float(br.height()) * sy)
        except Exception:
            pass
        try:
            fm_h = float(fm.height()) * sy
        except Exception:
            fm_h = 12.0 * sy
        try:
            fm_line = float(fm.lineSpacing()) * sy
        except Exception:
            fm_line = fm_h
        ink_h = max(heights) if heights else max(4.0, fm_h * 0.72)
        # Keep a little breathing room, but cap against huge font metrics.
        base_line_h = max(4.0, ink_h * 1.12)
        metric_cap = max(base_line_h, ink_h * 1.28)
        base_line_h = min(max(base_line_h, min(fm_h, metric_cap)), max(fm_line, metric_cap), metric_cap)
        avg_w = max(widths) if widths else max(4.0, float(getattr(fm, 'averageCharWidth', lambda: 8)()) * sx)
        try:
            avg_w = max(4.0, min(max(4.0, avg_w), max(4.0, float(fm.averageCharWidth()) * sx * 1.80)))
        except Exception:
            avg_w = max(4.0, avg_w)
        return max(4.0, avg_w), max(4.0, base_line_h)

    def _vertical_tight_cell_metrics_for_direct_editor(self, font, fm, sx=1.0, sy=1.0):
        """Return tight cell width/height for vertical direct editing.

        The rendered vertical text uses actual glyph cell size as the base so
        line spacing 50/100/150% feels the same as horizontal text.  The editor
        must use the same logical cell size for caret/click/selection math.
        """
        try:
            widths = []
            heights = []
            for ch in "가漢あ":
                path = QPainterPath()
                path.addText(0, 0, font, ch)
                rect = path.boundingRect()
                if not rect.isNull() and rect.width() > 0 and rect.height() > 0:
                    widths.append(float(rect.width()))
                    heights.append(float(rect.height()))
            fw = max(1.0, float(fm.height()))
            fl = max(1.0, float(fm.lineSpacing()))
            cell_w = min(max(1.0, max(widths) if widths else fw * 0.72), fw) * max(0.10, float(sx or 1.0))
            cell_h = min(max(1.0, max(heights) if heights else fl * 0.72), fl) * max(0.10, float(sy or 1.0))
            return max(4.0, cell_w), max(4.0, cell_h)
        except Exception:
            return max(4.0, float(fm.height()) * max(0.10, float(sx or 1.0))), max(4.0, float(fm.lineSpacing()) * max(0.10, float(sy or 1.0)))

    def _vertical_column_step_for_direct_editor(self, base_cell_w, line_factor):
        """Column center advance for vertical line spacing.

        50% means columns nearly touch/overlap, 100% means normal cell pitch,
        150%+ adds breathing room.  This matches the horizontal line-spacing feel.
        """
        try:
            return max(1.0, float(base_cell_w or 1.0) * float(line_factor or 1.0))
        except Exception:
            return max(1.0, float(base_cell_w or 1.0))

    def _vertical_effective_letter_spacing_for_direct_editor(self, base_pitch):
        try:
            base = max(1.0, float(base_pitch or 1.0))
        except Exception:
            base = 1.0
        try:
            raw = float(getattr(self, 'letter_spacing', 0) or 0)
        except Exception:
            raw = 0.0
        safe = max(0.0, base * 0.12)
        if raw > 0:
            return raw + safe * 0.35
        return raw + safe

    def _vertical_space_advance_for_direct_editor(self, ch, pitch):
        """세로쓰기 직접 편집기의 공백 advance.

        세로쓰기 공백을 글자 1칸으로 두면 단어 사이가 문단처럼 벌어진다.
        원문 공백은 유지하되, 화면 배치에서는 가로쓰기 띄어쓰기처럼 작은 간격으로 본다.
        """
        try:
            base = max(1.0, float(pitch or 1.0))
        except Exception:
            base = 1.0
        ratio = 0.50 if str(ch or '') == '　' else 0.32
        return max(1.0, base * ratio)

    def _vertical_char_advance_for_direct_editor(self, ch, pitch):
        if str(ch or '').isspace() and str(ch or '') != '\n':
            return self._vertical_space_advance_for_direct_editor(ch, pitch)
        try:
            return max(1.0, float(pitch or 1.0))
        except Exception:
            return 1.0

    def _vertical_line_advances_for_direct_editor(self, line, pitch):
        return [self._vertical_char_advance_for_direct_editor(ch, pitch) for ch in str(line or '')]

    def _direct_editor_desired_local_size(self):
        """Return the live editor box size needed for the current direct-edit text.

        This is deliberately independent from the current boundingRect.  The old direct
        editor kept the initial edit_rect fixed, so added vertical text could overflow
        outside the translucent editing box.  Here the size is derived from the current
        text, font metrics, letter spacing, line spacing, and width/height stretch.
        """
        try:
            font = QFont(getattr(self, '_inline_font', QFont()))
        except Exception:
            font = QFont()
        fm = self._cached_font_metrics(font)
        sx = positive_scale_factor(getattr(self, 'char_width_pct', 100))
        sy = positive_scale_factor(getattr(self, 'char_height_pct', 100))
        line_factor = abs(float(clamp_text_line_spacing(getattr(self, 'line_spacing_pct', 100), 100)) / 100.0)
        letter_spacing = float(getattr(self, 'letter_spacing', 0) or 0)
        text = self._plain_text_with_preedit_for_measurement()
        lines, _starts = self._split_vertical_lines(text)
        if not lines:
            lines = ['']

        if self._is_vertical_writing():
            base_cell_w, base_pitch = self._vertical_tight_cell_metrics_for_direct_editor(font, fm, sx, sy)
            pitch = max(1.0, base_pitch + self._vertical_effective_letter_spacing_for_direct_editor(base_pitch))
            if pitch < base_pitch * 0.35:
                pitch = base_pitch * 0.35
            column_step = self._vertical_column_step_for_direct_editor(base_cell_w, line_factor)
            col_count = max(1, len(lines))
            max_line_h = pitch
            for line in lines:
                advances = self._vertical_line_advances_for_direct_editor(line, pitch)
                max_line_h = max(max_line_h, sum(advances) if advances else pitch)
            width = base_cell_w + column_step * (col_count - 1) + 14.0
            height = max_line_h + 14.0
            return (max(18.0, width), max(18.0, height))

        min_cell_w, base_line_h = self._horizontal_tight_line_metrics_for_direct_editor(font, fm, sx, sy)
        line_h = max(4.0, float(base_line_h) * line_factor)
        max_w = min_cell_w
        for line in lines:
            line = str(line or '')
            line_w = 0.0
            if not line:
                line_w = min_cell_w
            for j, ch in enumerate(line):
                try:
                    adv = float(fm.horizontalAdvance(ch if ch else ' ')) * sx
                except Exception:
                    adv = min_cell_w
                if ch == ' ':
                    try:
                        adv = max(adv, float(fm.horizontalAdvance(' ')) * sx)
                    except Exception:
                        pass
                adv = max(1.0, adv)
                if j > 0:
                    line_w += letter_spacing
                line_w += adv
            max_w = max(max_w, line_w)
        width = max_w + 14.0
        height = line_h * max(1, len(lines)) + 12.0
        return (max(30.0, width), max(20.0, height))


    def _layout_horizontal_direct_text(self):
        cache_key = (
            'horizontal-direct',
            self.toPlainText(),
            getattr(self, '_v_preedit_text', ''),
            float(self.boundingRect().width()),
            float(self.boundingRect().height()),
            self.align,
            self.letter_spacing,
            self.line_spacing_pct,
            self.char_width_pct,
            self.char_height_pct,
            self._inline_font.toString() if hasattr(self, '_inline_font') else '',
        )
        if self._vertical_layout_cache and self._vertical_layout_cache.get('key') == cache_key:
            return self._vertical_layout_cache

        rect = self.boundingRect()
        pad_x = 5.0
        pad_y = 5.0
        font = QFont(getattr(self, '_inline_font', QFont()))
        fm = self._cached_font_metrics(font)
        sx = positive_scale_factor(getattr(self, 'char_width_pct', 100))
        sy = positive_scale_factor(getattr(self, 'char_height_pct', 100))
        line_factor = abs(float(clamp_text_line_spacing(getattr(self, 'line_spacing_pct', 100), 100)) / 100.0)
        min_cell_w, base_line_h = self._horizontal_tight_line_metrics_for_direct_editor(font, fm, sx, sy)
        line_h = max(4.0, float(base_line_h) * line_factor)
        letter_spacing = float(getattr(self, 'letter_spacing', 0) or 0)

        display_text, logical_text, preedit, preedit_caret, preedit_len = self._inline_display_text_with_preedit()
        text = display_text
        logical_len = len(logical_text)
        lines, starts = self._split_vertical_lines(text)
        widths = []
        advances_by_line = []
        for line in lines:
            advances = []
            line_w = 0.0
            for j, ch in enumerate(str(line or '')):
                try:
                    adv = float(fm.horizontalAdvance(ch if ch else ' ')) * sx
                except Exception:
                    adv = min_cell_w
                if ch == ' ':
                    try:
                        adv = max(adv, float(fm.horizontalAdvance(' ')) * sx)
                    except Exception:
                        pass
                adv = max(1.0, adv)
                if j > 0:
                    line_w += letter_spacing
                advances.append(adv)
                line_w += adv
            if not line:
                line_w = min_cell_w
            widths.append(max(min_cell_w, line_w))
            advances_by_line.append(advances)

        total_h = max(line_h, line_h * max(1, len(lines)))
        available_h = max(1.0, rect.height() - pad_y * 2.0)
        y_start = pad_y + (available_h - total_h) / 2.0
        y_start = max(-rect.height() * 2.0, min(rect.height() * 3.0, y_start))

        display_caret_map = {}
        char_rects = []
        content_rect = QRectF()
        columns = []
        available_w = max(1.0, rect.width() - pad_x * 2.0)
        for row, line in enumerate(lines):
            line = str(line or '')
            start_index = starts[row] if row < len(starts) else 0
            line_w = widths[row] if row < len(widths) else min_cell_w
            if self.align == 'right':
                x0 = rect.width() - pad_x - line_w
            elif self.align == 'center':
                x0 = pad_x + (available_w - line_w) / 2.0
            else:
                x0 = pad_x
            y0 = y_start + row * line_h
            # Store both display offsets and committed-text offsets.  When IME preedit
            # is inserted in the middle of a line, display offsets after the caret are
            # shifted, but cursor navigation must still use committed-text offsets.
            logical_start = self._logical_index_for_display_char(start_index, preedit_caret, preedit_len)
            if logical_start < 0:
                logical_start = preedit_caret
            display_end = start_index + len(line)
            if preedit_len and display_end <= preedit_caret:
                logical_end = display_end
            elif preedit_len and display_end <= preedit_caret + preedit_len:
                logical_end = preedit_caret
            elif preedit_len and display_end > preedit_caret + preedit_len:
                logical_end = display_end - preedit_len
            else:
                logical_end = display_end
            logical_start = max(0, min(logical_len, int(logical_start)))
            logical_end = max(logical_start, min(logical_len, int(logical_end)))
            columns.append({'line': line, 'start': logical_start, 'display_start': start_index, 'length': logical_end - logical_start, 'display_length': len(line), 'x': x0, 'y0': y0, 'pitch': line_h, 'cell_w': min_cell_w, 'line_h': line_h, 'col': row})
            x = x0
            display_caret_map[start_index] = QPointF(x0, y0 + line_h / 2.0)
            advances = advances_by_line[row] if row < len(advances_by_line) else []
            for j, ch in enumerate(line):
                adv = advances[j] if j < len(advances) else min_cell_w
                r = QRectF(x, y0, max(1.0, adv), line_h)
                char_rects.append((self._logical_index_for_display_char(start_index + j, preedit_caret, preedit_len), ch, r))
                if content_rect.isNull():
                    content_rect = QRectF(r)
                else:
                    content_rect = content_rect.united(r)
                x += adv
                if j < len(line) - 1:
                    x += letter_spacing
                display_caret_map[start_index + j + 1] = QPointF(x, y0 + line_h / 2.0)
            if not line:
                r = QRectF(x0, y0, min_cell_w, line_h)
                if content_rect.isNull():
                    content_rect = QRectF(r)
                else:
                    content_rect = content_rect.united(r)
            if row < len(lines) - 1:
                display_caret_map[start_index + len(line)] = QPointF(x, y0 + line_h / 2.0)
                display_caret_map[start_index + len(line) + 1] = QPointF(pad_x, y_start + (row + 1) * line_h + line_h / 2.0)

        display_caret_map[len(text)] = display_caret_map.get(len(text), QPointF(pad_x, y_start + line_h / 2.0))
        caret_map = {}
        for logical_pos in range(0, logical_len + 1):
            if preedit_len and logical_pos == preedit_caret:
                display_pos = preedit_caret + preedit_len
            else:
                display_pos = self._display_index_for_logical_caret(logical_pos, preedit_caret, preedit_len)
            pnt = display_caret_map.get(display_pos)
            if pnt is not None:
                caret_map[logical_pos] = pnt
        caret_map[logical_len] = caret_map.get(logical_len, display_caret_map.get(len(text), QPointF(pad_x, y_start + line_h / 2.0)))
        if content_rect.isNull() or content_rect.width() <= 0 or content_rect.height() <= 0:
            content_rect = QRectF(pad_x, y_start, min_cell_w, line_h)
        content_rect = content_rect.adjusted(-2, -2, 2, 2)
        out = {
            'key': cache_key,
            'font': font,
            'fm': fm,
            'columns': columns,
            'caret_map': caret_map,
            'char_rects': char_rects,
            'content_rect': content_rect,
            'base_cell_w': min_cell_w,
            'pitch': line_h,
            'horizontal_direct': True,
        }
        self._vertical_layout_cache = out
        return out

    def _layout_vertical_text(self):
        if not self._is_vertical_writing():
            return self._layout_horizontal_direct_text()
        cache_key = (
            self.toPlainText(),
            getattr(self, '_v_preedit_text', ''),
            float(self.boundingRect().width()),
            float(self.boundingRect().height()),
            self.align,
            self.letter_spacing,
            self.line_spacing_pct,
            self.char_width_pct,
            self.char_height_pct,
            self._inline_font.toString() if hasattr(self, '_inline_font') else '',
        )
        if self._vertical_layout_cache and self._vertical_layout_cache.get('key') == cache_key:
            return self._vertical_layout_cache

        rect = self.boundingRect()
        pad_x = 5.0
        pad_y = 5.0
        font = QFont(getattr(self, '_inline_font', QFont()))
        fm = self._cached_font_metrics(font)
        sx = positive_scale_factor(getattr(self, 'char_width_pct', 100))
        sy = positive_scale_factor(getattr(self, 'char_height_pct', 100))
        base_cell_w, base_pitch = self._vertical_tight_cell_metrics_for_direct_editor(font, fm, sx, sy)
        pitch = max(1.0, base_pitch + self._vertical_effective_letter_spacing_for_direct_editor(base_pitch))
        if pitch < base_pitch * 0.35:
            pitch = base_pitch * 0.35
        line_factor = abs(float(clamp_text_line_spacing(getattr(self, 'line_spacing_pct', 100), 100)) / 100.0)
        column_step = self._vertical_column_step_for_direct_editor(base_cell_w, line_factor)

        display_text, logical_text, preedit, preedit_caret, preedit_len = self._inline_display_text_with_preedit()
        text = display_text
        logical_len = len(logical_text)
        lines, starts = self._split_vertical_lines(text)
        col_count = max(1, len(lines))
        total_w = base_cell_w + column_step * (col_count - 1)
        right_x = rect.center().x() + total_w / 2.0 - base_cell_w / 2.0

        columns = []
        display_caret_map = {}
        char_rects = []
        content_rect = QRectF()

        for col, line in enumerate(lines):
            line = str(line or '')
            start_index = starts[col] if col < len(starts) else 0
            x = right_x - col * column_step
            advances = self._vertical_line_advances_for_direct_editor(line, pitch)
            line_h = max(pitch, sum(advances) if advances else pitch)
            available_h = max(1.0, rect.height() - pad_y * 2.0)
            if self.align == 'left':  # 세로쓰기에서는 위 정렬
                y0 = pad_y
            elif self.align == 'right':  # 세로쓰기에서는 아래 정렬
                y0 = rect.height() - pad_y - line_h
            else:
                y0 = pad_y + (available_h - line_h) / 2.0
            y0 = max(-rect.height() * 2.0, min(rect.height() * 3.0, y0))
            logical_start = self._logical_index_for_display_char(start_index, preedit_caret, preedit_len)
            if logical_start < 0:
                logical_start = preedit_caret
            display_end = start_index + len(line)
            if preedit_len and display_end <= preedit_caret:
                logical_end = display_end
            elif preedit_len and display_end <= preedit_caret + preedit_len:
                logical_end = preedit_caret
            elif preedit_len and display_end > preedit_caret + preedit_len:
                logical_end = display_end - preedit_len
            else:
                logical_end = display_end
            logical_start = max(0, min(logical_len, int(logical_start)))
            logical_end = max(logical_start, min(logical_len, int(logical_end)))
            column = {
                'line': line,
                'start': logical_start,
                'display_start': start_index,
                'length': logical_end - logical_start,
                'display_length': len(line),
                'x': x,
                'y0': y0,
                'pitch': pitch,
                'cell_w': base_cell_w,
                'line_h': line_h,
                'col': col,
                'advances': advances,
            }
            columns.append(column)
            y_cursor = y0
            display_caret_map[start_index] = QPointF(x, y_cursor)
            for j, ch in enumerate(line):
                adv = advances[j] if j < len(advances) else pitch
                r = QRectF(x - base_cell_w / 2.0, y_cursor, base_cell_w, max(1.0, adv))
                char_rects.append((self._logical_index_for_display_char(start_index + j, preedit_caret, preedit_len), ch, r))
                if content_rect.isNull():
                    content_rect = QRectF(r)
                else:
                    content_rect = content_rect.united(r)
                y_cursor += adv
                display_caret_map[start_index + j + 1] = QPointF(x, y_cursor)
            if not line:
                r = QRectF(x - base_cell_w / 2.0, y0, base_cell_w, pitch)
                if content_rect.isNull():
                    content_rect = QRectF(r)
                else:
                    content_rect = content_rect.united(r)
            # newline caret belongs to the visual end of the previous column.
            if col < len(lines) - 1:
                display_caret_map[start_index + len(line)] = QPointF(x, y_cursor)
                display_caret_map[start_index + len(line) + 1] = QPointF(right_x - (col + 1) * column_step, 0)

        # 마지막 커서 보정
        display_caret_map[len(text)] = display_caret_map.get(len(text), QPointF(right_x, rect.center().y()))
        caret_map = {}
        for logical_pos in range(0, logical_len + 1):
            if preedit_len and logical_pos == preedit_caret:
                display_pos = preedit_caret + preedit_len
            else:
                display_pos = self._display_index_for_logical_caret(logical_pos, preedit_caret, preedit_len)
            pnt = display_caret_map.get(display_pos)
            if pnt is not None:
                caret_map[logical_pos] = pnt
        caret_map[logical_len] = caret_map.get(logical_len, display_caret_map.get(len(text), QPointF(right_x, rect.center().y())))
        if content_rect.isNull() or content_rect.width() <= 0 or content_rect.height() <= 0:
            content_rect = QRectF(right_x - base_cell_w / 2.0, rect.center().y() - pitch / 2.0, base_cell_w, pitch)
        content_rect = content_rect.adjusted(-2, -2, 2, 2)

        out = {
            'key': cache_key,
            'font': font,
            'fm': fm,
            'columns': columns,
            'caret_map': caret_map,
            'char_rects': char_rects,
            'content_rect': content_rect,
            'base_cell_w': base_cell_w,
            'pitch': pitch,
        }
        self._vertical_layout_cache = out
        return out

    def _selected_range(self):
        try:
            a = int(getattr(self, '_v_selection_anchor', 0))
            b = int(getattr(self, '_v_caret_index', 0))
            return (min(a, b), max(a, b))
        except Exception:
            return (0, 0)

    @staticmethod
    def _clipboard_plain_text_from_qt_selection(text):
        # QTextCursor.selectedText() uses U+2029 for paragraph separators.
        return str(text or '').replace('\u2029', '\n').replace('\r\n', '\n').replace('\r', '\n')

    def _publish_inline_plain_text_clipboard(self, text, reason='copy'):
        """Publish inline-editor selected text to both OS clipboard and YSB paste buffer.

        The app has two clipboards: OS plain text and the internal text-box clipboard.
        Copying text *inside* an inline editor must update both, otherwise leaving the
        editor and pressing Ctrl+V may still paste an older text-box object.
        """
        text = self._clipboard_plain_text_from_qt_selection(text)
        if not text:
            return False
        try:
            QApplication.clipboard().setText(text)
        except Exception:
            pass
        try:
            main = getattr(self, 'main_window', None)
            if main is not None and hasattr(main, 'make_text_clipboard_item_from_plain_text'):
                item = main.make_text_clipboard_item_from_plain_text(text)
                if item:
                    main.text_clipboard = [item]
                    main.text_clipboard_is_plain = True
                    main.text_paste_pending = False
                    try:
                        if getattr(main, 'view', None) is not None and hasattr(main.view, 'clear_paste_preview'):
                            main.view.clear_paste_preview()
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            self._inline_trace('INLINE_EDITOR_CLIPBOARD_TEXT_COPY', reason=str(reason or ''), text_len=len(text))
        except Exception:
            pass
        return True

    def copy_widget_selection_to_plain_clipboard(self, cut=False):
        if self._vertical_editor:
            return False
        try:
            if self._edit is None:
                return False
            cursor = self._edit.textCursor()
            if not cursor.hasSelection():
                return False
            text = self._clipboard_plain_text_from_qt_selection(cursor.selectedText())
            if not text:
                return False
            self._publish_inline_plain_text_clipboard(text, reason='cut' if cut else 'copy')
            if cut:
                cursor.removeSelectedText()
                self._edit.setTextCursor(cursor)
                self._schedule_adjust_to_contents(reason='cut')
            return True
        except Exception:
            return False

    def _copy_direct_selection_to_plain_clipboard(self, cut=False):
        if not self._vertical_editor:
            return False
        a, b = self._selected_range()
        if not (b > a):
            return False
        text = self.toPlainText()[a:b]
        if not self._publish_inline_plain_text_clipboard(text, reason='cut' if cut else 'copy'):
            return False
        if cut:
            self._replace_vertical_selection('', reason='cut')
        return True

    def prepare_text_for_commit(self, reason='commit'):
        """Force pending IME/preedit state into committed text before closing.

        Ctrl+Enter/focus-out used to read toPlainText() while Korean IME still had a
        live preedit glyph.  That glyph is visible on screen but not in _v_text yet,
        so the final commit could miss the last edit.  Treat close/commit as an
        explicit acceptance of the visible preedit.
        """
        if self._vertical_editor:
            try:
                preedit = str(getattr(self, '_v_preedit_text', '') or '')
            except Exception:
                preedit = ''
            if preedit:
                try:
                    self._inline_trace('INLINE_EDITOR_IME_PREEDIT_FORCE_COMMIT', reason=str(reason or ''), preedit_len=len(preedit), caret=int(getattr(self, '_v_caret_index', 0) or 0))
                except Exception:
                    pass
                self._replace_vertical_selection(preedit, push_undo=False, reason='ime-preedit-force-commit')
            return self.toPlainText()
        try:
            im = QApplication.inputMethod()
            if im is not None and hasattr(im, 'commit'):
                im.commit()
        except Exception:
            pass
        try:
            if self._edit is not None:
                self._edit.document().adjustSize()
        except Exception:
            pass
        return self.toPlainText()

    def _push_vertical_undo_snapshot(self):
        if not self._vertical_editor:
            return
        try:
            snap = (self.toPlainText(), int(getattr(self, '_v_caret_index', 0)), int(getattr(self, '_v_selection_anchor', 0)))
            stack = getattr(self, '_v_undo_stack', None)
            if stack is None:
                self._v_undo_stack = []
                stack = self._v_undo_stack
            if not stack or stack[-1] != snap:
                stack.append(snap)
                if len(stack) > 120:
                    del stack[0:len(stack) - 120]
            self._v_redo_stack = []
        except Exception:
            pass

    def _sync_direct_editor_after_text_change(self, reason='text-change'):
        """Immediately rebuild the direct editor layout after text changes.

        Without this, inserted characters can appear to sit on top of the old layout
        until a caret move invalidates/repaints the glyph position table.  Both
        horizontal and vertical direct editors use the same layout cache, so every
        insert/delete/paste/IME commit/preedit must invalidate, resize, and repaint now.
        """
        try:
            old_scene_rect = self.mapToScene(self.boundingRect()).boundingRect()
        except Exception:
            old_scene_rect = QRectF()
        try:
            self.invalidate_vertical_layout()
        except Exception:
            pass
        try:
            self.adjust_to_contents()
        except Exception:
            pass
        try:
            self.invalidate_vertical_layout()
        except Exception:
            pass
        try:
            new_scene_rect = self.mapToScene(self.boundingRect()).boundingRect()
        except Exception:
            new_scene_rect = QRectF()
        try:
            dirty_local = self.boundingRect().adjusted(-12, -12, 12, 12)
            self.update(dirty_local)
        except Exception:
            try:
                self.update()
            except Exception:
                pass
        try:
            dirty_scene = QRectF(old_scene_rect)
            if dirty_scene.isNull() or dirty_scene.width() <= 0 or dirty_scene.height() <= 0:
                dirty_scene = QRectF(new_scene_rect)
            else:
                dirty_scene = dirty_scene.united(new_scene_rect)
            dirty_scene = dirty_scene.adjusted(-24, -24, 24, 24)
            sc = self.scene()
            if sc is not None:
                sc.update(dirty_scene)
        except Exception:
            pass
        try:
            self._inline_trace('INLINE_EDITOR_LIVE_SYNC', reason=reason,
                               text_len=len(self.toPlainText()),
                               preedit_len=len(str(getattr(self, '_v_preedit_text', '') or '')),
                               width=round(float(self.boundingRect().width()), 2),
                               height=round(float(self.boundingRect().height()), 2))
        except Exception:
            pass

    def _restore_vertical_snapshot(self, snap):
        try:
            text, caret, anchor = snap
        except Exception:
            return
        self._v_text = str(text or '')
        self._v_caret_index = max(0, min(len(self._v_text), int(caret)))
        self._v_selection_anchor = max(0, min(len(self._v_text), int(anchor)))
        self._v_preedit_text = ''
        self._v_ime_selection_preedit_active = False
        try:
            self._v_document.setPlainText(self._v_text)
        except Exception:
            pass
        self._sync_direct_editor_after_text_change(reason='restore-snapshot')
        self._update_desired_caret_axis_from_current()

    def _has_vertical_selection(self):
        a, b = self._selected_range()
        return b > a

    def _inline_caret_point(self, pos=None):
        """Return the current visual caret point from the direct inline layout."""
        try:
            if pos is None:
                pos = int(getattr(self, '_v_caret_index', 0) or 0)
            pos = max(0, min(len(self.toPlainText()), int(pos)))
            layout = self._layout_vertical_text()
            caret_map = layout.get('caret_map') or {}
            p = caret_map.get(pos)
            if p is not None:
                return QPointF(p)
        except Exception:
            pass
        try:
            return QPointF(self.boundingRect().center())
        except Exception:
            return QPointF(0.0, 0.0)

    def _update_desired_caret_axis_from_current(self):
        """Refresh visual navigation target after explicit caret edits/clicks."""
        try:
            p = self._inline_caret_point()
            self._v_desired_caret_x = float(p.x())
            self._v_desired_caret_y = float(p.y())
        except Exception:
            self._v_desired_caret_x = None
            self._v_desired_caret_y = None

    def _inline_editor_selection_dirty_rect(self):
        """Return a conservative local dirty rect for the current direct-editor selection.

        Selection/caret drawing is done by this QGraphicsItem, but the main view often runs
        with BoundingRectViewportUpdate and cached background while zooming/panning.  If only
        the new caret rect is updated, old selection highlights can visually remain as
        grey/blue block fragments.  Use the union of selected glyph cells, caret and bounds.
        """
        try:
            a, b = self._selected_range()
        except Exception:
            a = b = 0
        rect = QRectF()
        try:
            layout = self._layout_vertical_text()
            for idx, _ch, r in layout.get('char_rects') or []:
                try:
                    if a <= int(idx) < b:
                        rr = QRectF(r).adjusted(-4, -4, 4, 4)
                        rect = rr if rect.isNull() else rect.united(rr)
                except Exception:
                    pass
        except Exception:
            pass
        try:
            cr = QRectF(self._vertical_cursor_rect()).adjusted(-12, -12, 12, 12)
            rect = cr if rect.isNull() else rect.united(cr)
        except Exception:
            pass
        try:
            br = QRectF(self.boundingRect()).adjusted(-12, -12, 12, 12)
            if rect.isNull():
                rect = br
            else:
                rect = rect.united(br)
        except Exception:
            pass
        return rect

    def _force_inline_editor_dirty_repaint(self, local_rect=None, reason='selection-caret'):
        """Force repaint of inline editor dirty area in item, scene and viewport layers."""
        try:
            rect = QRectF(local_rect) if local_rect is not None else self._inline_editor_selection_dirty_rect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                rect = QRectF(self.boundingRect()).adjusted(-12, -12, 12, 12)
        except Exception:
            try:
                rect = QRectF(self.boundingRect()).adjusted(-12, -12, 12, 12)
            except Exception:
                rect = None
        try:
            if rect is not None:
                self.update(QRectF(rect).adjusted(-4, -4, 4, 4))
            else:
                self.update()
        except Exception:
            try:
                self.update()
            except Exception:
                pass
        try:
            scene = self.scene()
        except Exception:
            scene = None
        if scene is not None and rect is not None:
            try:
                scene_rect = self.mapToScene(QRectF(rect).adjusted(-8, -8, 8, 8)).boundingRect()
                scene.update(scene_rect)
            except Exception:
                pass
        try:
            mw = getattr(self, 'main_window', None)
            view = getattr(mw, 'view', None) if mw is not None else None
            if view is not None and hasattr(view, 'viewport'):
                view.viewport().update()
        except Exception:
            pass
        try:
            self._inline_trace('INLINE_EDITOR_FORCE_REPAINT', reason=str(reason or ''),
                               has_rect=bool(rect is not None))
        except Exception:
            pass

    def _set_vertical_caret(self, pos, keep_anchor=False, preserve_desired=False):
        text_len = len(self.toPlainText())
        old_caret = int(getattr(self, '_v_caret_index', 0) or 0)
        old_anchor = int(getattr(self, '_v_selection_anchor', old_caret) or old_caret)
        old_dirty = None
        old_selection_dirty = None
        try:
            old_dirty = QRectF(self._vertical_cursor_rect()).adjusted(-10, -10, 10, 10)
        except Exception:
            old_dirty = None
        try:
            if old_anchor != old_caret:
                old_selection_dirty = self._inline_editor_selection_dirty_rect()
        except Exception:
            old_selection_dirty = None

        pos = max(0, min(text_len, int(pos)))
        self._v_caret_index = pos
        if not keep_anchor:
            self._v_selection_anchor = pos
        self._v_preedit_text = ''
        self._v_ime_selection_preedit_active = False
        self._v_cursor_visible = True
        if not preserve_desired:
            self._update_desired_caret_axis_from_current()

        # 커서/선택 이동만으로는 글자 배치가 바뀌지 않는다. 대신 이전 커서/선택 영역과
        # 새 커서/선택 영역을 함께 다시 그려야 잔상이 남지 않는다. 특히 Ctrl+A나
        # 드래그 선택 뒤 방향키로 선택을 접는 경우, 예전 선택 하이라이트가 텍스트
        # 테두리/커서처럼 남을 수 있으므로 scene/viewport까지 강제로 갱신한다.
        try:
            new_dirty = QRectF(self._vertical_cursor_rect()).adjusted(-10, -10, 10, 10)
            old_selected = old_anchor != old_caret
            new_selected = int(getattr(self, '_v_selection_anchor', pos) or pos) != pos
            dirty = QRectF()
            for r in (old_dirty, old_selection_dirty, new_dirty, self._inline_editor_selection_dirty_rect() if new_selected else None):
                try:
                    if r is not None and QRectF(r).isValid():
                        rr = QRectF(r)
                        dirty = rr if dirty.isNull() else dirty.united(rr)
                except Exception:
                    pass
            if old_selected or new_selected or bool(keep_anchor):
                try:
                    dirty = dirty.united(QRectF(self.boundingRect()).adjusted(-12, -12, 12, 12)) if not dirty.isNull() else QRectF(self.boundingRect()).adjusted(-12, -12, 12, 12)
                except Exception:
                    pass
                self._force_inline_editor_dirty_repaint(dirty, reason='selection-caret-change')
            elif old_dirty is not None:
                self._force_inline_editor_dirty_repaint(old_dirty.united(new_dirty), reason='caret-move')
            else:
                self._force_inline_editor_dirty_repaint(new_dirty, reason='caret-move')
        except Exception:
            self._force_inline_editor_dirty_repaint(reason='caret-fallback')

    def _delete_selection_for_ime_preedit(self):
        """Remove an active selection when IME preedit starts.

        Korean IME can send only preedit text first (for example a single 초성)
        and send commitString later.  Native editors still replace the selected
        range immediately at the first preedit frame.  If we only draw preedit as
        display_text while keeping the selection text in the document, the 초성
        appears after the selected range and the old selection remains visible.
        """
        if not self._vertical_editor:
            return False
        a, b = self._selected_range()
        if not (b > a):
            return False
        text = self.toPlainText()
        self._push_vertical_undo_snapshot()
        self._v_text = text[:a] + text[b:]
        self._v_caret_index = a
        self._v_selection_anchor = a
        self._v_ime_selection_preedit_active = True
        try:
            self._v_document.setPlainText(self._v_text)
        except Exception:
            pass
        try:
            self._inline_trace('INLINE_EDITOR_IME_PREEDIT_REPLACED_SELECTION',
                               removed_len=b - a, caret=a, text_len=len(self._v_text))
        except Exception:
            pass
        return True

    def _replace_vertical_selection(self, insert_text, push_undo=True, reason='text-change'):
        if not self._vertical_editor:
            return
        text = self.toPlainText()
        a, b = self._selected_range()
        insert_text = str(insert_text or '')
        caret = max(0, min(len(text), int(getattr(self, '_v_caret_index', 0) or 0)))
        # A normal click must mean an insertion caret, not a one-character selection.
        # Tiny mouse jitter after press used to leave a stale anchor, so the first typed
        # character replaced/overlapped the next glyph while later characters inserted normally.
        has_selection = bool(b > a)
        if not has_selection:
            a = b = caret
        action = 'replace' if has_selection else 'insert'
        if a == b and not insert_text:
            return
        if push_undo:
            self._push_vertical_undo_snapshot()
        self._v_text = text[:a] + insert_text + text[b:]
        self._v_caret_index = a + len(insert_text)
        self._v_selection_anchor = self._v_caret_index
        self._v_preedit_text = ''
        self._v_ime_selection_preedit_active = False
        try:
            self._v_document.setPlainText(self._v_text)
        except Exception:
            pass
        self._sync_direct_editor_after_text_change(reason=reason)
        self._update_desired_caret_axis_from_current()
        try:
            self._inline_trace('INLINE_EDITOR_TEXT_CHANGE', action=action, inserted_len=len(insert_text), new_len=len(self._v_text), caret=self._v_caret_index)
        except Exception:
            pass

    def _delete_vertical_backward(self):
        if self._has_vertical_selection():
            self._replace_vertical_selection('')
            return
        if self._v_caret_index <= 0:
            return
        text = self.toPlainText()
        i = self._v_caret_index
        self._push_vertical_undo_snapshot()
        self._v_text = text[:i - 1] + text[i:]
        self._v_caret_index = i - 1
        self._v_selection_anchor = self._v_caret_index
        try:
            self._v_document.setPlainText(self._v_text)
        except Exception:
            pass
        self._sync_direct_editor_after_text_change(reason='delete-backward')
        self._update_desired_caret_axis_from_current()

    def _delete_vertical_forward(self):
        if self._has_vertical_selection():
            self._replace_vertical_selection('')
            return
        text = self.toPlainText()
        i = self._v_caret_index
        if i >= len(text):
            return
        self._push_vertical_undo_snapshot()
        self._v_text = text[:i] + text[i + 1:]
        self._v_selection_anchor = self._v_caret_index
        try:
            self._v_document.setPlainText(self._v_text)
        except Exception:
            pass
        self._sync_direct_editor_after_text_change(reason='delete-forward')
        self._update_desired_caret_axis_from_current()

    def _vertical_index_from_pos(self, pos):
        layout = self._layout_vertical_text()
        if layout.get('horizontal_direct'):
            lines, starts = self._split_vertical_lines(self.toPlainText())
            rows = layout.get('columns') or []
            if not rows:
                return 0
            y = float(pos.y())
            row = min(rows, key=lambda c: abs(y - (float(c.get('y0', 0.0)) + float(c.get('pitch', 1.0)) / 2.0)))
            line = str(row.get('line') or '')
            start = int(row.get('start') or 0)
            char_rects = [(idx, ch, QRectF(r)) for idx, ch, r in (layout.get('char_rects') or []) if start <= int(idx) < start + len(line)]
            x = float(pos.x())
            if not char_rects:
                return start
            for idx, _ch, r in char_rects:
                if x < r.center().x():
                    return int(idx)
            return start + len(line)

        columns = layout.get('columns') or []
        if not columns:
            return 0
        x = float(pos.x())
        y = float(pos.y())
        col = min(columns, key=lambda c: abs(x - float(c.get('x', 0.0))))
        line = str(col.get('line') or '')
        start = int(col.get('start') or 0)
        pitch = max(1.0, float(col.get('pitch') or 1.0))
        y0 = float(col.get('y0') or 0.0)

        # 공백 슬롯은 글자가 보이지 않기 때문에, 그 안을 클릭한 뒤 입력하면
        # 새 글자가 '공백 칸 안에 들어간 것처럼' 보인다. 실제 텍스트에는 공백이
        # 살아 있으므로 커서를 움직이면 다시 띄어쓰기가 살아나는 것처럼 느껴진다.
        # 세로쓰기에서는 공백 칸 클릭을 기본적으로 '공백 뒤' caret으로 해석해
        # 공백을 구분자처럼 보존하고, 새 글자가 빈칸을 덮어쓴 것처럼 보이지 않게 한다.
        try:
            for idx, ch, r in layout.get('char_rects') or []:
                idx = int(idx)
                if not (start <= idx < start + len(line)):
                    continue
                rr = QRectF(r)
                if rr.contains(pos):
                    if str(ch).isspace() and str(ch) != '\n':
                        return min(start + len(line), idx + 1)
                    return idx if y < rr.center().y() else min(start + len(line), idx + 1)
        except Exception:
            pass

        # 공백 advance가 일반 글자보다 짧기 때문에 pitch만으로 역산하면
        # 공백 뒤쪽 클릭에서 커서가 한 칸 밀릴 수 있다. char_rect에 걸리지 않은 위치는
        # 캐럿 좌표 중 가장 가까운 곳으로 보정한다.
        try:
            candidates = []
            caret_map = layout.get('caret_map') or {}
            for off in range(0, len(line) + 1):
                p = caret_map.get(start + off)
                if p is not None:
                    candidates.append((abs(float(p.y()) - y), off))
            if candidates:
                return start + sorted(candidates, key=lambda pair: pair[0])[0][1]
        except Exception:
            pass
        offset = int(round((y - y0) / pitch))
        offset = max(0, min(len(line), offset))
        return start + offset

    def _vertical_cursor_rect(self):
        layout = self._layout_vertical_text()
        caret_map = layout.get('caret_map') or {}
        p = caret_map.get(int(getattr(self, '_v_caret_index', 0)))
        if p is None:
            p = QPointF(self.boundingRect().center())
        if layout.get('horizontal_direct'):
            line_h = float(layout.get('pitch') or 14.0)
            thickness = max(2.0, min(5.0, line_h * 0.08))
            return QRectF(p.x() - thickness / 2.0, p.y() - line_h * 0.48, thickness, line_h * 0.96)
        cell_w = float(layout.get('base_cell_w') or 10.0)
        # 세로쓰기 커서는 문장 진행 방향 사이에 놓이는 '가로 커서'가 맞다.
        # 너무 얇으면 배경/확대율에 묻혀 안 보이므로 최소 높이를 둔다.
        thickness = max(3.0, min(8.0, cell_w * 0.08))
        return QRectF(p.x() - cell_w * 0.58, p.y() - thickness / 2.0, cell_w * 1.16, thickness)

    def _toggle_vertical_cursor_visible(self):
        if not self._vertical_editor:
            return
        # QGraphicsScene 안에서는 뷰/툴바가 순간적으로 포커스를 가져가는 일이 있어
        # hasFocus()만 믿으면 활성 편집기인데도 커서가 사라질 수 있다.
        self._v_cursor_visible = not bool(getattr(self, '_v_cursor_visible', True))
        try:
            self.update(self._vertical_cursor_rect().adjusted(-8, -8, 8, 8))
        except Exception:
            self.update()


    def cleanup_inline_caret_visuals(self, reason='close'):
        """Stop caret blinking and repaint the last inline-editor cursor/background area.

        The direct inline editor is a QGraphicsObject.  When Ctrl+Enter/focus-out closes it,
        the final text item may be refreshed immediately while the last caret frame is still
        painted in the viewport.  Stop the blink timer, hide the caret/preedit/selection, and
        explicitly repaint the old cursor/editor rect before the scene item is removed.
        """
        try:
            self._inline_trace('INLINE_EDITOR_CARET_CLEANUP_BEGIN', reason=str(reason or ''))
        except Exception:
            pass

        dirty_scene_rects = []
        try:
            dirty_scene_rects.append(self.mapToScene(self.boundingRect().adjusted(-12, -12, 12, 12)).boundingRect())
        except Exception:
            pass
        try:
            dirty_scene_rects.append(self.mapToScene(self._vertical_cursor_rect().adjusted(-12, -12, 12, 12)).boundingRect())
        except Exception:
            pass
        try:
            if self._edit_proxy is not None:
                dirty_scene_rects.append(self._edit_proxy.mapToScene(self._edit_proxy.boundingRect().adjusted(-12, -12, 12, 12)).boundingRect())
        except Exception:
            pass

        try:
            timer = getattr(self, '_blink_timer', None)
            if timer is not None:
                timer.stop()
        except Exception:
            pass
        try:
            self._inline_paint_suppressed = True
            self._closing = True
            self.setEnabled(False)
            self.clearFocus()
        except Exception:
            pass
        try:
            self._v_cursor_visible = False
            self._v_preedit_text = ''
            self._v_ime_selection_preedit_active = False
            self._v_selection_anchor = int(getattr(self, '_v_caret_index', 0) or 0)
        except Exception:
            pass
        try:
            if self._edit is not None:
                cursor = self._edit.textCursor()
                cursor.clearSelection()
                self._edit.setTextCursor(cursor)
                self._edit.setCursorWidth(0)
                self._edit.setVisible(False)
        except Exception:
            pass
        try:
            if self._edit_proxy is not None:
                self._edit_proxy.setEnabled(False)
                self._edit_proxy.setVisible(False)
        except Exception:
            pass
        try:
            self.prepareGeometryChange()
        except Exception:
            pass
        try:
            self.setOpacity(0.0)
        except Exception:
            pass
        try:
            self.setVisible(False)
        except Exception:
            pass

        scene = None
        try:
            scene = self.scene()
        except Exception:
            scene = None
        for rect in dirty_scene_rects:
            try:
                if scene is not None and rect is not None and rect.isValid():
                    scene.update(QRectF(rect).adjusted(-4, -4, 4, 4))
                    try:
                        self._inline_trace(
                            'INLINE_EDITOR_CARET_REPAINT_OLD_RECT',
                            reason=str(reason or ''),
                            x=round(float(QRectF(rect).x()), 2),
                            y=round(float(QRectF(rect).y()), 2),
                            w=round(float(QRectF(rect).width()), 2),
                            h=round(float(QRectF(rect).height()), 2),
                        )
                    except Exception:
                        pass
            except Exception:
                pass
        try:
            mw = getattr(self, 'main_window', None)
            view = getattr(mw, 'view', None) if mw is not None else None
            if view is not None and hasattr(view, 'viewport'):
                view.viewport().update()
        except Exception:
            pass
        try:
            self._inline_trace('INLINE_EDITOR_CARET_CLEANUP_DONE', reason=str(reason or ''))
        except Exception:
            pass

    def paint(self, painter, option, widget=None):
        # 종료 처리 중인 인라인 편집기는 절대 다시 그리지 않는다.
        # removeItem 직전/직후 Qt가 마지막 paint를 한 번 더 요청하면 파란 caret이 잔상처럼 남을 수 있다.
        try:
            if bool(getattr(self, '_inline_paint_suppressed', False)) or bool(getattr(self, '_closing', False)):
                return
        except Exception:
            pass
        bg_rect = self.boundingRect().adjusted(-4, -3, 4, 3)
        painter.save()
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(getattr(self, 'inline_edit_bg_color', QColor(255, 255, 255, 190)))
        painter.drawRoundedRect(bg_rect, 4, 4)
        painter.restore()

        if self._vertical_editor:
            self._paint_vertical_editor(painter)

        painter.save()
        pen = QPen(getattr(self, 'inline_edit_border_color', QColor(80, 160, 255)), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.boundingRect())
        painter.restore()

    def _inline_glyph_path(self, ch, rect, font, fm):
        path = QPainterPath()
        try:
            if ch == '\n' or str(ch).isspace():
                return path
            raw = QPainterPath()
            raw.addText(QPointF(0, 0), font, str(ch))
            br = raw.boundingRect()
            if br.isNull() or br.width() <= 0 or br.height() <= 0:
                return path
            # Final renderer scales glyph height after creating the path.  The editor preview
            # mirrors that enough to avoid the current "plain QPainter text" mismatch.
            try:
                sy = positive_scale_factor(getattr(self, 'char_height_pct', 100))
            except Exception:
                sy = 1.0
            tr = QTransform()
            tr.translate(float(rect.center().x()), float(rect.center().y()))
            tr.scale(1.0, sy)
            tr.translate(-float(br.center().x()), -float(br.center().y()))
            path = tr.map(raw)
        except Exception:
            pass
        return path

    def _draw_inline_preview_char(self, painter, ch, rect, font):
        """Draw one lightweight inline-editor preview glyph.

        Deliberately does not draw stroke, double stroke, shadow, gradient, warp, or other
        final-render effects.  The direct editor must stay responsive while typing, so it only
        reflects font, size, fill color, letter/line spacing layout, character width, and
        character height.
        """
        try:
            if ch == '\n' or str(ch).isspace():
                return
            rr = QRectF(rect)
            if rr.width() <= 0 or rr.height() <= 0:
                return
            try:
                sy = positive_scale_factor(getattr(self, 'char_height_pct', 100))
            except Exception:
                sy = 1.0
            # QFont stretch already carries char_width.  Height has no matching QFont knob,
            # so scale only the painter vertically around the glyph slot center.
            if abs(sy - 1.0) < 0.015:
                painter.drawText(rr, Qt.AlignmentFlag.AlignCenter, str(ch))
                return
            painter.save()
            c = rr.center()
            painter.translate(c)
            painter.scale(1.0, sy)
            scaled_rect = QRectF(-rr.width() / 2.0, -rr.height() / (2.0 * sy), rr.width(), rr.height() / sy)
            painter.drawText(scaled_rect, Qt.AlignmentFlag.AlignCenter, str(ch))
            painter.restore()
        except Exception:
            try:
                painter.drawText(QRectF(rect), Qt.AlignmentFlag.AlignCenter, str(ch))
            except Exception:
                pass

    def _paint_vertical_editor(self, painter):
        layout = self._layout_vertical_text()
        font = QFont(layout.get('font', getattr(self, '_inline_font', QFont())))
        painter.save()
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
            painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
        except Exception:
            pass
        painter.setFont(font)

        sel_a, sel_b = self._selected_range()
        if sel_b > sel_a:
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(80, 160, 255, 95))
            for idx, _ch, r in layout.get('char_rects') or []:
                if sel_a <= idx < sel_b:
                    painter.drawRoundedRect(QRectF(r).adjusted(0, 1, 0, -1), 2, 2)

        # 편집 중 미리보기는 가벼워야 한다. 최종 렌더의 획/이중획/그림자/그라디언트까지
        # 따라가면 입력할 때마다 QPainterPath와 stroke draw가 반복되어 렉이 생긴다.
        # 여기서는 사용자가 편집 위치를 판단하는 데 필요한 최소 스타일만 반영한다:
        # 글자 크기, 색상, 폰트, 행간, 자간, 너비, 높이.
        painter.setPen(QColor(getattr(self, '_inline_text_color', QColor('#000000'))))
        painter.setBrush(Qt.BrushStyle.NoBrush)
        for idx, ch, r in layout.get('char_rects') or []:
            if ch == '\n' or str(ch).isspace():
                continue
            self._draw_inline_preview_char(painter, str(ch), QRectF(r), font)

        # IME 조합 중인 문자열은 이제 layout 단계에서 실제 본문 사이에 임시 삽입된다.
        # 여기서 별도로 overlay로 다시 그리면 중간 삽입 때 뒤 글자를 밀지 못하고
        # 조합 초성이 다음 글자와 겹치거나 중복 표시된다.
        # 확정 전 preedit는 char_rects에 음수 index로만 들어가며 저장 데이터에는 반영되지 않는다.

        if bool(getattr(self, '_v_cursor_visible', True)):
            cr = self._vertical_cursor_rect()
            cursor_color = QColor(getattr(self, '_inline_text_color', QColor('#000000')))
            if self._color_luma(cursor_color) < 80:
                cursor_color = QColor(20, 120, 255)
            cursor_color.setAlpha(245)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(cursor_color)
            painter.drawRoundedRect(cr, 1.5, 1.5)
        painter.restore()

    def setFocus(self, reason=Qt.FocusReason.OtherFocusReason):
        try:
            super().setFocus(reason)
        except TypeError:
            try:
                super().setFocus()
            except Exception:
                pass
        except Exception:
            pass
        if not self._vertical_editor and self._edit is not None:
            try:
                self._edit.setFocus(reason)
            except TypeError:
                try:
                    self._edit.setFocus()
                except Exception:
                    pass
            except Exception:
                pass
        else:
            self._v_cursor_visible = True
            self.update()

    def focusInEvent(self, event):
        try:
            super().focusInEvent(event)
        except Exception:
            pass
        if self._vertical_editor:
            self._v_cursor_visible = True
            try:
                self.update(self._vertical_cursor_rect().adjusted(-8, -8, 8, 8))
            except Exception:
                self.update()

    def focusOutEvent(self, event):
        try:
            super().focusOutEvent(event)
        except Exception:
            pass
        if self._vertical_editor:
            try:
                self._inline_trace('INLINE_EDITOR_FOCUS_OUT')
            except Exception:
                pass
            self._handle_child_focus_out()


    def set_initial_caret_from_scene_pos(self, scene_pos):
        """Place the inline caret at the text position that was double-clicked.

        Opening the direct editor used to move the caret to the end of the text,
        even when the user double-clicked a specific word/letter.  Use the same
        visual hit-test logic as normal clicks after the editor has been sized and
        positioned, so centered/right-aligned horizontal text and vertical text both
        land where the user clicked.
        """
        try:
            self.adjust_to_contents()
        except Exception:
            pass
        if self._vertical_editor:
            try:
                local = self.mapFromScene(QPointF(scene_pos))
            except Exception:
                local = QPointF(0, 0)
            try:
                caret = self._vertical_index_from_pos(local)
            except Exception:
                caret = len(self.toPlainText())
            self._set_vertical_caret(caret, keep_anchor=False)
            try:
                self._inline_trace('INLINE_EDITOR_INITIAL_CARET_FROM_DOUBLE_CLICK', caret=int(getattr(self, '_v_caret_index', 0)), x=round(float(local.x()), 2), y=round(float(local.y()), 2))
            except Exception:
                pass
            return

        try:
            if self._edit is None:
                return
            try:
                local = self.mapFromScene(QPointF(scene_pos))
            except Exception:
                local = QPointF(0, 0)
            cursor = self._edit.cursorForPosition(QPoint(int(round(local.x())), int(round(local.y()))))
            cursor.clearSelection()
            self._edit.setTextCursor(cursor)
            try:
                self._inline_trace('INLINE_EDITOR_WIDGET_INITIAL_CARET_FROM_DOUBLE_CLICK', caret=int(cursor.position()), x=round(float(local.x()), 2), y=round(float(local.y()), 2))
            except Exception:
                pass
        except Exception:
            try:
                cursor = self.textCursor()
                cursor.movePosition(QTextCursor.MoveOperation.End)
                self.setTextCursor(cursor)
            except Exception:
                pass

    def mousePressEvent(self, event):
        if self._vertical_editor and event.button() == Qt.MouseButton.LeftButton:
            try:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            except Exception:
                pass
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            keep = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            try:
                local_pos = event.pos()
            except Exception:
                local_pos = QPointF(0, 0)
            # 클릭 위치 계산 직전 최신 레이아웃을 보장한다. 직전 입력/리사이즈가
            # 아직 queued adjust 상태이면 hit-test가 한 프레임 전 위치를 볼 수 있다.
            try:
                self.adjust_to_contents()
            except Exception:
                pass
            caret = self._vertical_index_from_pos(local_pos)
            self._set_vertical_caret(caret, keep_anchor=keep)
            try:
                self._inline_trace('INLINE_EDITOR_MOUSE_CARET_SET', caret=int(caret), x=round(float(local_pos.x()), 2), y=round(float(local_pos.y()), 2), keep=bool(keep))
            except Exception:
                pass
            try:
                self._v_mouse_press_pos = QPointF(local_pos)
                self._v_mouse_press_caret = int(caret)
            except Exception:
                self._v_mouse_press_pos = None
                self._v_mouse_press_caret = int(caret)
            # Only Shift-drag or a real drag beyond threshold creates selection.
            # Plain click/jitter must leave anchor == caret so the first typed glyph inserts.
            self._vertical_drag_selecting = bool(keep)
            event.accept()
            return
        try:
            super().mousePressEvent(event)
        except Exception:
            pass

    def hoverEnterEvent(self, event):
        if self._vertical_editor:
            try:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            except Exception:
                pass
            try:
                event.accept()
            except Exception:
                pass
            return
        try:
            super().hoverEnterEvent(event)
        except Exception:
            pass

    def hoverMoveEvent(self, event):
        if self._vertical_editor:
            try:
                self.setCursor(Qt.CursorShape.IBeamCursor)
            except Exception:
                pass
            try:
                event.accept()
            except Exception:
                pass
            return
        try:
            super().hoverMoveEvent(event)
        except Exception:
            pass

    def mouseMoveEvent(self, event):
        if self._vertical_editor and bool(event.buttons() & Qt.MouseButton.LeftButton):
            keep = bool(event.modifiers() & Qt.KeyboardModifier.ShiftModifier)
            if not keep and not bool(getattr(self, '_vertical_drag_selecting', False)):
                try:
                    press = QPointF(getattr(self, '_v_mouse_press_pos', event.pos()))
                    delta = QPointF(event.pos()) - press
                    threshold = 4
                    try:
                        threshold = QApplication.startDragDistance()
                    except Exception:
                        pass
                    if abs(float(delta.x())) + abs(float(delta.y())) < max(1, int(threshold)):
                        event.accept()
                        return
                except Exception:
                    event.accept()
                    return
                self._vertical_drag_selecting = True
            self._set_vertical_caret(self._vertical_index_from_pos(event.pos()), keep_anchor=True)
            event.accept()
            return
        try:
            super().mouseMoveEvent(event)
        except Exception:
            pass

    def mouseReleaseEvent(self, event):
        if self._vertical_editor:
            self._vertical_drag_selecting = False
            self._v_mouse_press_pos = None
            event.accept()
            return
        try:
            super().mouseReleaseEvent(event)
        except Exception:
            pass

    def keyPressEvent(self, event):
        if not self._vertical_editor:
            try:
                super().keyPressEvent(event)
            except Exception:
                pass
            return

        if self._is_alt_modifier_guard_event(event):
            event.accept()
            return
        try:
            key = event.key()
            mods = event.modifiers()
        except Exception:
            key = None
            mods = Qt.KeyboardModifier.NoModifier

        if key == Qt.Key.Key_Escape:
            self.main_window.finish_inline_text_edit(commit=False)
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and mods & Qt.KeyboardModifier.ControlModifier:
            try:
                self._inline_trace('INLINE_EDITOR_CTRL_ENTER_COMMIT_REQUEST')
            except Exception:
                pass
            self.main_window.finish_inline_text_edit(commit=True, commit_reason='ctrl_enter')
            event.accept()
            return
        # Text-entry shortcuts such as Ctrl+1..0 special symbols belong to the
        # inline editor, not to the toolbox/global shortcut layer.  Check them before
        # generic Ctrl handling so they are inserted instead of being swallowed.
        if self._handle_inline_text_input_shortcut(event):
            return
        if mods & Qt.KeyboardModifier.ControlModifier:
            if key == Qt.Key.Key_Z and (mods & Qt.KeyboardModifier.ShiftModifier):
                self.perform_inline_local_redo()
                event.accept()
                return
            if key == Qt.Key.Key_Z:
                self.perform_inline_local_undo()
                event.accept()
                return
            if key == Qt.Key.Key_Y:
                self.perform_inline_local_redo()
                event.accept()
                return
            if key == Qt.Key.Key_A:
                self._v_selection_anchor = 0
                self._v_caret_index = len(self.toPlainText())
                self.update()
                event.accept()
                return
            if key in (Qt.Key.Key_C, Qt.Key.Key_X):
                self._copy_direct_selection_to_plain_clipboard(cut=(key == Qt.Key.Key_X))
                event.accept()
                return
            if key == Qt.Key.Key_V:
                try:
                    clip = QApplication.clipboard().text()
                except Exception:
                    clip = ''
                if clip:
                    self._replace_vertical_selection(clip)
                event.accept()
                return
        keep = bool(mods & Qt.KeyboardModifier.ShiftModifier)

        # Ctrl+A/drag처럼 편집기 내부 글자가 선택된 상태에서 방향키를 누르면
        # 그 순간부터 '전체 선택/범위 선택'은 깨진 것으로 본다.
        # Shift 없이 방향키를 누른 경우에는 먼저 선택 강조를 접고 caret만 남겨,
        # 파란 선택 영역이 계속 남아 있는 상태를 막는다.
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right, Qt.Key.Key_Up, Qt.Key.Key_Down) and not keep:
            try:
                if self._has_vertical_selection():
                    a, b = self._selected_range()
                    collapse_to = a if key in (Qt.Key.Key_Left, Qt.Key.Key_Up) else b
                    self._set_vertical_caret(collapse_to, keep_anchor=False)
                    try:
                        self._inline_trace('INLINE_EDITOR_SELECTION_COLLAPSE_BY_ARROW',
                                           key=int(key), caret=int(collapse_to),
                                           selection_start=int(a), selection_end=int(b))
                    except Exception:
                        pass
                    event.accept()
                    return
            except Exception:
                pass

        if key == Qt.Key.Key_Backspace:
            self._delete_vertical_backward()
            event.accept()
            return
        if key == Qt.Key.Key_Delete:
            self._delete_vertical_forward()
            event.accept()
            return
        if key == Qt.Key.Key_Space and not (mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.AltModifier)):
            self._replace_vertical_selection(' ')
            event.accept()
            return
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._replace_vertical_selection('\n')
            event.accept()
            return
        if key == Qt.Key.Key_Up:
            if self._is_vertical_writing():
                self._set_vertical_caret(self._v_caret_index - 1, keep_anchor=keep)
            else:
                self._move_horizontal_line(up=True, keep_anchor=keep)
            event.accept()
            return
        if key == Qt.Key.Key_Down:
            if self._is_vertical_writing():
                self._set_vertical_caret(self._v_caret_index + 1, keep_anchor=keep)
            else:
                self._move_horizontal_line(up=False, keep_anchor=keep)
            event.accept()
            return
        if key == Qt.Key.Key_Home:
            text = self.toPlainText()
            prev_nl = text.rfind('\n', 0, self._v_caret_index)
            self._set_vertical_caret(prev_nl + 1, keep_anchor=keep)
            event.accept()
            return
        if key == Qt.Key.Key_End:
            text = self.toPlainText()
            next_nl = text.find('\n', self._v_caret_index)
            self._set_vertical_caret(len(text) if next_nl < 0 else next_nl, keep_anchor=keep)
            event.accept()
            return
        if key in (Qt.Key.Key_Left, Qt.Key.Key_Right):
            if self._is_vertical_writing():
                self._move_vertical_column(left=(key == Qt.Key.Key_Left), keep_anchor=keep)
            else:
                delta = -1 if key == Qt.Key.Key_Left else 1
                self._set_vertical_caret(self._v_caret_index + delta, keep_anchor=keep)
            event.accept()
            return

        text = event.text()
        if text and not (mods & Qt.KeyboardModifier.ControlModifier) and not (mods & Qt.KeyboardModifier.AltModifier):
            # Key_Unknown(0) is often an IME composition key.  If there is an active
            # preedit string, inputMethodEvent owns the text; inserting here can draw
            # one duplicate/overlapped glyph until the next caret move.
            try:
                if int(key or 0) == 0 and str(getattr(self, '_v_preedit_text', '') or ''):
                    event.accept()
                    return
            except Exception:
                pass
            self._replace_vertical_selection(text)
            event.accept()
            return
        try:
            super().keyPressEvent(event)
        except Exception:
            pass

    def _line_index_for_caret(self, lines, starts, pos):
        try:
            pos = int(pos)
        except Exception:
            pos = 0
        current_line = 0
        # A caret at the start of the next line is represented by the offset just
        # after the previous newline.  The old check treated that offset as part
        # of the previous line, so Up/Down from line starts skipped or inverted
        # visual rows.  Keep end-of-line on the previous row, but start-of-line
        # belongs to the current row.
        for i, start in enumerate(starts):
            try:
                line_len = len(lines[i])
            except Exception:
                line_len = 0
            start_i = int(start)
            end = start_i + int(line_len)
            if start_i <= pos <= end:
                current_line = i
                break
        return current_line

    def _horizontal_visual_rows(self):
        """Return horizontal direct-editor rows sorted by what the user sees.

        Text offsets are not enough for Up/Down movement: the offset immediately
        after a newline is the start of the next visual row, and center/right
        alignment shifts each row.  Build a visual row list from the layout
        coordinates so target row selection follows the screen, not raw offsets.
        """
        try:
            layout = self._layout_vertical_text()
        except Exception:
            return []
        if not (layout or {}).get('horizontal_direct'):
            return []
        rows = []
        for order, row in enumerate((layout or {}).get('columns') or []):
            try:
                line = str(row.get('line') or '')
                start = int(row.get('start') or 0)
                y0 = float(row.get('y0') or 0.0)
                pitch = max(1.0, float(row.get('pitch') or row.get('line_h') or 1.0))
                x0 = float(row.get('x') or 0.0)
                rows.append({
                    'visual_order': order,
                    'line': line,
                    'start': start,
                    'length': len(line),
                    'y': y0 + pitch / 2.0,
                    'x': x0,
                    'pitch': pitch,
                })
            except Exception:
                continue
        rows.sort(key=lambda r: (float(r.get('y', 0.0)), int(r.get('start', 0))))
        return rows

    def _nearest_visual_row_index_for_caret(self, rows, pos):
        if not rows:
            return 0
        try:
            pos = int(pos)
        except Exception:
            pos = 0
        try:
            p = self._inline_caret_point(pos)
            py = float(p.y())
            return min(range(len(rows)), key=lambda i: (abs(float(rows[i].get('y', 0.0)) - py), abs(int(rows[i].get('start', 0)) - pos)))
        except Exception:
            pass
        for i, row in enumerate(rows):
            start = int(row.get('start') or 0)
            end = start + int(row.get('length') or 0)
            if start <= pos <= end:
                return i
        return 0

    def _nearest_caret_in_line_by_axis(self, target_start, target_len, axis_value, axis='x'):
        layout = self._layout_vertical_text()
        caret_map = layout.get('caret_map') or {}
        candidates = []
        for off in range(0, int(target_len) + 1):
            idx = int(target_start) + off
            p = caret_map.get(idx)
            if p is None:
                continue
            try:
                v = float(p.x()) if axis == 'x' else float(p.y())
                candidates.append((abs(v - float(axis_value)), off, idx))
            except Exception:
                continue
        if candidates:
            candidates.sort(key=lambda item: (item[0], item[1]))
            return int(candidates[0][2])
        return int(target_start) + min(max(0, int(target_len)), int(target_len))

    def _move_horizontal_line(self, up=True, keep_anchor=False):
        """Move Up/Down by visual X instead of raw character offset.

        Center/right aligned lines do not share the same local start X.  Using the
        raw offset makes a caret visually jump to the wrong column.  Keep the
        desired X while moving vertically, like a normal text editor.  The target
        row itself is selected from visual Y order, so caret positions at the
        beginning of lines no longer get mistaken for the previous line.
        """
        text = self.toPlainText()
        lines, starts = self._split_vertical_lines(text)
        if not lines:
            return
        pos = int(getattr(self, '_v_caret_index', 0))
        try:
            desired_x = getattr(self, '_v_desired_caret_x', None)
            if desired_x is None:
                desired_x = float(self._inline_caret_point(pos).x())
                self._v_desired_caret_x = desired_x
        except Exception:
            desired_x = float(self._inline_caret_point(pos).x())

        rows = self._horizontal_visual_rows()
        if rows:
            current_row = self._nearest_visual_row_index_for_caret(rows, pos)
            target_row = current_row + (-1 if up else 1)
            if target_row < 0 or target_row >= len(rows):
                self._set_vertical_caret(pos, keep_anchor=keep_anchor, preserve_desired=True)
                return
            row = rows[target_row]
            target_start = int(row.get('start') or 0)
            target_len = int(row.get('length') or 0)
            target_pos = self._nearest_caret_in_line_by_axis(target_start, target_len, desired_x, axis='x')
            try:
                if bool(getattr(self, '_inline_caret_trace_enabled', False)):
                    self._inline_trace('INLINE_EDITOR_CARET_VERTICAL_MOVE',
                                       direction='up' if up else 'down',
                                       current_offset=pos,
                                       current_visual_row=current_row,
                                       target_visual_row=target_row,
                                       chosen_offset=target_pos,
                                       desired_x=round(float(desired_x), 2),
                                       row_count=len(rows))
            except Exception:
                pass
            self._set_vertical_caret(target_pos, keep_anchor=keep_anchor, preserve_desired=True)
            return

        current_line = self._line_index_for_caret(lines, starts, pos)
        target_line = current_line + (-1 if up else 1)
        if target_line < 0 or target_line >= len(lines):
            self._set_vertical_caret(pos, keep_anchor=keep_anchor, preserve_desired=True)
            return
        target_start = int(starts[target_line])
        target_len = len(lines[target_line])
        target_pos = self._nearest_caret_in_line_by_axis(target_start, target_len, desired_x, axis='x')
        self._set_vertical_caret(target_pos, keep_anchor=keep_anchor, preserve_desired=True)

    def _move_vertical_column(self, left=True, keep_anchor=False):
        """Move between vertical columns by visual Y instead of raw offset."""
        text = self.toPlainText()
        lines, starts = self._split_vertical_lines(text)
        if not lines:
            return
        pos = int(getattr(self, '_v_caret_index', 0))
        current_line = self._line_index_for_caret(lines, starts, pos)
        target_line = current_line + (1 if left else -1)
        if target_line < 0 or target_line >= len(lines):
            self._set_vertical_caret(pos, keep_anchor=keep_anchor, preserve_desired=True)
            return
        try:
            desired_y = getattr(self, '_v_desired_caret_y', None)
            if desired_y is None:
                desired_y = float(self._inline_caret_point(pos).y())
                self._v_desired_caret_y = desired_y
        except Exception:
            desired_y = float(self._inline_caret_point(pos).y())
        target_start = int(starts[target_line])
        target_len = len(lines[target_line])
        target_pos = self._nearest_caret_in_line_by_axis(target_start, target_len, desired_y, axis='y')
        self._set_vertical_caret(target_pos, keep_anchor=keep_anchor, preserve_desired=True)

    def inputMethodEvent(self, event):
        if not self._vertical_editor:
            try:
                super().inputMethodEvent(event)
            except Exception:
                pass
            return
        try:
            commit = event.commitString()
        except Exception:
            commit = ''
        try:
            preedit = event.preeditString()
        except Exception:
            preedit = ''
        preedit = str(preedit or '')
        commit = str(commit or '')

        # Ctrl+A / drag selection + Korean IME starts with a preedit-only frame.
        # Even a single 초성 must immediately replace the selected text on screen,
        # although it is not committed to the stored text yet.
        replaced_selection_for_preedit = False
        if preedit and not commit and self._has_vertical_selection():
            replaced_selection_for_preedit = self._delete_selection_for_ime_preedit()

        if commit:
            suppress_commit_undo = bool(getattr(self, '_v_ime_selection_preedit_active', False))
            self._replace_vertical_selection(commit,
                                             push_undo=not suppress_commit_undo,
                                             reason='ime-commit')
            self._v_ime_selection_preedit_active = False
        elif not preedit:
            self._v_ime_selection_preedit_active = False

        self._v_preedit_text = preedit
        self._sync_direct_editor_after_text_change(
            reason='ime-preedit-replace-selection' if replaced_selection_for_preedit else 'ime-preedit'
        )
        event.accept()

    def inputMethodQuery(self, query):
        if self._vertical_editor:
            if query == Qt.InputMethodQuery.ImCursorRectangle:
                return self._vertical_cursor_rect()
            if query == Qt.InputMethodQuery.ImSurroundingText:
                return self.toPlainText()
            if query == Qt.InputMethodQuery.ImCursorPosition:
                return int(getattr(self, '_v_caret_index', 0))
            if query == Qt.InputMethodQuery.ImAnchorPosition:
                return int(getattr(self, '_v_selection_anchor', getattr(self, '_v_caret_index', 0)))
            if query == Qt.InputMethodQuery.ImCurrentSelection:
                a, b = self._selected_range()
                return self.toPlainText()[a:b]
        try:
            return super().inputMethodQuery(query)
        except Exception:
            return None

    def toPlainText(self):
        if self._vertical_editor:
            return str(getattr(self, '_v_text', '') or '')
        try:
            return self._edit.toPlainText()
        except Exception:
            return ''

    def setPlainText(self, text):
        if self._vertical_editor:
            self._v_text = str(text or '')
            self._v_caret_index = min(int(getattr(self, '_v_caret_index', 0)), len(self._v_text))
            self._v_selection_anchor = self._v_caret_index
            try:
                self._v_document.setPlainText(self._v_text)
            except Exception:
                pass
            self._sync_direct_editor_after_text_change(reason='set-text')
            return
        try:
            self._edit.setPlainText(str(text or ''))
        except Exception:
            pass

    def textCursor(self):
        if self._vertical_editor:
            return _InlineCursorProxy(self)
        try:
            return self._edit.textCursor()
        except Exception:
            return QTextCursor()

    def setTextCursor(self, cursor):
        if self._vertical_editor:
            try:
                pos = cursor.position()
            except Exception:
                pos = getattr(self, '_v_caret_index', len(self.toPlainText()))
            try:
                anchor = cursor.anchor()
            except Exception:
                anchor = pos
            self._v_caret_index = max(0, min(len(self.toPlainText()), int(pos)))
            self._v_selection_anchor = max(0, min(len(self.toPlainText()), int(anchor)))
            self.invalidate_vertical_layout()
            self.update()
            return
        try:
            self._edit.setTextCursor(cursor)
        except Exception:
            pass

    def document(self):
        if self._vertical_editor:
            return getattr(self, '_v_document', None)
        try:
            return self._edit.document()
        except Exception:
            return None

    def _event_to_keysequence(self, event):
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return QKeySequence()
        try:
            mods_value = event.modifiers().value
        except AttributeError:
            mods_value = int(event.modifiers())
        return QKeySequence(mods_value | key)

    def _is_alt_modifier_guard_event(self, event):
        try:
            if event.key() != Qt.Key.Key_Alt:
                return False
            mods = event.modifiers()
            return bool(mods & (Qt.KeyboardModifier.ControlModifier | Qt.KeyboardModifier.ShiftModifier))
        except Exception:
            return False

    def _shortcut_matches(self, event, key_name):
        try:
            settings = getattr(self.main_window, 'shortcut_settings', None)
            if settings is None:
                return False
            seq = settings.seq(key_name)
            return key_event_matches_sequence(event, seq)
        except Exception:
            return False

    def _insert_inline_symbol(self, symbol):
        if self._vertical_editor:
            selected = ''
            a, b = self._selected_range()
            if b > a:
                selected = self.toPlainText()[a:b]
            pair_map = {
                "「」": ("「", "」"),
                "『』": ("『", "』"),
            }
            if symbol in pair_map:
                left, right = pair_map[symbol]
                if selected:
                    self._replace_vertical_selection(left + selected + right)
                else:
                    self._replace_vertical_selection(left + right)
                    self._set_vertical_caret(max(0, self._v_caret_index - 1), keep_anchor=False)
                return
            self._replace_vertical_selection(symbol)
            return
        cursor = self.textCursor()
        selected = cursor.selectedText()
        pair_map = {
            "「」": ("「", "」"),
            "『』": ("『", "』"),
        }
        if symbol in pair_map:
            left, right = pair_map[symbol]
            if selected:
                cursor.insertText(left + selected + right)
            else:
                cursor.insertText(left + right)
                cursor.movePosition(QTextCursor.MoveOperation.Left, QTextCursor.MoveMode.MoveAnchor, 1)
            self.setTextCursor(cursor)
            self._schedule_adjust_to_contents(reason='symbol')
            return
        cursor.insertText(symbol)
        self.setTextCursor(cursor)
        self._schedule_adjust_to_contents(reason='symbol')

    def _handle_inline_text_input_shortcut(self, event):
        for key, (_label, symbol) in TEXT_SYMBOLS.items():
            if self._shortcut_matches(event, "text_" + key):
                self._insert_inline_symbol(symbol)
                event.accept()
                return True
        return False

    def perform_inline_local_undo(self):
        if self._vertical_editor:
            try:
                stack = getattr(self, '_v_undo_stack', [])
                if not stack:
                    return True
                current = (self.toPlainText(), int(getattr(self, '_v_caret_index', 0)), int(getattr(self, '_v_selection_anchor', 0)))
                self._v_redo_stack.append(current)
                snap = stack.pop()
                self._restore_vertical_snapshot(snap)
            except Exception:
                pass
            return True
        try:
            self._edit.undo()
        except Exception:
            pass
        self._schedule_adjust_to_contents(reason='undo')
        return True

    def perform_inline_local_redo(self):
        if self._vertical_editor:
            try:
                stack = getattr(self, '_v_redo_stack', [])
                if not stack:
                    return True
                current = (self.toPlainText(), int(getattr(self, '_v_caret_index', 0)), int(getattr(self, '_v_selection_anchor', 0)))
                self._v_undo_stack.append(current)
                snap = stack.pop()
                self._restore_vertical_snapshot(snap)
            except Exception:
                pass
            return True
        try:
            self._edit.redo()
        except Exception:
            pass
        self._schedule_adjust_to_contents(reason='redo')
        return True

    def _handle_child_focus_out(self):
        if getattr(self.main_window, "_app_is_closing", False):
            return
        if getattr(self, '_closing', False):
            return
        try:
            view = getattr(self.main_window, 'view', None)
            if view is not None:
                vp = view.mapFromGlobal(QCursor.pos())
                sp = view.mapToScene(vp)
                edit_scene = self.mapToScene(self.boundingRect()).boundingRect().adjusted(-2, -2, 2, 2)
                if edit_scene.contains(sp):
                    QTimer.singleShot(0, lambda: self.setFocus(Qt.FocusReason.MouseFocusReason))
                    return
        except Exception:
            pass
        self.main_window.finish_inline_text_edit(commit=True, commit_reason='focus_out')


class TextTableWidget(QTableWidget):
    """텍스트 레이어 표.

    이 표의 드래그는 셀 텍스트 이동이 아니라 "행 전체 = 텍스트 레이어" 이동만 허용한다.
    Qt 기본 DragDrop/InternalMove는 셀 문자열을 MIME 데이터로 옮길 수 있어서,
    원문/번역문이 다른 행 안으로 들어가는 문제가 생긴다.

    그래서 이 위젯은 자체 마우스 처리로만 행 재배치를 수행한다.
    - 꾹 누르기/드래그 시작: 잡은 행 테두리 표시
    - 드래그 중: 행 위/아래 삽입선 표시
    - 드롭: 셀 데이터 삽입 금지, 행 순서만 변경
    """
    rowsReordered = pyqtSignal()

    ROW_MIME = "application/x-ysb-text-layer-row-move"

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._drag_start_pos = QPoint()
        self._pending_row_id_order = None
        self._pending_drop_row = None
        self._pending_source_rows = []

        self._row_drag_press_row = -1
        self._row_drag_hint_row = -1
        self._row_drag_active = False
        self._row_drag_insert_row = -1
        self._row_drag_source_rows = []
        self._row_drag_hint_timer = QTimer(self)
        self._row_drag_hint_timer.setSingleShot(True)
        self._row_drag_hint_timer.timeout.connect(self._show_row_drag_hint)
        try:
            self.setMouseTracking(True)
            self.viewport().setMouseTracking(True)
        except Exception:
            pass

    def _event_pos(self, event):
        try:
            return event.position().toPoint()
        except Exception:
            return event.pos()

    def _stop_row_drag_hint_timer(self):
        try:
            if self._row_drag_hint_timer.isActive():
                self._row_drag_hint_timer.stop()
        except Exception:
            pass

    def _show_row_drag_hint(self):
        row = int(getattr(self, '_row_drag_press_row', -1) or -1)
        if row <= 0 or row >= self.rowCount():
            return
        self._row_drag_hint_row = row
        try:
            self.viewport().setCursor(Qt.CursorShape.OpenHandCursor)
        except Exception:
            pass
        try:
            self.viewport().update()
        except Exception:
            pass

    def _clear_row_drag_visuals(self):
        self._stop_row_drag_hint_timer()
        self._row_drag_press_row = -1
        self._row_drag_hint_row = -1
        self._row_drag_active = False
        self._row_drag_insert_row = -1
        self._row_drag_source_rows = []
        try:
            self.viewport().unsetCursor()
        except Exception:
            pass
        try:
            self.viewport().update()
        except Exception:
            pass

    def _begin_row_drag(self):
        row = int(getattr(self, '_row_drag_press_row', -1) or -1)
        if row <= 0 or row >= self.rowCount():
            return False
        try:
            rows = self._selected_text_rows()
        except Exception:
            rows = []
        if row not in rows:
            rows = [row]
            try:
                self.selectRow(row)
            except Exception:
                pass
        rows = [r for r in sorted(set(rows)) if 0 < r < self.rowCount()]
        if not rows:
            return False
        self._stop_row_drag_hint_timer()
        self._row_drag_active = True
        self._row_drag_hint_row = row
        self._row_drag_source_rows = rows
        self._row_drag_insert_row = row
        try:
            self.viewport().setCursor(Qt.CursorShape.ClosedHandCursor)
        except Exception:
            pass
        try:
            self.viewport().update()
        except Exception:
            pass
        return True

    def _drop_insert_row_from_pos(self, pos):
        try:
            y = int(pos.y())
        except Exception:
            y = 0
        row = self.rowAt(y)
        if row < 0:
            try:
                first_y = self.rowViewportPosition(1) if self.rowCount() > 1 else 0
                if y < first_y:
                    return 1
            except Exception:
                pass
            return self.rowCount()
        if row <= 0:
            return 1
        try:
            top = self.rowViewportPosition(row)
            h = max(1, self.rowHeight(row))
            if y >= top + (h // 2):
                row += 1
        except Exception:
            pass
        return max(1, min(row, self.rowCount()))

    def _move_row_order_from_drop(self, source_rows, insert_row):
        row_ids = self._row_ids()
        indexed = [(row + 1, rid) for row, rid in enumerate(row_ids)]
        moving = [rid for row, rid in indexed if row in source_rows]
        remaining = [rid for row, rid in indexed if row not in source_rows]
        removed_before_target = sum(1 for row in source_rows if row < insert_row)
        insert_pos = max(0, min((insert_row - 1) - removed_before_target, len(remaining)))
        return remaining[:insert_pos] + moving + remaining[insert_pos:]

    def mousePressEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton:
                pos = self._event_pos(event)
                row = self.rowAt(pos.y())
                self._drag_start_pos = QPoint(pos)
                self._row_drag_press_row = row if row > 0 else -1
                self._row_drag_hint_row = -1
                self._row_drag_active = False
                self._row_drag_insert_row = -1
                self._row_drag_source_rows = []
                if self._row_drag_press_row > 0:
                    self._stop_row_drag_hint_timer()
                    self._row_drag_hint_timer.start(260)
        except Exception:
            pass
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        try:
            if event.buttons() & Qt.MouseButton.LeftButton and int(getattr(self, '_row_drag_press_row', -1) or -1) > 0:
                pos = self._event_pos(event)
                distance = (pos - self._drag_start_pos).manhattanLength()
                threshold = max(3, QApplication.startDragDistance())
                if not self._row_drag_active and distance >= threshold:
                    self._begin_row_drag()
                if self._row_drag_active:
                    insert_row = self._drop_insert_row_from_pos(pos)
                    if insert_row != self._row_drag_insert_row:
                        self._row_drag_insert_row = insert_row
                        try:
                            self.viewport().update()
                        except Exception:
                            pass
                    try:
                        event.accept()
                    except Exception:
                        pass
                    return
                # 드래그 후보 상태에서는 셀 텍스트 드래그/선택을 만들지 않는다.
                try:
                    event.accept()
                except Exception:
                    pass
                return
        except Exception:
            pass
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event):
        try:
            if event.button() == Qt.MouseButton.LeftButton and self._row_drag_active:
                source_rows = [r for r in getattr(self, '_row_drag_source_rows', []) if 0 < r < self.rowCount()]
                try:
                    pos = self._event_pos(event)
                    insert_row = self._drop_insert_row_from_pos(pos)
                except Exception:
                    insert_row = int(getattr(self, '_row_drag_insert_row', -1) or -1)
                changed = False
                if source_rows and insert_row >= 1:
                    if not (insert_row in source_rows or insert_row == max(source_rows) + 1):
                        old_order = self._row_ids()
                        new_order = self._move_row_order_from_drop(source_rows, insert_row)
                        if new_order != old_order:
                            self._pending_row_id_order = new_order
                            self._pending_drop_row = insert_row
                            self._pending_source_rows = source_rows
                            changed = True
                self._clear_row_drag_visuals()
                try:
                    event.accept()
                except Exception:
                    pass
                if changed:
                    self.rowsReordered.emit()
                return
        except Exception:
            pass
        self._clear_row_drag_visuals()
        super().mouseReleaseEvent(event)

    def leaveEvent(self, event):
        if not getattr(self, '_row_drag_active', False):
            self._stop_row_drag_hint_timer()
            if int(getattr(self, '_row_drag_hint_row', -1) or -1) >= 0:
                self._row_drag_hint_row = -1
                try:
                    self.viewport().unsetCursor()
                    self.viewport().update()
                except Exception:
                    pass
        super().leaveEvent(event)

    def paintEvent(self, event):
        super().paintEvent(event)
        try:
            painter = QPainter(self.viewport())
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            vw = self.viewport().width()

            hint_row = int(getattr(self, '_row_drag_hint_row', -1) or -1)
            if hint_row > 0 and hint_row < self.rowCount():
                y = self.rowViewportPosition(hint_row)
                h = self.rowHeight(hint_row)
                if h > 0:
                    rect = QRect(1, y + 1, max(1, vw - 3), max(1, h - 3))
                    pen = QPen(QColor('#E0A0AA'))
                    pen.setWidth(2)
                    painter.setPen(pen)
                    painter.setBrush(Qt.BrushStyle.NoBrush)
                    painter.drawRect(rect)
                    # 왼쪽 잡기 표시 막대. 텍스트가 아니라 "행 이동 가능" 시각 표시만 준다.
                    painter.fillRect(QRect(1, y + 2, 4, max(1, h - 4)), QColor('#E0A0AA'))

            if bool(getattr(self, '_row_drag_active', False)):
                insert_row = int(getattr(self, '_row_drag_insert_row', -1) or -1)
                if insert_row >= 1:
                    if insert_row >= self.rowCount():
                        last = max(1, self.rowCount() - 1)
                        y = self.rowViewportPosition(last) + self.rowHeight(last)
                    else:
                        y = self.rowViewportPosition(insert_row)
                    y = max(0, min(y, self.viewport().height() - 1))
                    pen = QPen(QColor('#FFD36A'))
                    pen.setWidth(3)
                    painter.setPen(pen)
                    painter.drawLine(0, y, vw, y)
                    painter.setBrush(QColor('#FFD36A'))
                    painter.setPen(Qt.PenStyle.NoPen)
                    painter.drawPolygon(QPolygon([QPoint(0, y - 5), QPoint(9, y), QPoint(0, y + 5)]))
                    painter.drawPolygon(QPolygon([QPoint(vw - 1, y - 5), QPoint(max(0, vw - 10), y), QPoint(vw - 1, y + 5)]))
            painter.end()
        except Exception:
            try:
                painter.end()
            except Exception:
                pass

    def mimeData(self, indexes):
        mime = QMimeData()
        rows = sorted({idx.row() for idx in indexes if idx.isValid() and idx.row() > 0})
        try:
            mime.setData(self.ROW_MIME, (",".join(str(r) for r in rows)).encode("utf-8"))
        except Exception:
            pass
        # 의도적으로 text/html/plain 데이터를 넣지 않는다.
        # 그래야 원문/번역문 셀 안으로 드래그 텍스트가 붙지 않는다.
        return mime

    def supportedDropActions(self):
        return Qt.DropAction.MoveAction

    def dragEnterEvent(self, event):
        # 기본 Qt 드롭은 쓰지 않는다. 텍스트 셀 드롭을 막기 위한 안전장치다.
        event.ignore()

    def dragMoveEvent(self, event):
        # 기본 Qt 드롭은 쓰지 않는다. 행 이동은 mouseMove/mouseRelease에서 직접 처리한다.
        event.ignore()

    def _drop_insert_row_from_event(self, event):
        return self._drop_insert_row_from_pos(self._event_pos(event))

    def _selected_text_rows(self):
        try:
            rows = sorted({idx.row() for idx in self.selectedIndexes() if idx.row() > 0})
        except Exception:
            rows = []
        try:
            cur = self.currentRow()
            if cur > 0 and cur not in rows:
                rows.append(cur)
                rows.sort()
        except Exception:
            pass
        return rows

    def _row_ids(self):
        ids = []
        for row in range(1, self.rowCount()):
            item = self.item(row, 0)
            if item is None:
                ids.append("")
            else:
                ids.append(str(item.text() or "").strip())
        return ids

    def dropEvent(self, event):
        # 외부/기본 드롭 경로는 모두 차단한다.
        # 행 재배치는 mouseReleaseEvent에서만 실행된다.
        event.ignore()


def ysb_focus_color_dialog_hex_field(dialog):
    """색상 선택 창을 열면 HEX 입력칸을 우선 포커싱하고 전체 선택한다."""
    try:
        edits = list(dialog.findChildren(QLineEdit))
    except Exception:
        edits = []
    if not edits:
        return
    target = None
    # Qt 비네이티브 QColorDialog의 HTML/HEX 입력칸은 보통 #RRGGBB 또는 6자리 HEX 값을 가진다.
    for edit in edits:
        try:
            text = str(edit.text() or '').strip()
        except Exception:
            text = ''
        if re.fullmatch(r'#?[0-9A-Fa-f]{6,8}', text):
            target = edit
            break
    if target is None:
        # 마지막 QLineEdit이 HTML/HEX 입력칸인 경우가 많다.
        target = edits[-1]
    try:
        target.setFocus(Qt.FocusReason.OtherFocusReason)
        target.selectAll()
    except Exception:
        pass


def ysb_get_color_with_hex_focus(current, parent=None, title="색상 선택"):
    """QColorDialog.getColor 대신 쓰는 헬퍼.

    네이티브 색상창은 내부 HEX 칸에 접근하기 어려우므로 비네이티브 창을 사용하고,
    창이 뜨자마자 색상 코드 입력칸에 포커스/전체선택을 준다.
    """
    try:
        cur = current if isinstance(current, QColor) else QColor(str(current or '#000000'))
    except Exception:
        cur = QColor('#000000')
    dlg = QColorDialog(cur, parent)
    try:
        dlg.setWindowTitle(str(title or "색상 선택"))
    except Exception:
        pass
    try:
        dlg.setOption(QColorDialog.ColorDialogOption.DontUseNativeDialog, True)
        dlg.setOption(QColorDialog.ColorDialogOption.ShowAlphaChannel, False)
    except Exception:
        pass
    try:
        if parent is not None and hasattr(parent, 'settings_dialog_style'):
            dlg.setStyleSheet(parent.settings_dialog_style())
    except Exception:
        pass
    try:
        QTimer.singleShot(0, lambda d=dlg: ysb_focus_color_dialog_hex_field(d))
        QTimer.singleShot(80, lambda d=dlg: ysb_focus_color_dialog_hex_field(d))
    except Exception:
        pass
    if dlg.exec() == QDialog.DialogCode.Accepted:
        color = dlg.selectedColor()
        if color.isValid():
            return color
    return QColor()


class TextAdvancedEffectDialog(QDialog):
    """고급 텍스트/획 옵션 설정 창."""

    previewChanged = pyqtSignal(dict)

    def __init__(self, data_item=None, parent=None):
        super().__init__(parent)
        self.data_item = data_item or {}
        self._ui_language = getattr(parent, "ui_language", LANG_KO) if parent is not None else LANG_KO
        self.setWindowTitle(translate_ui_text("고급 텍스트/획 옵션", self._ui_language))
        self.resize(620, 660)
        self.setMinimumSize(520, 500)
        try:
            if parent is not None and hasattr(parent, "settings_dialog_style"):
                self.setStyleSheet(parent.settings_dialog_style())
        except Exception:
            pass

        self._color_buttons = {}
        self._preview_timer = QTimer(self)
        self._preview_timer.setSingleShot(True)
        self._preview_timer.timeout.connect(self._emit_preview_changed)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(14, 14, 14, 14)
        layout.setSpacing(10)

        info = QLabel(translate_ui_text("선택한 텍스트 라인에 문자/획 그라데이션과 2중 획을 적용합니다. 평행사변형/사다리꼴/부채꼴 변형은 우클릭 메뉴에서 직접 조정합니다.", self._ui_language))
        info.setWordWrap(True)
        layout.addWidget(info)

        tabs = QTabWidget(self)
        tabs.setDocumentMode(True)

        text_tab = self._make_effect_tab([
            self._make_gradient_group(
                key="text",
                title=translate_ui_text("문자 그라데이션", self._ui_language),
                default1=str(self.data_item.get("text_gradient_color1") or self.data_item.get("text_color") or "#000000"),
                default2=str(self.data_item.get("text_gradient_color2") or "#FFFFFF"),
                enabled=bool(self.data_item.get("text_gradient_enabled", False)),
                angle=int(self.data_item.get("text_gradient_angle", 0) or 0),
                ratio=int(self.data_item.get("text_gradient_ratio", 50) or 50),
            ),
        ])
        stroke_tab = self._make_effect_tab([
            self._make_gradient_group(
                key="stroke",
                title=translate_ui_text("획 그라데이션", self._ui_language),
                default1=str(self.data_item.get("stroke_gradient_color1") or self.data_item.get("stroke_color") or "#FFFFFF"),
                default2=str(self.data_item.get("stroke_gradient_color2") or "#000000"),
                enabled=bool(self.data_item.get("stroke_gradient_enabled", False)),
                angle=int(self.data_item.get("stroke_gradient_angle", 0) or 0),
                ratio=int(self.data_item.get("stroke_gradient_ratio", 50) or 50),
            ),
            self._make_double_stroke_group(),
        ])
        effect_tab = self._make_effect_tab([
            self._make_shadow_group(),
            self._make_glow_group(),
        ])

        tabs.addTab(text_tab, translate_ui_text("텍스트", self._ui_language))
        tabs.addTab(stroke_tab, translate_ui_text("획", self._ui_language))
        tabs.addTab(effect_tab, translate_ui_text("효과", self._ui_language))
        layout.addWidget(tabs, 1)

        buttons = QDialogButtonBox()
        buttons.addButton(translate_ui_text("적용", self._ui_language), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(translate_ui_text("닫기", self._ui_language), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _make_effect_tab(self, widgets):
        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        try:
            scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        except Exception:
            pass
        content = QWidget(scroll)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(0, 0, 6, 0)
        content_layout.setSpacing(10)
        for widget in widgets:
            content_layout.addWidget(widget)
        content_layout.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def _make_color_button(self, key, color):
        btn = QPushButton(str(color or "#000000"))
        btn.setMinimumWidth(92)
        self._set_color_button(btn, color)
        btn.clicked.connect(lambda _=False, b=btn: self._pick_color(b))
        self._color_buttons[key] = btn
        return btn

    def _set_color_button(self, btn, color):
        c = QColor(str(color or "#000000"))
        if not c.isValid():
            c = QColor("#000000")
        text = c.name(QColor.NameFormat.HexRgb).upper()
        btn.setText(text)
        btn.setProperty("color_value", text)
        btn.setStyleSheet(f"QPushButton {{ background:{text}; color:{'#000000' if c.lightness() > 150 else '#ffffff'}; border:1px solid #777; padding:4px 8px; }}")

    def _pick_color(self, btn):
        cur = QColor(str(btn.property("color_value") or "#000000"))
        color = ysb_get_color_with_hex_focus(cur, self, translate_ui_text("색상 선택", self._ui_language))
        if not color.isValid():
            return
        self._set_color_button(btn, color.name(QColor.NameFormat.HexRgb).upper())
        self._queue_preview_changed()

    def _queue_preview_changed(self, *_args):
        try:
            self._preview_timer.start(90)
        except Exception:
            try:
                self._emit_preview_changed()
            except Exception:
                pass

    def _emit_preview_changed(self):
        try:
            self.previewChanged.emit(self.values())
        except Exception:
            pass

    def _make_gradient_group(self, key, title, default1, default2, enabled=False, angle=0, ratio=50):
        group = QGroupBox(title)
        form = QFormLayout(group)
        chk = QCheckBox(translate_ui_text("사용", self._ui_language))
        chk.setChecked(bool(enabled))
        setattr(self, f"{key}_gradient_enabled", chk)

        color_line = QHBoxLayout()
        color1 = self._make_color_button(f"{key}_gradient_color1", default1)
        color2 = self._make_color_button(f"{key}_gradient_color2", default2)
        color_line.addWidget(QLabel(translate_ui_text("색 1", self._ui_language)))
        color_line.addWidget(color1)
        color_line.addSpacing(8)
        color_line.addWidget(QLabel(translate_ui_text("색 2", self._ui_language)))
        color_line.addWidget(color2)
        color_line.addStretch()

        angle_spin = QSpinBox()
        angle_spin.setRange(-360, 360)
        angle_spin.setSuffix("°")
        angle_spin.setValue(int(angle or 0))
        setattr(self, f"{key}_gradient_angle", angle_spin)

        ratio_spin = QSpinBox()
        ratio_spin.setRange(1, 99)
        ratio_spin.setSuffix(" %")
        ratio_spin.setValue(max(1, min(99, int(ratio or 50))))
        setattr(self, f"{key}_gradient_ratio", ratio_spin)

        form.addRow(chk)
        form.addRow(translate_ui_text("색상", self._ui_language), color_line)
        form.addRow(translate_ui_text("각도", self._ui_language), angle_spin)
        form.addRow(translate_ui_text("비율", self._ui_language), ratio_spin)

        for _w in (chk, angle_spin, ratio_spin):
            try:
                if hasattr(_w, "stateChanged"):
                    _w.stateChanged.connect(self._queue_preview_changed)
                elif hasattr(_w, "valueChanged"):
                    _w.valueChanged.connect(self._queue_preview_changed)
            except Exception:
                pass
        return group

    def _make_double_stroke_group(self):
        group = QGroupBox(translate_ui_text("2중 획", self._ui_language))
        form = QFormLayout(group)
        chk = QCheckBox(translate_ui_text("사용", self._ui_language))
        chk.setChecked(bool(self.data_item.get("double_stroke_enabled", False)))
        self.double_stroke_enabled = chk

        color = self._make_color_button("double_stroke_color", str(self.data_item.get("double_stroke_color") or "#000000"))
        width_spin = QSpinBox()
        width_spin.setRange(0, 80)
        width_spin.setSuffix(" px")
        try:
            width_spin.setValue(max(0, min(80, int(self.data_item.get("double_stroke_width", 0) or 0))))
        except Exception:
            width_spin.setValue(0)
        self.double_stroke_width = width_spin

        form.addRow(chk)
        form.addRow(translate_ui_text("색상", self._ui_language), color)
        form.addRow(translate_ui_text("두께", self._ui_language), width_spin)

        for _w in (chk, width_spin):
            try:
                if hasattr(_w, "stateChanged"):
                    _w.stateChanged.connect(self._queue_preview_changed)
                elif hasattr(_w, "valueChanged"):
                    _w.valueChanged.connect(self._queue_preview_changed)
            except Exception:
                pass
        return group

    def _make_shadow_group(self):
        group = QGroupBox(translate_ui_text("문자 그림자", self._ui_language))
        form = QFormLayout(group)
        chk = QCheckBox(translate_ui_text("사용", self._ui_language))
        chk.setChecked(bool(self.data_item.get("text_shadow_enabled", False)))
        self.text_shadow_enabled = chk

        color = self._make_color_button("text_shadow_color", str(self.data_item.get("text_shadow_color") or "#000000"))

        opacity_spin = QSpinBox()
        opacity_spin.setRange(0, 100)
        opacity_spin.setSuffix(" %")
        opacity_spin.setValue(max(0, min(100, int(self.data_item.get("text_shadow_opacity", 45) or 45))))
        self.text_shadow_opacity = opacity_spin

        offset_x_spin = QSpinBox()
        offset_x_spin.setRange(-300, 300)
        offset_x_spin.setSuffix(" px")
        offset_x_spin.setValue(int(self.data_item.get("text_shadow_offset_x", 3) or 3))
        self.text_shadow_offset_x = offset_x_spin

        offset_y_spin = QSpinBox()
        offset_y_spin.setRange(-300, 300)
        offset_y_spin.setSuffix(" px")
        offset_y_spin.setValue(int(self.data_item.get("text_shadow_offset_y", 3) or 3))
        self.text_shadow_offset_y = offset_y_spin

        blur_spin = QSpinBox()
        blur_spin.setRange(0, 200)
        blur_spin.setSuffix(" px")
        blur_spin.setValue(max(0, min(200, int(self.data_item.get("text_shadow_blur", 4) or 4))))
        self.text_shadow_blur = blur_spin

        form.addRow(chk)
        form.addRow(translate_ui_text("색상", self._ui_language), color)
        form.addRow(translate_ui_text("불투명도", self._ui_language), opacity_spin)
        form.addRow(translate_ui_text("X 이동", self._ui_language), offset_x_spin)
        form.addRow(translate_ui_text("Y 이동", self._ui_language), offset_y_spin)
        form.addRow(translate_ui_text("흐림", self._ui_language), blur_spin)

        for _w in (chk, opacity_spin, offset_x_spin, offset_y_spin, blur_spin):
            try:
                if hasattr(_w, "stateChanged"):
                    _w.stateChanged.connect(self._queue_preview_changed)
                elif hasattr(_w, "valueChanged"):
                    _w.valueChanged.connect(self._queue_preview_changed)
            except Exception:
                pass
        return group

    def _make_glow_group(self):
        group = QGroupBox(translate_ui_text("문자 후광", self._ui_language))
        form = QFormLayout(group)
        chk = QCheckBox(translate_ui_text("사용", self._ui_language))
        chk.setChecked(bool(self.data_item.get("text_glow_enabled", False)))
        self.text_glow_enabled = chk

        color = self._make_color_button("text_glow_color", str(self.data_item.get("text_glow_color") or "#FFFFFF"))

        opacity_spin = QSpinBox()
        opacity_spin.setRange(0, 100)
        opacity_spin.setSuffix(" %")
        opacity_spin.setValue(max(0, min(100, int(self.data_item.get("text_glow_opacity", 35) or 35))))
        self.text_glow_opacity = opacity_spin

        offset_x_spin = QSpinBox()
        offset_x_spin.setRange(-300, 300)
        offset_x_spin.setSuffix(" px")
        offset_x_spin.setValue(int(self.data_item.get("text_glow_offset_x", 0) or 0))
        self.text_glow_offset_x = offset_x_spin

        offset_y_spin = QSpinBox()
        offset_y_spin.setRange(-300, 300)
        offset_y_spin.setSuffix(" px")
        offset_y_spin.setValue(int(self.data_item.get("text_glow_offset_y", 0) or 0))
        self.text_glow_offset_y = offset_y_spin

        size_spin = QSpinBox()
        size_spin.setRange(0, 200)
        size_spin.setSuffix(" px")
        size_spin.setValue(max(0, min(200, int(self.data_item.get("text_glow_size", 3) or 3))))
        self.text_glow_size = size_spin

        blur_spin = QSpinBox()
        blur_spin.setRange(0, 200)
        blur_spin.setSuffix(" px")
        blur_spin.setValue(max(0, min(200, int(self.data_item.get("text_glow_blur", 8) or 8))))
        self.text_glow_blur = blur_spin

        form.addRow(chk)
        form.addRow(translate_ui_text("색상", self._ui_language), color)
        form.addRow(translate_ui_text("불투명도", self._ui_language), opacity_spin)
        form.addRow(translate_ui_text("X 이동", self._ui_language), offset_x_spin)
        form.addRow(translate_ui_text("Y 이동", self._ui_language), offset_y_spin)
        form.addRow(translate_ui_text("크기", self._ui_language), size_spin)
        form.addRow(translate_ui_text("흐림", self._ui_language), blur_spin)

        for _w in (chk, opacity_spin, offset_x_spin, offset_y_spin, size_spin, blur_spin):
            try:
                if hasattr(_w, "stateChanged"):
                    _w.stateChanged.connect(self._queue_preview_changed)
                elif hasattr(_w, "valueChanged"):
                    _w.valueChanged.connect(self._queue_preview_changed)
            except Exception:
                pass
        return group

    def values(self):
        out = {}
        for key in ("text", "stroke"):
            out[f"{key}_gradient_enabled"] = bool(getattr(self, f"{key}_gradient_enabled").isChecked())
            out[f"{key}_gradient_color1"] = str(self._color_buttons[f"{key}_gradient_color1"].property("color_value") or "#000000")
            out[f"{key}_gradient_color2"] = str(self._color_buttons[f"{key}_gradient_color2"].property("color_value") or "#FFFFFF")
            out[f"{key}_gradient_angle"] = int(getattr(self, f"{key}_gradient_angle").value())
            out[f"{key}_gradient_ratio"] = int(getattr(self, f"{key}_gradient_ratio").value())
        out["double_stroke_enabled"] = bool(getattr(self, "double_stroke_enabled").isChecked())
        out["double_stroke_color"] = str(self._color_buttons["double_stroke_color"].property("color_value") or "#000000")
        out["double_stroke_width"] = int(getattr(self, "double_stroke_width").value())
        out["text_shadow_enabled"] = bool(getattr(self, "text_shadow_enabled").isChecked())
        out["text_shadow_color"] = str(self._color_buttons["text_shadow_color"].property("color_value") or "#000000")
        out["text_shadow_opacity"] = int(getattr(self, "text_shadow_opacity").value())
        out["text_shadow_offset_x"] = int(getattr(self, "text_shadow_offset_x").value())
        out["text_shadow_offset_y"] = int(getattr(self, "text_shadow_offset_y").value())
        out["text_shadow_blur"] = int(getattr(self, "text_shadow_blur").value())
        out["text_glow_enabled"] = bool(getattr(self, "text_glow_enabled").isChecked())
        out["text_glow_color"] = str(self._color_buttons["text_glow_color"].property("color_value") or "#FFFFFF")
        out["text_glow_opacity"] = int(getattr(self, "text_glow_opacity").value())
        out["text_glow_offset_x"] = int(getattr(self, "text_glow_offset_x").value())
        out["text_glow_offset_y"] = int(getattr(self, "text_glow_offset_y").value())
        out["text_glow_size"] = int(getattr(self, "text_glow_size").value())
        out["text_glow_blur"] = int(getattr(self, "text_glow_blur").value())
        return out


class TranslationPromptDialog(QDialog):
    """AI 번역 프롬프트 입력/수정 창."""

    def __init__(self, prompt_text="", parent=None):
        super().__init__(parent)
        self._ui_language = getattr(parent, "ui_language", LANG_KO) if parent is not None else LANG_KO
        self.setWindowTitle(translate_ui_text("번역 프롬프트 입력", self._ui_language))
        self.resize(760, 520)
        try:
            if parent is not None and hasattr(parent, "settings_dialog_style"):
                self.setStyleSheet(parent.settings_dialog_style())
        except Exception:
            pass

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        if self._ui_language == LANG_EN:
            prompt_help_text = (
                "Enter the prompt to send together with the AI translation API.\n"
                "OK saves it to the options cache. Cancel closes without saving."
            )
        else:
            prompt_help_text = (
                "AI 번역 API에 함께 전달할 프롬프트를 입력합니다.\n"
                "확인을 누르면 옵션 캐시에 저장되고, 닫기를 누르면 저장하지 않고 나갑니다."
            )
        title = QLabel(translate_ui_text("번역 프롬프트 입력", self._ui_language))
        title.setObjectName("SettingsDialogTitle")
        layout.addWidget(title)

        info = QLabel(prompt_help_text)
        info.setObjectName("SettingsDescription")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(str(prompt_text or ""))
        self.text_edit.setPlaceholderText(translate_ui_text("예: 일본어를 한국어로 자연스럽게 번역해줘. 캐릭터 말투와 줄바꿈을 유지해줘.", self._ui_language))
        layout.addWidget(self.text_edit, 1)

        buttons = QDialogButtonBox()
        buttons.addButton(translate_ui_text("확인", self._ui_language), QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton(translate_ui_text("닫기", self._ui_language), QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_prompt_text(self):
        return self.text_edit.toPlainText()


class GlossaryDialog(QDialog):
    """번역 참고용 TXT 단어장 캐시 관리 창."""

    def __init__(self, glossary_text="", glossary_path="", parent=None):
        super().__init__(parent)
        self._ui_language = normalize_ui_language(getattr(parent, "ui_language", current_ui_language()))
        self.setWindowTitle(translate_ui_text("단어장", self._ui_language))
        self.resize(760, 520)
        try:
            if parent is not None and hasattr(parent, "settings_dialog_style"):
                self.setStyleSheet(parent.settings_dialog_style())
        except Exception:
            pass

        self.glossary_text = str(glossary_text or "")
        self.glossary_path = str(glossary_path or "")
        self.changed = False

        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        title = QLabel(self.tr_ui("단어장"))
        title.setObjectName("SettingsDialogTitle")
        layout.addWidget(title)

        info = QLabel(self.tr_msg(
            "번역 참고 자료로 사용할 TXT 파일을 캐시에 저장합니다.\n"
            "배경 설명, 단어 해설, 1대1 대체 규칙 등을 넣어둘 수 있습니다."
        ))
        info.setObjectName("SettingsDescription")
        info.setWordWrap(True)
        layout.addWidget(info)

        self.status_label = QLabel()
        self.status_label.setObjectName("SettingsDescription")
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText(self.tr_ui("아직 불러온 단어장이 없습니다."))
        layout.addWidget(self.preview, 1)

        top_buttons = QHBoxLayout()
        self.btn_load = QPushButton(self.tr_ui("불러오기"))
        self.btn_refresh = QPushButton(self.tr_ui("갱신"))
        self.btn_reset = QPushButton(self.tr_ui("초기화"))
        top_buttons.addWidget(self.btn_load)
        top_buttons.addWidget(self.btn_refresh)
        top_buttons.addWidget(self.btn_reset)
        top_buttons.addStretch()
        layout.addLayout(top_buttons)

        bottom_buttons = QDialogButtonBox()
        bottom_buttons.addButton(self.tr_ui("닫기"), QDialogButtonBox.ButtonRole.RejectRole)
        bottom_buttons.rejected.connect(self.reject)
        layout.addWidget(bottom_buttons)

        self.btn_load.clicked.connect(self.load_glossary_file)
        self.btn_refresh.clicked.connect(self.refresh_glossary_file)
        self.btn_reset.clicked.connect(self.reset_glossary)

        self.refresh_preview()

    def tr_ui(self, text):
        return translate_ui_text(text, self._ui_language)

    def font_refresh_text(self, text):
        """글꼴 갱신 버튼/알림용 간단한 KO/EN 문구."""
        lang = str(getattr(self, "_ui_language", "ko") or "ko").lower()
        if not lang.startswith("en"):
            return translate_ui_text(text, self._ui_language)

        en = {
            "폰트 갱신": "Refresh Fonts",
            "Windows에 설치되어 있지만 목록에 보이지 않는 글꼴을 다시 찾습니다.": "Search again for fonts installed in Windows but missing from the list.",
            "폰트 갱신 확인": "Refresh Fonts",
            "Windows 글꼴 폴더와 사용자 글꼴 폴더를 다시 검색합니다.\n\n일부 글꼴은 Qt 기본 목록에 바로 보이지 않을 수 있어, 이 작업은 누락된 글꼴을 추가로 등록합니다.\n\n글꼴이 많으면 잠시 걸릴 수 있습니다. 계속할까요?": "This will scan the Windows Fonts folder and your user Fonts folder again.\n\nSome fonts may not appear in Qt's default list, so this registers missing fonts as application fonts.\n\nIt may take a moment if you have many fonts. Continue?",
            "폰트 갱신 완료": "Font refresh complete",
            "폰트 목록을 갱신했습니다.\n새로 추가된 글꼴 패밀리: {count}개": "The font list has been refreshed.\nNew font families added: {count}",
            "폰트 갱신 실패": "Font refresh failed",
            "폰트 갱신 중 오류가 발생했습니다.": "An error occurred while refreshing fonts.",
        }
        return en.get(text, translate_ui_text(text, self._ui_language))

    def tr_msg(self, text):
        return translate_ui_dynamic_text(text, self._ui_language)

    def refresh_preview(self):
        text = self.glossary_text or ""
        path = self.glossary_path or ""
        if text:
            path_text = path if path else self.tr_ui("캐시에만 저장됨")
            current_vocab_label = self.tr_ui("현재 단어장")
            char_count_label = self.tr_ui("글자 수")
            self.status_label.setText(f"{current_vocab_label}: {path_text}\n{char_count_label}: {len(text):,}")
            self.preview.setPlainText(text)
        else:
            current_vocab_label = self.tr_ui("현재 단어장")
            none_label = self.tr_ui("없음")
            self.status_label.setText(f"{current_vocab_label}: {none_label}")
            self.preview.clear()

    def load_glossary_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr_ui("단어장 TXT 불러오기"),
            self.glossary_path or "",
            "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        try:
            text = read_text_file_for_cache(path)
        except Exception as e:
            msg_text = self.tr_ui("TXT 파일을 읽지 못했습니다:")
            QMessageBox.critical(self, self.tr_ui("불러오기 실패"), f"{msg_text}\n{e}")
            return
        self.glossary_path = path
        self.glossary_text = text
        self.changed = True
        self.refresh_preview()
        QMessageBox.information(self, self.tr_ui("불러오기 완료"), self.tr_ui("단어장을 캐시에 반영했습니다. 닫기를 누르면 유지됩니다."))

    def refresh_glossary_file(self):
        if not self.glossary_path:
            QMessageBox.information(self, self.tr_ui("갱신할 파일 없음"), self.tr_ui("먼저 불러오기로 TXT 파일을 선택해주세요."))
            return
        if not os.path.exists(self.glossary_path):
            QMessageBox.warning(self, self.tr_ui("파일 없음"), self.tr_ui("기존 TXT 파일 경로를 찾을 수 없습니다. 다시 불러오기를 해주세요."))
            return
        try:
            text = read_text_file_for_cache(self.glossary_path)
        except Exception as e:
            msg_text = self.tr_ui("TXT 파일을 다시 읽지 못했습니다:")
            QMessageBox.critical(self, self.tr_ui("갱신 실패"), f"{msg_text}\n{e}")
            return
        self.glossary_text = text
        self.changed = True
        self.refresh_preview()
        QMessageBox.information(self, self.tr_ui("갱신 완료"), self.tr_ui("기존 TXT 파일 내용으로 단어장 캐시를 갱신했습니다."))

    def reset_glossary(self):
        ans = QMessageBox.question(
            self,
            self.tr_ui("단어장 초기화"),
            self.tr_ui("저장된 단어장 캐시를 지울까요?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        self.glossary_text = ""
        self.glossary_path = ""
        self.changed = True
        self.refresh_preview()

    def get_glossary_state(self):
        return self.glossary_text, self.glossary_path, self.changed





class EnterCommitFilter(QObject):
    """프리셋/설정 창의 단일 입력칸에서 Enter가 옆 버튼을 누르지 않도록 막는다.
    ESC는 폰트/입력 위젯에 포커스가 있을 때 먼저 포커스만 빼고, 창 닫기 같은 기본 동작은 막는다.
    """

    def __init__(self, parent_dialog=None, fallback_widget=None, accept_dialog=False, parent=None):
        super().__init__(parent)
        self.parent_dialog = parent_dialog
        self.fallback_widget = fallback_widget
        self.accept_dialog = bool(accept_dialog)

    def _find_parent(self, obj, cls):
        try:
            p = obj
            for _ in range(6):
                if p is None or not hasattr(p, "parent"):
                    return None
                p = p.parent()
                if isinstance(p, cls):
                    return p
        except Exception:
            return None
        return None

    def _is_font_or_input_focus(self, obj):
        try:
            if isinstance(obj, (QLineEdit, QAbstractSpinBox, QComboBox, QFontComboBox, QListWidget, QKeySequenceEdit)):
                return True
            if self._find_parent(obj, QFontComboBox) is not None:
                return True
            if self._find_parent(obj, QComboBox) is not None:
                return True
            if self._find_parent(obj, QAbstractSpinBox) is not None:
                return True
        except Exception:
            pass
        return False

    def _escape_focus(self, obj):
        try:
            combo = obj if isinstance(obj, QComboBox) else self._find_parent(obj, QComboBox)
            if combo is not None:
                try:
                    combo.hidePopup()
                except Exception:
                    pass
                try:
                    line = combo.lineEdit()
                    if line is not None:
                        line.clearFocus()
                except Exception:
                    pass
                try:
                    combo.clearFocus()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            spin = obj if isinstance(obj, QAbstractSpinBox) else self._find_parent(obj, QAbstractSpinBox)
            if spin is not None:
                try:
                    spin.interpretText()
                except Exception:
                    pass
                try:
                    line = spin.lineEdit()
                    if line is not None:
                        line.clearFocus()
                except Exception:
                    pass
                try:
                    spin.clearFocus()
                except Exception:
                    pass
        except Exception:
            pass
        try:
            obj.clearFocus()
        except Exception:
            pass
        target = self.fallback_widget or self.parent_dialog
        try:
            if target is not None:
                target.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass

    def eventFilter(self, obj, event):
        try:
            if event.type() == QEvent.Type.KeyPress and event.key() == Qt.Key.Key_Escape:
                if self._is_font_or_input_focus(obj):
                    self._escape_focus(obj)
                    event.accept()
                    return True

            if event.type() == QEvent.Type.KeyPress and event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
                if event.modifiers() & (
                    Qt.KeyboardModifier.ControlModifier
                    | Qt.KeyboardModifier.ShiftModifier
                    | Qt.KeyboardModifier.AltModifier
                ):
                    return False

                if self.accept_dialog and self.parent_dialog is not None:
                    self.parent_dialog.accept()
                    event.accept()
                    return True

                try:
                    spin = obj if isinstance(obj, QAbstractSpinBox) else self._find_parent(obj, QAbstractSpinBox)
                    if spin is not None:
                        spin.interpretText()
                        spin.clearFocus()
                except Exception:
                    pass

                try:
                    obj.clearFocus()
                except Exception:
                    pass

                target = self.fallback_widget or self.parent_dialog
                try:
                    if target is not None:
                        target.setFocus(Qt.FocusReason.OtherFocusReason)
                except Exception:
                    pass

                event.accept()
                return True
        except Exception:
            pass
        return super().eventFilter(obj, event)


class FontSelectDialog(QDialog):
    """YSB 전용 글꼴 선택 창.
    검색/목록/스타일/미리보기를 한 화면에서 제공한다.
    """

    # Qt 기본 글꼴 DB에서 누락되는 Windows 사용자/시스템 글꼴을 보강하기 위한
    # 세션 캐시. 글꼴 선택창을 열 때마다 Windows Fonts 폴더를 다시 훑지 않는다.
    _extra_font_scan_done = False
    _extra_font_families = []
    _extra_font_ids = []

    def __init__(self, current_family="", current_size=24, current_bold=False, current_italic=False, parent=None):
        super().__init__(parent)
        self._ui_language = normalize_ui_language(getattr(parent, "ui_language", current_ui_language()))
        self.parent_window = parent
        self.selected_family = str(current_family or "")
        self.selected_style = ""
        self.current_size = int(current_size or 24)
        self.current_bold = bool(current_bold)
        self.current_italic = bool(current_italic)
        self.all_families = []
        self.filtered_families = []
        self.font_db = None

        self.setWindowTitle(translate_ui_text("글꼴 선택", self._ui_language))
        self.resize(820, 600)
        try:
            if parent is not None and hasattr(parent, "settings_dialog_style"):
                self.setStyleSheet(parent.settings_dialog_style())
            if parent is not None and hasattr(parent, "apply_native_title_bar_theme"):
                parent.schedule_native_title_bar_theme(self, dark=not parent.is_light_theme())
        except Exception:
            pass

        root = QVBoxLayout(self)
        root.setContentsMargins(14, 14, 14, 14)
        root.setSpacing(10)

        title = QLabel(translate_ui_text("글꼴 선택", self._ui_language), self)
        title.setObjectName("SettingsDialogTitle")
        root.addWidget(title)

        info = QLabel(
            translate_ui_text(
                "글꼴 이름을 검색하거나 목록에서 선택합니다. 오른쪽에서 스타일과 미리보기를 확인한 뒤 확인을 누르면 적용됩니다.",
                self._ui_language,
            ),
            self,
        )
        info.setObjectName("SettingsDescription")
        info.setWordWrap(True)
        root.addWidget(info)

        top = QHBoxLayout()
        top.setSpacing(12)

        left_top = QVBoxLayout()
        left_top.setSpacing(4)
        search_label = QLabel(translate_ui_text("검색", self._ui_language), self)
        self.search_edit = QLineEdit(self)
        self.search_edit.setPlaceholderText(translate_ui_text("예: Gothic, Myeongjo, Noto", self._ui_language))
        self.search_edit.setToolTip(translate_ui_text("글꼴 이름을 입력하면 아래 목록이 즉시 줄어듭니다.", self._ui_language))
        self.search_edit.textChanged.connect(self.filter_fonts)
        left_top.addWidget(search_label)
        left_top.addWidget(self.search_edit)
        top.addLayout(left_top, 2)

        right_top = QVBoxLayout()
        right_top.setSpacing(4)
        style_label = QLabel(translate_ui_text("폰트 스타일", self._ui_language), self)
        self.style_combo = QComboBox(self)
        self.style_combo.setToolTip(translate_ui_text("Regular, Bold, DemiBold 같은 글꼴 스타일을 선택합니다.", self._ui_language))
        self.style_combo.currentIndexChanged.connect(self.on_style_changed)
        self.import_font_btn = QPushButton(self.font_import_text("폰트 불러오기"), self)
        self.import_font_btn.setToolTip(self.font_import_text("TTF, OTF, TTC 같은 폰트 파일을 불러옵니다."))
        self.import_font_btn.clicked.connect(self.import_font_file)
        style_row = QHBoxLayout()
        style_row.setSpacing(6)
        style_row.addWidget(self.style_combo, 1)
        style_row.addWidget(self.import_font_btn)
        right_top.addWidget(style_label)
        right_top.addLayout(style_row)
        top.addLayout(right_top, 1)

        root.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)

        list_header = QHBoxLayout()
        list_header.setSpacing(6)
        list_label = QLabel(translate_ui_text("글꼴 목록", self._ui_language), self)
        self.refresh_fonts_btn = QPushButton(self.font_refresh_text("폰트 갱신"), self)
        self.refresh_fonts_btn.setToolTip(self.font_refresh_text("Windows에 설치되어 있지만 목록에 보이지 않는 글꼴을 다시 찾습니다."))
        self.refresh_fonts_btn.clicked.connect(self.confirm_refresh_fonts)
        list_header.addWidget(list_label)
        list_header.addStretch()
        list_header.addWidget(self.refresh_fonts_btn)
        left.addLayout(list_header)

        self.font_list = QListWidget(self)
        self.font_list.setToolTip(translate_ui_text("목록에서 글꼴을 선택합니다. 더블클릭하면 바로 적용합니다.", self._ui_language))
        self.font_list.itemSelectionChanged.connect(self.on_font_selection_changed)
        self.font_list.itemDoubleClicked.connect(lambda _item: self.accept())
        left.addWidget(self.font_list, 1)
        mid.addLayout(left, 1)

        right = QVBoxLayout()
        right.setSpacing(6)

        selected_label_title = QLabel(translate_ui_text("선택한 글꼴", self._ui_language), self)
        self.selected_label = QLabel("-", self)
        self.selected_label.setObjectName("SettingsPath")
        right.addWidget(selected_label_title)
        right.addWidget(self.selected_label)

        preview_label = QLabel(translate_ui_text("미리보기", self._ui_language), self)
        self.preview_edit = QTextEdit(self)
        self.preview_edit.setReadOnly(False)
        self.preview_edit.setPlainText(
            "가나다라마바사아자차카타파하\n"
            "ABCDEFGHIJKLMNOPQRSTUVWXYZ\n"
            "abcdefghijklmnopqrstuvwxyz\n"
            "0123456789\n"
            "쿠っ…貴方たちっ"
        )
        self.preview_edit.setMinimumWidth(340)
        right.addWidget(preview_label)
        right.addWidget(self.preview_edit, 1)

        size_row = QHBoxLayout()
        size_row.addWidget(QLabel(translate_ui_text("미리보기 크기", self._ui_language), self))
        self.size_spin = QSpinBox(self)
        self.size_spin.setRange(8, 120)
        self.size_spin.setValue(max(8, min(120, self.current_size)))
        self.size_spin.valueChanged.connect(self.update_preview)
        size_row.addWidget(self.size_spin)
        size_row.addStretch()
        right.addLayout(size_row)

        mid.addLayout(right, 1)
        root.addLayout(mid, 1)

        buttons = QDialogButtonBox(self)
        self.ok_btn = buttons.addButton(translate_ui_text("확인", self._ui_language), QDialogButtonBox.ButtonRole.AcceptRole)
        self.cancel_btn = buttons.addButton(translate_ui_text("닫기", self._ui_language), QDialogButtonBox.ButtonRole.RejectRole)
        self.ok_btn.setDefault(True)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.install_font_dialog_enter_accept()

        self.load_fonts()
        self.select_initial_font()
        self.search_edit.setFocus()

    def tr_ui(self, text):
        return translate_ui_text(text, self._ui_language)

    def font_refresh_text(self, text):
        """글꼴 갱신 버튼/알림용 간단한 KO/EN 문구."""
        lang = str(getattr(self, "_ui_language", "ko") or "ko").lower()
        if not lang.startswith("en"):
            return translate_ui_text(text, self._ui_language)

        en = {
            "폰트 갱신": "Refresh Fonts",
            "Windows에 설치되어 있지만 목록에 보이지 않는 글꼴을 다시 찾습니다.": "Search again for fonts installed in Windows but missing from the list.",
            "폰트 갱신 확인": "Refresh Fonts",
            "Windows 글꼴 폴더와 사용자 글꼴 폴더를 다시 검색합니다.\n\n일부 글꼴은 Qt 기본 목록에 바로 보이지 않을 수 있어, 이 작업은 누락된 글꼴을 추가로 등록합니다.\n\n글꼴이 많으면 잠시 걸릴 수 있습니다. 계속할까요?": "This will scan the Windows Fonts folder and your user Fonts folder again.\n\nSome fonts may not appear in Qt's default list, so this registers missing fonts as application fonts.\n\nIt may take a moment if you have many fonts. Continue?",
            "폰트 갱신 완료": "Font refresh complete",
            "폰트 목록을 갱신했습니다.\n새로 추가된 글꼴 패밀리: {count}개": "The font list has been refreshed.\nNew font families added: {count}",
            "폰트 갱신 실패": "Font refresh failed",
            "폰트 갱신 중 오류가 발생했습니다.": "An error occurred while refreshing fonts.",
        }
        return en.get(text, translate_ui_text(text, self._ui_language))

    def font_import_text(self, text):
        lang = str(getattr(self, "_ui_language", "ko") or "ko").lower()
        if not lang.startswith("en"):
            return translate_ui_text(text, self._ui_language)
        en = {
            "폰트 불러오기": "Import Font",
            "TTF, OTF, TTC 같은 폰트 파일을 불러옵니다.": "Import font files such as TTF, OTF, or TTC.",
            "폰트 파일 선택": "Select Font File",
            "폰트 파일 (*.ttf *.otf *.ttc *.otc)": "Font Files (*.ttf *.otf *.ttc *.otc)",
            "폰트 불러오기 방식": "Import Font Mode",
            "프로그램에만 추가": "Add to this program only",
            "Windows에 설치": "Install to Windows",
            "폰트를 어디에 추가할까요?": "Where should this font be added?",
            "폰트 불러오기 완료": "Font import complete",
            "폰트를 불러왔습니다.": "The font has been imported.",
            "추가된 글꼴": "Added font families",
            "폰트 불러오기 실패": "Font import failed",
            "폰트 파일을 불러오지 못했습니다.": "Could not import the font file.",
            "Windows 설치는 Windows에서만 사용할 수 있습니다. 프로그램에만 추가합니다.": "Windows installation is only available on Windows. It will be added to this program only.",
        }
        return en.get(text, translate_ui_text(text, self._ui_language))

    @classmethod
    def imported_font_dir(cls):
        try:
            d = get_cache_dir() / "imported_fonts"
            d.mkdir(parents=True, exist_ok=True)
            return d
        except Exception:
            return None

    @classmethod
    def add_application_font_file(cls, path):
        try:
            font_id = QFontDatabase.addApplicationFont(str(path))
        except Exception:
            font_id = -1
        if font_id is None or int(font_id) < 0:
            return []
        try:
            cls._extra_font_ids.append(int(font_id))
        except Exception:
            pass
        try:
            families = [str(x) for x in QFontDatabase.applicationFontFamilies(int(font_id)) if str(x).strip()]
        except Exception:
            families = []
        if families:
            cls._extra_font_families = sorted(set(list(cls._extra_font_families) + families), key=lambda s: str(s).lower())
        return families

    @classmethod
    def load_imported_program_fonts(cls):
        d = cls.imported_font_dir()
        if d is None:
            return []
        families = []
        for path in sorted(d.glob("*")):
            if path.suffix.lower() not in {".ttf", ".otf", ".ttc", ".otc"}:
                continue
            families.extend(cls.add_application_font_file(path))
        return families

    def copy_font_to_program(self, source_path):
        folder = self.imported_font_dir()
        if folder is None:
            return Path(source_path)
        src = Path(source_path)
        dst = folder / src.name
        if dst.exists():
            stem = src.stem
            suffix = src.suffix
            n = 2
            while True:
                cand = folder / f"{stem}_{n}{suffix}"
                if not cand.exists():
                    dst = cand
                    break
                n += 1
        shutil.copy2(src, dst)
        return dst

    def install_font_to_windows_user(self, source_path):
        if not sys.platform.startswith("win"):
            return self.copy_font_to_program(source_path)
        src = Path(source_path)
        folder = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"
        folder.mkdir(parents=True, exist_ok=True)
        dst = folder / src.name
        if not dst.exists():
            shutil.copy2(src, dst)
        try:
            import winreg
            name = src.stem
            ext = src.suffix.lower()
            kind = "TrueType" if ext in {".ttf", ".ttc"} else "OpenType"
            reg_name = f"{name} ({kind})"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows NT\CurrentVersion\Fonts", 0, winreg.KEY_SET_VALUE) as key:
                winreg.SetValueEx(key, reg_name, 0, winreg.REG_SZ, str(dst))
        except Exception:
            pass
        try:
            import ctypes
            FR_PRIVATE = 0x10
            ctypes.windll.gdi32.AddFontResourceExW(str(dst), 0, 0)
            HWND_BROADCAST = 0xFFFF
            WM_FONTCHANGE = 0x001D
            ctypes.windll.user32.SendMessageTimeoutW(HWND_BROADCAST, WM_FONTCHANGE, 0, 0, 0, 1000, None)
        except Exception:
            pass
        return dst

    def import_font_file(self):
        path, _filter = QFileDialog.getOpenFileName(
            self,
            self.font_import_text("폰트 파일 선택"),
            "",
            self.font_import_text("폰트 파일 (*.ttf *.otf *.ttc *.otc)"),
        )
        if not path:
            return
        options = [self.font_import_text("프로그램에만 추가"), self.font_import_text("Windows에 설치")]
        choice, ok = QInputDialog.getItem(
            self,
            self.font_import_text("폰트 불러오기 방식"),
            self.font_import_text("폰트를 어디에 추가할까요?"),
            options,
            0,
            False,
        )
        if not ok:
            return
        try:
            if choice == self.font_import_text("Windows에 설치"):
                if not sys.platform.startswith("win"):
                    QMessageBox.information(self, self.font_import_text("폰트 불러오기 방식"), self.font_import_text("Windows 설치는 Windows에서만 사용할 수 있습니다. 프로그램에만 추가합니다."))
                    dst = self.copy_font_to_program(path)
                else:
                    dst = self.install_font_to_windows_user(path)
            else:
                dst = self.copy_font_to_program(path)
            families = self.add_application_font_file(dst)
            if not families:
                raise RuntimeError(self.font_import_text("폰트 파일을 불러오지 못했습니다."))
            try:
                self.__class__._extra_font_scan_done = True
                self.load_fonts()
                self.selected_family = families[0]
                self.filter_fonts(self.search_edit.text())
                # 새로 추가한 글꼴을 바로 선택한다.
                for i in range(self.font_list.count()):
                    if self.font_list.item(i).text() == families[0]:
                        self.font_list.setCurrentRow(i)
                        break
                self.on_font_selection_changed()
            except Exception:
                pass
            QMessageBox.information(
                self,
                self.font_import_text("폰트 불러오기 완료"),
                f"{self.font_import_text('폰트를 불러왔습니다.')}\n{self.font_import_text('추가된 글꼴')}: {', '.join(families)}",
            )
        except Exception as exc:
            QMessageBox.warning(self, self.font_import_text("폰트 불러오기 실패"), f"{self.font_import_text('폰트 파일을 불러오지 못했습니다.')}\n{exc}")

    def is_plain_enter_event(self, event):
        try:
            return (
                event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
                and not (
                    event.modifiers()
                    & (
                        Qt.KeyboardModifier.ControlModifier
                        | Qt.KeyboardModifier.ShiftModifier
                        | Qt.KeyboardModifier.AltModifier
                    )
                )
            )
        except Exception:
            return False

    def _is_completer_popup_event(self, obj=None):
        try:
            completer = getattr(self, "completer", None)
            popup = completer.popup() if completer is not None else None
            if popup is None or not popup.isVisible():
                return False
            if obj is popup:
                return True
            if isinstance(obj, QWidget) and (obj.window() is popup or obj.parentWidget() is popup):
                return True
            try:
                fw = QApplication.focusWidget()
                if isinstance(fw, QWidget) and (fw is popup or fw.window() is popup or fw.parentWidget() is popup):
                    return True
            except Exception:
                pass
        except Exception:
            pass
        return False

    def _is_search_edit_focus(self, obj=None):
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None
        for target in (obj if isinstance(obj, QWidget) else None, fw):
            try:
                if target is self.search_edit:
                    return True
                if isinstance(target, QWidget) and target.parentWidget() is self.search_edit:
                    return True
            except Exception:
                pass
        return False

    def _is_preview_text_focus(self, obj=None):
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None
        for target in (obj if isinstance(obj, QWidget) else None, fw):
            try:
                if target is self.preview_edit:
                    return True
                if isinstance(target, QWidget) and target.window() is self and self.preview_edit.isAncestorOf(target):
                    return True
            except Exception:
                pass
        return False

    def commit_search_enter(self):
        """검색창 Enter는 확인/적용이 아니라 검색어 확정으로만 처리한다."""
        try:
            # textChanged로 이미 필터링되지만 IME/완성 입력 직후 값을 한 번 더 반영한다.
            self.filter_fonts(self.search_edit.text())
        except Exception:
            pass
        try:
            self.search_edit.deselect()
        except Exception:
            pass
        try:
            self.search_edit.clearFocus()
        except Exception:
            pass
        try:
            # 검색 확정 뒤에는 목록으로 포커스를 넘긴다. 다음 Enter에서만 확인/적용된다.
            if self.font_list.count() > 0:
                if self.font_list.currentRow() < 0:
                    self.font_list.setCurrentRow(0)
                self.font_list.setFocus(Qt.FocusReason.OtherFocusReason)
            else:
                self.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass

    def accept_by_enter(self):
        # 검색창에 포커스가 있을 때 Enter는 검색어 확정만 한다.
        # 글꼴 적용은 포커스가 검색/미리보기 텍스트 박스 밖으로 나온 뒤 Enter를 눌렀을 때만 실행한다.
        if self._is_search_edit_focus():
            self.commit_search_enter()
            return
        if self._is_preview_text_focus():
            return
        try:
            if self.size_spin is not None:
                self.size_spin.interpretText()
        except Exception:
            pass
        self.accept()

    def install_font_dialog_enter_accept(self):
        self._enter_accept_filter = EnterCommitFilter(parent_dialog=self, accept_dialog=True, parent=self)
        # 검색창/미리보기 텍스트 박스에는 확인용 Enter 필터를 붙이지 않는다.
        # 검색창 Enter는 commit_search_enter()에서 검색어 확정만 처리한다.
        for _w in (self.style_combo, self.font_list, self.size_spin):
            try:
                _w.installEventFilter(self._enter_accept_filter)
            except Exception:
                pass

        try:
            self.search_edit.returnPressed.connect(self.commit_search_enter)
        except Exception:
            pass
        try:
            line = self.size_spin.lineEdit()
            if line is not None:
                line.installEventFilter(self._enter_accept_filter)
                line.returnPressed.connect(self.accept_by_enter)
        except Exception:
            pass

        # QComboBox는 Enter를 자체적으로 삼키거나 팝업 창으로 이벤트를 넘길 수 있다.
        # 그래서 글꼴 선택창이 떠 있는 동안 QApplication 레벨에서도 Enter를 잡는다.
        try:
            self.installEventFilter(self)
            for child in self.findChildren(QWidget):
                child.installEventFilter(self)
            app = QApplication.instance()
            if app is not None:
                app.installEventFilter(self)
                self._app_enter_filter_installed = True
        except Exception:
            self._app_enter_filter_installed = False

    def _font_dialog_focus_escape_target(self, obj=None):
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None
        for target in (obj if isinstance(obj, QWidget) else None, fw):
            if target is None:
                continue
            try:
                if target is self:
                    continue
                if isinstance(target, (QLineEdit, QTextEdit, QPlainTextEdit, QAbstractSpinBox, QComboBox, QFontComboBox, QListWidget, QKeySequenceEdit)):
                    return target
                p = target
                for _ in range(8):
                    p = p.parent() if p is not None and hasattr(p, "parent") else None
                    if isinstance(p, (QAbstractSpinBox, QComboBox, QFontComboBox, QListWidget, QKeySequenceEdit)):
                        return p
            except Exception:
                pass
        return None

    def escape_font_dialog_focus(self, obj=None):
        target = self._font_dialog_focus_escape_target(obj)
        if target is None:
            return False
        try:
            if isinstance(target, QComboBox):
                target.hidePopup()
        except Exception:
            pass
        try:
            if isinstance(target, QAbstractSpinBox):
                target.interpretText()
        except Exception:
            pass
        try:
            line = target.lineEdit()
            if line is not None:
                try:
                    line.deselect()
                except Exception:
                    pass
                line.clearFocus()
        except Exception:
            pass
        try:
            if hasattr(target, "deselect"):
                target.deselect()
            target.clearFocus()
        except Exception:
            pass
        try:
            self.setFocus(Qt.FocusReason.OtherFocusReason)
            QTimer.singleShot(0, lambda: self.setFocus(Qt.FocusReason.OtherFocusReason))
        except Exception:
            pass
        return True

    def eventFilter(self, obj, event):
        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and event.key() == Qt.Key.Key_Escape:
            try:
                active_modal = QApplication.activeModalWidget()
                active_window = QApplication.activeWindow()
                belongs_to_this_dialog = isinstance(obj, QWidget) and ((obj.window() is self) or (obj.parentWidget() is self))
                if active_modal is self or active_window is self or belongs_to_this_dialog:
                    if self.escape_font_dialog_focus(obj):
                        event.accept()
                        return True
            except Exception:
                pass

        if event.type() in (QEvent.Type.ShortcutOverride, QEvent.Type.KeyPress) and self.is_plain_enter_event(event):
            try:
                # 검색 결과는 하단 목록만 사용한다. QCompleter 팝업은 비활성화되어 있다.
                if self._is_completer_popup_event(obj):
                    return False

                # QApplication 레벨 필터이므로 다른 창의 Enter까지 먹지 않게,
                # 현재 글꼴 선택창이 모달/활성 상태일 때만 처리한다.
                active_modal = QApplication.activeModalWidget()
                active_window = QApplication.activeWindow()
                belongs_to_this_dialog = False
                if obj is self:
                    belongs_to_this_dialog = True
                elif isinstance(obj, QWidget):
                    belongs_to_this_dialog = (obj.window() is self) or (obj.parentWidget() is self)
                if active_modal is self or active_window is self or belongs_to_this_dialog:
                    if self._is_search_edit_focus(obj):
                        if event.type() == QEvent.Type.KeyPress:
                            self.commit_search_enter()
                        event.accept()
                        return True
                    if self._is_preview_text_focus(obj):
                        # 미리보기 텍스트 박스에서는 Enter를 텍스트 편집 입력으로 남겨둔다.
                        return False
                    if event.type() == QEvent.Type.KeyPress:
                        self.accept_by_enter()
                    event.accept()
                    return True
            except Exception:
                if event.type() == QEvent.Type.KeyPress:
                    self.accept_by_enter()
                event.accept()
                return True
        return super().eventFilter(obj, event)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            if self.escape_font_dialog_focus(QApplication.focusWidget()):
                event.accept()
                return
        if self.is_plain_enter_event(event):
            if self._is_search_edit_focus(QApplication.focusWidget()):
                self.commit_search_enter()
                event.accept()
                return
            if self._is_preview_text_focus(QApplication.focusWidget()):
                super().keyPressEvent(event)
                return
            self.accept_by_enter()
            event.accept()
            return
        super().keyPressEvent(event)

    def done(self, result):
        try:
            app = QApplication.instance()
            if app is not None and getattr(self, "_app_enter_filter_installed", False):
                app.removeEventFilter(self)
        except Exception:
            pass
        super().done(result)

    def load_fonts(self):
        # Qt6/PyQt6 환경에서는 QFontDatabase 인스턴스 생성 방식이 흔들릴 수 있다.
        # 먼저 정적 메서드로 읽고, 실패하면 인스턴스 방식으로 한 번 더 시도한다.
        families = []
        self.font_db = None

        try:
            families = list(QFontDatabase.families())
        except Exception:
            families = []

        if not families:
            try:
                self.font_db = QFontDatabase()
                families = list(self.font_db.families())
            except Exception:
                self.font_db = None
                families = []

        # 프로그램에 불러온 글꼴은 다음 실행에서도 보이도록 캐시 폴더에서 항상 등록한다.
        # addApplicationFont()로 등록한 패밀리는 QFontDatabase.families() 호출 시점에 따라
        # 바로 목록에 섞이지 않을 수 있으므로 반환값을 직접 목록에 합친다.
        try:
            imported_families = self.__class__.load_imported_program_fonts()
            if imported_families:
                families.extend(list(imported_families))
        except Exception:
            pass

        # 첫 진입에서는 Windows Fonts 폴더를 자동 스캔하지 않는다.
        # 사용자가 [폰트 갱신]을 눌러 명시적으로 요청한 경우에만 누락 글꼴을 보강한다.
        try:
            if self.__class__._extra_font_scan_done:
                families.extend(list(self.__class__._extra_font_families))
                families.extend(list(QFontDatabase.families()))
        except Exception:
            pass

        # 최후 fallback: 현재 QApplication 기본 폰트라도 목록에 넣어 빈 창을 피한다.
        if not families:
            try:
                families = [QApplication.font().family()]
            except Exception:
                families = []

        families = sorted({str(x) for x in families if str(x).strip()}, key=lambda s: s.lower())
        self.all_families = families
        self.filtered_families = list(families)
        self.populate_list(families)
        self.setup_completer()

    @classmethod
    def load_extra_system_font_families(cls, force=False):
        """Windows 글꼴 파일을 직접 앱 글꼴로 등록해 Qt 목록 누락을 줄인다.

        QFontDatabase.families()는 Qt가 인식한 패밀리만 반환하기 때문에,
        Windows에 실제 설치되어 있어도 사용자 계정 글꼴/일부 OTF/TTC/Variable Font가
        목록에 안 보이는 경우가 있다. 이 함수는 자동 실행하지 않고, 사용자가
        [폰트 갱신]을 눌렀을 때만 실행한다.
        """
        if cls._extra_font_scan_done and not force:
            return list(cls._extra_font_families)

        cls._extra_font_scan_done = True
        if force:
            cls._extra_font_families = []
            cls._extra_font_ids = []

        extra_families = []
        font_paths = cls.discover_windows_font_files()

        for path in font_paths:
            try:
                font_id = QFontDatabase.addApplicationFont(str(path))
            except Exception:
                font_id = -1

            if font_id is None or int(font_id) < 0:
                continue

            try:
                cls._extra_font_ids.append(int(font_id))
            except Exception:
                pass

            try:
                extra_families.extend([str(x) for x in QFontDatabase.applicationFontFamilies(int(font_id))])
            except Exception:
                pass

        cls._extra_font_families = sorted({x for x in extra_families if str(x).strip()}, key=lambda s: str(s).lower())
        return list(cls._extra_font_families)

    @staticmethod
    def discover_windows_font_files():
        """Windows 시스템/사용자 글꼴 파일 후보를 찾는다."""
        if not sys.platform.startswith("win"):
            return []

        exts = {".ttf", ".otf", ".ttc", ".otc"}
        candidates = []
        seen = set()

        def add_path(path_obj):
            try:
                p = Path(path_obj).expanduser()
            except Exception:
                return
            try:
                if not p.is_absolute():
                    return
                p = p.resolve()
            except Exception:
                pass
            key = str(p).lower()
            if key in seen:
                return
            if p.exists() and p.is_file() and p.suffix.lower() in exts:
                seen.add(key)
                candidates.append(p)

        def add_folder(folder_obj):
            try:
                folder = Path(folder_obj).expanduser()
            except Exception:
                return
            if not folder.exists() or not folder.is_dir():
                return
            try:
                for p in folder.rglob("*"):
                    if p.is_file() and p.suffix.lower() in exts:
                        add_path(p)
            except Exception:
                pass

        windir = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
        windows_fonts = Path(windir) / "Fonts"
        local_fonts = Path(os.environ.get("LOCALAPPDATA", "")) / "Microsoft" / "Windows" / "Fonts"

        add_folder(windows_fonts)
        add_folder(local_fonts)

        # 레지스트리에 등록되어 있지만 폴더 스캔에서 빠진 글꼴 경로도 보강한다.
        try:
            import winreg

            reg_locations = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
                (winreg.HKEY_CURRENT_USER, r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Fonts"),
            ]
            for root, subkey in reg_locations:
                try:
                    with winreg.OpenKey(root, subkey) as key:
                        count = winreg.QueryInfoKey(key)[1]
                        for idx in range(count):
                            try:
                                _name, value, _typ = winreg.EnumValue(key, idx)
                            except Exception:
                                continue
                            value_text = str(value or "").strip()
                            if not value_text:
                                continue

                            value_path = Path(value_text)
                            if value_path.is_absolute():
                                add_path(value_path)
                            else:
                                add_path(windows_fonts / value_text)
                                add_path(local_fonts / value_text)
                except Exception:
                    continue
        except Exception:
            pass

        return candidates

    def confirm_refresh_fonts(self):
        """사용자 확인 후 Windows 글꼴 폴더를 다시 스캔한다."""
        message = self.font_refresh_text(
            "Windows 글꼴 폴더와 사용자 글꼴 폴더를 다시 검색합니다.\n\n"
            "일부 글꼴은 Qt 기본 목록에 바로 보이지 않을 수 있어, 이 작업은 누락된 글꼴을 추가로 등록합니다.\n\n"
            "글꼴이 많으면 잠시 걸릴 수 있습니다. 계속할까요?"
        )
        try:
            reply = QMessageBox.question(
                self,
                self.font_refresh_text("폰트 갱신 확인"),
                message,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return
        except Exception:
            return

        before = set(str(x) for x in getattr(self, "all_families", []) if str(x).strip())
        search_text = ""
        try:
            search_text = self.search_edit.text()
        except Exception:
            search_text = ""

        try:
            self.refresh_fonts_btn.setEnabled(False)
        except Exception:
            pass
        QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
        try:
            extra = self.load_extra_system_font_families(force=True)

            families = []
            try:
                families.extend(list(QFontDatabase.families()))
            except Exception:
                pass
            try:
                families.extend(list(extra))
            except Exception:
                pass

            families = sorted({str(x) for x in families if str(x).strip()}, key=lambda s: s.lower())
            self.all_families = families

            if search_text:
                self.filter_fonts(search_text)
            else:
                self.filtered_families = list(families)
                self.populate_list(families)

            self.select_initial_font()
            added_count = max(0, len(set(families) - before))

            QMessageBox.information(
                self,
                self.font_refresh_text("폰트 갱신 완료"),
                self.font_refresh_text("폰트 목록을 갱신했습니다.\n새로 추가된 글꼴 패밀리: {count}개").format(count=added_count),
            )
        except Exception as exc:
            try:
                QMessageBox.warning(
                    self,
                    self.font_refresh_text("폰트 갱신 실패"),
                    f"{self.font_refresh_text('폰트 갱신 중 오류가 발생했습니다.')}\n{exc}",
                )
            except Exception:
                pass
        finally:
            QApplication.restoreOverrideCursor()
            try:
                self.refresh_fonts_btn.setEnabled(True)
            except Exception:
                pass


    def setup_completer(self):
        # 검색창 아래에 뜨는 QCompleter 팝업은 사용하지 않는다.
        # 검색 결과는 하단 글꼴 목록(QListWidget) 하나로만 보여준다.
        try:
            self.search_edit.setCompleter(None)
        except Exception:
            pass
        self.completer = None

    def on_completer_activated(self, text):
        fam = str(text or "")
        if not fam:
            return
        self.search_edit.blockSignals(True)
        try:
            self.search_edit.setText(fam)
        finally:
            self.search_edit.blockSignals(False)
        self.filtered_families = [f for f in self.all_families if f == fam]
        self.populate_list(self.filtered_families)
        self.select_family(fam)

    def populate_list(self, families):
        current = self.selected_family
        self.font_list.blockSignals(True)
        try:
            self.font_list.clear()
            for fam in families:
                item = QListWidgetItem(fam)
                item.setData(Qt.ItemDataRole.UserRole, fam)
                self.font_list.addItem(item)
            if current:
                for i in range(self.font_list.count()):
                    if self.font_list.item(i).data(Qt.ItemDataRole.UserRole) == current:
                        self.font_list.setCurrentRow(i)
                        break
        finally:
            self.font_list.blockSignals(False)
        if self.font_list.currentRow() < 0 and self.font_list.count() > 0:
            self.font_list.setCurrentRow(0)
        if self.font_list.count() == 0:
            self.selected_family = ""
            self.selected_label.setText(self.tr_ui("검색 결과 없음"))
            self.style_combo.clear()
            self.preview_edit.setFont(QFont())
            return
        self.on_font_selection_changed()

    def filter_fonts(self, text):
        query = str(text or "").strip().lower()
        if not query:
            self.filtered_families = list(self.all_families)
        else:
            tokens = [t for t in query.replace("_", " ").replace("-", " ").split() if t]

            def score(name):
                low = name.lower()
                if query in low:
                    return (0, low.index(query), len(name), low)
                if tokens and all(t in low for t in tokens):
                    return (1, sum(low.index(t) for t in tokens if t in low), len(name), low)
                compact = low.replace(" ", "")
                qcompact = query.replace(" ", "")
                if qcompact and qcompact in compact:
                    return (2, compact.index(qcompact), len(name), low)
                pos = -1
                ok = True
                total = 0
                for ch in query:
                    pos = low.find(ch, pos + 1)
                    if pos < 0:
                        ok = False
                        break
                    total += pos
                if ok:
                    return (3, total, len(name), low)
                return None

            ranked = []
            for fam in self.all_families:
                sc = score(fam)
                if sc is not None:
                    ranked.append((sc, fam))
            ranked.sort(key=lambda x: x[0])
            self.filtered_families = [fam for _sc, fam in ranked]
        self.populate_list(self.filtered_families)

    def select_initial_font(self):
        if not self.all_families:
            return
        target = self.selected_family or ""
        if target and self.select_family(target):
            return
        self.font_list.setCurrentRow(0)
        self.on_font_selection_changed()

    def select_family(self, family):
        target_low = str(family or "").lower()
        if not target_low:
            return False
        for i in range(self.font_list.count()):
            fam = str(self.font_list.item(i).data(Qt.ItemDataRole.UserRole) or "")
            if fam.lower() == target_low:
                self.font_list.setCurrentRow(i)
                self.font_list.scrollToItem(self.font_list.item(i))
                self.on_font_selection_changed()
                return True
        return False

    def styles_for_family(self, family):
        styles = []
        try:
            styles = list(QFontDatabase.styles(family))
        except Exception:
            styles = []

        if not styles:
            try:
                if self.font_db is not None:
                    styles = list(self.font_db.styles(family))
            except Exception:
                styles = []

        if not styles:
            styles = ["Regular", "Bold", "DemiBold", "Light", "Italic", "Bold Italic"]

        # 중복 제거
        out = []
        seen = set()
        for st in styles:
            st = str(st or "").strip()
            if not st:
                continue
            key = st.lower()
            if key not in seen:
                seen.add(key)
                out.append(st)
        return out or ["Regular"]

    def choose_preferred_style(self, styles):
        if self.selected_style in styles:
            return self.selected_style
        low_map = {s.lower(): s for s in styles}
        if self.current_bold and self.current_italic:
            for key in ("bold italic", "demibold italic", "semi bold italic"):
                if key in low_map:
                    return low_map[key]
        if self.current_bold:
            for key in ("bold", "demibold", "semi bold", "medium"):
                if key in low_map:
                    return low_map[key]
        if self.current_italic:
            for key in ("italic", "regular italic", "light italic"):
                if key in low_map:
                    return low_map[key]
        for key in ("regular", "normal", "medium"):
            if key in low_map:
                return low_map[key]
        return styles[0] if styles else ""

    def update_style_combo(self):
        fam = self.selected_family or ""
        styles = self.styles_for_family(fam)
        chosen = self.choose_preferred_style(styles)
        self.style_combo.blockSignals(True)
        try:
            self.style_combo.clear()
            for st in styles:
                self.style_combo.addItem(st)
            idx = styles.index(chosen) if chosen in styles else 0
            self.style_combo.setCurrentIndex(idx)
            self.selected_style = self.style_combo.currentText()
        finally:
            self.style_combo.blockSignals(False)

    def on_font_selection_changed(self):
        item = self.font_list.currentItem()
        if item is None:
            return
        fam = str(item.data(Qt.ItemDataRole.UserRole) or item.text())
        self.selected_family = fam
        self.selected_label.setText(fam)
        self.update_style_combo()
        self.update_preview()

    def on_style_changed(self):
        self.selected_style = self.style_combo.currentText()
        self.update_preview()

    def font_from_selection(self):
        fam = self.selected_family or ""
        style = self.selected_style or self.style_combo.currentText()
        size = int(self.size_spin.value())
        if not fam:
            return QFont()
        try:
            if style:
                return QFontDatabase.font(fam, style, size)
        except Exception:
            pass
        try:
            if self.font_db is not None and style:
                return self.font_db.font(fam, style, size)
        except Exception:
            pass
        font = QFont(fam, size)
        low = style.lower()
        if any(k in low for k in ("bold", "demibold", "semi bold", "black", "heavy", "extrabold")):
            font.setBold(True)
        if "italic" in low or "oblique" in low:
            font.setItalic(True)
        return font

    def update_preview(self):
        if not self.selected_family:
            return
        self.preview_edit.setFont(self.font_from_selection())

    def selected_font_family(self):
        return self.selected_family or ""

    def selected_font_style(self):
        return self.selected_style or self.style_combo.currentText() or ""

    def selected_is_bold(self):
        low = self.selected_font_style().lower()
        return any(k in low for k in ("bold", "demibold", "semi bold", "black", "heavy", "extrabold"))

    def selected_is_italic(self):
        low = self.selected_font_style().lower()
        return "italic" in low or "oblique" in low




class CenterTaskProgressOverlay(QFrame):
    """Small centered progress/cancel overlay for long API/local operations."""
    cancelRequested = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CenterTaskProgressOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.apply_theme(False)
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)

        panel = QFrame(self)
        panel.setObjectName("CenterTaskProgressPanel")
        self.panel = panel
        # 진행창은 작업별 상세 문구 길이가 다르다.
        # 고정 크기로 두면 일괄 작업처럼 줄이 많은 상세 문구가 아래에서 잘리므로,
        # 내용 높이에 맞춰 패널을 키우되 화면 크기 안에서만 커지게 한다.
        panel.setMinimumSize(600, 264)
        panel.setMaximumSize(900, 760)
        panel.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        panel_layout = QVBoxLayout(panel)
        panel_layout.setContentsMargins(18, 16, 18, 14)
        panel_layout.setSpacing(8)
        self.panel_layout = panel_layout

        self.title_label = QLabel("작업 중", panel)
        self.title_label.setObjectName("CenterTaskTitle")
        panel_layout.addWidget(self.title_label)

        self.detail_label = QLabel("", panel)
        self.detail_label.setObjectName("CenterTaskDetail")
        self.detail_label.setWordWrap(True)
        self.detail_label.setMinimumHeight(112)
        self.detail_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        self.detail_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Fixed)
        panel_layout.addWidget(self.detail_label)

        self.progress = QProgressBar(panel)
        self.progress.setRange(0, 0)
        self.progress.setValue(0)
        self.progress.setFixedHeight(18)
        panel_layout.addWidget(self.progress)

        self.note_label = QLabel("취소 시 현재 페이지 작업이 끝난 뒤 중단됩니다.", panel)
        self.note_label.setObjectName("CenterTaskNote")
        self.note_label.setWordWrap(True)
        self.note_label.setMinimumHeight(34)
        self.note_label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter)
        panel_layout.addWidget(self.note_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.cancel_btn = QPushButton("취소", panel)
        self.cancel_btn.clicked.connect(self._emit_cancel)
        btn_row.addWidget(self.cancel_btn)
        panel_layout.addLayout(btn_row)

        row.addWidget(panel)
        row.addStretch(1)
        outer.addLayout(row)
        outer.addStretch(1)

    def apply_theme(self, light=False):
        self._light_theme = bool(light)
        if light:
            self.setStyleSheet("""
                QFrame#CenterTaskProgressOverlay { background: rgba(244, 246, 250, 92); }
                QFrame#CenterTaskProgressPanel { background:#ffffff; border:1px solid #D1C9CE; border-radius:8px; }
                QLabel#CenterTaskTitle { color:#111827; font-size:17px; font-weight:700; }
                QLabel#CenterTaskDetail { color:#28262B; font-size:12px; }
                QLabel#CenterTaskNote { color:#d97706; font-size:11px; font-weight:600; }
                QProgressBar { background:#E7E2E5; border:1px solid #D1C9CE; border-radius:4px; height:16px; color:#111827; text-align:center; }
                QProgressBar::chunk { background:#8A4A52; border-radius:3px; }
                QPushButton { background:#FAF5F7; color:#111827; border:1px solid #D1C9CE; border-radius:4px; padding:5px 14px; }
                QPushButton:hover { background:#FBF5F6; border-color:#D7A3A9; }
                QPushButton:disabled { background:#F0EAED; color:#A29A9F; border-color:#E0DADF; }
            """)
        else:
            self.setStyleSheet("""
                QFrame#CenterTaskProgressOverlay { background: rgba(0, 0, 0, 90); }
                QFrame#CenterTaskProgressPanel { background:#211F23; border:1px solid #626977; border-radius:8px; }
                QLabel#CenterTaskTitle { color:#ffffff; font-size:17px; font-weight:700; }
                QLabel#CenterTaskDetail { color:#D7D2D5; font-size:12px; }
                QLabel#CenterTaskNote { color:#fbbf24; font-size:11px; }
                QProgressBar { background:#111827; border:1px solid #555056; border-radius:4px; height:16px; color:#ffffff; text-align:center; }
                QProgressBar::chunk { background:#8A4A52; border-radius:3px; }
                QPushButton { background:#3D383E; color:#ffffff; border:1px solid #746B72; border-radius:4px; padding:5px 14px; }
                QPushButton:hover { background:#5C555B; }
                QPushButton:disabled { background:#302C31; color:#827A80; }
            """)


    def _panel_size_limits(self):
        """Return safe dynamic size limits for the centered progress panel."""
        parent = self.parentWidget()
        try:
            if parent is not None:
                rect = parent.rect()
                parent_w = max(1, int(rect.width()))
                parent_h = max(1, int(rect.height()))
            else:
                parent_w, parent_h = 1280, 720
        except Exception:
            parent_w, parent_h = 1280, 720
        min_w = 600
        min_h = 264
        max_w = max(min_w, min(900, parent_w - 56))
        max_h = max(min_h, min(760, parent_h - 56))
        return min_w, min_h, max_w, max_h

    def _detail_text_height(self, width):
        text = str(self.detail_label.text() or "")
        if not text:
            return 112
        try:
            fm = QFontMetrics(self.detail_label.font())
            flags = int(Qt.TextFlag.TextWordWrap | Qt.TextFlag.TextExpandTabs)
            rect = fm.boundingRect(QRect(0, 0, max(80, int(width)), 100000), flags, text)
            # QLabel의 줄 간격/여백을 감안해 약간 더 준다.
            return max(112, int(rect.height()) + 12)
        except Exception:
            line_count = max(1, text.count("\n") + 1)
            return max(112, line_count * 18 + 12)

    def _resize_panel_to_content(self):
        """Grow the panel when detail text has many lines, capped by the parent window.

        The progress overlay is often used as a live supervisor panel for batch jobs.
        A fixed 560x264 panel clips multi-line status details, so the panel height is
        recalculated whenever the title/detail/cancel state changes.
        """
        try:
            min_w, min_h, max_w, max_h = self._panel_size_limits()
            # Wider than the old panel so page/file/status lines fit more comfortably.
            panel_w = min(max_w, max(min_w, 640))
            contents = self.panel_layout.contentsMargins()
            left = int(contents.left())
            right = int(contents.right())
            top = int(contents.top())
            bottom = int(contents.bottom())
            spacing = int(self.panel_layout.spacing())
            inner_w = max(80, panel_w - left - right)

            title_h = max(24, int(self.title_label.sizeHint().height()))
            progress_h = max(18, int(self.progress.sizeHint().height()))
            note_h = 0
            if self.note_label.isVisible():
                note_h = max(34, int(self.note_label.sizeHint().height()))
            btn_h = max(30, int(self.cancel_btn.sizeHint().height()) if self.cancel_btn.isVisible() else 0)
            visible_blocks = 3 + (1 if self.note_label.isVisible() else 0) + (1 if self.cancel_btn.isVisible() else 0)
            spacing_total = max(0, visible_blocks - 1) * spacing

            fixed_h = top + bottom + title_h + progress_h + note_h + btn_h + spacing_total
            max_detail_h = max(112, max_h - fixed_h)
            detail_h = min(max_detail_h, self._detail_text_height(inner_w))
            self.detail_label.setFixedHeight(detail_h)
            panel_h = max(min_h, min(max_h, fixed_h + detail_h))
            current = self.panel.size()
            if current.width() != panel_w or current.height() != panel_h:
                self.panel.setFixedSize(panel_w, panel_h)
        except Exception:
            try:
                self.panel.setFixedSize(640, 320)
                self.detail_label.setFixedHeight(152)
            except Exception:
                pass

    def _emit_cancel(self):
        self.cancel_btn.setEnabled(False)
        self.note_label.setText("취소 요청됨. 현재 페이지 작업이 끝난 뒤 중단됩니다.")
        self._resize_panel_to_content()
        self.cancelRequested.emit()

    def show_task(self, title, detail="", total=0, cancellable=True):
        """작업 진행창을 1회 표시한다.

        진행 중에는 이 위젯 인스턴스를 계속 재사용하고, 상태 변경은
        update_task()로 라벨/진행률만 바꾼다. show_task()가 다시 호출되더라도
        이미 보이는 중이면 창을 새로 띄우거나 크기를 다시 잡지 않는다.
        """
        parent = self.parentWidget()
        if parent is not None:
            try:
                self.apply_theme(_parent_prefers_light_theme(parent))
            except Exception:
                pass
            self.setGeometry(parent.rect())
        self.title_label.setText(str(title or "작업 중"))
        self.detail_label.setText(str(detail or ""))
        self.cancel_btn.setVisible(bool(cancellable))
        self.cancel_btn.setEnabled(bool(cancellable))
        self.note_label.setVisible(bool(cancellable))
        self.note_label.setText("취소 시 현재 페이지 작업이 끝난 뒤 중단됩니다.")
        if total and int(total) > 0:
            self.progress.setRange(0, int(total))
            self.progress.setValue(0)
        else:
            self.progress.setRange(0, 0)
        self._ysb_task_title = str(title or "작업 중")
        self._ysb_task_total = int(total or 0) if str(total or "").strip() else 0
        self._resize_panel_to_content()
        self.show()
        self.raise_()

    def update_task(self, current=None, total=None, detail=None):
        # 업데이트는 같은 창에서 텍스트/진행률만 바꾼다.
        if detail is not None:
            self.detail_label.setText(str(detail))
        if total is not None and int(total) > 0:
            new_total = int(total)
            if self.progress.maximum() != new_total:
                self.progress.setRange(0, new_total)
            self._ysb_task_total = new_total
        if current is not None and self.progress.maximum() > 0:
            self.progress.setValue(max(0, min(int(current), self.progress.maximum())))
        self._resize_panel_to_content()

    def set_paused(self, paused=True, detail=None):
        if detail is not None:
            self.detail_label.setText(str(detail))
        if paused:
            # Stop the indeterminate marquee so the visual state matches the alert.
            if self.progress.maximum() == 0:
                self.progress.setRange(0, 1)
                self.progress.setValue(0)
            self.progress.setEnabled(False)
        else:
            self.progress.setEnabled(True)
        self._resize_panel_to_content()

    def resizeEvent(self, event):
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        try:
            self._resize_panel_to_content()
        except Exception:
            pass
        super().resizeEvent(event)


class CenterTaskAlertOverlay(QFrame):
    """Non-modal center alert panel shown above long-task progress.

    It does not replace QMessageBox for pre-flight validation.  It is used while
    a worker is already running, so the user can read the alert, close it, and
    then press the existing progress panel's cancel button if needed.
    """
    dismissed = pyqtSignal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("CenterTaskAlertOverlay")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, True)
        self.setWindowFlags(Qt.WindowType.Widget)
        self.apply_theme(False)
        self.setVisible(False)

        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addStretch(1)
        row = QHBoxLayout()
        row.addStretch(1)

        self.panel = QFrame(self)
        self.panel.setObjectName("CenterTaskAlertPanel")
        self.panel.setFixedWidth(500)
        panel_layout = QVBoxLayout(self.panel)
        panel_layout.setContentsMargins(18, 14, 18, 12)
        panel_layout.setSpacing(8)

        self.title_label = QLabel("작업 알림", self.panel)
        self.title_label.setObjectName("CenterTaskAlertTitle")
        panel_layout.addWidget(self.title_label)

        self.detail_label = QLabel("", self.panel)
        self.detail_label.setObjectName("CenterTaskAlertDetail")
        self.detail_label.setWordWrap(True)
        panel_layout.addWidget(self.detail_label)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.close_btn = QPushButton("닫기", self.panel)
        self.close_btn.clicked.connect(self._close_clicked)
        btn_row.addWidget(self.close_btn)
        panel_layout.addLayout(btn_row)

        row.addWidget(self.panel)
        row.addStretch(1)
        outer.addLayout(row)
        # Put the alert below the progress panel's center area so they do not overlap.
        outer.addSpacing(190)
        outer.addStretch(1)

    def apply_theme(self, light=False):
        self._light_theme = bool(light)
        if light:
            self.setStyleSheet("""
                QFrame#CenterTaskAlertOverlay { background: transparent; }
                QFrame#CenterTaskAlertPanel { background:#ffffff; border:1px solid #C78A90; border-radius:8px; }
                QLabel#CenterTaskAlertTitle { color:#6F3940; font-size:16px; font-weight:800; }
                QLabel#CenterTaskAlertDetail { color:#5B3136; font-size:12px; }
                QPushButton { background:#fff7f7; color:#6F3940; border:1px solid #D7A3A9; border-radius:4px; padding:5px 14px; }
                QPushButton:hover { background:#F5E8EA; }
            """)
        else:
            self.setStyleSheet("""
                QFrame#CenterTaskAlertOverlay { background: transparent; }
                QFrame#CenterTaskAlertPanel { background:#2b2224; border:1px solid #C78A90; border-radius:8px; }
                QLabel#CenterTaskAlertTitle { color:#ffffff; font-size:16px; font-weight:800; }
                QLabel#CenterTaskAlertDetail { color:#ffe4e6; font-size:12px; }
                QPushButton { background:#4b1f24; color:#ffffff; border:1px solid #f87171; border-radius:4px; padding:5px 14px; }
                QPushButton:hover { background:#5B3136; }
            """)

    def _close_clicked(self):
        self.hide()
        self.dismissed.emit()

    def show_alert(self, title, detail):
        parent = self.parentWidget()
        if parent is not None:
            try:
                self.apply_theme(_parent_prefers_light_theme(parent))
            except Exception:
                pass
            self.setGeometry(parent.rect())
        self.title_label.setText(str(title or "작업 알림"))
        self.detail_label.setText(str(detail or ""))
        self.show()
        self.raise_()

    def resizeEvent(self, event):
        parent = self.parentWidget()
        if parent is not None:
            self.setGeometry(parent.rect())
        super().resizeEvent(event)


class PageTabButton(QFrame):
    def __init__(self, tab_bar, index, text=""):
        super().__init__(tab_bar.content_widget)
        self.tab_bar = tab_bar
        self.index = int(index)
        self._press_pos = None
        self._press_on_close = False
        self._last_style_key = None
        self._hover = False
        self._selected = False
        self._tokens = {}
        self.setAcceptDrops(True)
        self.setObjectName("PageTabButton")
        self.setAttribute(Qt.WidgetAttribute.WA_StyledBackground, False)
        self.setAttribute(Qt.WidgetAttribute.WA_Hover, True)
        self.setFixedHeight(28)
        self.setMinimumWidth(98)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Fixed)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setCursor(Qt.CursorShape.PointingHandCursor)
        self.setMouseTracking(True)
        # Page tabs intentionally do not show hover tooltips.
        # The full page name can be checked by double-click rename or the page list shortcut.
        self.setAttribute(Qt.WidgetAttribute.WA_AlwaysShowToolTips, False)
        self.setToolTip("")

        self._full_text = str(text or "")
        self._min_tab_width = 98
        # 폭 제한은 유지하되 너무 빨리 잘리지 않도록 조금 넓힌다.
        # 이 폭을 넘는 긴 이름만 가운데 생략(앞/뒤 보존)한다.
        self._max_tab_width = 270
        self._pad_left = 10
        self._pad_right = 8
        self._close_area_width = 26
        self._separator_width = 1
        self._right_margin = 2
        self._closable = True
        self.set_text(text)

    def set_closable(self, value):
        self._closable = bool(value)
        self._refresh_elided_text()
        self.update()

    def _close_chrome_width(self):
        if not self._closable:
            return 0
        return int(self._separator_width) + int(self._close_area_width) + int(self._right_margin)

    def _text_rect(self):
        chrome_w = self._close_chrome_width()
        return QRect(
            int(self._pad_left),
            1,
            max(8, self.width() - int(self._pad_left) - int(self._pad_right) - chrome_w),
            max(1, self.height() - 2),
        )

    def _separator_rect(self):
        if not self._closable:
            return QRect()
        x = self.width() - int(self._right_margin) - int(self._close_area_width) - int(self._separator_width)
        return QRect(x, 5, int(self._separator_width), max(1, self.height() - 10))

    def _close_rect(self):
        if not self._closable:
            return QRect()
        x = self.width() - int(self._right_margin) - int(self._close_area_width)
        # x가 아래로 처져 보이지 않도록 닫기 영역 자체를 1px 위로 둔다.
        return QRect(x, 2, int(self._close_area_width), max(1, self.height() - 6))

    def _refresh_elided_text(self):
        full = str(getattr(self, "_full_text", "") or "")
        fm = self.fontMetrics()
        chrome_w = self._close_chrome_width()
        text_w = int(fm.horizontalAdvance(full))
        desired_tab_w = int(self._pad_left) + text_w + int(self._pad_right) + chrome_w
        target_w = max(int(self._min_tab_width), min(int(self._max_tab_width), int(desired_tab_w)))
        self.setFixedWidth(target_w)
        # Keep native/custom tooltips disabled for page tabs.
        self.setToolTip("")

    def set_text(self, text):
        self._full_text = str(text or "")
        self._refresh_elided_text()
        self.update()

    def text(self):
        return str(getattr(self, "_full_text", "") or "")

    def set_visual_state(self, selected=False, tokens=None):
        self._selected = bool(selected)
        self._tokens = dict(tokens or {})
        self.update()

    def enterEvent(self, event):
        self._hover = True
        # Page tab hover should only change visual state, not show a tooltip.
        try:
            QToolTip.hideText()
        except Exception:
            pass
        self.update()
        super().enterEvent(event)

    def leaveEvent(self, event):
        self._hover = False
        try:
            QToolTip.hideText()
        except Exception:
            pass
        self.update()
        super().leaveEvent(event)

    def event(self, event):
        # Block native tooltip events completely for page tabs.
        try:
            if event.type() == QEvent.Type.ToolTip:
                QToolTip.hideText()
                event.ignore()
                return True
        except Exception:
            pass
        return super().event(event)

    def paintEvent(self, event):
        tokens = dict(getattr(self, "_tokens", {}) or {})
        if not tokens:
            tokens = self.tab_bar._theme_tokens() if hasattr(self.tab_bar, "_theme_tokens") else {}
        selected = bool(getattr(self, "_selected", False))
        hover = bool(getattr(self, "_hover", False))

        bg = tokens.get("selected_bg" if selected else "normal_bg", "#2B282D")
        if hover:
            bg = tokens.get("hover_bg", bg)
        fg = tokens.get("selected_fg" if selected else "normal_fg", "#ffffff")
        border = tokens.get("selected_border" if selected else "normal_border", "#3A363B")
        close_fg = tokens.get("close_fg", fg)

        painter = QPainter(self)
        try:
            painter.setRenderHint(QPainter.RenderHint.Antialiasing, False)
            rect = self.rect().adjusted(0, 0, -1, -1)
            painter.fillRect(rect, QColor(bg))
            painter.setPen(QPen(QColor(border), 1))
            painter.drawRect(rect)

            if self._closable:
                sep = self._separator_rect()
                if not sep.isNull():
                    painter.fillRect(sep, QColor(border))

            font = self.font()
            font.setBold(selected)
            painter.setFont(font)
            fm = QFontMetrics(font)
            text_rect = self._text_rect()
            elided = fm.elidedText(str(getattr(self, "_full_text", "") or ""), Qt.TextElideMode.ElideMiddle, max(8, text_rect.width()))
            painter.setPen(QPen(QColor(fg)))
            painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, elided)

            if self._closable:
                close_rect = self._close_rect()
                close_font = QFont(font)
                close_font.setBold(True)
                close_font.setPointSize(max(8, font.pointSize() + 1 if font.pointSize() > 0 else 10))
                painter.setFont(close_font)
                painter.setPen(QPen(QColor(close_fg)))
                # 글리프가 폰트에 따라 아래로 처져 보이는 것을 줄이기 위해 텍스트 박스를 1px 위로 보정한다.
                painter.drawText(close_rect.adjusted(0, -1, 0, -1), Qt.AlignmentFlag.AlignCenter, "×")
        finally:
            painter.end()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self.update()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self._press_pos = event.position().toPoint()
            self._press_on_close = self._closable and self._close_rect().contains(self._press_pos)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event):
        if self._press_on_close:
            event.accept()
            return
        if not (event.buttons() & Qt.MouseButton.LeftButton):
            return super().mouseMoveEvent(event)
        if self._press_pos is None:
            return super().mouseMoveEvent(event)
        if (event.position().toPoint() - self._press_pos).manhattanLength() < QApplication.startDragDistance():
            return super().mouseMoveEvent(event)

        drag = QDrag(self)
        mime = QMimeData()
        mime.setData("application/x-ysb-page-tab-index", str(self.index).encode("utf-8"))
        drag.setMimeData(mime)
        self.tab_bar.start_tab_drag()
        try:
            drag.exec(Qt.DropAction.MoveAction)
        finally:
            self.tab_bar.stop_tab_drag()

    def mouseReleaseEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if self._press_on_close and self._closable and self._close_rect().contains(pos):
                self.tab_bar.request_close(self.index)
                event.accept()
                return
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            try:
                self.tab_bar.activate_tab_from_mouse(self.index, event.modifiers())
            except Exception:
                self.tab_bar.setCurrentIndex(self.index)
            event.accept()
            return
        super().mouseReleaseEvent(event)

    def mouseDoubleClickEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            pos = event.position().toPoint()
            if self._closable and self._close_rect().contains(pos):
                event.accept()
                return
            self.setFocus(Qt.FocusReason.MouseFocusReason)
            self.tab_bar.setCurrentIndex(self.index)
            self.tab_bar.request_rename(self.index)
            event.accept()
            return
        super().mouseDoubleClickEvent(event)

    def dragEnterEvent(self, event):
        if self.tab_bar.handle_tab_drag_enter(event):
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self.tab_bar.handle_tab_drag_move(event, self):
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self.tab_bar.handle_tab_drop(event, self):
            return
        super().dropEvent(event)


class ScrollablePageTabBar(QWidget):
    currentChanged = pyqtSignal(int)
    tabCloseRequested = pyqtSignal(int)
    tabMoved = pyqtSignal(int, int)
    tabRenameRequested = pyqtSignal(int)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._tabs = []
        self._current = -1
        self._tabs_closable = True
        self._movable = True
        self._selected_indices = set()
        self._selection_anchor = -1
        self._light_theme = False
        self._style_tokens = {}
        self._drag_scroll_direction = 0
        self._drag_scroll_margin = 34
        self._drag_scroll_step = 22

        self.setAcceptDrops(True)
        self.setFixedHeight(28)

        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        self.scroll = QScrollArea(self)
        self.scroll.setWidgetResizable(False)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.scroll.setFixedHeight(28)
        self.scroll.viewport().setAcceptDrops(True)
        self.scroll.viewport().installEventFilter(self)

        self.content_widget = QWidget()
        self.content_layout = QHBoxLayout(self.content_widget)
        self.content_layout.setContentsMargins(0, 0, 0, 0)
        self.content_layout.setSpacing(7)
        self.content_widget.setFixedHeight(28)
        self.content_widget.setAcceptDrops(True)
        self.content_widget.installEventFilter(self)

        self.drop_indicator = QFrame(self.content_widget)
        self.drop_indicator.setObjectName("PageTabDropIndicator")
        self.drop_indicator.setFixedSize(12, 28)
        self.drop_indicator.hide()
        self._drop_indicator_index = None

        self.scroll.setWidget(self.content_widget)
        layout.addWidget(self.scroll, 1)

        self.rename_shortcut = QShortcut(QKeySequence("F2"), self)
        self.rename_shortcut.setContext(Qt.ShortcutContext.WidgetWithChildrenShortcut)
        self.rename_shortcut.activated.connect(lambda: self.request_rename(self._current))

        self._auto_scroll_timer = QTimer(self)
        self._auto_scroll_timer.setInterval(35)
        self._auto_scroll_timer.timeout.connect(self._perform_drag_auto_scroll)

    def setExpanding(self, value): pass
    def setDrawBase(self, value): pass
    def setUsesScrollButtons(self, value): pass
    def setElideMode(self, value): pass

    def setMovable(self, value):
        self._movable = bool(value)

    def setTabsClosable(self, value):
        self._tabs_closable = bool(value)
        for tab in self._tabs:
            try:
                tab.set_closable(self._tabs_closable)
            except Exception:
                pass
        self._update_content_width()

    def count(self):
        return len(self._tabs)

    def addTab(self, text):
        index = len(self._tabs)
        tab = PageTabButton(self, index, text)
        self._tabs.append(tab)
        self.content_layout.addWidget(tab)
        self._update_indices()
        self._apply_tab_style(index)
        return index

    def removeTab(self, index):
        try:
            index = int(index)
        except Exception:
            return
        if index < 0 or index >= len(self._tabs):
            return
        tab = self._tabs.pop(index)
        self.content_layout.removeWidget(tab)
        tab.deleteLater()
        self._selected_indices = {i - 1 if i > index else i for i in self._selected_indices if i != index}
        self._selected_indices = {i for i in self._selected_indices if 0 <= i < len(self._tabs)}
        if self._selection_anchor == index:
            self._selection_anchor = self._current
        elif self._selection_anchor > index:
            self._selection_anchor -= 1
        if self._current == index:
            self._current = min(index, len(self._tabs) - 1)
        elif self._current > index:
            self._current -= 1
        if self._current >= 0 and not self._selected_indices:
            self._selected_indices = {self._current}
        self._update_indices()
        self.apply_theme(self._light_theme)
        self._update_content_width()

    def setTabText(self, index, text):
        if 0 <= int(index) < len(self._tabs):
            self._tabs[int(index)].set_text(text)
            self._update_content_width()

    def setTabToolTip(self, index, text):
        # Page tabs should not show tooltips. Ignore all tooltip text requests.
        if 0 <= int(index) < len(self._tabs):
            try:
                self._tabs[int(index)].setToolTip("")
            except Exception:
                pass

    def tabRect(self, index):
        if 0 <= int(index) < len(self._tabs):
            tab = self._tabs[int(index)]
            pos = tab.mapTo(self, QPoint(0, 0))
            return QRect(pos, tab.size())
        return QRect()

    def currentIndex(self):
        return self._current

    def selectedIndices(self):
        return sorted(i for i in self._selected_indices if 0 <= int(i) < len(self._tabs))

    def setSelectedIndices(self, indices):
        old = set(getattr(self, "_selected_indices", set()))
        clean = set()
        for raw in indices or []:
            try:
                i = int(raw)
            except Exception:
                continue
            if 0 <= i < len(self._tabs):
                clean.add(i)
        if not clean and 0 <= self._current < len(self._tabs):
            clean.add(self._current)
        self._selected_indices = clean
        if clean:
            self._selection_anchor = sorted(clean)[-1]
        for i in sorted(old | clean):
            self._apply_tab_style(i, force=True)

    def clearSelection(self, keep_current=True):
        old = set(getattr(self, "_selected_indices", set()))
        if keep_current and 0 <= self._current < len(self._tabs):
            self._selected_indices = {self._current}
            self._selection_anchor = self._current
        else:
            self._selected_indices = set()
            self._selection_anchor = -1
        for i in sorted(old | self._selected_indices):
            self._apply_tab_style(i, force=True)

    def activate_tab_from_mouse(self, index, modifiers=None):
        try:
            index = int(index)
        except Exception:
            return
        if index < 0 or index >= len(self._tabs):
            return
        mods = modifiers or Qt.KeyboardModifier.NoModifier
        old_selected = set(getattr(self, "_selected_indices", set()))
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        if shift:
            anchor = self._selection_anchor if 0 <= self._selection_anchor < len(self._tabs) else (self._current if 0 <= self._current < len(self._tabs) else index)
            start, end = sorted((anchor, index))
            rng = set(range(start, end + 1))
            if ctrl:
                self._selected_indices = set(self._selected_indices) | rng
            else:
                self._selected_indices = rng
        elif ctrl:
            self._selection_anchor = index
            if index in self._selected_indices and len(self._selected_indices) > 1:
                self._selected_indices.remove(index)
            else:
                self._selected_indices.add(index)
        else:
            self._selection_anchor = index
            self._selected_indices = {index}
        self.setCurrentIndex(index, preserve_selection=True)
        for i in sorted(old_selected | self._selected_indices | {index}):
            self._apply_tab_style(i, force=True)

    def setCurrentIndex(self, index, preserve_selection=False):
        try:
            index = int(index)
        except Exception:
            return
        if index < 0 or index >= len(self._tabs):
            self._current = -1 if not self._tabs else max(0, min(index, len(self._tabs)-1))
            self._selected_indices = set() if self._current < 0 else {self._current}
            self._selection_anchor = self._current
            self.apply_theme(self._light_theme)
            return
        old = self._current
        old_selected = set(getattr(self, "_selected_indices", set()))
        self._current = index
        if not preserve_selection:
            self._selected_indices = {index}
            self._selection_anchor = index
        # 탭 전환 최적화: 전체 탭 재도색 금지. 이전/현재/선택 탭만 갱신한다.
        for i in sorted({old, index} | old_selected | set(self._selected_indices)):
            if 0 <= i < len(self._tabs):
                self._apply_tab_style(i, force=True)
        if index != old and not self.signalsBlocked():
            self.currentChanged.emit(index)

    def request_close(self, index):
        if not self.signalsBlocked():
            self.tabCloseRequested.emit(int(index))

    def request_rename(self, index):
        try:
            index = int(index)
        except Exception:
            return
        if index < 0 or index >= len(self._tabs):
            return
        if not self.signalsBlocked():
            self.tabRenameRequested.emit(index)

    def moveTab(self, from_index, to_index, emit_signal=True):
        try:
            from_index = int(from_index); to_index = int(to_index)
        except Exception:
            return
        if from_index == to_index:
            return
        if from_index < 0 or to_index < 0 or from_index >= len(self._tabs) or to_index >= len(self._tabs):
            return

        sb = self.scroll.horizontalScrollBar()
        drop_scroll = sb.value()

        selected_before = set(getattr(self, "_selected_indices", set()))
        anchor_before = getattr(self, "_selection_anchor", -1)
        order = list(range(len(self._tabs)))
        moved_value = order.pop(from_index)
        order.insert(to_index, moved_value)
        old_to_new = {old_i: new_i for new_i, old_i in enumerate(order)}

        tab = self._tabs.pop(from_index)
        self._tabs.insert(to_index, tab)
        self.content_layout.removeWidget(tab)
        self.content_layout.insertWidget(to_index, tab)
        self._selected_indices = {old_to_new.get(i, i) for i in selected_before if i in old_to_new}
        self._selection_anchor = old_to_new.get(anchor_before, anchor_before)

        if self._current == from_index:
            self._current = to_index
        elif from_index < self._current <= to_index:
            self._current -= 1
        elif to_index <= self._current < from_index:
            self._current += 1

        self._update_indices()
        self._update_content_width()
        # 드래그해서 놓은 위치가 정위치다.
        # 레이아웃 재계산 뒤에도 드롭 순간의 현재 스크롤 시점을 유지한다.
        try:
            QTimer.singleShot(0, lambda v=drop_scroll: self.scroll.horizontalScrollBar().setValue(
                max(self.scroll.horizontalScrollBar().minimum(), min(self.scroll.horizontalScrollBar().maximum(), int(v)))
            ))
        except Exception:
            pass
        self.apply_theme(self._light_theme)
        if emit_signal and not self.signalsBlocked():
            self.tabMoved.emit(from_index, to_index)

    def _update_indices(self):
        for i, tab in enumerate(self._tabs):
            tab.index = i
            try:
                tab.set_closable(self._tabs_closable)
            except Exception:
                pass
        self._update_content_width()

    def _update_content_width(self):
        total = 0
        spacing = int(self.content_layout.spacing())
        for tab in self._tabs:
            # PageTabButton already computes and fixes its own visible width.
            # Do not use sizeHint() here: QLabel's full text sizeHint can be
            # wider than the elided tab, which creates dark unused gutters
            # between tabs inside the scroll content area.
            total += int(tab.width())
        if self._tabs:
            total += max(0, len(self._tabs) - 1) * spacing
        try:
            if hasattr(self, "drop_indicator") and self.drop_indicator.isVisible():
                total += self.drop_indicator.width() + spacing
        except Exception:
            pass
        total = max(1, total)
        self.content_widget.setFixedWidth(total)
        self.content_widget.setFixedHeight(28)

    def _theme_tokens(self):
        if self._light_theme:
            return {
                "bar_bg": "#F1ECEF",
                "normal_bg": "#ffffff",
                "normal_fg": "#555056",
                "normal_border": "#D1C9CE",
                "selected_bg": "#F5E8EA",
                "selected_fg": "#111827",
                "selected_border": "#C78A90",
                "hover_bg": "#FBF5F6",
                "close_fg": "#555056",
            }
        return {
            "bar_bg": "#211F23",
            "normal_bg": "#2B282D",
            "normal_fg": "#BDB6BB",
            "normal_border": "#3A363B",
            "selected_bg": "#5B3136",
            "selected_fg": "#ffffff",
            "selected_border": "#C78A90",
            "hover_bg": "#3A343A",
            "close_fg": "#D7D2D5",
        }

    def _apply_tab_style(self, index, force=False):
        if not (0 <= int(index) < len(self._tabs)):
            return
        tab = self._tabs[int(index)]
        selected = int(index) == int(self._current) or int(index) in getattr(self, "_selected_indices", set())
        tokens = self._theme_tokens()
        key = (
            bool(self._light_theme),
            bool(selected),
            self._tabs_closable,
            tokens.get("normal_bg"),
            tokens.get("selected_bg"),
        )
        if not force and getattr(tab, "_last_style_key", None) == key:
            return
        tab._last_style_key = key

        # PageTabButton은 QLabel/QToolButton 자식 위젯에 의존하지 않고 직접 그린다.
        # 이전 방식은 Windows/QSS 조합에 따라 닫기 x가 사라지거나 텍스트가 버튼 영역을 침범했다.
        try:
            tab.set_visual_state(selected=selected, tokens=tokens)
        except Exception:
            tab.update()

    def apply_theme(self, light, force=False):
        new_light = bool(light)
        if not force and new_light == self._light_theme and self._style_tokens:
            # 테마가 바뀌지 않았으면 전체 재도색을 피한다.
            for i in range(len(self._tabs)):
                self._apply_tab_style(i)
            return
        self._light_theme = new_light
        self._style_tokens = self._theme_tokens()
        bg = self._style_tokens["bar_bg"]
        self.setStyleSheet(f"ScrollablePageTabBar {{ background:{bg}; border:0px; }}")
        self.scroll.setStyleSheet(f"QScrollArea {{ background:{bg}; border:0px; }}")
        self.content_widget.setStyleSheet(f"QWidget {{ background:{bg}; }}")
        for tab in self._tabs:
            tab._last_style_key = None
        self.update_drop_indicator_style()
        for i in range(len(self._tabs)):
            self._apply_tab_style(i, force=True)

    def update_drop_indicator_style(self):
        try:
            if self._light_theme:
                self.drop_indicator.setStyleSheet(
                    "QFrame#PageTabDropIndicator { background:#9bbce8; border:1px solid #A85D66; border-radius:0px; }"
                )
            else:
                self.drop_indicator.setStyleSheet(
                    "QFrame#PageTabDropIndicator { background:#C78A90; border:1px solid #C78A90; border-radius:0px; }"
                )
        except Exception:
            pass

    def show_drop_indicator(self, insertion_index):
        if not hasattr(self, "drop_indicator"):
            return
        try:
            insertion_index = max(0, min(int(insertion_index), len(self._tabs)))
        except Exception:
            insertion_index = len(self._tabs)
        if self._drop_indicator_index == insertion_index and self.drop_indicator.isVisible():
            return
        try:
            self.content_layout.removeWidget(self.drop_indicator)
        except Exception:
            pass
        self._drop_indicator_index = insertion_index
        self.update_drop_indicator_style()
        self.content_layout.insertWidget(insertion_index, self.drop_indicator)
        self.drop_indicator.show()
        self._update_content_width()

    def hide_drop_indicator(self):
        if not hasattr(self, "drop_indicator"):
            return
        try:
            self.content_layout.removeWidget(self.drop_indicator)
        except Exception:
            pass
        try:
            self.drop_indicator.hide()
        except Exception:
            pass
        self._drop_indicator_index = None
        self._update_content_width()

    def drop_insertion_index_at_content_pos(self, pos):
        if not self._tabs:
            return 0
        x = pos.x()
        if x <= 0:
            return 0
        for i, tab in enumerate(self._tabs):
            geo = tab.geometry()
            if x < geo.center().x():
                return i
        return len(self._tabs)

    def insertion_index_to_move_index(self, from_index, insertion_index):
        if not self._tabs:
            return -1
        n = len(self._tabs)
        try:
            from_index = int(from_index)
            insertion_index = int(insertion_index)
        except Exception:
            return -1
        insertion_index = max(0, min(insertion_index, n))
        if insertion_index > from_index:
            target = insertion_index - 1
        else:
            target = insertion_index
        return max(0, min(target, n - 1))

    def owner_window(self):
        try:
            w = self.window()
            if w is not None and hasattr(w, "normalize_image_drop_paths"):
                return w
        except Exception:
            pass
        try:
            p = self.parent()
            for _ in range(8):
                if p is None:
                    break
                if hasattr(p, "normalize_image_drop_paths"):
                    return p
                p = p.parent()
        except Exception:
            pass
        return None

    def image_paths_from_mime(self, mime):
        out = []
        try:
            if mime is None or not mime.hasUrls():
                return out
            owner = self.owner_window()
            raw = []
            for url in mime.urls():
                try:
                    if url.isLocalFile():
                        raw.append(url.toLocalFile())
                except Exception:
                    pass
            if owner is not None and hasattr(owner, "normalize_image_drop_paths"):
                return owner.normalize_image_drop_paths(raw)
            for p in raw:
                if str(p).lower().endswith(IMAGE_DROP_EXTS):
                    out.append(p)
        except Exception:
            pass
        return out

    def tab_gap_insertion_index_at_content_pos(self, pos, threshold=34):
        """외부 이미지 파일을 탭 사이에 넣을 수 있는지 판정한다.

        - 탭 사이/양끝/탭 경계 근처에서는 삽입 위치를 반환하고 인디케이터를 띄운다.
        - 탭의 중앙부처럼 '사이'가 아닌 곳은 None을 반환해 현재 페이지 뒤 삽입으로 fallback한다.
        """
        if not self._tabs:
            return 0
        x = pos.x()
        if x <= 0:
            return 0

        first = self._tabs[0].geometry()
        if x <= first.left() + threshold:
            return 0

        for i, tab in enumerate(self._tabs):
            geo = tab.geometry()
            tab_w = max(1, geo.width())
            edge_zone = max(threshold, min(46, int(tab_w * 0.28)))

            if x <= geo.left() + edge_zone and x >= geo.left() - threshold:
                return i
            if x >= geo.right() - edge_zone and x <= geo.right() + threshold:
                return i + 1

            if i < len(self._tabs) - 1:
                nxt = self._tabs[i + 1].geometry()
                if geo.right() < x < nxt.left():
                    return i + 1
                boundary = (geo.right() + nxt.left()) // 2
                if abs(x - boundary) <= threshold:
                    return i + 1

        last = self._tabs[-1].geometry()
        if x >= last.right() - max(threshold, min(46, int(max(1, last.width()) * 0.28))):
            return len(self._tabs)
        return None

    def handle_tab_drag_enter(self, event):
        try:
            if event.mimeData().hasFormat("application/x-ysb-page-tab-index"):
                event.acceptProposedAction()
                return True
            # 외부 이미지 드래그는 탭바에서 가로채지 않고 MainWindow로 넘긴다.
            if self.image_paths_from_mime(event.mimeData()):
                event.ignore()
                return False
        except Exception:
            pass
        return False

    def handle_tab_drag_move(self, event, obj):
        try:
            if event.mimeData().hasFormat("application/x-ysb-page-tab-index"):
                self._update_drag_auto_scroll(obj, event.position().toPoint())
                content_pos = self.content_pos_from_drag_event(obj, event.position().toPoint())
                self.show_drop_indicator(self.drop_insertion_index_at_content_pos(content_pos))
                event.acceptProposedAction()
                return True

            # 외부 이미지 파일 드래그는 탭 사이 삽입을 하지 않는다.
            # 인디케이터는 탭 자체 순서 변경에만 사용하고,
            # 이미지 드롭은 MainWindow의 기본 드롭 처리(현재 페이지 뒤 삽입)에 맡긴다.
            if self.image_paths_from_mime(event.mimeData()):
                self.hide_drop_indicator()
                event.ignore()
                return False
        except Exception:
            pass
        return False

    def content_pos_from_drag_event(self, obj, pos):
        try:
            if obj is self.scroll.viewport():
                return self.scroll.viewport().mapTo(self.content_widget, pos)
            if obj is self.content_widget:
                return pos
            if obj is self:
                return self.mapTo(self.content_widget, pos)
            if isinstance(obj, QWidget):
                return obj.mapTo(self.content_widget, pos)
        except Exception:
            pass
        return pos

    def handle_tab_drop(self, event, obj):
        try:
            if event.mimeData().hasFormat("application/x-ysb-page-tab-index"):
                self.stop_tab_drag()
                try:
                    from_index = int(bytes(event.mimeData().data("application/x-ysb-page-tab-index")).decode("utf-8"))
                except Exception:
                    return True

                content_pos = self.content_pos_from_drag_event(obj, event.position().toPoint())
                insertion_index = self.drop_insertion_index_at_content_pos(content_pos)
                to_index = self.insertion_index_to_move_index(from_index, insertion_index)
                self.hide_drop_indicator()
                if to_index >= 0:
                    self.moveTab(from_index, to_index, emit_signal=True)
                event.acceptProposedAction()
                return True

            image_paths = self.image_paths_from_mime(event.mimeData())
            if image_paths:
                self.hide_drop_indicator()
                # 외부 이미지 파일은 페이지탭이 직접 처리하지 않는다.
                # 상위 MainWindow 드롭 처리로 넘겨 현재 페이지 뒤 삽입 원칙을 유지한다.
                return False

            return False
        except Exception:
            try:
                event.acceptProposedAction()
            except Exception:
                pass
            return True

    def dragEnterEvent(self, event):
        if self.handle_tab_drag_enter(event):
            return
        super().dragEnterEvent(event)

    def dragMoveEvent(self, event):
        if self.handle_tab_drag_move(event, self):
            return
        super().dragMoveEvent(event)

    def dropEvent(self, event):
        if self.handle_tab_drop(event, self):
            return
        super().dropEvent(event)

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.DragEnter:
            if self.handle_tab_drag_enter(event):
                return True
        if event.type() == QEvent.Type.DragLeave:
            self.stop_tab_drag()
            return False
        if event.type() == QEvent.Type.DragMove:
            if self.handle_tab_drag_move(event, obj):
                return True
        if event.type() == QEvent.Type.Drop:
            if self.handle_tab_drop(event, obj):
                return True
        return super().eventFilter(obj, event)

    def start_tab_drag(self):
        self._drag_scroll_direction = 0

    def stop_tab_drag(self):
        self._drag_scroll_direction = 0
        try:
            self._auto_scroll_timer.stop()
        except Exception:
            pass
        try:
            self.hide_drop_indicator()
        except Exception:
            pass

    def _update_drag_auto_scroll(self, obj, pos):
        try:
            if obj is self.scroll.viewport():
                viewport_pos = pos
            else:
                viewport_pos = obj.mapTo(self.scroll.viewport(), pos)
            x = viewport_pos.x()
            w = self.scroll.viewport().width()
            if x < self._drag_scroll_margin:
                self._drag_scroll_direction = -1
            elif x > w - self._drag_scroll_margin:
                self._drag_scroll_direction = 1
            else:
                self._drag_scroll_direction = 0
            if self._drag_scroll_direction:
                if not self._auto_scroll_timer.isActive():
                    self._auto_scroll_timer.start()
            else:
                self._auto_scroll_timer.stop()
        except Exception:
            self.stop_tab_drag()

    def _perform_drag_auto_scroll(self):
        if not self._drag_scroll_direction:
            return
        try:
            sb = self.scroll.horizontalScrollBar()
            old = sb.value()
            new_value = max(sb.minimum(), min(sb.maximum(), old + self._drag_scroll_direction * self._drag_scroll_step))
            if new_value == old:
                return
            sb.setValue(new_value)
        except Exception:
            self.stop_tab_drag()

    def index_at_content_pos(self, pos):
        if not self._tabs:
            return -1
        x = pos.x()
        if x <= 0:
            return 0
        for i, tab in enumerate(self._tabs):
            geo = tab.geometry()
            if x < geo.center().x():
                return i
        return len(self._tabs) - 1

    def scroll_step(self, direction):
        if not self._tabs:
            return False
        sb = self.scroll.horizontalScrollBar()
        view_w = self.scroll.viewport().width()
        cur = sb.value()
        left_edge = cur
        right_edge = cur + max(0, view_w - 1)

        visible = []
        full = []
        for i, tab in enumerate(self._tabs):
            x = tab.x()
            r = x + tab.width() - 1
            if r >= left_edge and x <= right_edge:
                visible.append(i)
                if x >= left_edge and r <= right_edge:
                    full.append(i)

        if not visible:
            target = 0 if direction < 0 else len(self._tabs) - 1
        elif direction > 0:
            edge = max(visible)
            if edge not in full:
                target = edge
            else:
                target = min(edge + 1, len(self._tabs) - 1)
        else:
            edge = min(visible)
            if edge not in full:
                target = edge
            else:
                target = max(edge - 1, 0)

        tab = self._tabs[target]
        if direction > 0:
            new_value = tab.x() + tab.width() - view_w
        else:
            new_value = tab.x()
        new_value = max(sb.minimum(), min(sb.maximum(), int(new_value)))
        sb.setValue(new_value)
        return True




class OutputCleanupDialog(QDialog):
    """프로젝트 산출물 삭제 옵션 창."""

    def __init__(self, counts=None, parent=None):
        super().__init__(parent)
        self.counts = counts or {}
        self.setWindowTitle("출력물 삭제")
        self.setModal(True)
        self.setMinimumWidth(420)

        layout = QVBoxLayout(self)

        title = QLabel("삭제할 출력물을 선택하세요.")
        title.setStyleSheet("font-size:15px;font-weight:bold;")
        layout.addWidget(title)

        desc = QLabel(
            "현재 프로젝트의 출력 폴더에서 선택한 산출물만 삭제합니다.\n"
            "원본 이미지, 프로젝트 데이터, 마스크, 번역 데이터는 삭제하지 않습니다."
        )
        desc.setWordWrap(True)
        layout.addWidget(desc)

        self.cb_result = QCheckBox(f"최종결과 이미지  ({self.counts.get('result', 0)}개)")
        self.cb_script = QCheckBox(f"포토샵 스크립트  ({self.counts.get('script', 0)}개)")
        self.cb_txt = QCheckBox(f"TXT 지문  ({self.counts.get('txt', 0)}개)")

        # 삭제 기능이라 기본은 모두 해제. 사용자가 직접 고르게 한다.
        self.cb_result.setChecked(False)
        self.cb_script.setChecked(False)
        self.cb_txt.setChecked(False)

        for cb in (self.cb_result, self.cb_script, self.cb_txt):
            cb.stateChanged.connect(self.update_delete_enabled)
            layout.addWidget(cb)

        btn_row = QHBoxLayout()
        btn_row.addStretch(1)
        self.btn_delete = QPushButton("삭제")
        self.btn_delete.setMinimumWidth(96)
        self.btn_delete.clicked.connect(self.accept)
        self.btn_cancel = QPushButton("취소")
        self.btn_cancel.setMinimumWidth(96)
        self.btn_cancel.clicked.connect(self.reject)
        btn_row.addWidget(self.btn_delete)
        btn_row.addWidget(self.btn_cancel)
        layout.addLayout(btn_row)

        self.update_delete_enabled()

    def update_delete_enabled(self):
        self.btn_delete.setEnabled(any(self.selected().values()))

    def selected(self):
        return {
            "result": bool(self.cb_result.isChecked()),
            "script": bool(self.cb_script.isChecked()),
            "txt": bool(self.cb_txt.isChecked()),
        }





class EditorSplitterHandle(QSplitterHandle):
    """좌우 작업 영역 splitter handle.

    더블클릭하면 오른쪽 작업 패널 폭을 기본/숨김 2단 상태로 순환한다.
    오른쪽/왼쪽 패널 자체는 사용자가 거의 끝까지 접을 수 있게 둔다.
    """

    def mouseDoubleClickEvent(self, event):
        splitter = self.splitter()
        if hasattr(splitter, "cycle_right_panel_snap_width"):
            splitter.cycle_right_panel_snap_width()
            event.accept()
            return
        if hasattr(splitter, "reset_to_default_right_panel_width"):
            splitter.reset_to_default_right_panel_width()
            event.accept()
            return
        super().mouseDoubleClickEvent(event)


class EditorSplitter(QSplitter):
    """메인 이미지 뷰어와 우측 작업 패널을 나누는 splitter."""

    SNAP_DEFAULT = 0
    SNAP_ORIGINAL_ONLY = 1
    SNAP_HIDDEN = 2
    SNAP_CUSTOM = -1

    def __init__(self, orientation, parent=None, default_right_width=700):
        super().__init__(orientation, parent)
        self.default_right_width = int(default_right_width)
        # 더블클릭 순환 상태. 사용자가 직접 드래그하면 custom으로 돌리고,
        # custom 상태에서 다시 더블클릭하면 기본 정위치부터 시작한다.
        self._right_panel_snap_state = self.SNAP_CUSTOM
        self._right_panel_snap_applying = False
        try:
            self.splitterMoved.connect(self._mark_right_panel_snap_custom)
        except Exception:
            pass

    def createHandle(self):
        return EditorSplitterHandle(self.orientation(), self)

    def _mark_right_panel_snap_custom(self, *_args):
        if getattr(self, "_right_panel_snap_applying", False):
            return
        self._right_panel_snap_state = self.SNAP_CUSTOM

    def _available_splitter_width(self):
        sizes = self.sizes()
        total = sum(max(0, int(v)) for v in sizes)
        if total <= 0:
            total = max(0, int(self.width()) - max(0, (self.count() - 1) * int(self.handleWidth())))
        return max(0, int(total))

    def _apply_right_panel_width(self, right_width, state=None):
        if self.count() < 2:
            return
        total = self._available_splitter_width()
        if total <= 0:
            return
        right = max(0, min(int(right_width), total))
        left = max(0, total - right)
        self._right_panel_snap_applying = True
        try:
            self.setSizes([left, right])
        finally:
            self._right_panel_snap_applying = False
        if state is not None:
            self._right_panel_snap_state = int(state)

    def _right_panel_width_for_snap_state(self, state):
        total = self._available_splitter_width()
        if total <= 0:
            return 0
        if state == self.SNAP_ORIGINAL_ONLY:
            # 원문만 보기 좋은 폭. 너무 과하게 잘리지 않도록 기존보다 더 넓게 잡아,
            # 원문 리스트와 상단 기본 조작 영역이 답답하지 않게 보이게 한다.
            return min(max(380, int(self.default_right_width * 0.62)), total)
        if state == self.SNAP_HIDDEN:
            # 완전 숨김에 가까운 상태. splitter handle은 남겨 다시 열 수 있게 한다.
            return 0
        # 기본 정위치.
        return min(max(0, int(self.default_right_width)), total)

    def cycle_right_panel_snap_width(self):
        """오른쪽 작업 패널 폭을 기본 ↔ 숨김 2단으로 순환한다."""
        current = getattr(self, "_right_panel_snap_state", self.SNAP_CUSTOM)
        if current == self.SNAP_DEFAULT:
            next_state = self.SNAP_HIDDEN
        else:
            # 사용자 드래그(custom), 구형 원문만 보기 상태, 숨김 상태에서는 기본 폭으로 복귀한다.
            next_state = self.SNAP_DEFAULT
        self._apply_right_panel_width(self._right_panel_width_for_snap_state(next_state), state=next_state)

    def reset_to_default_right_panel_width(self):
        """오른쪽 패널이 사용자지정 콤보박스까지 보이는 기본 폭으로 복귀한다."""
        self._apply_right_panel_width(self._right_panel_width_for_snap_state(self.SNAP_DEFAULT), state=self.SNAP_DEFAULT)

    def set_right_panel_original_only_width(self):
        """오른쪽 패널을 원문만 보기 좋은 폭으로 맞춘다."""
        self._apply_right_panel_width(self._right_panel_width_for_snap_state(self.SNAP_ORIGINAL_ONLY), state=self.SNAP_ORIGINAL_ONLY)

    def hide_right_panel_width(self):
        """오른쪽 패널을 splitter handle만 남기는 수준으로 접는다."""
        self._apply_right_panel_width(self._right_panel_width_for_snap_state(self.SNAP_HIDDEN), state=self.SNAP_HIDDEN)


# Export all support names, including private-style helpers used by mixin methods.
__all__ = [name for name in globals() if not name.startswith("__")]
