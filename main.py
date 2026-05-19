import sys
import os
import shutil
import uuid
from pathlib import Path

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
from http.server import BaseHTTPRequestHandler, HTTPServer
from urllib.parse import urlparse, parse_qs
from datetime import datetime

import cv2
import numpy as np
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *
from PyQt6.QtNetwork import QLocalServer, QLocalSocket

from manga_engine import MangaProcessEngine, Config
from project_store import ProjectStore, PROJECT_FILENAME, YSB_EXTENSION, package_project, extract_ysb_package, read_ysb_manifest, safe_project_name, clean_workspace_name, unique_dir, unique_dir_with_code_suffix
from api_settings import ApiSettingsStore, ApiSettingsDialog, apply_settings_to_config
from shortcut_settings import ShortcutSettingsStore, ShortcutSettingsDialog, MacroSettingsDialog, TEXT_SYMBOLS, shortcut_label_map
from viewer import MuleImageViewer
from graphics_items import TypesettingItem, build_typesetting_text_path
from delegates import MultilineDelegate
from workers import UniversalBatchWorker, AnalysisWorker, InpaintWorker
from cache_utils import get_cache_dir, get_cache_file
from launcher import LauncherWidget, RecentProjectStore
from workspace_manager import get_workspace_root, temp_dir, workspaces_dir, default_package_dir, schedule_workspace_root_change, load_workspace_config, set_workspace_root, default_workspace_root, APP_FOLDER_NAME, configured_workspace_root_raw, configured_workspace_root_exists, app_config_dir


def resource_path(relative_path):
    """
    일반 실행 / PyInstaller --onedir / PyInstaller --onefile 모두에서
    포함 리소스 파일 경로를 안정적으로 찾는다.
    """
    if hasattr(sys, "_MEIPASS"):
        return str(Path(sys._MEIPASS) / relative_path)
    return str(Path(__file__).parent / relative_path)


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

# UI/log/message translation table is centralized in lang_text.py.
# Add new user-visible Korean/English strings there, not directly in this file.
from lang_text import UI_KO_EN, UI_EN_KO

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


def translate_ui_dynamic_text(text, lang=None):
    """고정 문구가 문장/로그 안에 섞여 있을 때 부분 치환한다.
    사용자 원문/번역문에는 사용하지 않고, UI/알림/로그용으로만 사용한다.
    """
    lang = normalize_ui_language(lang or current_ui_language())
    s = str(text)
    if lang == LANG_EN:
        for ko, en in sorted(UI_KO_EN.items(), key=lambda kv: len(kv[0]), reverse=True):
            if ko and ko in s:
                s = s.replace(ko, en)
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
        if en and en in s:
            s = s.replace(en, ko)
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


APP_VERSION = "v1.8.1"
APP_NAME_KO = "역식붕이 툴"
APP_NAME_EN = "YSB Tool"

YSBT_EXTENSION = ".ysbt"
YSBT_PROG_ID = "YSBTranslator.YSBTProject"
LEGACY_YSB_EXTENSION = ".ysb"
LEGACY_YSB_PROG_ID = "YSBTranslator.Project"

DARK_MESSAGEBOX_QSS = """
QMessageBox { background-color:#24272d; color:#f2f4f8; }
QMessageBox QLabel { color:#f2f4f8; line-height:1.35em; }
QMessageBox QPushButton {
    background-color:#30343d;
    color:#f2f4f8;
    border:1px solid #586173;
    border-radius:0px;
    padding:4px 10px;
    min-width:56px;
    min-height:22px;
}
QMessageBox QPushButton:hover { background-color:#3a404b; border-color:#74839a; }
QMessageBox QPushButton:pressed { background-color:#2b3038; }
QMessageBox QToolTip { background-color:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:0px; padding:5px; }
"""


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
        msg.setStyleSheet(DARK_MESSAGEBOX_QSS)
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
    msg.setStyleSheet(DARK_MESSAGEBOX_QSS)

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
    text = (
        f"{translate_ui_text('폴더 위치 변경으로 프로그램을 재기동합니다.\n취소할 시 이전 설정한 폴더 위치값으로 원복합니다.', lang)}\n\n"
        f"{translate_ui_text('현재 위치', lang)}:\n{current_path}\n\n"
        f"{translate_ui_text('변경 위치', lang)}:\n{target_path}"
    )
    msg = QMessageBox(parent)
    msg.setIcon(QMessageBox.Icon.Question)
    msg.setWindowTitle(title)
    msg.setText(text)
    msg.setStyleSheet(DARK_MESSAGEBOX_QSS)
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

    v1.8.1:
    - 가능하면 YSB_FileOpener.exe를 통해 재기동한다.
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
            launch_args = [str(Path(__file__).resolve())]
            app_dir = str(Path(__file__).resolve().parent)

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

    v1.8.1 opener patch:
    - YSB_FileOpener.exe가 있으면 파일 연결은 경량 런처를 우선 사용한다.
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


def get_association_icon() -> str:
    """파일 탐색기에 표시할 아이콘 위치."""
    if getattr(sys, "frozen", False):
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


def is_ysbt_file_association_registered_to_other_ysb() -> bool:
    """.ysbt가 역식붕이 툴 계열이지만 현재 실행 프로그램과 다른 명령을 가리키는지 확인한다.

    Windows가 버전 번호를 아는 것은 아니므로, 여기서 말하는 구버전 감지는
    실제로는 "등록된 실행 명령이 현재 실행 중인 프로그램과 다름"을 뜻한다.
    """
    if not is_ysbt_file_association_ours():
        return False
    registered = (get_registered_ysbt_file_association_command() or "").strip().lower()
    current = get_association_command().strip().lower()
    return bool(registered and registered != current)


def is_ysbt_file_association_registered() -> bool:
    """현재 사용자 계정의 .ysbt 연결이 현재 실행 중인 역식붕이 툴을 가리키는지 확인한다."""
    registered = get_registered_ysbt_file_association_command()
    if not registered:
        return False
    return registered.strip().lower() == get_association_command().strip().lower()


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
            QLineEdit { background-color: #2a2d33; color: #f2f2f2; border: 1px solid #555b66; padding: 4px; }
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

        try:
            current = Path(load_workspace_config().get("workspace_root") or get_workspace_root()).resolve()
            target_resolved = target.resolve()
        except Exception:
            current = Path(str(get_workspace_root()))
            target_resolved = target

        restart_needed = (not self.first_run) and (current != target_resolved)
        if restart_needed:
            if not workspace_restart_confirmation(self, current, target, self.ui_language):
                self.ed_path.setText(str(current))
                return

        # 언어 설정은 사용자가 확인/재기동 흐름을 승인한 뒤에만 저장한다.
        try:
            opts = load_app_options()
            opts[UI_LANGUAGE_KEY] = normalize_ui_language(getattr(self, "ui_language", LANG_KO))
            save_app_options(opts)
        except Exception:
            pass

        if not self._handle_association_choice():
            return

        try:
            if self.first_run:
                set_workspace_root(target)
                self.saved_workspace_root = str(target)
                QMessageBox.information(self, translate_ui_text("설정 완료", self.ui_language), f"{translate_ui_text('작업 폴더를 설정했습니다.', self.ui_language)}\n\n{target}")
            else:
                if restart_needed:
                    schedule_workspace_root_change(target)
                    self.saved_workspace_root = str(target)
                    self.accept()
                    restart_application_detached()
                    return
                else:
                    # 경로가 같으면 구조만 보장한다.
                    set_workspace_root(target)
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
            "time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
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
            "time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
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
FILE_OPENER_EXE_NAME = "YSBT Luncher.exe"
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
YSB_ROLE_OPENER = "YSB_FILE_OPENER"


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
            "time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
            "source": "main",
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


def is_ysb_opener_exe_by_metadata(exe_path: Path) -> bool:
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
    role_ok = role == YSB_ROLE_OPENER or internal == YSB_ROLE_OPENER
    return bool(family_ok and role_ok)


def get_file_opener_path() -> Path | None:
    """.ysbt 더블클릭 전용 경량 런처 경로를 반환한다.

    1순위는 EXE 버전 리소스 메타데이터다.
    - CompanyName: Zerostress8
    - ProductName: YSB Translator Tool
    - InternalName 또는 YSBAppRole: YSB_FILE_OPENER

    파일명이 바뀌어도 이 정보로 런처를 식별할 수 있다.
    """
    try:
        search_dirs = []
        if getattr(sys, "frozen", False):
            here = Path(sys.executable).resolve().parent
            self_exe = Path(sys.executable).resolve()
        else:
            here = Path(__file__).resolve().parent
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
                    if is_ysb_opener_exe_by_metadata(candidate):
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
            for launcher_name in (FILE_OPENER_EXE_NAME, "YSB_FileOpener.exe"):
                candidate = rd / launcher_name
                if candidate.exists():
                    return candidate

        if not getattr(sys, "frozen", False):
            candidate = Path(__file__).resolve().parent / "ysb_file_opener.py"
            return candidate if candidate.exists() else None

        # 3. 구버전/미표식 런처 fallback: 이름/크기 추정
        named = []
        small = []
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
                    low = candidate.name.lower()
                    try:
                        size = candidate.stat().st_size
                    except Exception:
                        size = 0
                    if size > 0 and size <= (30 * 1024 * 1024):
                        small.append((size, candidate))
                        if any(k in low for k in ("opener", "launcher", "open", "file")):
                            named.append((size, candidate))
            except Exception:
                continue

        if named:
            named.sort(key=lambda x: x[0])
            return named[0][1]
        if small:
            small.sort(key=lambda x: x[0])
            return small[0][1]
    except Exception:
        pass
    return None

# =========================================================
# 단일 실행 / .ysbt 더블클릭 전달
# =========================================================
SINGLE_INSTANCE_SERVER_NAME = "YSBTranslator_v15_single_instance"


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


class InlineTextEditItem(QGraphicsTextItem):
    """최종 화면에서 더블클릭으로 직접 수정하는 임시 텍스트 편집기."""

    def __init__(self, main_window, target_item, scene_rect):
        super().__init__()
        self.main_window = main_window
        self.target_item = target_item
        self._closing = False
        self._adjusting = False

        d = target_item.data
        self.original_text = str(d.get('translated_text', '') or '')
        self.align = (d.get('align') or 'center').lower()
        if self.align not in ('left', 'center', 'right'):
            self.align = 'center'

        # 편집기는 현재 보이는 실제 텍스트 bounds에서 시작한다.
        # 세로 기준은 top을 유지해서 사용자가 편집 중 텍스트가 튀어 보이지 않게 하고,
        # 완료 시에는 이 bounds 자체가 새 텍스트 영역이 된다.
        self.anchor_y = float(scene_rect.y())
        if self.align == 'right':
            self.anchor_x = float(scene_rect.right())
        elif self.align == 'center':
            self.anchor_x = float(scene_rect.center().x())
        else:
            self.anchor_x = float(scene_rect.x())

        self.document().setDocumentMargin(0)
        self.setZValue(5000)

        font = QFont(d.get('font_family') or main_window.cb_font.currentFont().family())
        font.setPixelSize(int(d.get('font_size', main_window.sb_font_size.value()) or main_window.sb_font_size.value()))
        self.setFont(font)

        color = QColor(str(d.get('text_color') or '#000000'))
        if not color.isValid():
            color = QColor('#000000')
        self.setDefaultTextColor(color)

        # 자동 줄내림으로 들어간 명시적 개행을 그대로 보존한다.
        self.setPlainText(self.original_text)
        self.apply_text_alignment()

        self.document().contentsChanged.connect(self.adjust_to_contents)
        self.adjust_to_contents()

        self.setTextInteractionFlags(Qt.TextInteractionFlag.TextEditorInteraction)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsFocusable, True)
        self.setFocus(Qt.FocusReason.MouseFocusReason)

    def apply_text_alignment(self):
        try:
            cursor = QTextCursor(self.document())
            cursor.select(QTextCursor.SelectionType.Document)
            block_format = QTextBlockFormat()
            if self.align == 'right':
                block_format.setAlignment(Qt.AlignmentFlag.AlignRight)
            elif self.align == 'center':
                block_format.setAlignment(Qt.AlignmentFlag.AlignCenter)
            else:
                block_format.setAlignment(Qt.AlignmentFlag.AlignLeft)
            cursor.mergeBlockFormat(block_format)
        except Exception:
            pass

    def _content_path_rect(self):
        """현재 편집 텍스트가 실제로 차지하는 타이트한 로컬 영역을 계산한다.

        QGraphicsTextItem.boundingRect()는 편집 커서/문서 여백/추가 줄 높이 때문에
        실제 글자보다 아래쪽이 한 줄 정도 더 남는 경우가 있다. 최종 식자 박스는
        TypesettingItem과 같은 QPainterPath 기준으로 다시 계산한다.
        """
        d = getattr(getattr(self, "target_item", None), "data", {}) or {}
        text = str(self.toPlainText() or "")
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        if not lines:
            lines = ['']

        font = QFont(self.font())
        try:
            font.setBold(bool(d.get('bold', False)))
            font.setItalic(bool(d.get('italic', False)))
            letter_spacing = int(d.get('letter_spacing', 0) or 0)
        except Exception:
            pass

        try:
            line_spacing_pct = max(50, min(300, int(d.get('line_spacing', 100) or 100)))
        except Exception:
            line_spacing_pct = 100
        try:
            char_width_pct = max(10, min(300, int(d.get('char_width', 100) or 100)))
        except Exception:
            char_width_pct = 100
        try:
            char_height_pct = max(10, min(300, int(d.get('char_height', 100) or 100)))
        except Exception:
            char_height_pct = 100

        fm = QFontMetrics(font)
        line_height = max(1, int(fm.lineSpacing() * (line_spacing_pct / 100.0)))
        align = getattr(self, 'align', 'center')
        path, _line_rects = build_typesetting_text_path(lines, font, align, line_height, letter_spacing)

        if char_width_pct != 100 or char_height_pct != 100:
            tr = QTransform()
            tr.scale(char_width_pct / 100.0, char_height_pct / 100.0)
            path = tr.map(path)

        rect = path.boundingRect()
        if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
            # 빈 텍스트/예외 상황용 최소 박스
            rect = QRectF(0, 0, 1, max(1, fm.height()))
        return rect

    def adjusted_scene_rect(self):
        # 실제 글자 path 기준으로 타이트한 rect를 반환한다.
        # 완료 후에는 이 rect 자체가 새 텍스트 영역이 된다.
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

    def adjust_to_contents(self):
        if self._adjusting:
            return
        self._adjusting = True
        try:
            text = self.toPlainText()
            lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
            if not lines:
                lines = ['']

            fm = QFontMetrics(self.font())
            max_w = 30.0
            for line in lines:
                max_w = max(max_w, float(fm.horizontalAdvance(line)))

            # 편집 중에는 실제 텍스트 자체의 가장 긴 줄 기준으로 영역이 실시간 확장된다.
            width = max_w + 8.0
            self.setTextWidth(width)

            if self.align == 'right':
                x = self.anchor_x - width
            elif self.align == 'center':
                x = self.anchor_x - width / 2.0
            else:
                x = self.anchor_x

            self.setPos(x, self.anchor_y)
            self.apply_text_alignment()
            self.update()
        finally:
            self._adjusting = False

    def paint(self, painter, option, widget=None):
        super().paint(painter, option, widget)
        pen = QPen(QColor(80, 160, 255), 1, Qt.PenStyle.DashLine)
        painter.setPen(pen)
        painter.setBrush(Qt.BrushStyle.NoBrush)
        painter.drawRect(self.boundingRect())

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Escape:
            self.main_window.finish_inline_text_edit(commit=False)
            event.accept()
            return
        if (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.main_window.finish_inline_text_edit(commit=True)
            event.accept()
            return
        super().keyPressEvent(event)

    def focusOutEvent(self, event):
        super().focusOutEvent(event)
        if getattr(self.main_window, "_app_is_closing", False):
            return
        if not self._closing:
            self.main_window.finish_inline_text_edit(commit=True)


class TextTableWidget(QTableWidget):
    """텍스트 행 드래그 순서 변경 감지용 테이블."""
    rowsReordered = pyqtSignal()

    def dropEvent(self, event):
        super().dropEvent(event)
        self.rowsReordered.emit()


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

    def tr_msg(self, text):
        return translate_ui_dynamic_text(text, self._ui_language)

    def refresh_preview(self):
        text = self.glossary_text or ""
        path = self.glossary_path or ""
        if text:
            path_text = path if path else self.tr_ui("캐시에만 저장됨")
            self.status_label.setText(f"{self.tr_ui("현재 단어장")}: {path_text}\n{self.tr_ui("글자 수")}: {len(text):,}")
            self.preview.setPlainText(text)
        else:
            self.status_label.setText(f"{self.tr_ui("현재 단어장")}: {self.tr_ui("없음")}")
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
            QMessageBox.critical(self, self.tr_ui("불러오기 실패"), f"{self.tr_ui("TXT 파일을 읽지 못했습니다:")}\n{e}")
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
            QMessageBox.critical(self, self.tr_ui("갱신 실패"), f"{self.tr_ui("TXT 파일을 다시 읽지 못했습니다:")}\n{e}")
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
        right_top.addWidget(style_label)
        right_top.addWidget(self.style_combo)
        top.addLayout(right_top, 1)

        root.addLayout(top)

        mid = QHBoxLayout()
        mid.setSpacing(12)

        left = QVBoxLayout()
        left.setSpacing(6)
        list_label = QLabel(translate_ui_text("글꼴 목록", self._ui_language), self)
        self.font_list = QListWidget(self)
        self.font_list.setToolTip(translate_ui_text("목록에서 글꼴을 선택합니다. 더블클릭하면 바로 적용합니다.", self._ui_language))
        self.font_list.itemSelectionChanged.connect(self.on_font_selection_changed)
        self.font_list.itemDoubleClicked.connect(lambda _item: self.accept())
        left.addWidget(list_label)
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

    def accept_by_enter(self):
        # 검색창/미리보기/스핀박스/목록 어디에 포커스가 있어도 Enter는 확인과 동일하게 처리한다.
        try:
            if self.size_spin is not None:
                self.size_spin.interpretText()
        except Exception:
            pass
        self.accept()

    def install_font_dialog_enter_accept(self):
        self._enter_accept_filter = EnterCommitFilter(parent_dialog=self, accept_dialog=True, parent=self)
        for _w in (self.search_edit, self.style_combo, self.font_list, self.preview_edit, self.size_spin):
            try:
                _w.installEventFilter(self._enter_accept_filter)
            except Exception:
                pass

        # 위 필터를 child 위젯이 먹지 못하는 경우 대비: 직접 시그널/단축키를 추가한다.
        try:
            self.search_edit.returnPressed.connect(self.accept_by_enter)
        except Exception:
            pass
        try:
            line = self.size_spin.lineEdit()
            if line is not None:
                line.installEventFilter(self._enter_accept_filter)
                line.returnPressed.connect(self.accept_by_enter)
        except Exception:
            pass

        for seq in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            try:
                sc = QShortcut(QKeySequence(seq), self)
                sc.setContext(Qt.ShortcutContext.ApplicationShortcut)
                sc.activated.connect(self.accept_by_enter)
                if not hasattr(self, "_enter_accept_shortcuts"):
                    self._enter_accept_shortcuts = []
                self._enter_accept_shortcuts.append(sc)
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
                    self.accept_by_enter()
                    event.accept()
                    return True
            except Exception:
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

    def setup_completer(self):
        try:
            completer = QCompleter(self.all_families, self)
            completer.setCaseSensitivity(Qt.CaseSensitivity.CaseInsensitive)
            try:
                completer.setFilterMode(Qt.MatchFlag.MatchContains)
            except Exception:
                pass
            completer.activated.connect(self.on_completer_activated)
            self.search_edit.setCompleter(completer)
            self.completer = completer
        except Exception:
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        # setup_ui() 도중 일부 도구 초기화가 log()를 호출할 수 있다.
        # 이 시점에는 아직 로그 위젯이 만들어지지 않았으므로 임시 버퍼에 보관한다.
        self._pending_log_messages = []
        self.update_window_title()
        self.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))
        self.resize(1600, 950)
        self.setAcceptDrops(True)

        self.api_settings = ApiSettingsStore.load()
        apply_settings_to_config(self.api_settings)
        self.engine = None
        self.restart_engine(show_error=False)

        self.paths = []
        self.idx = 0
        self.data = {}

        self.project_store = ProjectStore()
        self.project_dir = None
        self.workspace_root = str(get_workspace_root())
        self.ysbt_package_path = None
        self.suggested_project_name = None
        self.is_temp_project = False
        self.is_loading_project = False
        self.is_autosaving = False
        self._busy_counter = 0
        self._busy_reason_stack = []
        self._busy_widgets = []

        self.app_options = load_app_options()
        self.sync_translation_option_cache_to_config()
        self.sync_analysis_mask_options_to_config()

        # 저장본/작업 캐시 분리
        # auto_save_enabled=True  : 변경 즉시 실제 project.json에 저장
        # auto_save_enabled=False : 변경은 작업 캐시에만 저장하고, 프로젝트 저장 버튼으로만 확정
        self.auto_save_enabled = bool(self.app_options.get("auto_save_enabled", False))
        self.ui_theme = str(self.app_options.get(UI_THEME_KEY, THEME_DARK) or THEME_DARK).lower()
        if self.ui_theme not in (THEME_DARK, THEME_LIGHT):
            self.ui_theme = THEME_DARK
        self.ui_language = normalize_ui_language(self.app_options.get(UI_LANGUAGE_KEY, LANG_KO))
        self.analysis_number_box_width = int(self.app_options.get("analysis_number_box_width", 40) or 40)
        self.work_project_store = None
        self.work_project_dir = None
        self.has_unsaved_changes = False
        self._closing_confirmed = False
        # 종료 처리 중에는 focusOut/QTimer가 삭제된 QGraphicsScene에 접근하지 못하게 막는다.
        self._app_is_closing = False

        # 일괄 작업/페이지 로딩 중에는 화면에 남아 있는 마스크를
        # 현재 페이지 데이터에 자동 저장하면 안 된다.
        self.is_batch_running = False
        self.is_page_loading = False
        self.current_batch_mode = None

        self.inline_text_editor = None
        self.inline_text_target = None

        self.text_clipboard = []
        self.text_paste_pending = False
        self.last_canvas_context_pos = None

        self.last_mode = 0
        self._current_work_mode = 0
        self._global_event_filter_installed = False

        # 번역 묶음 수: 한 번의 API 요청에 몇 줄을 묶어 보낼지
        # 번역 API별로 따로 기억한다.
        self.trans_chunk_sizes = {
            "openai": 20,
            "deepseek": 8,
            "google": 50,
            "gemini": 10,
            "custom": 20,
        }

        self.default_text_color = "#000000"
        self.default_stroke_color = "#FFFFFF"
        self.default_line_spacing = 100
        self.default_letter_spacing = 0
        self.default_char_width = 100
        self.default_char_height = 100
        self.default_bold = False
        self.default_italic = False
        self.default_strike = False
        self.final_paint_color = "#FFFFFF"
        self.final_paint_above_text = False
        self.final_paint_opacity = 100
        self.default_align = "center"
        self.mask_toggle_enabled = False
        self.magic_wand_mask = None
        self.magic_wand_seed = None
        self.magic_wand_seeds = []
        self.magic_wand_history = []
        self._style_signal_lock = False
        self._preset_loading = False
        self._syncing_selection = False
        self._table_check_lock = False
        self.text_presets = {}

        self.shortcut_settings = ShortcutSettingsStore.load()
        self.actions = {}
        self.macro_actions = []
        self.item_preset_actions = []
        self.item_text_presets = {}
        self._item_preset_loading = False
        self._item_preset_signal_lock = False
        self.shortcut_label_map = shortcut_label_map()

        # 매크로 실행 큐
        # 비동기 작업(분석/인페인팅/일괄 작업)은 완료 콜백을 받아야 다음 단계로 넘어간다.
        self.macro_running = False
        self.macro_queue = []
        self.macro_current = None
        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current_name = ""
        self._suppress_project_undo = False
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_delayed_tooltip)
        self._tooltip_target = None
        self._tooltip_html = ""

        # 최종화면 텍스트 작업용 실행 취소 스택
        self.page_text_undo_stacks = {}
        # 표/화면 동기화 중에는 텍스트 undo 스냅샷을 만들지 않는다.
        self._text_undo_restore_lock = False
        # 자동저장 직전 화면의 텍스트 아이템 좌표를 data에 반영할 때 재진입을 막는다.
        self._text_scene_sync_lock = False

        # 전역 작업 되돌리기 스택.
        # 페이지/탭/줌/화면 이동/텍스트 편집처럼 여러 페이지를 오가며 생기는 작업을
        # 현재 페이지 전용 스택이 아니라 하나의 시간순 스택으로 관리한다.
        self.project_undo_stack = []
        self.project_redo_stack = []
        self._project_undo_restore_lock = False
        self._deferred_undo_records = {}
        # 매크로/글꼴 프리셋처럼 Undo 기록을 남기지 않는 작업은
        # 과거 Undo로 되돌아가면 상태가 꼬일 수 있으므로 Undo 경계를 세운다.
        self.undo_boundary = None
        self.macro_executed_any = False
        self.macro_has_undo_boundary = False
        self.macro_undo_record = None
        self._macro_allow_undo_append = False
        self.project_ui_view_states = {}

        self.setup_actions()
        self.setup_ui()
        self._last_show_final_text_checked = bool(self.cb_show_final_text.isChecked()) if hasattr(self, "cb_show_final_text") else True
        self._last_final_paint_above_text = bool(getattr(self, "final_paint_above_text", False))
        self.load_text_preset_cache()
        self.load_item_text_preset_cache()
        self.setup_menu()
        self.apply_theme(self.ui_theme)
        self.apply_shortcuts()
        self.apply_language(self.ui_language)
        self.install_global_input_filter()
        # 오래된 임시 작업 폴더는 한 달에 한 번 자동 정리한다.
        QTimer.singleShot(1500, self.auto_cleanup_temp_files_if_needed)

        # .ysbt 더블클릭 전용 경량 런처가 남긴 열기 요청을 감시한다.
        # 이미 켜진 앱에 파일 경로만 전달해 드래그앤드롭과 같은 빠른 열기를 구현한다.
        self.setup_external_open_queue_monitor()

    # =========================================================
    # 메뉴 / UI
    # =========================================================
    def showEvent(self, event):
        try:
            super().showEvent(event)
        finally:
            self.schedule_native_title_bar_theme(self, dark=not self.is_light_theme())

    def changeEvent(self, event):
        try:
            super().changeEvent(event)
        finally:
            try:
                if event.type() in (
                    QEvent.Type.WindowStateChange,
                    QEvent.Type.PaletteChange,
                    QEvent.Type.StyleChange,
                ):
                    self.schedule_native_title_bar_theme(self, dark=not self.is_light_theme())
            except Exception:
                pass

    def setup_actions(self):
        def make_action(key, text, slot):
            action = QAction(text, self)
            action.triggered.connect(slot)
            self.actions[key] = action
            self.addAction(action)
            return action

        # 프로젝트
        make_action("project_new", "새로 만들기", self.new_project_from_images)
        make_action("project_open", "열기", self.open_project)
        make_action("project_open_json", "JSON으로 열기", self.open_project_json)
        make_action("project_show_launcher", "홈화면으로 가기", self.show_launcher)
        make_action("project_save", "저장하기", self.save_project)
        make_action("project_save_as", "다른 이름으로 저장하기", self.save_project_as)
        make_action("project_recover_last_work", "복구하기", self.recover_last_work_project)

        # 개별 작업
        make_action("work_tab_cycle", "작업탭 변경", self.cycle_work_tab)
        make_action("work_page_prev", "이전 페이지", self.prev)
        make_action("work_page_next", "다음 페이지", self.next)
        make_action("work_open_current_project_folder", "현재 프로젝트의 작업 폴더로 이동하기", self.open_current_project_work_folder)
        make_action("work_analyze", "개별 분석", self.anal)
        make_action("work_text_number_width", "텍스트 넘버 크기 변경", self.open_text_number_width_dialog)
        make_action("work_translate", "개별 번역", self.trans)
        make_action("work_inpaint", "개별 인페인팅", self.run_inpainting)
        make_action("work_inpaint_source", "인페인팅을 원본으로", self.use_inpainted_as_source)
        make_action("work_restore_original_source", "원본으로 돌아가기", self.restore_original_source)
        make_action("work_extract_text", "개별 지문 추출", self.extract_text_current)
        make_action("work_import_translation", "개별 번역문 불러오기", self.import_translation_current)
        make_action("work_clear_translation", "번역문 내용 지우기", self.clear_translation_current)
        make_action("work_clean_text", "개별 텍스트 정리", self.clean_text_current)
        make_action("work_reset_text_rects", "현재 텍스트 기준 영역 재설정", self.reset_text_rects_current)
        make_action("work_export", "개별 출력", self.export_result)

        # 자동화 작업
        make_action("auto_text_size_current", "자동 텍스트 크기 조정", self.auto_text_size_current)
        make_action("auto_text_size_batch", "일괄 자동 텍스트 크기 조정", self.auto_text_size_batch)
        make_action("auto_linebreak_current", "자동 줄 내림", self.auto_linebreak_current)
        make_action("auto_linebreak_batch", "일괄 자동 줄 내림", self.auto_linebreak_batch)

        # 일괄 작업
        make_action("batch_analyze", "일괄 분석", lambda: self.run_batch('analyze'))
        make_action("batch_translate", "일괄 번역", lambda: self.run_batch('translate'))
        make_action("batch_inpaint", "일괄 인페인팅", lambda: self.run_batch('inpaint'))
        make_action("batch_extract_text", "일괄 지문 추출", self.extract_text_batch)
        make_action("batch_import_translation", "일괄 번역문 불러오기", self.import_translation_batch)
        make_action("batch_clear_translation", "일괄 번역문 내용 지우기", self.clear_translation_batch)
        make_action("batch_clean_text", "일괄 텍스트 정리", self.clean_text_batch)
        make_action("batch_reset_text_rects", "일괄 텍스트 기준 영역 재설정", self.reset_text_rects_batch)
        make_action("batch_export", "일괄 출력", lambda: self.run_batch('export'))

        # 설정 / 옵션
        make_action("option_settings_overview", "설정 / 옵션", self.open_settings_overview_dialog)
        self.act_auto_save_mode = make_action("option_auto_save_mode", "자동저장 모드", self.toggle_auto_save_mode)
        self.act_auto_save_mode.setCheckable(True)
        self.act_auto_save_mode.setChecked(self.auto_save_enabled)
        make_action("option_theme_settings", "테마 설정", self.open_theme_settings_dialog)
        make_action("option_language_settings", "언어 설정", self.open_language_settings_dialog)
        make_action("option_api_settings", "API 관리", self.open_api_settings_dialog)
        make_action("option_translation_prompt", "번역 프롬프트 입력", self.open_translation_prompt_dialog)
        make_action("option_glossary", "단어장", self.open_glossary_dialog)
        make_action("option_analysis_mask_settings", "분석 마스크 확장 비율", self.open_analysis_mask_settings_dialog)
        make_action("option_workspace_location", "작업 폴더 위치 변경", self.change_workspace_location)
        make_action("option_workspace_reset_default", "작업 폴더 위치 기본값으로 변경", self.reset_workspace_location_to_default)
        make_action("option_cleanup_temp_files", "임시 파일 관리", self.cleanup_temp_files_dialog)
        make_action("option_register_ysb", ".ysbt 확장자 연결 등록", self.register_ysb_file_association)
        make_action("option_unregister_ysbt", ".ysbt 확장자 연결 해제", self.unregister_ysbt_file_association)
        make_action("option_shortcut_settings", "단축키 통합 관리", self.open_shortcut_settings_dialog)
        make_action("option_macro_settings", "매크로 관리", self.open_macro_settings_dialog)
        make_action("option_text_preset_settings", "페이지 글꼴 프리셋 관리", self.open_text_preset_dialog)
        make_action("option_item_text_preset_settings", "개별 글꼴 프리셋 관리", self.open_item_text_preset_dialog)

        # 클라우드
        make_action("cloud_register", "클라우드 등록", self.cloud_register)
        make_action("cloud_unregister", "클라우드 등록 해제", self.cloud_unregister)
        make_action("cloud_cache_backup", "클라우드로 캐시 백업", self.cloud_backup_cache)
        make_action("cloud_cache_restore", "클라우드에서 캐시 불러오기", self.cloud_restore_cache)
        make_action("cloud_delete_backups", "클라우드 백업 삭제", self.cloud_delete_cache_backups)

        # 토글/보조 작업
        make_action("paint_redo", "작업 재실행", self.handle_general_redo)
        make_action("paint_magic_fill", "마스킹 칠하기", self.fill_magic_wand_mask)
        make_action("paint_mask_cut", "마스크 커팅", lambda: self.set_tool("mask_cut"))
        make_action("paint_mask_toggle", "마스크 ON/OFF", self.toggle_mask_toggle)
        make_action("view_text_toggle", "텍스트 표시 ON/OFF", self.toggle_show_final_text)
        make_action("final_paint_color", "최종 페인팅 색상", lambda: self.pick_color("final_paint"))
        make_action("final_paint_to_background", "최종 페인팅을 배경으로 반영", self.apply_final_paint_to_background)
        make_action("final_text_tool", "최종 텍스트 도구", lambda: self.set_tool("final_text"))
        make_action("final_paint_above_toggle", "텍스트 위 페인팅 ON/OFF", self.toggle_final_paint_above_text)
        make_action("final_paint_opacity_inc", "최종 브러시 불투명도 증가", lambda: self.adjust_final_paint_opacity(+5))
        make_action("final_paint_opacity_dec", "최종 브러시 불투명도 감소", lambda: self.adjust_final_paint_opacity(-5))

    def apply_shortcuts(self):
        for key, action in self.actions.items():
            seq = self.shortcut_settings.seq(key)
            action.setShortcut(seq)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)

        # 기존 매크로 액션 제거 후 현재 설정 기준으로 다시 등록한다.
        for action in getattr(self, "macro_actions", []):
            try:
                self.removeAction(action)
            except Exception:
                pass
        self.macro_actions = []

        for macro in getattr(self.shortcut_settings, "macros", []) or []:
            if not macro.get("enabled", True):
                continue
            shortcut = str(macro.get("shortcut", "") or "").strip()
            actions = list(macro.get("actions", []) or [])
            if not shortcut or not actions:
                continue
            action = QAction(str(macro.get("name", "매크로")), self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            action.triggered.connect(lambda checked=False, m=dict(macro): self.run_macro(m))
            self.addAction(action)
            self.macro_actions.append(action)

        for action in getattr(self, "item_preset_actions", []):
            try:
                self.removeAction(action)
            except Exception:
                pass
        self.item_preset_actions = []
        for name, preset in sorted(getattr(self, "item_text_presets", {}).items()):
            if not preset.get("enabled", True):
                continue
            shortcut = str(preset.get("shortcut", "") or "").strip()
            if not shortcut:
                continue
            action = QAction(f"개별 글꼴 프리셋: {name}", self)
            action.setShortcut(QKeySequence(shortcut))
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
            # 개별 글꼴 프리셋 "단축키" 적용은 Ctrl+Z 기록에서 제외한다.
            # 일반 텍스트 조정/콤보 적용은 기존처럼 Undo 대상이다.
            action.triggered.connect(lambda checked=False, n=name: self.apply_item_text_preset_by_name(n, record_undo=True))
            self.addAction(action)
            self.item_preset_actions.append(action)

        if hasattr(self, "cb_show_final_text"):
            self.configure_ui_tooltips()

    def update_paint_toolbar_visibility(self):
        """작업 탭별로 사용할 수 없는 좌측 도구 아이콘은 숨긴다."""
        mode = self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0

        mask_tabs = mode in (2, 3)
        final_tab = mode == 4
        drawing_tabs = mask_tabs or final_tab
        paint_only = mode == 3

        # 브러시/지우개/되돌리기는 마스크 탭 + 최종화면에서 사용.
        for attr in ("act_brush", "act_erase", "act_undo"):
            if hasattr(self, attr):
                getattr(self, attr).setVisible(drawing_tabs)

        # 요술봉은 마스크 탭 전용. 재분석은 텍스트 마스크 탭 하단의 파란 버튼으로 이동했다.
        if hasattr(self, "act_magic"):
            self.act_magic.setVisible(mask_tabs)
        if hasattr(self, "act_mask_wrap"):
            self.act_mask_wrap.setVisible(mask_tabs)
        if hasattr(self, "act_mask_cut"):
            self.act_mask_cut.setVisible(mask_tabs)
        if hasattr(self, "act_reanal"):
            self.act_reanal.setVisible(False)
        if hasattr(self, "btn_text_mask_reanalyze"):
            self.btn_text_mask_reanalyze.setVisible(mode == 2)

        # 마스크 ON/OFF는 페인팅 마스크 탭 전용.
        if hasattr(self, "act_mask_toggle"):
            self.act_mask_toggle.setVisible(paint_only)
        if hasattr(self, "mask_toggle_wrap") and self.mask_toggle_wrap:
            self.mask_toggle_wrap.setVisible(paint_only)

        # 최종화면 전용 도구.
        for attr in ("act_final_paint_color", "act_final_text_tool", "act_final_paint_to_bg", "act_final_paint_above_text"):
            if hasattr(self, attr):
                getattr(self, attr).setVisible(final_tab)

        if hasattr(self, "tb"):
            self.tb.setEnabled(drawing_tabs)

    def toggle_mask_toggle(self):
        # 마스크 ON/OFF는 페인팅 마스크 탭 전용이다.
        # 텍스트 마스크 탭에서는 관련 동작을 하지 않는다.
        if self.cb_mode.currentIndex() != 3:
            return
        if hasattr(self, "cb_mask_toggle") and self.cb_mask_toggle is not None:
            self.cb_mask_toggle.toggle()

    def toggle_show_final_text(self):
        if hasattr(self, "cb_show_final_text") and self.cb_show_final_text is not None:
            self.cb_show_final_text.toggle()

    def _tooltip_rich_text(self, title, shortcut_text="", description="", force_white_in_light=False):
        title = str(title or "")
        shortcut_text = str(shortcut_text or "").strip()
        description = str(description or "").strip()

        is_light = self.is_light_theme()
        if is_light and force_white_in_light:
            fg = "#ffffff"
            sub = "#ffffff"
            line = "#ffffff"
        elif is_light:
            fg = "#111827"
            sub = "#374151"
            line = "#cfd7e5"
        else:
            fg = "#ffffff"
            sub = "#e5e7eb"
            line = "#4b5563"

        # 배경은 QToolTip 자체 스타일을 따른다. 여기서는 글자색만 명확히 지정한다.
        base = (
            f'color:{fg};'
            'padding:1px 4px;'
            'white-space:normal;'
        )
        rows = [f'<div style="color:{fg};"><b>{title}</b></div>']
        if shortcut_text:
            rows.append(f'<div style="margin-top:2px;color:{sub};">{shortcut_text}</div>')
        if description:
            rows.append(f'<div style="margin-top:4px;color:{sub}; border-top:1px solid {line}; padding-top:3px;">{description}</div>')
        return f'<div style="{base}">' + ''.join(rows) + '</div>'

    def install_global_input_filter(self):
        """Ctrl+Z/Delete가 우측 표 편집기나 이미지 뷰에 포커스가 있을 때도 메인 작업으로 들어오게 한다.

        QTableWidget의 셀 편집기(QLineEdit/QTextEdit)는 Ctrl+Z를 자체 텍스트 편집 Undo로
        소비할 수 있다. YSB에서는 텍스트 라인 변경도 프로젝트 Undo 스택에 넣어야 하므로,
        메인 윈도우 안에서 발생한 Ctrl+Z는 먼저 편집 내용을 확정한 뒤 일반 Undo로 넘긴다.
        """
        if getattr(self, "_global_event_filter_installed", False):
            return
        app = QApplication.instance()
        if app is None:
            return
        try:
            app.installEventFilter(self)
            self._global_event_filter_installed = True
        except Exception:
            pass

    def _is_own_window_object(self, obj):
        try:
            if obj is self:
                return True
            w = obj if isinstance(obj, QWidget) else None
            if w is None:
                return False
            return w.window() is self
        except Exception:
            return False

    def _find_parent_widget_of_type(self, obj, cls):
        try:
            p = obj
            for _ in range(8):
                if p is None or not hasattr(p, "parent"):
                    return None
                p = p.parent()
                if isinstance(p, cls):
                    return p
        except Exception:
            return None
        return None

    def current_font_focus_widget(self, obj=None):
        """메인/프리셋의 글꼴 선택 콤보박스에 포커스가 있는지 확인한다."""
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None
        candidates = [obj, fw]
        for w in candidates:
            if w is None:
                continue
            try:
                if isinstance(w, QFontComboBox):
                    return w
                parent_font_combo = self._find_parent_widget_of_type(w, QFontComboBox)
                if parent_font_combo is not None:
                    return parent_font_combo
            except Exception:
                pass
        return None

    def escape_font_focus_first(self, obj=None):
        """ESC는 글꼴 선택 콤보박스의 포커스를 먼저 빼고, 다른 작업은 하지 않는다."""
        combo = self.current_font_focus_widget(obj)
        if combo is None:
            return False
        try:
            combo.hidePopup()
        except Exception:
            pass
        try:
            combo.clearFocus()
        except Exception:
            pass
        try:
            line = combo.lineEdit()
            if line is not None:
                line.clearFocus()
        except Exception:
            pass
        try:
            if getattr(self, "view", None) is not None:
                self.view.setFocus(Qt.FocusReason.OtherFocusReason)
            else:
                self.setFocus(Qt.FocusReason.OtherFocusReason)
        except Exception:
            pass
        return True

    def current_single_line_input_widget(self, obj=None):
        """ESC/Enter 포커스 탈출 대상이 되는 단일 입력 위젯을 찾는다."""
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None

        for target in (obj, fw):
            if target is None:
                continue
            try:
                if isinstance(target, (QLineEdit, QAbstractSpinBox, QComboBox, QFontComboBox, QKeySequenceEdit)):
                    return target
                # QSpinBox/QComboBox 내부 lineEdit이나 popup child에서 올라가기
                p = target
                for _ in range(8):
                    if p is None or not hasattr(p, "parent"):
                        break
                    p = p.parent()
                    if isinstance(p, (QAbstractSpinBox, QComboBox, QFontComboBox, QKeySequenceEdit)):
                        return p
            except Exception:
                pass
        return None

    def escape_single_line_input_focus_first(self, obj=None):
        """ESC는 단일 입력칸 포커스를 먼저 빼고, 다른 작업은 하지 않는다."""
        target = self.current_single_line_input_widget(obj)
        if target is None:
            return False

        # 멀티라인 텍스트 편집은 ESC 포커스 탈출 대상에서 제외한다.
        if isinstance(target, (QTextEdit, QPlainTextEdit)):
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
            if isinstance(target, QKeySequenceEdit):
                target.clear()
        except Exception:
            pass

        # 내부 lineEdit까지 같이 포커스 제거
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

        def move_focus():
            try:
                if getattr(self, "view", None) is not None:
                    self.view.setFocus(Qt.FocusReason.OtherFocusReason)
                else:
                    self.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

        move_focus()
        # 일부 입력 위젯이 ESC 처리 뒤 포커스를 다시 잡는 경우 대비.
        try:
            QTimer.singleShot(0, move_focus)
            QTimer.singleShot(30, move_focus)
        except Exception:
            pass
        return True

    def finish_single_line_input_by_enter(self, obj=None):
        """단일 입력칸에서 Enter를 누르면 값을 확정하고 포커스를 작업 화면으로 돌린다.
        QSpinBox/QDoubleSpinBox는 내부 QLineEdit이 Enter를 삼키거나 다시 포커스를 잡는 경우가 있어
        즉시 clearFocus + 지연 clearFocus를 같이 수행한다.
        """
        try:
            fw = QApplication.focusWidget()
        except Exception:
            fw = None

        def is_input_like(w):
            if w is None:
                return False
            try:
                if isinstance(w, (QLineEdit, QAbstractSpinBox)):
                    return True
                p = w.parent() if hasattr(w, "parent") else None
                if isinstance(w, QLineEdit) and isinstance(p, QComboBox):
                    return True
                for _ in range(4):
                    p = p.parent() if p is not None and hasattr(p, "parent") else None
                    if isinstance(p, QAbstractSpinBox):
                        return True
            except Exception:
                pass
            return False

        # eventFilter로 들어온 obj가 내부 lineEdit일 수 있으므로 obj를 우선 본다.
        target = obj if is_input_like(obj) else fw
        if target is None or not is_input_like(target):
            return False

        spin = None
        line = None
        try:
            if isinstance(target, QAbstractSpinBox):
                spin = target
                line = target.lineEdit()
            else:
                if isinstance(target, QLineEdit):
                    line = target
                p = target
                for _ in range(5):
                    if p is None or not hasattr(p, "parent"):
                        break
                    p = p.parent()
                    if isinstance(p, QAbstractSpinBox):
                        spin = p
                        try:
                            line = p.lineEdit()
                        except Exception:
                            pass
                        break
        except Exception:
            spin = None

        try:
            if spin is not None:
                spin.interpretText()
        except Exception:
            pass

        # 우측 표 셀 편집기면 표 에디터를 닫아 itemChanged를 확정한다.
        try:
            table = getattr(self, "tab", None)
            if table is not None and (target is table or table.isAncestorOf(target)):
                try:
                    table.commitData(target)
                except Exception:
                    pass
                try:
                    table.closeEditor(target, QAbstractItemDelegate.EndEditHint.NoHint)
                except Exception:
                    pass
                table.setFocus(Qt.FocusReason.OtherFocusReason)
                return True
        except Exception:
            pass

        def ensure_focus_sink():
            sink = getattr(self, "_enter_focus_sink", None)
            try:
                if sink is None:
                    sink = QWidget(self)
                    sink.setObjectName("EnterFocusSink")
                    sink.setFixedSize(1, 1)
                    sink.move(-100, -100)
                    sink.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                    try:
                        sink.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, True)
                    except Exception:
                        pass
                    sink.show()
                    self._enter_focus_sink = sink
                return sink
            except Exception:
                return None

        def clear_and_move_focus():
            # QSpinBox 내부 editor가 Enter 처리 뒤 다시 포커스를 잡는 경우가 있어 여러 대상을 같이 정리한다.
            for w in (line, target, spin):
                try:
                    if w is not None:
                        if hasattr(w, "deselect"):
                            w.deselect()
                        w.clearFocus()
                except Exception:
                    pass

            try:
                if getattr(self, "view", None) is not None:
                    try:
                        self.view.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                    except Exception:
                        pass
                    self.view.setFocus(Qt.FocusReason.OtherFocusReason)
                    return
            except Exception:
                pass

            sink = ensure_focus_sink()
            try:
                if sink is not None:
                    sink.setFocus(Qt.FocusReason.OtherFocusReason)
                    return
            except Exception:
                pass

            try:
                self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
                self.setFocus(Qt.FocusReason.OtherFocusReason)
            except Exception:
                pass

        clear_and_move_focus()
        # Qt가 spinbox keyPressEvent/editingFinished 뒤에 포커스를 다시 잡는 경우 대비.
        QTimer.singleShot(0, clear_and_move_focus)
        QTimer.singleShot(30, clear_and_move_focus)
        return True

    def commit_active_text_editors_before_undo(self):
        """Undo 직전 열린 셀/인라인 텍스트 편집을 data에 먼저 확정한다."""
        try:
            if getattr(self, "inline_text_editor", None) is not None:
                self.finish_inline_text_edit(commit=True, refresh=False)
        except Exception:
            pass

        fw = QApplication.focusWidget()
        if fw is None:
            return

        # 우측 텍스트 표의 임시 편집기라면 닫아서 itemChanged를 먼저 발생시킨다.
        try:
            if getattr(self, "tab", None) is not None and (fw is self.tab or self.tab.isAncestorOf(fw)):
                try:
                    self.tab.commitData(fw)
                except Exception:
                    pass
                try:
                    self.tab.closeEditor(fw, QAbstractItemDelegate.EndEditHint.NoHint)
                except Exception:
                    try:
                        fw.clearFocus()
                        self.tab.setFocus()
                    except Exception:
                        pass
                QApplication.processEvents()
        except Exception:
            pass

    def handle_global_undo_shortcut(self):
        self.commit_active_text_editors_before_undo()
        self.handle_general_undo()
        return True

    def install_enter_escape_for_input(self, widget):
        """QSpinBox 내부 editor가 Enter를 삼키는 경우까지 대비해 직접 필터/시그널을 붙인다."""
        if widget is None:
            return
        try:
            widget.installEventFilter(self)
        except Exception:
            pass

        def install_line():
            try:
                line = widget.lineEdit()
            except Exception:
                line = None
            if line is not None:
                try:
                    line.installEventFilter(self)
                except Exception:
                    pass
                try:
                    line.returnPressed.connect(lambda w=widget: self.finish_single_line_input_by_enter(w))
                except Exception:
                    pass
                try:
                    line.editingFinished.connect(lambda w=widget: QTimer.singleShot(0, lambda: self.finish_single_line_input_by_enter(w) if QApplication.focusWidget() is line else None))
                except Exception:
                    pass

        install_line()
        QTimer.singleShot(0, install_line)

        try:
            if isinstance(widget, QLineEdit):
                widget.returnPressed.connect(lambda w=widget: self.finish_single_line_input_by_enter(w))
        except Exception:
            pass

    def install_main_input_enter_escape_filters(self):
        """메인 상단 조작부 입력칸에서 Enter가 포커스 탈출로 동작하게 한다."""
        for widget in (
            getattr(self, "cb_font", None),
            getattr(self, "sb_font_size", None),
            getattr(self, "sb_strk", None),
            getattr(self, "sb_line_spacing", None),
            getattr(self, "sb_letter_spacing", None),
            getattr(self, "sb_char_width", None),
            getattr(self, "sb_char_height", None),
            getattr(self, "cb_item_text_preset", None),
            getattr(self, "cb_trans_provider", None),
            getattr(self, "sb_trans_chunk", None),
            getattr(self, "sb_final_paint_opacity", None),
            getattr(self, "sb_magic_tolerance", None),
            getattr(self, "sb_magic_expand", None),
        ):
            self.install_enter_escape_for_input(widget)

    def register_delayed_tooltip(self, widget, title, shortcut_text="", description=""):
        if widget is None:
            return

        # QWidget 툴팁과 QAction 툴팁이 동시에 살아 있으면
        # 작은 기본 툴팁 + 지연 툴팁 + 상태 설명이 중복 표시될 수 있다.
        # 그래서 실제 표시는 이 지연 툴팁 하나로 통일한다.
        try:
            widget.setToolTip("")
            action = widget.defaultAction() if hasattr(widget, "defaultAction") else None
            if action is not None:
                action.setToolTip("")
                action.setStatusTip("")
                action.setWhatsThis("")
        except Exception:
            pass

        try:
            title = self.tr_msg(title)
            description = self.tr_msg(description)
        except Exception:
            pass
        force_white_in_light = False
        try:
            force_white_in_light = bool(widget.property("force_white_tooltip_in_light") or widget.property("force_dark_tooltip"))
        except Exception:
            force_white_in_light = False
        widget.setProperty("delayed_tooltip_title", title)
        widget.setProperty("delayed_tooltip_shortcut", shortcut_text)
        widget.setProperty("delayed_tooltip_description", description)
        widget.setProperty("delayed_tooltip_force_white_in_light", force_white_in_light)
        widget.setProperty("delayed_tooltip_html", self._tooltip_rich_text(title, shortcut_text, description, force_white_in_light=force_white_in_light))
        widget.installEventFilter(self)

    def _show_delayed_tooltip(self):
        widget = self._tooltip_target
        html = self._tooltip_html
        if widget is None or not html:
            return
        if not widget.isVisible():
            return
        try:
            raw_title = widget.property("delayed_tooltip_title")
            if raw_title:
                raw_shortcut = widget.property("delayed_tooltip_shortcut") or ""
                raw_desc = widget.property("delayed_tooltip_description") or ""
                force_white = bool(widget.property("delayed_tooltip_force_white_in_light"))
                html = self._tooltip_rich_text(raw_title, raw_shortcut, raw_desc, force_white_in_light=force_white)
                self._tooltip_html = html
        except Exception:
            pass
        try:
            pos = widget.mapToGlobal(QPoint(widget.width() // 2, widget.height()))
        except Exception:
            pos = QCursor.pos()
        QToolTip.showText(pos, html, widget)

    def eventFilter(self, obj, event):
        et = event.type()
        if et == QEvent.Type.Show and isinstance(obj, QDialog):
            try:
                p = obj.parent()
                while p is not None:
                    if p is self:
                        self.schedule_native_title_bar_theme(obj, dark=not self.is_light_theme())
                        break
                    p = p.parent()
            except Exception:
                pass
        if et in (QEvent.Type.KeyPress, QEvent.Type.ShortcutOverride) and self._is_own_window_object(obj):
            try:
                key = event.key()
                mods = event.modifiers()
                ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)

                if key == Qt.Key.Key_Escape and self.escape_single_line_input_focus_first(obj):
                    event.accept()
                    return True

                if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and not (
                    mods & (
                        Qt.KeyboardModifier.ControlModifier
                        | Qt.KeyboardModifier.ShiftModifier
                        | Qt.KeyboardModifier.AltModifier
                    )
                ):
                    # 사용자는 입력을 끝낼 때 습관적으로 Enter를 누른다.
                    # QLineEdit/스핀박스/편집 가능한 콤보박스에서는 Enter가 옆 버튼을 누르거나
                    # 다음 위젯을 건드리지 않고, 편집을 확정한 뒤 포커스만 빠지게 한다.
                    if self.finish_single_line_input_by_enter(obj):
                        event.accept()
                        return True

                if et == QEvent.Type.ShortcutOverride:
                    return False

                if self._event_matches_shortcut(event, "paint_undo") or (ctrl and key == Qt.Key.Key_Z):
                    self.handle_global_undo_shortcut()
                    event.accept()
                    return True
                if self._event_matches_shortcut(event, "paint_redo") or (ctrl and key == Qt.Key.Key_Y):
                    self.handle_general_redo()
                    event.accept()
                    return True
                if key == Qt.Key.Key_Delete:
                    fw = QApplication.focusWidget()
                    in_table = getattr(self, "tab", None) is not None and (fw is self.tab or self.tab.isAncestorOf(fw))
                    if in_table and self.selected_table_text_ids():
                        self.delete_text_data_items(ask=True)
                        event.accept()
                        return True
            except Exception:
                pass
        if hasattr(obj, "property") and (obj.property("delayed_tooltip_title") or obj.property("delayed_tooltip_html")):
            # QAction/QToolButton 기본 툴팁은 action text를 작게 띄우는 경우가 있다.
            # 예: W, ☐ 같은 "아이콘 확대"처럼 보이는 검은 툴팁.
            # 지연 툴팁 하나만 쓰기 위해 기본 ToolTip 이벤트는 완전히 막는다.
            if et == QEvent.Type.ToolTip:
                return True

            if et == QEvent.Type.Enter:
                self._tooltip_target = obj
                try:
                    raw_title = obj.property("delayed_tooltip_title")
                    if raw_title:
                        self._tooltip_html = self._tooltip_rich_text(
                            raw_title,
                            obj.property("delayed_tooltip_shortcut") or "",
                            obj.property("delayed_tooltip_description") or "",
                            force_white_in_light=bool(obj.property("delayed_tooltip_force_white_in_light")),
                        )
                    else:
                        self._tooltip_html = obj.property("delayed_tooltip_html") or ""
                except Exception:
                    self._tooltip_html = obj.property("delayed_tooltip_html") or ""
                self._tooltip_timer.start(500)
            elif et in (QEvent.Type.Leave, QEvent.Type.MouseButtonPress, QEvent.Type.Hide, QEvent.Type.FocusOut):
                if self._tooltip_target is obj:
                    self._tooltip_timer.stop()
                    self._tooltip_target = None
                    self._tooltip_html = ""
                    QToolTip.hideText()
        return super().eventFilter(obj, event)

    def configure_ui_tooltips(self):
        def seq_text(key):
            if key.startswith("RAW:"):
                return key[4:]
            try:
                return self.shortcut_settings.seq(key).toString(QKeySequence.SequenceFormat.NativeText)
            except Exception:
                return ""

        # 좌측 그림판/마스크 도구
        if hasattr(self, "tb") and self.tb is not None:
            action_info = []
            if hasattr(self, "act_brush"): action_info.append((self.act_brush, "브러시", seq_text("paint_brush")))
            if hasattr(self, "act_erase"): action_info.append((self.act_erase, "지우개", seq_text("paint_erase")))
            if hasattr(self, "act_reanal"): action_info.append((self.act_reanal, "재분석", seq_text("paint_reanalyze")))
            if hasattr(self, "act_undo"): action_info.append((self.act_undo, "작업 취소", seq_text("paint_undo")))
            if hasattr(self, "act_redo"): action_info.append((self.act_redo, "작업 재실행", seq_text("paint_redo")))
            if hasattr(self, "act_magic"): action_info.append((self.act_magic, "요술봉 선택", seq_text("paint_magic_select")))
            if hasattr(self, "act_mask_wrap"): action_info.append((self.act_mask_wrap, "마스크 랩핑", seq_text("paint_mask_wrap"), "영역 안의 떨어진 마스크들을 하나의 채움 영역으로 감싸줍니다."))
            if hasattr(self, "act_mask_cut"): action_info.append((self.act_mask_cut, "마스크 커팅", seq_text("paint_mask_cut"), "선택 영역 밖 경계를 지정 픽셀만큼 잘라 붙어 있는 마스크를 분리합니다."))
            if hasattr(self, "act_final_text_tool"): action_info.append((self.act_final_text_tool, "최종 텍스트 도구", seq_text("final_text_tool"), "최종화면을 클릭하면 텍스트 영역을 만듭니다. 내용 작성 후 Ctrl+Return을 누르거나 다른 곳을 클릭하면 작성이 완료됩니다."))
            if hasattr(self, "act_final_paint_to_bg"): action_info.append((self.act_final_paint_to_bg, "최종 페인팅을 배경으로 반영", seq_text("final_paint_to_background")))
            if hasattr(self, "act_final_paint_above_text"): action_info.append((self.act_final_paint_above_text, "텍스트 위에 페인팅", seq_text("final_paint_above_toggle"), "ON이면 이후 새로 칠하는 브러시가 텍스트보다 위 레이어에 그려집니다."))
            for info in action_info:
                try:
                    if len(info) >= 4:
                        act, title, sk, desc = info
                    else:
                        act, title, sk = info
                        desc = ""
                    self.register_delayed_tooltip(self.tb.widgetForAction(act), title, sk, desc)
                except Exception:
                    pass

        if hasattr(self, "act_final_paint_color") and hasattr(self, "tb"):
            self.register_delayed_tooltip(self.tb.widgetForAction(self.act_final_paint_color), "최종 페인팅 색상", seq_text("final_paint_color"), "스포이드: Alt+마우스 좌클릭")
        if hasattr(self, "mask_toggle_wrap"):
            self.register_delayed_tooltip(
                self.mask_toggle_wrap,
                "페인팅 마스크 ON/OFF",
                seq_text("paint_mask_toggle"),
                "ON은 분석 기반, OFF는 직접 칠한 마스크를 사용합니다."
            )
        if hasattr(self, "final_paint_option_bar"):
            self.register_delayed_tooltip(self.sb_final_paint_opacity, "최종 브러시 불투명도", f"{seq_text('final_paint_opacity_dec')} / {seq_text('final_paint_opacity_inc')}", "최종화면 브러시 색상의 알파값을 조절합니다.")
        if hasattr(self, "magic_wand_bar"):
            self.register_delayed_tooltip(self.btn_magic_expand, "선택 영역 확장", seq_text("paint_magic_expand"))
            self.register_delayed_tooltip(self.btn_magic_fill, "마스킹 칠하기", seq_text("paint_magic_fill"))
            self.register_delayed_tooltip(self.sb_magic_tolerance, "RGB 허용범위", f"{seq_text('paint_magic_tolerance_inc')} / {seq_text('paint_magic_tolerance_dec')}")
            self.register_delayed_tooltip(self.sb_magic_expand, "영역 확장 범위", f"{seq_text('paint_magic_expand_inc')} / {seq_text('paint_magic_expand_dec')}")
        if hasattr(self, "mask_wrap_bar"):
            self.register_delayed_tooltip(self.btn_mask_wrap_rect, "사각형으로 영역 그리기", seq_text("paint_mask_wrap_rect"), "윈도우 캡처처럼 사각형 범위를 잡고 그 안의 마스크들을 하나로 감싸 채웁니다.")
            self.register_delayed_tooltip(self.btn_mask_wrap_free, "자유형으로 영역 그리기", seq_text("paint_mask_wrap_free"), "드래그한 자유형 범위 안에서만 마스크들을 하나로 감싸 채웁니다.")
        if hasattr(self, "mask_cut_bar"):
            self.register_delayed_tooltip(self.btn_mask_cut_rect, "사각형으로 영역 그리기", seq_text("paint_mask_wrap_rect"), "사각형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.")
            self.register_delayed_tooltip(self.btn_mask_cut_free, "자유형으로 영역 그리기", seq_text("paint_mask_wrap_free"), "자유형 보존 영역의 바깥 경계를 지정 픽셀만큼 잘라냅니다.")
            self.register_delayed_tooltip(self.sb_mask_cut_px, "커팅 폭", "", "선택 영역 밖으로 잘라낼 마스크 폭입니다.")

        # 툴팁 기본 글자색:
        # - 다크 테마: 흰색
        # - 화이트 테마: 검정색
        # 예외: 화이트 테마에서도 색상 버튼 6종은 글자만 흰색으로 표시한다.
        for _force_white_tip_widget in (
            getattr(self, "btn_quick_undo", None),
            getattr(self, "btn_quick_redo", None),
            getattr(self, "btn_translate", None),
            getattr(self, "btn_analyze", None),
            getattr(self, "btn_text_mask_reanalyze", None),
            getattr(self, "btn_inpaint", None),
        ):
            if _force_white_tip_widget is not None:
                try:
                    _force_white_tip_widget.setProperty("force_white_tooltip_in_light", True)
                except Exception:
                    pass

        # 우측 상단 작업 버튼/옵션
        if hasattr(self, "sb_trans_chunk"):
            self.register_delayed_tooltip(self.sb_trans_chunk, "묶음 수", "", "한 번의 API 요청에 묶어서 보낼 텍스트 줄 수")
        if hasattr(self, "btn_text_mask_reanalyze"):
            self.register_delayed_tooltip(self.btn_text_mask_reanalyze, "텍스트 마스크 재분석", seq_text("paint_reanalyze"), "텍스트 마스크 영역을 기준으로 OCR을 다시 실행합니다.")
        if hasattr(self, "btn_analyze"):
            self.register_delayed_tooltip(self.btn_analyze, "분석", seq_text("work_analyze"), "현재 페이지를 분석합니다.")
        if hasattr(self, "btn_translate"):
            self.register_delayed_tooltip(self.btn_translate, "번역", seq_text("work_translate"))
        if hasattr(self, "btn_inpaint"):
            self.register_delayed_tooltip(self.btn_inpaint, "인페인팅", seq_text("work_inpaint"))
        if hasattr(self, "btn_text_cleanup"):
            self.register_delayed_tooltip(self.btn_text_cleanup, "텍스트 정리", seq_text("work_clean_text"))
        if hasattr(self, "cb_show_final_text"):
            self.register_delayed_tooltip(self.cb_show_final_text, "텍스트 표시 ON/OFF", seq_text("view_text_toggle"))
        if hasattr(self, "cb_font"):
            self.register_delayed_tooltip(self.cb_font, "글꼴", seq_text("item_font_select"), "현재 선택한 텍스트의 글꼴을 바꿉니다.")
        if hasattr(self, "sb_font_size"):
            self.register_delayed_tooltip(self.sb_font_size, "글꼴 크기", seq_text("text_font_size"), "현재 선택한 텍스트의 글자 크기를 조절합니다.")
        if hasattr(self, "sb_strk"):
            self.register_delayed_tooltip(self.sb_strk, "획 크기", seq_text("text_stroke_size"), "현재 선택한 텍스트의 외곽선 두께를 조절합니다.")
        if hasattr(self, "sb_line_spacing"):
            self.register_delayed_tooltip(self.sb_line_spacing, "행간", seq_text("text_line_spacing"), "줄과 줄 사이 간격을 조절합니다.")
        if hasattr(self, "sb_letter_spacing"):
            self.register_delayed_tooltip(self.sb_letter_spacing, "자간", seq_text("text_letter_spacing"), "글자와 글자 사이 간격을 조절합니다.")
        if hasattr(self, "sb_char_width"):
            self.register_delayed_tooltip(self.sb_char_width, "너비", seq_text("text_char_width"), "문자의 가로 비율을 조절합니다.")
        if hasattr(self, "sb_char_height"):
            self.register_delayed_tooltip(self.sb_char_height, "높이", seq_text("text_char_height"), "문자의 세로 비율을 조절합니다.")
        if hasattr(self, "btn_bold"):
            self.register_delayed_tooltip(self.btn_bold, "굵게", seq_text("text_bold_toggle"))
            self.register_delayed_tooltip(self.btn_italic, "기울이기", seq_text("text_italic_toggle"))
            self.register_delayed_tooltip(self.btn_strike, "취소선", seq_text("text_strike_toggle"))
        if hasattr(self, "btn_prev_page"):
            self.register_delayed_tooltip(self.btn_prev_page, "이전 페이지", seq_text("work_page_prev"))
        if hasattr(self, "btn_next_page"):
            self.register_delayed_tooltip(self.btn_next_page, "다음 페이지", seq_text("work_page_next"))
        if hasattr(self, "btn_page"):
            self.register_delayed_tooltip(self.btn_page, "페이지 이동", "", "현재 페이지 번호를 눌러 원하는 페이지로 바로 이동합니다.")
        if hasattr(self, "cb_mode"):
            self.register_delayed_tooltip(self.cb_mode, "작업 탭", seq_text("work_tab_cycle"), "원본, 분석도, 마스크, 최종결과 탭을 전환합니다.")
        if hasattr(self, "btn_quick_undo"):
            self.register_delayed_tooltip(self.btn_quick_undo, "뒤로가기", seq_text("paint_undo"), "최근 작업을 되돌립니다.")
        if hasattr(self, "btn_quick_redo"):
            self.register_delayed_tooltip(self.btn_quick_redo, "앞으로 가기", seq_text("paint_redo"), "되돌린 작업을 다시 실행합니다.")
        if hasattr(self, "btn_text_color"):
            self.register_delayed_tooltip(self.btn_text_color, "문자 색상", seq_text("item_text_color"))
        if hasattr(self, "btn_stroke_color"):
            self.register_delayed_tooltip(self.btn_stroke_color, "획 색상", seq_text("item_stroke_color"))
        if hasattr(self, "btn_align_left"):
            self.register_delayed_tooltip(self.btn_align_left, "왼쪽 정렬", seq_text("item_align_left"))
            self.register_delayed_tooltip(self.btn_align_center, "가운데 정렬", seq_text("item_align_center"))
            self.register_delayed_tooltip(self.btn_align_right, "오른쪽 정렬", seq_text("item_align_right"))

    def message_box_style(self):
        """확인/경고/질문창 공통 스타일. 홈/클라우드 쪽의 부드러운 카드 톤에 맞춘다."""
        if self.is_light_theme():
            return """
                QMessageBox { background:#f4f6fa; color:#111827; }
                QMessageBox QLabel { color:#111827; line-height:1.35em; }
                QMessageBox QPushButton {
                    background:#ffffff;
                    color:#111827;
                    border:1px solid #cfd7e5;
                    border-radius:0px;
                    padding:7px 18px;
                    min-width:72px;
                }
                QMessageBox QPushButton:hover { background:#edf4ff; border-color:#aac4e8; }
                QMessageBox QPushButton:pressed { background:#e3edf9; }
                QMessageBox QToolTip { background-color:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:5px; }
            """
        return """
            QMessageBox { background:#24272d; color:#f2f4f8; }
            QMessageBox QLabel { color:#f2f4f8; line-height:1.35em; }
            QMessageBox QPushButton {
                background:#333843;
                color:#f2f4f8;
                border:1px solid #586173;
                border-radius:0px;
                padding:7px 18px;
                min-width:72px;
            }
            QMessageBox QPushButton:hover { background:#3d4654; border-color:#74839a; }
            QMessageBox QPushButton:pressed { background:#2b3038; }
            QMessageBox QToolTip { background-color:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:0px; padding:5px; }
        """

    def _message_button_with_shortcut(self, button, key_text):
        """QMessageBox 버튼에 문자 단축키를 붙인다. 예: Y/N."""
        try:
            button.setShortcut(QKeySequence(str(key_text)))
        except Exception:
            pass
        try:
            button.setAutoDefault(True)
        except Exception:
            pass
        return button

    def ask_yes_no_shortcut(self, title, message, yes_text="예", no_text="아니오", default_yes=True, icon=QMessageBox.Icon.Question, parent=None):
        """Enter/Y/N이 동작하는 단순 확인창. 버튼에는 반드시 (Y)/(N)을 표시한다."""
        msg = QMessageBox(parent or self)
        msg.setIcon(icon)
        msg.setWindowTitle(self.tr_ui(title))
        msg.setText(self.tr_ui(message))
        msg.setStyleSheet(self.message_box_style())
        btn_yes = msg.addButton(f"{self.tr_ui(yes_text)} (Y)", QMessageBox.ButtonRole.AcceptRole)
        btn_no = msg.addButton(f"{self.tr_ui(no_text)} (N)", QMessageBox.ButtonRole.RejectRole)
        self._message_button_with_shortcut(btn_yes, "Y")
        self._message_button_with_shortcut(btn_no, "N")
        try:
            msg.setDefaultButton(btn_yes if default_yes else btn_no)
        except Exception:
            pass
        try:
            msg.setEscapeButton(btn_no)
        except Exception:
            pass
        msg.exec()
        return msg.clickedButton() == btn_yes

    def show_ok_notice(self, title, message, parent=None):
        """확인 버튼 하나만 있는 알림창. Enter로 닫힌다."""
        msg = QMessageBox(parent or self)
        msg.setIcon(QMessageBox.Icon.Information)
        msg.setWindowTitle(self.tr_ui(title))
        msg.setText(self.tr_ui(message))
        msg.setStyleSheet(self.message_box_style())
        btn_ok = msg.addButton(self.tr_ui("확인"), QMessageBox.ButtonRole.AcceptRole)
        try:
            msg.setDefaultButton(btn_ok)
        except Exception:
            pass
        force_message_box_front(msg)
        msg.exec()

    def _show_launcher_screen_only(self):
        """프로젝트 상태를 건드리지 않고 런처 화면만 표시한다. 내부 전용."""
        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.refresh()
            if hasattr(self, "main_stack") and hasattr(self, "launcher_widget"):
                self.main_stack.setCurrentWidget(self.launcher_widget)
        except Exception:
            pass

    def clear_current_project_runtime_state(self):
        """런처로 돌아가기 위해 현재 프로젝트 세션을 완전히 닫는다."""
        try:
            if getattr(self, "inline_text_editor", None) is not None:
                try:
                    self.finish_inline_text_edit(commit=True, refresh=False)
                except Exception:
                    pass
            if getattr(self, "project_dir", None) and getattr(self, "paths", None):
                try:
                    self.commit_current_page_ui_to_data()
                except Exception:
                    pass
        except Exception:
            pass

        try:
            self.cleanup_work_cache()
        except Exception:
            pass
        try:
            self.delete_temp_project_if_needed()
        except Exception:
            pass

        self.paths = []
        self.data = {}
        self.idx = 0
        self.project_store = ProjectStore()
        self.project_dir = None
        self.ysbt_package_path = None
        self.suggested_project_name = None
        self.is_temp_project = False
        self.work_project_store = None
        self.work_project_dir = None
        self.has_unsaved_changes = False
        self.page_text_undo_stacks = {}
        self.project_undo_stack = []
        self.project_redo_stack = []
        self.undo_boundary = None
        self.project_ui_view_states = {}
        self.magic_wand_mask = None
        self.magic_wand_seed = None
        self.magic_wand_seeds = []
        self.magic_wand_history = []
        self.text_clipboard = []
        self.text_paste_pending = False

        try:
            if hasattr(self, "tab") and self.tab is not None:
                self.tab.blockSignals(True)
                self.tab.setRowCount(0)
                self.tab.blockSignals(False)
        except Exception:
            pass
        try:
            if hasattr(self, "view") and self.view is not None:
                self.view.set_image(None)
        except Exception:
            try:
                self.view.scene.clear()
            except Exception:
                pass
        try:
            self.update_undo_redo_buttons()
        except Exception:
            pass
        try:
            self.update_window_title()
        except Exception:
            pass

    def show_launcher(self):
        """홈화면으로 이동한다. 홈화면은 열린 프로젝트가 없는 상태여야 한다."""
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(
                self,
                self.tr_ui("일괄 작업 중"),
                self.tr_ui("일괄 작업 중에는 홈화면으로 이동할 수 없습니다.\n작업이 끝난 뒤 다시 시도해 주세요."),
            )
            return

        if self.has_open_project():
            # 홈화면은 휴대폰 홈처럼 빈 상태여야 하므로, 현재 파일/프로젝트 세션을 먼저 닫는다.
            try:
                if getattr(self, "project_dir", None) and getattr(self, "paths", None):
                    self.commit_current_page_ui_to_data()
                    if getattr(self, "auto_save_enabled", False):
                        self.auto_save_project()
            except Exception as e:
                try:
                    self.log(f"⚠️ 홈화면 이동 전 현재 화면 반영 실패: {e}")
                except Exception:
                    pass

            if getattr(self, "has_unsaved_changes", False):
                if not self.confirm_unsaved_before_switch():
                    self.log("↩️ 홈화면 이동 취소")
                    return

            self.clear_current_project_runtime_state()
            self.log("🏠 프로젝트를 닫고 홈화면으로 이동했습니다.")

        self._show_launcher_screen_only()

    def confirm_open_recent_project(self, path):
        """최근 프로젝트 카드는 바로 열지 않고 한 번 확인한다."""
        path = str(path or "")
        if not path or not os.path.exists(path):
            QMessageBox.warning(
                self,
                self.tr_ui("파일을 찾을 수 없음"),
                self.tr_msg("최근 프로젝트 파일을 찾을 수 없습니다.\n최근 목록에서 제거하거나 파일 위치를 확인해 주세요."),
            )
            return
        name = Path(path).name
        message = self.tr_msg("이 최근 프로젝트를 열까요?") + f"\n\n{name}"
        if not self.ask_yes_no_shortcut("최근 프로젝트 열기", message, yes_text="열기", no_text="취소", default_yes=True):
            self.log("↩️ 최근 프로젝트 열기 취소")
            return
        self.open_project_path(path)

    def show_editor(self):
        """런처에서 실제 작업 화면으로 전환한다."""
        try:
            if hasattr(self, "main_stack") and hasattr(self, "editor_widget"):
                self.main_stack.setCurrentWidget(self.editor_widget)
        except Exception:
            pass

    def refresh_launcher(self):
        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.refresh()
        except Exception:
            pass

    def record_current_project_recent(self):
        """현재 열린 YSBT 프로젝트를 최근 목록에 기록하고 첫 페이지 썸네일을 캐시한다."""
        try:
            package_path = getattr(self, "ysbt_package_path", None)
            if not package_path or not os.path.exists(str(package_path)):
                return False
            store = getattr(self, "recent_project_store", None) or RecentProjectStore()
            self.recent_project_store = store
            title = self.display_project_name() or Path(package_path).stem
            thumb = store.make_thumbnail(getattr(self, "paths", []) or [], package_path)
            store.add_project(
                package_path,
                title=title,
                page_count=len(getattr(self, "paths", []) or []),
                thumbnail_path=thumb,
                cloud_backup_status="local_only",
            )
            self.refresh_launcher()
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 최근 프로젝트 기록 실패: {e}")
            except Exception:
                pass
            return False

    def remove_recent_project_from_launcher(self, path):
        try:
            if hasattr(self, "recent_project_store"):
                self.recent_project_store.remove_project(path)
            self.refresh_launcher()
        except Exception:
            pass

    def reveal_recent_project_in_folder(self, path):
        try:
            if not path or not os.path.exists(str(path)):
                return
            folder = str(Path(path).parent)
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
        except Exception as e:
            QMessageBox.warning(self, self.tr_ui("폴더 열기 실패"), str(e))

    def open_current_project_work_folder(self):
        """현재 열려 있는 프로젝트의 실제 작업 폴더를 탐색기에서 연다."""
        project_dir = getattr(self, "project_dir", None)
        if not project_dir:
            QMessageBox.information(
                self,
                self.tr_ui("작업 폴더 열기"),
                self.tr_ui("현재 열린 프로젝트가 없습니다."),
            )
            return
        folder = os.path.abspath(str(project_dir))
        if not os.path.isdir(folder):
            QMessageBox.warning(
                self,
                self.tr_ui("작업 폴더 열기 실패"),
                f"{self.tr_ui('현재 프로젝트 작업 폴더를 찾을 수 없습니다.')}\n\n{folder}",
            )
            return
        try:
            QDesktopServices.openUrl(QUrl.fromLocalFile(folder))
            self.log(f"📁 {self.tr_ui('현재 프로젝트 작업 폴더를 열었습니다.')}: {folder}")
        except Exception as e:
            QMessageBox.warning(self, self.tr_ui("작업 폴더 열기 실패"), str(e))

    def cloud_dir(self):
        path = get_cache_dir() / "cloud"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def cloud_config_path(self):
        return self.cloud_dir() / "cloud_config.json"

    def cloud_token_path(self):
        return self.cloud_dir() / "google_drive_token.json"

    def cloud_client_secret_path(self):
        return self.cloud_dir() / "google_oauth_client_secret.json"

    def load_cloud_config(self):
        try:
            p = self.cloud_config_path()
            if p.exists():
                with open(p, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    return data
        except Exception:
            pass
        return {}

    def save_cloud_config(self, data):
        data = dict(data or {})
        self.cloud_dir().mkdir(parents=True, exist_ok=True)
        with open(self.cloud_config_path(), "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def cloud_is_registered(self):
        return self.cloud_token_path().exists()

    def cloud_status_text(self):
        cfg = self.load_cloud_config()
        if self.cloud_is_registered():
            email = str(cfg.get("account_email") or "").strip()
            when = str(cfg.get("registered_at") or "").strip()
            bits = [self.tr_ui("등록됨")]
            if email:
                bits.append(email)
            if when:
                bits.append(when)
            return " / ".join(bits)
        return self.tr_ui("미등록")

    def google_cloud_dependency_error_text(self, missing):
        missing = list(missing or [])
        package_hint = "google-auth google-auth-oauthlib google-api-python-client"
        return (
            self.tr_ui("Google Drive OAuth 연동에 필요한 파이썬 라이브러리가 없습니다.")
            + "\n\n"
            + self.tr_ui("누락 모듈:")
            + "\n"
            + "\n".join(f"- {m}" for m in missing)
            + "\n\n"
            + self.tr_ui("개발/테스트 환경에서는 아래 명령으로 설치할 수 있습니다.")
            + f"\n\npip install {package_hint}"
            + "\n\n"
            + self.tr_ui("EXE 배포판에서는 빌드 시 위 라이브러리를 함께 포함해야 합니다.")
        )

    def import_google_oauth_modules(self):
        missing = []
        InstalledAppFlow = None
        Credentials = None
        Request = None
        build = None
        try:
            from google_auth_oauthlib.flow import InstalledAppFlow as _InstalledAppFlow
            InstalledAppFlow = _InstalledAppFlow
        except Exception as e:
            missing.append(f"google_auth_oauthlib.flow ({e})")
        try:
            from google.oauth2.credentials import Credentials as _Credentials
            Credentials = _Credentials
        except Exception as e:
            missing.append(f"google.oauth2.credentials ({e})")
        try:
            from google.auth.transport.requests import Request as _Request
            Request = _Request
        except Exception as e:
            missing.append(f"google.auth.transport.requests ({e})")
        try:
            from googleapiclient.discovery import build as _build
            build = _build
        except Exception as e:
            missing.append(f"googleapiclient.discovery ({e})")
        if missing:
            raise ImportError(self.google_cloud_dependency_error_text(missing))
        return InstalledAppFlow, Credentials, Request, build

    def cloud_oauth_candidate_paths(self):
        """OAuth 클라이언트 JSON 후보를 자동 탐색한다.
        배포판에서는 EXE 옆 cloud_oauth_client.json을 두면 사용자는 로그인만 누르면 된다.
        """
        names = [
            "cloud_oauth_client.json",
            "google_oauth_client_secret.json",
            "client_secret.json",
            "ysb_google_oauth_client.json",
        ]
        candidates = []
        try:
            candidates.append(self.cloud_client_secret_path())
        except Exception:
            pass

        roots = []
        try:
            roots.append(Path.cwd())
        except Exception:
            pass
        try:
            roots.append(Path(__file__).resolve().parent)
        except Exception:
            pass
        try:
            if getattr(sys, "frozen", False):
                roots.append(Path(sys.executable).resolve().parent)
        except Exception:
            pass

        for root in roots:
            for name in names:
                candidates.append(Path(root) / name)
            try:
                candidates.extend(sorted(Path(root).glob("client_secret*.json")))
            except Exception:
                pass

        for name in names:
            try:
                candidates.append(Path(resource_path(name)))
            except Exception:
                pass

        out = []
        seen = set()
        for p in candidates:
            try:
                key = str(Path(p).resolve()).lower()
            except Exception:
                key = str(p).lower()
            if key in seen:
                continue
            seen.add(key)
            out.append(Path(p))
        return out

    def is_valid_google_oauth_client_secret(self, path):
        try:
            p = Path(path)
            if not p.exists() or not p.is_file():
                return False
            data = json.loads(p.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                return False
            obj = data.get("installed") or data.get("web") or {}
            return bool(obj.get("client_id") and obj.get("auth_uri") and obj.get("token_uri"))
        except Exception:
            return False

    def find_default_cloud_client_secret(self):
        for p in self.cloud_oauth_candidate_paths():
            if self.is_valid_google_oauth_client_secret(p):
                return str(p)
        return ""

    def copy_cloud_client_secret(self, src_path):
        src_path = Path(str(src_path or ""))
        if not src_path.exists():
            raise FileNotFoundError(str(src_path))
        dst = self.cloud_client_secret_path()
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(str(src_path), str(dst))
        return dst

    def select_cloud_client_secret_json(self, parent=None):
        path, _ = QFileDialog.getOpenFileName(
            parent or self,
            self.tr_ui("Google OAuth 클라이언트 JSON 선택"),
            "",
            self.tr_ui("JSON 파일 (*.json);;모든 파일 (*)"),
        )
        return path or ""

    def run_google_drive_oauth(self, client_secret_path, parent=None):
        """Google Drive OAuth 로그인 창을 열고 토큰을 로컬 캐시에 저장한다.

        기존 InstalledAppFlow.run_local_server()는 브라우저 창을 닫거나 로그인을 취소했을 때
        UI 스레드를 오래 붙잡을 수 있어, 취소 가능한 로컬 콜백 서버를 직접 띄운다.
        - 사용자가 Google 화면에서 취소/거부하면 CloudOAuthCancelled로 정상 취소 처리
        - 진행 창의 취소/X 버튼을 누르면 CloudOAuthCancelled로 정상 취소 처리
        - 제한 시간 동안 콜백이 없으면 CloudOAuthCancelled로 정상 취소 처리
        """
        InstalledAppFlow, Credentials, Request, build = self.import_google_oauth_modules()

        client_secret_path = Path(str(client_secret_path or ""))
        if not client_secret_path.exists():
            raise FileNotFoundError(str(client_secret_path))

        scopes = ["https://www.googleapis.com/auth/drive.file"]
        flow = InstalledAppFlow.from_client_secrets_file(str(client_secret_path), scopes=scopes)

        result = {"code": "", "state": "", "error": "", "error_description": ""}
        callback_received = threading.Event()
        cancel_requested = threading.Event()

        class OAuthCallbackHandler(BaseHTTPRequestHandler):
            def log_message(self, fmt, *args):
                # 콘솔 노이즈 방지
                return

            def do_GET(self):
                parsed = urlparse(self.path)
                query = parse_qs(parsed.query or "")
                result["code"] = str((query.get("code") or [""])[0] or "")
                result["state"] = str((query.get("state") or [""])[0] or "")
                result["error"] = str((query.get("error") or [""])[0] or "")
                result["error_description"] = str((query.get("error_description") or [""])[0] or "")

                if result["error"]:
                    title = "YSB Tool cloud registration was cancelled."
                    body = "You can close this browser window and return to YSB Tool."
                else:
                    title = "YSB Tool cloud registration is complete."
                    body = "You can close this browser window and return to YSB Tool."

                html = f"""<!doctype html>
<html><head><meta charset=\"utf-8\"><title>YSB Tool</title></head>
<body style=\"font-family:Arial,sans-serif;background:#111;color:#eee;padding:32px;\">
<h2>{title}</h2>
<p>{body}</p>
</body></html>""".encode("utf-8")
                try:
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(html)))
                    self.end_headers()
                    self.wfile.write(html)
                finally:
                    callback_received.set()

        # 포트 0으로 OS가 빈 포트를 배정하게 한다.
        server = HTTPServer(("localhost", 0), OAuthCallbackHandler)
        server.timeout = 0.25
        host, port = server.server_address
        redirect_uri = f"http://localhost:{port}/"
        flow.redirect_uri = redirect_uri

        # CSRF 방지용 state는 google-auth-oauthlib가 반환한 값을 검증한다.
        auth_url, expected_state = flow.authorization_url(
            access_type="offline",
            prompt="consent",
            include_granted_scopes="true",
        )

        def serve_until_done():
            try:
                while not callback_received.is_set() and not cancel_requested.is_set():
                    server.handle_request()
            finally:
                try:
                    server.server_close()
                except Exception:
                    pass

        thread = threading.Thread(target=serve_until_done, daemon=True)
        thread.start()

        progress = QProgressDialog(parent or self)
        progress.setWindowTitle(self.tr_ui("클라우드 등록"))
        progress.setLabelText(self.tr_ui("브라우저에서 Google 로그인을 완료해 주세요.\n로그인을 취소했거나 창을 닫았다면 아래 취소를 누르세요."))
        progress.setCancelButtonText(self.tr_ui("취소"))
        progress.setRange(0, 0)
        progress.setMinimumDuration(0)
        progress.setWindowModality(Qt.WindowModality.ApplicationModal)
        progress.setAutoClose(False)
        progress.setAutoReset(False)
        progress.show()

        try:
            webbrowser.open(auth_url)
        except Exception as e:
            cancel_requested.set()
            try:
                progress.close()
            except Exception:
                pass
            raise RuntimeError(self.tr_ui("브라우저를 열 수 없습니다." ) + f"\n{e}")

        timeout_seconds = 300
        deadline = time.time() + timeout_seconds
        try:
            while not callback_received.is_set():
                QApplication.processEvents(QEventLoop.ProcessEventsFlag.AllEvents, 50)
                if progress.wasCanceled():
                    cancel_requested.set()
                    raise CloudOAuthCancelled(self.tr_ui("클라우드 등록이 취소되었습니다."))
                if time.time() > deadline:
                    cancel_requested.set()
                    raise CloudOAuthCancelled(self.tr_ui("제한 시간 안에 Google 로그인이 완료되지 않아 클라우드 등록을 취소했습니다."))
                time.sleep(0.05)
        finally:
            cancel_requested.set()
            try:
                progress.close()
            except Exception:
                pass
            try:
                thread.join(timeout=1.0)
            except Exception:
                pass

        if result.get("error"):
            error = str(result.get("error") or "")
            desc = str(result.get("error_description") or "")
            if error in {"access_denied", "user_cancelled", "consent_required"}:
                raise CloudOAuthCancelled(self.tr_ui("Google 로그인이 취소되었습니다."))
            raise RuntimeError(f"OAuth error: {error}\n{desc}".strip())

        if expected_state and result.get("state") and result.get("state") != expected_state:
            raise RuntimeError(self.tr_ui("OAuth 응답 검증에 실패했습니다. 다시 시도해 주세요."))

        code = str(result.get("code") or "")
        if not code:
            raise CloudOAuthCancelled(self.tr_ui("Google 로그인 응답을 받지 못해 클라우드 등록을 취소했습니다."))

        # code를 토큰으로 교환한다. 여기서 실패하면 실제 등록 실패로 처리한다.
        flow.fetch_token(code=code)
        creds = flow.credentials
        if not creds:
            raise RuntimeError(self.tr_ui("Google OAuth 토큰을 가져오지 못했습니다."))

        # 연결 검증 겸 계정 정보를 최대한 가져온다.
        account_email = ""
        try:
            drive = build("drive", "v3", credentials=creds)
            about = drive.about().get(fields="user").execute()
            user = about.get("user") if isinstance(about, dict) else {}
            account_email = str((user or {}).get("emailAddress") or "")
        except Exception:
            account_email = ""

        self.cloud_token_path().parent.mkdir(parents=True, exist_ok=True)
        with open(self.cloud_token_path(), "w", encoding="utf-8") as f:
            f.write(creds.to_json())

        # client_secret도 캐시 폴더에 복사해 두면 원본 JSON 위치가 바뀌어도 토큰 갱신에 쓸 수 있다.
        cached_secret = self.copy_cloud_client_secret(client_secret_path)

        cfg = self.load_cloud_config()
        cfg.update({
            "provider": "google_drive",
            "registered": True,
            "registered_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "account_email": account_email,
            "scopes": scopes,
            "client_secret_path": str(cached_secret),
            "token_path": str(self.cloud_token_path()),
        })
        self.save_cloud_config(cfg)
        return cfg

    def ensure_google_drive_credentials(self, parent=None):
        """클라우드 작업 전 등록 여부와 토큰 상태를 확인한다. 실제 Drive API 작업 연결 전 준비 단계."""
        if not self.cloud_token_path().exists():
            QMessageBox.information(
                parent or self,
                self.tr_ui("클라우드 등록 필요"),
                self.tr_ui("Google Drive 계정이 아직 등록되어 있지 않습니다.\n먼저 클라우드 등록을 진행해 주세요."),
            )
            return None
        try:
            InstalledAppFlow, Credentials, Request, build = self.import_google_oauth_modules()
            creds = Credentials.from_authorized_user_file(str(self.cloud_token_path()), ["https://www.googleapis.com/auth/drive.file"])
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
                with open(self.cloud_token_path(), "w", encoding="utf-8") as f:
                    f.write(creds.to_json())
            return creds
        except Exception as e:
            QMessageBox.warning(parent or self, self.tr_ui("클라우드 연결 확인 실패"), str(e))
            return None

    def cloud_refresh_status_widgets(self, *extra_labels):
        """클라우드 등록/해제 뒤 열린 창의 상태 문구를 즉시 갱신한다."""
        status = self.cloud_status_text()
        labels = list(extra_labels or [])
        for attr in ("_cloud_register_status_label", "_cloud_overview_status_label"):
            lbl = getattr(self, attr, None)
            if lbl is not None:
                labels.append(lbl)
        for lbl in labels:
            try:
                if lbl is not None:
                    if lbl is getattr(self, "_cloud_overview_status_label", None):
                        lbl.setText(
                            self.tr_ui("클라우드 메뉴는 작업환경 캐시 백업/복원과 백업 삭제를 관리합니다.")
                            + "\n"
                            + self.tr_ui("현재 상태")
                            + ": "
                            + status
                        )
                    else:
                        lbl.setText(status)
                    lbl.update()
                    lbl.repaint()
            except Exception:
                pass
        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.repaint()
        except Exception:
            pass

    def cloud_prompt_password(self, title, message, confirm=False, parent=None):
        """API 키 포함 백업/복원용 암호 입력. 확인용 재입력 옵션 지원."""
        parent = parent or self
        password, ok = QInputDialog.getText(
            parent,
            self.tr_ui(title),
            self.tr_ui(message),
            QLineEdit.EchoMode.Password,
        )
        if not ok:
            return None
        password = str(password or "")
        if not password:
            QMessageBox.warning(parent, self.tr_ui(title), self.tr_ui("암호를 비워둘 수 없습니다."))
            return None
        if confirm:
            password2, ok2 = QInputDialog.getText(
                parent,
                self.tr_ui(title),
                self.tr_ui("확인을 위해 암호를 한 번 더 입력하세요."),
                QLineEdit.EchoMode.Password,
            )
            if not ok2:
                return None
            if password != str(password2 or ""):
                QMessageBox.warning(parent, self.tr_ui(title), self.tr_ui("입력한 암호가 서로 다릅니다."))
                return None
        return password

    def cloud_crypto_derive_key(self, password, salt, iterations=200000):
        return hashlib.pbkdf2_hmac("sha256", str(password).encode("utf-8"), salt, int(iterations), dklen=32)

    def cloud_crypto_keystream(self, key, nonce, length):
        out = bytearray()
        counter = 0
        while len(out) < int(length):
            out.extend(hashlib.sha256(key + nonce + counter.to_bytes(8, "big")).digest())
            counter += 1
        return bytes(out[:length])

    def cloud_crypto_xor(self, data, stream):
        return bytes((a ^ b) for a, b in zip(data, stream))

    def cloud_encrypt_bytes(self, plain_bytes, password):
        """외부 의존성 없는 1차 암호화 컨테이너.
        PBKDF2 + SHA256 기반 keystream + HMAC으로 평문 API 캐시 업로드를 막는다.
        """
        plain_bytes = bytes(plain_bytes or b"")
        salt = os.urandom(16)
        nonce = os.urandom(16)
        iterations = 200000
        key = self.cloud_crypto_derive_key(password, salt, iterations=iterations)
        stream = self.cloud_crypto_keystream(key, nonce, len(plain_bytes))
        cipher = self.cloud_crypto_xor(plain_bytes, stream)
        header = b"YSB-CLOUD-ENC-v1"
        mac = hmac.new(key, header + salt + nonce + cipher, hashlib.sha256).hexdigest()
        payload = {
            "format": "YSB-CLOUD-ENC-v1",
            "kdf": "PBKDF2-HMAC-SHA256",
            "iterations": iterations,
            "cipher": "SHA256-CTR-XOR",
            "salt": base64.b64encode(salt).decode("ascii"),
            "nonce": base64.b64encode(nonce).decode("ascii"),
            "hmac": mac,
            "data": base64.b64encode(cipher).decode("ascii"),
        }
        return json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")

    def cloud_decrypt_bytes(self, encrypted_bytes, password):
        payload = json.loads(bytes(encrypted_bytes or b"").decode("utf-8"))
        if payload.get("format") != "YSB-CLOUD-ENC-v1":
            raise RuntimeError(self.tr_ui("지원하지 않는 암호화 형식입니다."))
        salt = base64.b64decode(payload.get("salt", ""))
        nonce = base64.b64decode(payload.get("nonce", ""))
        cipher = base64.b64decode(payload.get("data", ""))
        iterations = int(payload.get("iterations", 200000) or 200000)
        key = self.cloud_crypto_derive_key(password, salt, iterations=iterations)
        header = b"YSB-CLOUD-ENC-v1"
        expected = hmac.new(key, header + salt + nonce + cipher, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, str(payload.get("hmac", ""))):
            raise RuntimeError(self.tr_ui("암호가 틀렸거나 암호화 파일이 손상되었습니다."))
        stream = self.cloud_crypto_keystream(key, nonce, len(cipher))
        return self.cloud_crypto_xor(cipher, stream)

    def read_cloud_backup_manifest(self, zip_path):
        try:
            with zipfile.ZipFile(zip_path, "r") as z:
                return json.loads(z.read("manifest.json").decode("utf-8"))
        except Exception:
            return {}

    def reload_runtime_caches_after_cloud_restore(self):
        """클라우드 캐시 복원 후 재시작 없이 즉시 반영 가능한 설정을 다시 읽는다."""
        try:
            self.app_options = load_app_options()
            self.sync_translation_option_cache_to_config()
            self.sync_analysis_mask_options_to_config()

            self.auto_save_enabled = bool(self.app_options.get("auto_save_enabled", False))
            try:
                if hasattr(self, "act_auto_save_mode"):
                    self.act_auto_save_mode.blockSignals(True)
                    self.act_auto_save_mode.setChecked(self.auto_save_enabled)
                    self.act_auto_save_mode.blockSignals(False)
            except Exception:
                pass

            self.ui_theme = str(self.app_options.get(UI_THEME_KEY, self.ui_theme) or THEME_DARK).lower()
            if self.ui_theme not in (THEME_DARK, THEME_LIGHT):
                self.ui_theme = THEME_DARK
            self.ui_language = normalize_ui_language(self.app_options.get(UI_LANGUAGE_KEY, self.ui_language))

            self.api_settings = ApiSettingsStore.load()
            apply_settings_to_config(self.api_settings)
            try:
                self.restart_engine(show_error=False)
            except Exception:
                pass

            self.shortcut_settings = ShortcutSettingsStore.load()
            self.apply_shortcuts()

            self.load_text_preset_cache()
            self.load_item_text_preset_cache()

            self.apply_theme(self.ui_theme)
            self.apply_language(self.ui_language)
            self.workspace_root = str(get_workspace_root())
            self.log("☁️ 클라우드 캐시 복원 후 런타임 설정을 자동 갱신했습니다.")
            return True
        except Exception as e:
            try:
                self.log(f"⚠️ 클라우드 캐시 자동 갱신 실패: {e}")
            except Exception:
                pass
            return False

    def build_google_drive_service(self, creds):
        """등록된 OAuth 토큰으로 Google Drive API service를 만든다."""
        try:
            InstalledAppFlow, Credentials, Request, build = self.import_google_oauth_modules()
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            raise RuntimeError(f"{self.tr_ui('Google Drive 서비스 생성 실패')}: {e}")

    def import_google_drive_media_modules(self):
        try:
            from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
            return MediaFileUpload, MediaIoBaseDownload
        except Exception as e:
            raise ImportError(
                self.tr_ui("Google Drive 파일 업로드/다운로드 모듈을 불러올 수 없습니다.")
                + f"\n\n{e}"
            )

    def drive_escape_query_text(self, text_value):
        return str(text_value or "").replace("\\", "\\\\").replace("'", "\\'")

    def drive_find_folder(self, service, name, parent_id=None):
        name_q = self.drive_escape_query_text(name)
        q = f"name = '{name_q}' and mimeType = 'application/vnd.google-apps.folder' and trashed = false"
        if parent_id:
            q += f" and '{parent_id}' in parents"
        result = service.files().list(
            q=q,
            spaces="drive",
            fields="files(id,name)",
            pageSize=10,
        ).execute()
        files = result.get("files", []) if isinstance(result, dict) else []
        return files[0] if files else None

    def drive_find_or_create_folder(self, service, name, parent_id=None):
        found = self.drive_find_folder(service, name, parent_id=parent_id)
        if found:
            return found.get("id")
        metadata = {
            "name": name,
            "mimeType": "application/vnd.google-apps.folder",
        }
        if parent_id:
            metadata["parents"] = [parent_id]
        folder = service.files().create(
            body=metadata,
            fields="id,name",
        ).execute()
        return folder.get("id")

    def ensure_cloud_drive_folders(self, service):
        # 공개 배포판의 Google Drive 연동은 작업환경 캐시 백업/복원 전용이다.
        # YSBT 프로젝트 파일은 사용자가 로컬 파일 또는 동기화 폴더로 직접 관리한다.
        root_id = self.drive_find_or_create_folder(service, "YSB_Translator_Backup")
        cache_id = self.drive_find_or_create_folder(service, "cache_backups", parent_id=root_id)
        cfg = self.load_cloud_config()
        cfg.update({
            "drive_root_folder_id": root_id,
            "drive_cache_folder_id": cache_id,
            "drive_project_folder_id": "",
            "drive_folder_checked_at": time.strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.save_cloud_config(cfg)
        return root_id, cache_id, None

    def cloud_backup_manifest(self, backup_type="cache", include_api_keys=False):
        cfg = self.load_cloud_config()
        return {
            "app": "YSB Translator",
            "backup_type": backup_type,
            "created_at": time.strftime("%Y-%m-%d %H:%M:%S"),
            "include_api_keys": bool(include_api_keys),
            "ui_language": getattr(self, "ui_language", LANG_KO),
            "provider": "google_drive",
            "account_email": cfg.get("account_email", ""),
            "format_version": 1,
        }

    def iter_cache_backup_sources(self, include_api_keys=False):
        """백업할 작업환경 캐시 파일 목록을 (실제경로, ZIP 내부경로)로 반환한다.
        API 키 제외가 기본이며, cloud/work_sessions 같은 임시성/토큰성 폴더는 제외한다.
        """
        cache_root = get_cache_dir()
        excluded_dirs = {"cloud", "work_sessions", "__pycache__", "recent_thumbnails"}
        excluded_files = {
            "google_drive_token.json",
            "cloud_config.json",
            "google_oauth_client_secret.json",
            "api_cache.json",
            "recent_projects.json",
        }

        if cache_root.exists():
            for p in cache_root.rglob("*"):
                if not p.is_file():
                    continue
                try:
                    rel = p.relative_to(cache_root)
                except Exception:
                    continue
                parts = set(rel.parts)
                if parts & excluded_dirs:
                    continue
                if p.name in excluded_files:
                    continue
                yield p, Path("cache") / rel

        # 작업 폴더 위치 설정은 Windows 사용자 설정 폴더에 있으므로 별도 포함한다.
        try:
            config_root = app_config_dir()
            workspace_cfg = config_root / "workspace_config.json"
            if workspace_cfg.exists():
                yield workspace_cfg, Path("config") / "workspace_config.json"
        except Exception:
            pass

    def create_cache_backup_zip(self, include_api_keys=False, api_password=None):
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = self.cloud_dir() / "local_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        zip_path = backup_dir / f"YSB_cache_backup_{ts}.zip"

        manifest = self.cloud_backup_manifest("cache", include_api_keys=include_api_keys)
        if include_api_keys:
            manifest["api_key_encryption"] = "YSB-CLOUD-ENC-v1"
        added = 0
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(manifest, ensure_ascii=False, indent=2))
            for src, arc in self.iter_cache_backup_sources(include_api_keys=include_api_keys):
                try:
                    z.write(src, str(arc).replace("\\", "/"))
                    added += 1
                except Exception as e:
                    try:
                        self.log(f"⚠️ 캐시 백업 항목 제외: {src} / {e}")
                    except Exception:
                        pass

            if include_api_keys:
                api_file = get_cache_file("api_cache.json")
                if api_file.exists():
                    if not api_password:
                        raise RuntimeError(self.tr_ui("API 키 포함 백업에는 암호가 필요합니다."))
                    encrypted = self.cloud_encrypt_bytes(api_file.read_bytes(), api_password)
                    z.writestr("secure/api_cache.json.enc", encrypted)
                    added += 1
        if added <= 0:
            raise RuntimeError(self.tr_ui("백업할 캐시 파일을 찾지 못했습니다."))
        return zip_path, added

    def upload_file_to_drive_folder(self, service, local_path, folder_id, mime_type="application/zip"):
        MediaFileUpload, MediaIoBaseDownload = self.import_google_drive_media_modules()
        local_path = Path(local_path)
        metadata = {
            "name": local_path.name,
            "parents": [folder_id],
        }
        media = MediaFileUpload(str(local_path), mimetype=mime_type, resumable=True)
        uploaded = service.files().create(
            body=metadata,
            media_body=media,
            fields="id,name,webViewLink,size,createdTime",
        ).execute()
        return uploaded

    def list_drive_files_in_folder(self, service, folder_id, name_prefix=""):
        q = f"'{folder_id}' in parents and trashed = false"
        if name_prefix:
            q += f" and name contains '{self.drive_escape_query_text(name_prefix)}'"
        files = []
        page_token = None
        while True:
            res = service.files().list(
                q=q,
                spaces="drive",
                fields="nextPageToken, files(id,name,size,createdTime,modifiedTime,webViewLink)",
                orderBy="modifiedTime desc",
                pageSize=50,
                pageToken=page_token,
            ).execute()
            files.extend(res.get("files", []) if isinstance(res, dict) else [])
            page_token = res.get("nextPageToken") if isinstance(res, dict) else None
            if not page_token:
                break
        return files

    def format_drive_time_local(self, iso_text):
        """Google Drive UTC ISO 시간을 현재 PC의 로컬 시간대로 변환해 표시한다.
        내부 정렬/비교에는 Drive의 원본 UTC 값을 유지하고, 사용자 표시만 로컬 시간으로 바꾼다.
        """
        if not iso_text:
            return ""
        try:
            raw = str(iso_text).strip()
            # Google Drive API 예: 2026-05-19T04:11:43.723Z
            dt_utc = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            dt_local = dt_utc.astimezone()  # Windows/OS 현재 시간대 기준
            return dt_local.strftime("%Y-%m-%d %H:%M:%S")
        except Exception:
            return str(iso_text)

    def format_drive_file_size(self, size_value):
        try:
            n = int(size_value or 0)
        except Exception:
            return str(size_value or "")
        units = ["bytes", "KB", "MB", "GB", "TB"]
        value = float(n)
        idx = 0
        while value >= 1024 and idx < len(units) - 1:
            value /= 1024.0
            idx += 1
        if idx == 0:
            return f"{n} bytes"
        return f"{value:.1f} {units[idx]}"

    def format_drive_backup_label(self, drive_file):
        name = drive_file.get("name", "(no name)") if isinstance(drive_file, dict) else "(no name)"
        iso_time = ""
        size = ""
        if isinstance(drive_file, dict):
            iso_time = drive_file.get("modifiedTime") or drive_file.get("createdTime") or ""
            size = drive_file.get("size", "")
        local_time = self.format_drive_time_local(iso_time)
        size_label = self.format_drive_file_size(size)
        parts = [name]
        if local_time:
            parts.append(local_time)
        if size_label:
            parts.append(size_label)
        return "  /  ".join(parts)

    def choose_drive_backup_file(self, service, folder_id, title, prefix):
        files = self.list_drive_files_in_folder(service, folder_id, name_prefix=prefix)
        if not files:
            QMessageBox.information(
                self,
                self.tr_ui(title),
                self.tr_ui("클라우드에 백업 파일이 없습니다."),
            )
            return None

        labels = []
        mapping = {}
        for f in files:
            label = self.format_drive_backup_label(f)
            labels.append(label)
            mapping[label] = f

        choice, ok = QInputDialog.getItem(
            self,
            self.tr_ui(title),
            self.tr_ui("불러올 백업 파일을 선택하세요."),
            labels,
            0,
            False,
        )
        if not ok or not choice:
            return None
        return mapping.get(choice)

    def download_drive_file(self, service, file_id, local_path):
        MediaFileUpload, MediaIoBaseDownload = self.import_google_drive_media_modules()
        request = service.files().get_media(fileId=file_id)
        local_path = Path(local_path)
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            downloader = MediaIoBaseDownload(f, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
        return local_path

    def create_local_restore_safety_backup(self):
        """클라우드 캐시를 덮어쓰기 전에 현재 로컬 캐시를 백업한다."""
        ts = time.strftime("%Y%m%d_%H%M%S")
        backup_dir = self.cloud_dir() / "restore_safety_backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        zip_path = backup_dir / f"YSB_local_before_restore_{ts}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("manifest.json", json.dumps(self.cloud_backup_manifest("local_before_restore", include_api_keys=False), ensure_ascii=False, indent=2))
            for src, arc in self.iter_cache_backup_sources(include_api_keys=False):
                try:
                    z.write(src, str(arc).replace("\\", "/"))
                except Exception:
                    pass
        return zip_path

    def safe_extract_cache_backup_zip(self, zip_path, apply_api_keys=False, api_password=None):
        """Drive에서 받은 캐시 백업 ZIP을 현재 캐시 폴더에 적용한다."""
        zip_path = Path(zip_path)
        if not zip_path.exists():
            raise FileNotFoundError(str(zip_path))

        cache_root = get_cache_dir().resolve()
        config_root = app_config_dir().resolve()

        with zipfile.ZipFile(zip_path, "r") as z:
            manifest = {}
            try:
                manifest = json.loads(z.read("manifest.json").decode("utf-8"))
            except Exception:
                manifest = {}

            if manifest.get("include_api_keys") and not apply_api_keys:
                raise RuntimeError(self.tr_ui("이 백업에는 API 키가 포함되어 있습니다. API 키까지 복원하려면 암호가 필요합니다."))
            if manifest.get("include_api_keys") and apply_api_keys and not api_password:
                raise RuntimeError(self.tr_ui("API 키 포함 백업 복원에는 암호가 필요합니다."))

            for info in z.infolist():
                name = info.filename.replace("\\", "/")
                if not name or name.endswith("/") or name == "manifest.json":
                    continue
                if ".." in Path(name).parts:
                    continue

                if name.startswith("cache/"):
                    rel = Path(name[len("cache/"):])
                    if rel.parts and rel.parts[0] in ("cloud", "work_sessions", "__pycache__"):
                        continue
                    if rel.name == "api_cache.json" and not apply_api_keys:
                        continue
                    dest = (cache_root / rel).resolve()
                    if not str(dest).startswith(str(cache_root)):
                        continue
                elif name.startswith("config/"):
                    rel = Path(name[len("config/"):])
                    if rel.name != "workspace_config.json":
                        continue
                    dest = (config_root / rel).resolve()
                    if not str(dest).startswith(str(config_root)):
                        continue
                else:
                    continue

                dest.parent.mkdir(parents=True, exist_ok=True)
                with z.open(info, "r") as src, open(dest, "wb") as out:
                    shutil.copyfileobj(src, out)

            if manifest.get("include_api_keys") and apply_api_keys:
                try:
                    encrypted_api = z.read("secure/api_cache.json.enc")
                except Exception:
                    encrypted_api = None
                if not encrypted_api:
                    raise RuntimeError(self.tr_ui("암호화된 API 설정 파일을 찾지 못했습니다."))
                plain_api = self.cloud_decrypt_bytes(encrypted_api, api_password)
                api_dest = (cache_root / "api_cache.json").resolve()
                api_dest.parent.mkdir(parents=True, exist_ok=True)
                with open(api_dest, "wb") as f:
                    f.write(plain_api)

        return True

    def format_drive_upload_result_message(self, uploaded, local_path=None, item_count=None):
        parts = [self.tr_ui("클라우드 백업이 완료되었습니다.")]
        if uploaded:
            name = uploaded.get("name", "")
            link = uploaded.get("webViewLink", "")
            if name:
                parts.append(f"\n{self.tr_ui('파일')}: {name}")
            created_local = self.format_drive_time_local(uploaded.get("createdTime", ""))
            if created_local:
                parts.append(f"\n{self.tr_ui('백업 시간')}: {created_local}")
            if link:
                parts.append(f"\n{self.tr_ui('링크')}: {link}")
        if item_count is not None:
            parts.append(f"\n{self.tr_ui('백업 항목')}: {item_count}")
        if local_path:
            parts.append(f"\n{self.tr_ui('로컬 백업 파일')}: {local_path}")
        return "\n".join(parts)

    def _cloud_action_dialog(self, title, description, action_text=None, action_callback=None, extra_builder=None, min_width=760, min_height=360):
        """클라우드 메뉴/허브에서 공통으로 쓰는 개별 동작 창.
        메뉴에서 직접 눌러도 이 전용 창이 뜨고, 허브에서 눌러도 같은 창이 뜬다.
        """
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui(title))
        dlg.resize(min_width, min_height)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title_label = QLabel(self.tr_ui(title), dlg)
        title_label.setObjectName("SettingsDialogTitle")
        root.addWidget(title_label)

        desc_label = QLabel(self.tr_ui(description), dlg)
        desc_label.setObjectName("SettingsDescription")
        desc_label.setWordWrap(True)
        root.addWidget(desc_label)

        content = QFrame(dlg)
        content.setObjectName("SettingsBlock")
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(16, 14, 16, 14)
        content_layout.setSpacing(10)
        root.addWidget(content, 1)

        context = {}
        if callable(extra_builder):
            try:
                extra_builder(content_layout, dlg, context)
            except TypeError:
                extra_builder(content_layout, dlg)

        content_layout.addStretch(1)

        btns = QDialogButtonBox(dlg)
        if action_text and callable(action_callback):
            run_btn = btns.addButton(self.tr_ui(action_text), QDialogButtonBox.ButtonRole.AcceptRole)
            try:
                run_btn.setAutoDefault(True)
                run_btn.setDefault(True)
            except Exception:
                pass
            def _run():
                action_callback(dlg, context)
            run_btn.clicked.connect(_run)
        close_btn = btns.addButton(self.tr_ui("닫기"), QDialogButtonBox.ButtonRole.RejectRole)
        close_btn.clicked.connect(dlg.reject)
        root.addWidget(btns)
        dlg.exec()

    def _cloud_info_row(self, layout, title, description):
        item = QFrame()
        item.setObjectName("SettingsItem")
        item_layout = QVBoxLayout(item)
        item_layout.setContentsMargins(12, 10, 12, 10)
        item_layout.setSpacing(4)
        t = QLabel(self.tr_ui(title), item)
        t.setObjectName("SettingsItemTitle")
        item_layout.addWidget(t)
        d = QLabel(self.tr_ui(description), item)
        d.setObjectName("SettingsDescription")
        d.setWordWrap(True)
        item_layout.addWidget(d)
        layout.addWidget(item)
        return d

    def _show_cloud_placeholder(self, title, message, parent=None):
        self.show_ok_notice(title, message, parent=parent or self)

    def cloud_register(self):
        def build(layout, dlg, ctx):
            self._cloud_info_row(
                layout,
                "연결 대상",
                "Google Drive 계정을 OAuth로 연결합니다. 등록 버튼을 누르면 브라우저가 열리고, Google 로그인/권한 허용을 완료하면 로컬 토큰이 저장됩니다.",
            )
            status_label = self._cloud_info_row(
                layout,
                "현재 상태",
                self.cloud_status_text(),
            )
            ctx["cloud_status_label"] = status_label
            self._cloud_register_status_label = status_label
            self._cloud_info_row(
                layout,
                "보안 안내",
                "OAuth 토큰은 현재 PC의 로컬 캐시에 저장됩니다. 등록 해제 시 이 토큰을 삭제합니다. Google OAuth 클라이언트 JSON은 Drive API 로그인 시작에만 사용됩니다.",
            )

            cfg = self.load_cloud_config()
            detected_secret = self.find_default_cloud_client_secret()
            cached_secret = str(cfg.get("client_secret_path") or "")
            if cached_secret and self.is_valid_google_oauth_client_secret(cached_secret):
                detected_secret = cached_secret
            if detected_secret:
                ctx["client_secret_path"] = detected_secret
                oauth_desc = "OAuth 설정이 준비되어 있습니다. Google 로그인 버튼을 누르면 브라우저에서 Google 계정 연결을 시작합니다."
            else:
                oauth_desc = "OAuth 설정을 찾지 못했습니다. 배포본에 cloud_oauth_client.json이 포함되어 있는지 확인해 주세요."

            self._cloud_info_row(
                layout,
                "Google 로그인",
                oauth_desc,
            )

        def run(dlg, ctx):
            client_secret_path = str(ctx.get("client_secret_path") or "") or self.find_default_cloud_client_secret()
            if not client_secret_path:
                self.show_ok_notice(
                    "클라우드 등록",
                    "Google OAuth 설정이 없어 로그인을 시작할 수 없습니다. 배포본에 cloud_oauth_client.json이 포함되어 있는지 확인해 주세요.",
                    parent=dlg,
                )
                return

            if not self.ask_yes_no_shortcut(
                "클라우드 등록",
                "브라우저를 열어 Google Drive 로그인을 시작할까요?",
                yes_text="로그인",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Question,
                parent=dlg,
            ):
                return

            try:
                cfg = self.run_google_drive_oauth(client_secret_path, parent=dlg)
            except CloudOAuthCancelled as e:
                self.show_ok_notice(
                    "클라우드 등록 취소",
                    str(e) or "클라우드 등록이 취소되었습니다.",
                    parent=dlg,
                )
                return
            except ImportError as e:
                QMessageBox.warning(dlg, self.tr_ui("클라우드 등록 준비 필요"), str(e))
                return
            except Exception as e:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드 등록 실패"),
                    self.tr_ui("Google Drive 계정 등록에 실패했습니다.") + f"\n\n{e}",
                )
                return

            self.cloud_refresh_status_widgets(ctx.get("cloud_status_label"))
            account = str(cfg.get("account_email") or "").strip()
            msg = "Google Drive 계정 등록이 완료되었습니다."
            if account:
                msg += f"\n\n{account}"
            self.show_ok_notice("클라우드 등록 완료", msg, parent=dlg)
            try:
                self.log(f"☁️ 클라우드 등록 완료: {account or 'Google Drive'}")
            except Exception:
                pass

        self._cloud_action_dialog(
            "클라우드 등록",
            "클라우드 백업/불러오기를 사용하려면 먼저 Google Drive 계정을 연결해야 합니다.",
            "Google 로그인",
            run,
            build,
            min_height=520,
        )

    def cloud_unregister(self):
        def build(layout, dlg, ctx):
            status_label = self._cloud_info_row(
                layout,
                "현재 상태",
                self.cloud_status_text(),
            )
            ctx["cloud_status_label"] = status_label
            self._cloud_register_status_label = status_label
            self._cloud_info_row(
                layout,
                "해제 범위",
                "현재 PC에 저장된 Google Drive OAuth 토큰과 클라우드 설정 캐시를 삭제합니다. 이후 클라우드 백업/복원 기능은 다시 등록해야 사용할 수 있습니다.",
            )
            self._cloud_info_row(
                layout,
                "주의",
                "등록 해제는 로컬 연결 정보를 지우는 작업입니다. 클라우드에 이미 올라간 백업 파일은 별도 삭제하지 않습니다.",
            )
        def run(dlg, ctx):
            if not self.ask_yes_no_shortcut(
                "클라우드 등록 해제",
                "클라우드 등록을 해제할까요?",
                yes_text="해제",
                no_text="취소",
                default_yes=False,
                icon=QMessageBox.Icon.Warning,
                parent=dlg,
            ):
                return

            revoke_log = ""
            try:
                if self.cloud_token_path().exists():
                    try:
                        InstalledAppFlow, Credentials, Request, build = self.import_google_oauth_modules()
                        creds = Credentials.from_authorized_user_file(str(self.cloud_token_path()), ["https://www.googleapis.com/auth/drive.file"])
                        try:
                            creds.revoke(Request())
                            revoke_log = "Google 인증 토큰 해제 요청 완료"
                        except Exception as e:
                            revoke_log = f"Google 인증 토큰 해제 요청 실패, 로컬 연결 정보만 삭제: {e}"
                    except Exception as e:
                        revoke_log = f"Google 라이브러리 로드 실패, 로컬 연결 정보만 삭제: {e}"
            except Exception as e:
                revoke_log = f"클라우드 등록 해제 사전 처리 중 예외, 로컬 연결 정보 삭제 진행: {e}"

            removed = []
            for p in (self.cloud_token_path(), self.cloud_config_path(), self.cloud_client_secret_path()):
                try:
                    if p.exists():
                        p.unlink()
                        removed.append(str(p))
                except Exception as e:
                    try:
                        self.log(f"⚠️ 클라우드 연결 정보 삭제 실패: {p} / {e}")
                    except Exception:
                        pass

            self.cloud_refresh_status_widgets(ctx.get("cloud_status_label"))
            self.show_ok_notice(
                "클라우드 등록 해제",
                "Google Drive 계정 연결이 해제되었습니다.",
                parent=dlg,
            )
            try:
                self.log("☁️ 클라우드 등록 해제 완료")
            except Exception:
                pass

        self._cloud_action_dialog(
            "클라우드 등록 해제",
            "이 PC에서 클라우드 연결을 끊는 전용 창입니다.",
            "해제",
            run,
            build,
        )

    def cloud_backup_cache(self):

        def build(layout, dlg, ctx):
            self._cloud_info_row(
                layout,
                "백업 대상",
                "옵션, 단축키, 매크로, 글꼴 프리셋, 번역 프롬프트, 단어장 같은 작업환경 캐시를 클라우드에 백업합니다.",
            )
            api_box = QFrame(dlg)
            api_box.setObjectName("SettingsItem")
            api_layout = QVBoxLayout(api_box)
            api_layout.setContentsMargins(12, 10, 12, 10)
            api_layout.setSpacing(6)
            cb = QCheckBox(self.tr_ui("API 키까지 백업"), api_box)
            cb.setToolTip(self.tr_ui("API 키는 유료 API 접근 정보일 수 있으므로, 선택한 경우 암호화가 필수입니다."))
            api_layout.addWidget(cb)
            ctx["include_api_keys_checkbox"] = cb
            api_desc = QLabel(self.tr_ui("기본값은 API 키 제외입니다. API 키까지 백업을 체크하면 업로드 전 반드시 암호화하고, 클라우드에서 불러올 때 반드시 복호화합니다. 암호화/복호화가 준비되지 않은 상태에서는 API 키 포함 백업을 실행하지 않습니다."), api_box)
            api_desc.setObjectName("SettingsDescription")
            api_desc.setWordWrap(True)
            api_layout.addWidget(api_desc)
            layout.addWidget(api_box)
            self._cloud_info_row(
                layout,
                "보안 규칙",
                "API 키는 평문으로 클라우드에 올리지 않습니다. API 키 포함 백업은 암호화 ZIP 또는 암호화된 별도 파일로 저장하고, 불러오기 단계에서 복호화 후 적용합니다.",
            )
        def run(dlg, ctx):
            cb = ctx.get("include_api_keys_checkbox")
            include_api = bool(cb.isChecked()) if cb is not None else False
            question = "현재 작업환경 캐시를 클라우드로 백업할까요?"
            if include_api:
                question = "API 키까지 포함하여 작업환경 캐시를 클라우드로 백업할까요? API 키는 업로드 전에 반드시 암호화됩니다."
            if not self.ask_yes_no_shortcut(
                "클라우드로 캐시 백업",
                question,
                yes_text="백업",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Warning if include_api else QMessageBox.Icon.Question,
                parent=dlg,
            ):
                return
            creds = self.ensure_google_drive_credentials(parent=dlg)
            if creds is None:
                return
            api_password = None
            if include_api:
                api_password = self.cloud_prompt_password(
                    "API 키 포함 캐시 백업",
                    "API 키를 암호화할 암호를 입력하세요. 이 암호를 잊으면 API 키 포함 백업은 복원할 수 없습니다.",
                    confirm=True,
                    parent=dlg,
                )
                if not api_password:
                    return
            try:
                service = self.build_google_drive_service(creds)
                root_id, cache_folder_id, project_folder_id = self.ensure_cloud_drive_folders(service)
                zip_path, item_count = self.create_cache_backup_zip(include_api_keys=include_api, api_password=api_password)
                uploaded = self.upload_file_to_drive_folder(service, zip_path, cache_folder_id, mime_type="application/zip")
            except Exception as e:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드로 캐시 백업 실패"),
                    self.tr_ui("캐시 백업을 클라우드에 올리지 못했습니다.") + f"\n\n{e}",
                )
                return
            self.show_ok_notice(
                "클라우드로 캐시 백업 완료",
                self.format_drive_upload_result_message(uploaded, local_path=str(zip_path), item_count=item_count),
                parent=dlg,
            )
            try:
                self.log(f"☁️ 캐시 백업 업로드 완료: {uploaded.get('name', '')}")
            except Exception:
                pass
        self._cloud_action_dialog(
            "클라우드로 캐시 백업",
            "현재 PC의 작업환경 캐시를 클라우드에 올리는 전용 창입니다. API 키는 별도 체크한 경우에만 포함하며, 포함 시 암호화가 필수입니다.",
            "백업",
            run,
            build,
            min_height=470,
        )

    def cloud_restore_cache(self):
        def build(layout, dlg, ctx):
            self._cloud_info_row(
                layout,
                "불러오기 대상",
                "클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용합니다. 실제 적용 전에는 현재 로컬 설정을 먼저 백업합니다.",
            )
            self._cloud_info_row(
                layout,
                "API 키 복호화 규칙",
                "백업에 API 키가 포함되어 있다면 반드시 복호화 과정을 거친 뒤에만 적용합니다. 복호화에 실패하면 API 키는 적용하지 않고, 기존 로컬 API 설정을 보호합니다.",
            )
            self._cloud_info_row(
                layout,
                "주의",
                "캐시 불러오기는 단축키, 프리셋, 옵션 같은 현재 작업환경을 바꿀 수 있습니다. 적용 전 확인창을 한 번 더 표시합니다.",
            )
        def run(dlg, ctx):
            if not self.ask_yes_no_shortcut(
                "클라우드에서 캐시 불러오기",
                "클라우드에 저장된 작업환경 캐시를 불러올까요? 현재 로컬 설정을 덮어쓸 수 있습니다.",
                yes_text="불러오기",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Warning,
                parent=dlg,
            ):
                return
            creds = self.ensure_google_drive_credentials(parent=dlg)
            if creds is None:
                return
            try:
                service = self.build_google_drive_service(creds)
                root_id, cache_folder_id, project_folder_id = self.ensure_cloud_drive_folders(service)
                selected = self.choose_drive_backup_file(service, cache_folder_id, "클라우드에서 캐시 불러오기", "YSB_cache_backup_")
                if not selected:
                    return
                if not self.ask_yes_no_shortcut(
                    "클라우드에서 캐시 불러오기",
                    f"{selected.get('name', '')}\n\n이 백업을 내려받아 현재 로컬 설정에 적용할까요?\n적용 전 현재 로컬 캐시는 안전 백업으로 저장됩니다.",
                    yes_text="적용",
                    no_text="취소",
                    default_yes=False,
                    icon=QMessageBox.Icon.Warning,
                    parent=dlg,
                ):
                    return
                safety = self.create_local_restore_safety_backup()
                download_dir = self.cloud_dir() / "downloads"
                download_dir.mkdir(parents=True, exist_ok=True)
                local_zip = download_dir / selected.get("name", "cloud_cache_backup.zip")
                self.download_drive_file(service, selected.get("id"), local_zip)
                manifest = self.read_cloud_backup_manifest(local_zip)
                apply_api = bool(manifest.get("include_api_keys"))
                api_password = None
                if apply_api:
                    api_password = self.cloud_prompt_password(
                        "API 키 포함 캐시 불러오기",
                        "이 백업에는 암호화된 API 설정이 포함되어 있습니다. 복호화 암호를 입력하세요.",
                        confirm=False,
                        parent=dlg,
                    )
                    if not api_password:
                        return
                self.safe_extract_cache_backup_zip(local_zip, apply_api_keys=apply_api, api_password=api_password)
                self.reload_runtime_caches_after_cloud_restore()
            except Exception as e:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드에서 캐시 불러오기 실패"),
                    self.tr_ui("클라우드 캐시 백업을 적용하지 못했습니다.") + f"\n\n{e}",
                )
                return
            self.show_ok_notice(
                "클라우드에서 캐시 불러오기 완료",
                "클라우드 캐시 백업을 적용하고 가능한 설정을 즉시 갱신했습니다.\n\n"
                + self.tr_ui("현재 로컬 설정 안전 백업")
                + f": {safety}\n"
                + self.tr_ui("작업 폴더 위치가 바뀐 백업이라면 재시작 후 완전히 반영됩니다."),
                parent=dlg,
            )
            try:
                self.log(f"☁️ 캐시 백업 복원 완료: {selected.get('name', '')}")
            except Exception:
                pass
        self._cloud_action_dialog(
            "클라우드에서 캐시 불러오기",
            "클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용하는 전용 창입니다.",
            "불러오기",
            run,
            build,
            min_height=450,
        )

    def delete_drive_file_permanently(self, service, file_id):
        service.files().delete(fileId=file_id).execute()

    def cloud_delete_cache_backups(self):
        def build(layout, dlg, ctx):
            self._cloud_info_row(
                layout,
                "삭제 대상",
                "Google Drive의 YSB_Translator_Backup/cache_backups 폴더에 저장된 작업환경 캐시 백업 ZIP만 삭제합니다. 프로젝트 파일은 공개 배포판 클라우드 백업 대상이 아닙니다.",
            )
            self._cloud_info_row(
                layout,
                "전체 백업 삭제",
                "클라우드에 있는 캐시 백업을 전부 삭제합니다. 이 작업은 되돌릴 수 없습니다.",
            )
            self._cloud_info_row(
                layout,
                "최신본만 남기기",
                "가장 최근에 수정된 캐시 백업 1개만 남기고 나머지 캐시 백업을 삭제합니다.",
            )

        def run(dlg, ctx):
            mode, ok = QInputDialog.getItem(
                dlg,
                self.tr_ui("클라우드 백업 삭제"),
                self.tr_ui("삭제 방식을 선택하세요."),
                [
                    self.tr_ui("최신 백업 1개만 남기고 삭제"),
                    self.tr_ui("전체 백업 삭제"),
                ],
                0,
                False,
            )
            if not ok or not mode:
                return

            creds = self.ensure_google_drive_credentials(parent=dlg)
            if creds is None:
                return

            try:
                service = self.build_google_drive_service(creds)
                root_id, cache_folder_id, _ = self.ensure_cloud_drive_folders(service)
                files = self.list_drive_files_in_folder(service, cache_folder_id, name_prefix="YSB_cache_backup_")
            except Exception as e:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드 백업 삭제 실패"),
                    self.tr_ui("클라우드 백업 목록을 불러오지 못했습니다.") + f"\n\n{e}",
                )
                return

            if not files:
                QMessageBox.information(
                    dlg,
                    self.tr_ui("클라우드 백업 삭제"),
                    self.tr_ui("삭제할 클라우드 캐시 백업이 없습니다."),
                )
                return

            delete_all = mode == self.tr_ui("전체 백업 삭제")
            if delete_all:
                targets = list(files)
                question = self.tr_ui("클라우드의 캐시 백업을 전부 삭제할까요?\n\n삭제 개수: {count}개\n이 작업은 되돌릴 수 없습니다.").format(count=len(targets))
            else:
                files_sorted = sorted(files, key=lambda f: str(f.get("modifiedTime") or f.get("createdTime") or ""), reverse=True)
                keep = files_sorted[0] if files_sorted else None
                targets = files_sorted[1:]
                if not targets:
                    QMessageBox.information(
                        dlg,
                        self.tr_ui("클라우드 백업 삭제"),
                        self.tr_ui("이미 최신 백업 1개만 남아 있습니다."),
                    )
                    return
                question = (
                    self.tr_ui("최신 캐시 백업 1개만 남기고 나머지를 삭제할까요?")
                    + "\n\n"
                    + self.tr_ui("남길 백업")
                    + f": {keep.get('name', '')}\n"
                    + self.tr_ui("삭제 개수")
                    + f": {len(targets)}개\n"
                    + self.tr_ui("이 작업은 되돌릴 수 없습니다.")
                )

            if not self.ask_yes_no_shortcut(
                "클라우드 백업 삭제",
                question,
                yes_text="삭제",
                no_text="취소",
                default_yes=False,
                icon=QMessageBox.Icon.Warning,
                parent=dlg,
            ):
                return

            deleted = 0
            errors = []
            for f in targets:
                try:
                    self.delete_drive_file_permanently(service, f.get("id"))
                    deleted += 1
                except Exception as e:
                    errors.append(f"{f.get('name', '')}: {e}")

            if errors:
                QMessageBox.warning(
                    dlg,
                    self.tr_ui("클라우드 백업 삭제 일부 실패"),
                    self.tr_ui("일부 백업을 삭제하지 못했습니다.")
                    + f"\n\n{self.tr_ui('삭제 성공')}: {deleted}개\n"
                    + "\n".join(errors[:10]),
                )
            else:
                self.show_ok_notice(
                    "클라우드 백업 삭제 완료",
                    self.tr_ui("클라우드 캐시 백업 삭제가 완료되었습니다.") + f"\n\n{self.tr_ui('삭제 개수')}: {deleted}개",
                    parent=dlg,
                )
            try:
                self.log(f"☁️ 클라우드 캐시 백업 삭제 완료: {deleted}개")
            except Exception:
                pass

        self._cloud_action_dialog(
            "클라우드 백업 삭제",
            "Google Drive에 저장된 작업환경 캐시 백업을 정리하는 전용 창입니다. 전체 삭제 또는 최신본 1개만 남기기를 선택할 수 있습니다.",
            "백업 삭제",
            run,
            build,
            min_height=470,
        )

    def cloud_backup_current_project(self):
        # 공개 배포판에서는 Google Drive 프로젝트 백업 기능을 제공하지 않는다.
        QMessageBox.information(
            self,
            self.tr_ui("기능 제거됨"),
            self.tr_ui("공개 배포판에서는 Google Drive 프로젝트 백업을 사용하지 않습니다. 프로젝트 파일은 로컬 파일 또는 사용자의 동기화 폴더로 직접 관리해 주세요."),
        )

    def cloud_restore_project_from_cloud(self):
        # 공개 배포판에서는 Google Drive 프로젝트 불러오기 기능을 제공하지 않는다.
        QMessageBox.information(
            self,
            self.tr_ui("기능 제거됨"),
            self.tr_ui("공개 배포판에서는 클라우드에서 프로젝트 불러오기를 사용하지 않습니다. 프로젝트 파일은 로컬 파일 또는 사용자의 동기화 폴더로 직접 관리해 주세요."),
        )

    def open_cloud_overview_dialog(self, include_project_backup=None):
        """홈화면/런처에서 쓰는 클라우드 허브 창.
        공개 배포판에서는 Google Drive 연동을 작업환경 캐시 백업/복원 전용으로 유지한다.
        include_project_backup 인자는 이전 버전 호환용으로만 남겨두며 사용하지 않는다.
        """
        include_project_backup = False

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("클라우드"))
        dlg.resize(800, 660)
        try:
            dlg.setStyleSheet(self.settings_dialog_style())
        except Exception:
            pass

        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("클라우드"), dlg)
        title.setObjectName("SettingsDialogTitle")
        root.addWidget(title)

        intro = QLabel(self.tr_ui("클라우드 메뉴는 작업환경 캐시 백업/복원과 백업 삭제를 관리합니다.") + "\n" + self.tr_ui("현재 상태") + ": " + self.cloud_status_text(), dlg)
        intro.setObjectName("SettingsDescription")
        intro.setWordWrap(True)
        self._cloud_overview_status_label = intro
        root.addWidget(intro)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget(scroll)
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        cloud_block, cloud_layout = self._settings_block(
            "클라우드",
            "Google Drive와 연결해 작업환경 캐시를 보존하고, 필요할 때 다시 불러오거나 오래된 백업을 정리하는 영역입니다.",
        )

        def add_cloud_item(title_text, description_text, button_text, slot):
            item = QFrame(dlg)
            item.setObjectName("SettingsItem")
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(12, 10, 12, 10)
            item_layout.setSpacing(12)
            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)
            t = QLabel(self.tr_ui(title_text), item)
            t.setObjectName("SettingsItemTitle")
            text_box.addWidget(t)
            d = QLabel(self.tr_ui(description_text), item)
            d.setObjectName("SettingsDescription")
            d.setWordWrap(True)
            text_box.addWidget(d)
            item_layout.addLayout(text_box, 1)
            btn = QPushButton(self.tr_ui(button_text), item)
            btn.setMinimumWidth(150)
            btn.clicked.connect(slot)
            item_layout.addWidget(btn, 0)
            cloud_layout.addWidget(item)

        add_cloud_item(
            "클라우드 등록",
            "Google Drive 계정을 연결합니다. 등록 후 작업환경 캐시 백업, 캐시 불러오기, 백업 삭제 기능을 사용할 수 있게 됩니다.",
            "등록",
            self.cloud_register,
        )
        add_cloud_item(
            "클라우드 등록 해제",
            "현재 PC에 저장된 클라우드 연결 토큰을 해제합니다. 이후 백업/불러오기 기능은 다시 등록해야 사용할 수 있습니다.",
            "해제",
            self.cloud_unregister,
        )
        add_cloud_item(
            "클라우드로 캐시 백업",
            "옵션, 단축키, 매크로, 프리셋, 프롬프트, 단어장 같은 작업환경 캐시를 백업합니다. API 키는 체크박스로 별도 선택하며, 포함 시 업로드 전 암호화와 불러오기 시 복호화가 필수입니다.",
            "캐시 백업",
            self.cloud_backup_cache,
        )
        add_cloud_item(
            "클라우드에서 캐시 불러오기",
            "클라우드에 저장된 작업환경 캐시를 내려받아 현재 PC에 적용합니다. API 키가 포함된 백업은 복호화 후에만 적용합니다.",
            "캐시 불러오기",
            self.cloud_restore_cache,
        )
        add_cloud_item(
            "클라우드 백업 삭제",
            "클라우드에 저장된 작업환경 캐시 백업을 정리합니다. 전체 백업 삭제 또는 최신 백업 1개만 남기기를 선택할 수 있습니다.",
            "백업 삭제",
            self.cloud_delete_cache_backups,
        )

        body_layout.addWidget(cloud_block)
        body_layout.addStretch(1)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close, dlg)
        btns.button(QDialogButtonBox.StandardButton.Close).setText(self.tr_ui("닫기"))
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)
        dlg.exec()

    def settings_dialog_style(self):
        """통합 설정/옵션 계열 창 전용 몽글 카드 스타일."""
        if self.is_light_theme():
            return """
                QDialog { background:#f4f6fa; color:#22252b; }
                QScrollArea { background:transparent; border:0; }
                QLabel { color:#22252b; }
                QFrame#SettingsBlock {
                    background:#ffffff;
                    border:1px solid #dfe5ef;
                    border-radius:16px;
                }
                QFrame#SettingsItem {
                    background:#f9fbfe;
                    border:1px solid #e4eaf3;
                    border-radius:14px;
                }
                QLabel#SettingsItemTitle { font-size:13px; font-weight:700; color:#1f232b; }
                QLabel#SettingsTitle, QLabel#SettingsDialogTitle { font-size:22px; font-weight:800; color:#1f232b; }
                QLabel#SettingsSectionTitle { font-size:16px; font-weight:750; color:#1f232b; }
                QLabel#SettingsDescription { color:#667085; line-height:140%; }
                QLabel#SettingsPath {
                    color:#667085;
                    background:#f1f4f9;
                    border:1px solid #e0e6f0;
                    border-radius:0px;
                    padding:3px 6px;
                }
                QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {
                    background:#ffffff;
                    color:#22252b;
                    border:1px solid #cfd7e5;
                    border-radius:0px;
                    padding:3px 6px;
                    selection-background-color:#dbeafe;
                    selection-color:#111827;
                }
                QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
                    border:1px solid #8fb4e8;
                    background:#ffffff;
                }
QCheckBox, QRadioButton { color:#22252b; spacing:9px; }
                QCheckBox::indicator, QRadioButton::indicator {
                    width:15px; height:15px;
                    border:1px solid #aab4c3;
                    background:#ffffff;
                    border-radius:0px;
                }
                QRadioButton::indicator { border-radius:0px; }
                QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                    background:#7aa8e8;
                    border:1px solid #7aa8e8;
                }
                QPushButton {
                    background:#f8fafc;
                    color:#22252b;
                    border:1px solid #cfd7e5;
                    border-radius:0px;
                    padding:4px 10px;
                }
                QPushButton:hover { background:#edf4ff; border-color:#aac4e8; }
                QPushButton:pressed { background:#e3edf9; }
                QPushButton:disabled { background:#edf0f5; color:#9aa4b2; border-color:#dde3ec; }
                QTabWidget::pane { border:1px solid #dfe5ef; border-radius:0px; background:#ffffff; }
                QTabBar::tab {
                    background:#edf1f7;
                    color:#4b5563;
                    border:1px solid #d9e0ea;
                    border-bottom:none;
                    border-top-left-radius:10px;
                    border-top-right-radius:3px;
                    padding:4px 10px;
                }
                QTabBar::tab:selected { background:#ffffff; color:#1f232b; font-weight:700; }
                QListWidget, QTableWidget, QTreeWidget {
                    background:#ffffff;
                    color:#22252b;
                    border:1px solid #dfe5ef;
                    border-radius:0px;
                    alternate-background-color:#f7f9fd;
                    selection-background-color:#dbeafe;
                    selection-color:#111827;
                }
                QHeaderView::section {
                    background:#f1f4f9;
                    color:#374151;
                    border:0;
                    border-right:1px solid #dfe5ef;
                    padding:7px;
                }
                QScrollBar:vertical { background:#eef2f8; width:12px; margin:0; border:0; border-radius:0px; }
                QScrollBar::handle:vertical { background:#cbd5e1; min-height:30px; border-radius:0px; }
                QScrollBar::handle:vertical:hover { background:#b7c3d4; }
                QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
                QScrollBar:horizontal { background:#eef2f8; height:12px; margin:0; border:0; border-radius:0px; }
                QScrollBar::handle:horizontal { background:#cbd5e1; min-width:30px; border-radius:0px; }
                QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            """
        return """
            QDialog { background:#202226; color:#f2f4f8; }
            QScrollArea { background:transparent; border:0; }
            QLabel { color:#f2f4f8; }
            QFrame#SettingsBlock {
                background:#282c33;
                border:1px solid #3b414c;
                border-radius:16px;
            }
            QFrame#SettingsItem {
                background:#24282f;
                border:1px solid #363c47;
                border-radius:14px;
            }
            QLabel#SettingsItemTitle { font-size:13px; font-weight:700; color:#ffffff; }
            QLabel#SettingsTitle, QLabel#SettingsDialogTitle { font-size:22px; font-weight:800; color:#ffffff; }
            QLabel#SettingsSectionTitle { font-size:16px; font-weight:750; color:#ffffff; }
            QLabel#SettingsDescription { color:#b5bfce; line-height:140%; }
            QLabel#SettingsPath {
                color:#c6ceda;
                background:#1f2228;
                border:1px solid #3b414c;
                border-radius:0px;
                padding:3px 6px;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {
                background:#1f2228;
                color:#f5f7fb;
                border:1px solid #434a56;
                border-radius:0px;
                padding:3px 6px;
                selection-background-color:#4c6f9f;
                selection-color:#ffffff;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
                border:1px solid #7ea2d6;
                background:#222630;
            }
QCheckBox, QRadioButton { color:#f2f4f8; spacing:9px; }
            QCheckBox::indicator, QRadioButton::indicator {
                width:15px; height:15px;
                border:1px solid #6f7786;
                background:#1f2228;
                border-radius:0px;
            }
            QRadioButton::indicator { border-radius:0px; }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked {
                background:#78a6e6;
                border:1px solid #78a6e6;
            }
            QPushButton {
                background:#333843;
                color:#f2f4f8;
                border:1px solid #555d6c;
                border-radius:0px;
                padding:4px 10px;
            }
            QPushButton:hover { background:#3d4654; border-color:#718098; }
            QPushButton:pressed { background:#2b303a; }
            QPushButton:disabled { background:#2a2d33; color:#858d9a; border-color:#3f4550; }
            QTabWidget::pane { border:1px solid #3b414c; border-radius:0px; background:#24282f; }
            QTabBar::tab {
                background:#2a2e36;
                color:#b5bfce;
                border:1px solid #3b414c;
                border-bottom:none;
                border-top-left-radius:10px;
                border-top-right-radius:3px;
                padding:4px 10px;
            }
            QTabBar::tab:selected { background:#333842; color:#ffffff; font-weight:700; }
            QListWidget, QTableWidget, QTreeWidget {
                background:#24282f;
                color:#f2f4f8;
                border:1px solid #3b414c;
                border-radius:0px;
                alternate-background-color:#282d35;
                selection-background-color:#3d587d;
                selection-color:#ffffff;
            }
            QHeaderView::section {
                background:#2d323b;
                color:#d7deea;
                border:0;
                border-right:1px solid #3b414c;
                padding:7px;
            }
            QScrollBar:vertical { background:#20242b; width:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:vertical { background:#424a57; min-height:30px; border-radius:0px; }
            QScrollBar::handle:vertical:hover { background:#566173; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background:#20242b; height:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:horizontal { background:#424a57; min-width:30px; border-radius:0px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
        """

    def _settings_block(self, title, description=None):
        block = QFrame()
        block.setObjectName("SettingsBlock")
        layout = QVBoxLayout(block)
        layout.setContentsMargins(16, 14, 16, 14)
        layout.setSpacing(10)
        title_label = QLabel(self.tr_ui(title))
        title_label.setObjectName("SettingsSectionTitle")
        layout.addWidget(title_label)
        if description:
            desc = QLabel(self.tr_ui(description))
            desc.setObjectName("SettingsDescription")
            desc.setWordWrap(True)
            layout.addWidget(desc)
        return block, layout

    def _settings_row(self, label_text, widget, description=None):
        row_wrap = QWidget()
        row = QHBoxLayout(row_wrap)
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(10)
        left = QVBoxLayout()
        left.setContentsMargins(0, 0, 0, 0)
        label = QLabel(self.tr_ui(label_text))
        label.setMinimumWidth(180)
        left.addWidget(label)
        if description:
            desc = QLabel(self.tr_ui(description))
            desc.setObjectName("SettingsDescription")
            desc.setWordWrap(True)
            left.addWidget(desc)
        row.addLayout(left, 1)
        row.addWidget(widget, 0)
        return row_wrap

    def _settings_button(self, text, slot):
        btn = QPushButton(self.tr_ui(text))
        btn.clicked.connect(slot)
        return btn

    def open_settings_overview_dialog(self):
        """설정과 옵션을 한 번에 보는 통합 창.
        - 확인: 이 창에서 직접 바꾼 설정을 저장하고 닫는다.
        - 닫기/X: 이 창에서 직접 바꾼 설정을 저장하지 않고 닫는다.
        - 복잡한 옵션은 각 전용 관리창의 확인/닫기 규칙을 따른다.
        """
        old_auto_save = bool(getattr(self, "auto_save_enabled", False))
        old_theme = str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK)
        old_language = normalize_ui_language(getattr(self, "ui_language", LANG_KO))
        old_temp_enabled = self.is_temp_auto_cleanup_enabled()
        old_temp_days = self.get_temp_auto_cleanup_days()

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("설정 / 옵션"))
        dlg.setModal(True)
        dlg.resize(820, 760)
        dlg.setStyleSheet(self.settings_dialog_style())

        root = QVBoxLayout(dlg)
        root.setContentsMargins(18, 18, 18, 18)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("설정 / 옵션"))
        title.setObjectName("SettingsDialogTitle")
        root.addWidget(title)

        intro = QLabel(self.tr_ui("확인을 누르면 이 창에서 바꾼 설정이 저장됩니다. 닫기나 X를 누르면 이 창에서 바꾼 설정은 저장하지 않습니다. 복잡한 항목은 오른쪽 버튼으로 전용 관리창을 엽니다."))
        intro.setObjectName("SettingsDescription")
        intro.setWordWrap(True)
        root.addWidget(intro)

        scroll = QScrollArea(dlg)
        scroll.setWidgetResizable(True)
        body = QWidget()
        body_layout = QVBoxLayout(body)
        body_layout.setContentsMargins(0, 0, 0, 0)
        body_layout.setSpacing(12)
        scroll.setWidget(body)
        root.addWidget(scroll, 1)

        def make_action_button(text, slot):
            btn = QPushButton(self.tr_ui(text), dlg)
            btn.setMinimumWidth(150)
            btn.clicked.connect(slot)
            return btn

        def add_item(layout, title_text, description_text, control_widget=None, button_text=None, button_slot=None):
            item = QFrame(dlg)
            item.setObjectName("SettingsItem")
            item_layout = QHBoxLayout(item)
            item_layout.setContentsMargins(12, 10, 12, 10)
            item_layout.setSpacing(12)
            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            text_box.setSpacing(4)
            t = QLabel(self.tr_ui(title_text), item)
            t.setObjectName("SettingsItemTitle")
            text_box.addWidget(t)
            d = QLabel(self.tr_ui(description_text), item)
            d.setObjectName("SettingsDescription")
            d.setWordWrap(True)
            text_box.addWidget(d)
            item_layout.addLayout(text_box, 1)
            if control_widget is not None:
                item_layout.addWidget(control_widget, 0)
            if button_text and button_slot:
                item_layout.addWidget(make_action_button(button_text, button_slot), 0)
            layout.addWidget(item)
            return item

        # 설정 섹션
        settings_block, settings_layout = self._settings_block(
            "설정",
            "프로그램의 기본 동작과 작업 환경을 정하는 항목입니다. 여기서 직접 바꾼 값은 확인을 눌러야 저장됩니다.",
        )

        cb_auto = QCheckBox(self.tr_ui("자동저장 모드"), dlg)
        cb_auto.setChecked(old_auto_save)
        add_item(
            settings_layout,
            "자동저장 모드",
            "ON이면 변경 사항을 실제 프로젝트에 바로 저장합니다. OFF이면 임시 작업 캐시에 먼저 저장하고, 프로젝트 저장 시 확정합니다.",
            cb_auto,
        )

        combo_theme = QComboBox(dlg)
        combo_theme.addItem(self.tr_ui("다크 테마"), THEME_DARK)
        combo_theme.addItem(self.tr_ui("화이트 테마"), THEME_LIGHT)
        combo_theme.setCurrentIndex(1 if old_theme == THEME_LIGHT else 0)
        add_item(
            settings_layout,
            "테마 설정",
            "프로그램 전체의 밝기 테마를 정합니다. 확인을 누르면 선택한 테마가 적용됩니다.",
            combo_theme,
        )

        combo_lang = QComboBox(dlg)
        combo_lang.addItem(self.tr_ui("한국어"), LANG_KO)
        combo_lang.addItem("English", LANG_EN)
        combo_lang.setCurrentIndex(1 if old_language == LANG_EN else 0)
        add_item(
            settings_layout,
            "언어 설정",
            "메뉴와 안내 문구의 표시 언어를 정합니다. 확인을 누르면 선택한 언어가 적용됩니다.",
            combo_lang,
        )

        workspace_widget = QWidget(dlg)
        workspace_row = QHBoxLayout(workspace_widget)
        workspace_row.setContentsMargins(0, 0, 0, 0)
        workspace_row.setSpacing(8)
        try:
            old_workspace_root = Path(load_workspace_config().get("workspace_root") or get_workspace_root())
        except Exception:
            old_workspace_root = Path(str(get_workspace_root()))
        workspace_target = {"path": old_workspace_root}
        workspace_label = QLabel(str(old_workspace_root), workspace_widget)
        workspace_label.setObjectName("SettingsPath")
        workspace_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        workspace_row.addWidget(workspace_label, 1)
        def change_workspace_from_dialog():
            # 통합 설정창에서는 개별 작업 폴더 설정창을 다시 띄우지 않는다.
            # 여기서는 경로값만 바꾸고, 실제 저장/재기동 확인은 통합 설정창의 [확인]에서 처리한다.
            current = str(workspace_target.get("path") or old_workspace_root)
            selected = QFileDialog.getExistingDirectory(dlg, self.tr_ui("작업 폴더 위치 선택"), current)
            if selected:
                try:
                    target = normalize_workspace_root_from_user(selected)
                except Exception:
                    QMessageBox.warning(dlg, self.tr_ui("경로 오류"), self.tr_ui("작업 폴더 경로가 올바르지 않습니다."))
                    return
                workspace_target["path"] = target
                workspace_label.setText(str(target))
        btn_change_workspace = QPushButton(self.tr_ui("위치 변경"), workspace_widget)
        btn_change_workspace.clicked.connect(change_workspace_from_dialog)
        workspace_row.addWidget(btn_change_workspace)
        def reset_workspace_from_dialog():
            # 즉시 저장하지 않고 표시값만 기본값으로 되돌린다.
            # [확인]에서 재기동을 승인해야 실제 적용된다.
            target = default_workspace_root()
            workspace_target["path"] = target
            workspace_label.setText(str(target))
        btn_reset_workspace = QPushButton(self.tr_ui("기본값으로\n변경"), workspace_widget)
        btn_reset_workspace.setToolTip(self.tr_ui("Windows 실제 문서 폴더 아래 YSB_Translator로 되돌립니다."))
        btn_reset_workspace.clicked.connect(reset_workspace_from_dialog)
        workspace_row.addWidget(btn_reset_workspace)
        add_item(
            settings_layout,
            "작업 폴더 위치",
            "프로젝트 작업 폴더와 캐시가 저장되는 기준 위치입니다. 위치를 바꾸면 프로그램을 재기동해야 적용됩니다. 취소하면 이전 작업 폴더 위치값으로 원복됩니다. 기본값은 Windows 실제 문서 폴더 아래 YSB_Translator입니다.",
            workspace_widget,
        )

        temp_widget = QWidget(dlg)
        temp_row = QHBoxLayout(temp_widget)
        temp_row.setContentsMargins(0, 0, 0, 0)
        temp_row.setSpacing(8)
        cb_temp_auto = QCheckBox(self.tr_ui("자동삭제"), temp_widget)
        cb_temp_auto.setChecked(old_temp_enabled)
        combo_days = QComboBox(temp_widget)
        for days, label in self.temp_cleanup_period_options():
            combo_days.addItem(self.tr_ui(label), days)
            if days == old_temp_days:
                combo_days.setCurrentIndex(combo_days.count() - 1)
        combo_days.setEnabled(cb_temp_auto.isChecked())
        cb_temp_auto.toggled.connect(lambda checked: combo_days.setEnabled(bool(checked)))
        temp_row.addWidget(cb_temp_auto)
        temp_row.addWidget(combo_days)
        add_item(
            settings_layout,
            "임시 파일 관리",
            "오래된 임시 작업 폴더를 자동으로 정리할지 정합니다. 즉시 삭제는 별도 확인 후 바로 실행됩니다.",
            temp_widget,
            "지금 정리",
            lambda: self.delete_temp_files_now(dlg),
        )

        add_item(
            settings_layout,
            "YSBT 파일 연결 등록",
            ".ysbt 파일을 더블클릭했을 때 현재 역식붕이 툴로 바로 열리게 Windows 연결을 등록합니다.",
            None,
            "등록",
            self.register_ysb_file_association,
        )
        add_item(
            settings_layout,
            "YSBT 파일 연결 해제",
            "현재 사용자 계정의 .ysbt 연결을 해제합니다. 이전 테스트용 .ysb 연결도 함께 정리합니다.",
            None,
            "해제",
            self.unregister_ysbt_file_association,
        )

        body_layout.addWidget(settings_block)

        # 옵션 섹션
        options_block, options_layout = self._settings_block(
            "옵션",
            "작업 기능을 관리하는 항목입니다. 이 창 안에 전부 펼치면 복잡해지므로, 각 항목의 버튼으로 기존 전용 관리창을 엽니다.",
        )
        option_items = [
            (
                "API 관리",
                "OpenAI, DeepSeek, OpenAI 호환 서버, 인페인팅 API 같은 외부 API 주소와 키, 모델명을 관리합니다. 유료 API 정보가 들어갈 수 있으니 저장 전 확인이 필요합니다.",
                "관리",
                self.open_api_settings_dialog,
            ),
            (
                "번역 프롬프트 입력",
                "AI 번역에 사용할 기본 지침을 편집합니다. 작품 말투, 번역 규칙, 금지 표현 같은 지시문을 이곳에서 관리합니다.",
                "편집",
                self.open_translation_prompt_dialog,
            ),
            (
                "단어장",
                "반복해서 나오는 이름, 고유명사, 말투 규칙, 번역 고정어를 관리합니다. 번역 품질을 일정하게 유지하는 데 쓰입니다.",
                "관리",
                self.open_glossary_dialog,
            ),
            (
                "분석 마스크 확장 비율",
                "OCR/분석 결과로 만들어지는 마스크의 여유 범위와 최소 확장 크기를 조절합니다. 최소 확장 크기를 0px로 두면 강제 최소 확장을 사용하지 않습니다.",
                "설정",
                self.open_analysis_mask_settings_dialog,
            ),
            (
                "단축키 통합 관리",
                "작업, 일괄 처리, 텍스트 입력, 옵션 기능에 연결된 단축키를 한곳에서 바꿉니다. 충돌 확인과 비활성화도 여기서 처리합니다.",
                "관리",
                self.open_shortcut_settings_dialog,
            ),
            (
                "매크로 관리",
                "여러 작업을 하나의 사용자 단축키로 묶어 실행하는 매크로를 관리합니다. 반복 작업을 줄이는 자동화용 기능입니다.",
                "관리",
                self.open_macro_settings_dialog,
            ),
            (
                "페이지 글꼴 프리셋 관리",
                "현재 페이지 또는 전체 페이지에 적용할 글꼴 스타일 묶음을 관리합니다. 페이지 단위 식질 스타일을 빠르게 맞출 때 사용합니다.",
                "관리",
                self.open_text_preset_dialog,
            ),
            (
                "개별 글꼴 프리셋 관리",
                "선택한 텍스트 박스 하나에 적용할 글꼴, 크기, 테두리, 색상 같은 개별 스타일 프리셋을 관리합니다.",
                "관리",
                self.open_item_text_preset_dialog,
            ),
        ]
        for title_text, desc_text, btn_text, slot in option_items:
            add_item(options_layout, title_text, desc_text, None, btn_text, slot)

        body_layout.addWidget(options_block)
        body_layout.addStretch(1)

        save_applied = {"ok": False, "restart": False}

        def apply_settings_overview_changes():
            new_auto_save = bool(cb_auto.isChecked())
            new_theme = str(combo_theme.currentData() or THEME_DARK)
            if new_theme not in (THEME_DARK, THEME_LIGHT):
                new_theme = THEME_DARK
            new_language = normalize_ui_language(combo_lang.currentData())
            new_temp_enabled = bool(cb_temp_auto.isChecked())
            new_temp_days = int(combo_days.currentData() or old_temp_days or 7)

            # 확인 → 저장 확인에서 예를 누른 뒤에만 실제 저장/적용한다.
            if new_theme != old_theme:
                self.ui_theme = new_theme
                self.apply_theme(new_theme)
            if new_language != old_language:
                self.ui_language = new_language
                self.apply_language(new_language)
            if new_temp_enabled != old_temp_enabled or new_temp_days != old_temp_days:
                self.set_temp_cleanup_options(new_temp_enabled, new_temp_days)
                self.log(f"🧹 임시 파일 자동삭제 설정: {'ON' if new_temp_enabled else 'OFF'} / {new_temp_days}일")
            if new_auto_save != old_auto_save:
                try:
                    self.act_auto_save_mode.blockSignals(True)
                    self.act_auto_save_mode.setChecked(new_auto_save)
                    self.act_auto_save_mode.blockSignals(False)
                except Exception:
                    pass
                self.toggle_auto_save_mode(new_auto_save)
            else:
                self.save_app_options_cache()
            self.log("⚙️ 설정 / 옵션 저장 완료")
            save_applied["ok"] = True

        def on_settings_overview_ok():
            # 설정창은 닫지 않은 상태에서 먼저 저장 여부를 묻는다.
            # 아니오(N)를 누르면 설정창으로 돌아가 다시 조작할 수 있다.
            if not self.ask_yes_no_shortcut(
                "설정 저장",
                "이 창에서 바꾼 설정을 저장할까요?",
                yes_text="저장",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Question,
                parent=dlg,
            ):
                self.log("⚙️ 설정 / 옵션 저장 취소")
                return

            try:
                current_workspace = Path(old_workspace_root).resolve()
                target_workspace = Path(workspace_target.get("path") or old_workspace_root).resolve()
            except Exception:
                current_workspace = Path(str(old_workspace_root))
                target_workspace = Path(str(workspace_target.get("path") or old_workspace_root))

            workspace_changed = current_workspace != target_workspace
            if workspace_changed:
                if not workspace_restart_confirmation(dlg, current_workspace, target_workspace, self.ui_language):
                    # 재기동을 취소하면 설정창은 그대로 두고 작업 폴더 표시값만 이전값으로 원복한다.
                    workspace_target["path"] = old_workspace_root
                    workspace_label.setText(str(old_workspace_root))
                    self.log("📁 작업 폴더 위치 변경 취소")
                    return
                try:
                    apply_settings_overview_changes()
                    schedule_workspace_root_change(target_workspace)
                    save_applied["restart"] = True
                    self.log(f"📁 작업 폴더 위치 변경 예약 및 재기동: {target_workspace}")
                    dlg.accept()
                    restart_application_detached()
                    return
                except Exception as e:
                    QMessageBox.critical(dlg, self.tr_ui("저장 실패"), f"{self.tr_ui('작업 폴더 위치를 변경하지 못했습니다.')}\n{e}")
                    workspace_target["path"] = old_workspace_root
                    workspace_label.setText(str(old_workspace_root))
                    return

            apply_settings_overview_changes()
            dlg.accept()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        btns.accepted.connect(on_settings_overview_ok)
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)

        if dlg.exec() != QDialog.DialogCode.Accepted:
            self.log("⚙️ 설정 / 옵션 변경 취소")
            return

        if save_applied.get("ok") and not save_applied.get("restart"):
            self.show_ok_notice("설정 저장 완료", "설정이 저장되었습니다.")

    def open_analysis_mask_settings_dialog(self):
        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("분석 마스크 확장 비율"))
        dlg.resize(660, 500)
        dlg.setStyleSheet(self.settings_dialog_style())
        root = QVBoxLayout(dlg)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)

        title = QLabel(self.tr_ui("분석 마스크 확장 비율"), dlg)
        title.setObjectName("SettingsTitle")
        root.addWidget(title)

        desc = QLabel(self.tr_ui("OCR/분석 결과로 만들어지는 마스크의 여유 범위와 최소 확장 크기를 조절합니다. 최소 확장 크기를 0px로 두면 강제 최소 확장을 사용하지 않습니다."), dlg)
        desc.setObjectName("SettingsDescription")
        desc.setWordWrap(True)
        root.addWidget(desc)

        form_box = QFrame(dlg)
        form_box.setObjectName("SettingsItem")
        form_layout = QVBoxLayout(form_box)
        form_layout.setContentsMargins(12, 12, 12, 12)
        form_layout.setSpacing(12)

        old_text_ratio = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO),
            DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO,
        )
        old_paint_ratio = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO),
            DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO,
        )
        old_text_min_px = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX),
            DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX,
        )
        old_paint_min_px = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX),
            DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX,
        )

        def make_ratio_spin(value):
            spin = QDoubleSpinBox(dlg)
            spin.setRange(0.00, 2.00)
            spin.setDecimals(2)
            spin.setSingleStep(0.05)
            spin.setValue(float(value))
            spin.setSuffix(" x")
            spin.setMinimumWidth(120)
            return spin

        def make_px_spin(value):
            spin = QSpinBox(dlg)
            spin.setRange(0, 100)
            spin.setSingleStep(1)
            spin.setValue(int(value))
            spin.setSuffix(" px")
            spin.setMinimumWidth(120)
            return spin

        def add_setting_row(title_text, description_text, editor):
            row = QHBoxLayout()
            text_box = QVBoxLayout()
            text_box.setContentsMargins(0, 0, 0, 0)
            item_title = QLabel(self.tr_ui(title_text), dlg)
            item_title.setObjectName("SettingsItemTitle")
            item_desc = QLabel(self.tr_ui(description_text), dlg)
            item_desc.setObjectName("SettingsDescription")
            item_desc.setWordWrap(True)
            text_box.addWidget(item_title)
            text_box.addWidget(item_desc)
            row.addLayout(text_box, 1)
            row.addWidget(editor, 0)
            form_layout.addLayout(row)

        spin_text = make_ratio_spin(old_text_ratio)
        add_setting_row(
            "텍스트 마스크 확장 비율",
            "분석 결과의 텍스트 마스크를 묶고 확장하는 비율입니다. 말풍선 글자 테두리가 덜 잡히면 이 값을 올리세요.",
            spin_text,
        )

        spin_text_min = make_px_spin(old_text_min_px)
        add_setting_row(
            "텍스트 마스크 최소 확장 크기",
            "텍스트 마스크를 만들 때 비율 계산값이 작아도 최소로 확장할 픽셀 크기입니다. 0px이면 최소 확장 강제를 사용하지 않습니다.",
            spin_text_min,
        )

        line = QFrame(dlg)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        form_layout.addWidget(line)

        spin_paint = make_ratio_spin(old_paint_ratio)
        add_setting_row(
            "페인트 마스크 확장 비율",
            "인페인팅/페인트 마스크를 만들 때 글자 주변을 얼마나 여유 있게 지울지 정합니다. 배경까지 너무 많이 잡히면 이 값을 낮추세요.",
            spin_paint,
        )

        spin_paint_min = make_px_spin(old_paint_min_px)
        add_setting_row(
            "페인트 마스크 최소 확장 크기",
            "페인트 마스크를 만들 때 비율 계산값이 작아도 최소로 확장할 픽셀 크기입니다. 0px이면 최소 확장 강제를 사용하지 않습니다.",
            spin_paint_min,
        )

        reset_row = QHBoxLayout()
        reset_row.addStretch(1)
        btn_reset = QPushButton(self.tr_ui("기본값으로 돌아가기"), dlg)
        reset_row.addWidget(btn_reset)
        form_layout.addLayout(reset_row)

        def reset_defaults():
            spin_text.setValue(DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO)
            spin_text_min.setValue(DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX)
            spin_paint.setValue(DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO)
            spin_paint_min.setValue(DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX)

        btn_reset.clicked.connect(reset_defaults)
        root.addWidget(form_box)
        root.addStretch(1)

        save_applied = {"ok": False, "restart": False}

        def apply_changes():
            text_ratio = clamp_analysis_mask_ratio(spin_text.value(), DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO)
            paint_ratio = clamp_analysis_mask_ratio(spin_paint.value(), DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO)
            text_min_px = clamp_analysis_mask_min_px(spin_text_min.value(), DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX)
            paint_min_px = clamp_analysis_mask_min_px(spin_paint_min.value(), DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX)
            self.app_options[ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY] = text_ratio
            self.app_options[ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY] = paint_ratio
            self.app_options[ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY] = text_min_px
            self.app_options[ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY] = paint_min_px
            self.sync_analysis_mask_options_to_config()
            self.save_app_options_cache()
            self.log(f"🎭 분석 마스크 확장 설정 저장: 텍스트 {text_ratio:.2f}/{text_min_px}px, 페인트 {paint_ratio:.2f}/{paint_min_px}px")
            save_applied["ok"] = True

        def on_ok():
            if not self.ask_yes_no_shortcut(
                "분석 마스크 설정 저장",
                "분석 마스크 확장 설정을 저장할까요?",
                yes_text="저장",
                no_text="취소",
                default_yes=True,
                icon=QMessageBox.Icon.Question,
                parent=dlg,
            ):
                self.log("🎭 분석 마스크 확장 설정 저장 취소")
                return
            apply_changes()
            dlg.accept()

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dlg)
        btns.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        btns.accepted.connect(on_ok)
        btns.rejected.connect(dlg.reject)
        root.addWidget(btns)

        if dlg.exec() == QDialog.DialogCode.Accepted and save_applied.get("ok"):
            self.show_ok_notice("분석 마스크 설정 저장 완료", "분석 마스크 확장 설정이 저장되었습니다.")

    def open_launcher_options_menu(self):
        menu = QMenu(self)
        menu.addAction(self.actions["option_theme_settings"])
        menu.addAction(self.actions["option_language_settings"])
        menu.addSeparator()
        menu.addAction(self.actions["option_api_settings"])
        menu.addAction(self.actions["option_translation_prompt"])
        menu.addAction(self.actions["option_glossary"])
        menu.addAction(self.actions["option_analysis_mask_settings"])
        menu.addSeparator()
        menu.addAction(self.actions["option_shortcut_settings"])
        menu.addAction(self.actions["option_macro_settings"])
        menu.exec(QCursor.pos())

    def open_launcher_help(self):
        QMessageBox.information(
            self,
            self.tr_ui("도움말 / 매뉴얼"),
            self.tr_ui("런처 화면에서는 새 프로젝트, 프로젝트 열기, 마지막 작업 복구, 최근 프로젝트 열기를 바로 사용할 수 있습니다."),
        )

    def setup_menu(self):
        menubar = self.menuBar()

        project_menu = menubar.addMenu(self.tr_ui("프로젝트")); self.project_menu = project_menu
        # 1. 새로 만들기 및 열기
        project_menu.addAction(self.actions["project_new"])
        project_menu.addAction(self.actions["project_open"])
        project_menu.addAction(self.actions["project_open_json"])
        project_menu.addSeparator()
        # 2. 저장하기
        project_menu.addAction(self.actions["project_save"])
        project_menu.addAction(self.actions["project_save_as"])
        project_menu.addSeparator()
        # 3. 복구하기
        project_menu.addAction(self.actions["project_recover_last_work"])
        project_menu.addSeparator()
        # 4. 기타 옵션
        project_menu.addAction(self.actions["project_show_launcher"])
        project_menu.addAction(self.actions["option_settings_overview"])

        work_menu = menubar.addMenu(self.tr_ui("작업")); self.work_menu = work_menu
        work_menu.addAction(self.actions["work_tab_cycle"])
        work_menu.addAction(self.actions["work_page_prev"])
        work_menu.addAction(self.actions["work_page_next"])
        work_menu.addSeparator()
        work_menu.addAction(self.actions["work_open_current_project_folder"])
        work_menu.addSeparator()
        work_menu.addAction(self.actions["work_analyze"])
        work_menu.addAction(self.actions["work_text_number_width"])
        work_menu.addAction(self.actions["work_translate"])
        work_menu.addAction(self.actions["work_inpaint"])
        work_menu.addAction(self.actions["work_inpaint_source"])
        work_menu.addAction(self.actions["work_restore_original_source"])
        work_menu.addAction(self.actions["work_extract_text"])
        work_menu.addAction(self.actions["work_import_translation"])
        work_menu.addAction(self.actions["work_clear_translation"])
        work_menu.addAction(self.actions["work_clean_text"])
        work_menu.addAction(self.actions["work_reset_text_rects"])
        work_menu.addAction(self.actions["work_export"])

        batch_menu = menubar.addMenu(self.tr_ui("일괄 작업")); self.batch_menu = batch_menu
        batch_menu.addAction(self.actions["batch_analyze"])
        batch_menu.addAction(self.actions["batch_translate"])
        batch_menu.addAction(self.actions["batch_inpaint"])
        batch_menu.addAction(self.actions["batch_extract_text"])
        batch_menu.addAction(self.actions["batch_import_translation"])
        batch_menu.addAction(self.actions["batch_clear_translation"])
        batch_menu.addAction(self.actions["batch_clean_text"])
        batch_menu.addAction(self.actions["batch_reset_text_rects"])
        batch_menu.addAction(self.actions["batch_export"])

        auto_menu = menubar.addMenu(self.tr_ui("자동화 작업")); self.auto_menu = auto_menu
        auto_menu.addAction(self.actions["auto_text_size_current"])
        auto_menu.addAction(self.actions["auto_text_size_batch"])
        auto_menu.addSeparator()
        auto_menu.addAction(self.actions["auto_linebreak_current"])
        auto_menu.addAction(self.actions["auto_linebreak_batch"])

        cloud_menu = menubar.addMenu(self.tr_ui("클라우드")); self.cloud_menu = cloud_menu
        cloud_menu.addAction(self.actions["cloud_register"])
        cloud_menu.addAction(self.actions["cloud_unregister"])
        cloud_menu.addSeparator()
        cloud_menu.addAction(self.actions["cloud_cache_backup"])
        cloud_menu.addAction(self.actions["cloud_cache_restore"])
        cloud_menu.addSeparator()
        cloud_menu.addAction(self.actions["cloud_delete_backups"])

        option_menu = menubar.addMenu(self.tr_ui("옵션")); self.option_menu = option_menu
        option_menu.addAction(self.actions["option_api_settings"])
        option_menu.addAction(self.actions["option_translation_prompt"])
        option_menu.addAction(self.actions["option_glossary"])
        option_menu.addAction(self.actions["option_analysis_mask_settings"])
        option_menu.addSeparator()
        option_menu.addAction(self.actions["option_shortcut_settings"])
        option_menu.addAction(self.actions["option_macro_settings"])
        option_menu.addAction(self.actions["option_text_preset_settings"])
        option_menu.addAction(self.actions["option_item_text_preset_settings"])
        settings_menu = menubar.addMenu(self.tr_ui("설정")); self.settings_menu = settings_menu
        settings_menu.addAction(self.actions["option_auto_save_mode"])
        settings_menu.addAction(self.actions["option_theme_settings"])
        settings_menu.addAction(self.actions["option_language_settings"])
        settings_menu.addSeparator()
        settings_menu.addAction(self.actions["option_workspace_location"])
        settings_menu.addAction(self.actions["option_workspace_reset_default"])
        settings_menu.addAction(self.actions["option_cleanup_temp_files"])
        settings_menu.addAction(self.actions["option_register_ysb"])
        settings_menu.addAction(self.actions["option_unregister_ysbt"])


    def setup_ui(self):
        self.main_stack = QStackedWidget()
        self.setCentralWidget(self.main_stack)

        self.recent_project_store = RecentProjectStore()
        self.launcher_widget = LauncherWidget(
            self.recent_project_store,
            app_version=APP_VERSION,
            lang=getattr(self, "ui_language", LANG_KO),
            theme=getattr(self, "ui_theme", THEME_DARK),
            parent=self,
        )
        self.launcher_widget.newProjectRequested.connect(self.new_project_from_images)
        self.launcher_widget.openProjectRequested.connect(self.open_project)
        self.launcher_widget.recoverRequested.connect(self.recover_last_work_project)
        self.launcher_widget.cloudRequested.connect(lambda: self.open_cloud_overview_dialog(include_project_backup=False))
        self.launcher_widget.optionsRequested.connect(self.open_settings_overview_dialog)
        self.launcher_widget.helpRequested.connect(self.open_launcher_help)
        self.launcher_widget.recentProjectOpenRequested.connect(self.confirm_open_recent_project)
        self.launcher_widget.recentProjectRemoveRequested.connect(self.remove_recent_project_from_launcher)
        self.launcher_widget.recentProjectRevealRequested.connect(self.reveal_recent_project_in_folder)
        self.main_stack.addWidget(self.launcher_widget)

        w = QWidget()
        self.editor_widget = w
        self.main_stack.addWidget(w)
        self.main_stack.setCurrentWidget(self.launcher_widget)
        lay = QHBoxLayout(w)
        split = QSplitter(Qt.Orientation.Horizontal)
        lay.addWidget(split)

        # Left Panel
        lp = QWidget()
        ll = QHBoxLayout(lp)
        ll.setContentsMargins(0, 0, 0, 0)

        self.view = MuleImageViewer(self)
        self.view.scene.selectionChanged.connect(self.on_scene_selection_changed)

        tb = QToolBar(orientation=Qt.Orientation.Vertical)
        tb.setStyleSheet("background:#24282f; border:1px solid #3b414c; border-radius:0px;")
        self.act_brush = QAction("🖌️", self, triggered=lambda: self.set_tool('draw'))
        tb.addAction(self.act_brush)
        self.act_erase = QAction("🧼", self, triggered=lambda: self.set_tool('erase'))
        tb.addAction(self.act_erase)

        self.act_reanal = QAction("🔄", self)
        self.act_reanal.triggered.connect(self.reanalyze_mask)
        tb.addAction(self.act_reanal)

        self.act_undo = QAction("↩️", self)
        self.act_undo.triggered.connect(self.handle_general_undo)
        tb.addAction(self.act_undo)

        self.act_magic = QAction("⭐", self)
        self.act_magic.triggered.connect(lambda: self.set_tool('magic_wand'))
        tb.addAction(self.act_magic)
        try:
            _magic_btn = tb.widgetForAction(self.act_magic)
            if _magic_btn is not None:
                _magic_btn.setStyleSheet("font-size:18px; color:#ffd43b;")
        except Exception:
            pass

        self.act_mask_wrap = QAction("🩹", self)
        self.act_mask_wrap.triggered.connect(lambda: self.set_tool('mask_wrap'))
        tb.addAction(self.act_mask_wrap)

        self.act_mask_cut = QAction("🔪", self)
        self.act_mask_cut.triggered.connect(lambda: self.set_tool('mask_cut'))
        tb.addAction(self.act_mask_cut)

        # QCheckBox를 QToolBar에 직접 넣으면 QToolBar 레이아웃 + QCheckBox indicator가 따로 놀아
        # 다른 도구 버튼들과 여백/정렬이 맞지 않는다.
        # 그래서 다른 그림판 도구와 동일하게 checkable QAction으로 통일한다.
        self.act_mask_toggle = QAction("☐", self)
        self.act_mask_toggle.setCheckable(True)
        # QAction 자체 툴팁은 QToolBar가 즉시 표시할 수 있으므로 비워둔다.
        # 실제 안내는 register_delayed_tooltip()의 지연 툴팁 하나로만 표시한다.
        self.act_mask_toggle.setToolTip("")
        self.act_mask_toggle.setStatusTip("")
        self.act_mask_toggle.setWhatsThis("")

        self.act_mask_toggle.toggled.connect(self.on_mask_toggle_changed)
        tb.addAction(self.act_mask_toggle)

        # 기존 코드 호환용 별칭: setChecked/toggle/blockSignals/setVisible 등을 QAction이 그대로 지원한다.
        self.cb_mask_toggle = self.act_mask_toggle
        self.mask_toggle_wrap = tb.widgetForAction(self.act_mask_toggle)
        if self.mask_toggle_wrap:
            self.mask_toggle_wrap.setToolTip("")
            self.mask_toggle_wrap.setStyleSheet("")

        self.act_final_paint_color = QAction("", self)
        self.act_final_paint_color.triggered.connect(lambda: self.pick_color("final_paint"))
        tb.addAction(self.act_final_paint_color)

        self.act_final_text_tool = QAction("T", self)
        self.act_final_text_tool.triggered.connect(lambda: self.set_tool("final_text"))
        tb.addAction(self.act_final_text_tool)

        self.act_final_paint_to_bg = QAction("↧", self)
        self.act_final_paint_to_bg.triggered.connect(self.apply_final_paint_to_background)
        tb.addAction(self.act_final_paint_to_bg)

        self.act_final_paint_above_text = QAction("T↓", self)
        self.act_final_paint_above_text.setCheckable(True)
        self.act_final_paint_above_text.setChecked(False)
        self.act_final_paint_above_text.toggled.connect(self.on_final_paint_above_text_toggled)
        tb.addAction(self.act_final_paint_above_text)

        self.tb = tb
        self.tb.setFixedWidth(42)
        self.tb.setVisible(True)
        self.tb.setEnabled(False)
        ll.addWidget(tb)

        vc = QWidget()
        vl = QVBoxLayout(vc)
        vl.setContentsMargins(0, 0, 0, 0)

        self.final_edit_bar = QWidget()
        final_bar = QHBoxLayout(self.final_edit_bar)
        final_bar.setContentsMargins(6, 4, 6, 4)
        final_bar.setSpacing(6)
        self.final_item_font = QFontComboBox()
        self.final_item_font.setMinimumWidth(180)
        self.final_item_size = QSpinBox()
        self.final_item_size.setRange(5, 500)
        self.final_item_size.setSuffix(" px")
        self.final_item_stroke = QSpinBox()
        self.final_item_stroke.setRange(0, 100)
        self.final_item_stroke.setSuffix(" px")
        self.btn_item_text_color = QPushButton("문자색")
        self.btn_item_stroke_color = QPushButton("획색")
        self.btn_item_align_left = QPushButton("≡◁")
        self.btn_item_align_center = QPushButton("≡◇")
        self.btn_item_align_right = QPushButton("▷≡")
        final_bar.addWidget(QLabel("선택 텍스트"))
        final_bar.addWidget(self.final_item_font, 1)
        final_bar.addWidget(QLabel("크기"))
        final_bar.addWidget(self.final_item_size)
        final_bar.addWidget(QLabel("획"))
        final_bar.addWidget(self.final_item_stroke)
        final_bar.addWidget(self.btn_item_text_color)
        final_bar.addWidget(self.btn_item_stroke_color)
        final_bar.addWidget(self.btn_item_align_left)
        final_bar.addWidget(self.btn_item_align_center)
        final_bar.addWidget(self.btn_item_align_right)
        self.final_edit_bar.hide()
        vl.addWidget(self.final_edit_bar)

        self.final_paint_option_bar = QWidget()
        final_paint_bar = QHBoxLayout(self.final_paint_option_bar)
        final_paint_bar.setContentsMargins(6, 4, 6, 4)
        final_paint_bar.setSpacing(6)
        self.sb_final_paint_opacity = QSpinBox()
        self.sb_final_paint_opacity.setRange(1, 100)
        self.sb_final_paint_opacity.setValue(100)
        self.sb_final_paint_opacity.setSuffix(" %")
        self.sb_final_paint_opacity.setFixedWidth(80)
        self.sb_final_paint_opacity.valueChanged.connect(self.on_final_paint_opacity_changed)
        final_paint_bar.addWidget(QLabel("브러시"))
        final_paint_bar.addWidget(QLabel("불투명도"))
        final_paint_bar.addWidget(self.sb_final_paint_opacity)
        final_paint_bar.addStretch()
        self.final_paint_option_bar.hide()
        vl.addWidget(self.final_paint_option_bar)

        self.magic_wand_bar = QWidget()
        magic_bar = QHBoxLayout(self.magic_wand_bar)
        magic_bar.setContentsMargins(6, 4, 6, 4)
        magic_bar.setSpacing(6)
        self.sb_magic_tolerance = QSpinBox()
        self.sb_magic_tolerance.setRange(0, 255)
        self.sb_magic_tolerance.setValue(20)
        self.sb_magic_tolerance.setFixedWidth(70)
        self.sb_magic_tolerance.setToolTip("요술봉 RGB 허용범위")
        self.btn_magic_expand = QPushButton("영역확장")
        self.btn_magic_expand.clicked.connect(self.expand_magic_wand_selection)
        self.sb_magic_expand = QSpinBox()
        self.sb_magic_expand.setRange(0, 200)
        self.sb_magic_expand.setValue(3)
        self.sb_magic_expand.setSuffix(" px")
        self.sb_magic_expand.setFixedWidth(80)
        self.sb_magic_expand.setToolTip("요술봉 영역확장 범위")
        self.btn_magic_fill = QPushButton("마스킹 칠하기")
        self.btn_magic_fill.clicked.connect(self.fill_magic_wand_mask)
        magic_bar.addWidget(QLabel("요술봉"))
        magic_bar.addWidget(QLabel("RGB 허용범위"))
        magic_bar.addWidget(self.sb_magic_tolerance)
        magic_bar.addWidget(self.btn_magic_expand)
        magic_bar.addWidget(QLabel("확장 범위"))
        magic_bar.addWidget(self.sb_magic_expand)
        magic_bar.addWidget(self.btn_magic_fill)
        magic_bar.addStretch()
        self.magic_wand_bar.hide()
        vl.addWidget(self.magic_wand_bar)
        self.sb_magic_tolerance.valueChanged.connect(self.on_magic_wand_tolerance_changed)

        self.mask_wrap_bar = QWidget()
        mask_wrap_bar_lay = QHBoxLayout(self.mask_wrap_bar)
        mask_wrap_bar_lay.setContentsMargins(6, 4, 6, 4)
        mask_wrap_bar_lay.setSpacing(6)
        self.btn_mask_wrap_rect = QPushButton(self.tr_ui("▭ 사각형"))
        self.btn_mask_wrap_rect.setCheckable(True)
        self.btn_mask_wrap_rect.clicked.connect(lambda checked=False: self.set_mask_wrap_shape("rect"))
        self.btn_mask_wrap_free = QPushButton(self.tr_ui("✎ 자유형"))
        self.btn_mask_wrap_free.setCheckable(True)
        self.btn_mask_wrap_free.clicked.connect(lambda checked=False: self.set_mask_wrap_shape("free"))
        mask_wrap_bar_lay.addWidget(QLabel(self.tr_ui("마스크 랩핑")))
        mask_wrap_bar_lay.addWidget(self.btn_mask_wrap_rect)
        mask_wrap_bar_lay.addWidget(self.btn_mask_wrap_free)
        mask_wrap_bar_lay.addWidget(QLabel(self.tr_ui("선택한 영역 안의 떨어진 마스크들을 하나의 채움 영역으로 감싸줍니다.")))
        mask_wrap_bar_lay.addStretch()
        self.mask_wrap_bar.hide()
        vl.addWidget(self.mask_wrap_bar)
        self.set_mask_wrap_shape("rect", silent=True)

        self.mask_cut_bar = QWidget()
        mask_cut_bar_lay = QHBoxLayout(self.mask_cut_bar)
        mask_cut_bar_lay.setContentsMargins(6, 4, 6, 4)
        mask_cut_bar_lay.setSpacing(6)
        self.btn_mask_cut_rect = QPushButton(self.tr_ui("▭ 사각형"))
        self.btn_mask_cut_rect.setCheckable(True)
        self.btn_mask_cut_rect.clicked.connect(lambda checked=False: self.set_mask_cut_shape("rect"))
        self.btn_mask_cut_free = QPushButton(self.tr_ui("✎ 자유형"))
        self.btn_mask_cut_free.setCheckable(True)
        self.btn_mask_cut_free.clicked.connect(lambda checked=False: self.set_mask_cut_shape("free"))
        self.sb_mask_cut_px = QSpinBox()
        self.sb_mask_cut_px.setRange(1, 200)
        self.sb_mask_cut_px.setValue(8)
        self.sb_mask_cut_px.setSuffix(" px")
        mask_cut_bar_lay.addWidget(QLabel(self.tr_ui("마스크 커팅")))
        mask_cut_bar_lay.addWidget(self.btn_mask_cut_rect)
        mask_cut_bar_lay.addWidget(self.btn_mask_cut_free)
        mask_cut_bar_lay.addWidget(QLabel(self.tr_ui("커팅 폭")))
        mask_cut_bar_lay.addWidget(self.sb_mask_cut_px)
        mask_cut_bar_lay.addWidget(QLabel(self.tr_ui("선택 영역 밖 경계를 지정 픽셀만큼 잘라 붙어 있는 마스크를 분리합니다.")))
        mask_cut_bar_lay.addStretch()
        self.mask_cut_bar.hide()
        vl.addWidget(self.mask_cut_bar)
        self.set_mask_cut_shape("rect", silent=True)

        vl.addWidget(self.view)
        ll.addWidget(vc)

        cl = QHBoxLayout()
        self.btn_prev_page = QPushButton("◀")
        self.btn_prev_page.clicked.connect(self.prev)
        cl.addWidget(self.btn_prev_page)
        self.btn_page = QPushButton("0 / 0")
        self.btn_page.setStyleSheet("border:none; font-weight:bold; color:#f2f2f2;")
        self.btn_page.clicked.connect(self.jump_page)
        cl.addWidget(self.btn_page)
        self.btn_next_page = QPushButton("▶")
        self.btn_next_page.clicked.connect(self.next)
        cl.addWidget(self.btn_next_page)

        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["1. 원본", "2. 분석도", "3. 텍스트 마스크", "4. 페인팅 마스크", "5. 최종결과"])
        self.cb_mode.currentIndexChanged.connect(self.mode_chg)
        cl.addWidget(self.cb_mode)

        # Undo / Redo quick buttons.
        # 작업 탭 콤보 바로 오른쪽에 두어 탭/페이지/텍스트 작업을 마우스로도 되돌릴 수 있게 한다.
        self.btn_quick_undo = QPushButton("↺")
        self.btn_quick_undo.setFixedWidth(36)
        self.btn_quick_undo.setMinimumHeight(26)
        self.btn_quick_undo.clicked.connect(self.handle_global_undo_shortcut)
        cl.addWidget(self.btn_quick_undo)
        self.btn_quick_redo = QPushButton("↻")
        self.btn_quick_redo.setFixedWidth(36)
        self.btn_quick_redo.setMinimumHeight(26)
        self.btn_quick_redo.clicked.connect(self.handle_general_redo)
        cl.addWidget(self.btn_quick_redo)
        self.update_paint_toolbar_visibility()
        self.update_undo_redo_buttons()

        cl.addStretch()
        self.btn_text_mask_reanalyze = QPushButton(self.tr_ui("🔄 재분석"))
        self.btn_text_mask_reanalyze.setStyleSheet("background:#3d587d;color:#ffffff;font-weight:700;border:1px solid #7ea2d6;border-radius:0px;padding:6px 10px")
        self.btn_text_mask_reanalyze.clicked.connect(self.reanalyze_mask)
        self.btn_text_mask_reanalyze.hide()
        cl.addWidget(self.btn_text_mask_reanalyze)
        self.btn_analyze = QPushButton(self.tr_ui("⚡ 분석"), clicked=self.anal)
        self.btn_analyze.setStyleSheet("background:#7d4a4a;color:#ffffff;font-weight:700;border:1px solid #a86b6b;border-radius:0px;padding:6px 10px")
        cl.addWidget(self.btn_analyze)
        vl.addLayout(cl)
        split.addWidget(lp)

        # Right Panel
        rp = QWidget()
        rp.setMinimumWidth(720)
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(4)

        self.right_panel = rp
        self.right_scroll = QScrollArea()
        self.right_scroll.setWidgetResizable(True)
        self.right_scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.right_scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        self.right_scroll.setMinimumWidth(260)
        self.right_scroll.setWidget(rp)
        split.addWidget(self.right_scroll)
        split.setChildrenCollapsible(False)
        split.setStretchFactor(0, 3)
        split.setStretchFactor(1, 2)
        split.setSizes([980, 620])

        # 글꼴 프리셋은 옵션 메뉴의 "글꼴 프리셋 관리"에서 다룬다.
        # 캐시/자동저장 로직 호환을 위해 컨트롤 객체는 숨겨 둔다.
        self.cb_text_preset = QComboBox(self)
        self.cb_text_preset.hide()
        self.btn_preset_save = QPushButton("프리셋 저장", self)
        self.btn_preset_save.hide()
        self.btn_preset_import = QPushButton("JSON 가져오기", self)
        self.btn_preset_import.hide()
        self.btn_preset_apply_page = QPushButton("페이지 적용", self)
        self.btn_preset_apply_page.hide()
        self.btn_preset_apply_all = QPushButton("전체 적용", self)
        self.btn_preset_apply_all.hide()

        # 우측 인터페이스 1줄: 선택 텍스트 스타일
        style_line = QHBoxLayout()
        style_line.setContentsMargins(0, 0, 0, 0)
        style_line.setSpacing(6)
        self.cb_font = QFontComboBox()
        self.cb_font.setFixedWidth(150)
        self.cb_font.setFixedHeight(26)
        self.cb_font.setToolTip("글꼴")
        self.sb_font_size = QSpinBox()
        self.sb_font_size.setRange(10, 300)
        self.sb_font_size.setValue(35)
        self.sb_font_size.setSuffix(" px")
        self.sb_font_size.setFixedWidth(100)
        self.sb_font_size.setToolTip("글꼴 크기")
        self.sb_strk = QSpinBox()
        self.sb_strk.setRange(0, 100)
        self.sb_strk.setValue(3)
        self.sb_strk.setSuffix(" px")
        self.sb_strk.setFixedWidth(90)
        self.sb_strk.setToolTip("획 크기")

        self.btn_text_color = QPushButton("")
        self.btn_text_color.setToolTip("문자 색상")
        self.btn_text_color.setFixedSize(26, 26)
        self.btn_stroke_color = QPushButton("")
        self.btn_stroke_color.setToolTip("획 색상")
        self.btn_stroke_color.setFixedSize(26, 26)

        self.btn_align_left = QPushButton("≡◁")
        self.btn_align_center = QPushButton("≡◇")
        self.btn_align_right = QPushButton("▷≡")
        for b in (self.btn_align_left, self.btn_align_center, self.btn_align_right):
            b.setFixedWidth(42)
            b.setFixedHeight(26)
            b.setToolTip("글자 정렬")

        self.sb_line_spacing = QSpinBox()
        self.sb_line_spacing.setRange(50, 300)
        self.sb_line_spacing.setValue(100)
        self.sb_line_spacing.setSuffix(" %")
        self.sb_line_spacing.setFixedWidth(78)
        self.sb_line_spacing.setToolTip("행간")

        self.sb_letter_spacing = QSpinBox()
        self.sb_letter_spacing.setRange(-100, 200)
        self.sb_letter_spacing.setValue(0)
        self.sb_letter_spacing.setSuffix(" px")
        self.sb_letter_spacing.setFixedWidth(78)
        self.sb_letter_spacing.setToolTip("자간")

        self.sb_char_width = QSpinBox()
        self.sb_char_width.setRange(10, 300)
        self.sb_char_width.setValue(100)
        self.sb_char_width.setSuffix(" %")
        self.sb_char_width.setFixedWidth(78)
        self.sb_char_width.setToolTip("문자 너비")

        self.sb_char_height = QSpinBox()
        self.sb_char_height.setRange(10, 300)
        self.sb_char_height.setValue(100)
        self.sb_char_height.setSuffix(" %")
        self.sb_char_height.setFixedWidth(78)
        self.sb_char_height.setToolTip("문자 높이")

        self.btn_bold = QPushButton("B")
        self.btn_italic = QPushButton("I")
        self.btn_strike = QPushButton("S")
        for b, tip in (
            (self.btn_bold, "굵게"),
            (self.btn_italic, "기울이기"),
            (self.btn_strike, "취소선"),
        ):
            b.setCheckable(True)
            b.setFixedWidth(32)
            b.setFixedHeight(26)
            b.setToolTip(tip)

        self.btn_bold.setStyleSheet("font-weight:bold;")
        self.btn_italic.setStyleSheet("font-style:italic;")
        self.btn_strike.setStyleSheet("text-decoration: line-through;")

        style_line.addWidget(QLabel("폰트"))
        style_line.addWidget(self.cb_font)
        style_line.addWidget(QLabel("크기"))
        style_line.addWidget(self.sb_font_size)
        style_line.addWidget(self.btn_text_color)
        style_line.addWidget(QLabel("획"))
        style_line.addWidget(self.sb_strk)
        style_line.addWidget(self.btn_stroke_color)
        style_line.addWidget(self.btn_align_left)
        style_line.addWidget(self.btn_align_center)
        style_line.addWidget(self.btn_align_right)
        style_line.addStretch()
        rl.addLayout(style_line)

        # 우측 인터페이스 2줄: 글꼴 상세 옵션
        detail_line = QHBoxLayout()
        detail_line.setContentsMargins(0, 0, 0, 0)
        detail_line.setSpacing(6)
        detail_line.addWidget(QLabel("행간"))
        detail_line.addWidget(self.sb_line_spacing)
        detail_line.addWidget(QLabel("자간"))
        detail_line.addWidget(self.sb_letter_spacing)
        detail_line.addWidget(QLabel("너비"))
        detail_line.addWidget(self.sb_char_width)
        detail_line.addWidget(QLabel("높이"))
        detail_line.addWidget(self.sb_char_height)
        detail_line.addWidget(self.btn_bold)
        detail_line.addWidget(self.btn_italic)
        detail_line.addWidget(self.btn_strike)

        self.cb_item_text_preset = QComboBox()
        self.cb_item_text_preset.setMinimumWidth(100)
        self.cb_item_text_preset.setMaximumWidth(110)
        self.cb_item_text_preset.setFixedHeight(26)
        self.cb_item_text_preset.setToolTip("개별 글꼴 프리셋")
        detail_line.addWidget(self.cb_item_text_preset)

        detail_line.addStretch()
        rl.addLayout(detail_line)

        # 우측 인터페이스 3줄: 자주 쓰는 작업만 남긴 압축 배치
        # 지문 추출 / 번역문 불러오기 / 인페인팅 원본 전환은 메뉴와 단축키로만 사용한다.
        al = QHBoxLayout()
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
        self.cb_trans_provider = QComboBox()
        self.cb_trans_provider.setFixedHeight(26)
        self.cb_trans_provider.addItem("OpenAI", "openai")
        self.cb_trans_provider.addItem("DeepSeek", "deepseek")
        self.cb_trans_provider.addItem("Google", "google")
        self.cb_trans_provider.addItem("Gemini", "gemini")
        self.cb_trans_provider.addItem("Custom", "custom")
        self.set_combo_current_data(self.cb_trans_provider, getattr(self.api_settings, "selected_translation_provider", "openai"))
        self.cb_trans_provider.currentIndexChanged.connect(self.on_translation_provider_changed)

        self.sb_trans_chunk = QSpinBox()
        self.sb_trans_chunk.setRange(1, 100)
        self.sb_trans_chunk.setValue(self.trans_chunk_sizes.get("openai", 20))
        self.sb_trans_chunk.setSuffix(" items" if getattr(self, "ui_language", LANG_KO) == LANG_EN else "개")
        self.sb_trans_chunk.setFixedHeight(26)
        self.sb_trans_chunk.setStatusTip(self.tr_msg("한 번의 API 요청에 묶어서 보낼 텍스트 줄 수"))
        self.sb_trans_chunk.valueChanged.connect(self.on_translation_chunk_changed)

        self.cb_show_final_text = QCheckBox("텍스트 표시")
        self.cb_show_final_text.setChecked(True)
        self.cb_show_final_text.setFixedHeight(26)
        self.cb_show_final_text.toggled.connect(self.on_show_final_text_toggled)

        self.btn_translate = QPushButton("🌐 번역", clicked=self.trans)
        self.btn_translate.setFixedHeight(26)
        self.btn_inpaint = QPushButton("🎨 인페인팅", clicked=self.run_inpainting, styleSheet="background:#456f56;color:#ffffff;border:1px solid #6f9b7b;border-radius:0px;padding:4px 10px")
        self.btn_inpaint.setFixedHeight(26)
        self.btn_text_cleanup = QPushButton("🧹 텍스트 정리", clicked=self.clean_text_current)
        self.btn_text_cleanup.setFixedHeight(26)

        al.addWidget(QLabel("번역AI"))
        al.addWidget(self.cb_trans_provider)
        al.addWidget(QLabel("묶음"))
        al.addWidget(self.sb_trans_chunk)
        al.addWidget(self.btn_translate)
        al.addWidget(self.btn_inpaint)
        al.addWidget(self.btn_text_cleanup)
        al.addWidget(self.cb_show_final_text)
        al.addStretch()
        rl.addLayout(al)

        self.tab = TextTableWidget(0, 4)
        self.tab.setHorizontalHeaderLabels(["ID", "X", "원문", "번역"])
        self.tab.setItemDelegateForColumn(
            3,
            MultilineDelegate(
                self.tab,
                shortcut_getter=self.get_special_shortcuts,
                linebreak_getter=self.get_linebreak_shortcut,
            )
        )
        self.tab.itemChanged.connect(self.on_table_item_changed)
        self.tab.itemSelectionChanged.connect(self.on_table_selection_changed)
        self.tab.rowsReordered.connect(self.on_text_table_rows_reordered)
        self.tab.setDragDropMode(QAbstractItemView.DragDropMode.InternalMove)
        self.tab.setDragDropOverwriteMode(False)
        self.tab.setDefaultDropAction(Qt.DropAction.MoveAction)
        self.tab.setDragEnabled(True)
        self.tab.setAcceptDrops(True)
        self.tab.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tab.customContextMenuRequested.connect(self.on_table_context_menu)
        self.tab.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        self.tab.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tab.setStyleSheet(
            "QTableWidget { background:#26282d; color:#f2f2f2; gridline-color:#4a4d55; border:1px solid #3b414c; border-radius:0px; }"
            "QTableWidget::item:selected { background:#3d587d; color:#ffffff; }"
        )
        rl.addWidget(self.tab)

        self.tab.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tab.setColumnWidth(0, 46)
        self.tab.setColumnWidth(1, 28)
        self.tab.setWordWrap(True)
        self.tab.verticalHeader().setVisible(False)
        self.tab.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        self.btn_export_result = QPushButton(self.tr_ui("📤 결과물 출력"), clicked=self.export_result, styleSheet="background:#3d587d;color:#ffffff;font-weight:700;border:1px solid #7ea2d6;border-radius:0px;height:40px")
        rl.addWidget(self.btn_export_result)
        self.log_w = QTextEdit()
        self.log_w.setMaximumHeight(100)
        self.log_w.setReadOnly(True)
        self.log_w.setStyleSheet("background:#222;color:#0f0;")
        rl.addWidget(self.log_w)
        self.flush_pending_log_messages()
        split.setSizes([1000, 600])

        self.cb_text_preset.currentIndexChanged.connect(self.on_text_preset_selected)
        self.btn_preset_save.clicked.connect(self.save_text_preset_named)
        self.btn_preset_import.clicked.connect(self.import_text_preset_json)
        self.btn_preset_apply_page.clicked.connect(lambda: self.apply_current_preset_to_page(self.idx, refresh=True))
        self.btn_preset_apply_all.clicked.connect(self.apply_current_preset_to_all_pages)

        self.cb_font.currentFontChanged.connect(self.on_global_text_style_changed)
        self.sb_font_size.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_strk.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_line_spacing.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_letter_spacing.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_char_width.valueChanged.connect(self.on_global_text_style_changed)
        self.sb_char_height.valueChanged.connect(self.on_global_text_style_changed)
        self.btn_bold.toggled.connect(self.on_global_text_style_changed)
        self.btn_italic.toggled.connect(self.on_global_text_style_changed)
        self.btn_strike.toggled.connect(self.on_global_text_style_changed)
        self.cb_item_text_preset.currentIndexChanged.connect(self.on_item_text_preset_selected)
        self.btn_text_color.clicked.connect(lambda: self.pick_color("global_text"))
        self.btn_stroke_color.clicked.connect(lambda: self.pick_color("global_stroke"))
        self.btn_align_left.clicked.connect(lambda: self.set_global_align("left"))
        self.btn_align_center.clicked.connect(lambda: self.set_global_align("center"))
        self.btn_align_right.clicked.connect(lambda: self.set_global_align("right"))

        self.final_item_font.currentFontChanged.connect(self.on_final_item_style_changed)
        self.final_item_size.valueChanged.connect(self.on_final_item_style_changed)
        self.final_item_stroke.valueChanged.connect(self.on_final_item_style_changed)
        self.btn_item_text_color.clicked.connect(lambda: self.pick_color("item_text"))
        self.btn_item_stroke_color.clicked.connect(lambda: self.pick_color("item_stroke"))
        self.btn_item_align_left.clicked.connect(lambda: self.apply_style_to_selected(align="left"))
        self.btn_item_align_center.clicked.connect(lambda: self.apply_style_to_selected(align="center"))
        self.btn_item_align_right.clicked.connect(lambda: self.apply_style_to_selected(align="right"))
        self.update_color_button_styles()
        self.install_main_input_enter_escape_filters()

    def shortcut_text_for_key(self, key, fallback=""):
        try:
            seq = self.shortcut_settings.seq(key)
            if seq and not seq.isEmpty():
                txt = seq.toString(QKeySequence.SequenceFormat.NativeText)
                return txt or fallback
        except Exception:
            pass
        return fallback

    def set_dialog_control_tooltip(self, widget, title, key="", desc=""):
        if widget is None:
            return
        shortcut = self.shortcut_text_for_key(key, "") if key else ""
        parts = [self.tr_ui(title)]
        if shortcut:
            parts.append(shortcut)
        if desc:
            parts.append(self.tr_msg(desc))
        try:
            widget.setToolTip("\n".join(parts))
        except Exception:
            pass

    def focus_dialog_control(self, widget):
        if widget is None:
            return
        try:
            widget.setFocus()
            if hasattr(widget, "selectAll"):
                widget.selectAll()
            elif hasattr(widget, "lineEdit") and widget.lineEdit() is not None:
                widget.lineEdit().selectAll()
        except Exception:
            pass

    def add_dialog_shortcut(self, dialog, key, callback):
        try:
            seq = self.shortcut_settings.seq(key)
        except Exception:
            seq = QKeySequence()
        if not seq or seq.isEmpty():
            return None
        sc = QShortcut(seq, dialog)
        sc.setContext(Qt.ShortcutContext.WindowShortcut)
        sc.activated.connect(callback)
        if not hasattr(dialog, "_ysb_style_shortcuts"):
            dialog._ysb_style_shortcuts = []
        dialog._ysb_style_shortcuts.append(sc)
        return sc

    def install_style_editor_shortcuts(self, dialog, controls):
        """메인 인터페이스와 같은 글꼴 상세 단축키/툴팁을 프리셋 창에도 적용한다."""
        if not dialog or not controls:
            return

        if not hasattr(dialog, "_ysb_enter_commit_filter"):
            dialog._ysb_enter_commit_filter = EnterCommitFilter(parent_dialog=dialog, fallback_widget=dialog, parent=dialog)
        for _name, _widget in list(controls.items()):
            if _widget is None:
                continue
            try:
                _widget.installEventFilter(dialog._ysb_enter_commit_filter)
            except Exception:
                pass
            try:
                line = _widget.lineEdit()
                if line is not None:
                    line.installEventFilter(dialog._ysb_enter_commit_filter)
            except Exception:
                pass

        def open_font_selector():
            font_widget = controls.get("font")
            size_widget = controls.get("size")
            bold_widget = controls.get("bold")
            italic_widget = controls.get("italic")
            try:
                current_family = font_widget.currentFont().family()
            except Exception:
                current_family = ""
            try:
                current_size = int(size_widget.value())
            except Exception:
                current_size = 24
            dlg = FontSelectDialog(
                current_family=current_family,
                current_size=current_size,
                current_bold=bool(bold_widget.isChecked()) if bold_widget else False,
                current_italic=bool(italic_widget.isChecked()) if italic_widget else False,
                parent=self,
            )
            if dlg.exec() == QDialog.DialogCode.Accepted and dlg.selected_font_family():
                if font_widget is not None:
                    font_widget.setCurrentFont(QFont(dlg.selected_font_family()))
                if bold_widget is not None:
                    bold_widget.setChecked(dlg.selected_is_bold())
                if italic_widget is not None:
                    italic_widget.setChecked(dlg.selected_is_italic())

        focus_map = {
            "text_font_size": ("size", "글꼴 크기", "현재 편집 중인 글자 크기 값을 선택합니다."),
            "text_stroke_size": ("stroke", "획 크기", "현재 편집 중인 외곽선 두께 값을 선택합니다."),
            "text_line_spacing": ("line_spacing", "행간", "줄과 줄 사이 간격 값을 선택합니다."),
            "text_letter_spacing": ("letter_spacing", "자간", "글자와 글자 사이 간격 값을 선택합니다."),
            "text_char_width": ("char_width", "너비", "문자의 가로 비율 값을 선택합니다."),
            "text_char_height": ("char_height", "높이", "문자의 세로 비율 값을 선택합니다."),
        }
        for key, (control_name, title, desc) in focus_map.items():
            widget = controls.get(control_name)
            self.set_dialog_control_tooltip(widget, title, key, desc)
            self.add_dialog_shortcut(dialog, key, lambda w=widget: self.focus_dialog_control(w))

        toggle_map = {
            "text_bold_toggle": ("bold", "굵게"),
            "text_italic_toggle": ("italic", "기울이기"),
            "text_strike_toggle": ("strike", "취소선"),
        }
        for key, (control_name, title) in toggle_map.items():
            widget = controls.get(control_name)
            self.set_dialog_control_tooltip(widget, title, key, "")
            self.add_dialog_shortcut(dialog, key, lambda w=widget: w.click() if w is not None else None)

        font_widget = controls.get("font")
        self.set_dialog_control_tooltip(font_widget, "글꼴 선택", "item_font_select", "전용 글꼴 선택창을 엽니다.")
        self.add_dialog_shortcut(dialog, "item_font_select", open_font_selector)

    def open_font_select_dialog(self):
        """전용 글꼴 선택 창을 열어 선택 텍스트 또는 기본 글꼴에 적용한다."""
        try:
            current_family = self.cb_font.currentFont().family()
        except Exception:
            current_family = ""
        try:
            current_size = int(self.sb_font_size.value())
        except Exception:
            current_size = 24
        try:
            current_bold = bool(self.btn_bold.isChecked())
            current_italic = bool(self.btn_italic.isChecked())
        except Exception:
            current_bold = False
            current_italic = False

        dlg = FontSelectDialog(
            current_family=current_family,
            current_size=current_size,
            current_bold=current_bold,
            current_italic=current_italic,
            parent=self,
        )
        if dlg.exec() != QDialog.DialogCode.Accepted:
            return False

        family = dlg.selected_font_family()
        if not family:
            return False

        style_updates = {
            "font_family": family,
            "bold": dlg.selected_is_bold(),
            "italic": dlg.selected_is_italic(),
        }

        if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
            self.apply_style_to_selected(**style_updates)
        else:
            self.cb_font.setCurrentFont(QFont(family))
            try:
                self.btn_bold.setChecked(bool(style_updates["bold"]))
                self.btn_italic.setChecked(bool(style_updates["italic"]))
            except Exception:
                pass
            self.on_global_text_style_changed()

        self.log((f"🔤 Font selected: {family} / {dlg.selected_font_style()}" if self.ui_language == LANG_EN else f"🔤 글꼴 선택: {family} / {dlg.selected_font_style()}"))
        return True

    def set_combo_current_data(self, combo, data):
        """QComboBox의 userData 값으로 현재 항목을 선택한다."""
        try:
            for i in range(combo.count()):
                if str(combo.itemData(i)) == str(data):
                    combo.setCurrentIndex(i)
                    return True
        except Exception:
            pass
        return False


    def tr_ui(self, text):
        return translate_ui_text(text, getattr(self, "ui_language", LANG_KO))

    def tr_msg(self, text):
        return translate_ui_dynamic_text(text, getattr(self, "ui_language", LANG_KO))

    def display_project_name(self):
        """창 제목에 표시할 현재 파일명.
        .ysbt 파일명은 사람이 보는 이름 그대로 두고, UUID는 내부 manifest/작업 폴더에서만 관리한다.
        구버전 이름_고유번호.ysbt 파일을 열었을 때만 표시용으로 뒤쪽 코드를 숨긴다.
        """
        name = ""
        try:
            if getattr(self, "ysbt_package_path", None):
                name = Path(self.ysbt_package_path).stem
            elif getattr(self, "suggested_project_name", None):
                name = str(self.suggested_project_name)
        except Exception:
            name = ""
        if not name:
            return ""
        name = re.sub(r"_[0-9a-fA-F]{8,12}$", "", name)
        return name

    def update_window_title(self):
        is_en = normalize_ui_language(getattr(self, "ui_language", current_ui_language())) == LANG_EN
        base_name = APP_NAME_EN if is_en else APP_NAME_KO
        base = f"{base_name} {APP_VERSION}"
        project_name = self.display_project_name()
        try:
            self.setWindowTitle(f"{base} - {project_name}" if project_name else base)
        except Exception:
            pass

    def split_uuid_suffix_from_name(self, name: str):
        stem = clean_workspace_name(name or "ysb_project")
        m = re.match(r"^(.*)_([0-9a-fA-F]{8,12})$", stem)
        if m:
            return clean_workspace_name(m.group(1) or stem), m.group(2).lower()
        return stem, None

    def make_ysbt_path_with_uuid_suffix(self, path: str, project_uuid: str | None = None):
        """사용자가 고른 .ysbt 경로를 확정한다.

        v1.6 정책:
        - .ysbt 파일명에는 UUID를 붙이지 않는다.
        - UUID는 패키지 내부 manifest.json에 저장한다.
        - 작업 폴더를 만들 때만 파일명 뒤에 uuid 짧은값을 붙인다.

        함수명은 기존 호출부 호환을 위해 유지한다.
        반환: (ysbt_path, display_project_name, project_uuid)
        """
        path = self.normalize_ysb_path(path)
        path_obj = Path(path)
        display_name, existing_code = self.split_uuid_suffix_from_name(path_obj.stem)
        if project_uuid:
            final_uuid = str(project_uuid)
        elif existing_code:
            # 구버전 이름_고유번호.ysbt를 저장할 때도 파일명은 정리하되,
            # 기존 코드 앞자리는 내부 UUID에 이어받는다.
            random_tail = uuid.uuid4().hex[len(existing_code):]
            final_uuid = (existing_code + random_tail)[:32]
        else:
            final_uuid = uuid.uuid4().hex
        clean_path = path_obj.with_name(safe_project_name(display_name) + YSB_EXTENSION)
        return str(clean_path), display_name, final_uuid

    def translate_child_widgets(self, root_widget):
        """설정창/프리셋창처럼 나중에 생성되는 창의 고정 문구를 현재 언어로 바꾼다."""
        if root_widget is None:
            return
        try:
            for widget in root_widget.findChildren((QLabel, QPushButton, QCheckBox, QGroupBox, QRadioButton)):
                try:
                    txt = widget.text()
                except Exception:
                    continue
                if txt:
                    widget.setText(self.tr_msg(txt))
        except Exception:
            pass
        try:
            for combo in root_widget.findChildren(QComboBox):
                for i in range(combo.count()):
                    txt = combo.itemText(i)
                    if txt:
                        combo.setItemText(i, self.tr_msg(txt))
        except Exception:
            pass
        try:
            for spin in root_widget.findChildren(QSpinBox):
                if spin.specialValueText():
                    spin.setSpecialValueText(self.tr_ui(spin.specialValueText()))
        except Exception:
            pass
        try:
            for widget in root_widget.findChildren(QWidget):
                tip = widget.toolTip()
                if tip:
                    widget.setToolTip(self.tr_msg(tip))
        except Exception:
            pass

    def apply_language(self, language=None):
        """저장된 표시 언어를 메인 UI에 적용한다.
        사용자 원문/번역문 데이터는 건드리지 않고, 고정 UI 문구만 교체한다.
        """
        lang = normalize_ui_language(language or getattr(self, "ui_language", LANG_KO))
        self.ui_language = lang
        try:
            self.update_window_title()
        except Exception:
            pass

        # 메뉴 제목
        for attr, ko in (
            ("project_menu", "프로젝트"),
            ("work_menu", "작업"),
            ("batch_menu", "일괄 작업"),
            ("auto_menu", "자동화 작업"),
            ("settings_menu", "설정"),
            ("cloud_menu", "클라우드"),
            ("option_menu", "옵션"),
        ):
            menu = getattr(self, attr, None)
            if menu is not None:
                try:
                    menu.setTitle(self.tr_ui(ko))
                except Exception:
                    pass

        action_ko = {
            "project_new": "새로 만들기",
            "project_open": "열기",
            "project_open_json": "JSON으로 열기",
            "project_show_launcher": "홈화면으로 가기",
            "project_save": "저장하기",
            "project_save_as": "다른 이름으로 저장하기",
            "project_recover_last_work": "복구하기",
            "option_settings_overview": "설정 / 옵션",
            "work_tab_cycle": "작업탭 변경",
            "work_page_prev": "이전 페이지",
            "work_page_next": "다음 페이지",
            "work_open_current_project_folder": "현재 프로젝트의 작업 폴더로 이동하기",
            "work_analyze": "개별 분석",
            "work_text_number_width": "텍스트 넘버 크기 변경",
            "work_translate": "개별 번역",
            "work_inpaint": "개별 인페인팅",
            "work_inpaint_source": "인페인팅을 원본으로",
            "work_restore_original_source": "원본으로 돌아가기",
            "work_extract_text": "개별 지문 추출",
            "work_import_translation": "개별 번역문 불러오기",
            "work_clear_translation": "번역문 내용 지우기",
            "work_clean_text": "개별 텍스트 정리",
            "work_reset_text_rects": "현재 텍스트 기준 영역 재설정",
            "work_export": "개별 출력",
            "batch_analyze": "일괄 분석",
            "batch_translate": "일괄 번역",
            "batch_inpaint": "일괄 인페인팅",
            "batch_extract_text": "일괄 지문 추출",
            "batch_import_translation": "일괄 번역문 불러오기",
            "batch_clear_translation": "일괄 번역문 내용 지우기",
            "batch_clean_text": "일괄 텍스트 정리",
            "batch_reset_text_rects": "일괄 텍스트 기준 영역 재설정",
            "batch_export": "일괄 출력",
            "auto_text_size_current": "자동 텍스트 크기 조정",
            "auto_text_size_batch": "일괄 자동 텍스트 크기 조정",
            "auto_linebreak_current": "자동 줄 내림",
            "auto_linebreak_batch": "일괄 자동 줄 내림",
            "option_auto_save_mode": "자동저장 모드",
            "option_theme_settings": "테마 설정",
            "option_language_settings": "언어 설정",
            "option_api_settings": "API 관리",
            "option_translation_prompt": "번역 프롬프트 입력",
            "option_glossary": "단어장",
            "option_analysis_mask_settings": "분석 마스크 확장 비율",
            "option_workspace_location": "작업 폴더 위치 변경",
            "option_workspace_reset_default": "작업 폴더 위치 기본값으로 변경",
            "option_cleanup_temp_files": "임시 파일 관리",
            "option_register_ysb": ".ysbt 확장자 연결 등록",
            "option_unregister_ysbt": ".ysbt 확장자 연결 해제",
            "option_shortcut_settings": "단축키 통합 관리",
            "option_macro_settings": "매크로 관리",
            "option_text_preset_settings": "페이지 글꼴 프리셋 관리",
            "option_item_text_preset_settings": "개별 글꼴 프리셋 관리",
            "cloud_register": "클라우드 등록",
            "cloud_unregister": "클라우드 등록 해제",
            "cloud_cache_backup": "클라우드로 캐시 백업",
            "cloud_cache_restore": "클라우드에서 캐시 불러오기",
            "cloud_delete_backups": "클라우드 백업 삭제",
            "paint_magic_fill": "마스킹 칠하기",
            "paint_mask_wrap": "마스크 랩핑",
            "paint_mask_cut": "마스크 커팅",
            "paint_mask_wrap_rect": "마스크 선택 사각형",
            "paint_mask_wrap_free": "마스크 선택 자유형",
            "paint_mask_toggle": "마스크 ON/OFF",
            "view_text_toggle": "텍스트 표시 ON/OFF",
            "final_paint_color": "최종 페인팅 색상",
            "final_paint_to_background": "최종 페인팅을 배경으로 반영",
            "final_text_tool": "최종 텍스트 도구",
            "final_paint_above_toggle": "텍스트 위 페인팅 ON/OFF",
            "final_paint_opacity_inc": "최종 브러시 불투명도 증가",
            "final_paint_opacity_dec": "최종 브러시 불투명도 감소",
        }
        for key, ko in action_ko.items():
            action = self.actions.get(key)
            if action is not None:
                try:
                    action.setText(self.tr_ui(ko))
                except Exception:
                    pass

        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.set_language(lang)
        except Exception:
            pass

        # 현재 생성된 고정 UI 위젯의 텍스트를 교체한다.
        widget_types = (QLabel, QPushButton, QCheckBox, QGroupBox, QRadioButton)
        for widget in self.findChildren(widget_types):
            try:
                txt = widget.text()
            except Exception:
                continue
            if txt:
                new_txt = self.tr_ui(txt)
                if new_txt != txt:
                    try:
                        widget.setText(new_txt)
                    except Exception:
                        pass

        # 우측 텍스트 표 헤더
        try:
            if hasattr(self, "tab"):
                headers = ["ID", "X", self.tr_ui("원문"), self.tr_ui("번역")]
                self.tab.setHorizontalHeaderLabels(headers)
                for row in (0,):
                    item = self.tab.item(row, 2)
                    if item and item.text() in ("전체 선택", "Select All"):
                        item.setText(self.tr_ui("전체 선택"))
        except Exception:
            pass

        # 콤보박스 기본 항목
        try:
            if hasattr(self, "cb_text_preset"):
                for i in range(self.cb_text_preset.count()):
                    if self.cb_text_preset.itemData(i) == "__last__":
                        self.cb_text_preset.setItemText(i, self.tr_ui("마지막 설정"))
            if hasattr(self, "cb_item_text_preset"):
                for i in range(self.cb_item_text_preset.count()):
                    if self.cb_item_text_preset.itemData(i) == "__custom__":
                        self.cb_item_text_preset.setItemText(i, self.tr_ui("사용자지정"))
        except Exception:
            pass

        # 작업 탭/모드 콤보박스 항목
        try:
            if hasattr(self, "cb_mode"):
                mode_labels = ["1. 원본", "2. 분석도", "3. 텍스트 마스크", "4. 페인팅 마스크", "5. 최종결과"]
                cur = self.cb_mode.currentIndex()
                self.cb_mode.blockSignals(True)
                for i, ko in enumerate(mode_labels):
                    if i < self.cb_mode.count():
                        self.cb_mode.setItemText(i, self.tr_ui(ko))
                self.cb_mode.setCurrentIndex(cur)
                self.cb_mode.blockSignals(False)
        except Exception:
            try:
                self.cb_mode.blockSignals(False)
            except Exception:
                pass

        # 콤보박스 안의 기본 한국어 항목
        try:
            for combo in self.findChildren(QComboBox):
                for i in range(combo.count()):
                    txt = combo.itemText(i)
                    if txt:
                        new_txt = self.tr_ui(txt)
                        if new_txt != txt:
                            combo.setItemText(i, new_txt)
        except Exception:
            pass

        # 일부 위젯은 이모지/특수값 때문에 일반 순회 번역만으로는 바뀌지 않으므로 직접 보정한다.
        try:
            # 행간/자간은 수치 기반으로 표시한다. 행간 기본값은 100%, 자간 기본값은 0px.
            # QSpinBox specialValueText("자동")는 최솟값 전용이라 음수/기본값 UX와 충돌한다.
            if hasattr(self, "btn_analyze"):
                self.btn_analyze.setText(self.tr_ui("⚡ 분석"))
            if hasattr(self, "btn_text_mask_reanalyze"):
                self.btn_text_mask_reanalyze.setText(self.tr_ui("🔄 재분석"))
            if hasattr(self, "btn_mask_wrap_rect"):
                self.btn_mask_wrap_rect.setText(self.tr_ui("▭ 사각형"))
            if hasattr(self, "btn_mask_wrap_free"):
                self.btn_mask_wrap_free.setText(self.tr_ui("✎ 자유형"))
            if hasattr(self, "btn_mask_cut_rect"):
                self.btn_mask_cut_rect.setText(self.tr_ui("▭ 사각형"))
            if hasattr(self, "btn_mask_cut_free"):
                self.btn_mask_cut_free.setText(self.tr_ui("✎ 자유형"))
            if hasattr(self, "btn_translate"):
                self.btn_translate.setText(self.tr_ui("🌐 번역"))
            if hasattr(self, "btn_inpaint"):
                self.btn_inpaint.setText(self.tr_ui("🎨 인페인팅"))
            if hasattr(self, "btn_text_cleanup"):
                self.btn_text_cleanup.setText(self.tr_ui("🧹 텍스트 정리"))
            if hasattr(self, "btn_export_result"):
                self.btn_export_result.setText(self.tr_ui("📤 결과물 출력"))
            if hasattr(self, "sb_trans_chunk"):
                self.sb_trans_chunk.setSuffix(" items" if lang == LANG_EN else "개")
                self.sb_trans_chunk.setStatusTip(self.tr_msg("한 번의 API 요청에 묶어서 보낼 텍스트 줄 수"))
        except Exception:
            pass

        # 기본 툴팁 문구도 언어 설정에 맞춘다.
        try:
            for widget in self.findChildren(QWidget):
                tip = widget.toolTip()
                if tip:
                    new_tip = self.tr_ui(tip)
                    if new_tip != tip:
                        widget.setToolTip(new_tip)
        except Exception:
            pass

        try:
            self.configure_ui_tooltips()
        except Exception:
            pass

    def open_language_settings_dialog(self):
        """옵션 > 언어 설정."""
        old_language = normalize_ui_language(getattr(self, "ui_language", LANG_KO))

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui("언어 설정"))
        dialog.resize(360, 160)
        layout = QVBoxLayout(dialog)

        label = QLabel(self.tr_ui("표시 언어를 선택하세요.\n확인을 누르면 즉시 적용되고, 닫기를 누르면 변경하지 않습니다."))
        label.setWordWrap(True)
        layout.addWidget(label)

        combo = QComboBox(dialog)
        combo.addItem(self.tr_ui("한국어"), LANG_KO)
        combo.addItem("English", LANG_EN)
        combo.setCurrentIndex(1 if old_language == LANG_EN else 0)
        layout.addWidget(combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        dialog.setStyleSheet(self.settings_dialog_style())

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = normalize_ui_language(combo.currentData())
        self.ui_language = selected
        self.save_app_options_cache()
        self.apply_language(selected)
        self.log("🌐 Language changed: English" if selected == LANG_EN else "🌐 언어 변경: 한국어")

    def apply_theme(self, theme=None):
        """저장된 테마값에 따라 전체 UI 테마를 적용한다."""
        theme = str(theme or getattr(self, "ui_theme", THEME_DARK) or THEME_DARK).lower()
        if theme not in (THEME_DARK, THEME_LIGHT):
            theme = THEME_DARK
        self.ui_theme = theme
        if theme == THEME_LIGHT:
            self.apply_light_theme()
        else:
            self.apply_dark_theme()
        try:
            if hasattr(self, "launcher_widget"):
                self.launcher_widget.set_theme(theme)
        except Exception:
            pass
        self.force_theme_repaint_after_apply()

    def refresh_top_bars_for_theme(self):
        """Qt 내부 상단 영역만 현재 테마에 맞춘다.
        Windows 네이티브 제목 표시줄은 건드리지 않는다. 네이티브 프레임을 강제로
        다시 그리면 최소화/복원/전체화면 전환 뒤 포커스와 입력 상태가 꼬일 수 있다.
        """
        light = self.is_light_theme()
        try:
            mb = self.menuBar()
            if mb is not None:
                if light:
                    mb.setStyleSheet(
                        "QMenuBar { background-color:#ffffff; color:#22252b; border-bottom:1px solid #e0e6f0; padding:2px 4px; }"
                        "QMenuBar::item { background:transparent; padding:6px 10px; border-radius:0px; }"
                        "QMenuBar::item:selected { background:#edf4ff; color:#111827; }"
                    )
                else:
                    mb.setStyleSheet(
                        "QMenuBar { background-color:#1d1f23; color:#f2f4f8; border-bottom:1px solid #303640; padding:2px 4px; }"
                        "QMenuBar::item { background:transparent; padding:6px 10px; border-radius:0px; }"
                        "QMenuBar::item:selected { background:#303640; color:#ffffff; }"
                    )
                mb.update()
        except Exception:
            pass

        try:
            if hasattr(self, "log_w") and self.log_w:
                if light:
                    self.log_w.setStyleSheet("background:#ffffff;color:#25704a;border:1px solid #dfe5ef;border-radius:0px;")
                else:
                    self.log_w.setStyleSheet("background:#1f2228;color:#8ee0a1;border:1px solid #3b414c;border-radius:0px;")
                self.log_w.update()
        except Exception:
            pass

    def force_theme_repaint_after_apply(self):
        # 안전 원칙: 테마 적용은 1회만 수행한다.
        # 지연 타이머, processEvents, activateWindow/raise_, 네이티브 프레임 Redraw는 사용하지 않는다.
        self.refresh_top_bars_for_theme()
        try:
            self.update()
        except Exception:
            pass

    def open_theme_settings_dialog(self):
        """옵션 > 테마 설정."""
        old_theme = str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK).lower()
        if old_theme not in (THEME_DARK, THEME_LIGHT):
            old_theme = THEME_DARK

        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui("테마 설정"))
        dialog.resize(360, 170)
        layout = QVBoxLayout(dialog)

        label = QLabel(self.tr_ui("화면에 적용할 테마를 선택하세요.\n확인을 누르면 즉시 적용되고, 닫기를 누르면 변경하지 않습니다."))
        label.setWordWrap(True)
        layout.addWidget(label)

        combo = QComboBox(dialog)
        combo.addItem(self.tr_ui("다크 테마"), THEME_DARK)
        combo.addItem(self.tr_ui("화이트 테마"), THEME_LIGHT)
        combo.setCurrentIndex(0 if old_theme == THEME_DARK else 1)
        layout.addWidget(combo)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel, dialog)
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(self.tr_ui("확인"))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(self.tr_ui("닫기"))
        buttons.accepted.connect(dialog.accept)
        buttons.rejected.connect(dialog.reject)
        layout.addWidget(buttons)

        # 현재 테마에 맞춰 설정창도 어색하지 않게 표시한다.
        if old_theme == THEME_LIGHT:
            dialog.setStyleSheet("""
                QDialog { background:#f6f7f9; color:#202124; }
                QLabel { color:#202124; }
                QComboBox { background:#ffffff; color:#202124; border:1px solid #b9bec7; padding:4px; }
                QPushButton { background:#ffffff; color:#202124; border:1px solid #aeb4bf; padding:5px 14px; }
                QPushButton:hover { background:#e9eef7; }
            """)
        else:
            dialog.setStyleSheet("""
                QDialog { background:#1f1f22; color:#f2f2f2; }
                QLabel { color:#f2f2f2; }
                QComboBox { background:#2d2f34; color:#f5f5f5; border:1px solid #53565f; padding:4px; }
                QPushButton { background:#353841; color:#f2f2f2; border:1px solid #5a5d66; padding:5px 14px; }
                QPushButton:hover { background:#424652; }
            """)

        if dialog.exec() != QDialog.DialogCode.Accepted:
            return

        selected = str(combo.currentData() or THEME_DARK)
        if selected not in (THEME_DARK, THEME_LIGHT):
            selected = THEME_DARK
        self.ui_theme = selected
        self.save_app_options_cache()
        self.apply_theme(selected)
        self.log(f"🎨 테마 변경: {'화이트 테마' if selected == THEME_LIGHT else '다크 테마'}")

    def apply_native_title_bar_theme(self, widget=None, dark=None):
        """Windows 네이티브 제목 표시줄 테마 적용은 공개판에서 비활성화한다.

        DwmSetWindowAttribute/SetWindowPos/RedrawWindow 같은 비클라이언트 영역 갱신은
        Windows와 Qt의 포커스 이벤트를 계속 흔들 수 있다. 색상 일치보다 입력 안정성을
        우선하므로 제목 표시줄은 OS 기본 동작에 맡긴다.
        """
        return

    def schedule_native_title_bar_theme(self, widget=None, dark=None):
        """네이티브 제목 표시줄 지연 갱신 비활성화.
        최소화/복원/전체화면 전환 뒤 버벅임과 먹통을 막기 위해 아무 작업도 하지 않는다.
        """
        return

    def apply_tooltip_theme(self, light=None):
        """QToolTip은 OS/Qt 기본 팔레트 영향을 많이 받아 글자색이 흐려질 수 있다.
        테마 적용 시마다 팔레트와 앱 스타일시트를 같이 고정해 대비를 보장한다.
        """
        if light is None:
            light = self.is_light_theme() if hasattr(self, "is_light_theme") else False

        app = QApplication.instance()
        if light:
            bg = QColor("#ffffff")
            fg = QColor("#111827")
            border = "#cfd7e5"
        else:
            bg = QColor("#1f2430")
            fg = QColor("#ffffff")
            border = "#4b5563"

        pal = QPalette()
        pal.setColor(QPalette.ColorRole.ToolTipBase, bg)
        pal.setColor(QPalette.ColorRole.ToolTipText, fg)
        try:
            QToolTip.setPalette(pal)
        except Exception:
            pass

        if app:
            try:
                app.setStyleSheet(
                    "QToolTip { "
                    f"background-color:{bg.name()}; "
                    f"color:{fg.name()}; "
                    f"border:1px solid {border}; "
                    "border-radius:0px; "
                    "padding:5px; "
                    "}"
                )
            except Exception:
                pass

    def apply_light_theme(self):
        """화이트 테마를 부드러운 카드형 톤으로 적용한다."""
        app = QApplication.instance()
        if app:
            app.setStyleSheet("""
                QToolTip { background-color:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:5px; }
            """)
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor("#f4f6fa"))
            pal.setColor(QPalette.ColorRole.WindowText, QColor("#22252b"))
            pal.setColor(QPalette.ColorRole.Base, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#f7f9fd"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#22252b"))
            pal.setColor(QPalette.ColorRole.Button, QColor("#f8fafc"))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor("#22252b"))
            pal.setColor(QPalette.ColorRole.Highlight, QColor("#dbeafe"))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#111827"))
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#111827"))
            app.setPalette(pal)
            self.apply_tooltip_theme(light=True)

        self.setStyleSheet("""
            QMainWindow, QWidget { background-color:#f4f6fa; color:#22252b; }
            QMenuBar {
                background-color:#ffffff;
                color:#22252b;
                border-bottom:1px solid #e0e6f0;
                padding:2px 4px;
            }
            QMenuBar::item { background:transparent; padding:6px 10px; border-radius:0px; }
            QMenuBar::item:selected { background:#edf4ff; }
            QMenu {
                background-color:#ffffff;
                color:#22252b;
                border:1px solid #dfe5ef;
                border-radius:0px;
                padding:6px;
            }
            QMenu::separator { height:1px; background:#e3e8f1; margin:6px 6px; }
            QMenu::item { padding:7px 28px 7px 12px; border-radius:0px; }
            QMenu::item:selected { background-color:#edf4ff; color:#111827; }
            QMessageBox { background:#f4f6fa; color:#111827; }
            QMessageBox QLabel { color:#111827; }
            QMessageBox QPushButton { background:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:4px 10px; min-width:56px; }
            QMessageBox QPushButton:hover { background:#edf4ff; border-color:#aac4e8; }
            QLabel, QCheckBox, QRadioButton, QGroupBox { color:#22252b; }
            QGroupBox {
                border:1px solid #dfe5ef;
                border-radius:0px;
                margin-top:12px;
                padding:10px;
                background:#ffffff;
            }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; color:#374151; }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {
                background-color:#ffffff;
                color:#22252b;
                border:1px solid #cfd7e5;
                border-radius:0px;
                padding:3px 6px;
                selection-background-color:#dbeafe;
                selection-color:#111827;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
                border:1px solid #8fb4e8;
            }
            QAbstractItemView {
                background-color:#ffffff;
                color:#22252b;
                border:1px solid #dfe5ef;
                border-radius:0px;
                alternate-background-color:#f7f9fd;
                selection-background-color:#dbeafe;
                selection-color:#111827;
                gridline-color:#e4eaf3;
            }
            QHeaderView::section {
                background-color:#f1f4f9;
                color:#374151;
                border:0;
                border-right:1px solid #dfe5ef;
                padding:7px;
            }
            QPushButton {
                background-color:#f8fafc;
                color:#22252b;
                border:1px solid #cfd7e5;
                border-radius:0px;
                padding:4px 10px;
            }
            QPushButton:hover { background-color:#edf4ff; border-color:#aac4e8; }
            QPushButton:pressed { background-color:#e3edf9; }
            QPushButton:disabled { background-color:#edf0f5; color:#9aa4b2; border-color:#dde3ec; }
            QToolBar {
                background-color:#eef2f8;
                border:1px solid #dfe5ef;
                border-radius:0px;
                spacing:5px;
                padding:4px;
            }
            QToolButton {
                background-color:#f8fafc;
                color:#22252b;
                border:1px solid #cfd7e5;
                border-radius:0px;
                padding:5px;
            }
            QToolButton:hover { background-color:#edf4ff; border-color:#aac4e8; }
            QToolButton:checked { background-color:#dbeafe; border-color:#8fb4e8; }
            QCheckBox::indicator, QRadioButton::indicator {
                width:15px; height:15px;
                border:1px solid #aab4c3;
                background:#ffffff;
                border-radius:0px;
            }
            QRadioButton::indicator { border-radius:0px; }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked { background:#7aa8e8; border:1px solid #7aa8e8; }
            QSplitter::handle { background:#dfe5ef; }
            QTabWidget::pane { border:1px solid #dfe5ef; border-radius:0px; background:#ffffff; }
            QTabBar::tab {
                background:#edf1f7;
                color:#4b5563;
                padding:8px 12px;
                border:1px solid #d9e0ea;
                border-bottom:none;
                border-top-left-radius:10px;
                border-top-right-radius:3px;
            }
            QTabBar::tab:selected { background:#ffffff; color:#1f232b; font-weight:bold; }
            QTabBar::tab:hover { background:#edf4ff; }
            QScrollBar:vertical { background:#eef2f8; width:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:vertical { background:#cbd5e1; min-height:30px; border-radius:0px; }
            QScrollBar::handle:vertical:hover { background:#b7c3d4; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background:#eef2f8; height:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:horizontal { background:#cbd5e1; min-width:30px; border-radius:0px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            QToolTip { background-color:#ffffff; color:#111827; border:1px solid #cfd7e5; border-radius:0px; padding:5px; }
        """)
        if hasattr(self, 'tb') and self.tb:
            self.tb.setStyleSheet("background:#eef2f8; border:1px solid #dfe5ef; border-radius:0px;")
        if hasattr(self, 'mask_toggle_wrap') and self.mask_toggle_wrap:
            self.mask_toggle_wrap.setStyleSheet("")
        if hasattr(self, 'btn_page') and self.btn_page:
            self.btn_page.setStyleSheet("border:none; font-weight:bold; color:#22252b;")
        if hasattr(self, 'tab') and self.tab:
            self.tab.setStyleSheet(
                "QTableWidget { background:#ffffff; color:#22252b; gridline-color:#e4eaf3; border:1px solid #dfe5ef; border-radius:0px; }"
                "QTableWidget::item:selected { background:#dbeafe; color:#111827; }"
                "QTableWidget QTableCornerButton::section { background:#f1f4f9; border:1px solid #dfe5ef; }"
            )
            self.repaint_text_table_theme()
        if hasattr(self, 'log_w') and self.log_w:
            self.log_w.setStyleSheet("background:#ffffff;color:#25704a;border:1px solid #dfe5ef;border-radius:0px;")
        self.update_color_button_styles()
        self.schedule_native_title_bar_theme(self, dark=False)

    def apply_dark_theme(self):
        """다크 테마를 홈/클라우드와 맞는 부드러운 카드형 톤으로 적용한다."""
        app = QApplication.instance()
        if app:
            app.setStyleSheet("""
                QToolTip { background-color:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:0px; padding:5px; }
            """)
            pal = QPalette()
            pal.setColor(QPalette.ColorRole.Window, QColor("#202226"))
            pal.setColor(QPalette.ColorRole.WindowText, QColor("#f2f4f8"))
            pal.setColor(QPalette.ColorRole.Base, QColor("#24282f"))
            pal.setColor(QPalette.ColorRole.AlternateBase, QColor("#282d35"))
            pal.setColor(QPalette.ColorRole.Text, QColor("#f2f4f8"))
            pal.setColor(QPalette.ColorRole.Button, QColor("#333843"))
            pal.setColor(QPalette.ColorRole.ButtonText, QColor("#f2f4f8"))
            pal.setColor(QPalette.ColorRole.Highlight, QColor("#3d587d"))
            pal.setColor(QPalette.ColorRole.HighlightedText, QColor("#ffffff"))
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#1f2430"))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#ffffff"))
            app.setPalette(pal)

        self.setStyleSheet("""
            QMainWindow, QWidget { background-color:#202226; color:#f2f4f8; }
            QMenuBar {
                background-color:#1d1f23;
                color:#f2f4f8;
                border-bottom:1px solid #303640;
                padding:2px 4px;
            }
            QMenuBar::item { background:transparent; padding:6px 10px; border-radius:0px; }
            QMenuBar::item:selected { background:#303640; }
            QMenu {
                background-color:#282c33;
                color:#f2f4f8;
                border:1px solid #3b414c;
                border-radius:0px;
                padding:6px;
            }
            QMenu::separator { height:1px; background:#3b414c; margin:6px 6px; }
            QMenu::item { padding:7px 28px 7px 12px; border-radius:0px; }
            QMenu::item:selected { background-color:#38404c; color:#ffffff; }
            QMessageBox { background:#24272d; color:#f2f4f8; }
            QMessageBox QLabel { color:#f2f4f8; }
            QMessageBox QPushButton { background:#333843; color:#f2f4f8; border:1px solid #586173; border-radius:0px; padding:4px 10px; min-width:56px; }
            QMessageBox QPushButton:hover { background:#3d4654; border-color:#74839a; }
            QLabel, QCheckBox, QRadioButton, QGroupBox { color:#f2f4f8; }
            QGroupBox {
                border:1px solid #3b414c;
                border-radius:0px;
                margin-top:12px;
                padding:10px;
                background:#282c33;
            }
            QGroupBox::title { subcontrol-origin:margin; left:12px; padding:0 5px; color:#d7deea; }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox, QKeySequenceEdit {
                background-color:#1f2228;
                color:#f5f7fb;
                border:1px solid #434a56;
                border-radius:0px;
                padding:3px 6px;
                selection-background-color:#4c6f9f;
                selection-color:#ffffff;
            }
            QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus, QFontComboBox:focus, QSpinBox:focus, QDoubleSpinBox:focus, QKeySequenceEdit:focus {
                border:1px solid #7ea2d6;
                background:#222630;
            }
            QAbstractItemView {
                background-color:#24282f;
                color:#f2f4f8;
                border:1px solid #3b414c;
                border-radius:0px;
                alternate-background-color:#282d35;
                selection-background-color:#3d587d;
                selection-color:#ffffff;
                gridline-color:#38404a;
            }
            QHeaderView::section {
                background-color:#2d323b;
                color:#d7deea;
                border:0;
                border-right:1px solid #3b414c;
                padding:7px;
            }
            QPushButton {
                background-color:#333843;
                color:#f2f4f8;
                border:1px solid #555d6c;
                border-radius:0px;
                padding:4px 10px;
            }
            QPushButton:hover { background-color:#3d4654; border-color:#718098; }
            QPushButton:pressed { background-color:#2b303a; }
            QPushButton:disabled { background-color:#2a2d33; color:#858d9a; border-color:#3f4550; }
            QToolBar {
                background-color:#24282f;
                border:1px solid #3b414c;
                border-radius:0px;
                spacing:5px;
                padding:4px;
            }
            QToolButton {
                background-color:#333843;
                color:#f2f4f8;
                border:1px solid #555d6c;
                border-radius:0px;
                padding:5px;
            }
            QToolButton:hover { background-color:#3d4654; border-color:#718098; }
            QToolButton:checked { background-color:#3d587d; border-color:#7ea2d6; }
            QCheckBox::indicator, QRadioButton::indicator {
                width:15px; height:15px;
                border:1px solid #6f7786;
                background:#1f2228;
                border-radius:0px;
            }
            QRadioButton::indicator { border-radius:0px; }
            QCheckBox::indicator:checked, QRadioButton::indicator:checked { background:#78a6e6; border:1px solid #78a6e6; }
            QSplitter::handle { background:#303640; }
            QTabWidget::pane { border:1px solid #3b414c; border-radius:0px; background:#24282f; }
            QTabBar::tab {
                background:#2a2e36;
                color:#b5bfce;
                padding:8px 12px;
                border:1px solid #3b414c;
                border-bottom:none;
                border-top-left-radius:10px;
                border-top-right-radius:3px;
            }
            QTabBar::tab:selected { background:#333842; color:#ffffff; font-weight:bold; }
            QTabBar::tab:hover { background:#38404c; }
            QScrollBar:vertical { background:#20242b; width:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:vertical { background:#424a57; min-height:30px; border-radius:0px; }
            QScrollBar::handle:vertical:hover { background:#566173; }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height:0; }
            QScrollBar:horizontal { background:#20242b; height:12px; margin:0; border:0; border-radius:0px; }
            QScrollBar::handle:horizontal { background:#424a57; min-width:30px; border-radius:0px; }
            QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width:0; }
            QToolTip { background-color:#1f2430; color:#ffffff; border:1px solid #4b5563; border-radius:0px; padding:5px; }
        """)
        if hasattr(self, 'tb') and self.tb:
            self.tb.setStyleSheet("background:#24282f; border:1px solid #3b414c; border-radius:0px;")
        if hasattr(self, 'mask_toggle_wrap') and self.mask_toggle_wrap:
            self.mask_toggle_wrap.setStyleSheet("")
        if hasattr(self, 'btn_page') and self.btn_page:
            self.btn_page.setStyleSheet("border:none; font-weight:bold; color:#f2f4f8;")
        if hasattr(self, 'tab') and self.tab:
            self.tab.setStyleSheet(
                "QTableWidget { background:#24282f; color:#f2f4f8; gridline-color:#38404a; border:1px solid #3b414c; border-radius:0px; }"
                "QTableWidget::item:selected { background:#3d587d; color:#ffffff; }"
                "QTableWidget QTableCornerButton::section { background:#2d323b; border:1px solid #3b414c; }"
            )
            self.repaint_text_table_theme()
        if hasattr(self, 'log_w') and self.log_w:
            self.log_w.setStyleSheet("background:#1f2228;color:#8ee0a1;border:1px solid #3b414c;border-radius:0px;")
        self.update_color_button_styles()

    # =========================================================
    # 스타일 / 마스크 / 텍스트 파일 유틸
    # =========================================================
    def make_color_icon(self, color_value):
        pix = QPixmap(22, 22)
        pix.fill(Qt.GlobalColor.transparent)
        painter = QPainter(pix)
        c = QColor(str(color_value or "#FFFFFF"))
        if not c.isValid():
            c = QColor("#FFFFFF")
        painter.setPen(QPen(QColor("#777777"), 1))
        painter.setBrush(QBrush(c))
        painter.drawRect(2, 2, 18, 18)
        painter.end()
        return QIcon(pix)

    def update_color_button_styles(self):
        pairs = [
            (getattr(self, "btn_text_color", None), self.default_text_color, "문자 색상"),
            (getattr(self, "btn_stroke_color", None), self.default_stroke_color, "획 색상"),
            (getattr(self, "btn_item_text_color", None), self.default_text_color, "문자 색상"),
            (getattr(self, "btn_item_stroke_color", None), self.default_stroke_color, "획 색상"),
        ]
        for btn, color, tooltip in pairs:
            if btn:
                btn.setText("")
                btn.setStatusTip(f"{tooltip}: {color}")
                btn.setFixedSize(26, 26)
                btn.setStyleSheet(f"background:{color}; border:1px solid #555d6c; border-radius:0px; padding:0px;")

        if hasattr(self, "act_final_paint_color"):
            self.act_final_paint_color.setIcon(self.make_color_icon(self.final_paint_color))
            self.act_final_paint_color.setText("")
            self.act_final_paint_color.setStatusTip(f"최종 페인팅 색상: {self.final_paint_color}")

    def text_preset_dir(self):
        path = get_cache_dir() / "text_preset"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def text_preset_path(self, name):
        safe = str(name or "preset").strip().replace("/", "_").replace("\\", "_")
        return self.text_preset_dir() / f"{safe}.json"

    def last_text_preset_path(self):
        return self.text_preset_dir() / "_last_preset.json"

    def text_preset_state_path(self):
        return self.text_preset_dir() / "_preset_state.json"

    def item_text_preset_dir(self):
        path = get_cache_dir() / "item_text_preset"
        path.mkdir(parents=True, exist_ok=True)
        return path

    def item_text_preset_path(self, name):
        safe = self.safe_preset_name(name)
        return self.item_text_preset_dir() / f"{safe}.json"

    def item_text_preset_state_path(self):
        return self.item_text_preset_dir() / "_item_preset_state.json"

    def load_item_text_preset_state(self):
        try:
            with open(self.item_text_preset_state_path(), "r", encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}
        state.setdefault("style", self.current_style_snapshot() if hasattr(self, "cb_font") else {})
        state.setdefault("include", {k: True for k, _ in self.style_field_specs()})
        return state

    def save_item_text_preset_state(self, style=None, include=None, selected=None):
        state = {
            "style": self.normalize_style_dict(style or self.current_style_snapshot()),
            "include": {k: bool((include or {}).get(k, False)) for k, _ in self.style_field_specs()},
            "selected": selected or None,
        }
        self.item_text_preset_dir().mkdir(parents=True, exist_ok=True)
        with open(self.item_text_preset_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


    def safe_preset_name(self, name):
        safe = str(name or "preset").strip().replace("/", "_").replace("\\", "_")
        return safe or "preset"

    def style_field_specs(self):
        return [
            ("font_family", "폰트"),
            ("font_size", "크기"),
            ("text_color", "문자색"),
            ("stroke_width", "획"),
            ("stroke_color", "획색"),
            ("align", "정렬"),
            ("line_spacing", "행간"),
            ("letter_spacing", "자간"),
            ("char_width", "너비"),
            ("char_height", "높이"),
            ("bold", "굵게"),
            ("italic", "기울임"),
            ("strike", "취소선"),
        ]

    def style_summary_text(self, style, include=None):
        style = self.normalize_style_dict(style)
        include = include or {k: True for k, _ in self.style_field_specs()}
        parts = []
        def yes(v): return "ON" if v else "OFF"
        for key, label in self.style_field_specs():
            if not include.get(key, False):
                continue
            value = style.get(key)
            if key == "font_family":
                value = str(value)
            elif key == "font_size":
                value = f"{value}px"
            elif key == "stroke_width":
                value = f"{value}px"
            elif key in ("line_spacing",):
                value = f"{100 if int(value or 0) == 0 else value}%"
            elif key in ("letter_spacing",):
                value = "자동" if int(value or 0) == 0 else f"{value}px"
            elif key in ("char_width", "char_height"):
                value = f"{value}%"
            elif key in ("bold", "italic", "strike"):
                value = yes(bool(value))
            parts.append(f"{label}:{value}")
        return " / ".join(parts) if parts else "포함 옵션 없음"

    def page_preset_state(self):
        try:
            with open(self.text_preset_state_path(), "r", encoding="utf-8") as f:
                state = json.load(f)
            if not isinstance(state, dict):
                state = {}
        except Exception:
            state = {}
        state.setdefault("active", "__last__")
        state.setdefault("enabled", {})
        return state

    def save_page_preset_state(self, state):
        state = dict(state or {})
        state.setdefault("active", "__last__")
        state.setdefault("enabled", {})
        self.text_preset_dir().mkdir(parents=True, exist_ok=True)
        with open(self.text_preset_state_path(), "w", encoding="utf-8") as f:
            json.dump(state, f, ensure_ascii=False, indent=2)


    def current_style_snapshot(self):
        return self.normalize_style_dict({
            "font_family": self.cb_font.currentFont().family(),
            "font_size": int(self.sb_font_size.value()),
            "stroke_width": int(self.sb_strk.value()),
            "text_color": self.default_text_color,
            "stroke_color": self.default_stroke_color,
            "align": self.default_align,
            "line_spacing": int(self.sb_line_spacing.value()) if hasattr(self, "sb_line_spacing") else self.default_line_spacing,
            "letter_spacing": int(self.sb_letter_spacing.value()) if hasattr(self, "sb_letter_spacing") else self.default_letter_spacing,
            "char_width": int(self.sb_char_width.value()) if hasattr(self, "sb_char_width") else self.default_char_width,
            "char_height": int(self.sb_char_height.value()) if hasattr(self, "sb_char_height") else self.default_char_height,
            "bold": bool(self.btn_bold.isChecked()) if hasattr(self, "btn_bold") else self.default_bold,
            "italic": bool(self.btn_italic.isChecked()) if hasattr(self, "btn_italic") else self.default_italic,
            "strike": bool(self.btn_strike.isChecked()) if hasattr(self, "btn_strike") else self.default_strike,
        })

    def normalize_style_dict(self, style):
        style = dict(style or {})
        align = str(style.get("align") or "center").lower()
        if align not in ("left", "center", "right"):
            align = "center"

        def _int(key, default, lo=None, hi=None):
            try:
                value = int(style.get(key, default))
            except Exception:
                value = default
            if lo is not None:
                value = max(lo, value)
            if hi is not None:
                value = min(hi, value)
            return value

        return {
            "font_family": str(style.get("font_family") or self.cb_font.currentFont().family()),
            "font_size": _int("font_size", self.sb_font_size.value(), 1, 1000),
            "stroke_width": _int("stroke_width", self.sb_strk.value(), 0, 300),
            "text_color": str(style.get("text_color") or "#000000"),
            "stroke_color": str(style.get("stroke_color") or "#FFFFFF"),
            "align": align,
            "line_spacing": _int("line_spacing", 100, 50, 300),
            "letter_spacing": _int("letter_spacing", 0, -500, 500),
            "char_width": _int("char_width", 100, 10, 300),
            "char_height": _int("char_height", 100, 10, 300),
            "bold": bool(style.get("bold", False)),
            "italic": bool(style.get("italic", False)),
            "strike": bool(style.get("strike", False)),
        }

    def apply_style_to_controls(self, style):
        style = self.normalize_style_dict(style)
        self._style_signal_lock = True
        try:
            self.cb_font.setCurrentFont(QFont(style["font_family"]))
            self.sb_font_size.setValue(int(style["font_size"]))
            self.sb_strk.setValue(int(style["stroke_width"]))
            self.default_text_color = style["text_color"]
            self.default_stroke_color = style["stroke_color"]
            self.default_align = style["align"]
            if hasattr(self, "sb_line_spacing"):
                self.sb_line_spacing.setValue(100 if int(style["line_spacing"] or 0) == 0 else int(style["line_spacing"]))
            if hasattr(self, "sb_letter_spacing"):
                self.sb_letter_spacing.setValue(int(style["letter_spacing"]))
            if hasattr(self, "sb_char_width"):
                self.sb_char_width.setValue(int(style["char_width"]))
            if hasattr(self, "sb_char_height"):
                self.sb_char_height.setValue(int(style["char_height"]))
            if hasattr(self, "btn_bold"):
                self.btn_bold.setChecked(bool(style["bold"]))
            if hasattr(self, "btn_italic"):
                self.btn_italic.setChecked(bool(style["italic"]))
            if hasattr(self, "btn_strike"):
                self.btn_strike.setChecked(bool(style["strike"]))
            self.update_color_button_styles()
        finally:
            self._style_signal_lock = False


    def save_last_text_preset(self, active="__last__"):
        if not hasattr(self, "cb_font"):
            return
        try:
            self.text_preset_dir().mkdir(parents=True, exist_ok=True)
            with open(self.last_text_preset_path(), "w", encoding="utf-8") as f:
                json.dump(self.current_style_snapshot(), f, ensure_ascii=False, indent=2)
            state = self.page_preset_state()
            state["active"] = active
            self.save_page_preset_state(state)
        except Exception as e:
            self.log(f"⚠️ 프리셋 자동저장 실패: {e}")

    def load_text_preset_cache(self):
        if not hasattr(self, "cb_text_preset"):
            return
        self._preset_loading = True
        self.text_presets = {}
        self.cb_text_preset.blockSignals(True)
        try:
            self.cb_text_preset.clear()
            self.cb_text_preset.addItem("마지막 설정", "__last__")
            preset_dir = self.text_preset_dir()
            for path in sorted(preset_dir.glob("*.json")):
                if path.name.startswith("_"):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        style = self.normalize_style_dict(json.load(f))
                    name = path.stem
                    self.text_presets[name] = style
                    self.cb_text_preset.addItem(name, name)
                except Exception:
                    continue

            state = self.page_preset_state()
            active = str(state.get("active") or "__last__")

            style = None
            if active != "__last__" and active in self.text_presets:
                style = self.text_presets[active]
                idx = self.cb_text_preset.findData(active)
                if idx >= 0:
                    self.cb_text_preset.setCurrentIndex(idx)
            else:
                try:
                    with open(self.last_text_preset_path(), "r", encoding="utf-8") as f:
                        style = self.normalize_style_dict(json.load(f))
                except Exception:
                    style = self.current_style_snapshot()
                self.cb_text_preset.setCurrentIndex(0)

            if style:
                self.apply_style_to_controls(style)
        finally:
            self.cb_text_preset.blockSignals(False)
            self._preset_loading = False
        self.save_last_text_preset(self.cb_text_preset.currentData() or "__last__")

    def on_text_preset_selected(self, *args):
        if self._preset_loading:
            return
        key = self.cb_text_preset.currentData() or "__last__"
        if key == "__last__":
            try:
                with open(self.last_text_preset_path(), "r", encoding="utf-8") as f:
                    style = self.normalize_style_dict(json.load(f))
            except Exception:
                style = self.current_style_snapshot()
        else:
            style = self.text_presets.get(str(key))
            if not style:
                return
        self.apply_style_to_controls(style)
        applied_to_selection = False
        if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
            self.apply_style_to_selected(**style)
            applied_to_selection = True
        self.save_last_text_preset(str(key))
        preset_label = self.cb_text_preset.currentText()
        self.log(f"🎛️ 글꼴 프리셋 로딩: {preset_label}")
        # 글꼴 프리셋은 일반 스타일 변경과 같은 Undo 대상이다.
        # 매크로와 달리 Undo 체인을 끊지 않는다.

    def save_text_preset_named(self):
        name, ok = QInputDialog.getText(self, "프리셋 저장", "저장할 프리셋 이름:")
        if not ok or not name.strip():
            return
        safe = name.strip().replace("/", "_").replace("\\", "_")
        path = self.text_preset_path(safe)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.current_style_snapshot(), f, ensure_ascii=False, indent=2)
        self.load_text_preset_cache()
        idx = self.cb_text_preset.findData(safe)
        if idx >= 0:
            self.cb_text_preset.setCurrentIndex(idx)
        self.save_last_text_preset(safe)
        self.log(f"💾 글꼴 프리셋 저장: {safe}")

    def import_text_preset_json(self):
        path, _ = QFileDialog.getOpenFileName(self, "글꼴 프리셋 JSON 가져오기", str(self.text_preset_dir()), "JSON (*.json)")
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8-sig") as f:
                style = self.normalize_style_dict(json.load(f))
        except Exception as e:
            QMessageBox.warning(self, "가져오기 실패", f"프리셋 JSON을 읽지 못했습니다.\n{e}")
            return
        default_name = Path(path).stem
        name, ok = QInputDialog.getText(self, "프리셋 이름", "저장할 프리셋 이름:", text=default_name)
        if not ok or not name.strip():
            return
        safe = name.strip().replace("/", "_").replace("\\", "_")
        with open(self.text_preset_path(safe), "w", encoding="utf-8") as f:
            json.dump(style, f, ensure_ascii=False, indent=2)
        self.load_text_preset_cache()
        idx = self.cb_text_preset.findData(safe)
        if idx >= 0:
            self.cb_text_preset.setCurrentIndex(idx)
        self.log(f"📥 글꼴 프리셋 가져오기 완료: {safe}")

    def normalize_shortcut_text(self, shortcut):
        """단축키 비교용 PortableText 정규화."""
        try:
            if isinstance(shortcut, QKeySequence):
                seq = shortcut
            else:
                seq = QKeySequence(str(shortcut or ""))
            return seq.toString(QKeySequence.SequenceFormat.PortableText)
        except Exception:
            return str(shortcut or "").strip()

    def standard_shortcut_label(self, key):
        if hasattr(self, "shortcut_label_map") and key in self.shortcut_label_map:
            return self.shortcut_label_map.get(key, key)
        if hasattr(self, "actions") and key in self.actions:
            return self.actions[key].text()
        return str(key)

    def ask_disable_conflict(self, parent, title, message):
        return QMessageBox.question(
            parent or self,
            title,
            message,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def resolve_conflicts_for_item_preset_shortcut(self, owner_name, seq_text, parent=None):
        """개별 글꼴 프리셋 단축키 지정 시 일반 단축키/매크로/다른 개별 프리셋과 충돌 검사.
        후입 우선: 사용자가 허용하면 기존 상대방을 비활성화한다.
        """
        seq_text = self.normalize_shortcut_text(seq_text)
        if not seq_text:
            return True

        # 1) 일반 단축키와 충돌하면 일반 단축키 OFF
        for key, shortcut in list(self.shortcut_settings.shortcuts.items()):
            if not self.shortcut_settings.enabled.get(key, True):
                continue
            if shortcut and self.normalize_shortcut_text(shortcut) == seq_text:
                label = self.standard_shortcut_label(key)
                ok = self.ask_disable_conflict(
                    parent,
                    "기존 단축키 비활성화 확인",
                    f"'{label}' 기능이 같은 단축키를 사용 중입니다.\n\n"
                    f"기존 단축키를 비활성화하고 '{owner_name}' 개별 글꼴 프리셋에 지정할까요?",
                )
                if not ok:
                    return False
                self.shortcut_settings.enabled[key] = False
                self.shortcut_settings.shortcuts[key] = ""

        # 2) 매크로와 충돌하면 매크로 OFF
        for macro in getattr(self.shortcut_settings, "macros", []) or []:
            if not macro.get("enabled", True):
                continue
            macro_seq = str(macro.get("shortcut", "") or "")
            if macro_seq and self.normalize_shortcut_text(macro_seq) == seq_text:
                macro_name = str(macro.get("name", "매크로"))
                ok = self.ask_disable_conflict(
                    parent,
                    "매크로 단축키 비활성화 확인",
                    f"'{macro_name}' 매크로가 같은 단축키를 사용 중입니다.\n\n"
                    f"매크로를 비활성화하고 '{owner_name}' 개별 글꼴 프리셋에 지정할까요?",
                )
                if not ok:
                    return False
                macro["enabled"] = False
                macro["shortcut"] = ""

        # 3) 다른 개별 글꼴 프리셋과 충돌하면 기존 개별 프리셋 OFF
        for name, preset in list(getattr(self, "item_text_presets", {}).items()):
            if str(name) == str(owner_name):
                continue
            if not preset.get("enabled", True):
                continue
            other_seq = str(preset.get("shortcut", "") or "")
            if other_seq and self.normalize_shortcut_text(other_seq) == seq_text:
                ok = self.ask_disable_conflict(
                    parent,
                    "개별 프리셋 단축키 비활성화 확인",
                    f"'{name}' 개별 글꼴 프리셋이 같은 단축키를 사용 중입니다.\n\n"
                    f"기존 개별 프리셋을 비활성화하고 '{owner_name}'에 지정할까요?",
                )
                if not ok:
                    return False
                preset["enabled"] = False
                self.save_item_text_preset_named(name, preset)

        ShortcutSettingsStore.save(self.shortcut_settings)
        return True

    def set_item_text_preset_shortcut_checked(self, name, seq_text, parent=None):
        preset = self.item_text_presets.get(name)
        if not preset:
            return False
        new_text = self.normalize_shortcut_text(seq_text)
        old_text = self.normalize_shortcut_text(preset.get("shortcut", "") or "")
        if new_text == old_text:
            return True
        if new_text and not self.resolve_conflicts_for_item_preset_shortcut(name, new_text, parent=parent):
            return False
        preset["shortcut"] = new_text
        self.save_item_text_preset_named(name, preset)
        self.refresh_item_text_preset_combo()
        self.apply_shortcuts()
        return True

    def set_item_text_preset_enabled_checked(self, name, enabled, parent=None):
        preset = self.item_text_presets.get(name)
        if not preset:
            return False
        if enabled:
            seq_text = self.normalize_shortcut_text(preset.get("shortcut", "") or "")
            if seq_text and not self.resolve_conflicts_for_item_preset_shortcut(name, seq_text, parent=parent):
                return False
        preset["enabled"] = bool(enabled)
        self.save_item_text_preset_named(name, preset)
        self.refresh_item_text_preset_combo()
        self.apply_shortcuts()
        return True

    def resolve_item_preset_conflicts_for_new_shortcut_settings(self, new_settings, parent=None, source_label="단축키"):
        """일반 단축키/매크로 설정 저장 시, 개별 프리셋과 겹치면 개별 프리셋을 비활성화한다."""
        changed = False
        for name, preset in list(getattr(self, "item_text_presets", {}).items()):
            if not preset.get("enabled", True):
                continue
            item_seq = self.normalize_shortcut_text(preset.get("shortcut", "") or "")
            if not item_seq:
                continue

            # 일반 단축키 충돌
            for key, shortcut in list(new_settings.shortcuts.items()):
                if not new_settings.enabled.get(key, True):
                    continue
                if shortcut and self.normalize_shortcut_text(shortcut) == item_seq:
                    label = self.standard_shortcut_label(key)
                    ok = self.ask_disable_conflict(
                        parent,
                        "개별 프리셋 단축키 비활성화 확인",
                        f"'{name}' 개별 글꼴 프리셋이 '{label}' 기능과 같은 단축키를 사용 중입니다.\n\n"
                        f"개별 글꼴 프리셋을 비활성화하고 {source_label} 설정을 저장할까요?",
                    )
                    if not ok:
                        return False
                    preset["enabled"] = False
                    self.save_item_text_preset_named(name, preset)
                    changed = True
                    break

            if not preset.get("enabled", True):
                continue

            # 매크로 충돌
            for macro in getattr(new_settings, "macros", []) or []:
                if not macro.get("enabled", True):
                    continue
                macro_seq = str(macro.get("shortcut", "") or "")
                if macro_seq and self.normalize_shortcut_text(macro_seq) == item_seq:
                    macro_name = str(macro.get("name", "매크로"))
                    ok = self.ask_disable_conflict(
                        parent,
                        "개별 프리셋 단축키 비활성화 확인",
                        f"'{name}' 개별 글꼴 프리셋이 '{macro_name}' 매크로와 같은 단축키를 사용 중입니다.\n\n"
                        f"개별 글꼴 프리셋을 비활성화하고 {source_label} 설정을 저장할까요?",
                    )
                    if not ok:
                        return False
                    preset["enabled"] = False
                    self.save_item_text_preset_named(name, preset)
                    changed = True
                    break

        if changed:
            self.refresh_item_text_preset_combo()
        return True

    def apply_pending_item_preset_disables_for_shortcut_settings(self, pending_names, new_settings):
        """단축키/매크로 설정창에서 입력 중 허용한 개별 프리셋 충돌을 OK 저장 시점에 적용한다.

        사용자가 중간에 단축키를 다시 바꿨을 수 있으므로, 최종 new_settings와 실제로
        아직 충돌하는 경우에만 해당 개별 프리셋을 비활성화한다.
        """
        changed = False
        for name in sorted({str(x) for x in (pending_names or []) if str(x)}):
            preset = self.item_text_presets.get(name)
            if not preset or not preset.get("enabled", True):
                continue
            item_seq = self.normalize_shortcut_text(preset.get("shortcut", "") or "")
            if not item_seq:
                continue

            conflict = False
            for key, shortcut in list(getattr(new_settings, "shortcuts", {}) .items()):
                if not getattr(new_settings, "enabled", {}).get(key, True):
                    continue
                if shortcut and self.normalize_shortcut_text(shortcut) == item_seq:
                    conflict = True
                    break
            if not conflict:
                for macro in getattr(new_settings, "macros", []) or []:
                    if not macro.get("enabled", True):
                        continue
                    macro_seq = self.normalize_shortcut_text(macro.get("shortcut", "") or "")
                    if macro_seq and macro_seq == item_seq:
                        conflict = True
                        break

            if conflict:
                preset["enabled"] = False
                self.save_item_text_preset_named(name, preset)
                changed = True
                self.log(f"🔕 개별 글꼴 프리셋 단축키 비활성화: {name}")

        if changed:
            self.refresh_item_text_preset_combo()
            self.apply_shortcuts()
        return changed

    def load_item_text_preset_cache(self):
        self.item_text_presets = {}
        preset_dir = self.item_text_preset_dir()
        for path in sorted(preset_dir.glob("*.json")):
            if path.name.startswith("_"):
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and "style" in raw:
                    style = self.normalize_style_dict(raw.get("style"))
                    include = raw.get("include") or {}
                    include = {k: bool(include.get(k, False)) for k, _ in self.style_field_specs()}
                    # 예전 파일/비어있는 파일은 전부 포함으로 보정
                    if not any(include.values()):
                        include = {k: True for k, _ in self.style_field_specs()}
                    preset = {
                        "style": style,
                        "include": include,
                        "enabled": bool(raw.get("enabled", True)),
                        "shortcut": str(raw.get("shortcut", "") or ""),
                    }
                else:
                    preset = {
                        "style": self.normalize_style_dict(raw),
                        "include": {k: True for k, _ in self.style_field_specs()},
                        "enabled": True,
                        "shortcut": "",
                    }
                self.item_text_presets[path.stem] = preset
            except Exception:
                continue

        self.refresh_item_text_preset_combo()
        # 단축키 액션 갱신
        if hasattr(self, "actions"):
            self.apply_shortcuts()

    def save_item_text_preset_named(self, name, preset):
        safe = self.safe_preset_name(name)
        path = self.item_text_preset_path(safe)
        payload = {
            "style": self.normalize_style_dict(preset.get("style")),
            "include": {k: bool((preset.get("include") or {}).get(k, False)) for k, _ in self.style_field_specs()},
            "enabled": bool(preset.get("enabled", True)),
            "shortcut": str(preset.get("shortcut", "") or ""),
        }
        with open(path, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        self.item_text_presets[safe] = payload
        return safe

    def refresh_item_text_preset_combo(self, select_key="__custom__"):
        if not hasattr(self, "cb_item_text_preset"):
            return
        self._item_preset_loading = True
        self.cb_item_text_preset.blockSignals(True)
        try:
            self.cb_item_text_preset.clear()
            self.cb_item_text_preset.addItem("사용자지정", "__custom__")
            for name, preset in sorted(self.item_text_presets.items()):
                if preset.get("enabled", True):
                    self.cb_item_text_preset.addItem(name, name)
            idx = self.cb_item_text_preset.findData(select_key)
            self.cb_item_text_preset.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self.cb_item_text_preset.blockSignals(False)
            self._item_preset_loading = False

    def set_item_preset_combo_custom(self):
        if not hasattr(self, "cb_item_text_preset") or self._item_preset_loading:
            return
        self.cb_item_text_preset.blockSignals(True)
        try:
            self.cb_item_text_preset.setCurrentIndex(0)
        finally:
            self.cb_item_text_preset.blockSignals(False)

    def set_item_preset_combo_mixed(self):
        if not hasattr(self, "cb_item_text_preset") or self._item_preset_loading:
            return
        self.cb_item_text_preset.blockSignals(True)
        try:
            idx = self.cb_item_text_preset.findData("__mixed__")
            if idx < 0:
                self.cb_item_text_preset.insertItem(1, "다수의 프리셋", "__mixed__")
                idx = 1
            self.cb_item_text_preset.setCurrentIndex(idx)
        finally:
            self.cb_item_text_preset.blockSignals(False)

    def update_item_preset_combo_for_selected_texts(self):
        """최종화면 텍스트 선택 상태에 따라 개별 프리셋 콤보 표시를 맞춘다."""
        if not hasattr(self, "cb_item_text_preset") or self._item_preset_loading:
            return

        items = self.selected_text_items()
        if not items:
            self.set_item_preset_combo_custom()
            return

        names = []
        for item in items:
            name = str(item.data.get("item_text_preset_name") or "").strip()
            if not name or name not in getattr(self, "item_text_presets", {}):
                name = "__custom__"
            names.append(name)

        uniq = sorted(set(names))
        if len(uniq) > 1:
            self.set_item_preset_combo_mixed()
            return

        key = uniq[0] if uniq else "__custom__"
        self.cb_item_text_preset.blockSignals(True)
        try:
            mix_idx = self.cb_item_text_preset.findData("__mixed__")
            if mix_idx >= 0:
                self.cb_item_text_preset.removeItem(mix_idx)

            idx = self.cb_item_text_preset.findData(key)
            self.cb_item_text_preset.setCurrentIndex(idx if idx >= 0 else 0)
        finally:
            self.cb_item_text_preset.blockSignals(False)

    def on_item_text_preset_selected(self, *args):
        if self._item_preset_loading or self._item_preset_signal_lock:
            return
        key = self.cb_item_text_preset.currentData() if hasattr(self, "cb_item_text_preset") else "__custom__"
        if not key or key in ("__custom__", "__mixed__"):
            return
        self.apply_item_text_preset_by_name(str(key), from_combo=True)

    def item_preset_style_subset(self, preset):
        style = self.normalize_style_dict(preset.get("style"))
        include = preset.get("include") or {}
        subset = {}
        for key, _label in self.style_field_specs():
            if include.get(key, False):
                subset[key] = style.get(key)
        return subset

    def apply_item_text_preset_by_name(self, name, from_combo=False, record_undo=True):
        name = str(name or "")
        preset = self.item_text_presets.get(name)
        if not preset:
            self.log(f"⚠️ 개별 글꼴 프리셋을 찾지 못했습니다: {name}")
            return False
        if not preset.get("enabled", True):
            self.log(f"⚠️ 비활성화된 개별 글꼴 프리셋입니다: {name}")
            return False
        subset = self.item_preset_style_subset(preset)
        if not subset:
            self.log(f"⚠️ 적용할 옵션이 없는 개별 글꼴 프리셋입니다: {name}")
            return False

        selected = self.selected_text_items()
        if selected and self.cb_mode.currentIndex() == 4:
            self.apply_style_to_selected(preset_name=name, record_undo=record_undo, **subset)
            if from_combo and hasattr(self, "cb_item_text_preset"):
                self._item_preset_signal_lock = True
                try:
                    idx = self.cb_item_text_preset.findData(name)
                    if idx >= 0:
                        self.cb_item_text_preset.setCurrentIndex(idx)
                finally:
                    self._item_preset_signal_lock = False
            self.log(f"🎛️ 개별 글꼴 프리셋 적용: {name}")
            # 글꼴 프리셋은 Undo 경계가 아니라 일반 Undo 스택에 포함한다.
            return True

        self.log("⚠️ 개별 글꼴 프리셋을 적용할 텍스트를 최종화면에서 선택하세요.")
        self.set_item_preset_combo_custom()
        return False

    def selected_scene_text_ids(self):
        ids = [item.data.get('id') for item in self.selected_text_items() if item.data.get('id') is not None]
        for tid in self.selected_table_text_ids():
            if tid is not None and tid not in ids:
                ids.append(tid)
        return ids

    def restore_text_items_by_snapshot(self, page_idx, snapshot_by_id):
        curr = self.data.get(page_idx)
        if not curr or not snapshot_by_id:
            return
        for i, d in enumerate(curr.get('data', [])):
            key = str(d.get('id'))
            if key in snapshot_by_id:
                curr['data'][i] = copy.deepcopy(snapshot_by_id[key])

    def open_text_preset_dialog(self):
        """페이지 글꼴 프리셋 관리.

        확인은 페이지 적용이 아니라 '마지막 설정' 저장 전용이다.
        실제 반영은 현재 페이지에 적용 / 전체 페이지에 적용 버튼에서만 수행한다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui("페이지 글꼴 프리셋 관리"))
        dialog.resize(1040, 620)
        dialog.setStyleSheet(self.settings_dialog_style())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info = QLabel(f"{self.tr_ui("저장 위치")}: {self.text_preset_dir()}")
        info.setWordWrap(True)
        layout.addWidget(info)

        original_idx = self.idx
        original_page_snapshot = copy.deepcopy(self.data.get(self.idx)) if self.idx in self.data else None
        original_style_snapshot = self.current_style_snapshot()
        original_active_key = self.cb_text_preset.currentData() if hasattr(self, "cb_text_preset") else "__last__"
        dialog_state = {"applied": False, "restored": False}
        dialog_lock = {"value": False}
        selected_name = {"value": None}

        dialog_text_color = {"value": original_style_snapshot.get("text_color", "#000000")}
        dialog_stroke_color = {"value": original_style_snapshot.get("stroke_color", "#FFFFFF")}
        dialog_align = {"value": original_style_snapshot.get("align", "center")}

        # ---------- style editor ----------
        editor = QWidget(dialog)
        editor_l = QVBoxLayout(editor)
        editor_l.setContentsMargins(0, 0, 0, 0)
        editor_l.setSpacing(6)

        row1 = QHBoxLayout()
        row1.setSpacing(6)
        dlg_font = QFontComboBox(dialog); dlg_font.setFixedWidth(160); dlg_font.setFixedHeight(26)
        dlg_size = QSpinBox(dialog); dlg_size.setRange(5, 500); dlg_size.setSuffix(" px"); dlg_size.setFixedWidth(82); dlg_size.setFixedHeight(26)
        dlg_stroke = QSpinBox(dialog); dlg_stroke.setRange(0, 100); dlg_stroke.setSuffix(" px"); dlg_stroke.setFixedWidth(78); dlg_stroke.setFixedHeight(26)
        dlg_text_color_btn = QPushButton("", dialog); dlg_text_color_btn.setFixedSize(26, 26)
        dlg_stroke_color_btn = QPushButton("", dialog); dlg_stroke_color_btn.setFixedSize(26, 26)
        dlg_align_left = QPushButton("≡◁", dialog); dlg_align_center = QPushButton("≡◇", dialog); dlg_align_right = QPushButton("▷≡", dialog)
        for b in (dlg_align_left, dlg_align_center, dlg_align_right):
            b.setFixedWidth(42); b.setFixedHeight(26)
        row1.addWidget(QLabel(self.tr_ui("폰트"))); row1.addWidget(dlg_font)
        row1.addWidget(QLabel(self.tr_ui("크기"))); row1.addWidget(dlg_size)
        row1.addWidget(dlg_text_color_btn)
        row1.addWidget(QLabel(self.tr_ui("획"))); row1.addWidget(dlg_stroke); row1.addWidget(dlg_stroke_color_btn)
        row1.addWidget(dlg_align_left); row1.addWidget(dlg_align_center); row1.addWidget(dlg_align_right)
        row1.addStretch()
        editor_l.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        dlg_line_spacing = QSpinBox(dialog); dlg_line_spacing.setRange(50, 300); dlg_line_spacing.setValue(100); dlg_line_spacing.setSuffix(" %"); dlg_line_spacing.setFixedWidth(86); dlg_line_spacing.setFixedHeight(26)
        dlg_letter_spacing = QSpinBox(dialog); dlg_letter_spacing.setRange(-100, 200); dlg_letter_spacing.setSuffix(" px"); dlg_letter_spacing.setFixedWidth(86); dlg_letter_spacing.setFixedHeight(26)
        dlg_char_width = QSpinBox(dialog); dlg_char_width.setRange(10, 300); dlg_char_width.setValue(100); dlg_char_width.setSuffix(" %"); dlg_char_width.setFixedWidth(86); dlg_char_width.setFixedHeight(26)
        dlg_char_height = QSpinBox(dialog); dlg_char_height.setRange(10, 300); dlg_char_height.setValue(100); dlg_char_height.setSuffix(" %"); dlg_char_height.setFixedWidth(86); dlg_char_height.setFixedHeight(26)
        dlg_bold = QPushButton("B", dialog); dlg_italic = QPushButton("I", dialog); dlg_strike = QPushButton("S", dialog)
        for b, tip in ((dlg_bold, "굵게"), (dlg_italic, "기울이기"), (dlg_strike, "취소선")):
            b.setCheckable(True); b.setFixedWidth(32); b.setFixedHeight(26); b.setToolTip(tip)
        dlg_bold.setStyleSheet("font-weight:bold;"); dlg_italic.setStyleSheet("font-style:italic;"); dlg_strike.setStyleSheet("text-decoration: line-through;")
        self.install_style_editor_shortcuts(dialog, {
            "font": dlg_font,
            "size": dlg_size,
            "stroke": dlg_stroke,
            "line_spacing": dlg_line_spacing,
            "letter_spacing": dlg_letter_spacing,
            "char_width": dlg_char_width,
            "char_height": dlg_char_height,
            "bold": dlg_bold,
            "italic": dlg_italic,
            "strike": dlg_strike,
        })
        row2.addWidget(QLabel(self.tr_ui("행간"))); row2.addWidget(dlg_line_spacing)
        row2.addWidget(QLabel(self.tr_ui("자간"))); row2.addWidget(dlg_letter_spacing)
        row2.addWidget(QLabel(self.tr_ui("너비"))); row2.addWidget(dlg_char_width)
        row2.addWidget(QLabel(self.tr_ui("높이"))); row2.addWidget(dlg_char_height)
        row2.addWidget(dlg_bold); row2.addWidget(dlg_italic); row2.addWidget(dlg_strike)
        row2.addStretch()
        editor_l.addLayout(row2)
        layout.addWidget(editor)

        def refresh_color_buttons():
            dlg_text_color_btn.setStyleSheet(f"background:{dialog_text_color['value']}; border:1px solid #444; padding:0px;")
            dlg_stroke_color_btn.setStyleSheet(f"background:{dialog_stroke_color['value']}; border:1px solid #444; padding:0px;")
            for align, btn in (("left", dlg_align_left), ("center", dlg_align_center), ("right", dlg_align_right)):
                btn.setStyleSheet("background:#dbeafe; border:1px solid #8fb4e8; border-radius:0px;" if dialog_align["value"] == align else "")

        def dialog_style_snapshot():
            return self.normalize_style_dict({
                "font_family": dlg_font.currentFont().family(),
                "font_size": int(dlg_size.value()),
                "stroke_width": int(dlg_stroke.value()),
                "text_color": dialog_text_color["value"],
                "stroke_color": dialog_stroke_color["value"],
                "align": dialog_align["value"],
                "line_spacing": int(dlg_line_spacing.value()),
                "letter_spacing": int(dlg_letter_spacing.value()),
                "char_width": int(dlg_char_width.value()),
                "char_height": int(dlg_char_height.value()),
                "bold": bool(dlg_bold.isChecked()),
                "italic": bool(dlg_italic.isChecked()),
                "strike": bool(dlg_strike.isChecked()),
            })

        def apply_style_to_dialog(style):
            style = self.normalize_style_dict(style)
            dialog_lock["value"] = True
            try:
                dlg_font.setCurrentFont(QFont(style["font_family"]))
                dlg_size.setValue(int(style["font_size"]))
                dlg_stroke.setValue(int(style["stroke_width"]))
                dialog_text_color["value"] = style["text_color"]
                dialog_stroke_color["value"] = style["stroke_color"]
                dialog_align["value"] = style["align"]
                dlg_line_spacing.setValue(100 if int(style["line_spacing"] or 0) == 0 else int(style["line_spacing"]))
                dlg_letter_spacing.setValue(int(style["letter_spacing"]))
                dlg_char_width.setValue(int(style["char_width"]))
                dlg_char_height.setValue(int(style["char_height"]))
                dlg_bold.setChecked(bool(style["bold"]))
                dlg_italic.setChecked(bool(style["italic"]))
                dlg_strike.setChecked(bool(style["strike"]))
                refresh_color_buttons()
            finally:
                dialog_lock["value"] = False

        # ---------- preset list ----------
        rows_widget = QWidget(dialog)
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setContentsMargins(0, 0, 0, 0)
        rows_layout.setSpacing(4)
        scroll = QScrollArea(dialog); scroll.setWidgetResizable(True); scroll.setWidget(rows_widget); scroll.setMinimumHeight(300)
        layout.addWidget(scroll, 1)

        def load_page_presets():
            presets = {}
            for path in sorted(self.text_preset_dir().glob("*.json")):
                if path.name.startswith("_"):
                    continue
                try:
                    with open(path, "r", encoding="utf-8") as f:
                        presets[path.stem] = self.normalize_style_dict(json.load(f))
                except Exception:
                    continue
            return presets

        def preview_style_on_current_page(style):
            if original_page_snapshot is None or original_idx not in self.data:
                self.apply_style_to_controls(style)
                return
            self.data[original_idx] = copy.deepcopy(original_page_snapshot)
            style = self.normalize_style_dict(style)
            self.apply_style_to_controls(style)
            curr = self.data.get(original_idx)
            targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
            self.apply_style_dict_to_data_items(targets, style)
            if self.idx == original_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)

        def refresh_rows(select_name=None):
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            header = QWidget(rows_widget)
            h = QHBoxLayout(header); h.setContentsMargins(6, 2, 6, 2)
            h.addWidget(QLabel("사용"), 0)
            h.addWidget(QLabel("선택"), 0)
            h.addWidget(QLabel("이름"), 1)
            h.addWidget(QLabel("내용"), 3)
            h.addWidget(QLabel("관리"), 1)
            rows_layout.addWidget(header)

            presets = load_page_presets()
            state = self.page_preset_state()
            enabled_map = state.get("enabled", {})
            for name, style in presets.items():
                row = QWidget(rows_widget)
                row_l = QHBoxLayout(row); row_l.setContentsMargins(6, 2, 6, 2); row_l.setSpacing(6)
                chk = QCheckBox(); chk.setChecked(bool(enabled_map.get(name, True)))
                btn_select = QPushButton("선택")
                name_edit = QLineEdit(name)
                try:
                    if not hasattr(dialog, "_ysb_enter_commit_filter"):
                        dialog._ysb_enter_commit_filter = EnterCommitFilter(parent_dialog=dialog, fallback_widget=dialog, parent=dialog)
                    name_edit.installEventFilter(dialog._ysb_enter_commit_filter)
                except Exception:
                    pass
                summary = QLabel(self.style_summary_text(style)); summary.setWordWrap(True)
                btn_update = QPushButton("수정 저장")
                btn_delete = QPushButton("삭제")

                if not chk.isChecked():
                    if self.is_light_theme():
                        row.setStyleSheet("background:#f1f3f6; color:#8a8f99;")
                        summary.setStyleSheet("color:#8a8f99;")
                        name_edit.setStyleSheet("background:#f7f8fa; color:#8a8f99; border:1px solid #d0d5df;")
                    else:
                        row.setStyleSheet("background:#242424; color:#888888;")
                        summary.setStyleSheet("color:#888888;")
                        name_edit.setStyleSheet("color:#888888;")
                is_selected = (selected_name["value"] == name or select_name == name)
                if is_selected:
                    if self.is_light_theme():
                        row_style = "background:#e8f1ff; border:1px solid #6fa8ff;"
                        child_style = "background:#ffffff; color:#202124; border:1px solid #6fa8ff;"
                    else:
                        row_style = "background:#31415c; border:1px solid #5b8def;"
                        child_style = "background:#2f5fa7; color:white; border:1px solid #80b4ff;"
                    row.setStyleSheet(row_style)
                    btn_select.setText("선택됨")
                    btn_select.setStyleSheet("background:#4b79c7; color:white; font-weight:bold; border:1px solid #9cc3ff;")
                    name_edit.setStyleSheet(child_style)
                    summary.setStyleSheet(child_style)
                    btn_update.setStyleSheet("background:#3d5f92; color:white;")
                    btn_delete.setStyleSheet("background:#3d5f92; color:white;")
                    selected_name["value"] = name

                row_l.addWidget(chk)
                row_l.addWidget(btn_select)
                row_l.addWidget(name_edit, 1)
                row_l.addWidget(summary, 3)
                row_l.addWidget(btn_update)
                row_l.addWidget(btn_delete)
                rows_layout.addWidget(row)

                def on_enabled(v, n=name):
                    st = self.page_preset_state()
                    st.setdefault("enabled", {})[n] = bool(v)
                    self.save_page_preset_state(st)
                    self.load_text_preset_cache()
                    self.log(f"🔘 페이지 글꼴 프리셋 {'사용' if v else '미사용'}: {n}")
                    refresh_rows(selected_name["value"])

                def on_select(_checked=False, n=name):
                    # 이미 선택된 프리셋을 다시 누르면 선택 해제한다.
                    if selected_name["value"] == n:
                        selected_name["value"] = None
                        if original_page_snapshot is not None and original_idx in self.data:
                            self.data[original_idx] = copy.deepcopy(original_page_snapshot)
                            if self.idx == original_idx:
                                self.ref_tab()
                                if self.cb_mode.currentIndex() == 4:
                                    self.mode_chg(4)
                        refresh_rows(None)
                        self.log(f"↩️ 페이지 글꼴 프리셋 선택 해제: {n}")
                        return

                    presets_now = load_page_presets()
                    style_now = presets_now.get(n)
                    if not style_now:
                        return
                    selected_name["value"] = n
                    apply_style_to_dialog(style_now)
                    preview_style_on_current_page(style_now)
                    refresh_rows(n)
                    self.log(f"🎛️ 페이지 글꼴 프리셋 선택: {n}")

                def on_name_finished(edit=name_edit, old_name=name):
                    new_name = self.safe_preset_name(edit.text())
                    if not new_name or new_name == old_name:
                        edit.setText(old_name); return
                    old_path = self.text_preset_path(old_name)
                    new_path = self.text_preset_path(new_name)
                    if new_path.exists():
                        QMessageBox.warning(dialog, self.tr_ui("이름 변경 실패"), self.tr_ui("같은 이름의 프리셋이 이미 있습니다."))
                        edit.setText(old_name); return
                    if old_path.exists():
                        old_path.rename(new_path)
                    st = self.page_preset_state()
                    enabled = st.setdefault("enabled", {})
                    if old_name in enabled:
                        enabled[new_name] = enabled.pop(old_name)
                    if st.get("active") == old_name:
                        st["active"] = new_name
                    self.save_page_preset_state(st)
                    if selected_name["value"] == old_name:
                        selected_name["value"] = new_name
                    refresh_rows(new_name)

                def on_update(_checked=False, n=name, label=summary):
                    style_now = dialog_style_snapshot()
                    with open(self.text_preset_path(n), "w", encoding="utf-8") as f:
                        json.dump(style_now, f, ensure_ascii=False, indent=2)
                    selected_name["value"] = n
                    label.setText(self.style_summary_text(style_now))
                    refresh_rows(n)
                    self.log(f"💾 페이지 글꼴 프리셋 수정 저장: {n}")

                def on_delete(_checked=False, n=name):
                    ans = QMessageBox.question(dialog, self.tr_ui("프리셋 삭제"), self.tr_msg(f"'{n}' 프리셋을 삭제할까요?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                    if ans != QMessageBox.StandardButton.Yes:
                        return
                    try:
                        self.text_preset_path(n).unlink(missing_ok=True)
                    except Exception:
                        pass
                    st = self.page_preset_state()
                    st.setdefault("enabled", {}).pop(n, None)
                    if st.get("active") == n:
                        st["active"] = "__last__"
                    self.save_page_preset_state(st)
                    if selected_name["value"] == n:
                        selected_name["value"] = None
                    refresh_rows()
                    self.log(f"🗑️ 페이지 글꼴 프리셋 삭제: {n}")

                chk.toggled.connect(on_enabled)
                btn_select.clicked.connect(on_select)
                name_edit.editingFinished.connect(on_name_finished)
                btn_update.clicked.connect(on_update)
                btn_delete.clicked.connect(on_delete)

            rows_layout.addStretch()

        def restore_full_original_state():
            if original_page_snapshot is not None and original_idx in self.data:
                self.data[original_idx] = copy.deepcopy(original_page_snapshot)
            self.apply_style_to_controls(original_style_snapshot)
            self.load_text_preset_cache()
            if self.idx == original_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
            dialog_state["restored"] = True

        def on_dialog_style_changed(*args):
            if dialog_lock["value"]:
                return
            refresh_color_buttons()
            preview_style_on_current_page(dialog_style_snapshot())

        def pick_dialog_color(target):
            current = dialog_text_color["value"] if target == "text" else dialog_stroke_color["value"]
            color = QColorDialog.getColor(QColor(current), self, "색상 선택")
            if not color.isValid():
                return
            if target == "text":
                dialog_text_color["value"] = color.name(QColor.NameFormat.HexRgb).upper()
            else:
                dialog_stroke_color["value"] = color.name(QColor.NameFormat.HexRgb).upper()
            on_dialog_style_changed()

        def set_dialog_align(align):
            dialog_align["value"] = align
            on_dialog_style_changed()

        for widget in (dlg_font, dlg_size, dlg_stroke, dlg_line_spacing, dlg_letter_spacing, dlg_char_width, dlg_char_height):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(on_dialog_style_changed)
        dlg_font.currentFontChanged.connect(on_dialog_style_changed)
        dlg_bold.toggled.connect(on_dialog_style_changed)
        dlg_italic.toggled.connect(on_dialog_style_changed)
        dlg_strike.toggled.connect(on_dialog_style_changed)
        dlg_text_color_btn.clicked.connect(lambda: pick_dialog_color("text"))
        dlg_stroke_color_btn.clicked.connect(lambda: pick_dialog_color("stroke"))
        dlg_align_left.clicked.connect(lambda: set_dialog_align("left"))
        dlg_align_center.clicked.connect(lambda: set_dialog_align("center"))
        dlg_align_right.clicked.connect(lambda: set_dialog_align("right"))

        btn_line = QHBoxLayout()
        btn_add = QPushButton(self.tr_ui("현재 스타일을 새 프리셋으로 추가"), dialog)
        btn_import = QPushButton(self.tr_ui("불러오기"), dialog)
        btn_apply_page = QPushButton(self.tr_ui("현재 페이지에 적용"), dialog)
        btn_apply_all = QPushButton(self.tr_ui("전체 페이지에 적용"), dialog)
        btn_ok = QPushButton(self.tr_ui("확인"), dialog)
        btn_close = QPushButton(self.tr_ui("닫기"), dialog)
        btn_line.addWidget(btn_add)
        btn_line.addWidget(btn_import)
        btn_line.addStretch()
        btn_line.addWidget(btn_apply_page)
        btn_line.addWidget(btn_apply_all)
        btn_line.addWidget(btn_ok)
        btn_line.addWidget(btn_close)
        layout.addLayout(btn_line)

        def add_current_as_preset():
            name, ok = QInputDialog.getText(dialog, self.tr_ui("페이지 프리셋 추가"), self.tr_ui("프리셋 이름:"))
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            if self.text_preset_path(safe).exists():
                ans = QMessageBox.question(dialog, self.tr_ui("덮어쓰기"), self.tr_msg(f"'{safe}' 프리셋이 이미 있습니다. 덮어쓸까요?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if ans != QMessageBox.StandardButton.Yes:
                    return
            with open(self.text_preset_path(safe), "w", encoding="utf-8") as f:
                json.dump(dialog_style_snapshot(), f, ensure_ascii=False, indent=2)
            st = self.page_preset_state()
            st.setdefault("enabled", {})[safe] = True
            self.save_page_preset_state(st)
            # 새로 추가는 목록에만 추가한다. 파란 선택 강조는 남기지 않는다.
            selected_name["value"] = None
            refresh_rows(None)
            self.log(f"💾 페이지 글꼴 프리셋 추가: {safe}")

        def import_page_preset():
            path, _ = QFileDialog.getOpenFileName(dialog, self.tr_ui("페이지 글꼴 프리셋 불러오기"), str(self.text_preset_dir()), "JSON (*.json)")
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)
                style = self.normalize_style_dict(raw.get("style") if isinstance(raw, dict) and "style" in raw else raw)
            except Exception as e:
                QMessageBox.warning(dialog, self.tr_ui("불러오기 실패"), f"{self.tr_ui("프리셋 JSON을 읽지 못했습니다.")}\n{e}")
                return
            default_name = Path(path).stem
            name, ok = QInputDialog.getText(dialog, self.tr_ui("프리셋 이름"), self.tr_ui("추가할 프리셋 이름:"), text=default_name)
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            with open(self.text_preset_path(safe), "w", encoding="utf-8") as f:
                json.dump(style, f, ensure_ascii=False, indent=2)
            # 불러오기는 프리셋 목록에 추가만 한다. 파란 선택 행은 남기지 않는다.
            selected_name["value"] = None
            apply_style_to_dialog(style)
            preview_style_on_current_page(style)
            refresh_rows(None)
            self.log(f"📥 페이지 글꼴 프리셋 불러오기 완료: {safe}")

        def commit_dialog_style(active_key=None):
            active_key = active_key or selected_name["value"] or "__last__"
            self.apply_style_to_controls(dialog_style_snapshot())
            self.save_last_text_preset(active_key)
            self.load_text_preset_cache()
            return dialog_style_snapshot()

        def apply_to_current_page_and_close():
            commit_dialog_style()
            if self.idx in self.data:
                self.apply_current_preset_to_page(self.idx, refresh=True)
                self.auto_save_project()
            else:
                self.log("⚠️ 현재 페이지가 없어 프리셋은 저장만 하고 페이지 적용은 생략합니다.")
            dialog_state["applied"] = True
            dialog.accept()

        def apply_to_all_pages_and_close():
            commit_dialog_style()
            if any(bool(self.data.get(i)) for i in range(len(self.paths))):
                self.apply_current_preset_to_all_pages()
                self.auto_save_project()
            else:
                self.log("⚠️ 전체 페이지 데이터가 없어 프리셋은 저장만 하고 전체 적용은 생략합니다.")
            dialog_state["applied"] = True
            dialog.accept()

        def confirm_save_last_only():
            # 확인은 페이지 적용이 아니다. 미리보기로 바뀐 현재 페이지 데이터를 먼저 원복한 뒤,
            # 상단에서 만진 "마지막 설정값"만 저장한다.
            if original_page_snapshot is not None and original_idx in self.data:
                self.data[original_idx] = copy.deepcopy(original_page_snapshot)
            commit_dialog_style()
            if self.idx == original_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
            dialog_state["restored"] = True
            self.log("💾 페이지 글꼴 프리셋 마지막 설정 저장 완료")
            dialog.accept()

        btn_add.clicked.connect(add_current_as_preset)
        btn_import.clicked.connect(import_page_preset)
        btn_apply_page.clicked.connect(apply_to_current_page_and_close)
        btn_apply_all.clicked.connect(apply_to_all_pages_and_close)
        btn_ok.clicked.connect(confirm_save_last_only)
        btn_close.clicked.connect(dialog.reject)

        apply_style_to_dialog(original_style_snapshot)
        refresh_color_buttons()
        refresh_rows(selected_name["value"])

        result = dialog.exec()
        if not dialog_state["applied"] and not dialog_state["restored"]:
            restore_full_original_state()

    def open_item_text_preset_dialog(self):
        """선택 텍스트에만 적용하는 개별 글꼴 프리셋 관리.

        이 창의 실시간 변경은 선택 텍스트에만 임시 미리보기로 보이고,
        확인/닫기로 나가면 실제 텍스트에는 적용하지 않는다.
        실제 적용은 우측 콤보 선택 또는 프리셋 단축키로만 한다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle(self.tr_ui("개별 글꼴 프리셋 관리"))
        dialog.resize(1120, 680)
        dialog.setStyleSheet(self.settings_dialog_style())

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info = QLabel(f"{self.tr_ui("저장 위치")}: {self.item_text_preset_dir()}\n{self.tr_msg("체크한 옵션만 프리셋에 포함됩니다. 이 창의 미리보기는 닫을 때 원래대로 복구됩니다.")}")
        info.setWordWrap(True)
        layout.addWidget(info)

        page_idx = self.idx
        original_page_snapshot = copy.deepcopy(self.data.get(page_idx)) if page_idx in self.data else None
        selected_ids = self.selected_scene_text_ids()
        curr = self.data.get(page_idx)
        selected_snapshot = {}
        if curr and selected_ids:
            idset = {str(x) for x in selected_ids}
            for d in curr.get('data', []):
                if str(d.get('id')) in idset:
                    selected_snapshot[str(d.get('id'))] = copy.deepcopy(d)

        state = self.load_item_text_preset_state()
        base_style = self.normalize_style_dict(state.get("style") or self.current_style_snapshot())
        include_default = state.get("include") or {k: True for k, _ in self.style_field_specs()}

        dialog_lock = {"value": False}
        selected_name = {"value": state.get("selected")}
        dialog_text_color = {"value": base_style["text_color"]}
        dialog_stroke_color = {"value": base_style["stroke_color"]}
        dialog_align = {"value": base_style["align"]}

        # ---------- editor ----------
        top = QWidget(dialog)
        top_l = QVBoxLayout(top); top_l.setContentsMargins(0, 0, 0, 0); top_l.setSpacing(6)

        row1 = QHBoxLayout(); row1.setSpacing(6)
        dlg_font = QFontComboBox(dialog); dlg_font.setFixedWidth(160); dlg_font.setFixedHeight(26)
        dlg_size = QSpinBox(dialog); dlg_size.setRange(5, 500); dlg_size.setSuffix(" px"); dlg_size.setFixedWidth(82); dlg_size.setFixedHeight(26)
        dlg_stroke = QSpinBox(dialog); dlg_stroke.setRange(0, 100); dlg_stroke.setSuffix(" px"); dlg_stroke.setFixedWidth(78); dlg_stroke.setFixedHeight(26)
        dlg_text_color_btn = QPushButton("", dialog); dlg_text_color_btn.setFixedSize(26, 26)
        dlg_stroke_color_btn = QPushButton("", dialog); dlg_stroke_color_btn.setFixedSize(26, 26)
        dlg_align_left = QPushButton("≡◁", dialog); dlg_align_center = QPushButton("≡◇", dialog); dlg_align_right = QPushButton("▷≡", dialog)
        for b in (dlg_align_left, dlg_align_center, dlg_align_right):
            b.setFixedWidth(42); b.setFixedHeight(26)
        row1.addWidget(QLabel(self.tr_ui("폰트"))); row1.addWidget(dlg_font)
        row1.addWidget(QLabel(self.tr_ui("크기"))); row1.addWidget(dlg_size)
        row1.addWidget(dlg_text_color_btn)
        row1.addWidget(QLabel(self.tr_ui("획"))); row1.addWidget(dlg_stroke); row1.addWidget(dlg_stroke_color_btn)
        row1.addWidget(dlg_align_left); row1.addWidget(dlg_align_center); row1.addWidget(dlg_align_right)
        row1.addStretch()
        top_l.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        dlg_line_spacing = QSpinBox(dialog); dlg_line_spacing.setRange(50, 300); dlg_line_spacing.setValue(100); dlg_line_spacing.setSuffix(" %"); dlg_line_spacing.setFixedWidth(86); dlg_line_spacing.setFixedHeight(26)
        dlg_letter_spacing = QSpinBox(dialog); dlg_letter_spacing.setRange(-100, 200); dlg_letter_spacing.setSuffix(" px"); dlg_letter_spacing.setFixedWidth(86); dlg_letter_spacing.setFixedHeight(26)
        dlg_char_width = QSpinBox(dialog); dlg_char_width.setRange(10, 300); dlg_char_width.setValue(100); dlg_char_width.setSuffix(" %"); dlg_char_width.setFixedWidth(86); dlg_char_width.setFixedHeight(26)
        dlg_char_height = QSpinBox(dialog); dlg_char_height.setRange(10, 300); dlg_char_height.setValue(100); dlg_char_height.setSuffix(" %"); dlg_char_height.setFixedWidth(86); dlg_char_height.setFixedHeight(26)
        dlg_bold = QPushButton("B", dialog); dlg_italic = QPushButton("I", dialog); dlg_strike = QPushButton("S", dialog)
        for b, tip in ((dlg_bold, "굵게"), (dlg_italic, "기울이기"), (dlg_strike, "취소선")):
            b.setCheckable(True); b.setFixedWidth(32); b.setFixedHeight(26); b.setToolTip(tip)
        dlg_bold.setStyleSheet("font-weight:bold;"); dlg_italic.setStyleSheet("font-style:italic;"); dlg_strike.setStyleSheet("text-decoration: line-through;")
        self.install_style_editor_shortcuts(dialog, {
            "font": dlg_font,
            "size": dlg_size,
            "stroke": dlg_stroke,
            "line_spacing": dlg_line_spacing,
            "letter_spacing": dlg_letter_spacing,
            "char_width": dlg_char_width,
            "char_height": dlg_char_height,
            "bold": dlg_bold,
            "italic": dlg_italic,
            "strike": dlg_strike,
        })
        row2.addWidget(QLabel(self.tr_ui("행간"))); row2.addWidget(dlg_line_spacing)
        row2.addWidget(QLabel(self.tr_ui("자간"))); row2.addWidget(dlg_letter_spacing)
        row2.addWidget(QLabel(self.tr_ui("너비"))); row2.addWidget(dlg_char_width)
        row2.addWidget(QLabel(self.tr_ui("높이"))); row2.addWidget(dlg_char_height)
        row2.addWidget(dlg_bold); row2.addWidget(dlg_italic); row2.addWidget(dlg_strike)
        row2.addStretch()
        top_l.addLayout(row2)

        include_box = QGroupBox("프리셋에 포함할 옵션", dialog)
        include_l = QGridLayout(include_box)
        include_checks = {}
        for idx, (key, label) in enumerate(self.style_field_specs()):
            chk = QCheckBox(label, include_box)
            chk.setChecked(bool(include_default.get(key, False)))
            include_checks[key] = chk
            include_l.addWidget(chk, idx // 7, idx % 7)
        top_l.addWidget(include_box)
        layout.addWidget(top)

        def current_dialog_style():
            return self.normalize_style_dict({
                "font_family": dlg_font.currentFont().family(),
                "font_size": int(dlg_size.value()),
                "stroke_width": int(dlg_stroke.value()),
                "text_color": dialog_text_color["value"],
                "stroke_color": dialog_stroke_color["value"],
                "align": dialog_align["value"],
                "line_spacing": int(dlg_line_spacing.value()),
                "letter_spacing": int(dlg_letter_spacing.value()),
                "char_width": int(dlg_char_width.value()),
                "char_height": int(dlg_char_height.value()),
                "bold": bool(dlg_bold.isChecked()),
                "italic": bool(dlg_italic.isChecked()),
                "strike": bool(dlg_strike.isChecked()),
            })

        def current_include():
            return {k: chk.isChecked() for k, chk in include_checks.items()}

        def refresh_color_buttons():
            dlg_text_color_btn.setStyleSheet(f"background:{dialog_text_color['value']}; border:1px solid #444; padding:0px;")
            dlg_stroke_color_btn.setStyleSheet(f"background:{dialog_stroke_color['value']}; border:1px solid #444; padding:0px;")
            for align, btn in (("left", dlg_align_left), ("center", dlg_align_center), ("right", dlg_align_right)):
                btn.setStyleSheet("background:#dbeafe; border:1px solid #8fb4e8; border-radius:0px;" if dialog_align["value"] == align else "")

        def apply_style_to_editor(style, include=None):
            st = self.normalize_style_dict(style)
            inc = include if include is not None else current_include()
            dialog_lock["value"] = True
            try:
                dlg_font.setCurrentFont(QFont(st["font_family"]))
                dlg_size.setValue(int(st["font_size"]))
                dlg_stroke.setValue(int(st["stroke_width"]))
                dialog_text_color["value"] = st["text_color"]
                dialog_stroke_color["value"] = st["stroke_color"]
                dialog_align["value"] = st["align"]
                dlg_line_spacing.setValue(100 if int(st["line_spacing"] or 0) == 0 else int(st["line_spacing"]))
                dlg_letter_spacing.setValue(int(st["letter_spacing"]))
                dlg_char_width.setValue(int(st["char_width"]))
                dlg_char_height.setValue(int(st["char_height"]))
                dlg_bold.setChecked(bool(st["bold"]))
                dlg_italic.setChecked(bool(st["italic"]))
                dlg_strike.setChecked(bool(st["strike"]))
                for k, chk in include_checks.items():
                    chk.setChecked(bool(inc.get(k, False)))
                refresh_color_buttons()
            finally:
                dialog_lock["value"] = False

        def preview_selected_only():
            if dialog_lock["value"]:
                return
            if not selected_snapshot:
                refresh_color_buttons()
                return

            # 누적 미리보기/다른 텍스트 오염 방지:
            # 매번 창을 열었을 때의 전체 페이지 원본 상태에서 다시 시작한다.
            if original_page_snapshot is not None and page_idx in self.data:
                self.data[page_idx] = copy.deepcopy(original_page_snapshot)
            else:
                self.restore_text_items_by_snapshot(page_idx, selected_snapshot)

            preset = {"style": current_dialog_style(), "include": current_include()}
            subset = self.item_preset_style_subset(preset)
            if subset:
                curr_now = self.data.get(page_idx)
                if curr_now:
                    idset = set(selected_snapshot.keys())
                    for d in curr_now.get('data', []):
                        if str(d.get('id')) in idset:
                            for k, v in subset.items():
                                d[k] = v
            if self.idx == page_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
                    self.reselect_text_items([int(x) for x in selected_snapshot.keys() if str(x).isdigit()])
            refresh_color_buttons()

        def pick_color(target):
            current = dialog_text_color["value"] if target == "text" else dialog_stroke_color["value"]
            color = QColorDialog.getColor(QColor(current), self, "색상 선택")
            if not color.isValid():
                return
            if target == "text":
                dialog_text_color["value"] = color.name(QColor.NameFormat.HexRgb).upper()
            else:
                dialog_stroke_color["value"] = color.name(QColor.NameFormat.HexRgb).upper()
            preview_selected_only()

        def set_align(a):
            dialog_align["value"] = a
            preview_selected_only()

        for widget in (dlg_font, dlg_size, dlg_stroke, dlg_line_spacing, dlg_letter_spacing, dlg_char_width, dlg_char_height):
            if hasattr(widget, "valueChanged"):
                widget.valueChanged.connect(preview_selected_only)
        dlg_font.currentFontChanged.connect(preview_selected_only)
        dlg_bold.toggled.connect(preview_selected_only)
        dlg_italic.toggled.connect(preview_selected_only)
        dlg_strike.toggled.connect(preview_selected_only)
        for chk in include_checks.values():
            chk.toggled.connect(preview_selected_only)
        dlg_text_color_btn.clicked.connect(lambda: pick_color("text"))
        dlg_stroke_color_btn.clicked.connect(lambda: pick_color("stroke"))
        dlg_align_left.clicked.connect(lambda: set_align("left"))
        dlg_align_center.clicked.connect(lambda: set_align("center"))
        dlg_align_right.clicked.connect(lambda: set_align("right"))

        # ---------- rows ----------
        rows_widget = QWidget(dialog)
        rows_layout = QVBoxLayout(rows_widget)
        rows_layout.setContentsMargins(0, 0, 0, 0); rows_layout.setSpacing(4)
        scroll = QScrollArea(dialog); scroll.setWidgetResizable(True); scroll.setWidget(rows_widget); scroll.setMinimumHeight(300)
        layout.addWidget(scroll, 1)

        def refresh_rows(select_name=None):
            while rows_layout.count():
                item = rows_layout.takeAt(0)
                if item.widget():
                    item.widget().deleteLater()

            header = QWidget(rows_widget)
            h = QHBoxLayout(header); h.setContentsMargins(6, 2, 6, 2)
            h.addWidget(QLabel("사용"), 0)
            h.addWidget(QLabel("선택"), 0)
            h.addWidget(QLabel("이름"), 1)
            h.addWidget(QLabel("포함/내용"), 3)
            h.addWidget(QLabel("단축키"), 1)
            h.addWidget(QLabel("관리"), 1)
            rows_layout.addWidget(header)

            for name, preset in sorted(self.item_text_presets.items()):
                row = QWidget(rows_widget)
                row_l = QHBoxLayout(row); row_l.setContentsMargins(6, 2, 6, 2); row_l.setSpacing(6)
                chk_enabled = QCheckBox(); chk_enabled.setChecked(bool(preset.get("enabled", True)))
                btn_select = QPushButton("선택")
                name_edit = QLineEdit(name)
                summary = QLabel(self.style_summary_text(preset.get("style"), preset.get("include"))); summary.setWordWrap(True)
                key_edit = QKeySequenceEdit(QKeySequence(str(preset.get("shortcut", "") or ""))); key_edit.setMaximumWidth(160)
                btn_update = QPushButton("수정 저장")
                btn_delete = QPushButton("삭제")

                if not chk_enabled.isChecked():
                    if self.is_light_theme():
                        row.setStyleSheet("background:#f1f3f6; color:#8a8f99;")
                        summary.setStyleSheet("color:#8a8f99;")
                        name_edit.setStyleSheet("background:#f7f8fa; color:#8a8f99; border:1px solid #d0d5df;")
                        key_edit.setStyleSheet("background:#f7f8fa; color:#8a8f99; border:1px solid #d0d5df;")
                    else:
                        row.setStyleSheet("background:#242424; color:#888888;")
                        summary.setStyleSheet("color:#888888;")
                        name_edit.setStyleSheet("color:#888888;")
                        key_edit.setStyleSheet("color:#888888;")

                is_selected = (selected_name["value"] == name or select_name == name)
                if is_selected:
                    if self.is_light_theme():
                        row_style = "background:#e8f1ff; border:1px solid #6fa8ff;"
                        child_style = "background:#ffffff; color:#202124; border:1px solid #6fa8ff;"
                    else:
                        row_style = "background:#31415c; border:1px solid #5b8def;"
                        child_style = "background:#2f5fa7; color:white; border:1px solid #80b4ff;"
                    row.setStyleSheet(row_style)
                    btn_select.setText("선택됨")
                    btn_select.setStyleSheet("background:#4b79c7; color:white; font-weight:bold; border:1px solid #9cc3ff;")
                    name_edit.setStyleSheet(child_style)
                    summary.setStyleSheet(child_style)
                    key_edit.setStyleSheet(child_style)
                    btn_update.setStyleSheet("background:#3d5f92; color:white;")
                    btn_delete.setStyleSheet("background:#3d5f92; color:white;")
                    selected_name["value"] = name

                row_l.addWidget(chk_enabled)
                row_l.addWidget(btn_select)
                row_l.addWidget(name_edit, 1)
                row_l.addWidget(summary, 3)
                row_l.addWidget(key_edit, 1)
                row_l.addWidget(btn_update)
                row_l.addWidget(btn_delete)
                rows_layout.addWidget(row)

                def on_select(_checked=False, n=name):
                    # 이미 선택된 프리셋을 다시 누르면 선택 해제한다.
                    if selected_name["value"] == n:
                        selected_name["value"] = None
                        if original_page_snapshot is not None and page_idx in self.data:
                            self.data[page_idx] = copy.deepcopy(original_page_snapshot)
                            if self.idx == page_idx:
                                self.ref_tab()
                                if self.cb_mode.currentIndex() == 4:
                                    self.mode_chg(4)
                                    self.reselect_text_items([int(x) for x in selected_snapshot.keys() if str(x).isdigit()])
                        refresh_rows(None)
                        self.log(f"↩️ 개별 글꼴 프리셋 선택 해제: {n}")
                        return

                    p = self.item_text_presets.get(n)
                    if not p:
                        return
                    selected_name["value"] = n
                    apply_style_to_editor(p.get("style") or self.current_style_snapshot(), p.get("include") or {})
                    preview_selected_only()
                    refresh_rows(n)
                    self.log(f"🎛️ 개별 글꼴 프리셋 선택: {n}")

                def on_enabled(v, n=name, checkbox=chk_enabled):
                    if not self.set_item_text_preset_enabled_checked(n, bool(v), parent=dialog):
                        checkbox.blockSignals(True)
                        try:
                            checkbox.setChecked(not bool(v))
                        finally:
                            checkbox.blockSignals(False)
                        return
                    self.log(f"🔘 개별 글꼴 프리셋 {'사용' if v else '미사용'}: {n}")
                    refresh_rows(selected_name["value"])

                def on_shortcut_finished(edit=key_edit, n=name, old_seq=str(preset.get("shortcut", "") or "")):
                    seq_text = edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                    if self.normalize_shortcut_text(seq_text) == self.normalize_shortcut_text(old_seq):
                        return
                    if not self.set_item_text_preset_shortcut_checked(n, seq_text, parent=dialog):
                        edit.blockSignals(True)
                        try:
                            if old_seq:
                                edit.setKeySequence(QKeySequence(old_seq))
                            else:
                                edit.clear()
                        finally:
                            edit.blockSignals(False)
                        return
                    self.log(f"⌨️ 개별 글꼴 프리셋 단축키 변경: {n} = {seq_text or '없음'}")
                    refresh_rows(selected_name["value"])

                def on_name_finished(edit=name_edit, old_name=name):
                    new_name = self.safe_preset_name(edit.text())
                    if new_name == old_name:
                        edit.setText(old_name); return
                    if self.item_text_preset_path(new_name).exists():
                        QMessageBox.warning(dialog, self.tr_ui("이름 변경 실패"), self.tr_ui("같은 이름의 프리셋이 이미 있습니다."))
                        edit.setText(old_name); return
                    old_path = self.item_text_preset_path(old_name)
                    new_path = self.item_text_preset_path(new_name)
                    if old_path.exists():
                        old_path.rename(new_path)
                    if selected_name["value"] == old_name:
                        selected_name["value"] = new_name
                    self.load_item_text_preset_cache()
                    refresh_rows(new_name)

                def on_update(_checked=False, n=name, label=summary):
                    p_old = self.item_text_presets.get(n) or {}
                    p = {
                        "style": current_dialog_style(),
                        "include": current_include(),
                        "enabled": bool(p_old.get("enabled", True)),
                        "shortcut": str(p_old.get("shortcut", "") or ""),
                    }
                    safe = self.save_item_text_preset_named(n, p)
                    selected_name["value"] = safe
                    label.setText(self.style_summary_text(p["style"], p["include"]))
                    self.refresh_item_text_preset_combo()
                    self.apply_shortcuts()
                    refresh_rows(safe)
                    self.log(f"💾 개별 글꼴 프리셋 수정 저장: {safe}")

                def on_delete(_checked=False, n=name):
                    ans = QMessageBox.question(dialog, self.tr_ui("개별 프리셋 삭제"), self.tr_msg(f"'{n}' 프리셋을 삭제할까요?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                    if ans != QMessageBox.StandardButton.Yes:
                        return
                    try:
                        self.item_text_preset_path(n).unlink(missing_ok=True)
                    except Exception:
                        pass
                    if selected_name["value"] == n:
                        selected_name["value"] = None
                    self.load_item_text_preset_cache()
                    refresh_rows()
                    self.log(f"🗑️ 개별 글꼴 프리셋 삭제: {n}")

                btn_select.clicked.connect(on_select)
                chk_enabled.toggled.connect(on_enabled)
                key_edit.editingFinished.connect(on_shortcut_finished)
                name_edit.editingFinished.connect(on_name_finished)
                btn_update.clicked.connect(on_update)
                btn_delete.clicked.connect(on_delete)

            rows_layout.addStretch()

        # ---------- bottom buttons ----------
        btn_line = QHBoxLayout()
        btn_add = QPushButton(self.tr_ui("현재 설정을 새 개별 프리셋으로 추가"), dialog)
        btn_import = QPushButton(self.tr_ui("불러오기"), dialog)
        btn_ok = QPushButton(self.tr_ui("확인"), dialog)
        btn_close = QPushButton(self.tr_ui("닫기"), dialog)
        btn_line.addWidget(btn_add)
        btn_line.addWidget(btn_import)
        btn_line.addStretch()
        btn_line.addWidget(btn_ok)
        btn_line.addWidget(btn_close)
        layout.addLayout(btn_line)

        def add_current():
            name, ok = QInputDialog.getText(dialog, self.tr_ui("개별 프리셋 추가"), self.tr_ui("프리셋 이름:"))
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            if self.item_text_preset_path(safe).exists():
                ans = QMessageBox.question(dialog, self.tr_ui("덮어쓰기"), self.tr_msg(f"'{safe}' 프리셋이 이미 있습니다. 덮어쓸까요?"), QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
                if ans != QMessageBox.StandardButton.Yes:
                    return
            preset = {
                "style": current_dialog_style(),
                "include": current_include(),
                "enabled": True,
                "shortcut": "",
            }
            self.save_item_text_preset_named(safe, preset)
            self.load_item_text_preset_cache()
            # 새로 추가는 목록에만 추가한다. 파란 선택 강조는 남기지 않는다.
            selected_name["value"] = None
            refresh_rows(None)
            self.log(f"💾 개별 글꼴 프리셋 추가: {safe}")

        def import_item_preset():
            path, _ = QFileDialog.getOpenFileName(dialog, self.tr_ui("개별 글꼴 프리셋 불러오기"), str(self.item_text_preset_dir()), "JSON (*.json)")
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)
                if isinstance(raw, dict) and "style" in raw:
                    style = self.normalize_style_dict(raw.get("style"))
                    inc = raw.get("include") or {k: True for k, _ in self.style_field_specs()}
                else:
                    style = self.normalize_style_dict(raw)
                    inc = {k: True for k, _ in self.style_field_specs()}
            except Exception as e:
                QMessageBox.warning(dialog, self.tr_ui("불러오기 실패"), f"{self.tr_ui("프리셋 JSON을 읽지 못했습니다.")}\n{e}")
                return
            default_name = Path(path).stem
            name, ok = QInputDialog.getText(dialog, self.tr_ui("프리셋 이름"), self.tr_ui("추가할 프리셋 이름:"), text=default_name)
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            preset = {"style": style, "include": inc, "enabled": True, "shortcut": ""}
            self.save_item_text_preset_named(safe, preset)
            self.load_item_text_preset_cache()
            # 불러오기는 프리셋 목록에 추가만 한다. 파란 선택 행은 남기지 않는다.
            selected_name["value"] = None
            apply_style_to_editor(style, inc)
            preview_selected_only()
            refresh_rows(None)
            self.log(f"📥 개별 글꼴 프리셋 불러오기 완료: {safe}")

        def restore_selected_preview():
            # 개별 프리셋 창은 실제 적용 창이 아니므로, 나갈 때는 창을 열기 전 페이지 상태로 통째로 복구한다.
            if original_page_snapshot is not None and page_idx in self.data:
                self.data[page_idx] = copy.deepcopy(original_page_snapshot)
            else:
                self.restore_text_items_by_snapshot(page_idx, selected_snapshot)
            if self.idx == page_idx:
                self.ref_tab()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
                    self.reselect_text_items([int(x) for x in selected_snapshot.keys() if str(x).isdigit()])
                    self.update_item_preset_combo_for_selected_texts()

        def accept_and_save_state():
            restore_selected_preview()
            self.save_item_text_preset_state(current_dialog_style(), current_include(), selected_name["value"])
            self.load_item_text_preset_cache()
            self.log("💾 개별 글꼴 프리셋 마지막 설정 저장 완료")
            dialog.accept()

        def reject_without_state():
            restore_selected_preview()
            dialog.reject()

        btn_add.clicked.connect(add_current)
        btn_import.clicked.connect(import_item_preset)
        btn_ok.clicked.connect(accept_and_save_state)
        btn_close.clicked.connect(reject_without_state)

        apply_style_to_editor(base_style, include_default)
        refresh_color_buttons()
        refresh_rows(selected_name["value"])
        preview_selected_only()
        result = dialog.exec()
        if result != QDialog.DialogCode.Accepted:
            restore_selected_preview()


    def set_preset_combo_to_last(self):
        if not hasattr(self, "cb_text_preset") or self._preset_loading:
            return
        self.cb_text_preset.blockSignals(True)
        try:
            self.cb_text_preset.setCurrentIndex(0)
        finally:
            self.cb_text_preset.blockSignals(False)

    def ensure_item_style_defaults_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr:
            return
        style = self.current_style_snapshot()
        for item in curr.get('data', []):
            item.setdefault('font_family', style['font_family'])
            item.setdefault('font_size', style['font_size'])
            item.setdefault('stroke_width', style['stroke_width'])
            item.setdefault('text_color', style['text_color'])
            item.setdefault('stroke_color', style['stroke_color'])
            item.setdefault('align', style['align'])
            item.setdefault('line_spacing', style['line_spacing'])
            item.setdefault('letter_spacing', style['letter_spacing'])
            item.setdefault('char_width', style['char_width'])
            item.setdefault('char_height', style['char_height'])
            item.setdefault('bold', style['bold'])
            item.setdefault('italic', style['italic'])
            item.setdefault('strike', style['strike'])

    def apply_style_dict_to_data_items(self, items, style):
        style = self.normalize_style_dict(style)
        for item in items or []:
            item.update({
                'font_family': style['font_family'],
                'font_size': style['font_size'],
                'stroke_width': style['stroke_width'],
                'text_color': style['text_color'],
                'stroke_color': style['stroke_color'],
                'align': style['align'],
                'line_spacing': style['line_spacing'],
                'letter_spacing': style['letter_spacing'],
                'char_width': style['char_width'],
                'char_height': style['char_height'],
                'bold': style['bold'],
                'italic': style['italic'],
                'strike': style['strike'],
            })

    def apply_current_preset_to_data_items(self, items):
        self.apply_style_dict_to_data_items(items, self.current_style_snapshot())

    def apply_current_preset_to_page(self, page_idx, refresh=False):
        curr = self.data.get(page_idx)
        if not curr:
            self.log("⚠️ 현재 페이지가 없어 프리셋 페이지 적용을 건너뜁니다.")
            return 0
        targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
        if targets:
            self.push_project_undo("현재 페이지 글꼴 프리셋 적용", page_idx=page_idx)
        self.apply_current_preset_to_data_items(targets)
        if refresh and page_idx == self.idx:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🎛️ 현재 페이지 프리셋 적용: {len(targets)}개")
        # 현재 페이지 프리셋 적용은 Undo 경계가 아니라 일반 Undo 스택에 포함한다.
        return len(targets)

    def apply_current_preset_to_all_pages(self):
        total = 0
        touched_current = False
        undo_record = self.make_project_undo_record("전체 페이지 글꼴 프리셋 적용", full_project=True)

        for i in range(len(self.paths)):
            curr = self.data.get(i)
            if not curr:
                continue
            targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
            self.apply_current_preset_to_data_items(targets)
            total += len(targets)
            if i == self.idx:
                touched_current = True

        if touched_current and self.idx in self.data:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)

        self.auto_save_project()
        if total:
            self.append_project_undo_record(undo_record)
            self.log(f"🎛️ 전체 페이지 프리셋 적용: {total}개")
            # 전체 페이지 프리셋 적용은 Undo 경계가 아니라 일반 Undo 스택에 포함한다.
        else:
            self.log("⚠️ 적용할 페이지/텍스트가 없어 전체 프리셋 적용을 건너뜁니다.")

    # =========================================================
    # 1.2 자동화 작업
    # =========================================================
    def auto_target_items_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr:
            return []
        return [x for x in curr.get('data', []) if x.get('use_inpaint', True)]

    def item_layout_text(self, item):
        text = str(item.get('translated_text', '') or '')
        if not text.strip():
            text = str(item.get('text', '') or '')
        return text

    def ensure_item_style_for_auto(self, item):
        style = self.current_style_snapshot()
        item.setdefault('font_family', style['font_family'])
        item.setdefault('font_size', style['font_size'])
        item.setdefault('stroke_width', style['stroke_width'])
        item.setdefault('text_color', style['text_color'])
        item.setdefault('stroke_color', style['stroke_color'])
        item.setdefault('align', style['align'])

    def auto_wrap_lines_for_metrics(self, text, fm, max_w, protect_short_tokens=True):
        """
        QFontMetrics 기준으로 줄바꿈 결과를 계산한다.

        1.2 조건:
        - 전체 텍스트가 5글자 이하라면 영역을 넘어도 줄내림하지 않는다.
        - 단어/덩어리가 5글자 이하라면 그 덩어리 내부는 끊지 않는다.
        - 6글자 이상 덩어리는 영역을 넘으면 글자 단위로 끊어 내린다.
        """
        text = str(text or '').replace('\r\n', '\n').replace('\r', '\n')
        max_w = max(1, int(max_w))

        # 공백 없는 단일 덩어리가 5글자 이하일 때만 한 줄 보호.
        # "저게 뭐야?"처럼 띄어쓰기가 있는 짧은 문장은 단어 사이에서 줄내림할 수 있어야 한다.
        compact_len = len(''.join(ch for ch in text if not ch.isspace()))
        has_spacing = any(ch.isspace() for ch in text.strip())
        if protect_short_tokens and compact_len <= 5 and not has_spacing:
            return [text.replace('\n', '').strip()]

        def split_units(paragraph):
            units = []
            buf = ''
            for ch in paragraph:
                if ch.isspace():
                    if buf:
                        units.append(buf)
                        buf = ''
                    if ch == ' ':
                        units.append(' ')
                else:
                    buf += ch
            if buf:
                units.append(buf)
            return units

        def append_line(lines, current):
            if current or not lines:
                lines.append(current.rstrip())

        def break_long_unit(unit, current, lines):
            # 6글자 이상 덩어리는 필요하면 글자 단위로 끊는다.
            for ch in unit:
                trial = current + ch
                if current and fm.horizontalAdvance(trial) > max_w:
                    append_line(lines, current)
                    current = ch
                else:
                    current = trial
            return current

        result = []
        for para in text.split('\n'):
            if para == '':
                result.append('')
                continue

            lines = []
            current = ''
            for unit in split_units(para):
                if unit == ' ':
                    # 줄 첫머리 공백은 버린다.
                    if current:
                        trial = current + unit
                        if fm.horizontalAdvance(trial) <= max_w:
                            current = trial
                    continue

                unit_len = len(unit)
                trial = current + unit

                if fm.horizontalAdvance(trial) <= max_w:
                    current = trial
                    continue

                if unit_len <= 5:
                    # 짧은 단어는 내부에서 끊지 않는다.
                    if current:
                        append_line(lines, current)
                    current = unit
                else:
                    # 긴 덩어리는 현재 줄에 들어갈 만큼 넣고, 넘치면 글자 단위로 끊는다.
                    current = break_long_unit(unit, current, lines)

            append_line(lines, current)
            result.extend(lines)

        return result or ['']

    def auto_measure_text_block(self, text, family, size, max_w, stroke=0):
        font = QFont(family)
        font.setPixelSize(int(size))
        fm = QFontMetrics(font)
        lines = self.auto_wrap_lines_for_metrics(text, fm, max_w)

        max_line_w = 0
        for line in lines:
            max_line_w = max(max_line_w, fm.horizontalAdvance(line))

        # lineSpacing이 실제 줄 간격에 더 가까워서 height()보다 안정적이다.
        total_h = fm.lineSpacing() * max(1, len(lines)) + int(stroke) * 2
        total_w = max_line_w + int(stroke) * 2
        return total_w, total_h, lines

    def _rect_from_vertices_like(self, vertices):
        try:
            pts = []
            for v in vertices or []:
                if isinstance(v, dict):
                    x = int(round(float(v.get('x', 0))))
                    y = int(round(float(v.get('y', 0))))
                else:
                    x = int(round(float(v[0])))
                    y = int(round(float(v[1])))
                pts.append((x, y))
            if not pts:
                return None
            xs = [p[0] for p in pts]
            ys = [p[1] for p in pts]
            x1, x2 = min(xs), max(xs)
            y1, y2 = min(ys), max(ys)
            return [x1, y1, max(1, x2 - x1), max(1, y2 - y1)]
        except Exception:
            return None

    def _normalize_ocr_piece(self, piece):
        if not isinstance(piece, dict):
            return None

        text = str(piece.get('text') or piece.get('inferText') or piece.get('label') or '').strip()
        rect = None
        if piece.get('rect') is not None:
            try:
                r = piece.get('rect')
                rect = [int(round(float(r[0]))), int(round(float(r[1]))), int(round(float(r[2]))), int(round(float(r[3])))]
            except Exception:
                rect = None
        if rect is None:
            if isinstance(piece.get('boundingPoly'), dict):
                rect = self._rect_from_vertices_like(piece.get('boundingPoly', {}).get('vertices'))
            elif piece.get('vertices') is not None:
                rect = self._rect_from_vertices_like(piece.get('vertices'))

        if not rect:
            return None

        x, y, w, h = rect
        compact_text = ''.join(ch for ch in text if not ch.isspace())
        try:
            char_count = int(piece.get('char_count') or len(compact_text) or 1)
        except Exception:
            char_count = max(1, len(compact_text))
        return {
            'text': text,
            'char_count': max(1, char_count),
            'rect': [x, y, w, h],
            'cx': x + w / 2.0,
            'cy': y + h / 2.0,
            'w': w,
            'h': h,
            'area': max(1, w * h),
            'source_provider': str(piece.get('source_provider', '') or piece.get('source', '') or ''),
            'locale': str(piece.get('locale', '') or ''),
        }

    def _collect_item_ocr_pieces(self, item):
        """분석 결과에 포함돼 있을 수 있는 OCR 조각들을 최대한 수집한다."""
        pieces = []
        for key in ['ocr_items', 'raw_items', 'source_items', 'children', 'segments', 'parts', 'items', 'fragments']:
            val = item.get(key)
            if isinstance(val, list):
                for p in val:
                    npiece = self._normalize_ocr_piece(p)
                    if npiece:
                        pieces.append(npiece)
        dedup = []
        seen = set()
        for p in pieces:
            sig = (tuple(p['rect']), p['text'])
            if sig in seen:
                continue
            seen.add(sig)
            dedup.append(p)
        return dedup

    def estimate_source_font_size_from_ocr_coords(self, item):
        """CLOVA OCR 조각 좌표를 이용해 원문 글자 크기를 추정한다.

        이전 방식의 문제:
        - 그룹 전체 rect 높이 / 전체 글자 수로 상한을 걸면,
          여러 세로열이 한 말풍선에 들어간 경우 글자 크기가 과하게 작아진다.
        - fallback/mask가 작은 값으로 나오면 OCR 좌표 추정값까지 같이 깎였다.

        새 방식:
        - OCR 조각 자체의 긴 방향/글자수 + 짧은 방향 폭을 우선 사용한다.
        - 글자 단위 OCR 조각이 있을 때만 중심 간격을 보조로 사용한다.
        - 그룹 전체 글자수 기반 전역 cap은 사용하지 않는다.
        """
        pieces = self._collect_item_ocr_pieces(item)
        if not pieces:
            return None

        rect = item.get('rect') or [0, 0, 1, 1]
        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception:
            box_w, box_h = 1, 1

        vertical = box_h >= box_w

        size_vals = [p['h'] if vertical else p['w'] for p in pieces]
        area_vals = [p['area'] for p in pieces]
        med_size = float(np.median(size_vals)) if size_vals else 0.0
        med_area = float(np.median(area_vals)) if area_vals else 0.0

        # 후리가나/첨자 후보는 이미 엔진에서 분리하지만,
        # 기존 프로젝트나 예외 케이스를 위해 한 번 더 방어한다.
        main_pieces = [
            p for p in pieces
            if (p['h'] if vertical else p['w']) >= max(3.0, med_size * 0.55)
            and p['area'] >= max(4.0, med_area * 0.30)
        ] or pieces

        piece_sizes = []
        for p in main_pieces:
            axis_len = float(p['h'] if vertical else p['w'])
            cross_len = float(p['w'] if vertical else p['h'])
            char_count = max(1, int(p['char_count']))

            provider = str(p.get('source_provider', '') or '').lower()
            if char_count <= 1:
                # 글자 단위로 잡힌 경우: 짧은 방향 폭이 글자 크기에 가깝다.
                if provider == 'google_vision':
                    score = max(cross_len * 1.00, axis_len * 0.80)
                else:
                    score = max(cross_len * 0.95, axis_len * 0.85)
            else:
                # 단어/문장 덩어리로 잡힌 경우:
                # 긴 방향/글자수는 글자 피치, 짧은 방향은 실제 획 폭에 가깝다.
                pitch = axis_len / char_count
                if provider == 'google_vision':
                    # Google Vision은 단어/행 단위 박스가 CLOVA보다 넓게 잡히는 경우가 있어
                    # 짧은 방향 폭을 조금 더 신뢰해 원문 글자 크기 추정이 과소평가되지 않게 한다.
                    score = max(pitch * 1.05, cross_len * 1.02)
                else:
                    score = max(pitch * 1.08, cross_len * 0.88)

            piece_sizes.append(score)

        if not piece_sizes:
            return None

        piece_est = float(np.median(piece_sizes))

        # 글자 단위 OCR 조각이 여러 개 있을 때만 중심 간격을 보조로 사용한다.
        gap_est = None
        single_pieces = [p for p in main_pieces if int(p.get('char_count', 1)) == 1]
        if len(single_pieces) >= 2:
            if vertical:
                base_axis = float(np.median([p['cx'] for p in single_pieces]))
                aligned = [p for p in single_pieces if abs(p['cx'] - base_axis) <= max(8.0, piece_est * 0.75)]
                aligned = aligned if len(aligned) >= 2 else single_pieces
                ordered = sorted(aligned, key=lambda p: p['cy'])
                gaps = [b['cy'] - a['cy'] for a, b in zip(ordered, ordered[1:]) if (b['cy'] - a['cy']) > 2]
            else:
                base_axis = float(np.median([p['cy'] for p in single_pieces]))
                aligned = [p for p in single_pieces if abs(p['cy'] - base_axis) <= max(8.0, piece_est * 0.75)]
                aligned = aligned if len(aligned) >= 2 else single_pieces
                ordered = sorted(aligned, key=lambda p: p['cx'])
                gaps = [b['cx'] - a['cx'] for a, b in zip(ordered, ordered[1:]) if (b['cx'] - a['cx']) > 2]

            if gaps:
                candidate = float(np.median(gaps)) * 0.96
                # 중심 간격이 조각 추정값과 너무 다르면, 줄/열 간격을 잘못 잡은 것으로 보고 버린다.
                if piece_est * 0.55 <= candidate <= piece_est * 1.80:
                    gap_est = candidate

        if gap_est is not None:
            est = (piece_est + gap_est) / 2.0
        else:
            est = piece_est

        # 아주 극단적인 값만 말풍선 크기로 제한한다.
        est = min(est, max(8.0, box_h * 0.90, box_w * 0.90))
        return max(5, int(round(est)))

    def estimate_source_font_size_from_mask(self, item, page_idx=None):
        """텍스트 마스크 연결요소로 폰트 크기 보정값을 얻는다."""
        if page_idx is None:
            page_idx = self.idx

        curr = self.data.get(page_idx)
        if not curr:
            return None

        mask = curr.get('mask_merge')
        if mask is None or not isinstance(mask, np.ndarray):
            return None

        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return None

        try:
            x, y, w, h = [int(v) for v in rect[:4]]
        except Exception:
            return None

        if mask.ndim == 3:
            gray = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
        else:
            gray = mask.copy()

        mh, mw = gray.shape[:2]
        x1 = max(0, x)
        y1 = max(0, y)
        x2 = min(mw, x + max(1, w))
        y2 = min(mh, y + max(1, h))
        if x2 <= x1 or y2 <= y1:
            return None

        crop = gray[y1:y2, x1:x2]
        if crop.size == 0:
            return None

        _, bw = cv2.threshold(crop, 0, 255, cv2.THRESH_BINARY)
        if int(np.count_nonzero(bw)) <= 0:
            return None

        num, labels, stats, cent = cv2.connectedComponentsWithStats(bw, 8)
        heights = []
        crop_area = max(1, crop.shape[0] * crop.shape[1])
        min_area = max(3, int(crop_area * 0.0003))

        for i in range(1, num):
            ww = int(stats[i, cv2.CC_STAT_WIDTH])
            hh = int(stats[i, cv2.CC_STAT_HEIGHT])
            aa = int(stats[i, cv2.CC_STAT_AREA])
            if aa < min_area or hh < 3 or ww < 1:
                continue
            heights.append(hh)

        if not heights:
            return None

        est = float(np.median(heights)) * 1.04
        try:
            box_h = max(1, int(rect[3]))
            est = min(est, box_h * 0.75)
        except Exception:
            pass
        return max(5, int(round(est)))

    def estimate_source_font_size_fallback(self, item):
        """OCR 박스와 원문 글자 수로 최후 보정값을 추정한다."""
        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return None

        source_text = str(item.get('text', '') or '')
        if not source_text.strip():
            return None

        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception:
            return None

        compact_len = max(1, len(''.join(ch for ch in source_text if not ch.isspace())))
        lines = [line.strip() for line in source_text.replace('\r\n', '\n').replace('\r', '\n').split('\n') if line.strip()]
        line_count = max(1, len(lines))
        vertical = box_h >= box_w

        height_based = (box_h / line_count) * 0.64
        density_based = ((box_w * box_h) / compact_len) ** 0.5 * 0.88

        if compact_len <= 5:
            density_based *= 0.85

        # 여러 세로열이 한 그룹에 들어간 경우 box_h / 전체 글자 수는 너무 작아진다.
        # fallback에서는 높이/밀도만 사용하고, 전체 글자 수 기반 긴축 cap은 걸지 않는다.
        est = min(height_based, density_based)
        return max(5, int(round(est)))

    def auto_text_size_item(self, item, page_idx=None):
        """원문 기준으로 font_size만 조정한다.

        우선순위:
        1) CLOVA OCR 조각 좌표 추정
        2) 텍스트 마스크 추정
        3) OCR 박스/글자수 fallback
        """
        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return False

        source_text = str(item.get('text', '') or '')
        if not source_text.strip():
            return False

        self.ensure_item_style_for_auto(item)

        ocr_est = self.estimate_source_font_size_from_ocr_coords(item)
        mask_est = self.estimate_source_font_size_from_mask(item, page_idx)
        fallback_est = self.estimate_source_font_size_fallback(item)

        candidates = []
        if ocr_est is not None:
            candidates.append(float(ocr_est))
        if mask_est is not None:
            candidates.append(float(mask_est))
        if fallback_est is not None:
            candidates.append(float(fallback_est))
        if not candidates:
            return False

        if ocr_est is not None:
            # OCR 조각 좌표가 있으면 그 값을 최우선으로 쓴다.
            # fallback/mask는 예전처럼 작은 값으로 OCR 추정치를 깎지 않는다.
            best = float(ocr_est)
        else:
            best = min(candidates)

        best = max(5, min(260, int(round(best))))
        old_value = int(item.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value())
        item['font_size'] = best
        return old_value != best

    def normalize_auto_wrap_source_text(self, text):
        """
        자동 줄 내림은 매번 기존 줄바꿈을 기준으로 이어 붙인 뒤 다시 계산한다.

        기존 줄바꿈을 그대로 보존하면,
        글자를 크게 키운 상태에서 자동 줄내림 → 한 글자씩 잘림 → 다시 실행해도 안 붙음
        같은 고착 현상이 생긴다.
        """
        parts = [p.strip() for p in str(text or '').replace('\r\n', '\n').replace('\r', '\n').split('\n')]
        parts = [p for p in parts if p]
        if not parts:
            return ""

        result = parts[0]
        for part in parts[1:]:
            prev = result[-1] if result else ''
            nxt = part[0] if part else ''

            # 영어/숫자 단어 사이만 공백을 보존하고,
            # 한글/일본어/기호는 기존 자동 줄바꿈을 없앤다는 느낌으로 붙인다.
            if prev.isascii() and nxt.isascii() and prev.isalnum() and nxt.isalnum():
                result += " " + part
            else:
                result += part

        return result

    def auto_wrap_text_for_item(self, item):
        """현재 번역문을 텍스트 박스 폭에 맞춰 자동 줄내림한다.

        v1.4 보정:
        - 텍스트는 영역 최상단부터 들어간다는 전제로 계산한다.
        - 줄내림 후 높이가 박스 하단을 넘으면 글자 크기를 1px씩 줄이고 다시 줄내림한다.
        - 좌우 폭 초과보다 하단 초과를 우선 방지한다.
        """
        rect = item.get('rect')
        if not rect or len(rect) < 4:
            return False

        original = str(item.get('translated_text', '') or '')
        if not original.strip():
            return False

        source_text = self.normalize_auto_wrap_source_text(original)
        if not source_text.strip():
            return False

        self.ensure_item_style_for_auto(item)

        try:
            box_w = max(1, int(rect[2]))
            box_h = max(1, int(rect[3]))
        except Exception:
            return False

        family = item.get('font_family') or self.cb_font.currentFont().family()
        start_size = int(item.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value())
        stroke = int(item.get('stroke_width', 0) or 0)

        # 기존 줄내림 기준은 유지하되, 하단을 넘으면 크기를 줄이면서 다시 감는다.
        max_w = max(1, int(box_w * 1.00) - stroke * 2)
        max_h = max(1, int(box_h) - stroke * 2)

        min_size = 5
        chosen_size = max(min_size, start_size)
        chosen_lines = None
        chosen_height = None

        for size in range(max(min_size, start_size), min_size - 1, -1):
            font = QFont(family)
            font.setPixelSize(size)
            fm = QFontMetrics(font)
            lines = self.auto_wrap_lines_for_metrics(source_text, fm, max_w, protect_short_tokens=True)
            line_count = max(1, len(lines))
            total_h = fm.lineSpacing() * line_count

            chosen_size = size
            chosen_lines = lines
            chosen_height = total_h

            if total_h <= max_h:
                break

        if chosen_lines is None:
            return False

        wrapped = '\n'.join(chosen_lines).strip()
        changed = False

        if wrapped and wrapped != original:
            item['translated_text'] = wrapped
            changed = True

        if int(item.get('font_size', start_size) or start_size) != chosen_size:
            item['font_size'] = int(chosen_size)
            changed = True

        if changed and chosen_height is not None and chosen_height > max_h:
            item['auto_wrap_height_overflow'] = True
        elif changed:
            item.pop('auto_wrap_height_overflow', None)

        return changed

    def auto_text_size_for_page(self, page_idx, refresh=False):
        changed = 0
        for item in self.auto_target_items_for_page(page_idx):
            if self.auto_text_size_item(item, page_idx=page_idx):
                changed += 1
        if refresh and page_idx == self.idx:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        return changed

    def auto_linebreak_for_page(self, page_idx, refresh=False):
        changed = 0
        for item in self.auto_target_items_for_page(page_idx):
            if self.auto_wrap_text_for_item(item):
                changed += 1
        if refresh and page_idx == self.idx:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        return changed

    def auto_text_size_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("자동 텍스트 크기 조정")
        changed = self.auto_text_size_for_page(self.idx, refresh=True)
        if changed:
            self.append_project_undo_record(undo_rec)
        self.auto_save_project()
        self.log(f"🤖 자동 텍스트 크기 조정 완료: 현재 페이지 {changed}개")

    def auto_text_size_batch(self):
        if not self.paths:
            return
        if getattr(self, "ui_language", LANG_KO) == LANG_EN:
            msg = f"Run Batch Auto Text Size on total {len(self.paths)} page(s)?"
        else:
            msg = f"자동 텍스트 크기 조정을 총 {len(self.paths)}페이지에 실행합니다."
        if not self.confirm_batch_operation("일괄 자동 텍스트 크기 조정", msg):
            self.log("↩️ 일괄 자동 텍스트 크기 조정 취소")
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("일괄 자동 텍스트 크기 조정", full_project=True)
        total = 0
        pages = 0
        for i in range(len(self.paths)):
            changed = self.auto_text_size_for_page(i, refresh=False)
            if changed:
                pages += 1
                total += changed
        if total:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🤖 일괄 자동 텍스트 크기 조정 완료: {pages}페이지 / {total}개")

    def auto_linebreak_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("자동 줄 내림")
        changed = self.auto_linebreak_for_page(self.idx, refresh=True)
        if changed:
            self.append_project_undo_record(undo_rec)
        self.auto_save_project()
        self.log(f"🤖 자동 줄 내림 완료: 현재 페이지 {changed}개")

    def auto_linebreak_batch(self):
        if not self.paths:
            return
        if getattr(self, "ui_language", LANG_KO) == LANG_EN:
            msg = f"Run Batch Auto Line Break on total {len(self.paths)} page(s)?"
        else:
            msg = f"자동 줄 내림을 총 {len(self.paths)}페이지에 실행합니다."
        if not self.confirm_batch_operation("일괄 자동 줄 내림", msg):
            self.log("↩️ 일괄 자동 줄 내림 취소")
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("일괄 자동 줄 내림", full_project=True)
        total = 0
        pages = 0
        for i in range(len(self.paths)):
            changed = self.auto_linebreak_for_page(i, refresh=False)
            if changed:
                pages += 1
                total += changed
        if total:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🤖 일괄 자동 줄 내림 완료: {pages}페이지 / {total}개")

    def current_scene_cursor_pos(self):
        try:
            return self.view.mapToScene(self.view.mapFromGlobal(QCursor.pos()))
        except Exception:
            rect = self.view.scene.sceneRect()
            return rect.center()

    def item_id_value(self, item_or_data):
        data = item_or_data.data if isinstance(item_or_data, TypesettingItem) else item_or_data
        try:
            return int(data.get('id'))
        except Exception:
            return data.get('id') if isinstance(data, dict) else None

    def find_data_item_by_id(self, item_id):
        curr = self.data.get(self.idx)
        if not curr:
            return None
        for d in curr.get('data', []):
            if str(d.get('id')) == str(item_id):
                return d
        return None

    def select_text_item_and_row(self, text_item):
        if text_item is None:
            return
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        scene = self._safe_graphics_scene()
        if scene is None:
            return
        self._syncing_selection = True
        try:
            try:
                for item in scene.items():
                    if isinstance(item, TypesettingItem):
                        item.setSelected(item is text_item)
            except RuntimeError:
                return
            self.select_table_rows_by_ids([text_item.data.get('id')])
        finally:
            self._syncing_selection = False
        self.on_scene_selection_changed()

    def row_to_text_data(self, row):
        curr = self.data.get(self.idx)
        if not curr or row <= 0:
            return None
        data_index = row - 1
        d = curr.get('data', [])
        if 0 <= data_index < len(d):
            return d[data_index]
        return None

    def selected_text_data_items(self):
        curr = self.data.get(self.idx)
        if not curr:
            return []
        ids = {str(x.data.get('id')) for x in self.selected_text_items()}
        ids.update(str(x) for x in self.selected_table_text_ids())
        if not ids:
            return []
        return [d for d in curr.get('data', []) if str(d.get('id')) in ids]

    def clear_masks_for_text_data(self, data_item):
        curr = self.data.get(self.idx)
        if not curr or not data_item:
            return

        rect = data_item.get('rect') or [0, 0, 0, 0]
        try:
            x = int(round(float(rect[0]) + float(data_item.get('x_off', 0) or 0)))
            y = int(round(float(rect[1]) + float(data_item.get('y_off', 0) or 0)))
            w = int(round(float(rect[2])))
            h = int(round(float(rect[3])))
        except Exception:
            return

        if w <= 0 or h <= 0:
            return

        for key in ('mask_merge', 'mask_inpaint', 'mask_merge_off', 'mask_inpaint_off'):
            mask = curr.get(key)
            if not isinstance(mask, np.ndarray):
                continue
            mh, mw = mask.shape[:2]
            x1 = max(0, x)
            y1 = max(0, y)
            x2 = min(mw, x + w)
            y2 = min(mh, y + h)
            if x2 <= x1 or y2 <= y1:
                continue
            if mask.ndim == 2:
                mask[y1:y2, x1:x2] = 0
            else:
                mask[y1:y2, x1:x2, :] = 0
            curr[key] = mask

    def delete_text_data_items(self, data_items=None, ask=True):
        curr = self.data.get(self.idx)
        if not curr:
            return False

        if data_items is None:
            data_items = self.selected_text_data_items()
        data_items = [d for d in (data_items or []) if d in curr.get('data', [])]
        if not data_items:
            self.log("⚠️ There is no text to delete." if self.ui_language == LANG_EN else "⚠️ 삭제할 텍스트가 없습니다.")
            return False

        if ask:
            if self.ui_language == LANG_EN:
                msg = f"Delete {len(data_items)} selected text item(s)?\nThe mask for those areas will also be cleared."
            else:
                msg = f"선택한 텍스트 {len(data_items)}개를 삭제할까요?\n해당 영역의 마스크도 함께 지워집니다."
            ans = QMessageBox.question(
                self,
                self.tr_ui("텍스트 삭제"),
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return False

        # 058에서 텍스트 라인 삭제를 프로젝트 스냅샷 Undo로 잡았더니
        # 표/탭 갱신 시 렉이 커져서, 가벼운 기존 page undo 방식으로 되돌린다.
        self.push_text_line_undo('텍스트 삭제', include_masks=True)

        deleted_count = 0
        for d in list(data_items):
            self.clear_masks_for_text_data(d)
            try:
                curr['data'].remove(d)
                deleted_count += 1
            except ValueError:
                pass

        if deleted_count <= 0:
            return False

        # 삭제 후 우측 텍스트 행 라인넘버(ID)를 1부터 다시 정렬한다.
        # 분석도/마스크 탭의 왼쪽 번호 박스도 같은 data id를 보므로 즉시 다시 그린다.
        self.renumber_text_items_for_current_page(curr)

        self.ref_tab()
        self.refresh_after_text_line_change(autosave=True)
        self.log((f"🗑️ Text deletion complete: {deleted_count} items / IDs reordered" if self.ui_language == LANG_EN else f"🗑️ 텍스트 삭제 완료: {deleted_count}개 / 번호 재정렬"))
        return True

    def copy_text_data_items(self, data_items=None):
        if data_items is None:
            data_items = self.selected_text_data_items()
        data_items = [d for d in (data_items or []) if isinstance(d, dict)]
        if not data_items:
            self.log("⚠️ 복사할 텍스트가 없습니다.")
            return False

        self.text_clipboard = [copy.deepcopy(d) for d in data_items]
        self.log(f"📋 텍스트 복사 완료: {len(self.text_clipboard)}개")
        return True

    def next_text_id(self):
        curr = self.data.get(self.idx)
        max_id = 0
        if curr:
            for d in curr.get('data', []):
                try:
                    max_id = max(max_id, int(d.get('id', 0)))
                except Exception:
                    pass
        return max_id + 1

    def paste_text_clipboard_at(self, scene_pos=None):
        curr = self.data.get(self.idx)
        if not curr:
            return False
        if not self.text_clipboard:
            self.log("⚠️ 붙여넣을 텍스트가 없습니다.")
            return False

        if scene_pos is None:
            scene_pos = self.current_scene_cursor_pos()
        try:
            px, py = float(scene_pos.x()), float(scene_pos.y())
        except Exception:
            px, py = 0.0, 0.0

        src_items = [copy.deepcopy(d) for d in self.text_clipboard]
        first = src_items[0].get('rect') or [0, 0, 1, 1]
        try:
            base_x = float(first[0]) + float(src_items[0].get('x_off', 0) or 0)
            base_y = float(first[1]) + float(src_items[0].get('y_off', 0) or 0)
        except Exception:
            base_x, base_y = 0.0, 0.0

        self.push_page_text_undo('텍스트 붙여넣기')

        new_ids = []
        next_id = self.next_text_id()
        for i, d in enumerate(src_items):
            rect = list(d.get('rect') or [0, 0, 260, 80])
            while len(rect) < 4:
                rect.append(1)
            try:
                old_x = float(rect[0]) + float(d.get('x_off', 0) or 0)
                old_y = float(rect[1]) + float(d.get('y_off', 0) or 0)
                dx = old_x - base_x
                dy = old_y - base_y
                rect[0] = int(round(px + dx))
                rect[1] = int(round(py + dy))
            except Exception:
                rect[0] = int(round(px))
                rect[1] = int(round(py))

            d['id'] = next_id
            next_id += 1
            d['rect'] = [int(rect[0]), int(rect[1]), max(1, int(rect[2])), max(1, int(rect[3]))]
            d['x_off'] = 0
            d['y_off'] = 0
            d['manual_text_rect'] = True
            d['text_anchor_mode'] = 'text'
            d['use_inpaint'] = True
            d.pop('pending_new_text', None)
            d.pop('force_show', None)
            new_ids.append(d['id'])
            curr.setdefault('data', []).append(d)

        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            self.reselect_text_items(new_ids)
        self.auto_save_project()
        self.log(f"📋 텍스트 붙여넣기 완료: {len(new_ids)}개")
        return True

    def enter_text_paste_mode(self):
        """Ctrl+V는 즉시 붙여넣지 않고, 커서에 미리보기만 붙인 뒤 클릭 위치에 확정한다."""
        if self.cb_mode.currentIndex() != 4:
            return False
        if not self.text_clipboard:
            self.log("⚠️ 붙여넣을 텍스트가 없습니다.")
            return False

        self.text_paste_pending = True
        self.set_tool("paste_text")
        try:
            self.view.show_paste_preview(self.text_clipboard, self.current_scene_cursor_pos())
        except Exception:
            pass
        self.log("📋 붙여넣기 위치 지정: 마우스를 움직인 뒤 클릭하면 붙여넣습니다. ESC로 취소.")
        return True

    def finish_text_paste_at(self, scene_pos):
        if not self.text_paste_pending:
            return False

        self.text_paste_pending = False
        try:
            self.view.clear_paste_preview()
        except Exception:
            pass

        ok = self.paste_text_clipboard_at(scene_pos)
        self.set_tool(None)
        return ok


    def show_final_text_context_menu(self, text_item, global_pos, scene_pos=None):
        if self.cb_mode.currentIndex() != 4 or text_item is None:
            return
        self.last_canvas_context_pos = scene_pos
        self.select_text_item_and_row(text_item)

        menu = QMenu(self)
        act_copy = menu.addAction("텍스트 복사")
        act_paste = menu.addAction("텍스트 붙여넣기")
        act_paste.setEnabled(bool(self.text_clipboard))
        menu.addSeparator()
        act_transform = menu.addAction("텍스트 변형")
        act_transform.setCheckable(True)
        act_transform.setChecked(bool(text_item.data.get('_transform_mode', False)))
        menu.addSeparator()
        act_delete = menu.addAction(self.tr_ui("텍스트 삭제"))

        chosen = menu.exec(global_pos)
        if chosen == act_copy:
            self.copy_text_data_items([text_item.data])
        elif chosen == act_paste:
            self.paste_text_clipboard_at(scene_pos)
        elif chosen == act_transform:
            self.toggle_text_transform_mode(text_item.data)
        elif chosen == act_delete:
            self.delete_text_data_items([text_item.data], ask=True)

    def clear_text_transform_modes(self, except_data=None):
        curr = self.data.get(self.idx)
        if not curr:
            return
        for d in curr.get('data', []):
            if except_data is not None and d is except_data:
                continue
            d.pop('_transform_mode', None)

    def toggle_text_transform_mode(self, data_item):
        """최종화면 텍스트 변형 모드 토글."""
        if self.cb_mode.currentIndex() != 4 or not data_item:
            return

        enabled = not bool(data_item.get('_transform_mode', False))
        self.clear_text_transform_modes(except_data=data_item)
        selected_id = data_item.get('id')

        if enabled:
            # 변형 모드는 영역 자체를 만지는 작업이다.
            # 따라서 OCR 초기 박스가 남아 있더라도 변형 진입 순간 현재 보이는
            # 실제 텍스트 bounds로 rect를 재생성하고 그 영역을 바로 띄운다.
            rect_changed = self.ensure_text_anchor_rect(
                data_item,
                record_undo=True,
                reason="텍스트 변형 영역 자동 재생성",
            )
            data_item['_transform_mode'] = True
            if rect_changed:
                self.log("🔷 텍스트 변형 영역 자동 재생성: OCR 영역 대신 현재 텍스트 bounds를 사용합니다.")
            self.log("🔷 텍스트 변형 모드 ON: 파란 테두리/핸들을 조작하세요. Alt+드래그로 이동, Ctrl+Enter 또는 배경 클릭으로 종료")
        else:
            data_item.pop('_transform_mode', None)
            self.log("🔷 텍스트 변형 모드 OFF")

        if self.cb_mode.currentIndex() == 4:
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress
            if selected_id is not None:
                self.reselect_text_items([selected_id])
        self.auto_save_project()

    def show_final_background_context_menu(self, global_pos, scene_pos):
        if self.cb_mode.currentIndex() != 4:
            return
        self.last_canvas_context_pos = scene_pos

        menu = QMenu(self)
        act_paste = menu.addAction("텍스트 붙여넣기")
        act_paste.setEnabled(bool(self.text_clipboard))
        act_add = menu.addAction("텍스트 추가")

        chosen = menu.exec(global_pos)
        if chosen == act_paste:
            self.paste_text_clipboard_at(scene_pos)
        elif chosen == act_add:
            self.set_tool("final_text")
            try:
                self.create_final_text_at(int(scene_pos.x()), int(scene_pos.y()))
            except Exception:
                pass

    def on_table_context_menu(self, pos):
        row = self.tab.rowAt(pos.y())
        if row <= 0:
            return

        if not self.tab.selectionModel().isRowSelected(row, QModelIndex()):
            self.tab.selectRow(row)

        data_item = self.row_to_text_data(row)
        if data_item is None:
            return

        menu = QMenu(self)
        act_delete = menu.addAction("텍스트행 삭제")
        chosen = menu.exec(self.tab.viewport().mapToGlobal(pos))
        if chosen == act_delete:
            self.delete_text_data_items([data_item], ask=True)

    def renumber_text_items_for_current_page(self, curr=None):
        """우측 텍스트 행의 라인넘버(ID)를 현재 순서 기준 1부터 다시 정렬한다."""
        if curr is None:
            curr = self.data.get(self.idx)
        if not curr:
            return
        for n, d in enumerate(curr.get('data', []) or [], start=1):
            d['id'] = n

    def select_all_current_text_editor_later(self):
        """QTableWidget 편집기/QLineEdit/QTextEdit가 열린 직후 전체 선택한다."""
        def _select():
            fw = QApplication.focusWidget()
            try:
                if isinstance(fw, QLineEdit):
                    fw.selectAll()
                    return
                if isinstance(fw, (QTextEdit, QPlainTextEdit)):
                    cur = fw.textCursor()
                    cur.select(QTextCursor.SelectionType.Document)
                    fw.setTextCursor(cur)
                    return
            except Exception:
                pass

        QTimer.singleShot(0, _select)
        QTimer.singleShot(30, _select)
        QTimer.singleShot(80, _select)

    def edit_table_translation_row(self, row):
        """우측 텍스트 표의 해당 행 번역문 칸을 편집 모드로 열고 전체 선택한다."""
        if not hasattr(self, "tab"):
            return False
        if row <= 0 or row >= self.tab.rowCount():
            return False

        item = self.tab.item(row, 3)
        if item is None:
            item = QTableWidgetItem("")
            self.tab.setItem(row, 3, item)

        self.tab.setFocus()
        self.tab.setCurrentCell(row, 3)
        self.tab.editItem(item)
        self.select_all_current_text_editor_later()
        return True

    def edit_selected_translation_text_f2(self):
        """F2: 선택된 텍스트 영역/텍스트 행의 번역문을 바로 수정한다."""
        # 최종화면에서 텍스트 객체가 선택되어 있으면 그 자리 편집으로 들어간다.
        if self.cb_mode.currentIndex() == 4:
            items = self.selected_text_items()
            if items:
                self.start_inline_text_edit(items[0], select_all=True)
                return True

        # 우측 표에서 선택된 행이 있으면 번역문 칸을 편집한다.
        if hasattr(self, "tab"):
            rows = sorted({idx.row() for idx in self.tab.selectedIndexes() if idx.row() > 0})
            row = rows[0] if rows else self.tab.currentRow()
            if row > 0:
                return self.edit_table_translation_row(row)

        return False

    def on_text_table_rows_reordered(self):
        """우측 텍스트 행 드래그 후 data 순서를 표 순서에 맞추고 ID를 재정렬한다."""
        if self._syncing_selection or self._table_check_lock:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return

        id_order = []
        for row in range(1, self.tab.rowCount()):
            item = self.tab.item(row, 0)
            if item:
                txt = item.text().strip()
                if txt and txt != "ALL":
                    id_order.append(txt)

        if not id_order:
            return

        old_data = curr.get('data', [])
        old_id_order = [str(d.get('id')) for d in old_data]
        if id_order == old_id_order:
            return

        # 058에서 프로젝트 스냅샷 Undo로 바꾼 뒤 탭 이동/표 갱신 렉이 커져
        # 행 순서 변경도 기존의 가벼운 page undo 방식으로 되돌린다.
        self.push_text_line_undo('텍스트 행 순서 변경')

        by_id = {str(d.get('id')): d for d in old_data}
        new_data = [by_id[i] for i in id_order if i in by_id]
        for d in old_data:
            if d not in new_data:
                new_data.append(d)

        curr['data'] = new_data
        self.renumber_text_items_for_current_page(curr)
        self.ref_tab()
        self.refresh_after_text_line_change(autosave=True)
        self.log("↕️ Text row order changed / IDs reordered" if self.ui_language == LANG_EN else "↕️ 텍스트 행 순서 변경 완료 / 번호 재정렬")

    def set_text_detail_focus(self, attr):
        widget = getattr(self, attr, None)
        if widget is None:
            return
        widget.setFocus()
        try:
            widget.selectAll()
        except Exception:
            pass

    def toggle_bold(self):
        if hasattr(self, "btn_bold"):
            self.btn_bold.toggle()

    def toggle_italic(self):
        if hasattr(self, "btn_italic"):
            self.btn_italic.toggle()

    def toggle_strike(self):
        if hasattr(self, "btn_strike"):
            self.btn_strike.toggle()

    def _safe_graphics_scene(self):
        """현재 QGraphicsScene이 살아 있으면 반환한다.

        Qt 종료/모드 전환/씬 재생성 타이밍에는 Python 래퍼는 남아 있는데
        내부 C++ QGraphicsScene이 이미 삭제된 상태가 될 수 있다. 이때 selectedItems(),
        items(), blockSignals() 같은 호출이 RuntimeError를 내므로 모든 scene 접근 전
        이 헬퍼를 통과시킨다.
        """
        view = getattr(self, "view", None)
        scene = getattr(view, "scene", None) if view is not None else None
        if scene is None:
            return None
        try:
            # C++ 객체 생존 여부를 확인하는 가장 가벼운 호출.
            scene.sceneRect()
        except RuntimeError:
            return None
        except Exception:
            return None
        return scene

    def selected_text_items(self):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return []
        scene = self._safe_graphics_scene()
        if scene is None:
            return []
        try:
            return [item for item in scene.selectedItems() if isinstance(item, TypesettingItem)]
        except RuntimeError:
            return []
        except Exception:
            return []

    def calculate_tight_text_scene_rect(self, data_item):
        """data_item의 현재 번역문/스타일이 실제로 차지하는 scene rect를 계산한다.

        OCR 원본 박스는 처음 배치용으로 유지하되, 사용자가 텍스트를 한 번 수정하면
        그 이후의 선택/변형 박스는 실제 텍스트 크기에 맞게 축소되어야 한다.
        Qt 문서 boundingRect 대신 TypesettingItem과 같은 QPainterPath 기준을 사용한다.
        """
        if not isinstance(data_item, dict):
            return None
        text = str(data_item.get('translated_text', '') or '')
        lines = text.replace('\r\n', '\n').replace('\r', '\n').split('\n')
        if not lines:
            lines = ['']

        try:
            fallback_family = self.cb_font.currentFont().family() if hasattr(self, 'cb_font') else 'Arial'
        except Exception:
            fallback_family = 'Arial'
        try:
            fallback_size = int(self.sb_font_size.value()) if hasattr(self, 'sb_font_size') else 24
        except Exception:
            fallback_size = 24

        font = QFont(str(data_item.get('font_family') or fallback_family))
        try:
            font.setPixelSize(int(data_item.get('font_size', fallback_size) or fallback_size))
        except Exception:
            font.setPixelSize(fallback_size)
        try:
            font.setBold(bool(data_item.get('bold', False)))
            font.setItalic(bool(data_item.get('italic', False)))
            letter_spacing = int(data_item.get('letter_spacing', 0) or 0)
        except Exception:
            pass

        try:
            line_spacing_pct = max(50, min(300, int(data_item.get('line_spacing', 100) or 100)))
        except Exception:
            line_spacing_pct = 100
        try:
            char_width_pct = max(10, min(300, int(data_item.get('char_width', 100) or 100)))
        except Exception:
            char_width_pct = 100
        try:
            char_height_pct = max(10, min(300, int(data_item.get('char_height', 100) or 100)))
        except Exception:
            char_height_pct = 100

        align = (data_item.get('align') or getattr(self, 'default_align', 'center') or 'center').lower()
        if align not in ('left', 'center', 'right'):
            align = 'center'

        fm = QFontMetrics(font)
        line_height = max(1, int(fm.lineSpacing() * (line_spacing_pct / 100.0)))
        path, _line_rects = build_typesetting_text_path(lines, font, align, line_height, letter_spacing)

        if char_width_pct != 100 or char_height_pct != 100:
            tr = QTransform()
            tr.scale(char_width_pct / 100.0, char_height_pct / 100.0)
            path = tr.map(path)

        path_rect = path.boundingRect()
        if path_rect.isNull() or path_rect.width() <= 0 or path_rect.height() <= 0:
            path_rect = QRectF(0, 0, 1, max(1, fm.height()))

        rect = list(data_item.get('rect') or [0, 0, 1, 1])
        while len(rect) < 4:
            rect.append(1)
        x_off = float(data_item.get('x_off', 0) or 0)
        y_off = float(data_item.get('y_off', 0) or 0)
        rect_x = float(rect[0])
        rect_y = float(rect[1])
        rect_w = max(1.0, float(rect[2]))
        rect_h = max(1.0, float(rect[3]))
        text_w = max(1.0, float(path_rect.width()))
        text_h = max(1.0, float(path_rect.height()))

        if align == 'left':
            anchor_x = rect_x + x_off
            left = anchor_x
        elif align == 'right':
            anchor_x = rect_x + x_off + rect_w
            left = anchor_x - text_w
        else:
            anchor_x = rect_x + x_off + rect_w / 2.0
            left = anchor_x - text_w / 2.0

        # v1.6.3+: 텍스트는 영역의 세로 중심에 배치된다.
        anchor_y = rect_y + y_off + rect_h / 2.0
        top = anchor_y - text_h / 2.0

        return QRectF(left, top, text_w, text_h)

    def shrink_text_rect_to_content(self, data_item):
        """텍스트 수정 후 작업/변형 박스를 실제 텍스트 크기로 줄인다."""
        return self.ensure_text_anchor_rect(data_item, record_undo=False)

    def ensure_text_anchor_rect(self, data_item, record_undo=False, reason="텍스트 영역 자동 재생성"):
        """현재 보이는 실제 텍스트 bounds를 새 텍스트 영역으로 확정한다.

        초기 OCR 영역은 최초 배치용 기준일 뿐이다. 텍스트 직접 수정 또는
        텍스트 변형 모드 진입 시점에는 현재 화면에 보이는 실제 글자 영역을
        기준으로 rect를 다시 만들고, 이후 선택/변형 박스가 이 영역을 보게 한다.
        """
        if not isinstance(data_item, dict):
            return False
        rect = self.calculate_tight_text_scene_rect(data_item)
        if rect is None:
            return False

        new_rect = [
            int(round(rect.x())),
            int(round(rect.y())),
            max(1, int(round(rect.width()))),
            max(1, int(round(rect.height()))),
        ]
        old_rect = list(data_item.get('rect') or [])
        while len(old_rect) < 4:
            old_rect.append(0)
        try:
            old_rect4 = [int(round(float(v))) for v in old_rect[:4]]
        except Exception:
            old_rect4 = old_rect[:4]
        old_x = int(round(float(data_item.get('x_off', 0) or 0)))
        old_y = int(round(float(data_item.get('y_off', 0) or 0)))
        already_text_anchor = bool(data_item.get('manual_text_rect')) or str(data_item.get('text_anchor_mode') or '').lower() == 'text'
        changed = (
            old_rect4 != new_rect
            or old_x != 0
            or old_y != 0
            or not already_text_anchor
        )
        if not changed:
            return False

        if record_undo:
            try:
                self.push_page_text_undo(reason)
            except Exception:
                pass

        data_item['rect'] = new_rect
        data_item['x_off'] = 0
        data_item['y_off'] = 0
        data_item['manual_text_rect'] = True
        data_item['text_anchor_mode'] = 'text'
        return True

    def reset_text_rects_current(self):
        """현재 페이지의 모든 텍스트 영역을 현재 보이는 텍스트 bounds 기준으로 재생성한다."""
        if not self.paths or self.idx not in self.data:
            self.log("⚠️ 영역을 재설정할 현재 페이지가 없습니다.")
            return

        # 최종화면에서 드래그 이동한 좌표가 아직 data에 완전히 박히기 전일 수 있으므로
        # 먼저 현재 UI 상태를 data에 동기화한 뒤, 그 상태를 Undo 기준으로 저장한다.
        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass

        curr = self.data.get(self.idx) or {}
        items = [d for d in (curr.get('data', []) or []) if isinstance(d, dict)]
        if not items:
            self.log("⚠️ 영역을 재설정할 텍스트가 없습니다.")
            return

        undo_rec = self.make_project_undo_record("현재 텍스트 기준 영역 재설정")
        changed = 0
        for d in items:
            try:
                if self.ensure_text_anchor_rect(d, record_undo=False, reason="현재 텍스트 기준 영역 재설정"):
                    changed += 1
            except Exception:
                continue

        if changed <= 0:
            self.log("↩️ 현재 텍스트 기준 영역 재설정: 변경된 영역이 없습니다.")
            return

        self.append_project_undo_record(undo_rec)
        self.auto_save_project()
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.log(f"📐 현재 텍스트 기준 영역 재설정 완료: {changed}개")

    def reset_text_rects_batch(self):
        """전체 페이지의 모든 텍스트 영역을 현재 텍스트 bounds 기준으로 일괄 재생성한다."""
        if not self.paths or not self.data:
            self.log("⚠️ 영역을 재설정할 프로젝트가 없습니다.")
            return

        try:
            self.commit_current_page_ui_to_data(include_mask=False)
        except Exception:
            pass

        total_candidates = 0
        try:
            for page_data in (self.data or {}).values():
                if isinstance(page_data, dict):
                    total_candidates += sum(1 for d in (page_data.get('data', []) or []) if isinstance(d, dict))
        except Exception:
            total_candidates = 0
        if total_candidates <= 0:
            self.log("⚠️ 영역을 재설정할 텍스트가 없습니다.")
            return

        msg = f"전체 {len(self.paths)}페이지의 텍스트 영역을 현재 텍스트 기준으로 다시 만들까요?\n총 {total_candidates}개 텍스트가 대상입니다."
        if not self.confirm_batch_operation("일괄 텍스트 기준 영역 재설정", msg):
            self.log("↩️ 일괄 텍스트 기준 영역 재설정 취소")
            return

        undo_rec = self.make_project_undo_record("일괄 텍스트 기준 영역 재설정", full_project=True)
        changed_pages = 0
        changed_total = 0
        old_batch = getattr(self, "is_batch_running", False)
        self.is_batch_running = True
        try:
            for page_idx in sorted((self.data or {}).keys()):
                page_data = self.data.get(page_idx)
                if not isinstance(page_data, dict):
                    continue
                page_changed = 0
                for d in (page_data.get('data', []) or []):
                    if not isinstance(d, dict):
                        continue
                    try:
                        if self.ensure_text_anchor_rect(d, record_undo=False, reason="일괄 텍스트 기준 영역 재설정"):
                            page_changed += 1
                    except Exception:
                        continue
                if page_changed:
                    changed_pages += 1
                    changed_total += page_changed
        finally:
            self.is_batch_running = old_batch

        if changed_total <= 0:
            self.log("↩️ 일괄 텍스트 기준 영역 재설정: 변경된 영역이 없습니다.")
            return

        self.append_project_undo_record(undo_rec)
        self.auto_save_project()
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.log(f"📐 일괄 텍스트 기준 영역 재설정 완료: {changed_pages}페이지 / {changed_total}개")

    def start_inline_text_edit(self, text_item, select_all=False):
        """최종 화면 텍스트를 더블클릭/F2 했을 때 그 자리에서 직접 편집한다."""
        if self.cb_mode.currentIndex() != 4:
            return

        if self.inline_text_editor is not None:
            self.finish_inline_text_edit(commit=True, refresh=False)

        if text_item is None:
            return

        self.inline_text_target = text_item
        text_item.setSelected(True)

        # 마지막 식자 단계의 직접 수정이므로, 기존 OCR 박스가 아니라 현재 실제 텍스트를 기준으로 편집을 시작한다.
        if hasattr(text_item, 'text_content_scene_rect'):
            scene_rect = text_item.text_content_scene_rect()
        else:
            local_rect = text_item.text_area_rect()
            scene_rect = text_item.mapToScene(local_rect).boundingRect()

        editor = InlineTextEditItem(self, text_item, scene_rect)
        self.inline_text_editor = editor

        text_item.setVisible(False)
        self.view.scene.addItem(editor)
        editor.setFocus(Qt.FocusReason.MouseFocusReason)

        cursor = editor.textCursor()
        cursor.clearSelection()
        if select_all:
            cursor.select(QTextCursor.SelectionType.Document)
        else:
            cursor.movePosition(QTextCursor.MoveOperation.End)
        editor.setTextCursor(cursor)

        self.log(f"✏️ 텍스트 직접 편집 시작 (ID: {text_item.data.get('id')})")

    def finish_inline_text_edit(self, commit=True, refresh=True):
        editor = self.inline_text_editor
        target = self.inline_text_target
        if editor is None:
            return

        is_closing = bool(getattr(self, "_app_is_closing", False))
        try:
            editor._closing = True
        except Exception:
            pass

        # Qt 종료/탭 재구성 타이밍에 QGraphicsTextItem의 C++ 객체가 먼저 삭제될 수 있다.
        # 이 상태에서 toPlainText()/scene()/removeItem() 등을 호출하면
        # "wrapped C/C++ object ... has been deleted"가 나므로 조용히 포인터만 정리한다.
        try:
            _ = editor.toPlainText()
        except RuntimeError:
            self.inline_text_editor = None
            self.inline_text_target = None
            return
        except Exception:
            pass

        selected_id = target.data.get('id') if target is not None else None
        pending_new = bool(target is not None and target.data.get('pending_new_text'))

        changed = False
        added_new = False
        canceled_new = False

        if commit and target is not None:
            try:
                new_text = editor.toPlainText()
            except RuntimeError:
                self.inline_text_editor = None
                self.inline_text_target = None
                return
            changed = (new_text != getattr(editor, 'original_text', ''))

            if pending_new and not str(new_text or '').strip():
                canceled_new = True
                changed = False
                self.log(f"↩️ 새 텍스트 입력 취소 (ID: {target.data.get('id')})")
            elif changed or pending_new:
                self.push_page_text_undo('텍스트 직접 수정' if not pending_new else '새 텍스트 추가')
                target.data['translated_text'] = new_text
                target.data.pop('force_show', None)
                target.data.pop('pending_new_text', None)

                # 직접 수정한 경우에는 기존 OCR 박스가 아니라 현재 편집 텍스트 자체를 기준으로
                # 텍스트 영역을 다시 잡는다. QGraphicsTextItem의 boundingRect()가 아래쪽에
                # 여분 한 줄을 남기는 경우를 피하기 위해 adjusted_scene_rect()의 타이트 계산을 쓴다.
                try:
                    edit_rect = editor.adjusted_scene_rect()
                    if edit_rect.width() > 1 and edit_rect.height() > 1:
                        target.data['rect'] = [
                            int(round(edit_rect.x())),
                            int(round(edit_rect.y())),
                            max(1, int(round(edit_rect.width()))),
                            max(1, int(round(edit_rect.height()))),
                        ]
                        target.data['x_off'] = 0
                        target.data['y_off'] = 0
                        target.data['manual_text_rect'] = True
                        target.data['text_anchor_mode'] = 'text'
                    else:
                        self.shrink_text_rect_to_content(target.data)
                except Exception:
                    try:
                        self.shrink_text_rect_to_content(target.data)
                    except Exception:
                        pass

                if pending_new:
                    curr = self.data.get(self.idx)
                    if curr is not None and target.data not in curr.setdefault('data', []):
                        curr['data'].append(target.data)
                        added_new = True
                    changed = True
                else:
                    target_id = str(target.data.get('id'))
                    self.tab.blockSignals(True)
                    try:
                        for row in range(1, self.tab.rowCount()):
                            id_item = self.tab.item(row, 0)
                            if id_item and id_item.text().strip() == target_id:
                                self.tab.setItem(row, 3, QTableWidgetItem(new_text))
                                break
                    finally:
                        self.tab.blockSignals(False)

            if changed:
                self.tab.resizeRowsToContents()
                self.auto_save_project()
                if added_new:
                    self.log(f"✅ 새 텍스트 추가 완료 (ID: {target.data.get('id')})")
                else:
                    self.log(f"✅ 텍스트 직접 수정 완료 (ID: {target.data.get('id')})")
            elif not canceled_new:
                self.log(f"↩️ 텍스트 직접 수정 변화 없음 (ID: {target.data.get('id')})")
        elif target is not None:
            if pending_new:
                canceled_new = True
                self.log(f"↩️ 새 텍스트 입력 취소 (ID: {target.data.get('id')})")
            else:
                self.log(f"↩️ 텍스트 직접 수정 취소 (ID: {target.data.get('id')})")

        try:
            if editor.scene() is not None:
                editor.scene().removeItem(editor)
        except Exception:
            pass

        if target is not None:
            try:
                if canceled_new and target.scene() is not None:
                    target.scene().removeItem(target)
                else:
                    target.setVisible(True)
            except Exception:
                pass

        self.inline_text_editor = None
        self.inline_text_target = None

        if (not is_closing) and commit and (changed or added_new) and refresh and self.cb_mode.currentIndex() == 4:
            self.ref_tab()
            self.mode_chg(4)
            if selected_id is not None and not canceled_new:
                self.reselect_text_items([selected_id])
        elif (not is_closing) and selected_id is not None and not canceled_new:
            self.reselect_text_items([selected_id])


    def on_scene_selection_changed(self):
        # 프로그램 종료/씬 재생성 중 selectionChanged가 뒤늦게 들어오면
        # 삭제된 QGraphicsScene에 접근하지 않고 조용히 무시한다.
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        if self._safe_graphics_scene() is None:
            return

        # 개별 텍스트 스타일 작업은 우측 패널의 "선택 텍스트 스타일"에서만 한다.
        # 예전처럼 이미지 위쪽에 별도 작업바가 뜨지 않게 항상 숨긴다.
        if hasattr(self, 'final_edit_bar'):
            self.final_edit_bar.hide()

        active_transform = self.current_transform_data_item()
        if active_transform is not None:
            active_id = active_transform.get('id')
            items = self.selected_text_items()
            if not any(item.data.get('id') == active_id for item in items):
                self.reselect_text_items([active_id])
                items = self.selected_text_items()
        else:
            items = self.selected_text_items()
        ids = [item.data.get('id') for item in items]
        self.select_table_rows_by_ids(ids)

        if not items or self._style_signal_lock:
            return

        d = items[0].data
        self._style_signal_lock = True
        try:
            self.cb_font.setCurrentFont(QFont(d.get('font_family') or self.cb_font.currentFont().family()))
            self.sb_font_size.setValue(int(d.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()))
            self.sb_strk.setValue(int(d.get('stroke_width', self.sb_strk.value()) or 0))
            self.default_text_color = d.get('text_color') or self.default_text_color
            self.default_stroke_color = d.get('stroke_color') or self.default_stroke_color
            self.default_align = d.get('align') or self.default_align
            if hasattr(self, "sb_line_spacing"):
                self.sb_line_spacing.setValue(int(d.get('line_spacing', self.default_line_spacing) or self.default_line_spacing))
            if hasattr(self, "sb_letter_spacing"):
                self.sb_letter_spacing.setValue(int(d.get('letter_spacing', self.default_letter_spacing) or self.default_letter_spacing))
            if hasattr(self, "sb_char_width"):
                self.sb_char_width.setValue(int(d.get('char_width', self.default_char_width) or self.default_char_width))
            if hasattr(self, "sb_char_height"):
                self.sb_char_height.setValue(int(d.get('char_height', self.default_char_height) or self.default_char_height))
            if hasattr(self, "btn_bold"):
                self.btn_bold.setChecked(bool(d.get('bold', False)))
            if hasattr(self, "btn_italic"):
                self.btn_italic.setChecked(bool(d.get('italic', False)))
            if hasattr(self, "btn_strike"):
                self.btn_strike.setChecked(bool(d.get('strike', False)))
            self.update_color_button_styles()
            self.update_item_preset_combo_for_selected_texts()
        finally:
            self._style_signal_lock = False

    def on_final_item_style_changed(self, *args):
        if self._style_signal_lock:
            return
        if not self.selected_text_items():
            return
        self.apply_style_to_selected(
            font_family=self.final_item_font.currentFont().family(),
            font_size=self.final_item_size.value(),
            stroke_width=self.final_item_stroke.value(),
        )

    def apply_style_to_selected(self, keep_selection=True, preset_name=None, record_undo=True, **style):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        items = self.selected_text_items()
        if not items:
            return
        selected_ids = [item.data.get('id') for item in items]
        if record_undo:
            self.push_page_text_undo('텍스트 스타일 변경')
        for item in items:
            for key, value in style.items():
                item.data[key] = value
            if preset_name:
                item.data['item_text_preset_name'] = str(preset_name)
            else:
                item.data.pop('item_text_preset_name', None)
            # 이미 직접 수정된 텍스트는 OCR 박스를 버린 상태이므로,
            # 스타일 변경 후에도 실제 글자 bounds를 기준으로 텍스트 영역을 다시 만든다.
            try:
                if bool(item.data.get('manual_text_rect')) or str(item.data.get('text_anchor_mode') or '').lower() == 'text':
                    self.shrink_text_rect_to_content(item.data)
            except Exception:
                pass
        self.auto_save_project()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            if keep_selection:
                self.reselect_text_items(selected_ids)
            self.update_item_preset_combo_for_selected_texts()

    def reselect_text_items(self, selected_ids):
        ids = set(selected_ids or [])
        if not ids or getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        scene = self._safe_graphics_scene()
        if scene is None:
            return
        try:
            for item in scene.items():
                if isinstance(item, TypesettingItem) and item.data.get('id') in ids:
                    item.setSelected(True)
        except RuntimeError:
            return
        except Exception:
            return

    def select_table_rows_by_ids(self, selected_ids):
        if not hasattr(self, 'tab') or self._syncing_selection:
            return
        ids = {str(x) for x in (selected_ids or []) if x is not None}
        self._syncing_selection = True
        try:
            model = self.tab.model()
            sm = self.tab.selectionModel()
            if not sm:
                return
            sm.clearSelection()
            first_row = None
            for row in range(1, self.tab.rowCount()):
                id_item = self.tab.item(row, 0)
                if id_item and id_item.text().strip() in ids:
                    top = model.index(row, 0)
                    bottom = model.index(row, self.tab.columnCount() - 1)
                    sel = QItemSelection(top, bottom)
                    sm.select(sel, QItemSelectionModel.SelectionFlag.Select | QItemSelectionModel.SelectionFlag.Rows)
                    if first_row is None:
                        first_row = row
            if first_row is not None:
                # setCurrentCell()은 환경에 따라 선택을 마지막 한 줄로 줄일 수 있어서 사용하지 않는다.
                # 현재 인덱스만 조용히 옮기고 다중 선택 상태는 유지한다.
                sm.setCurrentIndex(model.index(first_row, 0), QItemSelectionModel.SelectionFlag.NoUpdate)
        finally:
            self._syncing_selection = False

    def selected_table_text_ids(self):
        if not hasattr(self, 'tab'):
            return []
        rows = sorted({idx.row() for idx in self.tab.selectedIndexes() if idx.row() > 0})
        ids = []
        for row in rows:
            item = self.tab.item(row, 0)
            if item:
                ids.append(item.text().strip())
        return ids

    def on_table_selection_changed(self):
        if self._syncing_selection:
            return
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        if self.cb_mode.currentIndex() != 4:
            return
        scene = self._safe_graphics_scene()
        if scene is None:
            return
        active_transform = self.current_transform_data_item()
        if active_transform is not None:
            self.reselect_text_items([active_transform.get('id')])
            return
        ids = set(self.selected_table_text_ids())
        self._syncing_selection = True
        try:
            scene.blockSignals(True)
            try:
                for item in scene.items():
                    if isinstance(item, TypesettingItem):
                        item.setSelected(str(item.data.get('id')) in ids)
            finally:
                scene.blockSignals(False)
        except RuntimeError:
            pass
        except Exception:
            pass
        finally:
            self._syncing_selection = False
        # 우측 스타일 칸은 첫 선택 항목 기준으로 맞춘다.
        self.on_scene_selection_changed()

    def on_global_text_style_changed(self, *args):
        if self._style_signal_lock:
            return
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        self.set_preset_combo_to_last()
        self.set_item_preset_combo_custom()
        self.save_last_text_preset("__last__")
        selected = self.selected_text_items()
        if selected and self.cb_mode.currentIndex() == 4:
            self.apply_style_to_selected(
                font_family=self.cb_font.currentFont().family(),
                font_size=self.sb_font_size.value(),
                stroke_width=self.sb_strk.value(),
                text_color=self.default_text_color,
                stroke_color=self.default_stroke_color,
                align=self.default_align,
                line_spacing=self.sb_line_spacing.value(),
                letter_spacing=self.sb_letter_spacing.value(),
                char_width=self.sb_char_width.value(),
                char_height=self.sb_char_height.value(),
                bold=self.btn_bold.isChecked(),
                italic=self.btn_italic.isChecked(),
                strike=self.btn_strike.isChecked(),
            )

    def set_global_align(self, align):
        if getattr(self, "_app_is_closing", False) or getattr(self, "_closing_confirmed", False):
            return
        self.default_align = align
        self.set_preset_combo_to_last()
        self.set_item_preset_combo_custom()
        self.save_last_text_preset("__last__")
        selected = self.selected_text_items()
        if selected and self.cb_mode.currentIndex() == 4:
            self.apply_style_to_selected(align=align)

    def pick_color(self, target):
        if target == "final_paint":
            current = self.final_paint_color
        else:
            current = self.default_text_color if "text" in target else self.default_stroke_color
        color = QColorDialog.getColor(QColor(current), self, "색상 선택")
        if not color.isValid():
            return
        hex_color = color.name(QColor.NameFormat.HexRgb).upper()
        if target == "global_text":
            self.default_text_color = hex_color
            self.update_color_button_styles()
            self.on_global_text_style_changed()
        elif target == "global_stroke":
            self.default_stroke_color = hex_color
            self.update_color_button_styles()
            self.on_global_text_style_changed()
        elif target == "item_text":
            self.apply_style_to_selected(text_color=hex_color)
        elif target == "item_stroke":
            self.apply_style_to_selected(stroke_color=hex_color)
        elif target == "final_paint":
            self.final_paint_color = hex_color
            self.update_color_button_styles()
            self.log(f"🎨 최종 페인팅 색상: {hex_color}")

    def on_show_final_text_toggled(self, checked):
        old_state = bool(getattr(self, "_last_show_final_text_checked", not bool(checked)))
        new_state = bool(checked)
        if (
            old_state != new_state
            and not getattr(self, "_project_undo_restore_lock", False)
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
        ):
            try:
                rec = self.make_project_undo_record("텍스트 표시 ON/OFF")
                rec.setdefault("ui_state", self.current_project_ui_state())
                rec["ui_state"]["show_final_text"] = old_state
                self.append_project_undo_record(rec)
            except Exception:
                pass
        self._last_show_final_text_checked = new_state
        if self.cb_mode.currentIndex() == 4:
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress
        self.auto_save_project()

    def active_mask_key(self, mode_idx=None):
        mode_idx = self.cb_mode.currentIndex() if mode_idx is None else mode_idx
        # 텍스트 마스크는 분석/재분석용이라 토글을 쓰지 않는다.
        # 토글은 페인팅 마스크에서만 ON(분석 기반) / OFF(수동 마스크)로 분리한다.
        if mode_idx == 2:
            return 'mask_merge'
        if mode_idx == 3:
            return 'mask_inpaint' if self.mask_toggle_enabled else 'mask_inpaint_off'
        return None

    def get_active_mask(self, curr, mode_idx=None):
        key = self.active_mask_key(mode_idx)
        if not key or not curr:
            return None
        return curr.get(key)

    def set_active_mask(self, curr, mask, mode_idx=None):
        key = self.active_mask_key(mode_idx)
        if key and curr is not None:
            curr[key] = mask.copy() if isinstance(mask, np.ndarray) else mask

    def on_mask_toggle_changed(self, checked):
        curr = self.data.get(self.idx)
        old_state = self.mask_toggle_enabled
        mode = self.cb_mode.currentIndex()
        if (
            mode == 3
            and not getattr(self, "_project_undo_restore_lock", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
        ):
            try:
                self.commit_current_page_ui_to_data(include_mask=True)
                self.push_project_undo("마스크 ON/OFF")
            except Exception:
                pass

        # 토글은 페인팅 마스크 전용이다.
        # 텍스트 마스크에서는 분석 마스크(mask_merge)만 쓰므로 ON/OFF 분리 저장을 하지 않는다.
        if curr is not None and mode == 3:
            # 토글을 바꾸기 직전, 화면에 떠 있는 현재 페인팅 마스크를 이전 토글 슬롯에 먼저 저장한다.
            m = self.view.get_mask_np()
            if m is not None:
                curr['mask_inpaint' if old_state else 'mask_inpaint_off'] = m.copy()

        self.mask_toggle_enabled = bool(checked)
        if hasattr(self, "act_mask_toggle"):
            self.act_mask_toggle.setText("☑" if checked else "☐")
        if curr is not None:
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
        state = "ON" if checked else "OFF"
        self.log(f"🎚️ 페인팅 마스크 토글: {state}")

        if mode == 3:
            # 토글은 탭 이동이 아니라 같은 페인팅 마스크 탭 안에서
            # mask_inpaint / mask_inpaint_off 슬롯만 바꾸는 작업이다.
            # 따라서 mode_chg(3)로 화면을 다시 그릴 때:
            # 1) 탭 변경 Undo를 만들지 않고
            # 2) 이전 화면 마스크를 새 토글 슬롯에 덮어쓰지 않도록 막는다.
            old_suppress_mode_undo = getattr(self, "_suppress_mode_undo", False)
            old_skip_mode_mask_commit = getattr(self, "_skip_mode_mask_commit", False)
            old_mask_toggle_refreshing = getattr(self, "_mask_toggle_refreshing", False)
            self._suppress_mode_undo = True
            self._skip_mode_mask_commit = True
            self._mask_toggle_refreshing = True
            try:
                self.mode_chg(3)
            finally:
                self._suppress_mode_undo = old_suppress_mode_undo
                self._skip_mode_mask_commit = old_skip_mode_mask_commit
                self._mask_toggle_refreshing = old_mask_toggle_refreshing
        self.auto_save_project()

    def set_mask_toggle_safely(self, checked):
        self.mask_toggle_enabled = bool(checked)
        if hasattr(self, 'cb_mask_toggle'):
            self.cb_mask_toggle.blockSignals(True)
            try:
                self.cb_mask_toggle.setChecked(bool(checked))
                if hasattr(self, "act_mask_toggle"):
                    self.act_mask_toggle.setText("☑" if checked else "☐")
            finally:
                self.cb_mask_toggle.blockSignals(False)

    def get_page_stem(self, page_idx):
        """
        TXT 추출/일괄 번역문 불러오기용 파일명 기준.

        무조건 현재 프로젝트에서 실제로 불러온 원본 이미지 파일명 기준으로 맞춘다.
        예: images/0001.webp -> Txt/0001.txt
            images/0002.png  -> Txt/0002.txt

        예전 original_name 값이 001, sample 같은 이름으로 남아 있으면
        일괄 불러오기 매칭이 깨질 수 있으므로 여기서는 사용하지 않는다.
        """
        try:
            return Path(os.path.basename(self.paths[page_idx])).stem
        except Exception:
            curr = self.data.get(page_idx, {})
            name = curr.get('original_name') or f"{page_idx + 1:04d}"
            return Path(str(name)).stem

    def get_output_root(self):
        if self.project_dir:
            return self.project_dir
        if self.paths:
            return os.path.dirname(os.path.abspath(self.paths[self.idx]))
        return os.getcwd()

    def ensure_subdir(self, name):
        root = self.get_output_root()
        path = os.path.join(root, name)
        os.makedirs(path, exist_ok=True)
        return path

    def choose_text_extract_mode(self):
        ko_items = ["원문만", "번역문만", "원문+번역문"]
        display_items = [self.tr_ui(x) for x in ko_items]
        value, ok = QInputDialog.getItem(
            self,
            self.tr_ui("지문 추출"),
            self.tr_ui("추출할 내용:"),
            display_items,
            0,
            False
        )
        if not ok:
            return None
        try:
            idx = display_items.index(value)
            return ko_items[idx]
        except ValueError:
            return value

    def build_text_export_content(self, page_idx, mode):
        curr = self.data.get(page_idx, {})
        blocks = []
        for i, item in enumerate(curr.get('data', []), 1):
            text_id = str(item.get('id', i))
            original = str(item.get('text', '') or '')
            translated = str(item.get('translated_text', '') or '')
            marker = f"[{text_id}]"
            if mode == "원문만":
                blocks.append(f"{marker}\n\n{original}")
            elif mode == "번역문만":
                blocks.append(f"{marker}\n\n{translated}")
            else:
                blocks.append(f"{marker}\n\n{original}\n\n{translated}")
        return "\n\n".join(blocks).rstrip() + "\n"

    def extract_text_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        mode = self.choose_text_extract_mode()
        if not mode:
            return
        txt_dir = self.ensure_subdir("Txt")
        out_path = os.path.join(txt_dir, f"{self.get_page_stem(self.idx)}.txt")
        with open(out_path, "w", encoding="utf-8") as f:
            f.write(self.build_text_export_content(self.idx, mode))
        self.log((f"📄 Extract text complete: {out_path}" if self.ui_language == LANG_EN else f"📄 지문 추출 완료: {out_path}"))
        self.auto_save_project()

    def extract_text_batch(self):
        if not self.paths:
            return
        if getattr(self, "ui_language", LANG_KO) == LANG_EN:
            msg = f"Create text extraction TXT files for total {len(self.paths)} page(s)?"
        else:
            msg = f"지문 추출 TXT를 총 {len(self.paths)}페이지 기준으로 생성합니다."
        if not self.confirm_batch_operation("일괄 지문 추출", msg):
            self.log("↩️ Batch extract text canceled" if self.ui_language == LANG_EN else "↩️ 일괄 지문 추출 취소")
            return
        self.commit_current_page_ui_to_data()
        mode = self.choose_text_extract_mode()
        if not mode:
            return
        txt_dir = self.ensure_subdir("Txt")
        count = 0
        for i in range(len(self.paths)):
            if i not in self.data or not self.data[i].get('data'):
                continue
            out_path = os.path.join(txt_dir, f"{self.get_page_stem(i)}.txt")
            with open(out_path, "w", encoding="utf-8") as f:
                f.write(self.build_text_export_content(i, mode))
            count += 1
        self.log((f"📄 Batch text extraction complete: {count} items / {txt_dir}" if self.ui_language == LANG_EN else f"📄 일괄 지문 추출 완료: {count}개 / {txt_dir}"))
        self.auto_save_project()

    def parse_translation_txt(self, path, valid_ids):
        valid = {str(x) for x in valid_ids}

        def marker_to_id(token):
            token = str(token or "").strip()
            if len(token) >= 3 and token.startswith("[") and token.endswith("]"):
                inner = token[1:-1].strip()
                if inner.isdigit() and inner in valid:
                    return inner
            return None

        with open(path, "r", encoding="utf-8-sig") as f:
            lines = f.read().splitlines()

        result = {}
        i = 0
        while i < len(lines):
            text_id = marker_to_id(lines[i])
            if text_id:
                i += 1
                buf = []
                while i < len(lines):
                    # 다음 번호는 [1]처럼 대괄호 안의 숫자이고,
                    # 현재 페이지에 실제 존재하는 텍스트 번호일 때만 인정한다.
                    # 그래서 1131313, 421 같은 숫자 번역문은 안전하게 본문으로 들어간다.
                    if marker_to_id(lines[i]):
                        break
                    if lines[i].strip():
                        buf.append(lines[i].rstrip())
                    i += 1

                if buf:
                    result[text_id] = "\n".join(buf).strip()
                continue

            i += 1

        return result

    def apply_translation_map_to_page(self, page_idx, trans_map):
        curr = self.data.get(page_idx)
        if not curr:
            return 0
        count = 0
        for i, item in enumerate(curr.get('data', []), 1):
            text_id = str(item.get('id', i))
            if text_id in trans_map:
                new_text = str(trans_map[text_id] or '')
                old_text = str(item.get('translated_text', '') or '')
                if new_text != old_text:
                    item['translated_text'] = new_text
                    try:
                        self.shrink_text_rect_to_content(item)
                    except Exception:
                        pass
                    count += 1
        return count

    def find_translation_txt_in_folder(self, folder, page_stem):
        """일괄 번역문 불러오기용 TXT 탐색.

        기본 규칙은 원본 이미지 파일명과 같은 TXT 파일이다.
        Windows에서 사용하기 쉽게 대소문자 차이는 무시하고,
        선택한 폴더 바로 아래를 먼저 찾은 뒤 없으면 하위 폴더까지 한 번 더 찾는다.
        """
        if not folder or not page_stem:
            return None
        root = Path(folder)
        if not root.exists() or not root.is_dir():
            return None
        target = f"{page_stem}.txt".casefold()

        try:
            for child in root.iterdir():
                if child.is_file() and child.name.casefold() == target:
                    return str(child)
        except Exception:
            pass

        try:
            for child in root.rglob("*.txt"):
                if child.is_file() and child.name.casefold() == target:
                    return str(child)
        except Exception:
            pass
        return None

    def import_translation_current(self):
        if not self.paths or self.idx not in self.data:
            return
        curr = self.data[self.idx]
        valid_ids = [str(x.get('id', i + 1)) for i, x in enumerate(curr.get('data', []))]
        if not valid_ids:
            self.log("⚠️ 불러올 텍스트 번호가 없습니다.")
            return
        path, _ = QFileDialog.getOpenFileName(self, self.tr_ui("번역문 TXT 불러오기"), self.ensure_subdir("Txt"), "Text (*.txt)")
        if not path:
            return
        trans_map = self.parse_translation_txt(path, valid_ids)
        if not trans_map:
            QMessageBox.warning(self, self.tr_ui("불러오기 실패"), self.tr_ui("현재 페이지 텍스트 번호와 맞는 번역문을 찾지 못했습니다."))
            return
        undo_rec = self.make_project_undo_record("번역문 불러오기")
        count = self.apply_translation_map_to_page(self.idx, trans_map)
        if count:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.log(f"📥 번역문 불러오기 완료: {count}개")
        self.auto_save_project()

    def import_translation_batch(self):
        if not self.paths:
            return
        start_dir = self.ensure_subdir("Txt")
        folder = QFileDialog.getExistingDirectory(self, self.tr_ui("일괄 번역문 TXT 폴더 선택"), start_dir)
        if not folder:
            return
        if not self.confirm_batch_operation("일괄 번역문 불러오기", f"선택한 폴더의 TXT 번역문을 {len(self.paths)}페이지에 적용합니다."):
            self.log("↩️ 일괄 번역문 불러오기 취소")
            return
        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("일괄 번역문 불러오기", full_project=True)
        total_pages = 0
        total_items = 0
        missing = 0
        for i in range(len(self.paths)):
            curr = self.data.get(i)
            if not curr or not curr.get('data'):
                continue
            txt_path = self.find_translation_txt_in_folder(folder, self.get_page_stem(i))
            if not txt_path:
                missing += 1
                continue
            valid_ids = [str(x.get('id', n + 1)) for n, x in enumerate(curr.get('data', []))]
            trans_map = self.parse_translation_txt(txt_path, valid_ids)
            if not trans_map:
                continue
            count = self.apply_translation_map_to_page(i, trans_map)
            if count:
                total_pages += 1
                total_items += count
        if total_items:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        if total_pages == 0:
            QMessageBox.warning(
                self,
                self.tr_ui("일괄 불러오기 실패"),
                self.tr_msg("선택한 폴더에서 원본 이미지 파일명과 같은 TXT 파일을 찾지 못했거나, 맞는 텍스트 번호를 찾지 못했습니다.\n"
                "예: sample.jpg 페이지라면 sample.txt 파일이 필요합니다."),
            )
        self.log(f"📥 일괄 번역문 불러오기 완료: {total_pages}페이지 / {total_items}개 / TXT 없음 {missing}개")
        self.auto_save_project()

    def clear_translation_current(self):
        """현재 페이지의 번역문 칸을 모두 비운다."""
        if not self.paths or self.idx not in self.data:
            return

        self.commit_current_page_ui_to_data()
        curr = self.data.get(self.idx)
        if not curr or not curr.get('data'):
            self.log("⚠️ 지울 번역문이 없습니다.")
            return

        undo_rec = self.make_project_undo_record("번역문 내용 지우기")
        count = 0
        for item in curr.get('data', []):
            if str(item.get('translated_text', '') or ''):
                item['translated_text'] = ''
                try:
                    self.shrink_text_rect_to_content(item)
                except Exception:
                    pass
                count += 1

        if count:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🧹 번역문 내용 지우기 완료: {count}개")

    def clear_translation_batch(self):
        """전체 페이지의 번역문 칸을 모두 비운다."""
        if not self.paths:
            return

        if not self.confirm_batch_operation("일괄 번역문 내용 지우기", f"전체 {len(self.paths)}페이지의 번역문 내용을 지웁니다."):
            self.log("↩️ 일괄 번역문 내용 지우기 취소")
            return

        self.commit_current_page_ui_to_data()
        undo_rec = self.make_project_undo_record("일괄 번역문 내용 지우기", full_project=True)

        total_pages = 0
        total_items = 0

        for page_idx in range(len(self.paths)):
            curr = self.data.get(page_idx)
            if not curr or not curr.get('data'):
                continue

            page_count = 0
            for item in curr.get('data', []):
                if str(item.get('translated_text', '') or ''):
                    item['translated_text'] = ''
                    try:
                        self.shrink_text_rect_to_content(item)
                    except Exception:
                        pass
                    page_count += 1

            if page_count:
                total_pages += 1
                total_items += page_count

        if total_items:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🧹 일괄 번역문 내용 지우기 완료: {total_pages}페이지 / {total_items}개")

    def clear_masks_for_removed_items(self, curr, removed_items):
        if not curr or not removed_items:
            return
        mask_keys = ['mask_merge', 'mask_inpaint', 'mask_merge_off', 'mask_inpaint_off']
        for item in removed_items:
            try:
                x, y, w, h = [int(v) for v in item.get('rect', [0, 0, 0, 0])]
            except Exception:
                continue
            for key in mask_keys:
                m = curr.get(key)
                if not isinstance(m, np.ndarray):
                    continue
                yy1 = max(0, y)
                yy2 = min(m.shape[0], y + h)
                xx1 = max(0, x)
                xx2 = min(m.shape[1], x + w)
                if yy2 > yy1 and xx2 > xx1:
                    m[yy1:yy2, xx1:xx2] = 0

    def clean_text_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr or 'data' not in curr:
            return 0
        old_items = list(curr.get('data', []))
        removed = [x for x in old_items if not x.get('use_inpaint', True)]
        kept = [x for x in old_items if x.get('use_inpaint', True)]
        if not removed:
            return 0

        self.clear_masks_for_removed_items(curr, removed)
        for n, item in enumerate(kept, 1):
            item['id'] = n
        curr['data'] = kept
        return len(removed)

    def clean_text_current(self):
        if not self.paths or self.idx not in self.data:
            return
        self.commit_current_page_ui_to_data()
        removed_count = sum(1 for x in self.data[self.idx].get('data', []) if not x.get('use_inpaint', True))
        if removed_count <= 0:
            self.log("🧹 There are no unchecked items to delete." if self.ui_language == LANG_EN else "🧹 삭제할 체크 해제 항목이 없습니다.")
            return
        if self.ui_language == LANG_EN:
            msg = f"Delete {removed_count} unchecked text item(s) and reorder IDs?\nThe masks for those text areas will also be cleared."
        else:
            msg = f"체크 해제된 텍스트 {removed_count}개를 삭제하고 번호를 재정렬할까요?\n해당 텍스트 영역의 마스크도 함께 지워집니다."
        ans = QMessageBox.question(
            self,
            self.tr_ui("텍스트 정리"),
            msg,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        undo_rec = self.make_project_undo_record("텍스트 정리")
        removed = self.clean_text_for_page(self.idx)
        if removed:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log((f"🧹 Clean text complete: {removed} items deleted / IDs reordered" if self.ui_language == LANG_EN else f"🧹 텍스트 정리 완료: {removed}개 삭제 / 번호 재정렬"))
        self.auto_save_project()

    def clean_text_batch(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        total_candidates = 0
        for i in range(len(self.paths)):
            curr = self.data.get(i)
            if curr:
                total_candidates += sum(1 for x in curr.get('data', []) if not x.get('use_inpaint', True))
        if total_candidates <= 0:
            self.log("🧹 There are no unchecked items to clean in batch." if self.ui_language == LANG_EN else "🧹 일괄 정리할 체크 해제 항목이 없습니다.")
            return
        if self.ui_language == LANG_EN:
            msg = f"Delete {total_candidates} unchecked text item(s) across all pages and reorder IDs?\nThe masks for those text areas will also be cleared."
        else:
            msg = f"전체 페이지에서 체크 해제된 텍스트 {total_candidates}개를 삭제하고 번호를 재정렬할까요?\n해당 텍스트 영역의 마스크도 함께 지워집니다."
        ans = QMessageBox.question(
            self,
            self.tr_ui("일괄 텍스트 정리"),
            msg,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        undo_rec = self.make_project_undo_record("일괄 텍스트 정리", full_project=True)
        total_removed = 0
        pages = 0
        for i in range(len(self.paths)):
            removed = self.clean_text_for_page(i)
            if removed:
                total_removed += removed
                pages += 1
        if total_removed:
            self.append_project_undo_record(undo_rec)
        self.ref_tab()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log((f"🧹 Batch clean text complete: {pages} page(s) / {total_removed} items deleted" if self.ui_language == LANG_EN else f"🧹 일괄 텍스트 정리 완료: {pages}페이지 / {total_removed}개 삭제"))
        self.auto_save_project()

    def bg_clean_to_np_image(self, bg):
        """bg_clean 값을 화면/마스크 작업용 OpenCV 이미지(BGR np.ndarray)로 변환한다."""
        if bg is None:
            return None

        try:
            if isinstance(bg, np.ndarray):
                return bg.copy()

            if isinstance(bg, (bytes, bytearray)):
                arr = np.frombuffer(bg, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return img.copy() if img is not None else None

            if isinstance(bg, str) and os.path.exists(bg):
                arr = np.fromfile(bg, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
                return img.copy() if img is not None else None
        except Exception:
            return None

        return None

    def get_real_original_image(self, page_idx):
        """프로젝트 images 폴더에 있는 실제 원본 파일을 다시 읽는다."""
        if page_idx < 0 or page_idx >= len(self.paths):
            return None
        try:
            return cv2.imdecode(np.fromfile(self.paths[page_idx], np.uint8), 1)
        except Exception:
            return None

    def normalize_image_to_original_size(self, page_idx, img):
        """
        인페인팅 결과 이미지를 프로젝트 원본 해상도에 맞춘다.

        일부 인페인팅 API는 결과 해상도를 바꿔서 반환할 수 있다.
        이 상태로 다시 인페인팅하면 기존 마스크/텍스트 좌표와 크기가 어긋날 수 있으므로
        툴 내부 기준 이미지는 항상 원본 해상도에 맞춘다.
        """
        if img is None:
            return None

        ref = self.get_real_original_image(page_idx)
        if ref is None:
            return img

        rh, rw = ref.shape[:2]
        h, w = img.shape[:2]
        if (h, w) == (rh, rw):
            return img

        try:
            resized = cv2.resize(img, (rw, rh), interpolation=cv2.INTER_CUBIC)
            self.log(f"↔️ 인페인팅 결과 해상도 보정: {w}x{h} → {rw}x{rh}")
            return resized
        except Exception:
            return img

    def encode_np_image_to_png_bytes(self, img):
        if img is None:
            return None
        try:
            ok, buf = cv2.imencode(".png", img)
            if ok:
                return buf.tobytes()
        except Exception:
            pass
        return None

    def set_working_source_image(self, curr, img):
        """인페인팅/최종 브러시 반영 후 '원본 탭 기준 이미지'로 쓸 작업중 소스를 저장한다."""
        if curr is None or img is None:
            return
        encoded = self.encode_np_image_to_png_bytes(img)
        curr['working_source'] = encoded if encoded is not None else img
        curr['use_inpainted_as_source'] = True
        curr['ori'] = img.copy() if isinstance(img, np.ndarray) else img

    def write_np_image_as_inpaint_source(self, page_idx, img):
        """현재 기준 이미지를 인페인팅 입력 파일로 저장한다. Windows 한글 경로 안전 처리."""
        if img is None:
            return None

        clean_dir = self.ensure_subdir("clean")
        out_path = os.path.join(clean_dir, f"inpaint_source_{page_idx + 1:04d}.png")

        try:
            ok, buf = cv2.imencode(".png", img)
            if not ok:
                self.log("⚠️ 인페인팅 기준 이미지 인코딩 실패")
                return None

            # cv2.imwrite는 Windows 한글 경로에서 실패할 수 있어 np.tofile로 저장한다.
            buf.tofile(out_path)

            if not os.path.exists(out_path) or os.path.getsize(out_path) <= 0:
                self.log("⚠️ 인페인팅 기준 이미지 파일 저장 실패")
                return None

            return out_path
        except Exception as e:
            self.log(f"⚠️ 인페인팅 기준 이미지 저장 오류: {e}")
            return None

    def normalize_inpaint_mask_to_input_image(self, input_path, mask):
        """인페인팅 입력 이미지와 마스크 크기가 다르면 마스크를 입력 이미지 크기에 맞춘다."""
        if mask is None:
            return None

        try:
            img = cv2.imdecode(np.fromfile(input_path, np.uint8), cv2.IMREAD_COLOR)
            if img is None:
                return mask

            ih, iw = img.shape[:2]
            mh, mw = mask.shape[:2]
            if (mh, mw) == (ih, iw):
                return mask

            fixed = cv2.resize(mask, (iw, ih), interpolation=cv2.INTER_NEAREST)
            self.log((f"↔️ Inpaint mask size normalized: {mw}x{mh} → {iw}x{ih}" if self.ui_language == LANG_EN else f"↔️ 인페인팅 마스크 해상도 보정: {mw}x{mh} → {iw}x{ih}"))
            return fixed
        except Exception:
            return mask

    def get_source_display_image(self, page_idx):
        """
        원본/분석/마스크 탭에서 실제로 보여줄 기준 이미지.

        use_inpainted_as_source=True면 프로젝트 내부의 작업중 원본(working_source)을 우선 사용한다.
        working_source는 "인페인팅을 원본으로"와 "최종 브러시를 원본으로"가 공유하는 최신 기준 파일이다.
        """
        curr = self.data.get(page_idx, {})

        if curr.get('use_inpainted_as_source'):
            img = self.bg_clean_to_np_image(curr.get('working_source'))
            if img is not None:
                img = self.normalize_image_to_original_size(page_idx, img)
                curr['ori'] = img.copy()
                return curr['ori']

            img = self.bg_clean_to_np_image(curr.get('bg_clean'))
            if img is not None:
                img = self.normalize_image_to_original_size(page_idx, img)
                self.set_working_source_image(curr, img)
                return curr['ori']

        img = curr.get('ori')
        if img is None:
            img = self.get_real_original_image(page_idx)
            if img is not None:
                curr['ori'] = img
        return img


    def get_inpainting_input_path(self, page_idx):
        curr = self.data.get(page_idx, {})
        if curr.get('use_inpainted_as_source'):
            # 덧칠 모드에서는 현재 원본 탭에 표시되는 이미지(curr['ori'])를 그대로 입력으로 쓴다.
            # bg_clean을 다시 직접 쓰면, 최신 결과와 표시 기준이 엇갈릴 수 있다.
            img = self.get_source_display_image(page_idx)
            src = self.write_np_image_as_inpaint_source(page_idx, img)
            if src:
                return src
            self.log("⚠️ Failed to save the inpaint source image. Using the real original image instead." if self.ui_language == LANG_EN else "⚠️ 인페인팅 기준 이미지 저장 실패. 실제 원본 이미지로 진행합니다.")
        return self.paths[page_idx]

    def use_inpainted_as_source(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        if not curr.get('bg_clean'):
            QMessageBox.warning(self, self.tr_ui("인페인팅 결과 없음"), self.tr_ui("먼저 인페인팅된 이미지가 있어야 원본으로 가져올 수 있습니다."))
            return

        img = self.bg_clean_to_np_image(curr.get('bg_clean'))
        if img is None:
            QMessageBox.warning(self, self.tr_ui("이미지 변환 실패"), self.tr_ui("인페인팅 결과 이미지를 원본 탭에 표시할 수 없습니다."))
            return

        # 실제 원본 파일은 건드리지 않고, 프로젝트 내부 작업중 원본(working_source)에 저장한다.
        img = self.normalize_image_to_original_size(self.idx, img)
        self.set_working_source_image(curr, img)
        self.log("🔁 Inpaint result has been imported as the working source image for the Original tab." if self.ui_language == LANG_EN else "🔁 인페인팅 결과를 원본 탭의 작업중 기준 이미지로 가져왔습니다.")
        self.auto_save_project()
        self.mode_chg(self.cb_mode.currentIndex())

    def restore_original_source(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        curr['use_inpainted_as_source'] = False
        curr['working_source'] = None
        real_ori = self.get_real_original_image(self.idx)
        if real_ori is not None:
            curr['ori'] = real_ori
        self.log("↩️ The Original tab base image has been restored to the real original image." if self.ui_language == LANG_EN else "↩️ 원본 탭의 기준 이미지를 실제 원본으로 되돌렸습니다.")
        self.auto_save_project()
        self.mode_chg(self.cb_mode.currentIndex())

    # =========================================================
    # API / 엔진
    # =========================================================
    def restart_engine(self, show_error=True):
        apply_settings_to_config(self.api_settings)

        try:
            self.engine = MangaProcessEngine()
            if show_error and hasattr(self, "log_w"):
                self.log("🔧 Engine restarted" if self.ui_language == LANG_EN else "🔧 엔진 재시동 완료")
            return True
        except Exception as e:
            self.engine = None
            print(f"Engine Init Error: {e}")
            if show_error:
                QMessageBox.warning(
                    self,
                    self.tr_ui("엔진 초기화 실패"),
                    self.tr_msg("API 설정이 비어 있거나 잘못되어 엔진을 시작하지 못했습니다.\n"
                    "[옵션 > API 관리]에서 키를 저장한 뒤 다시 시도해주세요.\n\n") + f"{self.tr_ui('오류')}: {e}"
                )
            return False

    def ensure_engine_ready(self):
        if self.engine is not None:
            return True

        QMessageBox.warning(
            self,
            self.tr_ui("API 설정 필요"),
            self.tr_msg("엔진이 아직 준비되지 않았습니다.\n[옵션 > API 관리]에서 키를 저장해주세요.")
        )
        return False

    # =========================================================
    # 프로젝트 인터락 / 외부 실행 요청
    # =========================================================
    def bring_to_front(self):
        """두 번째 실행 요청이 들어왔을 때 현재 창을 앞으로 가져온다."""
        self.force_app_focus(reason="single-instance")

    def force_app_focus(self, reason="external-open", log_once=False):
        """
        .ysbt 더블클릭 / 드래그 앤 드롭 / 외부 열기 후 창 포커스를 YSB로 되돌린다.
        Windows는 다른 프로세스가 만든 포커스 변경을 막는 경우가 있어 Qt 포커스와 Win32 포커스를 여러 번 같이 시도한다.
        """
        delays = (0, 80, 220, 450)
        for delay in delays:
            QTimer.singleShot(delay, lambda r=reason: self._force_app_focus_once(r))
        if log_once:
            try:
                if self.ui_language == LANG_EN:
                    self.log(f"🪟 Focus requested: {reason}")
                else:
                    self.log(f"🪟 창 포커스 요청: {reason}")
            except Exception:
                pass

    def _force_app_focus_once(self, reason="external-open"):
        try:
            if self.isMinimized():
                self.showNormal()
            else:
                self.show()

            try:
                self.setWindowState((self.windowState() & ~Qt.WindowState.WindowMinimized) | Qt.WindowState.WindowActive)
            except Exception:
                pass

            # Qt 기본 포커스 요청
            self.raise_()
            self.activateWindow()
            self.setFocus(Qt.FocusReason.ActiveWindowFocusReason)

            # Windows에서는 파일 더블클릭/두 번째 프로세스 전달 뒤 포커스가 탐색기나 cmd에 남는 경우가 있다.
            if sys.platform.startswith("win"):
                try:
                    import ctypes
                    user32 = ctypes.windll.user32
                    hwnd = int(self.winId())
                    SW_RESTORE = 9
                    HWND_TOPMOST = -1
                    HWND_NOTOPMOST = -2
                    SWP_NOMOVE = 0x0002
                    SWP_NOSIZE = 0x0001
                    SWP_SHOWWINDOW = 0x0040
                    ASFW_ANY = -1
                    try:
                        user32.AllowSetForegroundWindow(ASFW_ANY)
                    except Exception:
                        pass
                    try:
                        user32.ShowWindow(hwnd, SW_RESTORE)
                    except Exception:
                        pass
                    # 포커스 제한이 걸린 환경에서도 앞으로 나오도록 topmost를 아주 짧게 토글한다.
                    try:
                        user32.SetWindowPos(hwnd, HWND_TOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                        user32.SetWindowPos(hwnd, HWND_NOTOPMOST, 0, 0, 0, 0, SWP_NOMOVE | SWP_NOSIZE | SWP_SHOWWINDOW)
                    except Exception:
                        pass
                    try:
                        user32.BringWindowToTop(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.SetForegroundWindow(hwnd)
                    except Exception:
                        pass
                    try:
                        user32.SetFocus(hwnd)
                    except Exception:
                        pass
                except Exception:
                    pass
        except Exception:
            pass

    def has_open_project(self):
        return bool(self.project_dir or self.paths)

    def busy_reason_text(self, reason=""):
        reason = str(reason or "").strip()
        if reason:
            return reason
        return "Working..." if getattr(self, "ui_language", LANG_KO) == LANG_EN else "작업 중"

    def begin_busy_state(self, reason="작업 중"):
        """긴 내부 작업 중에는 Wait Cursor와 UI 잠금을 걸어 중복 클릭을 막는다."""
        try:
            if not hasattr(self, "_busy_counter"):
                self._busy_counter = 0
            if not hasattr(self, "_busy_reason_stack"):
                self._busy_reason_stack = []
            self._busy_counter += 1
            self._busy_reason_stack.append(self.busy_reason_text(reason))
            if self._busy_counter > 1:
                QApplication.processEvents()
                return

            try:
                QApplication.setOverrideCursor(Qt.CursorShape.WaitCursor)
            except Exception:
                pass

            widgets = []
            try:
                cw = self.centralWidget()
                if cw is not None:
                    widgets.append(cw)
            except Exception:
                pass
            try:
                mb = self.menuBar()
                if mb is not None:
                    widgets.append(mb)
            except Exception:
                pass
            try:
                for tb in self.findChildren(QToolBar):
                    widgets.append(tb)
            except Exception:
                pass

            self._busy_widgets = []
            for w in widgets:
                try:
                    self._busy_widgets.append((w, bool(w.isEnabled())))
                    w.setEnabled(False)
                except Exception:
                    pass

            try:
                self.setCursor(Qt.CursorShape.WaitCursor)
            except Exception:
                pass

            text = self._busy_reason_stack[-1] if self._busy_reason_stack else self.busy_reason_text(reason)
            self.log(
                f"⏳ Busy: {text} / UI locked"
                if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                f"⏳ 작업 중: {text} / UI 잠금"
            )
            QApplication.processEvents()
        except Exception:
            pass

    def end_busy_state(self, reason=""):
        """begin_busy_state()로 잠근 UI와 커서를 복구한다."""
        try:
            if not hasattr(self, "_busy_counter"):
                self._busy_counter = 0
            if self._busy_counter <= 0:
                self._busy_counter = 0
                return

            self._busy_counter -= 1
            try:
                if getattr(self, "_busy_reason_stack", None):
                    self._busy_reason_stack.pop()
            except Exception:
                pass

            if self._busy_counter > 0:
                QApplication.processEvents()
                return

            for w, enabled in reversed(getattr(self, "_busy_widgets", []) or []):
                try:
                    w.setEnabled(enabled)
                except Exception:
                    pass
            self._busy_widgets = []

            try:
                self.unsetCursor()
            except Exception:
                pass
            try:
                while QApplication.overrideCursor() is not None:
                    QApplication.restoreOverrideCursor()
            except Exception:
                pass

            text = self.busy_reason_text(reason)
            self.log(
                f"✅ Busy finished: {text} / UI unlocked"
                if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                f"✅ 작업 완료: {text} / UI 잠금 해제"
            )
            QApplication.processEvents()
        except Exception:
            try:
                QApplication.restoreOverrideCursor()
            except Exception:
                pass

    def guard_project_action(self, action_name="프로젝트 작업"):
        """일괄 작업 중에는 프로젝트 열기/저장/위치 변경 같은 구조 변경 동작을 막는다."""
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(
                self,
                self.tr_ui("일괄 작업 중"),
                self.tr_msg(f"현재 일괄 작업이 진행 중입니다.\n{action_name}은(는) 일괄 작업이 끝난 뒤 다시 시도해 주세요."),
            )
            self.log(f"⛔ 일괄 작업 중 차단됨: {action_name}")
            return False
        return True

    def set_project_action_interlock(self, locked):
        """일괄 작업 중 사용하면 위험한 프로젝트 관련 메뉴를 비활성화한다."""
        for key in (
            "project_new",
            "project_open",
            "project_open_json",
            "project_save",
            "project_save_as",
            "option_workspace_location",
            "option_workspace_reset_default",
        ):
            action = self.actions.get(key) if hasattr(self, "actions") else None
            if action is not None:
                action.setEnabled(not locked)

    def close_current_project_state_for_switch(self):
        """새 프로젝트를 열기 전 현재 프로젝트의 임시 상태를 정리한다."""
        try:
            self.cleanup_work_cache()
        except Exception:
            pass
        try:
            self.delete_temp_project_if_needed()
        except Exception:
            pass
        self.has_unsaved_changes = False

    def confirm_close_current_project_for_open(self, source_text=""):
        """외부 .ysbt 열기 요청이 들어왔을 때 현재 프로젝트를 닫을지 확인한다."""
        if not self.has_open_project():
            return True
        title = self.tr_ui("프로젝트 열기")
        message = self.tr_msg(
            "현재 열려있는 프로젝트를 닫고 새 프로젝트를 열까요?\n\n"
            "[예] 기존 프로젝트를 닫고 새 프로젝트를 엽니다.\n"
            "[아니오] 열기를 취소합니다."
        )
        if source_text:
            message += f"\n\n{self.tr_ui('열려고 하는 파일:')}\n{source_text}"
        ans = styled_question(
            self,
            title,
            message,
            default_yes=False,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 외부 프로젝트 열기 취소")
            return False

        # 저장하지 않은 작업이 있으면 기존 저장 확인 루틴을 한 번 더 거친다.
        # 사용자가 저장/저장 안 함/취소 중 선택할 수 있게 해서 데이터 손실을 막는다.
        if self.has_unsaved_changes:
            return self.confirm_unsaved_before_switch()

        self.close_current_project_state_for_switch()
        return True

    def setup_external_open_queue_monitor(self):
        """YSB_FileOpener가 기록한 .ysbt 열기 요청 큐를 감시한다."""
        try:
            self.write_external_open_runtime_info()
        except Exception:
            pass

        self._external_open_queue_timer = QTimer(self)
        self._external_open_queue_timer.setInterval(350)
        self._external_open_queue_timer.timeout.connect(self.process_external_open_queue)
        self._external_open_queue_timer.start()

        self._external_runtime_timer = QTimer(self)
        self._external_runtime_timer.setInterval(5000)
        self._external_runtime_timer.timeout.connect(self.write_external_open_runtime_info)
        self._external_runtime_timer.start()

        QTimer.singleShot(700, self.process_external_open_queue)

    def write_external_open_runtime_info(self):
        """경량 런처가 메인 앱 실행 여부를 빠르게 판단할 수 있게 pid 정보를 남긴다."""
        try:
            path = ysb_main_runtime_info_path()
            path.parent.mkdir(parents=True, exist_ok=True)
            data = {
                "pid": os.getpid(),
                "exe": str(Path(sys.executable).resolve()),
                "time": datetime.utcnow().isoformat(timespec="seconds") + "Z",
                "queue": str(ysb_open_queue_path()),
            }
            tmp = path.with_suffix(".tmp")
            tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(path)
        except Exception:
            pass

    def cleanup_external_open_runtime_info(self):
        """정상 종료 시 런처용 pid 정보를 정리한다. 실패해도 종료는 막지 않는다."""
        try:
            path = ysb_main_runtime_info_path()
            if path.exists():
                try:
                    data = json.loads(path.read_text(encoding="utf-8"))
                    if int(data.get("pid") or -1) != os.getpid():
                        return
                except Exception:
                    pass
                path.unlink()
        except Exception:
            pass

    def process_external_open_queue(self):
        """open_queue.jsonl에 쌓인 .ysbt 열기 요청을 기존 창에서 처리한다."""
        queue_path = ysb_open_queue_path()
        if not queue_path.exists():
            return
        try:
            processing_path = queue_path.with_suffix(f".processing.{os.getpid()}.{int(time.time() * 1000)}")
            try:
                queue_path.replace(processing_path)
            except FileNotFoundError:
                return
            except Exception:
                # 다른 프로세스가 쓰는 순간이면 다음 타이머에서 다시 처리한다.
                return

            try:
                raw = processing_path.read_text(encoding="utf-8", errors="replace")
            finally:
                try:
                    processing_path.unlink()
                except Exception:
                    pass

            for line in raw.splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    payload = json.loads(line)
                except Exception:
                    continue
                if not isinstance(payload, dict):
                    continue
                command = str(payload.get("command") or "activate")
                if command == "activate":
                    self.handle_single_instance_payload({"command": "activate", "source": "file-opener-queue"})
                    continue
                if command != "open":
                    continue
                path = str(payload.get("path") or "")
                if not path:
                    continue
                if not (path.lower().endswith(YSB_EXTENSION) or os.path.basename(path).lower() == PROJECT_FILENAME):
                    continue
                self.handle_single_instance_payload({"command": "open", "path": path, "source": "file-opener-queue"})
        except Exception as e:
            try:
                self.log(f"⚠️ 외부 열기 큐 처리 실패: {e}")
            except Exception:
                pass

    def handle_single_instance_payload(self, payload):
        """두 번째 실행 프로세스에서 넘어온 메시지를 현재 창에서 처리한다."""
        self.force_app_focus(reason="external request")
        payload = payload or {}
        command = str(payload.get("command", "activate") or "activate")
        if command != "open":
            return
        path = str(payload.get("path", "") or "")
        if not path:
            return
        if not self.guard_project_action("외부 YSBT 파일 열기"):
            return
        if not self.confirm_close_current_project_for_open(path):
            return
        self.open_project_path(path, external_request=True)
        self.force_app_focus(reason="external file open")

    def _dragged_ysbt_path(self, event):
        try:
            mime = event.mimeData()
            if not mime or not mime.hasUrls():
                return ""
            for url in mime.urls():
                path = url.toLocalFile()
                if path and path.lower().endswith(YSB_EXTENSION):
                    return os.path.abspath(path)
        except Exception:
            return ""
        return ""

    def dragEnterEvent(self, event):
        path = self._dragged_ysbt_path(event)
        if path:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dragMoveEvent(self, event):
        path = self._dragged_ysbt_path(event)
        if path:
            event.acceptProposedAction()
        else:
            event.ignore()

    def dropEvent(self, event):
        path = self._dragged_ysbt_path(event)
        if not path:
            event.ignore()
            return
        event.acceptProposedAction()
        if not self.guard_project_action("YSBT 파일 드래그 열기"):
            return
        if not self.confirm_close_current_project_for_open(path):
            return
        self.open_project_path(path, external_request=True)
        self.force_app_focus(reason="drag and drop open")

    # =========================================================
    # 프로젝트 저장 / 불러오기
    # =========================================================
    def change_workspace_location(self):
        """옵션 메뉴에서 작업 폴더 설정 창을 다시 연다.

        첫 실행 설정창과 같은 UI를 쓰되, 닫기를 눌러도 프로그램은 종료하지 않는다.
        위치가 바뀐 경우에는 다음 실행 시 이동되도록 예약한다.
        """
        if not self.guard_project_action("작업 폴더 위치 변경"):
            return
        dlg = WorkspaceSetupDialog(self, first_run=False)
        if dlg.exec() == QDialog.DialogCode.Accepted:
            self.workspace_root = str(get_workspace_root())
            self.log("📁 작업 폴더 설정 확인")
        else:
            self.log("📁 작업 폴더 설정 변경 취소")

    def reset_workspace_location_to_default(self, parent=None):
        """작업 폴더 위치를 Windows 실제 문서 폴더 기준 기본값으로 되돌린 뒤 재기동한다."""
        if not self.guard_project_action("작업 폴더 위치 기본값으로 변경"):
            return
        parent = parent or self
        target = default_workspace_root()
        try:
            current = Path(load_workspace_config().get("workspace_root") or get_workspace_root()).resolve()
            target_resolved = target.resolve()
        except Exception:
            current = Path(str(get_workspace_root()))
            target_resolved = target

        if current == target_resolved:
            set_workspace_root(target)
            QMessageBox.information(
                parent,
                self.tr_ui("설정 완료"),
                f"{self.tr_ui('작업 폴더 위치가 이미 기본값입니다.')}\n\n{target}",
            )
            self.log(f"📁 작업 폴더 기본값 확인: {target}")
            return

        if not workspace_restart_confirmation(parent, current, target, self.ui_language):
            self.log("📁 작업 폴더 기본값 변경 취소")
            return

        try:
            schedule_workspace_root_change(target)
            self.log(f"📁 작업 폴더 기본값 변경 예약 및 재기동: {target}")
            restart_application_detached()
        except Exception as e:
            QMessageBox.critical(
                parent,
                self.tr_ui("저장 실패"),
                f"{self.tr_ui('작업 폴더 위치를 기본값으로 변경하지 못했습니다.')}\n{e}",
            )

    def register_ysb_file_association(self):
        if not is_windows():
            QMessageBox.information(self, self.tr_ui("지원 안내"), self.tr_msg(".ysbt 확장자 연결 등록은 Windows에서만 지원합니다."))
            return
        if is_ysbt_file_association_registered():
            QMessageBox.information(self, self.tr_ui("이미 등록됨"), self.tr_msg(".ysbt 확장자가 현재 실행 중인 역식붕이 툴에 이미 연결되어 있습니다."))
            return

        if is_ysbt_file_association_registered_to_other_ysb():
            registered = get_registered_ysbt_file_association_command() or "알 수 없음"
            message = (
                ".ysbt 확장자가 다른 위치의 역식붕이 툴에 연결되어 있습니다.\n"
                "현재 실행 중인 프로그램으로 연결을 갱신할까요?\n\n"
                f"현재 등록된 실행 명령:\n{registered}\n\n"
                "이 작업은 Windows의 확장자 연결 정보만 현재 프로그램으로 덮어씁니다. 기존 .ysbt 프로젝트 파일은 변경되지 않습니다."
            )
        else:
            message = (
                "현재 사용자 계정에 .ysbt 확장자 연결을 등록합니다.\n"
                "등록 후 .ysbt 파일을 더블클릭하면 역식붕이 툴로 열립니다. 계속할까요?"
            )

        ans = QMessageBox.question(
            self,
            self.tr_ui(".ysbt 확장자 연결 등록"),
            self.tr_msg(message),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            register_ysbt_file_association_raw()
            QMessageBox.information(self, self.tr_ui("등록 완료"), self.tr_ui(".ysbt 확장자 연결을 현재 실행 중인 역식붕이 툴로 등록했습니다.\n아이콘 표시는 Windows 아이콘 캐시 때문에 조금 늦게 갱신될 수 있습니다."))
            self.log("🔗 .ysbt 확장자 연결 등록/갱신 완료")
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("등록 실패"), f"{self.tr_ui('.ysbt 확장자 연결 등록에 실패했습니다.')}\n{e}")

    def unregister_ysbt_file_association(self):
        """현재 사용자 계정에 등록된 .ysbt 연결을 제거한다.

        이전 테스트 버전에서 이 프로그램이 등록한 .ysb 연결도 함께 정리한다.
        단, 다른 프로그램에 연결된 .ysb는 변경하지 않는다.
        """
        if not is_windows():
            QMessageBox.information(self, self.tr_ui("지원 안내"), self.tr_ui("확장자 연결 해제는 Windows에서만 지원합니다."))
            return
        ans = QMessageBox.question(
            self,
            self.tr_ui("확장자 연결 해제"),
            self.tr_ui("현재 사용자 계정의 .ysbt 연결을 해제합니다.\n이전 테스트 버전에서 이 프로그램이 등록한 .ysb 연결도 함께 정리합니다.\n다른 프로그램에 연결된 .ysb는 변경하지 않습니다.\n\n계속할까요?"),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        try:
            removed = unregister_ysbt_file_association_raw(include_legacy=True)
            msg = self.tr_ui("확장자 연결 해제를 완료했습니다.")
            if removed:
                msg += "\n\n" + self.tr_ui("제거 항목") + ":\n- " + "\n- ".join(removed)
            else:
                msg += "\n\n" + self.tr_ui("제거할 연결 항목이 없었습니다.")
            QMessageBox.information(self, self.tr_ui("해제 완료"), msg)
            self.log("🔗 확장자 연결 해제 완료: " + (", ".join(removed) if removed else "제거 항목 없음"))
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("해제 실패"), f"{self.tr_ui('확장자 연결 해제에 실패했습니다.')}\n{e}")

    def workspace_temp_project_dir(self, project_name="unsaved_project"):
        """새 프로젝트용 임시 작업 폴더를 만든다.

        v1.8 런처 이후에는 사용자가 작업 폴더를 문서/YSB_Translator로 잡아두었는지
        바로 확인할 수 있어야 하므로, 새 프로젝트의 임시 작업도 workspaces 아래에 만든다.
        아직 .ysbt로 저장되지 않은 상태라는 의미는 is_temp_project 플래그로 관리한다.
        """
        safe = safe_project_name(project_name)
        return unique_dir(workspaces_dir(), f"unsaved_{safe}_{uuid.uuid4().hex[:8]}")

    def workspace_project_dir(self, project_name="ysb_project", code=None, *, append_code=True):
        safe = clean_workspace_name(project_name)
        return unique_dir_with_code_suffix(workspaces_dir(), safe, code, append_code=append_code)

    def normalize_ysb_path(self, path):
        if not path:
            return path
        return path if path.lower().endswith(YSB_EXTENSION) else path + YSB_EXTENSION

    def current_package_default_path(self):
        base = getattr(self, "suggested_project_name", None) or (Path(self.project_dir).name if self.project_dir else "ysb_project")
        base = clean_workspace_name(base)
        return str(default_package_dir() / f"{safe_project_name(base)}{YSB_EXTENSION}")

    def delete_temp_project_if_needed(self):
        """저장되지 않은 임시 프로젝트 폴더를 안전하게 삭제한다.

        예전에는 임시 프로젝트가 temp 아래에만 있었지만, v1.8 런처 이후 새 프로젝트는
        사용자가 지정한 작업 폴더의 workspaces 아래에 unsaved_* 형태로 보이게 만든다.
        따라서 is_temp_project=True이고 아직 .ysbt 패키지에 연결되지 않은 경우에는
        temp/workspaces 내부의 unsaved_* 폴더를 정리한다.
        """
        if self.is_temp_project and self.project_dir and os.path.exists(self.project_dir):
            try:
                proj = os.path.abspath(self.project_dir)
                roots = [os.path.abspath(str(temp_dir())), os.path.abspath(str(workspaces_dir()))]
                name = os.path.basename(proj)
                can_delete = (not getattr(self, "ysbt_package_path", None)) and name.startswith("unsaved_")
                if can_delete and any(proj.startswith(root) for root in roots):
                    shutil.rmtree(self.project_dir, ignore_errors=True)
                    self.log(f"🧹 임시 프로젝트 삭제: {self.project_dir}")
            except Exception:
                pass
        self.is_temp_project = False

    def promote_temp_project_to_workspace(self, project_name=None):
        if not self.is_temp_project:
            return True
        if not self.project_dir or not os.path.exists(self.project_dir):
            return False

        name = clean_workspace_name(project_name or Path(self.project_dir).name)
        dst = self.workspace_project_dir(name)
        old_dir = self.project_dir
        try:
            # 현재 temp 프로젝트 저장 후, 새 폴더를 만들지 않고 temp 폴더 자체를 정식 작업 폴더로 승격한다.
            self.save_project_store(self.project_store)
            if os.path.abspath(old_dir) != os.path.abspath(dst):
                shutil.move(old_dir, dst)
            self.project_dir = dst
            self.project_store = ProjectStore(dst)
            # UUID는 manifest 내부에 유지하고, 폴더명/프로젝트명은 깔끔한 이름으로 갱신한다.
            self.project_store.write_manifest(project_name=name)
            self.is_temp_project = False

            # 혹시 이전 버전에서 workspaces 안에 unsaved_* 찌꺼기가 생겼다면,
            # 현재 승격한 폴더와 다른 빈/동일 임시 폴더만 안전하게 제거한다.
            try:
                ws_root = os.path.abspath(str(workspaces_dir()))
                old_abs = os.path.abspath(old_dir)
                dst_abs = os.path.abspath(dst)
                if old_abs.startswith(ws_root) and os.path.basename(old_abs).startswith("unsaved_") and old_abs != dst_abs and os.path.exists(old_abs):
                    shutil.rmtree(old_abs, ignore_errors=True)
            except Exception:
                pass

            self.reload_saved_project_from_disk(refresh_view=False)
            self.log(f"📦 임시 프로젝트를 작업 폴더로 승격: {dst}")
            return True
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("프로젝트 이동 실패"), f"{self.tr_ui("임시 프로젝트를 작업 폴더로 옮기지 못했습니다.")}\n{e}")
            return False

    def record_recovery_project_dir(self, project_dir):
        """비정상 종료 후 복구 후보로 쓸 마지막 작업 폴더를 옵션 캐시에 기록한다."""
        try:
            if not project_dir:
                return
            project_dir = os.path.abspath(str(project_dir))
            if not os.path.exists(os.path.join(project_dir, PROJECT_FILENAME)):
                return
            self.app_options["last_recovery_project_dir"] = project_dir
            save_app_options(self.app_options)
        except Exception:
            pass

    def recovery_candidate_roots(self):
        return [self.project_cache_root(), temp_dir()]

    def find_recovery_candidates(self):
        """work_sessions/temp 안에서 project.json이 있는 복구 후보를 최신순으로 찾는다."""
        candidates = []
        seen = set()

        def add_candidate(path):
            try:
                p = Path(path)
                project_file = p / PROJECT_FILENAME
                if not project_file.exists():
                    return
                resolved = str(p.resolve())
                if resolved in seen:
                    return
                seen.add(resolved)
                try:
                    mtime = max(project_file.stat().st_mtime, p.stat().st_mtime)
                except Exception:
                    mtime = p.stat().st_mtime if p.exists() else 0
                candidates.append((mtime, str(p), str(project_file)))
            except Exception:
                pass

        # 1순위: 마지막 작업 캐시로 명시 기록한 폴더
        last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "").strip()
        if last_dir:
            add_candidate(last_dir)

        # 2순위: work cache / temp 폴더 전체 검색
        for root in self.recovery_candidate_roots():
            try:
                root = Path(root)
                if not root.exists():
                    continue
                for child in root.iterdir():
                    if child.is_dir():
                        add_candidate(child)
            except Exception:
                pass

        candidates.sort(key=lambda x: x[0], reverse=True)
        return candidates

    def recover_last_work_project(self):
        """마지막 작업 캐시/임시 프로젝트를 열어 복구한다."""
        if not self.guard_project_action("마지막 작업 복구"):
            return
        candidates = self.find_recovery_candidates()
        if not candidates:
            QMessageBox.information(
                self,
                self.tr_ui("복구할 작업 없음"),
                self.tr_ui("복구할 수 있는 임시 작업 파일을 찾지 못했습니다."),
            )
            self.log("⚠️ 복구할 임시 작업 파일 없음")
            return

        _mtime, project_dir, project_file = candidates[0]
        msg = (
            f"{self.tr_ui('마지막 작업 폴더를 복구할까요?')}\n\n"
            f"{project_dir}\n\n"
            f"{self.tr_ui('복구한 작업은 아직 정식 YSBT 파일이 아닐 수 있습니다. 필요한 경우 [프로젝트 저장]으로 다시 저장해 주세요.')}"
        )
        ans = QMessageBox.question(
            self,
            self.tr_ui("마지막 작업 복구"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.Yes,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 마지막 작업 복구 취소")
            return

        if not self.confirm_unsaved_before_switch():
            return

        try:
            # 복구 폴더 자체를 임시 프로젝트로 연다. 원본 .ysbt와 연결하지 않고,
            # 사용자가 저장할 때 새 YSBT로 확정하게 한다.
            self.load_project_json(project_file, package_path=None, temp_project=False)
            self.ysbt_package_path = None
            self.is_temp_project = True
            self.has_unsaved_changes = True
            self.record_recovery_project_dir(project_dir)
            self.update_window_title()
            self.log(f"🧯 마지막 작업 복구 완료: {project_dir}")
            self.log("💾 복구한 작업은 [프로젝트 저장] 또는 [다른 이름으로 저장]으로 YSBT 파일에 확정하세요.")
        except Exception as e:
            QMessageBox.critical(
                self,
                self.tr_ui("복구 실패"),
                f"{self.tr_ui('마지막 작업을 복구하지 못했습니다.')}\n{project_dir}\n\n{e}",
            )
            self.log(f"❌ 마지막 작업 복구 실패: {e}")

    def temp_path_created_timestamp(self, path):
        """폴더 생성 시각을 우선 사용하고, 불가능하면 수정 시각을 사용한다."""
        try:
            return Path(path).stat().st_ctime
        except Exception:
            try:
                return Path(path).stat().st_mtime
            except Exception:
                return 0

    def temp_cleanup_category_roots(self):
        return [
            ("temp", self.tr_ui("임시 프로젝트"), temp_dir()),
            ("work_sessions", self.tr_ui("작업 캐시"), self.project_cache_root()),
        ]

    def empty_temp_cleanup_summary(self):
        return {
            "temp": {"label": self.tr_ui("임시 프로젝트"), "count": 0, "size": 0},
            "work_sessions": {"label": self.tr_ui("작업 캐시"), "count": 0, "size": 0},
        }

    def format_size_mb(self, size_bytes):
        try:
            return f"{float(size_bytes or 0) / (1024 * 1024):.1f} MB"
        except Exception:
            return "0.0 MB"

    def collect_temp_cleanup_targets(self, *, older_than_days=None, skip_current=True, exclude_recovery=False):
        """temp/work_sessions에서 삭제 가능한 임시 작업 폴더를 분류별로 모은다."""
        skip_dirs = set()
        if skip_current:
            for p in (getattr(self, "project_dir", None), getattr(self, "work_project_dir", None)):
                if p:
                    try:
                        skip_dirs.add(str(Path(p).resolve()))
                    except Exception:
                        pass

        if exclude_recovery:
            try:
                last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "").strip()
                if last_dir:
                    skip_dirs.add(str(Path(last_dir).resolve()))
            except Exception:
                pass

        now_ts = time.time()
        max_age_seconds = None
        if older_than_days is not None:
            try:
                max_age_seconds = max(0, int(older_than_days)) * 24 * 60 * 60
            except Exception:
                max_age_seconds = None

        targets = []
        total_size = 0
        summary = self.empty_temp_cleanup_summary()

        for key, label, root in self.temp_cleanup_category_roots():
            try:
                root = Path(root)
                if not root.exists():
                    continue
                for child in root.iterdir():
                    if not child.is_dir():
                        continue
                    try:
                        resolved = str(child.resolve())
                    except Exception:
                        resolved = str(child)
                    if resolved in skip_dirs:
                        continue

                    if max_age_seconds is not None:
                        created_ts = self.temp_path_created_timestamp(child)
                        if created_ts and (now_ts - created_ts) < max_age_seconds:
                            continue

                    folder_size = 0
                    try:
                        for file in child.rglob("*"):
                            if file.is_file():
                                folder_size += file.stat().st_size
                    except Exception:
                        pass

                    targets.append(child)
                    total_size += folder_size
                    summary.setdefault(key, {"label": label, "count": 0, "size": 0})
                    summary[key]["label"] = label
                    summary[key]["count"] += 1
                    summary[key]["size"] += folder_size
            except Exception:
                pass

        return targets, total_size, summary

    def temp_cleanup_summary_text(self, summary, total_count=None, total_size=None):
        summary = summary or self.empty_temp_cleanup_summary()
        temp_info = summary.get("temp", {})
        work_info = summary.get("work_sessions", {})
        if total_count is None:
            total_count = int(temp_info.get("count", 0) or 0) + int(work_info.get("count", 0) or 0)
        if total_size is None:
            total_size = int(temp_info.get("size", 0) or 0) + int(work_info.get("size", 0) or 0)
        return (
            f"{self.tr_ui('임시 프로젝트')}: {int(temp_info.get('count', 0) or 0)} / {self.format_size_mb(temp_info.get('size', 0))}\n"
            f"{self.tr_ui('작업 캐시')}: {int(work_info.get('count', 0) or 0)} / {self.format_size_mb(work_info.get('size', 0))}\n"
            f"{self.tr_ui('총합')}: {int(total_count or 0)} / {self.format_size_mb(total_size)}"
        )

    def temp_cleanup_period_options(self):
        return [
            (7, "일주일"),
            (30, "한달"),
            (90, "3개월"),
            (180, "6개월"),
            (365, "12개월"),
        ]

    def get_temp_auto_cleanup_days(self):
        try:
            days = int((self.app_options or {}).get("temp_auto_cleanup_days", 7) or 7)
        except Exception:
            days = 7
        if days not in (7, 30, 90, 180, 365):
            days = 7
        return days

    def is_temp_auto_cleanup_enabled(self):
        return bool((self.app_options or {}).get("temp_auto_cleanup_enabled", True))

    def set_temp_cleanup_options(self, enabled=None, days=None):
        try:
            if enabled is not None:
                self.app_options["temp_auto_cleanup_enabled"] = bool(enabled)
            if days is not None:
                days = int(days)
                if days not in (7, 30, 90, 180, 365):
                    days = 7
                self.app_options["temp_auto_cleanup_days"] = days
            save_app_options(self.app_options)
        except Exception:
            pass

    def auto_cleanup_temp_files_if_needed(self):
        """설정된 주기마다, 설정된 기간 이상 지난 임시 작업 폴더를 자동 삭제한다."""
        try:
            if not self.is_temp_auto_cleanup_enabled():
                self.log(
                    "🧹 Auto temp cleanup is disabled."
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    "🧹 자동 임시 파일 정리: 꺼짐"
                )
                return

            period_days = self.get_temp_auto_cleanup_days()
            max_age_days = period_days
            now_ts = time.time()
            last_ts = float((self.app_options or {}).get("last_temp_auto_cleanup_at", 0) or 0)
            if last_ts and (now_ts - last_ts) < period_days * 24 * 60 * 60:
                return

            targets, total_size, summary = self.collect_temp_cleanup_targets(older_than_days=max_age_days, skip_current=True, exclude_recovery=True)

            deleted = 0
            failed = 0
            for path in targets:
                try:
                    shutil.rmtree(path, ignore_errors=False)
                    deleted += 1
                except Exception:
                    failed += 1

            try:
                last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "")
                if last_dir and not os.path.exists(last_dir):
                    self.app_options.pop("last_recovery_project_dir", None)
            except Exception:
                pass

            self.app_options["last_temp_auto_cleanup_at"] = now_ts
            self.app_options["temp_auto_cleanup_enabled"] = True
            self.app_options["temp_auto_cleanup_days"] = period_days
            save_app_options(self.app_options)

            if deleted or failed:
                size_mb = total_size / (1024 * 1024)
                self.log(
                    f"🧹 Auto temp cleanup: deleted {deleted}, failed {failed}, approx. {size_mb:.1f} MB / period {period_days} days"
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    f"🧹 자동 임시 파일 정리: 삭제 {deleted}개 / 실패 {failed}개 / 약 {size_mb:.1f} MB / 주기 {period_days}일"
                )
            else:
                self.log(
                    "🧹 Auto temp cleanup: no old temporary files."
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    "🧹 자동 임시 파일 정리: 오래된 임시 파일 없음"
                )
        except Exception as e:
            try:
                self.log(
                    f"⚠️ Auto temp cleanup failed: {e}"
                    if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                    f"⚠️ 자동 임시 파일 정리 실패: {e}"
                )
            except Exception:
                pass

    def delete_temp_files_now(self, parent=None):
        """현재 작업과 연결되지 않은 temp/work_sessions 임시 파일을 즉시 삭제한다."""
        targets, total_size, summary = self.collect_temp_cleanup_targets(
            older_than_days=None,
            skip_current=True,
            exclude_recovery=False,
        )

        if not targets:
            QMessageBox.information(
                parent or self,
                self.tr_ui("삭제할 임시 파일 없음"),
                self.tr_ui("삭제할 수 있는 임시 작업 파일이 없습니다."),
            )
            self.log("🧹 삭제할 임시 작업 파일 없음")
            return False

        msg = (
            f"{self.tr_ui('현재 열려 있는 작업을 제외한 임시 작업 폴더를 삭제합니다.')}\n\n"
            f"{self.temp_cleanup_summary_text(summary, len(targets), total_size)}\n\n"
            f"{self.tr_ui('삭제 후에는 해당 임시 작업을 복구할 수 없습니다. 계속할까요?')}"
        )
        ans = QMessageBox.question(
            parent or self,
            self.tr_ui("임시 파일 삭제"),
            msg,
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if ans != QMessageBox.StandardButton.Yes:
            self.log("↩️ 임시 파일 삭제 취소")
            return False

        deleted = 0
        failed = 0
        for path in targets:
            try:
                shutil.rmtree(path, ignore_errors=False)
                deleted += 1
            except Exception:
                failed += 1

        # 삭제한 폴더가 마지막 복구 기록이면 기록도 비운다.
        try:
            last_dir = str((self.app_options or {}).get("last_recovery_project_dir") or "")
            if last_dir and not os.path.exists(last_dir):
                self.app_options.pop("last_recovery_project_dir", None)
                save_app_options(self.app_options)
        except Exception:
            pass

        self.log(f"🧹 임시 파일 삭제 완료: {deleted}개 삭제 / {failed}개 실패")
        QMessageBox.information(
            parent or self,
            self.tr_ui("임시 파일 삭제 완료"),
            self.tr_ui(f"임시 파일 삭제가 완료되었습니다.\n삭제: {deleted}개\n실패: {failed}개"),
        )
        return True

    def cleanup_temp_files_dialog(self):
        """임시 파일 수동 삭제 + 자동 삭제 옵션 설정 창."""
        if not self.guard_project_action("임시 파일 관리"):
            return

        dlg = QDialog(self)
        dlg.setWindowTitle(self.tr_ui("임시 파일 관리"))
        dlg.setModal(True)
        layout = QVBoxLayout(dlg)

        desc = QLabel(self.tr_ui("임시 파일 삭제와 자동 삭제 주기를 설정합니다."))
        desc.setWordWrap(True)
        layout.addWidget(desc)

        stats_label = QLabel("")
        stats_label.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        stats_label.setWordWrap(True)
        layout.addWidget(stats_label)

        row = QHBoxLayout()
        btn_delete = QPushButton(self.tr_ui("임시파일 삭제"))
        cb_auto = QCheckBox(self.tr_ui("임시파일 자동삭제"))
        combo_days = QComboBox()

        current_days = self.get_temp_auto_cleanup_days()
        for days, label in self.temp_cleanup_period_options():
            combo_days.addItem(self.tr_ui(label), days)
            if days == current_days:
                combo_days.setCurrentIndex(combo_days.count() - 1)

        cb_auto.setChecked(self.is_temp_auto_cleanup_enabled())
        combo_days.setEnabled(cb_auto.isChecked())

        row.addWidget(btn_delete)
        row.addStretch(1)
        row.addWidget(cb_auto)
        row.addWidget(combo_days)
        layout.addLayout(row)

        note = QLabel(self.tr_ui("자동 삭제는 선택한 기간마다 실행되며, 선택한 기간 이상 지난 임시 작업 폴더만 삭제합니다."))
        note.setWordWrap(True)
        layout.addWidget(note)

        btns = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        layout.addWidget(btns)

        def refresh_stats():
            try:
                targets, total_size, summary = self.collect_temp_cleanup_targets(
                    older_than_days=None,
                    skip_current=True,
                    exclude_recovery=False,
                )
                stats_label.setText(self.temp_cleanup_summary_text(summary, len(targets), total_size))
            except Exception as e:
                stats_label.setText(f"{self.tr_ui('임시 파일 상태를 읽지 못했습니다.')}: {e}")

        def save_options():
            days = combo_days.currentData()
            self.set_temp_cleanup_options(cb_auto.isChecked(), days)
            combo_days.setEnabled(cb_auto.isChecked())
            self.log(
                f"🧹 임시 파일 자동삭제 설정: {'ON' if cb_auto.isChecked() else 'OFF'} / {int(days)}일"
            )

        def delete_and_refresh():
            changed = self.delete_temp_files_now(dlg)
            if changed:
                refresh_stats()

        cb_auto.toggled.connect(lambda _checked: save_options())
        combo_days.currentIndexChanged.connect(lambda _idx: save_options())
        btn_delete.clicked.connect(delete_and_refresh)
        btns.rejected.connect(dlg.reject)

        refresh_stats()
        dlg.resize(560, 220)
        dlg.exec()

    def open_project_path(self, path, external_request=False):
        """파일 연결/명령행 인자로 받은 .ysbt 또는 project.json을 연다."""
        if not path:
            return
        if not self.guard_project_action("프로젝트 열기"):
            return
        path = os.path.abspath(path)
        if not external_request:
            if not self.confirm_unsaved_before_switch():
                return
        if path.lower().endswith(YSB_EXTENSION):
            self.open_ysb_package(path)
            if external_request:
                self.force_app_focus(reason="external project open")
            return
        if os.path.isdir(path):
            project_file = os.path.join(path, PROJECT_FILENAME)
        else:
            project_file = path
        if os.path.basename(project_file) != PROJECT_FILENAME or not os.path.exists(project_file):
            QMessageBox.warning(self, self.tr_ui("프로젝트 없음"), f"{self.tr_ui("열 수 있는 프로젝트 파일이 아닙니다.")}\n{path}")
            return
        self.load_project_json(project_file)
        if external_request:
            self.force_app_focus(reason="external project open")

    def load_project_json(self, project_file, package_path=None, temp_project=False):
        self.is_loading_project = True
        try:
            self.commit_current_page_ui_to_data()
            self.project_store = ProjectStore()
            self.paths, self.data, self.idx = self.project_store.load(project_file)
            self.page_text_undo_stacks = {}
            self.project_undo_stack = []
            self.project_redo_stack = []
            self.undo_boundary = None
            self.update_undo_redo_buttons()
            ui_state = getattr(self.project_store, "ui_state", {}) or {}
            self.project_ui_view_states = copy.deepcopy(ui_state.get("view_states") or {})
            self.restore_project_ui_state(ui_state, refresh=False)
            self.project_dir = self.project_store.project_dir
            self.ysbt_package_path = package_path
            self.suggested_project_name = self.split_uuid_suffix_from_name(Path(package_path).stem)[0] if package_path else None
            self.is_temp_project = bool(temp_project)
            self.update_window_title()
            self.mark_saved_state()
            self.log(f"📂 프로젝트 열림: {self.project_dir}")
            if package_path:
                self.log(f"📦 연결된 YSBT 파일: {package_path}")

            # 새 프로젝트 생성은 원본 탭으로 시작하지만, 기존 프로젝트 열기는 마지막 작업 탭/화면 상태로 복원한다.
            mode_to_load = 0 if temp_project else int(ui_state.get("current_mode", 0) or 0)
            self.set_work_mode_without_undo(mode_to_load)
            self.show_editor()
            self.load()
            self.record_current_project_recent()
            state = self.project_ui_view_states.get(self.view_state_key(self.idx, mode_to_load))
            if state:
                self.apply_view_state(state)
                QTimer.singleShot(0, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                QTimer.singleShot(30, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                QTimer.singleShot(80, lambda st=copy.deepcopy(state): self.apply_view_state(st))

            if not self.auto_save_enabled:
                self.start_work_cache_from_current(mark_dirty=False)
        finally:
            self.is_loading_project = False

    def open_ysb_package(self, package_path):
        try:
            # 기준은 항상 .ysbt 파일이다. 같은 UUID/같은 .ysbt이면 기존 작업 폴더를 조용히 재사용하고,
            # 다른 파일이면 extract_ysb_package가 충돌 없는 새 작업 폴더를 만든다.
            target_dir, manifest, reused = extract_ysb_package(package_path, workspaces_dir(), reuse_existing=True)
            self.load_project_json(os.path.join(target_dir, PROJECT_FILENAME), package_path=package_path, temp_project=False)
        except Exception as e:
            QMessageBox.critical(self, self.tr_ui("YSBT 열기 실패"), f"{self.tr_ui('YSBT 프로젝트를 열지 못했습니다.')}\n{package_path}\n\n{e}")

    def project_cache_root(self):
        root = get_cache_dir() / "work_sessions"
        root.mkdir(parents=True, exist_ok=True)
        return root

    def cleanup_work_cache(self):
        if self.work_project_dir and os.path.exists(self.work_project_dir):
            try:
                shutil.rmtree(self.work_project_dir, ignore_errors=True)
            except Exception:
                pass
        self.work_project_dir = None
        self.work_project_store = None

    def make_work_cache_dir(self):
        if self.project_dir:
            base = Path(self.project_dir).name
        else:
            base = "unsaved_project"
        safe_base = "".join(c if c.isalnum() or c in ("_", "-", ".") else "_" for c in base)
        return str(self.project_cache_root() / f"{safe_base}_{uuid.uuid4().hex[:10]}")

    def start_work_cache_from_current(self, mark_dirty=False):
        """현재 메모리 상태를 기준으로 새 작업 캐시를 만든다."""
        if not self.project_dir or not self.paths:
            return
        old_cache = self.work_project_dir
        cache_dir = self.make_work_cache_dir()

        store = ProjectStore(cache_dir)
        self.save_project_store(store)

        # store.save()가 paths를 cache 내부 이미지 경로로 고정할 수 있으므로 이후 작업은 캐시 기준으로 돌아간다.
        self.work_project_store = store
        self.work_project_dir = cache_dir
        self.record_recovery_project_dir(cache_dir)
        self.has_unsaved_changes = bool(mark_dirty)

        if old_cache and old_cache != cache_dir and os.path.exists(old_cache):
            try:
                shutil.rmtree(old_cache, ignore_errors=True)
            except Exception:
                pass

        self.log(f"🧪 작업 캐시 시작: {cache_dir}")

    def save_to_work_cache(self):
        if not self.project_dir or not self.paths:
            return
        if self.work_project_store is None or not self.work_project_dir:
            self.start_work_cache_from_current(mark_dirty=False)
        if self.work_project_store is None:
            return
        self.save_project_store(self.work_project_store)
        self.record_recovery_project_dir(self.work_project_dir)
        self.has_unsaved_changes = True

    def mark_saved_state(self):
        self.has_unsaved_changes = False

    def save_app_options_cache(self):
        self.app_options["auto_save_enabled"] = bool(self.auto_save_enabled)
        self.app_options[UI_THEME_KEY] = str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK)
        self.app_options[UI_LANGUAGE_KEY] = normalize_ui_language(getattr(self, "ui_language", LANG_KO))
        self.app_options["analysis_number_box_width"] = int(getattr(self, "analysis_number_box_width", 40))
        self.app_options["temp_auto_cleanup_enabled"] = bool(self.app_options.get("temp_auto_cleanup_enabled", True))
        cleanup_days = int(self.app_options.get("temp_auto_cleanup_days", 7) or 7)
        if cleanup_days not in (7, 30, 90, 180, 365):
            cleanup_days = 7
        self.app_options["temp_auto_cleanup_days"] = cleanup_days
        self.app_options[ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY] = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY, getattr(Config, "MERGE_RATIO", DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO)),
            DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO,
        )
        self.app_options[ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY] = clamp_analysis_mask_ratio(
            self.app_options.get(ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY, getattr(Config, "INPAINT_RATIO", DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO)),
            DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO,
        )
        self.app_options[ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY] = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY, getattr(Config, "MERGE_MIN_STROKE_PX", DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX)),
            DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX,
        )
        self.app_options[ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY] = clamp_analysis_mask_min_px(
            self.app_options.get(ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY, getattr(Config, "MIN_STROKE_PX", DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX)),
            DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX,
        )
        self.sync_analysis_mask_options_to_config()
        self.app_options.setdefault(TRANSLATION_PROMPT_KEY, "")
        self.app_options.setdefault(TRANSLATION_GLOSSARY_TEXT_KEY, "")
        self.app_options.setdefault(TRANSLATION_GLOSSARY_PATH_KEY, "")
        save_app_options(self.app_options)

    def sync_translation_option_cache_to_config(self):
        """옵션 캐시에 저장된 번역 프롬프트/단어장을 번역 엔진 Config에 반영한다."""
        try:
            Config.TRANSLATION_PROMPT = str(self.app_options.get(TRANSLATION_PROMPT_KEY, "") or "")
            Config.TRANSLATION_GLOSSARY_TEXT = str(self.app_options.get(TRANSLATION_GLOSSARY_TEXT_KEY, "") or "")
        except Exception:
            pass

    def sync_analysis_mask_options_to_config(self):
        """옵션 캐시의 분석 마스크 확장 설정을 엔진 Config에 반영한다."""
        try:
            text_ratio = clamp_analysis_mask_ratio(
                self.app_options.get(ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO),
                DEFAULT_ANALYSIS_TEXT_MASK_EXPAND_RATIO,
            )
            paint_ratio = clamp_analysis_mask_ratio(
                self.app_options.get(ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY, DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO),
                DEFAULT_ANALYSIS_PAINT_MASK_EXPAND_RATIO,
            )
            text_min_px = clamp_analysis_mask_min_px(
                self.app_options.get(ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX),
                DEFAULT_ANALYSIS_TEXT_MASK_MIN_EXPAND_PX,
            )
            paint_min_px = clamp_analysis_mask_min_px(
                self.app_options.get(ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY, DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX),
                DEFAULT_ANALYSIS_PAINT_MASK_MIN_EXPAND_PX,
            )
            self.app_options[ANALYSIS_TEXT_MASK_EXPAND_RATIO_KEY] = text_ratio
            self.app_options[ANALYSIS_PAINT_MASK_EXPAND_RATIO_KEY] = paint_ratio
            self.app_options[ANALYSIS_TEXT_MASK_MIN_EXPAND_PX_KEY] = text_min_px
            self.app_options[ANALYSIS_PAINT_MASK_MIN_EXPAND_PX_KEY] = paint_min_px
            Config.MERGE_RATIO = text_ratio
            Config.INPAINT_RATIO = paint_ratio
            Config.MERGE_MIN_STROKE_PX = text_min_px
            Config.MIN_STROKE_PX = paint_min_px
        except Exception:
            pass

    def reload_saved_project_from_disk(self, refresh_view=True):
        """실제 프로젝트 저장본을 다시 로드해서 paths를 프로젝트 폴더 기준으로 되돌린다."""
        if not self.project_dir:
            return False
        project_file = os.path.join(self.project_dir, PROJECT_FILENAME)
        if not os.path.exists(project_file):
            return False

        self.is_loading_project = True
        try:
            store = ProjectStore()
            self.paths, self.data, self.idx = store.load(project_file)
            self.project_store = store
            self.project_dir = store.project_dir
            ui_state = getattr(store, "ui_state", {}) or {}
            self.project_ui_view_states = copy.deepcopy(ui_state.get("view_states") or getattr(self, "project_ui_view_states", {}) or {})
            self.restore_project_ui_state(ui_state, refresh=False)
            if refresh_view:
                mode_to_load = int(ui_state.get("current_mode", self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0) or 0)
                self.set_work_mode_without_undo(mode_to_load)
                self.load()
                state = self.project_ui_view_states.get(self.view_state_key(self.idx, mode_to_load))
                if state:
                    self.apply_view_state(state)
                    QTimer.singleShot(0, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                    QTimer.singleShot(30, lambda st=copy.deepcopy(state): self.apply_view_state(st))
                    QTimer.singleShot(80, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            return True
        finally:
            self.is_loading_project = False

    def commit_to_real_project_only(self):
        """작업 캐시 상태를 실제 프로젝트에 저장하되, 새 작업 캐시는 만들지 않는다."""
        if not self.project_dir or not self.paths:
            return False
        self.commit_current_page_ui_to_data()
        self.save_project_store(self.project_store)
        self.mark_saved_state()
        return True

    def toggle_auto_save_mode(self, checked):
        checked = bool(checked)

        if checked:
            if self.has_unsaved_changes:
                ans = QMessageBox.question(
                    self,
                    "자동저장 전환",
                    "저장하지 않은 작업이 있습니다.\n현재 작업 캐시를 프로젝트에 저장하고 자동저장 모드로 전환할까요?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    self.act_auto_save_mode.blockSignals(True)
                    self.act_auto_save_mode.setChecked(False)
                    self.act_auto_save_mode.blockSignals(False)
                    return
                if not self.commit_to_real_project_only():
                    self.act_auto_save_mode.blockSignals(True)
                    self.act_auto_save_mode.setChecked(False)
                    self.act_auto_save_mode.blockSignals(False)
                    return

            # 핵심: 자동저장 ON에서는 paths가 실제 프로젝트 폴더를 가리켜야 한다.
            # OFF 캐시를 삭제하기 전에 저장본을 다시 로드해서 캐시 경로 의존을 끊는다.
            self.auto_save_enabled = True
            self.save_app_options_cache()
            self.reload_saved_project_from_disk(refresh_view=True)
            self.cleanup_work_cache()
            self.mark_saved_state()
            self.log("💾 자동저장 모드 ON: 변경 사항이 실제 프로젝트에 바로 저장됩니다.")
        else:
            self.auto_save_enabled = False
            self.save_app_options_cache()
            # 이후 변경은 작업 캐시에만 저장한다.
            if self.project_dir and self.paths:
                self.start_work_cache_from_current(mark_dirty=False)
            self.log("🧪 자동저장 모드 OFF: 변경 사항은 작업 캐시에만 저장됩니다.")

    def confirm_unsaved_before_switch(self):
        if not self.has_unsaved_changes:
            return True

        msg = QMessageBox(self)
        msg.setIcon(QMessageBox.Icon.Warning)
        msg.setWindowTitle(self.tr_ui("저장하지 않은 작업"))
        msg.setText(self.tr_ui("저장하지 않은 작업이 있습니다."))
        msg.setInformativeText(self.tr_ui("현재 프로젝트를 닫기 전에 저장할까요?"))
        btn_save = msg.addButton(self.tr_ui("저장"), QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton(self.tr_ui("저장 안 함"), QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_save:
            self.save_project()
            return not self.has_unsaved_changes
        if clicked == btn_discard:
            self.cleanup_work_cache()
            self.delete_temp_project_if_needed()
            self.has_unsaved_changes = False
            return True
        return False

    def closeEvent(self, event):
        """프로그램 종료 처리.

        최종화면의 인라인 텍스트 편집/QGraphics 상태가 열린 채로 종료 확인창이 뜨면
        focusOutEvent와 closeEvent가 겹쳐 예외가 날 수 있다. 종료 전에 현재 편집 상태를
        먼저 안전하게 확정하고, 종료 처리 중 예외가 나도 프로그램이 바로 튕기지 않게 막는다.
        """
        try:
            if getattr(self, "is_batch_running", False):
                QMessageBox.information(
                    self,
                    self.tr_ui("일괄 작업 중"),
                    self.tr_ui("일괄 작업 중에는 프로그램을 종료할 수 없습니다.\n작업이 끝난 뒤 다시 종료해 주세요."),
                )
                event.ignore()
                return

            if getattr(self, "_closing_confirmed", False):
                self.cleanup_external_open_runtime_info()
                event.accept()
                return

            self._app_is_closing = True

            # 핵심 보정: 최종화면 인라인 텍스트 편집 중 종료하면 QMessageBox 포커스 이동으로
            # finish_inline_text_edit()가 closeEvent 도중 재진입할 수 있다. 먼저 확정해서 안정화한다.
            if getattr(self, "inline_text_editor", None) is not None:
                try:
                    self.finish_inline_text_edit(commit=True, refresh=False)
                except Exception as e:
                    self.log(f"⚠️ 종료 전 텍스트 편집 확정 실패: {e}")

            # 최종화면/표의 현재 UI 상태를 가능한 한 data에 반영한다. 실패해도 종료 확인창은 유지한다.
            try:
                if getattr(self, "project_dir", None) and getattr(self, "paths", None):
                    self.commit_current_page_ui_to_data()
                    if getattr(self, "auto_save_enabled", False):
                        self.auto_save_project()
            except Exception as e:
                self.log(f"⚠️ 종료 전 현재 화면 상태 반영 실패: {e}")

            if self.has_unsaved_changes:
                msg = QMessageBox(self)
                msg.setIcon(QMessageBox.Icon.Warning)
                msg.setWindowTitle(self.tr_ui("저장하지 않은 작업"))
                msg.setText(self.tr_ui("저장하지 않은 작업이 있습니다."))
                msg.setInformativeText(self.tr_ui("종료하기 전에 프로젝트를 저장할까요?"))
                btn_save = msg.addButton(self.tr_ui("저장"), QMessageBox.ButtonRole.AcceptRole)
                btn_discard = msg.addButton(self.tr_ui("저장 안 함"), QMessageBox.ButtonRole.DestructiveRole)
                btn_cancel = msg.addButton(self.tr_ui("취소"), QMessageBox.ButtonRole.RejectRole)
                msg.setDefaultButton(btn_save)
                msg.exec()

                clicked = msg.clickedButton()
                if clicked == btn_cancel:
                    self._app_is_closing = False
                    event.ignore()
                    return
                if clicked == btn_save:
                    self.save_project()
                    if self.has_unsaved_changes:
                        self._app_is_closing = False
                        event.ignore()
                        return
                elif clicked == btn_discard:
                    try:
                        self.cleanup_work_cache()
                    except Exception as e:
                        self.log(f"⚠️ 작업 캐시 정리 실패: {e}")
                    try:
                        self.delete_temp_project_if_needed()
                    except Exception as e:
                        self.log(f"⚠️ 임시 프로젝트 삭제 실패: {e}")
                    self.has_unsaved_changes = False
            else:
                # 정상 종료 시 남은 작업 캐시는 삭제한다. 실패해도 종료 자체를 튕기게 만들지 않는다.
                try:
                    self.cleanup_work_cache()
                except Exception as e:
                    self.log(f"⚠️ 작업 캐시 정리 실패: {e}")

            self.cleanup_external_open_runtime_info()
            self._closing_confirmed = True
            event.accept()
        except Exception as e:
            self._app_is_closing = False
            try:
                import traceback
                detail = traceback.format_exc()
                self.log(f"❌ 종료 처리 중 오류: {e}")
                QMessageBox.critical(
                    self,
                    self.tr_ui("종료 오류"),
                    self.tr_ui("프로그램 종료 처리 중 오류가 발생했습니다.\n작업 보호를 위해 종료를 취소합니다.") + f"\n\n{detail}",
                )
            except Exception:
                pass
            event.ignore()

    def new_project_from_images(self):
        if not self.guard_project_action("새 프로젝트 만들기"):
            return
        if not self.confirm_unsaved_before_switch():
            return

        source_paths, _ = QFileDialog.getOpenFileNames(
            self,
            self.tr_ui("프로젝트에 넣을 이미지 선택"),
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not source_paths:
            return

        # 프로젝트 이름은 첫 생성 때 묻지 않는다.
        # 실제 이름은 .ysbt로 저장할 때 파일명 기준으로 확정된다.
        self.suggested_project_name = safe_project_name(Path(source_paths[0]).stem + "_project")
        project_dir = self.workspace_temp_project_dir(self.suggested_project_name)

        self.commit_current_page_ui_to_data()

        self.project_store = ProjectStore(project_dir)
        self.paths, self.data = self.project_store.create_from_images(project_dir, source_paths)
        self.page_text_undo_stacks = {}
        self.project_undo_stack = []
        self.project_redo_stack = []
        self.undo_boundary = None
        self.update_undo_redo_buttons()
        self.project_ui_view_states = {}
        self.project_store.write_manifest(project_name="unsaved_project")
        self.project_dir = project_dir
        self.record_recovery_project_dir(project_dir)
        self.ysbt_package_path = None
        self.is_temp_project = True
        self.update_window_title()
        self.idx = 0
        self.is_loading_project = False
        self.log(f"📁 새 임시 프로젝트 작업 폴더 생성: {project_dir}")
        self.log("💾 아직 YSBT 파일로 저장되지 않았습니다. [프로젝트 저장] 또는 [다른 이름으로 저장]을 눌러 .ysbt로 저장하세요.")
        self.has_unsaved_changes = True
        if not self.auto_save_enabled:
            self.start_work_cache_from_current(mark_dirty=True)
        self.reset_mode_to_original()
        self.show_editor()
        self.load()

    def open_project(self):
        """YSBT 전용 프로젝트 열기.

        v1.6부터 기본 프로젝트 열기는 .ysbt 패키지만 지원한다.
        구버전 폴더/project.json 열기 흐름은 아래에 주석으로 남겨두고,
        별도 메뉴인 [JSON으로 열기]에서만 project.json을 열 수 있게 분리한다.
        """
        if not self.guard_project_action("프로젝트 열기"):
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr_ui("YSBT 프로젝트 열기"),
            str(default_package_dir()),
            "YSBT Project (*.ysbt);;All Files (*.*)"
        )
        if not path:
            return

        self.open_project_path(path)

        # [LEGACY_DISABLED]
        # 예전에는 파일 선택을 취소하면 구버전 폴더 프로젝트(project.json)를
        # 열 수 있도록 폴더 선택창으로 넘어갔다.
        # 이제 기본 프로젝트 열기는 .ysbt에 올인하므로 이 흐름은 비활성화한다.
        # 나중에 필요하면 아래 흐름을 되살리면 된다.
        #
        # project_dir = QFileDialog.getExistingDirectory(
        #     self, self.tr_ui("구버전 프로젝트 폴더 선택"), str(workspaces_dir())
        # )
        # if project_dir:
        #     self.open_project_path(os.path.join(project_dir, PROJECT_FILENAME))

    def open_project_json(self):
        """구버전/디버그용 project.json 직접 열기. 기본 열기와 분리한다."""
        if not self.guard_project_action("JSON으로 열기"):
            return

        path, _ = QFileDialog.getOpenFileName(
            self,
            self.tr_ui("프로젝트 JSON 열기"),
            str(workspaces_dir()),
            "Project JSON (project.json);;JSON (*.json);;All Files (*.*)"
        )
        if not path:
            return

        self.open_project_path(path)

    def save_project(self):
        if not self.guard_project_action("프로젝트 저장"):
            return
        if not self.project_dir:
            self.log("⚠️ 프로젝트가 없습니다. 새 프로젝트를 먼저 만들어주세요.")
            return
        if not self.ysbt_package_path:
            # 새 프로젝트/구버전 폴더 프로젝트는 첫 저장 때 .ysbt 위치를 정한다.
            self.save_project_as()
            return

        self.begin_busy_state("프로젝트 저장")
        try:
            self.commit_current_page_ui_to_data()
            self.save_project_store(self.project_store)
            try:
                package_project(self.project_dir, self.ysbt_package_path)
            except Exception as e:
                QMessageBox.critical(self, self.tr_ui("YSBT 저장 실패"), f"{self.tr_ui("프로젝트는 작업 폴더에 저장했지만, YSBT 파일 저장에 실패했습니다.")}\n\n{e}")
                self.has_unsaved_changes = True
                return
            self.mark_saved_state()
            self.update_window_title()
            self.log(f"💾 프로젝트 저장 완료: {self.ysbt_package_path}")
            self.record_current_project_recent()

            # 자동저장 OFF에서는 저장본을 다시 로드한 뒤, 새 작업 캐시를 기준으로 이어간다.
            if not self.auto_save_enabled:
                self.reload_saved_project_from_disk(refresh_view=False)
                self.start_work_cache_from_current(mark_dirty=False)
                if self.cb_mode.currentIndex() >= 0:
                    self.load()
        finally:
            self.end_busy_state("프로젝트 저장")

    def ensure_save_as_output_parent(self, path_abs: str):
        """다른 이름으로 저장 대상 폴더가 없을 때 먼저 만든다."""
        parent = os.path.dirname(os.path.abspath(str(path_abs or "")))
        if parent and not os.path.isdir(parent):
            os.makedirs(parent, exist_ok=True)

    def _write_image_for_save_as_fallback(self, img, dst_path: str) -> bool:
        """원본 이미지 경로가 사라진 경우 메모리 이미지/작업 이미지를 새 저장용 파일로 복구한다."""
        if img is None:
            return False
        try:
            os.makedirs(os.path.dirname(dst_path), exist_ok=True)
            ext = Path(dst_path).suffix.lower()
            if ext not in (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff"):
                ext = ".png"
                dst_path = str(Path(dst_path).with_suffix(ext))

            if isinstance(img, (bytes, bytearray)):
                with open(dst_path, "wb") as f:
                    f.write(img)
                return os.path.exists(dst_path) and os.path.getsize(dst_path) > 0

            if isinstance(img, np.ndarray):
                encode_ext = ".jpg" if ext == ".jpeg" else ext
                ok, buf = cv2.imencode(encode_ext, img)
                if ok:
                    buf.tofile(dst_path)
                    return os.path.exists(dst_path) and os.path.getsize(dst_path) > 0
        except Exception:
            return False
        return False

    def prepare_save_as_paths_for_store(self, target_project_dir: str):
        """Save As용 이미지 경로 목록을 만든다.

        ProjectStore.save()는 원본 이미지 파일이 실제 디스크에 있어야 새 프로젝트 폴더로 복사할 수 있다.
        그런데 작업 폴더 이동/임시 캐시 정리/구버전 경로 문제로 self.paths의 일부가 사라진 경우
        다른 이름으로 저장이 [WinError 3]로 실패할 수 있다.

        이 함수는 저장 전에 각 이미지 경로를 확인하고,
        경로가 없으면 현재 프로젝트 images 폴더나 메모리의 ori/working_source로 복구한다.
        """
        prepared = list(self.paths or [])
        image_dir = os.path.join(str(target_project_dir), "images")
        os.makedirs(image_dir, exist_ok=True)

        project_images_dir = os.path.join(str(self.project_dir or ""), "images")
        known_exts = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".tif", ".tiff")

        for i, src in enumerate(prepared):
            src_text = str(src or "")
            if src_text and os.path.exists(src_text):
                continue

            candidates = []
            if src_text:
                candidates.append(src_text)
                if self.project_dir and not os.path.isabs(src_text):
                    candidates.append(os.path.join(str(self.project_dir), src_text))
                if self.project_dir:
                    candidates.append(os.path.join(str(self.project_dir), "images", os.path.basename(src_text)))

            if os.path.isdir(project_images_dir):
                try:
                    for ext in known_exts:
                        candidates.append(os.path.join(project_images_dir, f"{i + 1:04d}{ext}"))
                except Exception:
                    pass

            found = None
            for cand in candidates:
                try:
                    if cand and os.path.exists(cand):
                        found = os.path.abspath(cand)
                        break
                except Exception:
                    pass

            if found:
                prepared[i] = found
                continue

            curr = self.data.get(i, {}) if isinstance(self.data, dict) else {}
            ext = Path(src_text).suffix.lower() if src_text else ".png"
            if ext not in known_exts:
                ext = ".png"
            dst = os.path.join(image_dir, f"{i + 1:04d}{ext}")

            recovered = False
            img = curr.get("ori") if isinstance(curr, dict) else None
            if img is not None:
                recovered = self._write_image_for_save_as_fallback(img, dst)

            if not recovered and isinstance(curr, dict):
                working_source = curr.get("working_source")
                if working_source is not None:
                    recovered = self._write_image_for_save_as_fallback(working_source, dst)

            if not recovered:
                raise FileNotFoundError(
                    "다른 이름으로 저장할 원본 이미지 경로를 찾지 못했습니다.\n"
                    f"페이지: {i + 1}\n"
                    f"기존 경로: {src_text or '(비어 있음)'}"
                )

            prepared[i] = dst

        return prepared


    def save_project_as(self):
        if not self.guard_project_action("다른 이름으로 저장"):
            return
        if not self.paths:
            self.log("⚠️ 저장할 이미지/프로젝트가 없습니다.")
            return

        default_path = self.ysbt_package_path or self.current_package_default_path()
        path, _ = QFileDialog.getSaveFileName(
            self,
            self.tr_ui("다른 이름으로 YSBT 저장"),
            default_path,
            "YSBT Project (*.ysbt)"
        )
        if not path:
            return
        old_package_path = os.path.abspath(self.ysbt_package_path) if self.ysbt_package_path else None
        old_is_temp_project = bool(getattr(self, "is_temp_project", False))
        path_abs, display_project_name, new_uuid = self.make_ysbt_path_with_uuid_suffix(path)
        path_abs = os.path.abspath(path_abs)

        # 같은 .ysbt 파일을 고른 경우에는 일반 저장과 동일하게 처리한다.
        if old_package_path and os.path.abspath(path_abs).lower() == old_package_path.lower():
            self.save_project()
            return

        self.begin_busy_state("다른 이름으로 저장")
        try:
            self.commit_current_page_ui_to_data()

            # Save As는 새 .ysbt 패키지와 새 작업 폴더로 분기한다.
            # 기존 .ysbt 파일에는 현재까지의 미저장 변경분을 쓰지 않고,
            # 새 파일/새 작업 폴더가 현재 상태를 이어받는다.
            project_name = clean_workspace_name(display_project_name or Path(path_abs).stem)
            old_project_dir = self.project_dir
            old_work_cache = self.work_project_dir
            # .ysbt 파일명은 깔끔하게 유지하고, 실제 작업 폴더에만 uuid 짧은값을 붙인다.
            new_project_dir = self.workspace_project_dir(project_name, code=new_uuid[:8], append_code=True)

            try:
                self.ensure_save_as_output_parent(path_abs)
                new_store = ProjectStore(new_project_dir)
                # ProjectStore.save()는 전달받은 paths를 새 작업 폴더 내부 이미지 경로로 고정한다.
                # 실패 시 기존 self.paths가 오염되지 않도록 복사본을 사용하고, 성공 후에만 반영한다.
                save_as_paths = self.prepare_save_as_paths_for_store(new_project_dir)
                self.save_project_store(new_store, paths=save_as_paths)
                new_store.write_manifest(package_source=path_abs, project_name=project_name, project_uuid=new_uuid)
                package_project(new_project_dir, path_abs, project_name=project_name, project_uuid=new_uuid)
            except Exception as e:
                QMessageBox.critical(self, self.tr_ui("YSBT 저장 실패"), f"{self.tr_ui('YSBT 파일을 저장하지 못했습니다.')}\n{path_abs}\n\n{e}")
                self.has_unsaved_changes = True
                return

            # 현재 작업은 새 파일/새 작업 폴더로 전환한다.
            self.paths = save_as_paths
            self.project_dir = new_project_dir
            self.project_store = ProjectStore(new_project_dir)
            self.ysbt_package_path = path_abs
            self.suggested_project_name = display_project_name
            self.is_temp_project = False
            self.update_window_title()

            # 기존 임시 캐시/임시 프로젝트 정리.
            if old_work_cache and old_work_cache != self.work_project_dir and os.path.exists(old_work_cache):
                try:
                    shutil.rmtree(old_work_cache, ignore_errors=True)
                except Exception:
                    pass
            if old_is_temp_project and old_project_dir and os.path.abspath(old_project_dir) != os.path.abspath(new_project_dir):
                try:
                    old_abs = os.path.abspath(old_project_dir)
                    roots = [os.path.abspath(str(temp_dir())), os.path.abspath(str(workspaces_dir()))]
                    if os.path.basename(old_abs).startswith("unsaved_") and any(old_abs.startswith(root) for root in roots) and os.path.exists(old_abs):
                        shutil.rmtree(old_abs, ignore_errors=True)
                except Exception:
                    pass
            self.work_project_dir = None
            self.work_project_store = None

            # Save As는 "현재 상태를 새 파일 B로 분기"하는 동작이다.
            # 따라서 기존 파일 A의 작업 폴더는 B로 갱신/삭제하지 않고, A.ysbt에 저장된 상태로 되돌려 둔다.
            # A와 B의 작업 폴더가 동시에 남아 있어야 사용자가 기대하는 Save As 동작과 맞다.
            try:
                if old_package_path and old_project_dir and os.path.abspath(old_project_dir) != os.path.abspath(new_project_dir):
                    old_abs = os.path.abspath(old_project_dir)
                    roots = [os.path.abspath(str(workspaces_dir())), os.path.abspath(str(temp_dir()))]
                    if any(old_abs.startswith(root) for root in roots) and os.path.exists(old_package_path):
                        # 자동저장 ON 등으로 A의 작업 폴더에 미저장 변경분이 들어갔을 수 있으므로,
                        # A.ysbt 패키지 기준으로 A 작업 폴더를 조용히 복구한다.
                        if os.path.exists(old_abs):
                            shutil.rmtree(old_abs, ignore_errors=True)
                        extract_ysb_package(old_package_path, workspaces_dir(), reuse_existing=False)
            except Exception as e:
                try:
                    self.log(f"⚠️ Save As 이후 기존 작업 폴더 복구 실패: {e}")
                except Exception:
                    pass

            self.reload_saved_project_from_disk(refresh_view=False)
            self.mark_saved_state()
            self.log(f"💾 다른 이름으로 저장 완료: {self.ysbt_package_path}")
            self.record_current_project_recent()
            if not self.auto_save_enabled:
                self.start_work_cache_from_current(mark_dirty=False)
            self.load()
        finally:
            self.end_busy_state("다른 이름으로 저장")

    def auto_save_project(self):
        if self.is_loading_project or self.is_autosaving:
            return
        if not self.project_dir:
            return
        self.is_autosaving = True
        try:
            # 자동저장 진입 시점에 우측 표 텍스트와 최종화면 텍스트 좌표를 먼저 data에 고정한다.
            # 이전 버전은 마스크/브러시는 화면에서 바로 읽어왔지만, 텍스트 이동/수정은
            # 일부 경로에서 data 반영이 늦어져 자동저장 결과가 빠질 수 있었다.
            self.commit_current_page_ui_to_data(include_mask=False)
            if self.auto_save_enabled:
                self.save_project_store(self.project_store)
                # 자동저장 ON은 실제 프로젝트 파일까지 확정한다.
                # .ysbt가 있는 프로젝트는 작업 폴더 project.json만이 아니라 패키지 파일도 즉시 갱신한다.
                # 자동저장 OFF일 때는 아래 save_to_work_cache()만 사용하므로 실제 파일은 건드리지 않는다.
                if self.ysbt_package_path and not self.is_temp_project:
                    try:
                        package_project(self.project_dir, self.ysbt_package_path)
                    except Exception as e:
                        self.has_unsaved_changes = True
                        self.log(f"⚠️ 자동저장 패키지 갱신 실패: {e}")
                        return
                # 새 임시 프로젝트는 폴더에는 저장되어도 아직 .ysbt 패키지가 없으므로 저장 필요 상태를 유지한다.
                self.has_unsaved_changes = bool(self.is_temp_project or not self.ysbt_package_path)
            else:
                self.save_to_work_cache()
        finally:
            self.is_autosaving = False

    def sync_final_text_scene_to_data(self):
        """최종화면의 실제 텍스트 아이템 위치를 현재 페이지 data에 동기화한다.

        일반 드래그/변형 드래그는 대부분 해당 이벤트에서 data를 갱신하지만,
        자동저장/페이지 이동/닫기처럼 이벤트 타이밍이 섞이는 경우를 위해
        저장 직전 화면에 남아 있는 TypesettingItem의 좌표를 한 번 더 확정한다.
        """
        if getattr(self, "_text_scene_sync_lock", False) or getattr(self, "_text_undo_restore_lock", False):
            return False
        scene = self._safe_graphics_scene()
        if scene is None:
            return False
        curr = self.data.get(self.idx)
        if not curr:
            return False

        self._text_scene_sync_lock = True
        changed = False
        try:
            data_list = curr.get('data', []) or []
            by_id = {str(d.get('id')): d for d in data_list if isinstance(d, dict)}
            try:
                scene_items = list(scene.items())
            except RuntimeError:
                return False
            except Exception:
                return False
            for item in scene_items:
                if not isinstance(item, TypesettingItem):
                    continue
                d = getattr(item, 'data', None)
                if not isinstance(d, dict):
                    continue
                if d.get('pending_new_text'):
                    continue
                item_id = str(d.get('id'))
                target = by_id.get(item_id)
                if target is None:
                    continue

                rect = list(target.get('rect') or [0, 0, 1, 1])
                while len(rect) < 4:
                    rect.append(1)
                try:
                    align = (target.get('align') or 'center').lower()
                    if align == 'left':
                        anchor_x = float(rect[0])
                    elif align == 'right':
                        anchor_x = float(rect[0]) + float(rect[2])
                    else:
                        anchor_x = float(rect[0]) + float(rect[2]) / 2.0

                    path_rect = getattr(item, '_text_path_rect', item.boundingRect())
                    item_pos = item.pos()
                    rect_x = float(rect[0])
                    rect_y = float(rect[1])
                    rect_w = max(1.0, float(rect[2]))
                    rect_h = max(1.0, float(rect[3]))
                    if align == 'left':
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.left()) - rect_x))
                    elif align == 'right':
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.right()) - (rect_x + rect_w)))
                    else:
                        new_x_off = int(round(float(item_pos.x()) + float(path_rect.center().x()) - (rect_x + rect_w / 2.0)))
                    new_y_off = int(round(float(item_pos.y()) + float(path_rect.center().y()) - (rect_y + rect_h / 2.0)))
                except Exception:
                    continue

                old_x_off = int(target.get('x_off', 0) or 0)
                old_y_off = int(target.get('y_off', 0) or 0)
                if new_x_off != old_x_off or new_y_off != old_y_off:
                    target['x_off'] = new_x_off
                    target['y_off'] = new_y_off
                    changed = True
            return changed
        finally:
            self._text_scene_sync_lock = False

    def commit_current_page_ui_to_data(self, include_mask=True):
        curr = self.data.get(self.idx)
        if not curr:
            return

        # 최종화면 탭에서는 화면 위 텍스트 아이템의 현재 위치를 저장 데이터에 먼저 고정한다.
        self.sync_final_text_scene_to_data()

        # 표 상태 반영
        for row in range(1, self.tab.rowCount()):
            data_index = row - 1
            if data_index < 0 or data_index >= len(curr.get('data', [])):
                continue

            curr['data'][data_index]['use_inpaint'] = self.get_table_check_state(row)

            orig_item = self.tab.item(row, 2)
            if orig_item is not None:
                curr['data'][data_index]['text'] = orig_item.text()

            trans_item = self.tab.item(row, 3)
            curr['data'][data_index]['translated_text'] = trans_item.text() if trans_item else ""

        # 화면 마스크 자동 저장은 평상시 현재 페이지에서만 허용.
        # 페이지 로딩/일괄 작업 중에는 이전 화면의 마스크가 다른 페이지에 섞일 수 있으므로 차단한다.
        if (not include_mask) or self.is_page_loading or self.is_batch_running:
            return

        if self.cb_mode.currentIndex() in [2, 3]:
            m = self.view.get_mask_np()
            if m is not None:
                self.set_active_mask(curr, m, self.cb_mode.currentIndex())
                curr['mask_toggle_enabled'] = self.mask_toggle_enabled

    def on_final_paint_opacity_changed(self, value):
        self.final_paint_opacity = max(1, min(100, int(value)))
        self.log(f"🖌️ 최종 브러시 불투명도: {self.final_paint_opacity}%")

    def update_final_paint_option_bar_visibility(self):
        show = (
            hasattr(self, "final_paint_option_bar")
            and self.cb_mode.currentIndex() == 4
            and getattr(self.view, "draw_mode", None) == "draw"
        )
        if hasattr(self, "final_paint_option_bar"):
            self.final_paint_option_bar.setVisible(bool(show))
        if hasattr(self, "sb_final_paint_opacity"):
            self.sb_final_paint_opacity.blockSignals(True)
            try:
                self.sb_final_paint_opacity.setValue(int(self.final_paint_opacity))
            finally:
                self.sb_final_paint_opacity.blockSignals(False)

    def update_final_paint_z_order(self):
        """최종 페인팅 레이어는 항상 아래/위 두 장으로 고정한다."""
        below = getattr(self.view, "final_paint_item", None)
        above = getattr(self.view, "final_paint_above_item", None)
        if below is not None:
            below.setZValue(8)
        if above is not None:
            above.setZValue(80)

    def on_final_paint_above_text_toggled(self, checked):
        # 기존에 그린 레이어의 위치는 바꾸지 않는다.
        # 이 토글은 이후 새로 그리는 브러시가 들어갈 레이어만 선택한다.
        old_state = bool(getattr(self, "_last_final_paint_above_text", getattr(self, "final_paint_above_text", False)))
        new_state = bool(checked)
        if (
            old_state != new_state
            and not getattr(self, "_project_undo_restore_lock", False)
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
        ):
            try:
                rec = self.make_project_undo_record("텍스트 위 페인팅 ON/OFF")
                rec.setdefault("ui_state", self.current_project_ui_state())
                rec["ui_state"]["final_paint_above_text"] = old_state
                self.append_project_undo_record(rec)
            except Exception:
                pass
        self.final_paint_above_text = new_state
        self._last_final_paint_above_text = new_state
        if hasattr(self, "act_final_paint_above_text"):
            self.act_final_paint_above_text.setText("T↑" if self.final_paint_above_text else "T↓")
        state = "ON" if checked else "OFF"
        self.log(f"🎚️ 새 브러시를 텍스트 위에 그리기: {state}")
        self.auto_save_project()

    def toggle_final_paint_above_text(self):
        if hasattr(self, "act_final_paint_above_text"):
            self.act_final_paint_above_text.toggle()
        else:
            self.on_final_paint_above_text_toggled(not self.final_paint_above_text)

    def adjust_final_paint_opacity(self, delta):
        value = max(1, min(100, int(self.final_paint_opacity) + int(delta)))
        self.final_paint_opacity = value
        if hasattr(self, "sb_final_paint_opacity"):
            self.sb_final_paint_opacity.blockSignals(True)
            try:
                self.sb_final_paint_opacity.setValue(value)
            finally:
                self.sb_final_paint_opacity.blockSignals(False)
        self.log(f"🖌️ 최종 브러시 불투명도: {value}%")

    def final_paint_rgba_from_value(self, value):
        if value is None:
            return None
        try:
            if isinstance(value, (bytes, bytearray)):
                arr = np.frombuffer(value, np.uint8)
                img = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
            elif isinstance(value, np.ndarray):
                img = value.copy()
            else:
                return None

            if img is None:
                return None
            if img.ndim == 2:
                img = cv2.cvtColor(img, cv2.COLOR_GRAY2RGBA)
            elif img.ndim == 3 and img.shape[2] == 3:
                img = cv2.cvtColor(img, cv2.COLOR_BGR2RGBA)
            elif img.ndim == 3 and img.shape[2] == 4:
                # cv2 imdecode는 BGRA이므로 RGBA로 변환
                img = cv2.cvtColor(img, cv2.COLOR_BGRA2RGBA)
            return img
        except Exception:
            return None

    def compose_final_paint_on_bgr(self, base_bgr, paint_value):
        if base_bgr is None:
            return None
        base = base_bgr.copy()
        paint = self.final_paint_rgba_from_value(paint_value)
        if paint is None:
            return base
        h, w = base.shape[:2]
        if paint.shape[0] != h or paint.shape[1] != w:
            paint = cv2.resize(paint, (w, h), interpolation=cv2.INTER_LINEAR)
        alpha = paint[:, :, 3:4].astype(np.float32) / 255.0
        rgb = paint[:, :, :3].astype(np.float32)
        bgr = rgb[:, :, ::-1]
        out = base.astype(np.float32) * (1.0 - alpha) + bgr * alpha
        return np.clip(out, 0, 255).astype(np.uint8)

    def final_base_image_for_page(self, page_idx):
        curr = self.data.get(page_idx)
        if not curr:
            return None
        base = self.bg_clean_to_np_image(curr.get('bg_clean'))
        if base is not None:
            return base
        return self.get_source_display_image(page_idx)

    def on_final_paint_edited(self):
        if self.is_page_loading or self.is_batch_running:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        curr['final_paint'] = self.view.get_final_paint_png_bytes()
        if hasattr(self.view, "get_final_paint_above_png_bytes"):
            curr['final_paint_above'] = self.view.get_final_paint_above_png_bytes()
        self.log("💾 최종 페인팅 자동 저장")
        self.auto_save_project()

    def pick_final_paint_color_from_scene(self, x, y):
        if self.cb_mode.currentIndex() != 4:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        base = self.final_base_image_for_page(self.idx)
        if base is None:
            return
        img = self.compose_final_paint_on_bgr(base, curr.get('final_paint'))
        img = self.compose_final_paint_on_bgr(img, curr.get('final_paint_above'))
        h, w = img.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return
        b, g, r = [int(v) for v in img[y, x]]
        self.final_paint_color = QColor(r, g, b).name(QColor.NameFormat.HexRgb).upper()
        self.update_color_button_styles()
        self.log(f"🧪 스포이드: {self.final_paint_color}")

    def apply_final_paint_to_background(self):
        if self.cb_mode.currentIndex() != 4:
            self.log("⚠️ 최종화면에서만 사용할 수 있습니다.")
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        paint_bytes = self.view.get_final_paint_png_bytes()
        paint_above_bytes = self.view.get_final_paint_above_png_bytes() if hasattr(self.view, "get_final_paint_above_png_bytes") else None
        if paint_bytes is None and paint_above_bytes is None:
            self.log("⚠️ 반영할 최종 페인팅이 없습니다.")
            return

        base = self.final_base_image_for_page(self.idx)
        if base is None:
            self.log("⚠️ 반영할 배경 이미지가 없습니다.")
            return

        merged = self.compose_final_paint_on_bgr(base, paint_bytes)
        merged = self.compose_final_paint_on_bgr(merged, paint_above_bytes)
        encoded = self.encode_np_image_to_png_bytes(merged)
        if encoded is not None:
            curr['bg_clean'] = encoded
        else:
            curr['bg_clean'] = merged

        # "원본으로 반영"은 실제 파일을 덮어쓰지 않고,
        # 프로젝트 내부 작업중 원본(working_source)을 최신 기준으로 교체한다.
        self.set_working_source_image(curr, merged)

        curr['final_paint'] = None
        curr['final_paint_above'] = None
        self.auto_save_project()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log("📌 최종 페인팅을 원본 탭 기준 이미지로 반영했습니다.")

    def create_final_text_at(self, x, y):
        if self.cb_mode.currentIndex() != 4:
            return
        curr = self.data.get(self.idx)
        if not curr:
            return

        data_list = curr.setdefault('data', [])
        max_id = 0
        for item in data_list:
            try:
                max_id = max(max_id, int(item.get('id', 0)))
            except Exception:
                pass
        new_id = max_id + 1

        w, h = 260, 80
        temp_data = {
            'id': new_id,
            'text': '',
            'translated_text': '',
            'rect': [int(x - w / 2), int(y - h / 2), w, h],
            'use_inpaint': True,
            'font_family': self.cb_font.currentFont().family(),
            'font_size': int(self.sb_font_size.value()),
            'stroke_width': int(self.sb_strk.value()),
            'text_color': str(self.default_text_color or "#000000"),
            'stroke_color': str(self.default_stroke_color or "#FFFFFF"),
            'align': self.default_align,
            'x_off': 0,
            'y_off': 0,
            'manual_text_rect': True,
            'text_anchor_mode': 'text',
            'force_show': True,
            'pending_new_text': True,
        }

        # 아직 우측 텍스트 행에는 넣지 않는다.
        # 실제 텍스트 입력이 완료될 때 finish_inline_text_edit()에서 data_list에 추가한다.
        item = TypesettingItem(
            temp_data,
            self.cb_font.currentFont().family(),
            self.sb_font_size.value(),
            self.sb_strk.value(),
            self.on_text_item_moved,
            text_color=self.default_text_color,
            stroke_color=self.default_stroke_color,
            align=self.default_align,
        )
        item.main_window = self
        self.view.scene.addItem(item)
        item.setZValue(30)
        item.setSelected(True)
        self.start_inline_text_edit(item)
        self.log(f"➕ 새 텍스트 영역 생성 대기 (ID: {new_id})")


    def on_view_mask_edited(self):
        # 붓질이 끝났을 때 현재 페이지의 마스크만 자동 저장한다.
        if self.is_page_loading or self.is_batch_running:
            return

        curr = self.data.get(self.idx)
        if not curr:
            return

        m = self.view.get_mask_np()
        if m is None:
            return

        mode = self.cb_mode.currentIndex()
        if mode == 2:
            self.set_active_mask(curr, m, mode)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
            self.log("💾 텍스트 마스크 자동 저장")
        elif mode == 3:
            self.set_active_mask(curr, m, mode)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
            self.log("💾 페인팅 마스크 자동 저장")
        else:
            return

        self.auto_save_project()

    # =========================================================
    # 일반 UI 함수
    # =========================================================
    def flush_pending_log_messages(self):
        pending = list(getattr(self, "_pending_log_messages", []) or [])
        if not pending or not hasattr(self, "log_w") or self.log_w is None:
            return
        self._pending_log_messages = []
        for msg in pending:
            try:
                self.log_w.append(str(msg))
            except Exception:
                pass
        try:
            self.log_w.verticalScrollBar().setValue(self.log_w.verticalScrollBar().maximum())
        except Exception:
            pass

    def log(self, m):
        try:
            m = self.tr_msg(m)
        except Exception:
            pass
        if not hasattr(self, "log_w") or self.log_w is None:
            try:
                self._pending_log_messages.append(str(m))
            except Exception:
                self._pending_log_messages = [str(m)]
            try:
                print(str(m))
            except Exception:
                pass
            return
        try:
            self.log_w.append(str(m))
            self.log_w.verticalScrollBar().setValue(self.log_w.verticalScrollBar().maximum())
        except Exception:
            try:
                print(str(m))
            except Exception:
                pass

    def get_special_shortcuts(self):
        symbol_map = {}
        for key, (_label, symbol) in TEXT_SYMBOLS.items():
            symbol_map[symbol] = self.shortcut_settings.seq("text_" + key)
        return symbol_map

    def get_linebreak_shortcut(self):
        return self.shortcut_settings.seq("text_linebreak")

    def on_translation_provider_changed(self, save=True):
        provider = self.cb_trans_provider.currentData() or "openai"
        default_value = 8 if provider == "deepseek" else (50 if provider == "google" else (10 if provider == "gemini" else 20))
        value = self.trans_chunk_sizes.get(provider, default_value)

        self.sb_trans_chunk.blockSignals(True)
        try:
            self.sb_trans_chunk.setValue(int(value))
        finally:
            self.sb_trans_chunk.blockSignals(False)

        if save and hasattr(self, "api_settings"):
            try:
                self.api_settings.selected_translation_provider = str(provider)
                ApiSettingsStore.save(self.api_settings)
                apply_settings_to_config(self.api_settings)
            except Exception:
                pass

    def on_translation_chunk_changed(self, value):
        provider = self.cb_trans_provider.currentData() or "openai"
        self.trans_chunk_sizes[provider] = int(value)

    def get_current_translation_chunk_size(self):
        provider = self.cb_trans_provider.currentData() or "openai"
        return int(self.trans_chunk_sizes.get(provider, self.sb_trans_chunk.value()))

    def open_text_number_width_dialog(self):
        """분석도 노란 텍스트 번호 박스 너비를 즉시 조정한다."""
        dlg = QDialog(self)
        dlg.setWindowTitle("텍스트 넘버 크기 변경")
        dlg.resize(360, 120)

        layout = QVBoxLayout(dlg)
        info = QLabel("분석도에 표시되는 노란 텍스트 번호 박스의 너비값을 조정합니다.")
        info.setWordWrap(True)
        layout.addWidget(info)

        line = QHBoxLayout()
        line.addWidget(QLabel("너비값"))
        spin = QSpinBox()
        spin.setRange(20, 300)
        spin.setValue(int(getattr(self, "analysis_number_box_width", 40)))
        spin.setSuffix(" px")
        spin.setKeyboardTracking(True)
        spin.selectAll()
        line.addWidget(spin, 1)
        layout.addLayout(line)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        layout.addWidget(buttons)

        old_value = int(getattr(self, "analysis_number_box_width", 40))

        def apply_value(value):
            self.analysis_number_box_width = int(value)
            self.save_app_options_cache()
            if self.cb_mode.currentIndex() == 1:
                self.mode_chg(1)

        spin.valueChanged.connect(apply_value)
        buttons.accepted.connect(dlg.accept)
        buttons.rejected.connect(dlg.reject)

        spin.setFocus()
        spin.selectAll()

        result = dlg.exec()
        if result != QDialog.DialogCode.Accepted:
            self.analysis_number_box_width = old_value
            self.save_app_options_cache()
            if self.cb_mode.currentIndex() == 1:
                self.mode_chg(1)
        else:
            apply_value(spin.value())
            self.log(f"🔢 텍스트 넘버 박스 너비 변경: {spin.value()}px")

    def open_shortcut_settings_dialog(self):
        dlg = ShortcutSettingsDialog(self.shortcut_settings, self)
        if not dlg.exec():
            return
        new_settings = dlg.get_settings()
        # 단축키 창에서 비활성화된 기존 단축키 상태를 유지하면서 매크로도 보존한다.
        if not hasattr(new_settings, "macros"):
            new_settings.macros = getattr(self.shortcut_settings, "macros", [])
        self.apply_pending_item_preset_disables_for_shortcut_settings(getattr(dlg, "_pending_disabled_item_presets", set()), new_settings)
        if not self.resolve_item_preset_conflicts_for_new_shortcut_settings(new_settings, parent=self, source_label="단축키"):
            self.log("↩️ 단축키 설정 저장 취소: 개별 글꼴 프리셋 단축키 충돌")
            return
        self.shortcut_settings = new_settings
        ShortcutSettingsStore.save(self.shortcut_settings)
        self.apply_shortcuts()
        self.log("⌨️ 단축키 설정 캐시 저장 완료")

    def open_macro_settings_dialog(self):
        dlg = MacroSettingsDialog(self.shortcut_settings, self)
        if not dlg.exec():
            return
        new_settings = dlg.get_settings()
        self.apply_pending_item_preset_disables_for_shortcut_settings(getattr(dlg, "_pending_disabled_item_presets", set()), new_settings)
        if not self.resolve_item_preset_conflicts_for_new_shortcut_settings(new_settings, parent=self, source_label="매크로"):
            self.log("↩️ 매크로 설정 저장 취소: 개별 글꼴 프리셋 단축키 충돌")
            return
        self.shortcut_settings = new_settings
        ShortcutSettingsStore.save(self.shortcut_settings)
        self.apply_shortcuts()
        self.log("🧩 매크로 설정 캐시 저장 완료")

    def macro_action_requires_undo_boundary(self, key):
        """Undo로 복원하면 상태가 꼬일 수 있는 매크로 단계인지 판단한다.

        분석/번역/인페인팅 계열은 외부/API 결과 또는 큰 처리 결과를 반영하므로
        매크로 전체를 Undo 경계로 처리한다. 그 외 일반 편집 매크로는 1개의
        Undo 스냅샷으로 되돌릴 수 있게 둔다.
        """
        key = str(key or "")
        return key in {
            "work_analyze",
            "paint_reanalyze",
            "work_translate",
            "work_inpaint",
            "batch_analyze",
            "batch_translate",
            "batch_inpaint",
        }

    def macro_actions_require_undo_boundary(self, actions):
        return any(self.macro_action_requires_undo_boundary(k) for k in (actions or []))

    def macro_wait_kind_for_key(self, key):
        """매크로에서 다음 단계로 넘어가기 전에 완료 신호를 기다려야 하는 기능."""
        if key in ("work_analyze", "paint_reanalyze"):
            return "analysis"
        if key == "work_inpaint":
            return "inpaint"
        if key.startswith("batch_"):
            return "batch"
        return ""

    def macro_batch_key_for_mode(self, mode):
        return {
            "analyze": "batch_analyze",
            "translate": "batch_translate",
            "inpaint": "batch_inpaint",
            "export": "batch_export",
        }.get(str(mode or ""), "")

    def run_macro(self, macro):
        name = str(macro.get("name", "매크로"))
        actions = list(macro.get("actions", []) or [])
        if not actions:
            self.log(f"⚠️ 매크로 '{name}'에 등록된 기능이 없습니다.")
            return

        if self.macro_running:
            QMessageBox.information(self, self.tr_ui("매크로 실행 중"), self.tr_msg("이미 실행 중인 매크로가 있습니다. 현재 매크로가 끝난 뒤 다시 실행해주세요."))
            return

        has_batch = any(str(k).startswith("batch_") for k in actions)
        if has_batch:
            ans = QMessageBox.question(
                self,
                "매크로 실행 확인",
                f"'{name}' 매크로에 일괄 작업이 포함되어 있습니다.\n실행할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                self.log(f"↩️ 매크로 취소: {name}")
                return

        has_undo_boundary = self.macro_actions_require_undo_boundary(actions)
        macro_undo_record = None
        if not has_undo_boundary:
            # 일반 편집 매크로는 내부 단계별 Undo를 쌓지 않고,
            # 매크로 실행 직전 상태 1개만 저장해서 Ctrl+Z 한 번으로 되돌린다.
            full_project = any(str(k).startswith("batch_") or str(k).endswith("_batch") for k in actions)
            macro_undo_record = self.make_project_undo_record(f"매크로 실행: {name}", full_project=full_project)

        self.macro_running = True
        self.macro_queue = list(actions)
        self.macro_current = None
        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current_name = name
        self.macro_executed_any = False
        self.macro_has_undo_boundary = has_undo_boundary
        self.macro_undo_record = macro_undo_record

        self.log(f"🧩 매크로 실행: {name} / {len(self.macro_queue)}단계")
        QTimer.singleShot(0, self.run_next_macro_step)

    def run_next_macro_step(self):
        if not self.macro_running:
            return

        if not self.macro_queue:
            name = self.macro_current_name or "매크로"
            executed_any = bool(getattr(self, "macro_executed_any", False))
            has_boundary = bool(getattr(self, "macro_has_undo_boundary", False))
            macro_undo_record = getattr(self, "macro_undo_record", None)
            self.log(f"✅ 매크로 완료: {name}")
            self.macro_running = False
            self.macro_current = None
            self.macro_waiting_key = None
            self.macro_waiting_kind = None
            self.macro_current_name = ""
            self.macro_executed_any = False
            self.macro_has_undo_boundary = False
            self.macro_undo_record = None
            if executed_any:
                if has_boundary:
                    self.break_undo_chain("macro", name)
                elif macro_undo_record:
                    old_allow = getattr(self, "_macro_allow_undo_append", False)
                    self._macro_allow_undo_append = True
                    try:
                        self.append_project_undo_record(macro_undo_record)
                    finally:
                        self._macro_allow_undo_append = old_allow
                    self.update_undo_redo_buttons()
                    self.log(
                        f"↶ Macro undo snapshot saved: {name}"
                        if getattr(self, "ui_language", LANG_KO) == LANG_EN else
                        f"↶ 매크로 Undo 기록 생성: {name}"
                    )
            return

        key = self.macro_queue.pop(0)
        self.macro_current = key
        action = self.actions.get(key)

        if action is None:
            self.log(f"⚠️ [{self.macro_current_name}] 매크로 기능 없음: {key}")
            QTimer.singleShot(0, self.run_next_macro_step)
            return

        if not action.isEnabled():
            self.log(f"⚠️ [{self.macro_current_name}] 비활성 기능 건너뜀: {action.text()}")
            QTimer.singleShot(0, self.run_next_macro_step)
            return

        wait_kind = self.macro_wait_kind_for_key(key)
        self.macro_waiting_key = key if wait_kind else None
        self.macro_waiting_kind = wait_kind or None

        self.log(f"🧩 [{self.macro_current_name}] 단계 실행: {action.text()}")

        try:
            self.macro_executed_any = True
            action.trigger()
            QApplication.processEvents()
        except Exception as e:
            self.log(f"❌ [{self.macro_current_name}] 매크로 중단: {key} / {e}")
            self.stop_macro_queue()
            return

        if wait_kind:
            # 비동기 작업은 워커가 실제로 시작됐는지 잠깐 뒤 확인한다.
            # 시작되지 않은 경우(취소/데이터 없음/키 없음 등)는 매크로가 무한 대기하지 않도록 다음 단계로 넘긴다.
            QTimer.singleShot(250, lambda k=key, wk=wait_kind: self.verify_macro_wait_started(k, wk))
        else:
            # 동기 작업은 함수가 끝난 뒤 바로 다음 단계.
            QTimer.singleShot(0, self.run_next_macro_step)

    def verify_macro_wait_started(self, key, wait_kind):
        if not self.macro_running or self.macro_waiting_key != key:
            return

        running = False
        try:
            if wait_kind == "analysis":
                running = hasattr(self, "w") and self.w is not None and self.w.isRunning()
            elif wait_kind == "inpaint":
                running = hasattr(self, "iw") and self.iw is not None and self.iw.isRunning()
            elif wait_kind == "batch":
                running = hasattr(self, "bw") and self.bw is not None and self.bw.isRunning()
        except Exception:
            running = False

        if not running:
            self.log(f"↪️ [{self.macro_current_name}] 단계 대기 생략: 작업이 시작되지 않음 ({key})")
            self.macro_mark_current_step_done(key)

    def macro_mark_current_step_done(self, key=None):
        if not self.macro_running:
            return

        if key and self.macro_waiting_key and key != self.macro_waiting_key:
            return

        if self.macro_waiting_key:
            self.log(f"✅ [{self.macro_current_name}] 단계 완료: {self.macro_waiting_key}")

        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current = None
        QTimer.singleShot(0, self.run_next_macro_step)

    def stop_macro_queue(self):
        self.macro_running = False
        self.macro_queue = []
        self.macro_current = None
        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current_name = ""
        self.macro_has_undo_boundary = False
        self.macro_undo_record = None

    def current_transform_data_item(self):
        curr = self.data.get(self.idx)
        if not curr:
            return None
        for d in curr.get('data', []) or []:
            if d.get('_transform_mode', False):
                return d
        return None

    def is_text_transform_active(self):
        return self.current_transform_data_item() is not None

    def view_state_key(self, page_idx=None, mode=None):
        if page_idx is None:
            page_idx = getattr(self, "idx", 0)
        if mode is None:
            try:
                mode = self.cb_mode.currentIndex()
            except Exception:
                mode = getattr(self, "last_mode", 0)
        return f"{int(page_idx)}:{int(mode)}"

    def capture_view_state(self):
        """현재 뷰의 확대율/이동 위치를 JSON 저장 가능한 값으로 캡처한다."""
        try:
            tr = self.view.transform()
            return {
                "transform": [
                    float(tr.m11()), float(tr.m12()), float(tr.m13()),
                    float(tr.m21()), float(tr.m22()), float(tr.m23()),
                    float(tr.m31()), float(tr.m32()), float(tr.m33()),
                ],
                "h_scroll": int(self.view.horizontalScrollBar().value()),
                "v_scroll": int(self.view.verticalScrollBar().value()),
            }
        except Exception:
            return {}

    def apply_view_state(self, state):
        if getattr(self, "_app_is_closing", False):
            return False
        if not isinstance(state, dict) or not state:
            return False
        vals = state.get("transform") or []
        try:
            if len(vals) == 9:
                self.view.setTransform(QTransform(*[float(x) for x in vals]))
            if "h_scroll" in state:
                self.view.horizontalScrollBar().setValue(int(state.get("h_scroll") or 0))
            if "v_scroll" in state:
                self.view.verticalScrollBar().setValue(int(state.get("v_scroll") or 0))
            return True
        except Exception:
            return False

    def restore_current_view_state_later(self, page_idx=None, mode=None):
        try:
            key = self.view_state_key(self.idx if page_idx is None else page_idx, self.cb_mode.currentIndex() if mode is None else mode)
            state = copy.deepcopy((getattr(self, "project_ui_view_states", {}) or {}).get(key) or {})
            if not state:
                return False
            self.apply_view_state(state)
            QTimer.singleShot(0, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            QTimer.singleShot(30, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            QTimer.singleShot(80, lambda st=copy.deepcopy(state): self.apply_view_state(st))
            return True
        except Exception:
            return False

    def remember_current_view_state(self):
        if not hasattr(self, "view") or not hasattr(self, "cb_mode"):
            return
        try:
            key = self.view_state_key(self.idx, self.cb_mode.currentIndex())
            self.project_ui_view_states[key] = self.capture_view_state()
        except Exception:
            pass

    def restore_project_ui_state(self, ui_state, refresh=False):
        if not isinstance(ui_state, dict):
            return False
        old_restore = getattr(self, "_project_undo_restore_lock", False)
        self._project_undo_restore_lock = True
        try:
            if hasattr(self, "cb_show_final_text") and "show_final_text" in ui_state:
                self.cb_show_final_text.blockSignals(True)
                try:
                    self.cb_show_final_text.setChecked(bool(ui_state.get("show_final_text")))
                    self._last_show_final_text_checked = bool(ui_state.get("show_final_text"))
                finally:
                    self.cb_show_final_text.blockSignals(False)
            if hasattr(self, "act_final_paint_above_text") and "final_paint_above_text" in ui_state:
                val = bool(ui_state.get("final_paint_above_text"))
                self.final_paint_above_text = val
                self.act_final_paint_above_text.blockSignals(True)
                try:
                    self.act_final_paint_above_text.setChecked(val)
                    self.act_final_paint_above_text.setText("T↑" if val else "T↓")
                    self._last_final_paint_above_text = val
                finally:
                    self.act_final_paint_above_text.blockSignals(False)
            if isinstance(ui_state.get("view_states"), dict):
                self.project_ui_view_states = copy.deepcopy(ui_state.get("view_states") or {})
            if refresh and hasattr(self, "cb_mode") and self.cb_mode.currentIndex() == 4:
                old_suppress = getattr(self, "_suppress_mode_undo", False)
                self._suppress_mode_undo = True
                try:
                    self.mode_chg(4)
                finally:
                    self._suppress_mode_undo = old_suppress
            return True
        finally:
            self._project_undo_restore_lock = old_restore

    def current_project_ui_state(self):
        self.remember_current_view_state()
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = int(getattr(self, "last_mode", 0) or 0)
        return {
            "current_mode": mode,
            "view_states": copy.deepcopy(getattr(self, "project_ui_view_states", {}) or {}),
            "show_final_text": bool(self.cb_show_final_text.isChecked()) if hasattr(self, "cb_show_final_text") else True,
            "final_paint_above_text": bool(getattr(self, "final_paint_above_text", False)),
        }

    def save_project_store(self, store, paths=None, data=None, idx=None):
        """ProjectStore.save() 호출 전에 UI 상태를 같이 넣는 공통 저장 함수."""
        if store is None:
            return False
        try:
            store.ui_state = self.current_project_ui_state()
        except Exception:
            store.ui_state = getattr(store, "ui_state", {}) or {}
        store.save(paths if paths is not None else self.paths, data if data is not None else self.data, self.idx if idx is None else idx)
        return True

    def undo_boundary_log_text(self, event, kind, name=""):
        """Undo 경계 생성/차단 로그 문구를 현재 UI 언어에 맞춰 돌려준다."""
        kind = str(kind or "action")
        name = str(name or "").strip()
        is_en = getattr(self, "ui_language", LANG_KO) == LANG_EN

        boundary_labels = {
            "macro": ("매크로", "macro"),
            "font_preset": ("글꼴 프리셋", "font preset"),
            "analysis": ("분석 결과", "analysis results"),
            "reanalyze": ("텍스트 마스크 재분석 결과", "text mask re-analysis results"),
            "translation": ("번역 결과", "translation results"),
            "inpaint": ("인페인팅 결과", "inpainting results"),
            "batch_analysis": ("일괄 분석 결과", "batch analysis results"),
            "batch_translation": ("일괄 번역 결과", "batch translation results"),
            "batch_inpaint": ("일괄 인페인팅 결과", "batch inpainting results"),
        }
        ko_label, en_label = boundary_labels.get(kind, ("작업", "action"))
        ko_name = name or ko_label
        en_name = name or en_label

        if kind == "macro":
            if event == "set":
                return (
                    f"🧱 Undo boundary set: macro '{en_name}' was executed, so previous undo history was cleared."
                    if is_en else
                    f"🧱 Undo 경계 생성: 매크로 '{ko_name}' 실행으로 이전 되돌리기 내역을 끊었습니다."
                )
            return (
                f"⛔ Cannot undo: macro '{en_name}' created an undo boundary. To prevent state conflicts, actions before that point cannot be restored."
                if is_en else
                f"⛔ 되돌릴 수 없습니다: 매크로 '{ko_name}' 실행 이후 Undo 경계가 생겼습니다. 상태 꼬임 방지를 위해 그 이전으로는 돌아가지 않습니다."
            )

        api_boundary_kinds = {
            "analysis", "reanalyze", "translation", "inpaint",
            "batch_analysis", "batch_translation", "batch_inpaint",
        }
        if kind in api_boundary_kinds:
            if event == "set":
                return (
                    f"🧱 Undo boundary set: {en_label} were applied, so previous undo history was cleared."
                    if is_en else
                    f"🧱 Undo 경계 생성: {ko_label} 반영으로 이전 되돌리기 내역을 끊었습니다."
                )
            return (
                f"⛔ Cannot undo: {en_label} created an undo boundary. To prevent state conflicts, actions before that point cannot be restored."
                if is_en else
                f"⛔ 되돌릴 수 없습니다: {ko_label} 반영 이후 Undo 경계가 생겼습니다. 상태 꼬임 방지를 위해 그 이전으로는 돌아가지 않습니다."
            )

        if event == "set":
            return (
                "🧱 Undo boundary set: previous undo history was cleared to prevent state conflicts."
                if is_en else
                "🧱 Undo 경계 생성: 상태 꼬임 방지를 위해 이전 되돌리기 내역을 끊었습니다."
            )
        return (
            "⛔ Cannot undo: an undo boundary was created. To prevent state conflicts, actions before that point cannot be restored."
            if is_en else
            "⛔ 되돌릴 수 없습니다: Undo 경계가 생겼습니다. 상태 꼬임 방지를 위해 그 이전으로는 돌아가지 않습니다."
        )

    def break_undo_chain(self, kind="action", name=""):
        """매크로/글꼴 프리셋처럼 Undo 기록을 남기지 않는 작업 뒤에 과거 Undo를 차단한다."""
        self.undo_boundary = {"kind": str(kind or "action"), "name": str(name or "")}
        self.project_undo_stack = []
        self.project_redo_stack = []
        self.page_text_undo_stacks = {}
        self._deferred_undo_records = {}
        try:
            self.view.history.clear()
        except Exception:
            pass
        self.log(self.undo_boundary_log_text("set", kind, name))
        self.update_undo_redo_buttons()
        return True

    def log_undo_boundary_blocked(self):
        boundary = getattr(self, "undo_boundary", None)
        if not boundary:
            return False
        self.log(self.undo_boundary_log_text("blocked", boundary.get("kind"), boundary.get("name")))
        return True

    def set_work_mode_without_undo(self, mode):
        try:
            mode = int(mode)
        except Exception:
            mode = 0
        if not hasattr(self, "cb_mode") or self.cb_mode.count() <= 0:
            self.last_mode = mode
            self._current_work_mode = mode
            return
        mode = max(0, min(mode, self.cb_mode.count() - 1))
        self.cb_mode.blockSignals(True)
        try:
            self.cb_mode.setCurrentIndex(mode)
        finally:
            self.cb_mode.blockSignals(False)
        self.last_mode = mode
        self._current_work_mode = mode

    def copy_page_data_for_undo(self, page_idx=None):
        if page_idx is None:
            page_idx = self.idx
        curr = self.data.get(page_idx)
        if not isinstance(curr, dict):
            return None
        out = {}
        for k, v in curr.items():
            if k == 'ori':
                out[k] = v
            elif isinstance(v, np.ndarray):
                out[k] = v.copy()
            else:
                out[k] = copy.deepcopy(v)
        return out

    def copy_project_data_for_undo(self):
        """일괄 텍스트 작업용 전체 프로젝트 스냅샷.

        번역문 일괄 불러오기/일괄 지우기/텍스트 정리처럼 여러 페이지를 한 번에
        바꾸는 작업은 현재 페이지만 저장하면 Ctrl+Z 복원이 깨진다.
        이 경우 변경 전 self.data 전체를 저장해 하나의 Undo 단계로 되돌린다.
        """
        out = {}
        try:
            keys = list((self.data or {}).keys())
        except Exception:
            keys = []
        for page_idx in keys:
            page_data = self.copy_page_data_for_undo(page_idx)
            if page_data is not None:
                out[page_idx] = page_data
        return out

    def append_project_undo_record(self, rec, clear_redo=True):
        if not rec:
            return False
        if getattr(self, "_project_undo_restore_lock", False):
            return False
        # 매크로 실행 중에는 단계별 Undo를 쌓지 않는다.
        # 일반 매크로는 완료 시점에 매크로 1개짜리 Undo만 저장하고,
        # 분석/번역/인페인팅 포함 매크로는 Undo 경계로 끊는다.
        if getattr(self, "macro_running", False) and not getattr(self, "_macro_allow_undo_append", False):
            return False
        if not hasattr(self, "project_undo_stack") or self.project_undo_stack is None:
            self.project_undo_stack = []
        self.project_undo_stack.append(rec)
        # Undo 스택은 가볍게 20단계만 유지한다.
        # 텍스트 라인/탭 이동까지 모두 스택에 넣기 때문에 오래된 기록은 FIFO로 버린다.
        if len(self.project_undo_stack) > 20:
            self.project_undo_stack.pop(0)
        if clear_redo:
            # 새 작업이 들어오면 기존 Redo 흐름은 더 이상 유효하지 않다.
            self.project_redo_stack = []
        self.update_undo_redo_buttons()
        return True

    def append_project_redo_record(self, rec):
        if not rec:
            return False
        if not hasattr(self, "project_redo_stack") or self.project_redo_stack is None:
            self.project_redo_stack = []
        self.project_redo_stack.append(rec)
        if len(self.project_redo_stack) > 20:
            self.project_redo_stack.pop(0)
        self.update_undo_redo_buttons()
        return True

    def make_project_undo_record(self, reason="작업", page_idx=None, full_project=False):
        if page_idx is None:
            page_idx = self.idx
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = int(getattr(self, "last_mode", 0) or 0)
        rec = {
            "reason": str(reason or "작업"),
            "page_idx": int(page_idx),
            "mode": mode,
            "view_state": self.capture_view_state(),
            "magic_wand_state": self.capture_magic_wand_state(),
            "ui_state": self.current_project_ui_state(),
        }
        if full_project:
            rec["project_data"] = self.copy_project_data_for_undo()
        else:
            rec["page_data"] = self.copy_page_data_for_undo(page_idx)
        return rec

    def make_ui_undo_record(self, reason="화면 작업", page_idx=None, mode=None):
        """탭/페이지/줌/화면 이동용 경량 Undo 기록.

        이 작업들은 data 자체를 바꾸지 않으므로 이미지/마스크/텍스트 전체를
        복사하지 않는다. 이전 구현처럼 page_data를 매번 복사하면 탭 이동이나
        최종화면 전환이 무거워지고, Ctrl+Z 연속 동작도 끊기는 원인이 된다.
        """
        if page_idx is None:
            page_idx = self.idx
        try:
            current_mode = int(self.cb_mode.currentIndex())
        except Exception:
            current_mode = int(getattr(self, "last_mode", 0) or 0)
        if mode is None:
            mode = current_mode
        return {
            "reason": str(reason or "화면 작업"),
            "page_idx": int(page_idx),
            "mode": int(mode),
            "view_state": self.capture_view_state(),
            "magic_wand_state": self.capture_magic_wand_state(),
            "ui_state": self.current_project_ui_state(),
            "ui_only": True,
        }

    def is_ui_only_undo_reason(self, reason):
        text = str(reason or "")
        return text in ("작업 탭 변경", "페이지 이동", "화면 이동", "화면 확대/축소")

    def push_project_undo(self, reason="작업", page_idx=None, full_project=False):
        if getattr(self, "_project_undo_restore_lock", False):
            return False
        # 매크로 실행 중 발생한 단계별 작업은 Ctrl+Z 스택에 쌓지 않는다.
        # 매크로는 여러 기능을 연쇄 실행하므로 Undo 기록에 섞이면 복구 순서가 꼬일 수 있다.
        if getattr(self, "macro_running", False) or getattr(self, "_suppress_project_undo", False):
            return False
        if getattr(self, "is_loading_project", False) or getattr(self, "is_page_loading", False) or getattr(self, "is_batch_running", False):
            return False
        if not self.paths or page_idx is None and self.idx not in self.data:
            return False
        target_page = self.idx if page_idx is None else page_idx
        if (not full_project) and self.is_ui_only_undo_reason(reason):
            rec = self.make_ui_undo_record(reason, target_page)
        else:
            rec = self.make_project_undo_record(reason, target_page, full_project=full_project)
        return self.append_project_undo_record(rec)

    def begin_deferred_project_undo(self, key, reason="작업"):
        if not key:
            return None
        if getattr(self, "macro_running", False) or getattr(self, "_suppress_project_undo", False):
            return None
        if getattr(self, "_project_undo_restore_lock", False) or getattr(self, "is_page_loading", False) or getattr(self, "is_batch_running", False):
            return None
        if self.is_ui_only_undo_reason(reason):
            rec = self.make_ui_undo_record(reason)
        else:
            rec = self.make_project_undo_record(reason)
        self._deferred_undo_records[str(key)] = rec
        return rec

    def finish_deferred_project_undo(self, key, force=False, changed=None, autosave=True):
        rec = self._deferred_undo_records.pop(str(key), None)
        if getattr(self, "macro_running", False) or getattr(self, "_suppress_project_undo", False):
            if autosave:
                self.auto_save_project()
            return False
        if not rec:
            return False
        if changed is None:
            changed = True
        if not force and not changed:
            return False
        self.append_project_undo_record(rec)
        if autosave:
            self.auto_save_project()
        return True

    def copy_text_line_state_for_undo(self, page_idx=None, include_masks=False):
        """원문/번역문/텍스트행 삭제/재정렬용 경량 스냅샷.

        일반 텍스트 라인 수정은 이미지/전체 마스크를 복사할 필요가 없다.
        현재 페이지의 data 리스트만 복사해서 Ctrl+Z 복원을 가볍게 만든다.
        삭제처럼 마스크 슬롯을 같이 건드리는 작업만 include_masks=True로 필요한
        마스크 슬롯을 추가 보존한다.
        """
        if page_idx is None:
            page_idx = self.idx
        curr = self.data.get(page_idx)
        if not isinstance(curr, dict):
            return None
        state = {
            "data": copy.deepcopy(curr.get("data", []) or []),
        }
        if include_masks:
            for key in ("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off"):
                value = curr.get(key)
                state[key] = value.copy() if isinstance(value, np.ndarray) else copy.deepcopy(value)
            state["mask_toggle_enabled"] = bool(curr.get("mask_toggle_enabled", False))
        return state

    def make_text_line_undo_record(self, reason="텍스트 라인 변경", page_idx=None, include_masks=False):
        if page_idx is None:
            page_idx = self.idx
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = int(getattr(self, "last_mode", 0) or 0)
        return {
            "reason": str(reason or "텍스트 라인 변경"),
            "page_idx": int(page_idx),
            "mode": mode,
            "view_state": self.capture_view_state(),
            "magic_wand_state": self.capture_magic_wand_state(),
            "ui_state": self.current_project_ui_state(),
            "text_line_state": self.copy_text_line_state_for_undo(page_idx, include_masks=include_masks),
        }

    def push_text_line_undo(self, reason="텍스트 라인 변경", page_idx=None, include_masks=False):
        if getattr(self, "_project_undo_restore_lock", False):
            return False
        if getattr(self, "macro_running", False) or getattr(self, "_suppress_project_undo", False):
            return False
        if getattr(self, "is_loading_project", False) or getattr(self, "is_page_loading", False) or getattr(self, "is_batch_running", False):
            return False
        if not self.paths or (page_idx is None and self.idx not in self.data):
            return False
        rec = self.make_text_line_undo_record(reason, self.idx if page_idx is None else page_idx, include_masks=include_masks)
        return self.append_project_undo_record(rec)

    def make_current_undo_record_like(self, rec):
        """Undo/Redo 왕복용 현재 상태 스냅샷을 기존 기록과 같은 가벼운 단위로 만든다."""
        reason = str((rec or {}).get("reason") or "작업")
        try:
            page_idx = int(getattr(self, "idx", 0) or 0)
        except Exception:
            page_idx = 0

        text_line_state = (rec or {}).get("text_line_state")
        if isinstance(text_line_state, dict):
            include_masks = any(k in text_line_state for k in ("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off", "mask_toggle_enabled"))
            return self.make_text_line_undo_record(reason, page_idx=page_idx, include_masks=include_masks)
        if (rec or {}).get("ui_only"):
            try:
                mode = int(self.cb_mode.currentIndex())
            except Exception:
                mode = int(getattr(self, "last_mode", 0) or 0)
            return self.make_ui_undo_record(reason, page_idx=page_idx, mode=mode)
        if isinstance((rec or {}).get("project_data"), dict):
            return self.make_project_undo_record(reason, page_idx=page_idx, full_project=True)
        return self.make_project_undo_record(reason, page_idx=page_idx, full_project=False)

    def restore_project_history_record(self, rec):
        """Undo/Redo 기록 1개를 실제 작업 상태로 복원한다."""
        page_idx = int(rec.get("page_idx", self.idx) or 0)
        if page_idx < 0 or page_idx >= len(self.paths):
            return False

        self._project_undo_restore_lock = True
        self._text_undo_restore_lock = True
        try:
            text_line_state = rec.get("text_line_state")
            if isinstance(text_line_state, dict):
                curr = self.data.get(page_idx)
                if isinstance(curr, dict):
                    curr["data"] = copy.deepcopy(text_line_state.get("data", []) or [])
                    for key in ("mask_merge", "mask_inpaint", "mask_merge_off", "mask_inpaint_off"):
                        if key in text_line_state:
                            value = text_line_state.get(key)
                            curr[key] = value.copy() if isinstance(value, np.ndarray) else copy.deepcopy(value)
                    if "mask_toggle_enabled" in text_line_state:
                        curr["mask_toggle_enabled"] = bool(text_line_state.get("mask_toggle_enabled"))
            elif not rec.get("ui_only"):
                project_data = rec.get("project_data")
                if isinstance(project_data, dict):
                    restored = {}
                    for k, v in project_data.items():
                        restored[k] = self.copy_undo_page_data(v) if isinstance(v, dict) else copy.deepcopy(v)
                    self.data = restored
                else:
                    page_data = rec.get("page_data")
                    if isinstance(page_data, dict):
                        self.data[page_idx] = self.copy_undo_page_data(page_data)

            self.idx = page_idx
            mode = int(rec.get("mode", 0) or 0)
            self.set_work_mode_without_undo(mode)
            self.restore_project_ui_state(rec.get("ui_state"), refresh=False)

            prev_loading = self.is_page_loading
            self.is_page_loading = True
            try:
                self.load()
            finally:
                self.is_page_loading = prev_loading

            self.restore_project_ui_state(rec.get("ui_state"), refresh=(mode == 4))

            state = copy.deepcopy(rec.get("view_state") or {})
            if state:
                self.apply_view_state(state)
                QTimer.singleShot(0, lambda st=state: self.apply_view_state(st))
                QTimer.singleShot(30, lambda st=state: self.apply_view_state(st))
                QTimer.singleShot(80, lambda st=state: self.apply_view_state(st))

            try:
                self.view.history.clear()
            except Exception:
                pass
            try:
                self.restore_magic_wand_state(rec.get("magic_wand_state"))
            except Exception:
                pass
            self.page_text_undo_stacks = {}
            self.auto_save_project()
        finally:
            self._text_undo_restore_lock = False
            self._project_undo_restore_lock = False
        return True

    def undo_project_action(self):
        stack = getattr(self, "project_undo_stack", None) or []
        if not stack:
            self.update_undo_redo_buttons()
            return False
        rec = stack.pop()
        redo_rec = self.make_current_undo_record_like(rec)
        if not self.restore_project_history_record(rec):
            self.update_undo_redo_buttons()
            return False
        self.append_project_redo_record(redo_rec)
        self.log(f"↩️ {rec.get('reason', '작업')} 되돌림")
        self.update_undo_redo_buttons()
        return True

    def redo_project_action(self):
        stack = getattr(self, "project_redo_stack", None) or []
        if not stack:
            self.update_undo_redo_buttons()
            return False
        rec = stack.pop()
        undo_rec = self.make_current_undo_record_like(rec)
        if not self.restore_project_history_record(rec):
            self.update_undo_redo_buttons()
            return False
        self.append_project_undo_record(undo_rec, clear_redo=False)
        self.log(f"↷ {rec.get('reason', '작업')} 재실행")
        self.update_undo_redo_buttons()
        return True

    def copy_undo_page_data(self, page_data):
        out = {}
        for k, v in (page_data or {}).items():
            if k == 'ori':
                out[k] = v
            elif isinstance(v, np.ndarray):
                out[k] = v.copy()
            else:
                out[k] = copy.deepcopy(v)
        return out

    def push_page_text_undo(self, reason="텍스트 작업"):
        # v1.6.3: 페이지를 넘긴 뒤에도 이전 페이지 텍스트 작업을 되돌릴 수 있도록
        # 페이지 전용 스택 대신 전역 작업 스택에 현재 페이지 상태를 저장한다.
        return self.push_project_undo(reason)

    def undo_page_text(self):
        # 구버전 호출 호환용. 실제 Ctrl+Z는 handle_general_undo()에서
        # undo_project_action()을 먼저 사용한다.
        return self.undo_project_action()

    def end_active_text_transform(self, refresh=True):
        active = self.current_transform_data_item()
        if active is None:
            return False
        active.pop('_transform_mode', None)
        if refresh and self.cb_mode.currentIndex() == 4:
            selected_id = active.get('id')
            self.mode_chg(4)
            if selected_id is not None:
                self.reselect_text_items([selected_id])
        self.auto_save_project()
        self.log("🔷 텍스트 변형 모드 종료")
        return True

    def can_general_undo(self):
        try:
            if getattr(self, "project_undo_stack", None):
                return True
            if getattr(getattr(self, "view", None), "history", None):
                return True
            if getattr(getattr(self, "view", None), "draw_mode", None) == 'magic_wand' and getattr(self, 'magic_wand_history', None):
                return True
        except Exception:
            pass
        return False

    def can_general_redo(self):
        return bool(getattr(self, "project_redo_stack", None))

    def set_history_button_tooltips(self):
        def shortcut_text(key, fallback=""):
            try:
                seq = self.shortcut_settings.seq(key)
                txt = seq.toString(QKeySequence.SequenceFormat.NativeText)
                return txt or fallback
            except Exception:
                return fallback
        if hasattr(self, "btn_quick_undo"):
            title = self.tr_ui("작업 취소")
            desc = self.tr_msg("되돌릴 수 있는 작업이 있으면 이전 상태로 돌아갑니다.")
            self.btn_quick_undo.setToolTip(f"{title} ({shortcut_text('paint_undo', 'Ctrl+Z')})\n{desc}")
        if hasattr(self, "btn_quick_redo"):
            title = self.tr_ui("작업 재실행")
            desc = self.tr_msg("되돌린 작업을 다시 적용합니다.")
            self.btn_quick_redo.setToolTip(f"{title} ({shortcut_text('paint_redo', 'Ctrl+Y')})\n{desc}")

    def history_button_style(self, enabled):
        if enabled:
            return "background:#3b465a;color:#ffffff;border:1px solid #7f8ba3;font-weight:bold;"
        return "background:#2a2d34;color:#777b84;border:1px solid #444852;font-weight:bold;"

    def update_undo_redo_buttons(self):
        try:
            can_undo = self.can_general_undo()
            can_redo = self.can_general_redo()
            if hasattr(self, "btn_quick_undo"):
                self.btn_quick_undo.setEnabled(can_undo)
                self.btn_quick_undo.setStyleSheet(self.history_button_style(can_undo))
            if hasattr(self, "btn_quick_redo"):
                self.btn_quick_redo.setEnabled(can_redo)
                self.btn_quick_redo.setStyleSheet(self.history_button_style(can_redo))
            self.set_history_button_tooltips()
        except Exception:
            pass

    def handle_general_undo(self):
        if self.undo_project_action():
            return
        if self.log_undo_boundary_blocked():
            self.update_undo_redo_buttons()
            return
        if getattr(self.view, 'draw_mode', None) == 'magic_wand' and getattr(self, 'magic_wand_history', None):
            self.undo_magic_wand_selection()
            self.update_undo_redo_buttons()
            return
        self.view.undo()
        self.update_undo_redo_buttons()

    def handle_general_redo(self):
        if self.redo_project_action():
            return
        self.log("⚠️ 다시 실행할 내역이 없습니다." if self.ui_language == LANG_KO else "⚠️ There is no action to redo.")
        self.update_undo_redo_buttons()

    def open_api_settings_dialog(self):
        dlg = ApiSettingsDialog(self.api_settings, self)
        if not dlg.exec():
            return

        self.api_settings = dlg.get_settings()
        ApiSettingsStore.save(self.api_settings)
        apply_settings_to_config(self.api_settings)
        self.sync_translation_option_cache_to_config()
        if hasattr(self, "cb_trans_provider"):
            self.cb_trans_provider.blockSignals(True)
            try:
                self.set_combo_current_data(self.cb_trans_provider, getattr(self.api_settings, "selected_translation_provider", "openai"))
                self.on_translation_provider_changed(save=False)
            finally:
                self.cb_trans_provider.blockSignals(False)
        self.restart_engine(show_error=True)
        self.log("🔑 API settings cache saved" if self.ui_language == LANG_EN else "🔑 API 설정 캐시 저장 완료")

    def open_translation_prompt_dialog(self):
        old_prompt = str(self.app_options.get(TRANSLATION_PROMPT_KEY, "") or "")
        dlg = TranslationPromptDialog(old_prompt, self)
        if not dlg.exec():
            self.log("↩️ 번역 프롬프트 저장 취소")
            return

        new_prompt = dlg.get_prompt_text()
        self.app_options[TRANSLATION_PROMPT_KEY] = new_prompt
        self.save_app_options_cache()
        self.sync_translation_option_cache_to_config()
        self.log(f"📝 번역 프롬프트 캐시 저장 완료 ({len(new_prompt):,}자)")

    def open_glossary_dialog(self):
        old_text = str(self.app_options.get(TRANSLATION_GLOSSARY_TEXT_KEY, "") or "")
        old_path = str(self.app_options.get(TRANSLATION_GLOSSARY_PATH_KEY, "") or "")
        dlg = GlossaryDialog(old_text, old_path, self)
        dlg.exec()

        new_text, new_path, changed = dlg.get_glossary_state()
        if not changed:
            return

        self.app_options[TRANSLATION_GLOSSARY_TEXT_KEY] = new_text
        self.app_options[TRANSLATION_GLOSSARY_PATH_KEY] = new_path
        self.save_app_options_cache()
        self.sync_translation_option_cache_to_config()

        if new_text:
            self.log(f"📚 단어장 캐시 저장 완료 ({len(new_text):,}자)")
        else:
            self.log("📚 단어장 캐시 초기화 완료")

    def capture_magic_wand_state(self):
        """요술봉 미리보기 상태를 전역 Undo 스택에 같이 저장한다."""
        try:
            active = bool(getattr(getattr(self, 'view', None), 'draw_mode', None) == 'magic_wand')
        except Exception:
            active = False
        return {
            "active": active,
            "mask": self.magic_wand_mask.copy() if isinstance(getattr(self, 'magic_wand_mask', None), np.ndarray) else None,
            "seed": tuple(self.magic_wand_seed) if getattr(self, 'magic_wand_seed', None) else None,
            "seeds": [tuple(x) for x in (getattr(self, 'magic_wand_seeds', []) or [])],
        }

    def restore_magic_wand_state(self, state):
        """Undo 복원 후 요술봉 선택/확장 상태를 화면에 다시 그린다."""
        if not isinstance(state, dict):
            self.clear_magic_wand_selection()
            return False
        mask = state.get('mask')
        self.magic_wand_mask = mask.copy() if isinstance(mask, np.ndarray) else None
        self.magic_wand_seeds = [tuple(x) for x in (state.get('seeds') or [])]
        self.magic_wand_seed = tuple(state.get('seed')) if state.get('seed') else (self.magic_wand_seeds[-1] if self.magic_wand_seeds else None)
        if state.get('active') and self.cb_mode.currentIndex() in [2, 3]:
            try:
                self.set_tool('magic_wand')
            except Exception:
                pass
        if self.magic_wand_mask is not None:
            try:
                self.view.draw_magic_wand_preview(self.magic_wand_mask)
            except Exception:
                pass
        else:
            try:
                self.view.clear_magic_wand_preview()
            except Exception:
                pass
        return True

    def push_magic_wand_history(self):
        mask = self.magic_wand_mask.copy() if isinstance(self.magic_wand_mask, np.ndarray) else None
        seeds = list(getattr(self, "magic_wand_seeds", []) or [])
        self.magic_wand_history.append((mask, seeds))
        if len(self.magic_wand_history) > 20:
            self.magic_wand_history.pop(0)

    def undo_magic_wand_selection(self):
        if not getattr(self, "magic_wand_history", None):
            self.log("⚠️ 되돌릴 요술봉 선택이 없습니다.")
            return False
        mask, seeds = self.magic_wand_history.pop()
        self.magic_wand_mask = mask
        self.magic_wand_seeds = list(seeds or [])
        self.magic_wand_seed = self.magic_wand_seeds[-1] if self.magic_wand_seeds else None
        if self.magic_wand_mask is not None:
            self.view.draw_magic_wand_preview(self.magic_wand_mask)
        else:
            self.view.clear_magic_wand_preview()
        self.log("↩️ 요술봉 선택 되돌림")
        return True

    def clear_magic_wand_selection(self):
        self.magic_wand_mask = None
        self.magic_wand_seed = None
        self.magic_wand_seeds = []
        self.magic_wand_history = []
        if hasattr(self, "view") and hasattr(self.view, "clear_magic_wand_preview"):
            self.view.clear_magic_wand_preview()

    def current_magic_source_image(self):
        return self.get_source_display_image(self.idx)

    def set_mask_wrap_shape(self, shape, silent=False):
        shape = "free" if str(shape) == "free" else "rect"
        try:
            self.view.mask_wrap_shape = shape
            self.view.clear_mask_wrap_preview()
        except Exception:
            pass
        for btn, active in ((getattr(self, "btn_mask_wrap_rect", None), shape == "rect"), (getattr(self, "btn_mask_wrap_free", None), shape == "free")):
            if btn is None:
                continue
            try:
                btn.blockSignals(True)
                btn.setChecked(active)
                btn.blockSignals(False)
                if active:
                    btn.setStyleSheet("font-weight:bold; background:#2f80ed; color:white;")
                else:
                    btn.setStyleSheet("opacity:0.7;")
            except Exception:
                pass
        if not silent:
            if shape == "rect":
                self.log("🩹 마스크 랩핑 모드: 사각형")
            else:
                self.log("🩹 마스크 랩핑 모드: 자유형")

    def set_mask_cut_shape(self, shape, silent=False):
        shape = "free" if str(shape) == "free" else "rect"
        try:
            self.view.mask_cut_shape = shape
            self.view.clear_mask_cut_preview()
        except Exception:
            pass
        for btn, active in ((getattr(self, "btn_mask_cut_rect", None), shape == "rect"), (getattr(self, "btn_mask_cut_free", None), shape == "free")):
            if btn is None:
                continue
            try:
                btn.blockSignals(True)
                btn.setChecked(active)
                btn.blockSignals(False)
                if active:
                    btn.setStyleSheet("font-weight:bold; background:#c2410c; color:white;")
                else:
                    btn.setStyleSheet("opacity:0.7;")
            except Exception:
                pass
        if not silent:
            if shape == "rect":
                self.log(self.tr_ui("🔪 마스크 커팅 모드: 사각형"))
            else:
                self.log(self.tr_ui("🔪 마스크 커팅 모드: 자유형"))

    def apply_mask_wrapping(self, region_mask):
        """선택한 영역 안의 분리된 마스크 덩어리들을 하나의 채움 영역으로 감싸준다."""
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = -1
        if mode not in (2, 3):
            self.log("⚠️ 마스크 랩핑은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.")
            return
        if region_mask is None:
            self.log("⚠️ 마스크 랩핑 영역이 비어 있습니다.")
            return
        before = self.view.get_mask_np()
        if before is None:
            self.log(self.tr_ui("⚠️ 현재 탭에 마스크 레이어가 없습니다."))
            return

        try:
            mask = (before > 0).astype(np.uint8) * 255
            region = (region_mask > 0).astype(np.uint8) * 255
            if mask.shape[:2] != region.shape[:2]:
                region = cv2.resize(region, (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_NEAREST)

            # 선택 영역 안에 실제로 들어온 마스크 조각만 대상으로 삼는다.
            inside = cv2.bitwise_and(mask, region)
            num, labels, stats, _ = cv2.connectedComponentsWithStats(inside, 8)
            comps = [i for i in range(1, num) if int(stats[i, cv2.CC_STAT_AREA]) > 0]
            if len(comps) < 2:
                self.log("⚠️ 선택한 영역 안에 랩핑할 마스크가 2개 이상 필요합니다.")
                return

            ys, xs = np.where(inside > 0)
            if len(xs) == 0 or len(ys) == 0:
                self.log("⚠️ 마스크 랩핑 영역 안에서 마스크를 찾지 못했습니다.")
                return

            try:
                self.commit_current_page_ui_to_data(include_mask=True)
                self.push_project_undo("마스크 랩핑")
            except Exception:
                pass

            x1, x2 = int(xs.min()), int(xs.max())
            y1, y2 = int(ys.min()), int(ys.max())
            fill = np.zeros_like(mask, dtype=np.uint8)
            cv2.rectangle(fill, (x1, y1), (x2, y2), 255, thickness=-1)
            # 사용자가 잡은 영역 밖은 절대 건드리지 않는다.
            fill = cv2.bitwise_and(fill, region)
            wrapped = cv2.bitwise_or(mask, fill)

            if np.array_equal(wrapped, mask):
                self.log("⚠️ 마스크 랩핑으로 추가될 영역이 없습니다.")
                return

            color = QColor(0, 0, 255, 150) if mode == 3 else QColor(255, 0, 0, 150)
            self.view.set_user_mask_np(wrapped, color)
            self.on_view_mask_edited()
            self.log(f"🩹 마스크 랩핑 완료: {len(comps)}개 마스크 덩어리를 1개 영역으로 감쌈")
        except Exception as e:
            self.log(f"⚠️ 마스크 랩핑 실패: {e}")


    def apply_mask_cutting(self, region_mask):
        """선택 영역 내부는 보존하고, 선택 영역 바깥 경계 주변의 마스크를 지정 px만큼 잘라낸다."""
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = -1
        if mode not in (2, 3):
            self.log(self.tr_ui("⚠️ 마스크 커팅은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요."))
            return
        if region_mask is None:
            self.log(self.tr_ui("⚠️ 마스크 커팅 영역이 비어 있습니다."))
            return

        before = self.view.get_mask_np()
        if before is None:
            self.log(self.tr_ui("⚠️ 현재 탭에 마스크 레이어가 없습니다."))
            return

        try:
            cut_px = int(getattr(self, "sb_mask_cut_px", None).value()) if hasattr(self, "sb_mask_cut_px") else 8
        except Exception:
            cut_px = 8
        cut_px = max(1, min(200, int(cut_px)))

        try:
            mask = (before > 0).astype(np.uint8) * 255
            region = (region_mask > 0).astype(np.uint8) * 255
            if mask.shape[:2] != region.shape[:2]:
                region = cv2.resize(region, (mask.shape[1], mask.shape[0]), interpolation=cv2.INTER_NEAREST)

            kernel_size = cut_px * 2 + 1
            kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
            expanded = cv2.dilate(region, kernel, iterations=1)
            cut_band = cv2.bitwise_and(expanded, cv2.bitwise_not(region))

            if np.count_nonzero(cut_band) <= 0:
                self.log(self.tr_ui("⚠️ 마스크 커팅으로 제거할 외곽 영역이 없습니다."))
                return

            target_pixels = cv2.bitwise_and(mask, cut_band)
            removed = int(np.count_nonzero(target_pixels))
            if removed <= 0:
                self.log(self.tr_ui("⚠️ 지정한 커팅 영역에 제거할 마스크가 없습니다."))
                return

            try:
                self.commit_current_page_ui_to_data(include_mask=True)
                self.push_project_undo("마스크 커팅")
            except Exception:
                pass

            cut = mask.copy()
            cut[cut_band > 0] = 0

            if np.array_equal(cut, mask):
                self.log(self.tr_ui("⚠️ 마스크 커팅으로 변경된 영역이 없습니다."))
                return

            color = QColor(0, 0, 255, 150) if mode == 3 else QColor(255, 0, 0, 150)
            self.view.set_user_mask_np(cut, color)
            self.on_view_mask_edited()
            lang = normalize_ui_language(getattr(self, "ui_language", None) or current_ui_language())
            if lang == LANG_EN:
                self.log(f"🔪 Mask cutting complete: outer {cut_px}px / {removed} px removed")
            else:
                self.log(f"🔪 마스크 커팅 완료: 외곽 {cut_px}px / {removed} px 제거")
        except Exception as e:
            lang = normalize_ui_language(getattr(self, "ui_language", None) or current_ui_language())
            if lang == LANG_EN:
                self.log(f"⚠️ Mask cutting failed: {e}")
            else:
                self.log(f"⚠️ 마스크 커팅 실패: {e}")

    def magic_wand_pick(self, x, y):
        if self.cb_mode.currentIndex() not in [2, 3]:
            self.log("⚠️ 요술봉은 텍스트 마스크/페인팅 마스크 탭에서만 사용할 수 있습니다.")
            return

        img = self.current_magic_source_image()
        if img is None:
            self.log("⚠️ 요술봉 기준 이미지가 없습니다.")
            return

        h, w = img.shape[:2]
        if x < 0 or y < 0 or x >= w or y >= h:
            return

        tol = int(self.sb_magic_tolerance.value()) if hasattr(self, "sb_magic_tolerance") else 20
        try:
            self.push_project_undo("요술봉 선택")
        except Exception:
            self.push_magic_wand_history()
        self.magic_wand_seed = (int(x), int(y))
        if not hasattr(self, "magic_wand_seeds"):
            self.magic_wand_seeds = []
        self.magic_wand_seeds.append(self.magic_wand_seed)

        new_mask = self.build_magic_wand_mask(img, self.magic_wand_seed, tol)
        if self.magic_wand_mask is None:
            self.magic_wand_mask = new_mask
        else:
            self.magic_wand_mask = cv2.bitwise_or(self.magic_wand_mask.astype(np.uint8), new_mask.astype(np.uint8))

        self.view.draw_magic_wand_preview(self.magic_wand_mask)
        self.log(f"요술봉 선택 추가: x={x}, y={y}, 허용범위={tol}, 누적={len(self.magic_wand_seeds)}")

    def build_magic_wand_mask(self, img, seed, tolerance):
        """
        Photoshop 요술봉에 가까운 기본 동작:
        클릭 픽셀과 RGB/BGR 값이 비슷하고, 서로 연결된 영역만 flood fill로 선택한다.
        """
        h, w = img.shape[:2]
        work_img = img.copy()
        flood_mask = np.zeros((h + 2, w + 2), dtype=np.uint8)
        tol = max(0, min(255, int(tolerance)))
        diff = (tol, tol, tol)
        flags = 8 | cv2.FLOODFILL_FIXED_RANGE | (255 << 8)

        try:
            cv2.floodFill(work_img, flood_mask, tuple(seed), (0, 255, 255), diff, diff, flags)
        except Exception as e:
            self.log(f"⚠️ 요술봉 선택 실패: {e}")
            return np.zeros((h, w), dtype=np.uint8)

        return flood_mask[1:h + 1, 1:w + 1].copy()

    def on_magic_wand_tolerance_changed(self, value):
        # 허용범위를 바꾸면 누적 클릭 지점 전체를 기준으로 미리보기를 다시 계산한다.
        # 단, 영역확장 후 허용범위를 바꾸면 확장 상태는 재계산된다.
        if self.view.draw_mode != 'magic_wand':
            return
        seeds = list(getattr(self, "magic_wand_seeds", []) or [])
        if not seeds:
            return
        try:
            self.push_project_undo("요술봉 허용범위 변경")
        except Exception:
            pass
        img = self.current_magic_source_image()
        if img is None:
            return

        merged = None
        for seed in seeds:
            part = self.build_magic_wand_mask(img, seed, int(value))
            merged = part if merged is None else cv2.bitwise_or(merged.astype(np.uint8), part.astype(np.uint8))

        self.magic_wand_mask = merged
        self.view.draw_magic_wand_preview(self.magic_wand_mask)

    def expand_magic_wand_selection(self):
        if self.magic_wand_mask is None:
            self.log("⚠️ 먼저 요술봉으로 영역을 선택하세요.")
            return

        amount = int(self.sb_magic_expand.value()) if hasattr(self, "sb_magic_expand") else 3
        if amount <= 0:
            self.view.draw_magic_wand_preview(self.magic_wand_mask)
            return

        try:
            self.push_project_undo("요술봉 영역확장")
        except Exception:
            self.push_magic_wand_history()
        kernel_size = amount * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        self.magic_wand_mask = cv2.dilate(self.magic_wand_mask, kernel, iterations=1)
        self.view.draw_magic_wand_preview(self.magic_wand_mask)
        self.log(f"요술봉 영역확장: {amount}px")

    def fill_magic_wand_mask(self):
        if self.magic_wand_mask is None:
            self.log("⚠️ 먼저 요술봉으로 영역을 선택하세요.")
            return

        if self.cb_mode.currentIndex() not in [2, 3]:
            self.log("⚠️ 마스킹 칠하기는 텍스트 마스크/페인팅 마스크 탭에서만 가능합니다.")
            return

        if self.view.user_mask_item is None:
            self.log(self.tr_ui("⚠️ 현재 탭에 마스크 레이어가 없습니다."))
            return

        try:
            self.commit_current_page_ui_to_data(include_mask=True)
            self.push_project_undo("요술봉 마스킹 칠하기")
        except Exception:
            pass

        before = self.view.get_mask_np()
        if before is None:
            before = np.zeros_like(self.magic_wand_mask, dtype=np.uint8)

        combined = cv2.bitwise_or(before, self.magic_wand_mask.astype(np.uint8))
        color = QColor(0, 0, 255, 150) if self.cb_mode.currentIndex() == 3 else QColor(255, 0, 0, 150)
        self.view.set_user_mask_np(combined, color)
        self.clear_magic_wand_selection()
        self.on_view_mask_edited()
        self.log("요술봉 선택 영역을 현재 마스크에 칠했습니다.")

    def adjust_magic_tolerance(self, delta):
        if not hasattr(self, "sb_magic_tolerance"):
            return
        self.sb_magic_tolerance.setValue(max(0, min(255, self.sb_magic_tolerance.value() + int(delta))))

    def adjust_magic_expand_range(self, delta):
        if not hasattr(self, "sb_magic_expand"):
            return
        self.sb_magic_expand.setValue(max(0, min(200, self.sb_magic_expand.value() + int(delta))))

    def set_tool(self, m):
        mode = self.cb_mode.currentIndex() if hasattr(self, "cb_mode") else 0

        if m == 'magic_wand' and mode not in [2, 3]:
            self.log("⚠️ 요술봉은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.")
            return
        if m == 'mask_wrap' and mode not in [2, 3]:
            self.log("⚠️ 마스크 랩핑은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.")
            return
        if m == 'mask_cut' and mode not in [2, 3]:
            self.log(self.tr_ui("⚠️ 마스크 커팅은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요."))
            return
        if m == 'final_text' and mode != 4:
            self.log("⚠️ 텍스트 도구는 최종화면에서만 사용할 수 있습니다.")
            return
        if m == 'paste_text' and mode != 4:
            self.log("⚠️ 텍스트 붙여넣기는 최종화면에서만 사용할 수 있습니다.")
            return
        if m in ('draw', 'erase') and mode not in [2, 3, 4]:
            self.log("⚠️ 브러시/지우개는 마스크 탭 또는 최종화면에서만 사용할 수 있습니다.")
            return

        if m != 'paste_text':
            self.text_paste_pending = False
            try:
                self.view.clear_paste_preview()
            except Exception:
                pass

        self.view.draw_mode = m
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag if m else QGraphicsView.DragMode.ScrollHandDrag)
        if hasattr(self, "magic_wand_bar"):
            self.magic_wand_bar.setVisible(m == 'magic_wand' and mode in [2, 3])
        if hasattr(self, "mask_wrap_bar"):
            self.mask_wrap_bar.setVisible(m == 'mask_wrap' and mode in [2, 3])
        if hasattr(self, "mask_cut_bar"):
            self.mask_cut_bar.setVisible(m == 'mask_cut' and mode in [2, 3])
        if m != 'magic_wand':
            self.clear_magic_wand_selection()
        if m != 'mask_wrap' and hasattr(self.view, "clear_mask_wrap_preview"):
            self.view.clear_mask_wrap_preview()
        if m != 'mask_cut' and hasattr(self.view, "clear_mask_cut_preview"):
            self.view.clear_mask_cut_preview()

        self.update_final_paint_option_bar_visibility()

        if m == 'final_text':
            self.log("🔤 도구: 텍스트")
        elif m == 'paste_text':
            self.log("📋 도구: 텍스트 붙여넣기 위치 지정")
        elif m == 'draw':
            self.log("🖌️ 도구: 브러시")
        elif m == 'erase':
            self.log("🧼 도구: 지우개")
        elif m == 'mask_wrap':
            self.log("🩹 도구: 마스크 랩핑")
        elif m == 'mask_cut':
            self.log(self.tr_ui("🔪 도구: 마스크 커팅"))
        elif m is None:
            self.log("✋ 도구: 이동")

    def reset_mode_to_original(self):
        """
        새 프로젝트/프로젝트 열기 시 이전 작업 탭 상태가 섞이지 않도록
        원본 탭으로 강제 이동한다.
        """
        self.last_mode = 0
        self.cb_mode.blockSignals(True)
        try:
            self.cb_mode.setCurrentIndex(0)
        finally:
            self.cb_mode.blockSignals(False)

    def cycle_work_tab(self):
        """
        작업 탭을 다음 탭으로 이동한다.
        마지막 탭이면 처음 탭으로 루프한다.
        """
        fw = QApplication.focusWidget()
        if isinstance(fw, (QTextEdit, QLineEdit)):
            return

        if self.cb_mode.count() <= 0:
            return

        next_index = (self.cb_mode.currentIndex() + 1) % self.cb_mode.count()
        self.cb_mode.setCurrentIndex(next_index)

    def load(self):
        if not self.paths:
            return

        p = self.paths[self.idx]
        self.btn_page.setText(f"{self.idx + 1} / {len(self.paths)}")

        if self.idx not in self.data:
            self.data[self.idx] = {
                'ori': cv2.imdecode(np.fromfile(p, np.uint8), 1),
                'data': [],
                'mask_merge': None,
                'mask_inpaint': None,
                'mask_merge_off': None,
                'mask_inpaint_off': None,
                'mask_toggle_enabled': False,
                'use_inpainted_as_source': False,
                'bg_clean': None,
                'working_source': None,
                'final_paint': None,
                'final_paint_above': None,
            }
        elif self.data[self.idx].get('ori') is None:
            self.data[self.idx]['ori'] = cv2.imdecode(np.fromfile(p, np.uint8), 1)

        self.set_mask_toggle_safely(bool(self.data[self.idx].get('mask_toggle_enabled', self.mask_toggle_enabled)))

        # load() 중 mode_chg()가 실행되면 뷰어에 이전 페이지 마스크가 남아 있을 수 있다.
        # 이때 자동 저장이 끼면 다른 페이지 마스크가 덮이므로 로딩 플래그로 차단한다.
        prev_loading = self.is_page_loading
        self.is_page_loading = True
        try:
            self.ref_tab()
            self.mode_chg(self.cb_mode.currentIndex())
        finally:
            self.is_page_loading = prev_loading

    def is_light_theme(self):
        return str(getattr(self, "ui_theme", THEME_DARK) or THEME_DARK).lower() == THEME_LIGHT

    def table_row_color(self, checked):
        # 우측 텍스트 표 행 색상은 테마에 따라 따로 관리한다.
        # 체크 ON/OFF는 색으로 구분하되, 화이트 테마에서는 어두운 배경이 남지 않게 한다.
        if self.is_light_theme():
            return QColor("#ffffff") if checked else QColor("#fff1f1")
        return QColor("#2b2e34") if checked else QColor("#4a2b2b")

    def table_text_color(self, checked=True):
        return QColor("#202124") if self.is_light_theme() else QColor("#f2f2f2")

    def table_header_color(self):
        return QColor("#eef1f6") if self.is_light_theme() else QColor("#31343a")

    def table_header_text_color(self):
        return QColor("#202124") if self.is_light_theme() else QColor("#f2f2f2")

    def table_check_widget_style(self, color):
        border = "#d7dbe3" if self.is_light_theme() else "#4a4d55"
        return f"background:{color.name()}; border:none;"

    def repaint_text_table_theme(self):
        """테마 전환 직후 기존 우측 텍스트 표의 배경/글자색을 다시 칠한다."""
        if not hasattr(self, "tab") or self.tab is None:
            return
        self._table_check_lock = True
        self.tab.blockSignals(True)
        try:
            if self.tab.rowCount() > 0:
                self.clear_native_table_check_item(0)
                self.paint_all_row_header()
            for row in range(1, self.tab.rowCount()):
                self.clear_native_table_check_item(row)
                self.set_table_row_visual(row, self.get_table_check_state(row))
        finally:
            self.tab.blockSignals(False)
            self._table_check_lock = False

    def get_table_checkbox(self, row):
        widget = self.tab.cellWidget(row, 1)
        if widget:
            return widget.findChild(QCheckBox)
        return None

    def get_table_check_state(self, row):
        cb = self.get_table_checkbox(row)
        if cb is not None:
            return cb.isChecked()
        item = self.tab.item(row, 1)
        return item is not None and item.checkState() == Qt.CheckState.Checked

    def clear_native_table_check_item(self, row):
        """체크 표시는 cellWidget(QCheckBox) 하나만 사용한다.
        QTableWidgetItem의 CheckStateRole이 남아 있으면 테마 전환 후 기본 체크박스가
        같이 그려져 체크박스가 2개처럼 보일 수 있으므로 항상 제거한다.
        """
        try:
            item = self.tab.item(row, 1)
            if item is None:
                return
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            item.setData(Qt.ItemDataRole.CheckStateRole, None)
        except Exception:
            pass

    def set_table_check_state(self, row, checked):
        cb = self.get_table_checkbox(row)
        if cb is not None:
            cb.blockSignals(True)
            try:
                cb.setChecked(bool(checked))
            finally:
                cb.blockSignals(False)
        self.clear_native_table_check_item(row)

    def make_center_check_widget(self, row, checked):
        wrap = QWidget()
        lay = QHBoxLayout(wrap)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)
        cb = QCheckBox()
        cb.setFixedSize(18, 18)
        cb.setStyleSheet("QCheckBox { padding:0px; margin:0px; } QCheckBox::indicator { width:14px; height:14px; }")
        cb.setChecked(bool(checked))
        cb.stateChanged.connect(lambda state, r=row: self.on_table_check_widget_changed(r, state))
        lay.addStretch()
        lay.addWidget(cb, 0, Qt.AlignmentFlag.AlignCenter)
        lay.addStretch()
        return wrap

    def set_table_row_visual(self, row, checked):
        self.clear_native_table_check_item(row)
        color = self.table_row_color(checked)
        for c in range(self.tab.columnCount()):
            cell = self.tab.item(row, c)
            if cell:
                cell.setBackground(color)
                cell.setForeground(self.table_text_color(checked))
        widget = self.tab.cellWidget(row, 1)
        if widget:
            widget.setStyleSheet(self.table_check_widget_style(color))

    def paint_all_row_header(self):
        self.clear_native_table_check_item(0)
        bg = self.table_header_color()
        fg = self.table_header_text_color()
        for c in range(self.tab.columnCount()):
            cell = self.tab.item(0, c)
            if cell:
                cell.setBackground(bg)
                cell.setForeground(fg)
        widget = self.tab.cellWidget(0, 1)
        if widget:
            widget.setStyleSheet(self.table_check_widget_style(bg))

    def on_table_check_widget_changed(self, row, state):
        if self._table_check_lock:
            return
        self.apply_table_check_state(row, state in (Qt.CheckState.Checked, Qt.CheckState.Checked.value, 2))

    def apply_table_check_state(self, row, is_checked):
        if self.idx not in self.data:
            return

        curr_data = self.data.get(self.idx)
        if not curr_data or 'data' not in curr_data:
            return

        try:
            changed_for_undo = False
            if row == 0:
                changed_for_undo = any(bool(x.get('use_inpaint', True)) != bool(is_checked) for x in curr_data.get('data', []))
            else:
                data_index = row - 1
                if 0 <= data_index < len(curr_data.get('data', [])):
                    changed_for_undo = bool(curr_data['data'][data_index].get('use_inpaint', True)) != bool(is_checked)
            if changed_for_undo:
                self.push_project_undo('체크 상태 변경')
        except Exception:
            pass

        self._table_check_lock = True
        self.tab.blockSignals(True)
        try:
            if row == 0:
                for i, data_item in enumerate(curr_data['data']):
                    table_row = i + 1
                    data_item['use_inpaint'] = is_checked
                    self.set_table_check_state(table_row, is_checked)
                    self.set_table_row_visual(table_row, is_checked)
                self.set_table_check_state(0, is_checked)
                self.paint_all_row_header()
            else:
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr_data['data']):
                    return
                curr_data['data'][data_index]['use_inpaint'] = is_checked
                self.set_table_check_state(row, is_checked)
                self.set_table_row_visual(row, is_checked)

                all_checked = len(curr_data['data']) > 0 and all(x.get('use_inpaint', True) for x in curr_data['data'])
                self.set_table_check_state(0, all_checked)
                self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)
            self._table_check_lock = False

        if self.cb_mode.currentIndex() in [1, 2, 3]:
            self.refresh_boxes_only()
        elif self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)

        if row == 0:
            self.log((f"🔄 All check states auto-refreshed: {'ON' if is_checked else 'OFF'}" if self.ui_language == LANG_EN else f"🔄 전체 체크 상태 자동 갱신: {'ON' if is_checked else 'OFF'}"))
        else:
            data_index = row - 1
            if 0 <= data_index < len(curr_data['data']):
                self.log((f"🔄 Check state auto-refreshed: ID {curr_data['data'][data_index].get('id')} = {'ON' if is_checked else 'OFF'}" if self.ui_language == LANG_EN else f"🔄 체크 상태 자동 갱신: ID {curr_data['data'][data_index].get('id')} = {'ON' if is_checked else 'OFF'}"))
        self.auto_save_project()

    def ref_tab(self):
        curr = self.data.get(self.idx)
        if not curr:
            self._table_check_lock = True
            self.tab.blockSignals(True)
            try:
                self.tab.clearContents()
                self.tab.setRowCount(1)

                all_id_item = QTableWidgetItem("ALL")
                all_id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tab.setItem(0, 0, all_id_item)

                all_check_item = QTableWidgetItem("")
                all_check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tab.setItem(0, 1, all_check_item)
                self.tab.setCellWidget(0, 1, self.make_center_check_widget(0, False))

                self.tab.setItem(0, 2, QTableWidgetItem(self.tr_ui("전체 선택")))
                self.tab.setItem(0, 3, QTableWidgetItem(""))

                self.paint_all_row_header()
                for c in range(4):
                    item = self.tab.item(0, c)
                    if item:
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)
            finally:
                self.tab.blockSignals(False)
                self._table_check_lock = False

            self.tab.resizeRowsToContents()
            return

        d = curr.get('data', [])

        self._table_check_lock = True
        self.tab.blockSignals(True)
        try:
            self.tab.clearContents()
            self.tab.setRowCount(len(d) + 1)

            all_checked = len(d) > 0 and all(x.get('use_inpaint', True) for x in d)

            all_id_item = QTableWidgetItem("ALL")
            all_id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.tab.setItem(0, 0, all_id_item)

            all_check_item = QTableWidgetItem("")
            all_check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self.tab.setItem(0, 1, all_check_item)
            self.tab.setCellWidget(0, 1, self.make_center_check_widget(0, all_checked))

            self.tab.setItem(0, 2, QTableWidgetItem(self.tr_ui("전체 선택")))
            self.tab.setItem(0, 3, QTableWidgetItem(""))

            self.paint_all_row_header()
            for c in range(4):
                item = self.tab.item(0, c)
                if item:
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

            for i, x in enumerate(d):
                row = i + 1
                is_checked = bool(x.get('use_inpaint', True))

                id_item = QTableWidgetItem(str(x.get('id', i + 1)))
                id_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
                self.tab.setItem(row, 0, id_item)

                check_item = QTableWidgetItem("")
                check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
                self.tab.setItem(row, 1, check_item)
                self.tab.setCellWidget(row, 1, self.make_center_check_widget(row, is_checked))

                text_item = QTableWidgetItem(x.get('text', ''))
                text_item.setData(Qt.ItemDataRole.UserRole, str(x.get('text', '') or ''))
                trans_item = QTableWidgetItem(x.get('translated_text', ''))
                trans_item.setData(Qt.ItemDataRole.UserRole, str(x.get('translated_text', '') or ''))
                self.tab.setItem(row, 2, text_item)
                self.tab.setItem(row, 3, trans_item)

                self.set_table_row_visual(row, is_checked)
        finally:
            self.tab.blockSignals(False)
            self._table_check_lock = False

        self.tab.resizeRowsToContents()

    # =========================================================
    # 분석 / 재분석 / 번역 / 식질
    # =========================================================
    def anal(self):
        if not self.ensure_engine_ready():
            return
        if not self.paths:
            self.log("⚠️ 이미지 없음")
            return
        if not self.check_ocr_api_or_alert():
            return

        self.commit_current_page_ui_to_data(include_mask=False)

        target_idx = self.idx
        self.prepare_text_mask_slots_for_fresh_analysis(target_idx)
        self.begin_busy_state("분석")
        self.w = AnalysisWorker(self.engine, self.get_inpainting_input_path(target_idx))
        self.w.log.connect(self.log)
        self.w.finished.connect(
            lambda o, d, mm, mi, page_idx=target_idx:
                self.anal_end_for_page(page_idx, o, d, mm, mi, preserve_text_mask=False)
        )
        self.w.start()

    def reanalyze_mask(self):
        mode_idx = self.cb_mode.currentIndex()

        if mode_idx not in [2, 3]:
            return

        m = self.view.get_mask_np()
        if m is None:
            return

        target_idx = self.idx
        curr = self.data[target_idx]

        if mode_idx == 2:
            # 텍스트 마스크는 현재 토글 상태의 저장 슬롯에 저장
            self.set_active_mask(curr, m, mode_idx)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled

            # 워커에 넘길 기존 데이터는 복사본으로 넘긴다.
            # 그래야 재분석 중 기존 페이지 데이터가 직접 흔들리지 않는다.
            existing_data = copy.deepcopy(curr.get('data', []))

            if not self.check_ocr_api_or_alert():
                return

            self.begin_busy_state("텍스트 마스크 재분석")
            self.w = AnalysisWorker(
                self.engine,
                self.get_inpainting_input_path(target_idx),
                m.copy(),
                existing_data
            )
            self.w.log.connect(self.log)
            self.w.finished.connect(
                lambda o, d, mm, mi, page_idx=target_idx:
                    self.anal_end_for_page(page_idx, o, d, mm, mi, preserve_text_mask=True)
            )
            self.w.start()

        elif mode_idx == 3:
            # 페인팅 마스크는 재분석이 아니라 현재 페이지 저장만
            self.set_active_mask(curr, m, mode_idx)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
            self.log((f"💾 Painting mask saved for page {target_idx + 1}" if self.ui_language == LANG_EN else f"💾 {target_idx + 1}페이지 페인팅 마스크 저장됨"))
            self.auto_save_project()

    def prepare_text_mask_slots_for_fresh_analysis(self, page_idx):
        """
        일반 [분석]은 기존 텍스트 마스크를 기준으로 누적하지 않는다.
        재분석은 사용자가 칠한 마스크를 기준으로 보존해야 하지만,
        일반 분석은 OCR 결과로 mask_merge / mask_inpaint를 새로 만들기 때문에
        이전 텍스트 마스크가 화면/저장 슬롯에 남지 않도록 먼저 비운다.
        """
        curr = self.data.get(page_idx)
        if not curr:
            return
        try:
            curr['mask_merge'] = None
            curr['mask_inpaint'] = None
            # 텍스트 마스크는 ON/OFF 슬롯을 사용하지 않지만, 예전 버전/작업 캐시에서
            # 남아 있을 수 있는 보조 슬롯까지 같이 지워야 전체 분석이 항상 새 상태가 된다.
            curr['mask_merge_off'] = None
            # 일반 분석은 초기화에 가까운 작업이므로 기존 수동/자동 마스킹 슬롯을 모두 비운다.
            curr['mask_inpaint_off'] = None
            curr['mask_toggle_enabled'] = True
            if page_idx == getattr(self, 'idx', -1) and self.cb_mode.currentIndex() == 2:
                try:
                    self.view.set_user_mask_np(None)
                except Exception:
                    pass
        except Exception:
            pass

    def anal_end_for_page(self, page_idx, o, d, mm, mi, preserve_text_mask=False):
        """
        분석/재분석 결과를 시작 당시의 page_idx에만 반영한다.
        self.idx를 직접 쓰면 작업 도중 페이지 이동 시 다른 페이지를 덮어쓸 수 있다.

        preserve_text_mask=False: 일반 분석. 기존 텍스트 마스크 슬롯을 버리고 새 OCR 마스크로 교체한다.
        preserve_text_mask=True: 텍스트 마스크 재분석. 사용자가 칠한 재분석 마스크를 보존한다.
        """
        if page_idx < 0 or page_idx >= len(self.paths):
            self.end_busy_state("분석")
            return

        if page_idx not in self.data:
            self.data[page_idx] = {
                'ori': o,
                'data': [],
                'mask_merge': None,
                'mask_inpaint': None,
                'mask_merge_off': None,
                'mask_inpaint_off': None,
                'mask_toggle_enabled': False,
                'use_inpainted_as_source': False,
                'bg_clean': None,
                'working_source': None,
                'final_paint': None,
                'final_paint_above': None,
            }

        old_inpaint_off = self.data[page_idx].get('mask_inpaint_off')
        if not preserve_text_mask:
            old_inpaint_off = None

        if preserve_text_mask:
            # 재분석은 사용자가 칠한 텍스트 마스크를 기준으로 OCR을 다시 거는 작업이다.
            # 따라서 워커가 반환한 mm(=재분석에 사용한 마스크)을 그대로 유지한다.
            self.data[page_idx].update({
                'ori': o,
                'data': d,
                'mask_merge': mm,
                'mask_inpaint': mi,
                'mask_toggle_enabled': True,
            })
            if self.data[page_idx].get('mask_merge_off') is None:
                self.data[page_idx]['mask_merge_off'] = None
            if self.data[page_idx].get('mask_inpaint_off') is None:
                self.data[page_idx]['mask_inpaint_off'] = old_inpaint_off
            self.log((
                f"✅ Text mask re-analysis applied to page {page_idx + 1} (manual mask preserved)"
                if self.ui_language == LANG_EN
                else f"✅ {page_idx + 1}페이지 텍스트 마스크 재분석 반영 완료 (재분석 마스크 보존)"
            ))
        else:
            # 일반 분석은 새 OCR 결과를 기준으로 텍스트 마스크를 다시 만드는 작업이다.
            # 이전 mask_merge/mask_inpaint가 남으면 분석을 반복해도 이전 상태가 섞여 보일 수 있으므로
            # 텍스트 마스크 계열은 명시적으로 새 결과로 교체한다.
            self.data[page_idx].update({
                'ori': o,
                'data': d,
                'mask_merge': mm.copy() if isinstance(mm, np.ndarray) else mm,
                'mask_inpaint': mi.copy() if isinstance(mi, np.ndarray) else mi,
                'mask_merge_off': None,
                # 일반 분석은 기존 마스킹 자료를 무시하고 새로 따는 작업이므로 OFF 마스크도 초기화한다.
                'mask_inpaint_off': None,
                'mask_toggle_enabled': True,
            })
            self.log((
                f"✅ Analysis applied to page {page_idx + 1} (text mask rebuilt)"
                if self.ui_language == LANG_EN
                else f"✅ {page_idx + 1}페이지 분석 결과 반영 완료 (텍스트 마스크 새로 생성)"
            ))

        # 현재 보고 있는 페이지가 작업 완료된 페이지일 때만 화면 갱신
        if page_idx == self.idx:
            self.ref_tab()

            # 분석/재분석 결과 반영 직후 분석도 탭으로 이동할 때,
            # 직전 텍스트/페인팅 마스크 화면에 남아 있던 구 마스크가 mode_chg에서
            # 새 분석 결과를 덮어쓰지 않도록 마스크 자동 커밋을 잠시 막는다.
            old_skip_mode_mask_commit = getattr(self, "_skip_mode_mask_commit", False)
            self._skip_mode_mask_commit = True
            try:
                if self.cb_mode.currentIndex() != 1:
                    self.cb_mode.setCurrentIndex(1)
                else:
                    self.mode_chg(1)
            finally:
                self._skip_mode_mask_commit = old_skip_mode_mask_commit

            # ON 강제 조건 1/2: 일반 분석 또는 텍스트 마스크 재분석 완료 직후에만 켠다.
            self.set_mask_toggle_safely(True)

        # ON 강제 조건 1/2: 분석 결과가 들어온 페이지는 분석 마스크 사용 상태로 저장한다.
        # 사용자가 이후 직접 OFF로 바꾸면 다시 임의로 ON시키지 않는다.
        self.data[page_idx]['mask_toggle_enabled'] = True

        self.auto_save_project()

        # 분석/재분석은 OCR/API 결과가 반영되는 작업 경계다.
        # 결과 반영 이후에는 이전 편집 Undo로 돌아가면 마스크/텍스트 상태가 꼬일 수 있으므로
        # 성공적으로 데이터에 적용된 뒤 Undo 체인을 끊는다.
        self.break_undo_chain("reanalyze" if preserve_text_mask else "analysis")
        self.end_busy_state("텍스트 마스크 재분석" if preserve_text_mask else "분석")
        self.macro_mark_current_step_done("work_analyze")

    def _show_api_missing_and_open_settings(self, category, provider_name, detail_ko=None, detail_en=None):
        """API 설정 누락을 사용자에게 알리고 바로 API 관리창을 연다."""
        lang_en = getattr(self, "ui_language", LANG_KO) == LANG_EN
        category_map = {
            "ocr": ("OCR API", "OCR API"),
            "inpaint": ("인페인팅 API", "Inpainting API"),
            "translation": ("번역 API", "Translation API"),
        }
        category_ko, category_en = category_map.get(category, ("API", "API"))
        if lang_en:
            title = "API Settings Required"
            detail = detail_en or "Required API settings are missing."
            msg = (
                f"The selected {category_en} ({provider_name}) is not configured or its key is missing.\n"
                f"Please check the selected provider and fill in the required settings in [Options > API Settings].\n\n"
                f"Details: {detail}"
            )
            self.log(f"❌ {category_en} missing or invalid: {provider_name}")
        else:
            title = "API 설정 필요"
            detail = detail_ko or "필요한 API 설정이 비어 있습니다."
            msg = (
                f"선택된 {category_ko} ({provider_name}) 설정이 비어 있거나 키가 없습니다.\n"
                f"[옵션 > API 관리]에서 선택된 API와 필수 설정을 확인해 주세요.\n\n"
                f"상세: {detail}"
            )
            self.log(f"❌ {category_ko} 설정 누락: {provider_name}")
        QMessageBox.critical(self, title, msg)
        try:
            self.open_api_settings_dialog()
        except Exception as e:
            self.log((f"⚠️ Failed to open API Settings: {e}" if lang_en else f"⚠️ API 관리창 열기 실패: {e}"))
        return False

    def check_ocr_api_or_alert(self):
        """선택된 OCR API 설정이 비어 있으면 작업 시작 전에 막고 API 관리창을 연다."""
        settings = getattr(self, "api_settings", None) or ApiSettingsStore.load()
        provider = str(getattr(settings, "selected_ocr_provider", "clova") or "clova").lower()
        if provider == "google_vision":
            if not str(getattr(settings, "google_vision_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings(
                    "ocr",
                    "Google Vision OCR",
                    "Google Vision OCR API Key가 비어있습니다.",
                    "Google Vision OCR API Key is empty.",
                )
        else:
            missing = []
            if not str(getattr(settings, "clova_api_url", "") or "").strip():
                missing.append("Invoke URL")
            if not str(getattr(settings, "clova_secret_key", "") or "").strip():
                missing.append("Secret Key")
            if missing:
                return self._show_api_missing_and_open_settings(
                    "ocr",
                    "CLOVA OCR",
                    "CLOVA OCR " + ", ".join(missing) + " 설정이 비어있습니다.",
                    "CLOVA OCR " + ", ".join(missing) + " setting(s) are empty.",
                )
        return True

    def check_inpaint_api_or_alert(self):
        """선택된 인페인팅 API 설정이 비어 있으면 작업 시작 전에 막고 API 관리창을 연다."""
        settings = getattr(self, "api_settings", None) or ApiSettingsStore.load()
        provider = str(getattr(settings, "selected_inpaint_provider", "replicate_lama") or "replicate_lama").lower()
        provider_name = "Replicate Stable Diffusion Inpainting" if provider == "replicate_stable" else "Replicate LaMa"

        if provider == "replicate_stable":
            stable_token = str(getattr(settings, "stable_replicate_api_token", "") or getattr(settings, "replicate_api_token", "") or "").strip()
            if not stable_token:
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "Stable Replicate API Token이 비어있습니다.",
                    "Stable Replicate API Token is empty.",
                )
            if not str(getattr(settings, "stable_inpaint_model", "") or "").strip():
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "Stable Diffusion 인페인팅 모델명이 비어있습니다.",
                    "Stable Diffusion inpainting model name is empty.",
                )
        else:
            lama_token = str(getattr(settings, "lama_replicate_api_token", "") or getattr(settings, "replicate_api_token", "") or "").strip()
            if not lama_token:
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "LaMa Replicate API Token이 비어있습니다.",
                    "LaMa Replicate API Token is empty.",
                )
            if not str(getattr(settings, "repaint_model", "") or "").strip():
                return self._show_api_missing_and_open_settings(
                    "inpaint",
                    provider_name,
                    "LaMa 인페인팅 모델명이 비어있습니다.",
                    "LaMa inpainting model name is empty.",
                )
        return True

    def check_translation_api_key_or_alert(self, provider=None):
        """번역 API 키가 없을 때 원문 반환으로 조용히 넘어가지 않게 UI에서 먼저 막는다."""
        settings = getattr(self, "api_settings", None) or ApiSettingsStore.load()
        provider = (provider or getattr(settings, "selected_translation_provider", "openai") or self.cb_trans_provider.currentData() or "openai").lower()

        def _provider_display_name(code: str) -> str:
            mapping = {
                "openai": "OpenAI",
                "deepseek": "DeepSeek",
                "google": "Google Translate",
                "gemini": "Gemini",
                "custom": "Custom / OpenAI-Compatible",
            }
            return mapping.get((code or "").lower(), str(code or "OpenAI"))

        provider_name = _provider_display_name(provider)

        if provider == "deepseek":
            if not str(getattr(settings, "deepseek_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings("translation", provider_name, "DeepSeek API Key가 비어있습니다.", "DeepSeek API Key is empty.")
        elif provider == "google":
            if not str(getattr(settings, "google_translate_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings("translation", provider_name, "Google Translate API Key가 비어있습니다.", "Google Translate API Key is empty.")
        elif provider == "gemini":
            if not str(getattr(settings, "gemini_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings("translation", provider_name, "Gemini API Key가 비어있습니다.", "Gemini API Key is empty.")
        elif provider == "custom":
            missing = []
            if not str(getattr(settings, "custom_translation_base_url", "") or "").strip():
                missing.append("Base URL")
            if not str(getattr(settings, "custom_translation_model", "") or "").strip():
                missing.append("Model")
            if not str(getattr(settings, "custom_translation_api_key", "") or "").strip():
                missing.append("API Key")
            if missing:
                return self._show_api_missing_and_open_settings(
                    "translation",
                    provider_name,
                    "Custom 번역 API " + ", ".join(missing) + " 설정이 비어있습니다.",
                    "Custom translation API " + ", ".join(missing) + " setting(s) are empty.",
                )
        else:
            if not str(getattr(settings, "openai_api_key", "") or "").strip():
                return self._show_api_missing_and_open_settings("translation", provider_name, "OpenAI API Key가 비어있습니다.", "OpenAI API Key is empty.")

        return True

    def trans(self):
        if not self.ensure_engine_ready():
            return
        if self.idx not in self.data:
            self.log("⚠️ 번역할 데이터가 없습니다.")
            return
        curr = self.data.get(self.idx)
        if not curr or not curr.get('data'):
            self.log("⚠️ 텍스트 박스가 없어서 번역할 게 없습니다.")
            return

        try:
            self.log("⏳ 번역 요청 중... (화면이 잠시 멈출 수 있습니다)")
            QApplication.processEvents()

            texts = []
            target_rows = []
            for row in range(1, self.tab.rowCount()):
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr['data']):
                    continue
                is_checked = self.get_table_check_state(row)
                curr['data'][data_index]['use_inpaint'] = is_checked
                if not is_checked:
                    continue
                item = self.tab.item(row, 2)
                texts.append(item.text() if item else "")
                target_rows.append(row)

            if not texts:
                self.log("⚠️ 체크된 번역 대상이 없습니다.")
                return

            provider = self.cb_trans_provider.currentData()
            if not self.check_translation_api_key_or_alert(provider):
                return
            self.begin_busy_state("번역")
            chunk_size = self.get_current_translation_chunk_size()
            self.log(
                f"🌐 번역 엔진: {self.cb_trans_provider.currentText()} / "
                f"대상 {len(texts)}개 / 묶음 {chunk_size}개"
            )
            res = self.engine.translate_text_batch(
                texts,
                provider=provider,
                chunk_size=chunk_size
            )

            if len(res) != len(texts):
                QMessageBox.warning(self, self.tr_ui("번역 개수 불일치"), self.tr_msg(f"요청 {len(texts)}개 / 응답 {len(res)}개\n\n밀림 방지를 위해 결과 반영을 중단했습니다."))
                return

            self.tab.blockSignals(True)
            try:
                for row, t in zip(target_rows, res):
                    data_index = row - 1
                    if data_index < 0 or data_index >= len(curr['data']):
                        continue
                    safe_text = str(t) if t is not None else ""
                    curr['data'][data_index]['translated_text'] = safe_text
                    self.tab.setItem(row, 3, QTableWidgetItem(safe_text))
                self.paint_all_row_header()
            finally:
                self.tab.blockSignals(False)

            self.tab.resizeRowsToContents()

            # 최종 화면에서 번역을 실행한 경우, 번역문 갱신 후 화면도 한 번 갱신한다.
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)

            self.log("✅ 번역 완료")
            self.auto_save_project()

            # 번역은 외부/API 결과를 텍스트 라인에 반영하는 작업 경계다.
            # 성공 반영 후 이전 Undo 스택을 끊어 번역 전 편집 상태로 돌아가지 않게 한다.
            self.break_undo_chain("translation")

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log(f"❌ 번역 중 에러 발생: {e}")
            QMessageBox.critical(self, self.tr_ui("번역 오류"), f"{self.tr_ui("에러가 발생했습니다:")}\n{e}")
        finally:
            self.end_busy_state("번역")

    def clip_mask_to_checked_text_boxes(self, mask, data):
        """
        페인팅 마스크 토글 ON 전용:
        분석 기반 페인팅 마스크는 체크된 텍스트 박스 영역 안에서만 지우도록 제한한다.
        사용자가 ON 상태에서 박스 밖을 칠해도 실제 인페인팅 마스크에는 들어가지 않는다.
        """
        if mask is None:
            return None

        if mask.ndim == 3:
            gray = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY)
        else:
            gray = mask.copy()

        h, w = gray.shape[:2]
        allowed = np.zeros((h, w), dtype=np.uint8)

        for item in data or []:
            if not item.get('use_inpaint', True):
                continue
            rect = item.get('rect')
            if not rect or len(rect) < 4:
                continue
            try:
                rx, ry, rw, rh = [int(v) for v in rect[:4]]
            except Exception:
                continue

            x1 = max(0, rx)
            y1 = max(0, ry)
            x2 = min(w, rx + max(0, rw))
            y2 = min(h, ry + max(0, rh))
            if x2 > x1 and y2 > y1:
                allowed[y1:y2, x1:x2] = 255

        return cv2.bitwise_and(gray, allowed)

    def build_inpainting_payload_for_current_toggle(self, curr):
        """
        인페인팅 입력 분기:
        - 토글 ON: 분석 기반 페인팅 마스크를 체크된 텍스트 박스 안으로 제한한다.
        - 토글 OFF: 텍스트 박스/체크 상태를 무시하고 OFF 페인팅 마스크를 그대로 사용한다.
        """
        data = curr.get('data', [])
        if self.mask_toggle_enabled:
            mask = curr.get('mask_inpaint')
            if mask is not None:
                mask = self.clip_mask_to_checked_text_boxes(mask, data)
            return data, mask

        # OFF 상태는 분석 없이 직접 칠한 마스크로만 인페인팅한다.
        # engine.execute_inpainting()이 data의 체크박스 영역을 추가로 건드리지 않도록 data를 비워 넘긴다.
        return [], curr.get('mask_inpaint_off')

    def run_inpainting(self):
        if not self.ensure_engine_ready():
            return
        if not self.check_inpaint_api_or_alert():
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        self.commit_current_page_ui_to_data()
        input_path = self.get_inpainting_input_path(self.idx)
        if not input_path or not os.path.exists(input_path):
            self.log("⚠️ 인페인팅 입력 이미지 파일을 만들지 못했습니다.")
            return

        inpaint_data, inpaint_mask = self.build_inpainting_payload_for_current_toggle(curr)
        inpaint_mask = self.normalize_inpaint_mask_to_input_image(input_path, inpaint_mask)

        if not self.mask_toggle_enabled and inpaint_mask is None:
            self.log("⚠️ OFF 페인팅 마스크가 없습니다. 마스크 OFF 상태에서는 직접 칠한 마스크가 필요합니다.")
            return

        if inpaint_mask is not None and int(np.count_nonzero(inpaint_mask)) == 0:
            self.log("⚠️ 인페인팅 마스크가 비어 있습니다.")
            return

        self.log(f"🧾 인페인팅 입력: {input_path}")
        self.begin_busy_state("인페인팅")
        self.iw = InpaintWorker(self.engine, input_path, inpaint_data, inpaint_mask)
        self.iw.log.connect(self.log)
        self.iw.finished.connect(self.inpaint_end)
        self.iw.start()

    def inpaint_end(self, bg):
        if not bg:
            self.log("⚠️ 식질 실패: 결과물이 비어있습니다.")
            self.end_busy_state("인페인팅")
            self.macro_mark_current_step_done("work_inpaint")
            return

        curr = self.data[self.idx]

        img = self.bg_clean_to_np_image(bg)
        if img is not None:
            img = self.normalize_image_to_original_size(self.idx, img)
            encoded = self.encode_np_image_to_png_bytes(img)
            curr['bg_clean'] = encoded if encoded is not None else bg

            # 인페인팅을 원본으로 쓰는 상태라면, 새 결과를 작업중 원본으로 갱신한다.
            # 이렇게 해야 1차 인페인팅 결과 위에 2차/3차 인페인팅을 계속 덧칠하는 흐름이 된다.
            if curr.get('use_inpainted_as_source'):
                self.set_working_source_image(curr, img)
        else:
            curr['bg_clean'] = bg

        # 최종화면 브러시 페인팅은 "출력 전 임시 보정 레이어"다.
        # 원본으로 반영(Alt+P)하지 않은 상태에서 다시 인페인팅하면,
        # 새 인페인팅 결과를 기준으로 초기화되어야 하므로 페인팅 레이어를 비운다.
        curr['final_paint'] = None
        curr['final_paint_above'] = None

        self.auto_save_project()
        self.refresh_text_only()

        # 인페인팅은 배경 이미지와 최종 페인팅 레이어 기준을 바꾸는 작업 경계다.
        # 성공 반영 후 이전 Undo 스택을 끊어 인페인팅 전 상태로 되돌아가지 않게 한다.
        self.break_undo_chain("inpaint")
        self.end_busy_state("인페인팅")
        self.macro_mark_current_step_done("work_inpaint")

    # =========================================================
    # 체크 / 박스 / 텍스트 갱신
    # =========================================================
    def toggle_check_from_box(self, data_item):
        # 분석도 화면에서만 박스 클릭 토글 허용
        # 0: 원본 / 1: 분석도 / 2: 텍스트 마스크 / 3: 페인팅 마스크 / 4: 최종결과
        if self.cb_mode.currentIndex() != 1:
            return

        curr = self.data.get(self.idx)
        if not curr or 'data' not in curr:
            return

        try:
            data_index = curr['data'].index(data_item)
        except ValueError:
            return

        new_state = not data_item.get('use_inpaint', True)
        table_row = data_index + 1
        self.apply_table_check_state(table_row, new_state)
        self.log((f"🔄 Box click toggle: ID {data_item.get('id')} = {'ON' if new_state else 'OFF'}" if self.ui_language == LANG_EN else f"🔄 박스 클릭 토글: ID {data_item.get('id')} = {'ON' if new_state else 'OFF'}"))

    def refresh_boxes_only(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        for item in list(self.view.scene.items()):
            if item.zValue() >= 20:
                self.view.scene.removeItem(item)
        self.view.draw_static_boxes(curr.get('data', []))

    def refresh_after_text_line_change(self, autosave=True):
        """텍스트 라인/ID/체크 상태가 바뀐 뒤 현재 탭 표시를 즉시 갱신한다.

        분석도/텍스트 마스크/페인팅 마스크 탭은 왼쪽 번호 박스가 scene에
        따로 그려져 있으므로 data의 id만 바꿔서는 화면 번호가 갱신되지 않는다.
        최종결과 탭은 TypesettingItem을 다시 만들어야 선택/변형 영역까지 맞는다.
        """
        try:
            mode = int(self.cb_mode.currentIndex())
        except Exception:
            mode = 0

        if mode in (1, 2, 3):
            self.refresh_boxes_only()
        elif mode == 4:
            old_suppress = getattr(self, "_suppress_mode_undo", False)
            self._suppress_mode_undo = True
            try:
                self.mode_chg(4)
            finally:
                self._suppress_mode_undo = old_suppress

        if autosave:
            self.auto_save_project()

    def refresh_text_only(self):
        curr = self.data.get(self.idx)
        if not curr:
            self.log("⚠️ 데이터가 없습니다.")
            return
        if not curr.get('bg_clean'):
            self.log("⚠️ 인페인팅을 먼저 해주세요.")
            return

        self.commit_current_page_ui_to_data()
        self.cb_mode.setCurrentIndex(4)
        self.mode_chg(4)
        self.log("✨ 텍스트 갱신 완료")
        self.auto_save_project()

    def on_text_item_moved(self, message):
        self.log(message)
        self.auto_save_project()

    def on_table_item_changed(self, item):
        self.tab.resizeRowsToContents()
        if self.idx not in self.data:
            return
        curr_data = self.data.get(self.idx)
        if not curr_data or 'data' not in curr_data:
            return

        row = item.row()
        col = item.column()

        # 텍스트 라인 수정은 현재 페이지 data 리스트만 저장하는 경량 Undo로 처리한다.
        # 비교 기준은 curr_data가 아니라 셀 생성 시 UserRole에 넣어둔 직전 텍스트다.
        # 이렇게 해야 표 편집/동기화 순서가 꼬여도 수정 전 상태를 안정적으로 잡을 수 있다.
        if row > 0 and col in (2, 3):
            data_index = row - 1
            if 0 <= data_index < len(curr_data['data']):
                key = 'text' if col == 2 else 'translated_text'
                new_text = str(item.text() or '')
                role_old = item.data(Qt.ItemDataRole.UserRole)
                old_text = str(role_old if role_old is not None else curr_data['data'][data_index].get(key, '') or '')
                if new_text != old_text:
                    self.push_text_line_undo('원문 텍스트 수정' if col == 2 else '번역문 텍스트 수정')
                    curr_data['data'][data_index][key] = new_text
                    item.setData(Qt.ItemDataRole.UserRole, new_text)
                    if col == 3:
                        try:
                            self.shrink_text_rect_to_content(curr_data['data'][data_index])
                        except Exception:
                            pass
                    if self.cb_mode.currentIndex() == 4:
                        old_suppress = getattr(self, "_suppress_mode_undo", False)
                        self._suppress_mode_undo = True
                        try:
                            self.mode_chg(4)
                        finally:
                            self._suppress_mode_undo = old_suppress
                    self.auto_save_project()
            return

        if col != 1:
            return

        # 체크박스는 현재 중앙 정렬용 QWidget으로 표시되지만,
        # 구버전 프로젝트/예외 상황에서 QTableWidgetItem 신호가 들어오면 같은 처리 함수로 넘긴다.
        try:
            is_checked = item.checkState() == Qt.CheckState.Checked
        except Exception:
            is_checked = self.get_table_check_state(row)
        self.apply_table_check_state(row, is_checked)

    def upd_map(self):
        curr_data = self.data[self.idx]
        active_count = 0
        self._table_check_lock = True
        self.tab.blockSignals(True)
        try:
            for row in range(1, self.tab.rowCount()):
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr_data['data']):
                    continue
                is_checked = self.get_table_check_state(row)
                curr_data['data'][data_index]['use_inpaint'] = is_checked
                if is_checked:
                    active_count += 1
                self.set_table_row_visual(row, is_checked)

            all_checked = active_count == len(curr_data['data']) and len(curr_data['data']) > 0
            self.set_table_check_state(0, all_checked)
            self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)
            self._table_check_lock = False

        if self.cb_mode.currentIndex() in [1, 2, 3]:
            self.refresh_boxes_only()
        self.log(f"🔄 갱신 완료 (활성: {active_count}개) - 비활성 행은 붉게 표시됨")
        self.auto_save_project()

    # =========================================================
    # 화면 모드 / 페이지 이동 / 출력 / 배치
    # =========================================================
    def mode_chg(self, i):
        # cb_mode.currentIndexChanged는 콤보박스 값이 이미 바뀐 뒤 들어오므로,
        # 직전 탭은 cb_mode가 아니라 별도 추적값(_current_work_mode)을 기준으로 잡는다.
        old_mode_for_undo = int(getattr(self, "_current_work_mode", getattr(self, "last_mode", 0)) or 0)
        new_mode_for_undo = int(i)
        # 마스크 토글처럼 "같은 탭을 새 마스크 슬롯으로 다시 그리기" 위한 내부 갱신은
        # 사용자가 탭을 이동한 작업이 아니므로 Undo 스택에 탭 변경으로 기록하면 안 된다.
        suppress_mode_undo = bool(
            getattr(self, "_suppress_mode_undo", False)
            or getattr(self, "_mask_toggle_refreshing", False)
        )
        track_mode_change = (
            old_mode_for_undo != new_mode_for_undo
            and not suppress_mode_undo
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
            and not getattr(self, "_project_undo_restore_lock", False)
            and bool(getattr(self, "paths", []))
        )
        if track_mode_change:
            try:
                self.project_ui_view_states[self.view_state_key(self.idx, old_mode_for_undo)] = self.capture_view_state()
                rec = self.make_ui_undo_record("작업 탭 변경", self.idx, mode=old_mode_for_undo)
                rec["view_state"] = copy.deepcopy(self.project_ui_view_states.get(self.view_state_key(self.idx, old_mode_for_undo)) or {})
                self.append_project_undo_record(rec)
            except Exception:
                pass

        if getattr(self, "inline_text_editor", None) is not None:
            self.finish_inline_text_edit(commit=True, refresh=False)

        # 이전 마스크 탭에서 벗어나기 전에 자동 반영.
        # 단, 페이지 로딩/일괄 작업 중에는 절대 화면 마스크를 저장하지 않는다.
        if (
            not self.is_page_loading
            and not self.is_batch_running
            and not getattr(self, "_skip_mode_mask_commit", False)
            and self.last_mode in [2, 3]
        ):
            curr = self.data.get(self.idx)
            m = self.view.get_mask_np()
            if curr is not None and m is not None:
                self.set_active_mask(curr, m, self.last_mode)
                curr['mask_toggle_enabled'] = self.mask_toggle_enabled
                self.auto_save_project()

        if (
            not self.is_page_loading
            and not self.is_batch_running
            and self.last_mode == 4
        ):
            curr = self.data.get(self.idx)
            if curr is not None and hasattr(self.view, "get_final_paint_png_bytes"):
                curr['final_paint'] = self.view.get_final_paint_png_bytes()
                if hasattr(self.view, "get_final_paint_above_png_bytes"):
                    curr['final_paint_above'] = self.view.get_final_paint_above_png_bytes()
                self.auto_save_project()

        # 사용자가 작업 탭을 바꾸면 브러시/지우개/요술봉/텍스트 입력 같은 도구는
        # 새 탭에서 그대로 이어지면 오작동하기 쉽다. 탭 이동은 항상 이동 모드로 정리한다.
        auto_move_on_tab_change = (
            old_mode_for_undo != new_mode_for_undo
            and not suppress_mode_undo
            and not getattr(self, "is_loading_project", False)
            and not getattr(self, "is_page_loading", False)
            and not getattr(self, "is_batch_running", False)
            and not getattr(self, "_project_undo_restore_lock", False)
        )
        if auto_move_on_tab_change and getattr(self.view, "draw_mode", None):
            self.set_tool(None)

        preserve_view_state = (not self.is_page_loading) and bool(self.view.scene.items())
        saved_transform = self.view.transform() if preserve_view_state else None
        saved_h_scroll = self.view.horizontalScrollBar().value() if preserve_view_state else None
        saved_v_scroll = self.view.verticalScrollBar().value() if preserve_view_state else None

        def restore_view_state_later():
            if not preserve_view_state or saved_transform is None:
                return

            def _restore():
                try:
                    self.view.setTransform(saved_transform)
                    if saved_h_scroll is not None:
                        self.view.horizontalScrollBar().setValue(saved_h_scroll)
                    if saved_v_scroll is not None:
                        self.view.verticalScrollBar().setValue(saved_v_scroll)
                except Exception:
                    pass

            # centerOn은 스크롤바 정수 반올림 때문에 반복 탭 이동 시 좌우로 누적 오차가 생길 수 있다.
            # 그래서 저장된 스크롤바 값을 직접 복원한다.
            QTimer.singleShot(0, _restore)
            QTimer.singleShot(30, _restore)
            QTimer.singleShot(80, _restore)

        self.last_mode = i
        self._current_work_mode = i
        self.update_paint_toolbar_visibility()

        curr = self.data.get(self.idx)
        if not curr:
            if hasattr(self, "magic_wand_bar"):
                self.magic_wand_bar.hide()
            if hasattr(self, "mask_wrap_bar"):
                self.mask_wrap_bar.hide()
            if hasattr(self, "final_edit_bar"):
                self.final_edit_bar.hide()
            return

        if i != 4 and getattr(self.view, "draw_mode", None) == 'paste_text':
            self.set_tool(None)

        if i not in [2, 3] and getattr(self.view, "draw_mode", None) in ('magic_wand', 'mask_wrap'):
            self.set_tool(None)
        elif hasattr(self, "magic_wand_bar"):
            self.magic_wand_bar.setVisible(getattr(self.view, "draw_mode", None) == 'magic_wand' and i in [2, 3])
        if hasattr(self, "mask_wrap_bar"):
            self.mask_wrap_bar.setVisible(getattr(self.view, "draw_mode", None) == 'mask_wrap' and i in [2, 3])
        self.final_edit_bar.hide()
        self.update_final_paint_option_bar_visibility()

        source_img = self.get_source_display_image(self.idx)

        if i == 0:
            self.view.set_image(source_img, fit=not preserve_view_state)
        elif i == 1:
            self.view.set_image(source_img, fit=not preserve_view_state)
            self.view.draw_static_boxes(curr['data'])
        elif i == 2:
            self.view.set_overlay(source_img, self.get_active_mask(curr, 2), QColor(255, 0, 0, 100), fit=not preserve_view_state)
            self.view.draw_static_boxes(curr['data'])
        elif i == 3:
            self.view.set_overlay(source_img, self.get_active_mask(curr, 3), QColor(0, 0, 255, 100), fit=not preserve_view_state)
            self.view.draw_static_boxes(curr['data'])
        elif i == 4:
            self.ensure_item_style_defaults_for_page(self.idx)
            final_base = self.final_base_image_for_page(self.idx)
            self.view.set_image(final_base, fit=not preserve_view_state)
            self.view.set_final_paint_overlay(curr.get('final_paint'), curr.get('final_paint_above'), fit=False)
            self.update_final_paint_z_order()
            self.view.draw_movable_texts(
                curr['data'],
                self.cb_font.currentFont().family(),
                self.sb_font_size.value(),
                self.sb_strk.value(),
                show_text=self.cb_show_final_text.isChecked(),
                text_color=self.default_text_color,
                stroke_color=self.default_stroke_color,
                align=self.default_align,
            )

        restore_view_state_later()

        if track_mode_change:
            try:
                self.remember_current_view_state()
                self.auto_save_project()
            except Exception:
                pass

    def prev(self):
        if not self.paths:
            return

        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        self.push_project_undo('페이지 이동')
        self.auto_save_project()

        self.idx = (self.idx - 1) % len(self.paths)
        self.load()
        self.restore_current_view_state_later()
        self.auto_save_project()

    def next(self):
        if not self.paths:
            return

        self.commit_current_page_ui_to_data()
        self.remember_current_view_state()
        self.push_project_undo('페이지 이동')
        self.auto_save_project()

        self.idx = (self.idx + 1) % len(self.paths)
        self.load()
        self.restore_current_view_state_later()
        self.auto_save_project()

    def jump_page(self):
        if not self.paths:
            return
        num, ok = QInputDialog.getInt(
            self,
            self.tr_ui("페이지 이동"),
            self.tr_msg(f"페이지 (1~{len(self.paths)}):"),
            self.idx + 1,
            1,
            len(self.paths),
        )
        if ok:
            if num - 1 == self.idx:
                return
            self.commit_current_page_ui_to_data()
            self.remember_current_view_state()
            self.push_project_undo('페이지 이동')
            self.auto_save_project()
            self.idx = num - 1
            self.load()
            self.restore_current_view_state_later()
            self.auto_save_project()

    def qt_pixmap_from_image_source(self, img):
        """출력용 Qt 렌더에 사용할 QPixmap을 만든다.
        viewer._np2pix와 같은 기준으로 BGR(OpenCV) 이미지를 Qt 화면 색상에 맞춘다.
        """
        try:
            if img is None:
                return QPixmap()

            if isinstance(img, (bytes, bytearray)):
                qimg = QImage.fromData(bytes(img))
                if not qimg.isNull():
                    return QPixmap.fromImage(qimg)
                return QPixmap()

            if isinstance(img, str):
                qimg = QImage(img)
                if not qimg.isNull():
                    return QPixmap.fromImage(qimg)
                # 한글/특수 경로 방어: cv2로 읽어서 다시 넘긴다.
                try:
                    arr = np.fromfile(img, np.uint8)
                    decoded = cv2.imdecode(arr, cv2.IMREAD_UNCHANGED)
                    if decoded is not None:
                        return self.qt_pixmap_from_image_source(decoded)
                except Exception:
                    pass
                return QPixmap()

            if isinstance(img, QImage):
                return QPixmap.fromImage(img)

            if isinstance(img, QPixmap):
                return img

            if isinstance(img, np.ndarray):
                if img.ndim == 2:
                    h, w = img.shape[:2]
                    qimg = QImage(img.data, w, h, w, QImage.Format.Format_Grayscale8).copy()
                    return QPixmap.fromImage(qimg)

                if img.ndim == 3:
                    h, w, c = img.shape
                    if c == 3:
                        # OpenCV BGR → Qt RGB. viewer._np2pix와 동일한 처리.
                        qimg = QImage(img.data, w, h, c * w, QImage.Format.Format_RGB888).rgbSwapped().copy()
                        return QPixmap.fromImage(qimg)
                    if c == 4:
                        # RGBA 계열 페인트 레이어 등은 viewer 기준과 맞춰 그대로 처리한다.
                        qimg = QImage(img.data, w, h, c * w, QImage.Format.Format_RGBA8888).copy()
                        return QPixmap.fromImage(qimg)
        except Exception:
            pass
        return QPixmap()

    def render_current_final_scene_to_image_qt(self, result_path):
        """현재 최종화면에 실제로 떠 있는 QGraphicsScene을 그대로 PNG로 저장한다.

        Result 출력은 화면에서 보이는 최종 결과와 같아야 한다.
        이전 방식은 data를 기준으로 TypesettingItem을 다시 만들어 렌더했기 때문에,
        텍스트 편집/영역 재설정/변형 직후의 화면 상태와 몇 픽셀 어긋날 수 있었다.
        최종화면 탭에서 출력할 때는 현재 scene 자체를 렌더해서 화면 기준을 최우선으로 맞춘다.
        """
        try:
            if not hasattr(self, 'cb_mode') or self.cb_mode.currentIndex() != 4:
                return False
            scene = self._safe_graphics_scene()
            if scene is None:
                return False

            rect = scene.sceneRect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                rect = scene.itemsBoundingRect()
            if rect.isNull() or rect.width() <= 0 or rect.height() <= 0:
                return False

            w = max(1, int(round(rect.width())))
            h = max(1, int(round(rect.height())))

            # 출력 PNG에는 선택 박스/점선/변형 핸들이 찍히면 안 된다.
            # 현재 scene을 그대로 쓰되, 렌더 순간에만 보조 가이드를 숨긴다.
            text_items = []
            old_suppress = []
            try:
                for it in scene.items():
                    if isinstance(it, TypesettingItem):
                        text_items.append(it)
                        old_suppress.append(bool(getattr(it, 'suppress_guides', False)))
                        it.suppress_guides = True
                        it.update()
            except RuntimeError:
                return False

            out = QImage(w, h, QImage.Format.Format_RGB32)
            out.fill(Qt.GlobalColor.white)
            painter = QPainter(out)
            try:
                try:
                    painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                    painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
                except Exception:
                    pass
                scene.render(painter, QRectF(0, 0, w, h), rect)
            finally:
                painter.end()
                for it, old in zip(text_items, old_suppress):
                    try:
                        it.suppress_guides = old
                        it.update()
                    except RuntimeError:
                        pass
                    except Exception:
                        pass

            try:
                os.makedirs(os.path.dirname(result_path), exist_ok=True)
            except Exception:
                pass
            if out.save(result_path, 'PNG'):
                return True

            try:
                tmp_path = os.path.join(os.path.dirname(result_path), '__ysb_current_scene_result_tmp.png')
                if out.save(tmp_path, 'PNG'):
                    shutil.move(tmp_path, result_path)
                    return True
            except Exception:
                pass
            return False
        except Exception as e:
            try:
                self.log(f"⚠️ 현재 최종화면 기준 출력 실패: {e}")
            except Exception:
                pass
            return False

    def render_final_result_image_qt(self, result_path, bg_image, paint_above_data=None):
        """최종 PNG를 Qt 최종화면과 같은 렌더러로 다시 저장한다.

        엔진의 PIL 렌더는 검수용으로 충분하지만, QGraphicsPath 기반 최종화면과
        폰트 메트릭/기준선이 달라 텍스트 좌표가 몇 픽셀씩 어긋날 수 있다.
        그래서 Result_XXXX.png는 실제 최종화면과 같은 TypesettingItem을
        오프스크린 QGraphicsScene에 올려 다시 렌더한다.
        """
        curr = self.data.get(self.idx)
        if not curr:
            return False

        bg_pix = self.qt_pixmap_from_image_source(bg_image)
        if bg_pix.isNull() or bg_pix.width() <= 0 or bg_pix.height() <= 0:
            return False

        scene = QGraphicsScene()
        bg_item = scene.addPixmap(bg_pix)
        bg_item.setZValue(0)
        scene.setSceneRect(QRectF(0, 0, bg_pix.width(), bg_pix.height()))

        visible_items = []
        for d in curr.get('data', []):
            if not d.get('use_inpaint', True):
                continue
            if not str(d.get('translated_text', '') or '').strip() and not d.get('force_show'):
                continue
            visible_items.append(d)

        total_items = len(visible_items)
        for order_idx, d in enumerate(visible_items):
            item = TypesettingItem(
                d,
                self.cb_font.currentFont().family(),
                self.sb_font_size.value(),
                self.sb_strk.value(),
                None,
                text_color=self.default_text_color,
                stroke_color=self.default_stroke_color,
                align=self.default_align,
            )
            # 출력 PNG에는 작업용 점선 박스/선택 박스/변형 핸들을 찍지 않는다.
            item.suppress_guides = True
            item.setSelected(False)
            item.setZValue(30 + (total_items - order_idx))
            scene.addItem(item)

        if paint_above_data is not None and hasattr(self, "view") and hasattr(self.view, "_paint_qimage_from_data"):
            try:
                above_qimg = self.view._paint_qimage_from_data(paint_above_data, bg_pix.width(), bg_pix.height())
                if not above_qimg.isNull():
                    above_item = scene.addPixmap(QPixmap.fromImage(above_qimg))
                    above_item.setZValue(80)
            except Exception:
                pass

        out = QImage(bg_pix.width(), bg_pix.height(), QImage.Format.Format_RGB32)
        out.fill(Qt.GlobalColor.white)
        painter = QPainter(out)
        try:
            try:
                painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)
                painter.setRenderHint(QPainter.RenderHint.TextAntialiasing, True)
                painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform, True)
            except Exception:
                pass
            scene.render(
                painter,
                QRectF(0, 0, bg_pix.width(), bg_pix.height()),
                QRectF(0, 0, bg_pix.width(), bg_pix.height()),
            )
        finally:
            painter.end()
            scene.clear()

        try:
            os.makedirs(os.path.dirname(result_path), exist_ok=True)
        except Exception:
            pass

        if out.save(result_path, "PNG"):
            return True

        # 일부 환경에서 한글 경로 저장이 실패할 때를 대비한 임시 파일 우회.
        try:
            tmp_path = os.path.join(os.path.dirname(result_path), "__ysb_qt_result_tmp.png")
            if out.save(tmp_path, "PNG"):
                shutil.move(tmp_path, result_path)
                return True
        except Exception:
            pass
        return False

    def export_result(self):
        curr = self.data.get(self.idx)
        if not curr:
            self.log("⚠️ 데이터 없음")
            return
        self.commit_current_page_ui_to_data()
        if self.cb_mode.currentIndex() == 4 and hasattr(self.view, "get_final_paint_png_bytes"):
            curr['final_paint'] = self.view.get_final_paint_png_bytes()
            if hasattr(self.view, "get_final_paint_above_png_bytes"):
                curr['final_paint_above'] = self.view.get_final_paint_above_png_bytes()
        self.ensure_item_style_defaults_for_page(self.idx)
        export_bg = curr.get('bg_clean')
        if export_bg is None:
            export_bg = self.final_base_image_for_page(self.idx)
        if export_bg is None:
            export_bg = self.get_source_display_image(self.idx)

        if curr.get('final_paint'):
            base_img = self.bg_clean_to_np_image(export_bg)
            export_img = self.compose_final_paint_on_bgr(base_img, curr.get('final_paint'))
            export_bg = self.encode_np_image_to_png_bytes(export_img) or export_img
        p = self.engine.export_project_result(curr['data'], self.paths[self.idx], export_bg, self.cb_font.currentFont().family(), self.sb_strk.value(), self.sb_font_size.value(), output_root=self.get_output_root())
        result_path = os.path.join(self.get_output_root(), "Result", f"Result_{Path(self.paths[self.idx]).stem}.png")

        # Result PNG는 포토샵 스크립트용 엔진 렌더(PIL)가 아니라 Qt 렌더로 다시 저장한다.
        # 최종화면 탭에서 출력하는 경우에는 data로 다시 조립하지 않고,
        # 현재 화면에 실제로 떠 있는 QGraphicsScene을 그대로 렌더한다.
        # 이렇게 해야 글꼴/영역 재설정/변형 직후의 화면과 출력 PNG가 1:1에 가깝게 맞는다.
        qt_result_rendered = False
        if self.cb_mode.currentIndex() == 4:
            qt_result_rendered = self.render_current_final_scene_to_image_qt(result_path)
            if qt_result_rendered:
                self.log("🖼️ 현재 최종화면 기준으로 최종 이미지 재저장")

        if not qt_result_rendered:
            qt_result_rendered = self.render_final_result_image_qt(result_path, export_bg, curr.get('final_paint_above'))
            if qt_result_rendered:
                self.log("🖼️ 최종 이미지 Qt 재구성 렌더 기준으로 재저장")

        # 텍스트 위 페인팅 레이어는 텍스트 렌더링 이후 최종 PNG 위에 다시 합성한다.
        # 단, Qt 렌더가 성공한 경우에는 위 페인팅까지 함께 렌더했으므로 중복 합성하지 않는다.
        if curr.get('final_paint_above') and (not qt_result_rendered) and os.path.exists(result_path):
            try:
                result_img = cv2.imdecode(np.fromfile(result_path, np.uint8), cv2.IMREAD_COLOR)
                if result_img is not None:
                    result_img = self.compose_final_paint_on_bgr(result_img, curr.get('final_paint_above'))
                    ok, buf = cv2.imencode(".png", result_img)
                    if ok:
                        buf.tofile(result_path)
            except Exception as e:
                self.log(f"⚠️ 텍스트 위 페인팅 출력 합성 실패: {e}")

        self.log(f"✅ 스크립트 저장: {p}")
        self.log(f"🖼️ 최종 이미지 저장: {result_path}")
        self.auto_save_project()

    def confirm_batch_operation(self, title, detail=None):
        # 매크로 안에 포함된 일괄 작업은 run_macro()에서 최초 1회만 확인한다.
        # 중간 단계마다 확인창이 뜨면 자동화 흐름이 끊기므로 여기서는 통과시킨다.
        if getattr(self, "macro_running", False):
            return True

        message = detail or f"{title}을(를) 실행할까요?"
        return QMessageBox.question(
            self,
            self.tr_msg(title),
            self.tr_msg(message),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def run_batch(self, mode):
        if getattr(self, "is_batch_running", False):
            QMessageBox.information(self, self.tr_ui("일괄 작업 중"), self.tr_msg("이미 일괄 작업이 진행 중입니다.\n현재 작업이 끝난 뒤 다시 실행해 주세요."))
            return
        if not self.ensure_engine_ready():
            return
        if not self.paths:
            self.log("⚠️ 파일 없음")
            return

        mode_names = {
            "analyze": "일괄 분석",
            "translate": "일괄 번역",
            "inpaint": "일괄 인페인팅",
            "refresh": "일괄 텍스트 갱신",
            "export": "일괄 출력",
        }
        title = mode_names.get(mode, "일괄 작업")

        if mode == "analyze":
            if not self.check_ocr_api_or_alert():
                return
        if mode == "inpaint":
            if not self.check_inpaint_api_or_alert():
                return
        if mode == "translate":
            if not self.check_translation_api_key_or_alert(self.cb_trans_provider.currentData()):
                return
        if getattr(self, "ui_language", LANG_KO) == LANG_EN:
            batch_message = f"Run {self.tr_ui(title)} on total {len(self.paths)} page(s)?"
        else:
            batch_message = f"{title}을(를) 총 {len(self.paths)}페이지에 실행합니다."
        if not self.confirm_batch_operation(title, batch_message):
            self.log(f"↩️ {title} 취소")
            return

        # 일괄 시작 전 현재 페이지의 UI 상태를 한 번만 확정한다.
        # 일괄 분석은 일반 분석과 동일하게 기존 마스크를 무시하고 새로 따야 하므로
        # 현재 화면 마스크를 데이터에 다시 저장하지 않는다.
        self.commit_current_page_ui_to_data(include_mask=(mode != "analyze"))
        self.auto_save_project()

        self.is_batch_running = True
        self.current_batch_mode = mode
        self.begin_busy_state(title)
        self.set_project_action_interlock(True)

        self.bw = UniversalBatchWorker(self, mode)
        self.bw.progress.connect(self.log)
        self.bw.finished_item.connect(self.on_batch_item_finished)
        self.bw.finished_all.connect(lambda m=mode: self.on_batch_finished(m))
        self.bw.start()

    def on_batch_item_finished(self, i, payload=None):
        # workers.py가 payload를 넘기는 새 구조와, main.data를 직접 갱신하는 구 구조를 모두 지원한다.
        # 일괄 중에는 self.load()를 호출하지 않는다. 화면에 남은 마스크가 다른 페이지에 저장될 수 있기 때문.
        if i < 0 or i >= len(self.paths):
            return

        if i not in self.data:
            self.data[i] = {
                'ori': None,
                'data': [],
                'mask_merge': None,
                'mask_inpaint': None,
                'mask_merge_off': None,
                'mask_inpaint_off': None,
                'mask_toggle_enabled': False,
                'use_inpainted_as_source': False,
                'bg_clean': None,
                'working_source': None,
                'final_paint': None,
                'final_paint_above': None,
            }

        if payload:
            curr = self.data[i]
            for key, value in payload.items():
                if isinstance(value, np.ndarray):
                    curr[key] = value.copy()
                else:
                    curr[key] = value

            # 일괄 인페인팅으로 bg_clean이 새로 들어오면,
            # 원본으로 반영하지 않은 최종 페인팅 레이어는 새 결과 기준으로 초기화한다.
            if getattr(self, "current_batch_mode", None) == "inpaint" and "bg_clean" in payload:
                img = self.bg_clean_to_np_image(curr.get('bg_clean'))
                if img is not None:
                    img = self.normalize_image_to_original_size(i, img)
                    encoded = self.encode_np_image_to_png_bytes(img)
                    if encoded is not None:
                        curr['bg_clean'] = encoded
                    if curr.get('use_inpainted_as_source'):
                        self.set_working_source_image(curr, img)
                curr['final_paint'] = None
                curr['final_paint_above'] = None

        # ON 강제 조건 3: 일괄 분석으로 결과가 들어온 페이지는 분석 마스크 사용 상태로 저장한다.
        if getattr(self, "current_batch_mode", None) == "analyze":
            # 일반 일괄 분석도 개별 분석과 동일하게 이전 텍스트 마스크를 누적하지 않는다.
            # worker payload의 mask_merge / mask_inpaint가 새 기준이며, 이전 보조 텍스트 마스크는 비운다.
            self.data[i]['mask_merge_off'] = None
            self.data[i]['mask_inpaint_off'] = None
            self.data[i]['mask_toggle_enabled'] = True

    def on_batch_finished(self, mode):
        self.is_batch_running = False
        self.set_project_action_interlock(False)

        # ON 강제 조건 3: 일괄 분석 완료 직후 현재 페이지 체크박스도 ON으로 맞춘다.
        if mode == "analyze":
            if self.idx in self.data:
                self.data[self.idx]['mask_toggle_enabled'] = True
            self.set_mask_toggle_safely(True)

        # 일괄 종료 후 한 번만 저장/로드한다.
        self.auto_save_project()

        if self.paths:
            self.load()

        if mode == "analyze":
            # 일괄 분석 완료 후 분석도로 이동
            if self.cb_mode.currentIndex() != 1:
                self.cb_mode.setCurrentIndex(1)
            else:
                self.mode_chg(1)

        elif mode == "inpaint":
            # 일괄 인페인팅 완료 후 최종결과 화면으로 이동
            if self.cb_mode.currentIndex() != 4:
                self.cb_mode.setCurrentIndex(4)
            else:
                self.mode_chg(4)

        # 일괄 분석/번역/인페인팅은 여러 페이지에 외부/API 결과를 반영하는 작업 경계다.
        # 성공적으로 전체 흐름이 끝난 뒤 이전 Undo 스택을 끊는다.
        batch_boundary_kind = {
            "analyze": "batch_analysis",
            "translate": "batch_translation",
            "inpaint": "batch_inpaint",
        }.get(mode)
        if batch_boundary_kind:
            self.break_undo_chain(batch_boundary_kind)

        self.current_batch_mode = None
        self.end_busy_state({
            "analyze": "일괄 분석",
            "translate": "일괄 번역",
            "inpaint": "일괄 인페인팅",
            "export": "일괄 출력",
        }.get(mode, "일괄 작업"))
        self.macro_mark_current_step_done(self.macro_batch_key_for_mode(mode))

    def _event_matches_shortcut(self, event, key_name):
        seq = self.shortcut_settings.seq(key_name)
        if not seq or seq.isEmpty():
            return False
        key = event.key()
        if key in (Qt.Key.Key_Control, Qt.Key.Key_Shift, Qt.Key.Key_Alt, Qt.Key.Key_Meta):
            return False
        try:
            mods_value = event.modifiers().value
        except AttributeError:
            mods_value = int(event.modifiers())
        pressed = QKeySequence(mods_value | key)
        return pressed.matches(seq) == QKeySequence.SequenceMatch.ExactMatch

    def keyPressEvent(self, event):
        if self.is_text_transform_active() and (
            event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter)
            and event.modifiers() & Qt.KeyboardModifier.ControlModifier
        ):
            self.end_active_text_transform(refresh=True)
            event.accept()
            return

        key = event.key()

        # F2: 현재 편집 가능한 텍스트/이름 칸은 전체 선택.
        # 선택된 텍스트 영역/우측 텍스트 행이면 번역문 수정으로 바로 진입.
        if key == Qt.Key.Key_F2:
            fw = QApplication.focusWidget()
            if isinstance(fw, QLineEdit):
                fw.setFocus()
                fw.selectAll()
                event.accept()
                return
            if isinstance(fw, (QTextEdit, QPlainTextEdit)):
                cur = fw.textCursor()
                cur.select(QTextCursor.SelectionType.Document)
                fw.setTextCursor(cur)
                event.accept()
                return
            if self.edit_selected_translation_text_f2():
                event.accept()
                return

        # 텍스트 편집 중에도 Ctrl+Z는 YSB 전역 Undo로 처리한다.
        # 일반 글자 입력/복사/붙여넣기 등은 기존 편집기 동작을 우선한다.
        fw = QApplication.focusWidget()
        if isinstance(fw, (QTextEdit, QLineEdit)):
            mods_for_edit = event.modifiers()
            if (mods_for_edit & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_Z:
                self.handle_global_undo_shortcut()
                event.accept()
                return
            if (mods_for_edit & Qt.KeyboardModifier.ControlModifier) and key == Qt.Key.Key_Y:
                self.handle_general_redo()
                event.accept()
                return
            super().keyPressEvent(event)
            return

        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        alt = bool(mods & Qt.KeyboardModifier.AltModifier)

        # Alt+숫자: 작업탭 직접 이동
        if alt and key in (
            Qt.Key.Key_1, Qt.Key.Key_2, Qt.Key.Key_3, Qt.Key.Key_4, Qt.Key.Key_5
        ):
            tab_index = {
                Qt.Key.Key_1: 0,
                Qt.Key.Key_2: 1,
                Qt.Key.Key_3: 2,
                Qt.Key.Key_4: 3,
                Qt.Key.Key_5: 4,
            }.get(key)
            if tab_index is not None and tab_index < self.cb_mode.count():
                self.cb_mode.setCurrentIndex(tab_index)
                return

        if key == Qt.Key.Key_Delete:
            if self.cb_mode.currentIndex() == 4 and self.selected_text_data_items():
                self.delete_text_data_items(ask=True)
                return
            if getattr(self, "tab", None) is not None and self.tab.hasFocus() and self.selected_table_text_ids():
                self.delete_text_data_items(ask=True)
                return

        if ctrl and key == Qt.Key.Key_C:
            if self.cb_mode.currentIndex() == 4 and self.selected_text_data_items():
                self.copy_text_data_items()
                return

        if ctrl and key == Qt.Key.Key_V:
            if self.cb_mode.currentIndex() == 4 and self.text_clipboard:
                self.enter_text_paste_mode()
                return

        if self.cb_mode.currentIndex() == 4:
            if self._event_matches_shortcut(event, "text_font_size"):
                self.set_text_detail_focus("sb_font_size")
                return
            if self._event_matches_shortcut(event, "text_stroke_size"):
                self.set_text_detail_focus("sb_strk")
                return
            if self._event_matches_shortcut(event, "text_line_spacing"):
                self.set_text_detail_focus("sb_line_spacing")
                return
            if self._event_matches_shortcut(event, "text_letter_spacing"):
                self.set_text_detail_focus("sb_letter_spacing")
                return
            if self._event_matches_shortcut(event, "text_char_width"):
                self.set_text_detail_focus("sb_char_width")
                return
            if self._event_matches_shortcut(event, "text_char_height"):
                self.set_text_detail_focus("sb_char_height")
                return
            if self._event_matches_shortcut(event, "text_bold_toggle"):
                self.toggle_bold()
                return
            if self._event_matches_shortcut(event, "text_italic_toggle"):
                self.toggle_italic()
                return
            if self._event_matches_shortcut(event, "text_strike_toggle"):
                self.toggle_strike()
                return

        # ESC 동작:
        # - 그림판/요술봉 도구 사용 중이면 무조건 이동 모드로 복귀
        # - 최종 화면에서 텍스트가 선택되어 있으면 전체 선택 해제
        if key == Qt.Key.Key_Escape:
            if getattr(self.view, "draw_mode", None):
                self.set_tool(None)
                self.log("↔️ 이동 모드")
                return
            if self.cb_mode.currentIndex() == 4:
                self.view.scene.clearSelection()
                self.on_scene_selection_changed()
                self.log("선택 해제")
                return

        # 그림판/마스크/최종 페인팅 도구 단축키는 관련 탭에서만 사용한다.
        paint_keys = [
            "paint_magic_select", "paint_magic_expand",
            "paint_magic_tolerance_inc", "paint_magic_tolerance_dec",
            "paint_magic_expand_inc", "paint_magic_expand_dec",
            "paint_mask_cut",
            "paint_brush", "paint_erase", "paint_move",
            "paint_zoom_out", "paint_zoom_in", "paint_reanalyze", "paint_undo", "paint_redo",
            "final_paint_color", "final_paint_to_background", "final_text_tool",
            "final_paint_above_toggle", "final_paint_opacity_inc", "final_paint_opacity_dec",
        ]
        if self.cb_mode.currentIndex() not in (2, 3, 4):
            for paint_key in paint_keys:
                if self._event_matches_shortcut(event, paint_key):
                    return

        # 요술봉 전용 단축키
        if self._event_matches_shortcut(event, "paint_magic_select"):
            self.set_tool('magic_wand')
            return
        if self._event_matches_shortcut(event, "paint_magic_expand"):
            self.expand_magic_wand_selection()
            return
        if self._event_matches_shortcut(event, "paint_magic_tolerance_inc"):
            self.adjust_magic_tolerance(+1)
            return
        if self._event_matches_shortcut(event, "paint_magic_tolerance_dec"):
            self.adjust_magic_tolerance(-1)
            return
        if self._event_matches_shortcut(event, "paint_magic_expand_inc"):
            self.adjust_magic_expand_range(+1)
            return
        if self._event_matches_shortcut(event, "paint_magic_expand_dec"):
            self.adjust_magic_expand_range(-1)
            return
        if self._event_matches_shortcut(event, "paint_mask_wrap"):
            self.set_tool('mask_wrap')
            return
        if self._event_matches_shortcut(event, "paint_mask_cut"):
            self.set_tool('mask_cut')
            return
        if getattr(self.view, "draw_mode", None) in ('mask_wrap', 'mask_cut'):
            if self._event_matches_shortcut(event, "paint_mask_wrap_rect"):
                if getattr(self.view, "draw_mode", None) == 'mask_cut':
                    self.set_mask_cut_shape('rect')
                else:
                    self.set_mask_wrap_shape('rect')
                return
            if self._event_matches_shortcut(event, "paint_mask_wrap_free"):
                if getattr(self.view, "draw_mode", None) == 'mask_cut':
                    self.set_mask_cut_shape('free')
                else:
                    self.set_mask_wrap_shape('free')
                return

        if self._event_matches_shortcut(event, "work_tab_cycle"):
            self.cycle_work_tab()
            return
        if self._event_matches_shortcut(event, "work_page_prev"):
            self.prev()
            return
        if self._event_matches_shortcut(event, "work_page_next"):
            self.next()
            return

        # 최종 화면에서는 F1/글꼴 선택 단축키로 전용 글꼴 선택창을 연다.
        # 텍스트가 선택되어 있으면 선택 텍스트에 적용하고, 없으면 기본 글꼴을 바꾼다.
        if self.cb_mode.currentIndex() == 4 and self._event_matches_shortcut(event, "item_font_select"):
            self.open_font_select_dialog()
            return

        # 최종 화면에서 텍스트를 선택한 상태일 때만 작동하는 개별 텍스트 단축키
        if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
            if self._event_matches_shortcut(event, "item_font_select"):
                self.open_font_select_dialog()
                return
            if self._event_matches_shortcut(event, "item_font_inc"):
                self.push_page_text_undo('텍스트 글자 크기 증가')
                for item in self.selected_text_items():
                    item.data['font_size'] = int(item.data.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()) + 1
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
                return
            if self._event_matches_shortcut(event, "item_font_dec"):
                self.push_page_text_undo('텍스트 글자 크기 감소')
                for item in self.selected_text_items():
                    item.data['font_size'] = max(1, int(item.data.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()) - 1)
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
                return
            if self._event_matches_shortcut(event, "item_align_left"):
                self.apply_style_to_selected(align="left")
                return
            if self._event_matches_shortcut(event, "item_align_center"):
                self.apply_style_to_selected(align="center")
                return
            if self._event_matches_shortcut(event, "item_align_right"):
                self.apply_style_to_selected(align="right")
                return
            if self._event_matches_shortcut(event, "item_stroke_inc"):
                self.push_page_text_undo('텍스트 획 증가')
                for item in self.selected_text_items():
                    item.data['stroke_width'] = int(item.data.get('stroke_width', self.sb_strk.value()) or 0) + 1
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
                return
            if self._event_matches_shortcut(event, "item_stroke_dec"):
                self.push_page_text_undo('텍스트 획 감소')
                for item in self.selected_text_items():
                    item.data['stroke_width'] = max(0, int(item.data.get('stroke_width', self.sb_strk.value()) or 0) - 1)
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
                return
            if self._event_matches_shortcut(event, "item_text_color"):
                self.pick_color("item_text")
                return
            if self._event_matches_shortcut(event, "item_stroke_color"):
                self.pick_color("item_stroke")
                return

        if self.cb_mode.currentIndex() == 4:
            if self._event_matches_shortcut(event, "final_paint_color"):
                self.pick_color("final_paint")
                return
            if self._event_matches_shortcut(event, "final_paint_to_background"):
                self.apply_final_paint_to_background()
                return
            if self._event_matches_shortcut(event, "final_text_tool"):
                self.set_tool("final_text")
                return
            if self._event_matches_shortcut(event, "final_paint_above_toggle"):
                self.toggle_final_paint_above_text()
                return
            if self._event_matches_shortcut(event, "final_paint_opacity_inc"):
                self.adjust_final_paint_opacity(+5)
                return
            if self._event_matches_shortcut(event, "final_paint_opacity_dec"):
                self.adjust_final_paint_opacity(-5)
                return

        if self._event_matches_shortcut(event, "paint_brush"):
            self.set_tool('draw')
            return
        if self._event_matches_shortcut(event, "paint_erase"):
            self.set_tool('erase')
            return
        if self._event_matches_shortcut(event, "paint_move"):
            self.set_tool(None)
            return
        if self._event_matches_shortcut(event, "paint_zoom_out"):
            self.view.brush_size = max(1, self.view.brush_size - 5)
            self.log(f"➖ 브러시: {self.view.brush_size}")
            return
        if self._event_matches_shortcut(event, "paint_zoom_in"):
            self.view.brush_size += 5
            self.log(f"➕ 브러시: {self.view.brush_size}")
            return
        if self._event_matches_shortcut(event, "paint_reanalyze"):
            self.reanalyze_mask()
            return
        if self._event_matches_shortcut(event, "paint_undo"):
            self.handle_general_undo()
            return
        if self._event_matches_shortcut(event, "paint_redo"):
            self.handle_general_redo()
            return

        super().keyPressEvent(event)


_handling_fatal_exception = False

def exception_hook(exctype, value, traceback):
    global _handling_fatal_exception
    import traceback as tb
    error_msg = "".join(tb.format_exception(exctype, value, traceback))
    print(error_msg)

    # 예외 표시 중 Qt 이벤트가 다시 들어와 같은 예외를 반복 발생시키면
    # CMD에 무한히 쌓이고 프로그램 종료가 늦어진다. 한 번만 다이얼로그를 띄운다.
    if _handling_fatal_exception:
        try:
            sys.__stderr__.write(error_msg + "\n")
        except Exception:
            pass
        sys.exit(1)

    _handling_fatal_exception = True
    try:
        msg_box = QMessageBox()
        msg_box.setIcon(QMessageBox.Icon.Critical)
        msg_box.setText("치명적인 오류 발생!")
        msg_box.setInformativeText(str(value))
        msg_box.setDetailedText(error_msg)
        msg_box.exec()
    except Exception:
        pass
    sys.exit(1)


if __name__ == "__main__":
    sys.excepthook = exception_hook

    # Windows 작업표시줄이 PyQt 기본 아이콘 대신 앱 아이콘을 잡도록 지정한다.
    try:
        import ctypes
        ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("YSB.YeoksikBoongi.Tool")
    except Exception:
        pass

    app = QApplication(sys.argv)

    close_pyinstaller_boot_splash()

    # 두 번째 실행이면 기존 프로세스에 열기 요청만 전달하고 종료한다.
    # 이 경로에서는 어떤 스플래시도 만들지 않는다.
    if notify_running_instance(sys.argv[1:]):
        sys.exit(0)

    single_instance_server = SingleInstanceServer()
    if not single_instance_server.start():
        QMessageBox.warning(None, "단일 실행 경고", "단일 실행 서버를 시작하지 못했습니다.\n프로그램은 계속 실행되지만 중복 실행 차단이 정상 동작하지 않을 수 있습니다.")

    app.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))

    launcher_owned = is_launcher_splash_owner()
    write_launcher_mode_debug("after_launcher_owned_check")
    if launcher_owned:
        # 런처가 55%에서 멈추지 않도록, 런처 모드 판정 직후 즉시 진행률을 남긴다.
        report_launcher_progress(56, translate_ui_text("메인 초기화 시작 중..."))

    # 런처가 시작한 경우:
    # - 메인 스플래시는 절대 만들지 않는다.
    # - 메인은 런처의 단일 스플래시에 진행률만 보고한다.
    if launcher_owned:
        write_main_startup_signal()
        write_launcher_mode_debug("after_startup_signal")
        report_launcher_progress(58, translate_ui_text("환경 준비 중..."))

        # 작업 폴더 설정창 같은 실제 입력창이 필요하면, 런처를 먼저 닫게 한다.
        try:
            needs_setup, _reason, _kind = workspace_root_needs_setup()
        except Exception:
            needs_setup = False
        if needs_setup:
            report_launcher_progress(100, translate_ui_text("설정 화면으로 전환 중..."), done=True)
            wait_for_launcher_closed_if_needed()
            if not run_initial_workspace_setup_if_needed():
                sys.exit(0)
        else:
            if not run_initial_workspace_setup_if_needed():
                sys.exit(0)

        # 런처가 확장자 사전 확인을 처리한 경우 메인은 중복 알림을 띄우지 않는다.
        report_launcher_progress(65, translate_ui_text("환경 준비 중..."))
        prompt_update_ysbt_file_association_if_needed(None)

        report_launcher_progress(78, translate_ui_text("인터페이스 로딩 중..."))
        w = MainWindow()
        single_instance_server.set_main_window(w)

        report_launcher_progress(92, translate_ui_text("화면 구성 마무리 중..."))
        w.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))

        try:
            if len(sys.argv) > 1:
                open_arg = sys.argv[1]
                QTimer.singleShot(250, lambda p=open_arg: w.open_project_path(p, external_request=True))
        except Exception:
            pass

        report_launcher_progress(100, translate_ui_text("시작 완료"), done=True)
        wait_for_launcher_closed_if_needed()
        w.show()
        sys.exit(app.exec())

    # 메인 EXE 직접 실행:
    # - 런처가 폴더에 있더라도 호출하지 않는다.
    # - 메인 스플래시만 표시한다.
    if not run_initial_workspace_setup_if_needed():
        sys.exit(0)

    prompt_update_ysbt_file_association_if_needed(None)

    splash = make_splash_screen()
    if splash is not None:
        splash.set_progress(45, translate_ui_text("환경 준비 중..."))

    if splash is not None:
        splash.set_progress(62, translate_ui_text("인터페이스 로딩 중..."))

    w = MainWindow()
    single_instance_server.set_main_window(w)

    if splash is not None:
        splash.set_progress(88, translate_ui_text("화면 구성 마무리 중..."))

    w.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))
    w.show()

    try:
        if len(sys.argv) > 1:
            open_arg = sys.argv[1]
            QTimer.singleShot(250, lambda p=open_arg: w.open_project_path(p, external_request=True))
    except Exception:
        pass

    if splash is not None:
        splash.set_progress(100, translate_ui_text("시작 완료"))
        splash.stop()
        QApplication.processEvents()
        QTimer.singleShot(120, lambda: splash.finish(w))

    sys.exit(app.exec())
