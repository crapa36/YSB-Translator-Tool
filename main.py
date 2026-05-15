import sys
import os
import shutil
import uuid
from pathlib import Path

import copy
import json

import cv2
import numpy as np
from PyQt6.QtWidgets import *
from PyQt6.QtGui import *
from PyQt6.QtCore import *

from manga_engine import MangaProcessEngine, Config
from project_store import ProjectStore, PROJECT_FILENAME
from api_settings import ApiSettingsStore, ApiSettingsDialog, apply_settings_to_config
from shortcut_settings import ShortcutSettingsStore, ShortcutSettingsDialog, MacroSettingsDialog, TEXT_SYMBOLS, shortcut_label_map
from viewer import MuleImageViewer
from graphics_items import TypesettingItem
from delegates import MultilineDelegate
from workers import UniversalBatchWorker, AnalysisWorker, InpaintWorker
from cache_utils import get_cache_dir, get_cache_file


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
        pyi_splash.update_text("인터페이스 로딩 중...")
        pyi_splash.close()
    except Exception:
        pass


APP_OPTIONS_FILE = get_cache_file("app_options.json")
TRANSLATION_PROMPT_KEY = "translation_prompt"
TRANSLATION_GLOSSARY_TEXT_KEY = "translation_glossary_text"
TRANSLATION_GLOSSARY_PATH_KEY = "translation_glossary_path"


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
        if APP_OPTIONS_FILE.exists():
            with open(APP_OPTIONS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
    except Exception:
        pass
    return {}


def save_app_options(options):
    try:
        APP_OPTIONS_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(APP_OPTIONS_FILE, "w", encoding="utf-8") as f:
            json.dump(dict(options or {}), f, ensure_ascii=False, indent=2)
    except Exception:
        pass



class YSBSplashScreen(QSplashScreen):
    """
    로고 하단에 진행바를 직접 그리는 스플래시 화면.
    실제 로딩 퍼센트라기보다 앱 초기화 단계에 맞춘 stage progress 개념이다.
    """
    def __init__(self, pixmap):
        super().__init__(pixmap, Qt.WindowType.WindowStaysOnTopHint)
        self.setWindowFlag(Qt.WindowType.FramelessWindowHint, True)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground, False)
        self._progress = 0
        self._message = "로딩 중..."
        self._timer = QTimer(self)
        self._timer.setInterval(90)
        self._timer.timeout.connect(self._tick_progress)

    def start(self):
        self._timer.start()

    def stop(self):
        self._timer.stop()

    def _tick_progress(self):
        # 실제 로딩이 끝나기 전엔 90%까지만 자동 진행
        if self._progress < 90:
            self._progress += 1
            self.update()

    def set_progress(self, value, message=None):
        self._progress = max(0, min(100, int(value)))
        if message is not None:
            self._message = str(message)
        self.update()
        QApplication.processEvents()

    def drawContents(self, painter):
        # 바닥 진행바 영역
        margin_x = 36
        bar_h = 18
        y = self.pixmap().height() - 42
        bar_rect = QRect(margin_x, y, self.pixmap().width() - margin_x * 2, bar_h)

        painter.setRenderHint(QPainter.RenderHint.Antialiasing, True)

        # 배경 바
        painter.setPen(QPen(QColor(30, 30, 30, 210), 1))
        painter.setBrush(QColor(20, 20, 20, 200))
        painter.drawRoundedRect(bar_rect, 8, 8)

        # 진행 채움
        fill_w = int((bar_rect.width() - 4) * (self._progress / 100.0))
        if fill_w > 0:
            fill_rect = QRect(bar_rect.x() + 2, bar_rect.y() + 2, fill_w, bar_rect.height() - 4)
            painter.setPen(Qt.PenStyle.NoPen)
            painter.setBrush(QColor(255, 40, 40, 235))
            painter.drawRoundedRect(fill_rect, 6, 6)

        # 메시지 / 퍼센트
        text_rect = QRect(margin_x, y - 24, self.pixmap().width() - margin_x * 2, 20)
        painter.setPen(QColor(245, 245, 245))
        font = QFont("맑은 고딕", 10)
        painter.setFont(font)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignVCenter, self._message)
        painter.drawText(text_rect, Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignVCenter, f"{self._progress}%")

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
    splash.start()
    splash.set_progress(35, "압축 해제 완료 · 인터페이스 로딩 중...")
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

    def adjusted_scene_rect(self):
        br = self.boundingRect()
        return self.mapToScene(br).boundingRect()

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
        self.setWindowTitle("번역 프롬프트 입력")
        self.resize(760, 520)

        layout = QVBoxLayout(self)

        info = QLabel(
            "AI 번역 API에 함께 전달할 프롬프트를 입력합니다.\n"
            "확인을 누르면 옵션 캐시에 저장되고, 닫기를 누르면 저장하지 않고 나갑니다."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.text_edit = QTextEdit()
        self.text_edit.setPlainText(str(prompt_text or ""))
        self.text_edit.setPlaceholderText("예: 일본어를 한국어로 자연스럽게 번역해줘. 캐릭터 말투와 줄바꿈을 유지해줘.")
        layout.addWidget(self.text_edit, 1)

        buttons = QDialogButtonBox()
        buttons.addButton("확인", QDialogButtonBox.ButtonRole.AcceptRole)
        buttons.addButton("닫기", QDialogButtonBox.ButtonRole.RejectRole)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def get_prompt_text(self):
        return self.text_edit.toPlainText()


class GlossaryDialog(QDialog):
    """번역 참고용 TXT 단어장 캐시 관리 창."""

    def __init__(self, glossary_text="", glossary_path="", parent=None):
        super().__init__(parent)
        self.setWindowTitle("단어장")
        self.resize(760, 520)

        self.glossary_text = str(glossary_text or "")
        self.glossary_path = str(glossary_path or "")
        self.changed = False

        layout = QVBoxLayout(self)

        info = QLabel(
            "번역 참고 자료로 사용할 TXT 파일을 캐시에 저장합니다.\n"
            "배경 설명, 단어 해설, 1대1 대체 규칙 등을 넣어둘 수 있습니다."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self.status_label = QLabel()
        self.status_label.setWordWrap(True)
        layout.addWidget(self.status_label)

        self.preview = QTextEdit()
        self.preview.setReadOnly(True)
        self.preview.setPlaceholderText("아직 불러온 단어장이 없습니다.")
        layout.addWidget(self.preview, 1)

        top_buttons = QHBoxLayout()
        self.btn_load = QPushButton("불러오기")
        self.btn_refresh = QPushButton("갱신")
        self.btn_reset = QPushButton("초기화")
        top_buttons.addWidget(self.btn_load)
        top_buttons.addWidget(self.btn_refresh)
        top_buttons.addWidget(self.btn_reset)
        top_buttons.addStretch()
        layout.addLayout(top_buttons)

        bottom_buttons = QDialogButtonBox()
        bottom_buttons.addButton("닫기", QDialogButtonBox.ButtonRole.RejectRole)
        bottom_buttons.rejected.connect(self.reject)
        layout.addWidget(bottom_buttons)

        self.btn_load.clicked.connect(self.load_glossary_file)
        self.btn_refresh.clicked.connect(self.refresh_glossary_file)
        self.btn_reset.clicked.connect(self.reset_glossary)

        self.refresh_preview()

    def refresh_preview(self):
        text = self.glossary_text or ""
        path = self.glossary_path or ""
        if text:
            path_text = path if path else "캐시에만 저장됨"
            self.status_label.setText(f"현재 단어장: {path_text}\n글자 수: {len(text):,}자")
            self.preview.setPlainText(text)
        else:
            self.status_label.setText("현재 단어장: 없음")
            self.preview.clear()

    def load_glossary_file(self):
        path, _ = QFileDialog.getOpenFileName(
            self,
            "단어장 TXT 불러오기",
            self.glossary_path or "",
            "Text Files (*.txt);;All Files (*)"
        )
        if not path:
            return
        try:
            text = read_text_file_for_cache(path)
        except Exception as e:
            QMessageBox.critical(self, "불러오기 실패", f"TXT 파일을 읽지 못했습니다:\n{e}")
            return
        self.glossary_path = path
        self.glossary_text = text
        self.changed = True
        self.refresh_preview()
        QMessageBox.information(self, "불러오기 완료", "단어장을 캐시에 반영했습니다. 닫기를 누르면 유지됩니다.")

    def refresh_glossary_file(self):
        if not self.glossary_path:
            QMessageBox.information(self, "갱신할 파일 없음", "먼저 불러오기로 TXT 파일을 선택해주세요.")
            return
        if not os.path.exists(self.glossary_path):
            QMessageBox.warning(self, "파일 없음", "기존 TXT 파일 경로를 찾을 수 없습니다. 다시 불러오기를 해주세요.")
            return
        try:
            text = read_text_file_for_cache(self.glossary_path)
        except Exception as e:
            QMessageBox.critical(self, "갱신 실패", f"TXT 파일을 다시 읽지 못했습니다:\n{e}")
            return
        self.glossary_text = text
        self.changed = True
        self.refresh_preview()
        QMessageBox.information(self, "갱신 완료", "기존 TXT 파일 내용으로 단어장 캐시를 갱신했습니다.")

    def reset_glossary(self):
        ans = QMessageBox.question(
            self,
            "단어장 초기화",
            "저장된 단어장 캐시를 지울까요?",
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


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("역식붕이 툴 v1.4")
        self.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))
        self.resize(1600, 950)

        self.api_settings = ApiSettingsStore.load()
        apply_settings_to_config(self.api_settings)
        self.engine = None
        self.restart_engine(show_error=False)

        self.paths = []
        self.idx = 0
        self.data = {}

        self.project_store = ProjectStore()
        self.project_dir = None
        self.is_loading_project = False
        self.is_autosaving = False

        self.app_options = load_app_options()
        self.sync_translation_option_cache_to_config()

        # 저장본/작업 캐시 분리
        # auto_save_enabled=True  : 변경 즉시 실제 project.json에 저장
        # auto_save_enabled=False : 변경은 작업 캐시에만 저장하고, 프로젝트 저장 버튼으로만 확정
        self.auto_save_enabled = bool(self.app_options.get("auto_save_enabled", False))
        self.analysis_number_box_width = int(self.app_options.get("analysis_number_box_width", 40) or 40)
        self.work_project_store = None
        self.work_project_dir = None
        self.has_unsaved_changes = False
        self._closing_confirmed = False

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

        # 번역 묶음 수: 한 번의 API 요청에 몇 줄을 묶어 보낼지
        # OpenAI / DeepSeek를 각각 따로 기억한다.
        self.trans_chunk_sizes = {
            "openai": 20,
            "deepseek": 8,
        }

        self.default_text_color = "#000000"
        self.default_stroke_color = "#FFFFFF"
        self.default_line_spacing = 0
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
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_delayed_tooltip)
        self._tooltip_target = None
        self._tooltip_html = ""

        # 최종화면 텍스트 작업용 실행 취소 스택
        self.page_text_undo_stacks = {}

        self.setup_actions()
        self.setup_ui()
        self.load_text_preset_cache()
        self.load_item_text_preset_cache()
        self.setup_menu()
        self.apply_dark_theme()
        self.apply_shortcuts()

    # =========================================================
    # 메뉴 / UI
    # =========================================================
    def setup_actions(self):
        def make_action(key, text, slot):
            action = QAction(text, self)
            action.triggered.connect(slot)
            self.actions[key] = action
            self.addAction(action)
            return action

        # 프로젝트
        make_action("project_new", "새 프로젝트 만들기", self.new_project_from_images)
        make_action("project_open", "프로젝트 열기", self.open_project)
        make_action("project_save", "프로젝트 저장", self.save_project)
        make_action("project_save_as", "다른 이름으로 저장", self.save_project_as)

        # 개별 작업
        make_action("work_tab_cycle", "작업탭 변경", self.cycle_work_tab)
        make_action("work_page_prev", "이전 페이지", self.prev)
        make_action("work_page_next", "다음 페이지", self.next)
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
        make_action("batch_export", "일괄 출력", lambda: self.run_batch('export'))

        # 옵션
        self.act_auto_save_mode = make_action("option_auto_save_mode", "자동저장 모드", self.toggle_auto_save_mode)
        self.act_auto_save_mode.setCheckable(True)
        self.act_auto_save_mode.setChecked(self.auto_save_enabled)
        make_action("option_api_settings", "API 관리", self.open_api_settings_dialog)
        make_action("option_translation_prompt", "번역 프롬프트 입력", self.open_translation_prompt_dialog)
        make_action("option_glossary", "단어장", self.open_glossary_dialog)
        make_action("option_shortcut_settings", "단축키 통합 관리", self.open_shortcut_settings_dialog)
        make_action("option_macro_settings", "매크로 관리", self.open_macro_settings_dialog)
        make_action("option_text_preset_settings", "페이지 글꼴 프리셋 관리", self.open_text_preset_dialog)
        make_action("option_item_text_preset_settings", "개별 글꼴 프리셋 관리", self.open_item_text_preset_dialog)

        # 토글/보조 작업
        make_action("paint_magic_fill", "마스킹 칠하기", self.fill_magic_wand_mask)
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
            action.triggered.connect(lambda checked=False, n=name: self.apply_item_text_preset_by_name(n))
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

        # 요술봉/재분석은 마스크 탭 전용.
        for attr in ("act_magic", "act_reanal"):
            if hasattr(self, attr):
                getattr(self, attr).setVisible(mask_tabs)

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

    def _tooltip_rich_text(self, title, shortcut_text="", description=""):
        title = str(title or "")
        shortcut_text = str(shortcut_text or "").strip()
        description = str(description or "").strip()
        base = 'background-color:#fff8d6; color:#000000; white-space:nowrap; padding:2px 8px;'
        rows = [f'<div style="color:#000000;"><b>{title}</b></div>']
        if shortcut_text:
            rows.append(f'<div style="margin-top:2px;color:#333333;">{shortcut_text}</div>')
        if description:
            rows.append(f'<div style="margin-top:4px;color:#333333; border-top:1px solid #c9bd7a; padding-top:3px;">{description}</div>')
        return f'<div style="{base}">' + ''.join(rows) + '</div>'

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

        widget.setProperty("delayed_tooltip_html", self._tooltip_rich_text(title, shortcut_text, description))
        widget.installEventFilter(self)

    def _show_delayed_tooltip(self):
        widget = self._tooltip_target
        html = self._tooltip_html
        if widget is None or not html:
            return
        if not widget.isVisible():
            return
        try:
            pos = widget.mapToGlobal(QPoint(widget.width() // 2, widget.height()))
        except Exception:
            pos = QCursor.pos()
        QToolTip.showText(pos, html, widget)

    def eventFilter(self, obj, event):
        et = event.type()
        if hasattr(obj, "property") and obj.property("delayed_tooltip_html"):
            # QAction/QToolButton 기본 툴팁은 action text를 작게 띄우는 경우가 있다.
            # 예: W, ☐ 같은 "아이콘 확대"처럼 보이는 검은 툴팁.
            # 지연 툴팁 하나만 쓰기 위해 기본 ToolTip 이벤트는 완전히 막는다.
            if et == QEvent.Type.ToolTip:
                return True

            if et == QEvent.Type.Enter:
                self._tooltip_target = obj
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
            if hasattr(self, "act_magic"): action_info.append((self.act_magic, "요술봉 선택", seq_text("paint_magic_select")))
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

        # 우측 상단 작업 버튼/옵션
        if hasattr(self, "sb_trans_chunk"):
            self.register_delayed_tooltip(self.sb_trans_chunk, "묶음 수", "한 번의 API 요청에 묶어서 보낼 텍스트 줄 수")
        if hasattr(self, "btn_translate"):
            self.register_delayed_tooltip(self.btn_translate, "번역", seq_text("work_translate"))
        if hasattr(self, "btn_inpaint"):
            self.register_delayed_tooltip(self.btn_inpaint, "인페인팅", seq_text("work_inpaint"))
        if hasattr(self, "btn_text_cleanup"):
            self.register_delayed_tooltip(self.btn_text_cleanup, "텍스트 정리", seq_text("work_clean_text"))
        if hasattr(self, "cb_show_final_text"):
            self.register_delayed_tooltip(self.cb_show_final_text, "텍스트 표시 ON/OFF", seq_text("view_text_toggle"))
        if hasattr(self, "btn_text_color"):
            self.register_delayed_tooltip(self.btn_text_color, "문자 색상", seq_text("item_text_color"))
        if hasattr(self, "btn_stroke_color"):
            self.register_delayed_tooltip(self.btn_stroke_color, "획 색상", seq_text("item_stroke_color"))
        if hasattr(self, "btn_align_left"):
            self.register_delayed_tooltip(self.btn_align_left, "왼쪽 정렬", seq_text("item_align_left"))
            self.register_delayed_tooltip(self.btn_align_center, "가운데 정렬", seq_text("item_align_center"))
            self.register_delayed_tooltip(self.btn_align_right, "오른쪽 정렬", seq_text("item_align_right"))

    def setup_menu(self):
        menubar = self.menuBar()

        project_menu = menubar.addMenu("프로젝트")
        project_menu.addAction(self.actions["project_new"])
        project_menu.addAction(self.actions["project_open"])
        project_menu.addAction(self.actions["project_save"])
        project_menu.addAction(self.actions["project_save_as"])

        work_menu = menubar.addMenu("작업")
        work_menu.addAction(self.actions["work_tab_cycle"])
        work_menu.addAction(self.actions["work_page_prev"])
        work_menu.addAction(self.actions["work_page_next"])
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
        work_menu.addAction(self.actions["work_export"])

        batch_menu = menubar.addMenu("일괄 작업")
        batch_menu.addAction(self.actions["batch_analyze"])
        batch_menu.addAction(self.actions["batch_translate"])
        batch_menu.addAction(self.actions["batch_inpaint"])
        batch_menu.addAction(self.actions["batch_extract_text"])
        batch_menu.addAction(self.actions["batch_import_translation"])
        batch_menu.addAction(self.actions["batch_clear_translation"])
        batch_menu.addAction(self.actions["batch_clean_text"])
        batch_menu.addAction(self.actions["batch_export"])

        auto_menu = menubar.addMenu("자동화 작업")
        auto_menu.addAction(self.actions["auto_text_size_current"])
        auto_menu.addAction(self.actions["auto_text_size_batch"])
        auto_menu.addSeparator()
        auto_menu.addAction(self.actions["auto_linebreak_current"])
        auto_menu.addAction(self.actions["auto_linebreak_batch"])

        option_menu = menubar.addMenu("옵션")

        option_menu.addAction(self.actions["option_auto_save_mode"])
        option_menu.addSeparator()
        option_menu.addAction(self.actions["option_api_settings"])
        option_menu.addAction(self.actions["option_translation_prompt"])
        option_menu.addAction(self.actions["option_glossary"])
        option_menu.addAction(self.actions["option_shortcut_settings"])
        option_menu.addAction(self.actions["option_macro_settings"])
        option_menu.addAction(self.actions["option_text_preset_settings"])
        option_menu.addAction(self.actions["option_item_text_preset_settings"])

    def setup_ui(self):
        w = QWidget()
        self.setCentralWidget(w)
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
        tb.setStyleSheet("background:#444;")
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

        self.act_magic = QAction("W", self)
        self.act_magic.triggered.connect(lambda: self.set_tool('magic_wand'))
        tb.addAction(self.act_magic)

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

        vl.addWidget(self.view)
        ll.addWidget(vc)

        cl = QHBoxLayout()
        cl.addWidget(QPushButton("◀", clicked=self.prev))
        self.btn_page = QPushButton("0 / 0")
        self.btn_page.setStyleSheet("border:none; font-weight:bold; color:#f2f2f2;")
        self.btn_page.clicked.connect(self.jump_page)
        cl.addWidget(self.btn_page)
        cl.addWidget(QPushButton("▶", clicked=self.next))

        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["1. 원본", "2. 분석도", "3. 텍스트 마스크", "4. 페인팅 마스크", "5. 최종결과"])
        self.cb_mode.currentIndexChanged.connect(self.mode_chg)
        cl.addWidget(self.cb_mode)
        self.update_paint_toolbar_visibility()

        cl.addStretch()
        cl.addWidget(QPushButton("⚡ 분석", clicked=self.anal, styleSheet="background:#f55;color:white;font-weight:bold"))
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
        self.sb_font_size = QSpinBox()
        self.sb_font_size.setRange(10, 300)
        self.sb_font_size.setValue(35)
        self.sb_font_size.setSuffix(" px")
        self.sb_font_size.setFixedWidth(82)
        self.sb_strk = QSpinBox()
        self.sb_strk.setRange(0, 100)
        self.sb_strk.setValue(3)
        self.sb_strk.setSuffix(" px")
        self.sb_strk.setFixedWidth(72)

        self.btn_text_color = QPushButton("")
        self.btn_text_color.setToolTip("문자 색상")
        self.btn_text_color.setFixedSize(28, 28)
        self.btn_stroke_color = QPushButton("")
        self.btn_stroke_color.setToolTip("획 색상")
        self.btn_stroke_color.setFixedSize(28, 28)

        self.btn_align_left = QPushButton("≡◁")
        self.btn_align_center = QPushButton("≡◇")
        self.btn_align_right = QPushButton("▷≡")
        for b in (self.btn_align_left, self.btn_align_center, self.btn_align_right):
            b.setFixedWidth(42)
            b.setMinimumHeight(26)
            b.setToolTip("글자 정렬")

        self.sb_line_spacing = QSpinBox()
        self.sb_line_spacing.setRange(0, 300)
        self.sb_line_spacing.setSpecialValueText("자동")
        self.sb_line_spacing.setValue(0)
        self.sb_line_spacing.setSuffix(" %")
        self.sb_line_spacing.setFixedWidth(72)
        self.sb_line_spacing.setToolTip("행간")

        self.sb_letter_spacing = QSpinBox()
        self.sb_letter_spacing.setRange(0, 200)
        self.sb_letter_spacing.setSpecialValueText("자동")
        self.sb_letter_spacing.setValue(0)
        self.sb_letter_spacing.setSuffix(" px")
        self.sb_letter_spacing.setFixedWidth(72)
        self.sb_letter_spacing.setToolTip("자간")

        self.sb_char_width = QSpinBox()
        self.sb_char_width.setRange(10, 300)
        self.sb_char_width.setValue(100)
        self.sb_char_width.setSuffix(" %")
        self.sb_char_width.setFixedWidth(72)
        self.sb_char_width.setToolTip("문자 너비")

        self.sb_char_height = QSpinBox()
        self.sb_char_height.setRange(10, 300)
        self.sb_char_height.setValue(100)
        self.sb_char_height.setSuffix(" %")
        self.sb_char_height.setFixedWidth(72)
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
            b.setMinimumHeight(26)
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
        self.cb_trans_provider.addItem("OpenAI", "openai")
        self.cb_trans_provider.addItem("DeepSeek", "deepseek")
        self.cb_trans_provider.addItem("Google", "google")
        self.cb_trans_provider.currentIndexChanged.connect(self.on_translation_provider_changed)

        self.sb_trans_chunk = QSpinBox()
        self.sb_trans_chunk.setRange(1, 100)
        self.sb_trans_chunk.setValue(self.trans_chunk_sizes.get("openai", 20))
        self.sb_trans_chunk.setSuffix("개")
        self.sb_trans_chunk.setStatusTip("한 번의 API 요청에 묶어서 보낼 텍스트 줄 수")
        self.sb_trans_chunk.valueChanged.connect(self.on_translation_chunk_changed)

        self.cb_show_final_text = QCheckBox("텍스트 표시")
        self.cb_show_final_text.setChecked(True)
        self.cb_show_final_text.toggled.connect(self.on_show_final_text_toggled)

        self.btn_translate = QPushButton("🌐 번역", clicked=self.trans)
        self.btn_inpaint = QPushButton("🎨 인페인팅", clicked=self.run_inpainting, styleSheet="background:#4b4;color:white")
        self.btn_text_cleanup = QPushButton("🧹 텍스트 정리", clicked=self.clean_text_current)

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
            "QTableWidget { background:#26282d; color:#f2f2f2; gridline-color:#4a4d55; }"
            "QTableWidget::item:selected { background:#fff176; color:#000000; }"
        )
        rl.addWidget(self.tab)

        self.tab.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tab.setColumnWidth(0, 46)
        self.tab.setColumnWidth(1, 28)
        self.tab.setWordWrap(True)
        self.tab.verticalHeader().setVisible(False)
        self.tab.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        rl.addWidget(QPushButton("📤 결과물 출력", clicked=self.export_result, styleSheet="background:#48f;color:white;font-weight:bold;height:40px"))
        self.log_w = QTextEdit()
        self.log_w.setMaximumHeight(100)
        self.log_w.setReadOnly(True)
        self.log_w.setStyleSheet("background:#222;color:#0f0;")
        rl.addWidget(self.log_w)
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

    def apply_dark_theme(self):
        # QToolTip은 OS/Qt 스타일에 따라 MainWindow stylesheet만으로는
        # 일부 위젯에서 검은 기본 툴팁이 남을 수 있어서 앱 전체에 한 번 더 강제한다.
        app = QApplication.instance()
        if app:
            app.setStyleSheet("""
                QToolTip {
                    background-color: #fff8d6;
                    color: #000000;
                    border: 1px solid #777777;
                    padding: 6px;
                }
            """)
            pal = app.palette()
            pal.setColor(QPalette.ColorRole.ToolTipBase, QColor("#fff8d6"))
            pal.setColor(QPalette.ColorRole.ToolTipText, QColor("#000000"))
            app.setPalette(pal)

        self.setStyleSheet("""
            QMainWindow, QWidget {
                background-color: #1f1f22;
                color: #f2f2f2;
            }
            QMenuBar {
                background-color: #232326;
                color: #f2f2f2;
            }
            QMenuBar::item {
                background: transparent;
                padding: 4px 8px;
            }
            QMenuBar::item:selected {
                background: #35353a;
            }
            QMenu {
                background-color: #2b2b30;
                color: #f2f2f2;
                border: 1px solid #4a4a52;
            }
            QMenu::item:selected {
                background-color: #3c3f46;
            }
            QLabel, QCheckBox, QRadioButton, QGroupBox {
                color: #f2f2f2;
            }
            QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QFontComboBox, QSpinBox, QDoubleSpinBox {
                background-color: #2d2f34;
                color: #f5f5f5;
                border: 1px solid #53565f;
                selection-background-color: #4b79ff;
                selection-color: #ffffff;
            }
            QAbstractItemView {
                background-color: #26282d;
                color: #f5f5f5;
                border: 1px solid #4a4d55;
                alternate-background-color: #2d3036;
                selection-background-color: #fff176;
                selection-color: #000000;
                gridline-color: #4a4d55;
            }
            QHeaderView::section {
                background-color: #31343a;
                color: #f2f2f2;
                border: 1px solid #4a4d55;
                padding: 4px;
            }
            QPushButton {
                background-color: #353841;
                color: #f2f2f2;
                border: 1px solid #5a5d66;
                padding: 4px 8px;
            }
            QPushButton:hover {
                background-color: #424652;
            }
            QPushButton:pressed {
                background-color: #2d3038;
            }
            QPushButton:disabled {
                background-color: #2a2b2f;
                color: #8b8d93;
                border-color: #44474f;
            }
            QToolBar {
                background-color: #24262b;
                border: 1px solid #3d4048;
                spacing: 4px;
            }
            QToolButton {
                background-color: #353841;
                color: #f2f2f2;
                border: 1px solid #5a5d66;
                padding: 4px;
            }
            QToolButton:hover {
                background-color: #424652;
            }
            QCheckBox::indicator {
                width: 14px;
                height: 14px;
                border: 1px solid #72757f;
                background: #2d2f34;
            }
            QCheckBox::indicator:checked {
                background: #5da9ff;
            }
            QSplitter::handle {
                background: #353841;
            }
            QToolTip {
                background-color: #fff8d6;
                color: #000000;
                border: 1px solid #777777;
                padding: 6px;
            }
        """)
        if hasattr(self, 'tb') and self.tb:
            self.tb.setStyleSheet("background:#24262b; border:1px solid #3d4048;")
        if hasattr(self, 'mask_toggle_wrap') and self.mask_toggle_wrap:
            self.mask_toggle_wrap.setStyleSheet("")
        if hasattr(self, 'btn_page') and self.btn_page:
            self.btn_page.setStyleSheet("border:none; font-weight:bold; color:#f2f2f2;")
        if hasattr(self, 'tab') and self.tab:
            self.tab.setStyleSheet(
                "QTableWidget { background:#26282d; color:#f5f5f5; gridline-color:#4a4d55; }"
                "QTableWidget::item:selected { background:#fff176; color:#000000; }"
            )
        if hasattr(self, 'log_w') and self.log_w:
            self.log_w.setStyleSheet("background:#111214;color:#75ff75;border:1px solid #3b3e46;")

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
                btn.setFixedSize(28, 28)
                btn.setStyleSheet(f"background:{color}; border:1px solid #444; padding:0px;")

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
                value = "자동" if int(value or 0) == 0 else f"{value}%"
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
            "line_spacing": _int("line_spacing", 0, 0, 300),
            "letter_spacing": _int("letter_spacing", 0, 0, 500),
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
                self.sb_line_spacing.setValue(int(style["line_spacing"]))
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
        if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
            self.apply_style_to_selected(**style)
        self.save_last_text_preset(str(key))
        self.log(f"🎛️ 글꼴 프리셋 로딩: {self.cb_text_preset.currentText()}")

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

    def apply_item_text_preset_by_name(self, name, from_combo=False):
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
            self.apply_style_to_selected(preset_name=name, **subset)
            if from_combo and hasattr(self, "cb_item_text_preset"):
                self._item_preset_signal_lock = True
                try:
                    idx = self.cb_item_text_preset.findData(name)
                    if idx >= 0:
                        self.cb_item_text_preset.setCurrentIndex(idx)
                finally:
                    self._item_preset_signal_lock = False
            self.log(f"🎛️ 개별 글꼴 프리셋 적용: {name}")
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
        dialog.setWindowTitle("페이지 글꼴 프리셋 관리")
        dialog.resize(1040, 620)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info = QLabel(f"저장 위치: {self.text_preset_dir()}")
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
        dlg_font = QFontComboBox(dialog); dlg_font.setFixedWidth(160)
        dlg_size = QSpinBox(dialog); dlg_size.setRange(5, 500); dlg_size.setSuffix(" px"); dlg_size.setFixedWidth(74)
        dlg_stroke = QSpinBox(dialog); dlg_stroke.setRange(0, 100); dlg_stroke.setSuffix(" px"); dlg_stroke.setFixedWidth(70)
        dlg_text_color_btn = QPushButton("", dialog); dlg_text_color_btn.setFixedSize(28, 28)
        dlg_stroke_color_btn = QPushButton("", dialog); dlg_stroke_color_btn.setFixedSize(28, 28)
        dlg_align_left = QPushButton("≡◁", dialog); dlg_align_center = QPushButton("≡◇", dialog); dlg_align_right = QPushButton("▷≡", dialog)
        for b in (dlg_align_left, dlg_align_center, dlg_align_right):
            b.setFixedWidth(42); b.setMinimumHeight(26)
        row1.addWidget(QLabel("폰트")); row1.addWidget(dlg_font)
        row1.addWidget(QLabel("크기")); row1.addWidget(dlg_size)
        row1.addWidget(dlg_text_color_btn)
        row1.addWidget(QLabel("획")); row1.addWidget(dlg_stroke); row1.addWidget(dlg_stroke_color_btn)
        row1.addWidget(dlg_align_left); row1.addWidget(dlg_align_center); row1.addWidget(dlg_align_right)
        row1.addStretch()
        editor_l.addLayout(row1)

        row2 = QHBoxLayout()
        row2.setSpacing(6)
        dlg_line_spacing = QSpinBox(dialog); dlg_line_spacing.setRange(0, 300); dlg_line_spacing.setSpecialValueText("자동"); dlg_line_spacing.setSuffix(" %"); dlg_line_spacing.setFixedWidth(72)
        dlg_letter_spacing = QSpinBox(dialog); dlg_letter_spacing.setRange(0, 200); dlg_letter_spacing.setSpecialValueText("자동"); dlg_letter_spacing.setSuffix(" px"); dlg_letter_spacing.setFixedWidth(72)
        dlg_char_width = QSpinBox(dialog); dlg_char_width.setRange(10, 300); dlg_char_width.setValue(100); dlg_char_width.setSuffix(" %"); dlg_char_width.setFixedWidth(72)
        dlg_char_height = QSpinBox(dialog); dlg_char_height.setRange(10, 300); dlg_char_height.setValue(100); dlg_char_height.setSuffix(" %"); dlg_char_height.setFixedWidth(72)
        dlg_bold = QPushButton("B", dialog); dlg_italic = QPushButton("I", dialog); dlg_strike = QPushButton("S", dialog)
        for b, tip in ((dlg_bold, "굵게"), (dlg_italic, "기울이기"), (dlg_strike, "취소선")):
            b.setCheckable(True); b.setFixedWidth(32); b.setMinimumHeight(26); b.setToolTip(tip)
        dlg_bold.setStyleSheet("font-weight:bold;"); dlg_italic.setStyleSheet("font-style:italic;"); dlg_strike.setStyleSheet("text-decoration: line-through;")
        row2.addWidget(QLabel("행간")); row2.addWidget(dlg_line_spacing)
        row2.addWidget(QLabel("자간")); row2.addWidget(dlg_letter_spacing)
        row2.addWidget(QLabel("너비")); row2.addWidget(dlg_char_width)
        row2.addWidget(QLabel("높이")); row2.addWidget(dlg_char_height)
        row2.addWidget(dlg_bold); row2.addWidget(dlg_italic); row2.addWidget(dlg_strike)
        row2.addStretch()
        editor_l.addLayout(row2)
        layout.addWidget(editor)

        def refresh_color_buttons():
            dlg_text_color_btn.setStyleSheet(f"background:{dialog_text_color['value']}; border:1px solid #444; padding:0px;")
            dlg_stroke_color_btn.setStyleSheet(f"background:{dialog_stroke_color['value']}; border:1px solid #444; padding:0px;")
            for align, btn in (("left", dlg_align_left), ("center", dlg_align_center), ("right", dlg_align_right)):
                btn.setStyleSheet("background:#dfefff; border:1px solid #448aff;" if dialog_align["value"] == align else "")

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
                dlg_line_spacing.setValue(int(style["line_spacing"]))
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
                summary = QLabel(self.style_summary_text(style)); summary.setWordWrap(True)
                btn_update = QPushButton("수정 저장")
                btn_delete = QPushButton("삭제")

                if not chk.isChecked():
                    row.setStyleSheet("background:#242424; color:#888888;")
                    summary.setStyleSheet("color:#888888;")
                    name_edit.setStyleSheet("color:#888888;")
                is_selected = (selected_name["value"] == name or select_name == name)
                if is_selected:
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
                        QMessageBox.warning(dialog, "이름 변경 실패", "같은 이름의 프리셋이 이미 있습니다.")
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
                    ans = QMessageBox.question(dialog, "프리셋 삭제", f"'{n}' 프리셋을 삭제할까요?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
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
        btn_add = QPushButton("현재 스타일을 새 프리셋으로 추가", dialog)
        btn_import = QPushButton("불러오기", dialog)
        btn_apply_page = QPushButton("현재 페이지에 적용", dialog)
        btn_apply_all = QPushButton("전체 페이지에 적용", dialog)
        btn_ok = QPushButton("확인", dialog)
        btn_close = QPushButton("닫기", dialog)
        btn_line.addWidget(btn_add)
        btn_line.addWidget(btn_import)
        btn_line.addStretch()
        btn_line.addWidget(btn_apply_page)
        btn_line.addWidget(btn_apply_all)
        btn_line.addWidget(btn_ok)
        btn_line.addWidget(btn_close)
        layout.addLayout(btn_line)

        def add_current_as_preset():
            name, ok = QInputDialog.getText(dialog, "페이지 프리셋 추가", "프리셋 이름:")
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            if self.text_preset_path(safe).exists():
                ans = QMessageBox.question(dialog, "덮어쓰기", f"'{safe}' 프리셋이 이미 있습니다. 덮어쓸까요?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
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
            path, _ = QFileDialog.getOpenFileName(dialog, "페이지 글꼴 프리셋 불러오기", str(self.text_preset_dir()), "JSON (*.json)")
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    raw = json.load(f)
                style = self.normalize_style_dict(raw.get("style") if isinstance(raw, dict) and "style" in raw else raw)
            except Exception as e:
                QMessageBox.warning(dialog, "불러오기 실패", f"프리셋 JSON을 읽지 못했습니다.\n{e}")
                return
            default_name = Path(path).stem
            name, ok = QInputDialog.getText(dialog, "프리셋 이름", "추가할 프리셋 이름:", text=default_name)
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
        dialog.setWindowTitle("개별 글꼴 프리셋 관리")
        dialog.resize(1120, 680)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info = QLabel(f"저장 위치: {self.item_text_preset_dir()}\n체크한 옵션만 프리셋에 포함됩니다. 이 창의 미리보기는 닫을 때 원래대로 복구됩니다.")
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
        dlg_font = QFontComboBox(dialog); dlg_font.setFixedWidth(160)
        dlg_size = QSpinBox(dialog); dlg_size.setRange(5, 500); dlg_size.setSuffix(" px"); dlg_size.setFixedWidth(74)
        dlg_stroke = QSpinBox(dialog); dlg_stroke.setRange(0, 100); dlg_stroke.setSuffix(" px"); dlg_stroke.setFixedWidth(70)
        dlg_text_color_btn = QPushButton("", dialog); dlg_text_color_btn.setFixedSize(28, 28)
        dlg_stroke_color_btn = QPushButton("", dialog); dlg_stroke_color_btn.setFixedSize(28, 28)
        dlg_align_left = QPushButton("≡◁", dialog); dlg_align_center = QPushButton("≡◇", dialog); dlg_align_right = QPushButton("▷≡", dialog)
        for b in (dlg_align_left, dlg_align_center, dlg_align_right):
            b.setFixedWidth(42); b.setMinimumHeight(26)
        row1.addWidget(QLabel("폰트")); row1.addWidget(dlg_font)
        row1.addWidget(QLabel("크기")); row1.addWidget(dlg_size)
        row1.addWidget(dlg_text_color_btn)
        row1.addWidget(QLabel("획")); row1.addWidget(dlg_stroke); row1.addWidget(dlg_stroke_color_btn)
        row1.addWidget(dlg_align_left); row1.addWidget(dlg_align_center); row1.addWidget(dlg_align_right)
        row1.addStretch()
        top_l.addLayout(row1)

        row2 = QHBoxLayout(); row2.setSpacing(6)
        dlg_line_spacing = QSpinBox(dialog); dlg_line_spacing.setRange(0, 300); dlg_line_spacing.setSpecialValueText("자동"); dlg_line_spacing.setSuffix(" %"); dlg_line_spacing.setFixedWidth(72)
        dlg_letter_spacing = QSpinBox(dialog); dlg_letter_spacing.setRange(0, 200); dlg_letter_spacing.setSpecialValueText("자동"); dlg_letter_spacing.setSuffix(" px"); dlg_letter_spacing.setFixedWidth(72)
        dlg_char_width = QSpinBox(dialog); dlg_char_width.setRange(10, 300); dlg_char_width.setValue(100); dlg_char_width.setSuffix(" %"); dlg_char_width.setFixedWidth(72)
        dlg_char_height = QSpinBox(dialog); dlg_char_height.setRange(10, 300); dlg_char_height.setValue(100); dlg_char_height.setSuffix(" %"); dlg_char_height.setFixedWidth(72)
        dlg_bold = QPushButton("B", dialog); dlg_italic = QPushButton("I", dialog); dlg_strike = QPushButton("S", dialog)
        for b, tip in ((dlg_bold, "굵게"), (dlg_italic, "기울이기"), (dlg_strike, "취소선")):
            b.setCheckable(True); b.setFixedWidth(32); b.setMinimumHeight(26); b.setToolTip(tip)
        dlg_bold.setStyleSheet("font-weight:bold;"); dlg_italic.setStyleSheet("font-style:italic;"); dlg_strike.setStyleSheet("text-decoration: line-through;")
        row2.addWidget(QLabel("행간")); row2.addWidget(dlg_line_spacing)
        row2.addWidget(QLabel("자간")); row2.addWidget(dlg_letter_spacing)
        row2.addWidget(QLabel("너비")); row2.addWidget(dlg_char_width)
        row2.addWidget(QLabel("높이")); row2.addWidget(dlg_char_height)
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
                btn.setStyleSheet("background:#dfefff; border:1px solid #448aff;" if dialog_align["value"] == align else "")

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
                dlg_line_spacing.setValue(int(st["line_spacing"]))
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
                    row.setStyleSheet("background:#242424; color:#888888;")
                    summary.setStyleSheet("color:#888888;")
                    name_edit.setStyleSheet("color:#888888;")
                    key_edit.setStyleSheet("color:#888888;")

                is_selected = (selected_name["value"] == name or select_name == name)
                if is_selected:
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

                def on_enabled(v, n=name):
                    p = self.item_text_presets.get(n)
                    if not p:
                        return
                    p["enabled"] = bool(v)
                    self.save_item_text_preset_named(n, p)
                    self.refresh_item_text_preset_combo()
                    self.apply_shortcuts()
                    self.log(f"🔘 개별 글꼴 프리셋 {'사용' if v else '미사용'}: {n}")
                    refresh_rows(selected_name["value"])

                def on_shortcut_changed(seq, n=name):
                    p = self.item_text_presets.get(n)
                    if not p:
                        return
                    p["shortcut"] = seq.toString(QKeySequence.SequenceFormat.NativeText)
                    self.save_item_text_preset_named(n, p)
                    self.apply_shortcuts()

                def on_name_finished(edit=name_edit, old_name=name):
                    new_name = self.safe_preset_name(edit.text())
                    if new_name == old_name:
                        edit.setText(old_name); return
                    if self.item_text_preset_path(new_name).exists():
                        QMessageBox.warning(dialog, "이름 변경 실패", "같은 이름의 프리셋이 이미 있습니다.")
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
                    ans = QMessageBox.question(dialog, "개별 프리셋 삭제", f"'{n}' 프리셋을 삭제할까요?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
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
                key_edit.keySequenceChanged.connect(on_shortcut_changed)
                name_edit.editingFinished.connect(on_name_finished)
                btn_update.clicked.connect(on_update)
                btn_delete.clicked.connect(on_delete)

            rows_layout.addStretch()

        # ---------- bottom buttons ----------
        btn_line = QHBoxLayout()
        btn_add = QPushButton("현재 설정을 새 개별 프리셋으로 추가", dialog)
        btn_import = QPushButton("불러오기", dialog)
        btn_ok = QPushButton("확인", dialog)
        btn_close = QPushButton("닫기", dialog)
        btn_line.addWidget(btn_add)
        btn_line.addWidget(btn_import)
        btn_line.addStretch()
        btn_line.addWidget(btn_ok)
        btn_line.addWidget(btn_close)
        layout.addLayout(btn_line)

        def add_current():
            name, ok = QInputDialog.getText(dialog, "개별 프리셋 추가", "프리셋 이름:")
            if not ok or not name.strip():
                return
            safe = self.safe_preset_name(name)
            if self.item_text_preset_path(safe).exists():
                ans = QMessageBox.question(dialog, "덮어쓰기", f"'{safe}' 프리셋이 이미 있습니다. 덮어쓸까요?", QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
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
            path, _ = QFileDialog.getOpenFileName(dialog, "개별 글꼴 프리셋 불러오기", str(self.item_text_preset_dir()), "JSON (*.json)")
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
                QMessageBox.warning(dialog, "불러오기 실패", f"프리셋 JSON을 읽지 못했습니다.\n{e}")
                return
            default_name = Path(path).stem
            name, ok = QInputDialog.getText(dialog, "프리셋 이름", "추가할 프리셋 이름:", text=default_name)
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
        self.apply_current_preset_to_data_items(targets)
        if refresh and page_idx == self.idx:
            self.ref_tab()
            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🎛️ 현재 페이지 프리셋 적용: {len(targets)}개")
        return len(targets)

    def apply_current_preset_to_all_pages(self):
        total = 0
        touched_current = False

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
            self.log(f"🎛️ 전체 페이지 프리셋 적용: {total}개")
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
        char_count = max(1, len(compact_text))
        return {
            'text': text,
            'char_count': char_count,
            'rect': [x, y, w, h],
            'cx': x + w / 2.0,
            'cy': y + h / 2.0,
            'w': w,
            'h': h,
            'area': max(1, w * h),
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

            if char_count <= 1:
                # 글자 단위로 잡힌 경우: 짧은 방향 폭이 글자 크기에 가깝다.
                score = max(cross_len * 0.95, axis_len * 0.85)
            else:
                # 단어/문장 덩어리로 잡힌 경우:
                # 긴 방향/글자수는 글자 피치, 짧은 방향은 실제 획 폭에 가깝다.
                pitch = axis_len / char_count
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
        changed = self.auto_text_size_for_page(self.idx, refresh=True)
        self.auto_save_project()
        self.log(f"🤖 자동 텍스트 크기 조정 완료: 현재 페이지 {changed}개")

    def auto_text_size_batch(self):
        if not self.paths:
            return
        if not self.confirm_batch_operation("일괄 자동 텍스트 크기 조정", f"자동 텍스트 크기 조정을 {len(self.paths)}페이지에 실행합니다."):
            self.log("↩️ 일괄 자동 텍스트 크기 조정 취소")
            return
        self.commit_current_page_ui_to_data()
        total = 0
        pages = 0
        for i in range(len(self.paths)):
            changed = self.auto_text_size_for_page(i, refresh=False)
            if changed:
                pages += 1
                total += changed
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🤖 일괄 자동 텍스트 크기 조정 완료: {pages}페이지 / {total}개")

    def auto_linebreak_current(self):
        if not self.paths:
            return
        self.commit_current_page_ui_to_data()
        changed = self.auto_linebreak_for_page(self.idx, refresh=True)
        self.auto_save_project()
        self.log(f"🤖 자동 줄 내림 완료: 현재 페이지 {changed}개")

    def auto_linebreak_batch(self):
        if not self.paths:
            return
        if not self.confirm_batch_operation("일괄 자동 줄 내림", f"자동 줄 내림을 {len(self.paths)}페이지에 실행합니다."):
            self.log("↩️ 일괄 자동 줄 내림 취소")
            return
        self.commit_current_page_ui_to_data()
        total = 0
        pages = 0
        for i in range(len(self.paths)):
            changed = self.auto_linebreak_for_page(i, refresh=False)
            if changed:
                pages += 1
                total += changed
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
        self._syncing_selection = True
        try:
            if hasattr(self, "view"):
                for item in self.view.scene.items():
                    if isinstance(item, TypesettingItem):
                        item.setSelected(item is text_item)
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
            self.log("⚠️ 삭제할 텍스트가 없습니다.")
            return False

        if ask:
            msg = f"선택한 텍스트 {len(data_items)}개를 삭제할까요?\n해당 영역의 마스크도 함께 지워집니다."
            ans = QMessageBox.question(
                self,
                "텍스트 삭제",
                msg,
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.Yes,
            )
            if ans != QMessageBox.StandardButton.Yes:
                return False

        for d in list(data_items):
            self.clear_masks_for_text_data(d)
            try:
                curr['data'].remove(d)
            except ValueError:
                pass

        # 삭제 후 우측 텍스트 행 라인넘버(ID)를 1부터 다시 정렬한다.
        self.renumber_text_items_for_current_page(curr)

        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🗑️ 텍스트 삭제 완료: {len(data_items)}개")
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
        act_delete = menu.addAction("텍스트 삭제")

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
        if enabled:
            data_item['_transform_mode'] = True
            self.log("🔷 텍스트 변형 모드 ON: 파란 테두리/핸들을 조작하세요. Alt+드래그로 이동, Ctrl+Enter 또는 배경 클릭으로 종료")
        else:
            data_item.pop('_transform_mode', None)
            self.log("🔷 텍스트 변형 모드 OFF")

        selected_id = data_item.get('id')
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
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
        by_id = {str(d.get('id')): d for d in old_data}
        new_data = [by_id[i] for i in id_order if i in by_id]
        for d in old_data:
            if d not in new_data:
                new_data.append(d)

        curr['data'] = new_data
        self.renumber_text_items_for_current_page(curr)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log("↕️ 텍스트 행 순서 변경 완료")

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

    def selected_text_items(self):
        if not hasattr(self, "view"):
            return []
        return [item for item in self.view.scene.selectedItems() if isinstance(item, TypesettingItem)]

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

        editor._closing = True

        selected_id = target.data.get('id') if target is not None else None
        pending_new = bool(target is not None and target.data.get('pending_new_text'))

        changed = False
        added_new = False
        canceled_new = False

        if commit and target is not None:
            new_text = editor.toPlainText()
            changed = (new_text != getattr(editor, 'original_text', ''))

            if pending_new and not str(new_text or '').strip():
                canceled_new = True
                changed = False
                self.log(f"↩️ 새 텍스트 입력 취소 (ID: {target.data.get('id')})")
            elif changed or pending_new:
                target.data['translated_text'] = new_text
                target.data.pop('force_show', None)
                target.data.pop('pending_new_text', None)

                # 직접 수정한 경우에는 기존 OCR 박스가 아니라 현재 편집 텍스트 자체를 기준으로
                # 텍스트 영역을 다시 잡는다.
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

        if commit and (changed or added_new) and refresh and self.cb_mode.currentIndex() == 4:
            self.ref_tab()
            self.mode_chg(4)
            if selected_id is not None and not canceled_new:
                self.reselect_text_items([selected_id])
        elif selected_id is not None and not canceled_new:
            self.reselect_text_items([selected_id])


    def on_scene_selection_changed(self):
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

    def apply_style_to_selected(self, keep_selection=True, preset_name=None, **style):
        items = self.selected_text_items()
        if not items:
            return
        selected_ids = [item.data.get('id') for item in items]
        for item in items:
            for key, value in style.items():
                item.data[key] = value
            if preset_name:
                item.data['item_text_preset_name'] = str(preset_name)
            else:
                item.data.pop('item_text_preset_name', None)
        self.auto_save_project()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            if keep_selection:
                self.reselect_text_items(selected_ids)
            self.update_item_preset_combo_for_selected_texts()

    def reselect_text_items(self, selected_ids):
        ids = set(selected_ids or [])
        if not ids:
            return
        for item in self.view.scene.items():
            if isinstance(item, TypesettingItem) and item.data.get('id') in ids:
                item.setSelected(True)

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
        if self.cb_mode.currentIndex() != 4:
            return
        active_transform = self.current_transform_data_item()
        if active_transform is not None:
            self.reselect_text_items([active_transform.get('id')])
            return
        ids = set(self.selected_table_text_ids())
        self._syncing_selection = True
        self.view.scene.blockSignals(True)
        try:
            for item in self.view.scene.items():
                if isinstance(item, TypesettingItem):
                    item.setSelected(str(item.data.get('id')) in ids)
        finally:
            self.view.scene.blockSignals(False)
            self._syncing_selection = False
        # 우측 스타일 칸은 첫 선택 항목 기준으로 맞춘다.
        self.on_scene_selection_changed()

    def on_global_text_style_changed(self, *args):
        if self._style_signal_lock:
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
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)

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
            # mode_chg의 이전 탭 자동저장이 새 토글 슬롯에 덮어쓰지 않도록 차단한다.
            old_last_mode = self.last_mode
            self.last_mode = -1
            self.mode_chg(3)
            if self.last_mode == -1:
                self.last_mode = old_last_mode
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
        items = ["원문만", "번역문만", "원문+번역문"]
        value, ok = QInputDialog.getItem(self, "지문 추출", "추출할 내용:", items, 0, False)
        return value if ok else None

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
        self.log(f"📄 지문 추출 완료: {out_path}")
        self.auto_save_project()

    def extract_text_batch(self):
        if not self.paths:
            return
        if not self.confirm_batch_operation("일괄 지문 추출", f"지문 추출 TXT를 {len(self.paths)}페이지 기준으로 생성합니다."):
            self.log("↩️ 일괄 지문 추출 취소")
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
        self.log(f"📄 일괄 지문 추출 완료: {count}개 / {txt_dir}")
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
                item['translated_text'] = trans_map[text_id]
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
        path, _ = QFileDialog.getOpenFileName(self, "번역문 TXT 불러오기", self.ensure_subdir("Txt"), "Text (*.txt)")
        if not path:
            return
        trans_map = self.parse_translation_txt(path, valid_ids)
        if not trans_map:
            QMessageBox.warning(self, "불러오기 실패", "현재 페이지 텍스트 번호와 맞는 번역문을 찾지 못했습니다.")
            return
        count = self.apply_translation_map_to_page(self.idx, trans_map)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.log(f"📥 번역문 불러오기 완료: {count}개")
        self.auto_save_project()

    def import_translation_batch(self):
        if not self.paths:
            return
        start_dir = self.ensure_subdir("Txt")
        folder = QFileDialog.getExistingDirectory(self, "일괄 번역문 TXT 폴더 선택", start_dir)
        if not folder:
            return
        if not self.confirm_batch_operation("일괄 번역문 불러오기", f"선택한 폴더의 TXT 번역문을 {len(self.paths)}페이지에 적용합니다."):
            self.log("↩️ 일괄 번역문 불러오기 취소")
            return
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
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        if total_pages == 0:
            QMessageBox.warning(
                self,
                "일괄 불러오기 실패",
                "선택한 폴더에서 원본 이미지 파일명과 같은 TXT 파일을 찾지 못했거나, 맞는 텍스트 번호를 찾지 못했습니다.\n"
                "예: sample.jpg 페이지라면 sample.txt 파일이 필요합니다.",
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

        count = 0
        for item in curr.get('data', []):
            if str(item.get('translated_text', '') or ''):
                item['translated_text'] = ''
                count += 1

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
                    page_count += 1

            if page_count:
                total_pages += 1
                total_items += page_count

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
            self.log("🧹 삭제할 체크 해제 항목이 없습니다.")
            return
        ans = QMessageBox.question(
            self,
            "텍스트 정리",
            f"체크 해제된 텍스트 {removed_count}개를 삭제하고 번호를 재정렬할까요?\n해당 텍스트 영역의 마스크도 함께 지워집니다.",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        removed = self.clean_text_for_page(self.idx)
        self.ref_tab()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log(f"🧹 텍스트 정리 완료: {removed}개 삭제 / 번호 재정렬")
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
            self.log("🧹 일괄 정리할 체크 해제 항목이 없습니다.")
            return
        ans = QMessageBox.question(
            self,
            "일괄 텍스트 정리",
            f"전체 페이지에서 체크 해제된 텍스트 {total_candidates}개를 삭제하고 번호를 재정렬할까요?\n해당 텍스트 영역의 마스크도 함께 지워집니다.",
        )
        if ans != QMessageBox.StandardButton.Yes:
            return
        total_removed = 0
        pages = 0
        for i in range(len(self.paths)):
            removed = self.clean_text_for_page(i)
            if removed:
                total_removed += removed
                pages += 1
        self.ref_tab()
        self.mode_chg(self.cb_mode.currentIndex())
        self.log(f"🧹 일괄 텍스트 정리 완료: {pages}페이지 / {total_removed}개 삭제")
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
            self.log(f"↔️ 인페인팅 마스크 해상도 보정: {mw}x{mh} → {iw}x{ih}")
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
            self.log("⚠️ 인페인팅 기준 이미지 저장 실패. 실제 원본 이미지로 진행합니다.")
        return self.paths[page_idx]

    def use_inpainted_as_source(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        if not curr.get('bg_clean'):
            QMessageBox.warning(self, "인페인팅 결과 없음", "먼저 인페인팅된 이미지가 있어야 원본으로 가져올 수 있습니다.")
            return

        img = self.bg_clean_to_np_image(curr.get('bg_clean'))
        if img is None:
            QMessageBox.warning(self, "이미지 변환 실패", "인페인팅 결과 이미지를 원본 탭에 표시할 수 없습니다.")
            return

        # 실제 원본 파일은 건드리지 않고, 프로젝트 내부 작업중 원본(working_source)에 저장한다.
        img = self.normalize_image_to_original_size(self.idx, img)
        self.set_working_source_image(curr, img)
        self.log("🔁 인페인팅 결과를 원본 탭의 작업중 기준 이미지로 가져왔습니다.")
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
        self.log("↩️ 원본 탭의 기준 이미지를 실제 원본으로 되돌렸습니다.")
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
                self.log("🔧 엔진 재시동 완료")
            return True
        except Exception as e:
            self.engine = None
            print(f"Engine Init Error: {e}")
            if show_error:
                QMessageBox.warning(
                    self,
                    "엔진 초기화 실패",
                    "API 설정이 비어 있거나 잘못되어 엔진을 시작하지 못했습니다.\n"
                    "[옵션 > API 관리]에서 키를 저장한 뒤 다시 시도해주세요.\n\n"
                    f"오류: {e}"
                )
            return False

    def ensure_engine_ready(self):
        if self.engine is not None:
            return True

        QMessageBox.warning(
            self,
            "API 설정 필요",
            "엔진이 아직 준비되지 않았습니다.\n[옵션 > API 관리]에서 키를 저장해주세요."
        )
        return False

    # =========================================================
    # 프로젝트 저장 / 불러오기
    # =========================================================
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
        store.save(self.paths, self.data, self.idx)

        # store.save()가 paths를 cache 내부 이미지 경로로 고정할 수 있으므로 이후 작업은 캐시 기준으로 돌아간다.
        self.work_project_store = store
        self.work_project_dir = cache_dir
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
        self.work_project_store.save(self.paths, self.data, self.idx)
        self.has_unsaved_changes = True

    def mark_saved_state(self):
        self.has_unsaved_changes = False

    def save_app_options_cache(self):
        self.app_options["auto_save_enabled"] = bool(self.auto_save_enabled)
        self.app_options["analysis_number_box_width"] = int(getattr(self, "analysis_number_box_width", 40))
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
            if refresh_view:
                self.reset_mode_to_original()
                self.load()
            return True
        finally:
            self.is_loading_project = False

    def commit_to_real_project_only(self):
        """작업 캐시 상태를 실제 프로젝트에 저장하되, 새 작업 캐시는 만들지 않는다."""
        if not self.project_dir or not self.paths:
            return False
        self.commit_current_page_ui_to_data()
        self.project_store.save(self.paths, self.data, self.idx)
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
        msg.setWindowTitle("저장하지 않은 작업")
        msg.setText("저장하지 않은 작업이 있습니다.")
        msg.setInformativeText("현재 프로젝트를 닫기 전에 저장할까요?")
        btn_save = msg.addButton("저장", QMessageBox.ButtonRole.AcceptRole)
        btn_discard = msg.addButton("저장 안 함", QMessageBox.ButtonRole.DestructiveRole)
        btn_cancel = msg.addButton("취소", QMessageBox.ButtonRole.RejectRole)
        msg.setDefaultButton(btn_save)
        msg.exec()

        clicked = msg.clickedButton()
        if clicked == btn_save:
            self.save_project()
            return not self.has_unsaved_changes
        if clicked == btn_discard:
            self.cleanup_work_cache()
            self.has_unsaved_changes = False
            return True
        return False

    def closeEvent(self, event):
        if self._closing_confirmed:
            event.accept()
            return

        if self.has_unsaved_changes:
            msg = QMessageBox(self)
            msg.setIcon(QMessageBox.Icon.Warning)
            msg.setWindowTitle("저장하지 않은 작업")
            msg.setText("저장하지 않은 작업이 있습니다.")
            msg.setInformativeText("종료하기 전에 프로젝트를 저장할까요?")
            btn_save = msg.addButton("저장", QMessageBox.ButtonRole.AcceptRole)
            btn_discard = msg.addButton("저장 안 함", QMessageBox.ButtonRole.DestructiveRole)
            btn_cancel = msg.addButton("취소", QMessageBox.ButtonRole.RejectRole)
            msg.setDefaultButton(btn_save)
            msg.exec()

            clicked = msg.clickedButton()
            if clicked == btn_cancel:
                event.ignore()
                return
            if clicked == btn_save:
                self.save_project()
                if self.has_unsaved_changes:
                    event.ignore()
                    return
            elif clicked == btn_discard:
                self.cleanup_work_cache()
                self.has_unsaved_changes = False
        else:
            # 정상 종료 시 남은 작업 캐시는 삭제한다.
            self.cleanup_work_cache()

        self._closing_confirmed = True
        event.accept()

    def new_project_from_images(self):
        if not self.confirm_unsaved_before_switch():
            return

        source_paths, _ = QFileDialog.getOpenFileNames(
            self,
            "프로젝트에 넣을 이미지 선택",
            "",
            "Images (*.png *.jpg *.jpeg *.webp *.bmp)"
        )
        if not source_paths:
            return

        parent_dir = QFileDialog.getExistingDirectory(self, "프로젝트를 만들 상위 폴더 선택")
        if not parent_dir:
            return

        default_name = Path(source_paths[0]).stem + "_project"
        project_name, ok = QInputDialog.getText(self, "새 프로젝트 이름", "프로젝트 폴더 이름:", text=default_name)
        if not ok or not project_name.strip():
            return

        safe_name = project_name.strip().replace("/", "_").replace("\\", "_")
        project_dir = os.path.join(parent_dir, safe_name)

        if os.path.exists(os.path.join(project_dir, PROJECT_FILENAME)):
            ans = QMessageBox.question(
                self,
                "기존 프로젝트 발견",
                f"이미 project.json이 있는 폴더입니다.\n{project_dir}\n\n덮어쓰고 새 프로젝트로 만들까요?",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        self.commit_current_page_ui_to_data()

        self.project_store = ProjectStore(project_dir)
        self.paths, self.data = self.project_store.create_from_images(project_dir, source_paths)
        self.project_dir = project_dir
        self.idx = 0
        self.is_loading_project = False
        self.log(f"📁 새 프로젝트 생성: {project_dir}")
        self.mark_saved_state()
        if not self.auto_save_enabled:
            self.start_work_cache_from_current(mark_dirty=False)
        self.reset_mode_to_original()
        self.load()

    def open_project(self):
        if not self.confirm_unsaved_before_switch():
            return

        project_dir = QFileDialog.getExistingDirectory(self, "프로젝트 폴더 선택")
        if not project_dir:
            return

        project_file = os.path.join(project_dir, PROJECT_FILENAME)
        if not os.path.exists(project_file):
            QMessageBox.warning(
                self,
                "프로젝트 없음",
                f"선택한 폴더에 {PROJECT_FILENAME}이 없어.\n새 프로젝트는 [프로젝트 > 새 프로젝트 만들기]로 생성해야 합니다."
            )
            return

        self.is_loading_project = True
        try:
            self.commit_current_page_ui_to_data()
            self.project_store = ProjectStore()
            self.paths, self.data, self.idx = self.project_store.load(project_file)
            self.project_dir = self.project_store.project_dir
            self.mark_saved_state()
            if not self.auto_save_enabled:
                self.start_work_cache_from_current(mark_dirty=False)
            self.log(f"📂 프로젝트 열림: {project_dir}")
            self.reset_mode_to_original()
            self.load()
        finally:
            self.is_loading_project = False

    def save_project(self):
        if not self.project_dir:
            self.log("⚠️ 프로젝트 폴더가 없습니다. 새 프로젝트를 먼저 만들어주세요.")
            return

        self.commit_current_page_ui_to_data()
        self.project_store.save(self.paths, self.data, self.idx)
        self.mark_saved_state()
        self.log("💾 프로젝트 저장 완료")

        # 자동저장 OFF에서는 저장본을 다시 로드한 뒤, 새 작업 캐시를 기준으로 이어간다.
        if not self.auto_save_enabled:
            self.reload_saved_project_from_disk(refresh_view=False)
            self.start_work_cache_from_current(mark_dirty=False)
            if self.cb_mode.currentIndex() >= 0:
                self.load()

    def save_project_as(self):
        if not self.paths:
            self.log("⚠️ 저장할 이미지/프로젝트가 없습니다.")
            return

        parent_dir = QFileDialog.getExistingDirectory(self, "새 프로젝트를 저장할 상위 폴더 선택")
        if not parent_dir:
            return

        default_name = Path(self.project_dir).name + "_copy" if self.project_dir else "ysik_project_copy"
        project_name, ok = QInputDialog.getText(self, "다른 이름으로 저장", "새 프로젝트 폴더 이름:", text=default_name)
        if not ok or not project_name.strip():
            return

        safe_name = project_name.strip().replace("/", "_").replace("\\", "_")
        project_dir = os.path.join(parent_dir, safe_name)

        if os.path.exists(os.path.join(project_dir, PROJECT_FILENAME)):
            ans = QMessageBox.question(
                self,
                "기존 프로젝트 발견",
                f"이미 project.json이 있는 폴더입니다.\n{project_dir}\n\n덮어쓰고 저장할까요?",
            )
            if ans != QMessageBox.StandardButton.Yes:
                return

        self.commit_current_page_ui_to_data()

        self.project_store = ProjectStore(project_dir)
        self.project_dir = project_dir
        self.project_store.save(self.paths, self.data, self.idx)
        self.mark_saved_state()
        self.log(f"💾 다른 이름으로 저장 완료: {project_dir}")
        self.reload_saved_project_from_disk(refresh_view=False)
        if not self.auto_save_enabled:
            self.start_work_cache_from_current(mark_dirty=False)
        self.load()

    def auto_save_project(self):
        if self.is_loading_project or self.is_autosaving:
            return
        if not self.project_dir:
            return
        self.is_autosaving = True
        try:
            if self.auto_save_enabled:
                self.project_store.save(self.paths, self.data, self.idx)
                self.has_unsaved_changes = False
            else:
                self.save_to_work_cache()
        finally:
            self.is_autosaving = False

    def commit_current_page_ui_to_data(self, include_mask=True):
        curr = self.data.get(self.idx)
        if not curr:
            return

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
        self.final_paint_above_text = bool(checked)
        if hasattr(self, "act_final_paint_above_text"):
            self.act_final_paint_above_text.setText("T↑" if self.final_paint_above_text else "T↓")
        state = "ON" if checked else "OFF"
        self.log(f"🎚️ 새 브러시를 텍스트 위에 그리기: {state}")

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
            'rect': [int(x - w / 2), int(y), w, h],
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
    def log(self, m):
        self.log_w.append(m)
        self.log_w.verticalScrollBar().setValue(self.log_w.verticalScrollBar().maximum())

    def get_special_shortcuts(self):
        symbol_map = {}
        for key, (_label, symbol) in TEXT_SYMBOLS.items():
            symbol_map[symbol] = self.shortcut_settings.seq("text_" + key)
        return symbol_map

    def get_linebreak_shortcut(self):
        return self.shortcut_settings.seq("text_linebreak")

    def on_translation_provider_changed(self):
        provider = self.cb_trans_provider.currentData() or "openai"
        default_value = 8 if provider == "deepseek" else (50 if provider == "google" else 20)
        value = self.trans_chunk_sizes.get(provider, default_value)

        self.sb_trans_chunk.blockSignals(True)
        try:
            self.sb_trans_chunk.setValue(int(value))
        finally:
            self.sb_trans_chunk.blockSignals(False)

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
        if not self.resolve_item_preset_conflicts_for_new_shortcut_settings(new_settings, parent=self, source_label="매크로"):
            self.log("↩️ 매크로 설정 저장 취소: 개별 글꼴 프리셋 단축키 충돌")
            return
        self.shortcut_settings = new_settings
        ShortcutSettingsStore.save(self.shortcut_settings)
        self.apply_shortcuts()
        self.log("🧩 매크로 설정 캐시 저장 완료")

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
            QMessageBox.information(self, "매크로 실행 중", "이미 실행 중인 매크로가 있습니다. 현재 매크로가 끝난 뒤 다시 실행해주세요.")
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

        self.macro_running = True
        self.macro_queue = list(actions)
        self.macro_current = None
        self.macro_waiting_key = None
        self.macro_waiting_kind = None
        self.macro_current_name = name

        self.log(f"🧩 매크로 실행: {name} / {len(self.macro_queue)}단계")
        QTimer.singleShot(0, self.run_next_macro_step)

    def run_next_macro_step(self):
        if not self.macro_running:
            return

        if not self.macro_queue:
            name = self.macro_current_name or "매크로"
            self.log(f"✅ 매크로 완료: {name}")
            self.macro_running = False
            self.macro_current = None
            self.macro_waiting_key = None
            self.macro_waiting_kind = None
            self.macro_current_name = ""
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

    def push_page_text_undo(self, reason="텍스트 작업"):
        curr = self.data.get(self.idx)
        if not curr:
            return False
        stack = self.page_text_undo_stacks.setdefault(self.idx, [])
        stack.append({
            'data': copy.deepcopy(curr.get('data', [])),
            'reason': str(reason),
        })
        if len(stack) > 50:
            stack.pop(0)
        return True

    def undo_page_text(self):
        curr = self.data.get(self.idx)
        stack = self.page_text_undo_stacks.get(self.idx) or []
        if not curr or not stack:
            return False
        snapshot = stack.pop()
        curr['data'] = copy.deepcopy(snapshot.get('data', []))
        self.auto_save_project()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.log(f"↩️ {snapshot.get('reason', '텍스트 작업')} 되돌림")
        return True

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

    def handle_general_undo(self):
        if self.cb_mode.currentIndex() == 4 and self.undo_page_text():
            return
        if getattr(self.view, 'draw_mode', None) == 'magic_wand' and getattr(self, 'magic_wand_history', None):
            self.undo_magic_wand_selection()
            return
        self.view.undo()

    def open_api_settings_dialog(self):
        dlg = ApiSettingsDialog(self.api_settings, self)
        if not dlg.exec():
            return

        self.api_settings = dlg.get_settings()
        ApiSettingsStore.save(self.api_settings)
        apply_settings_to_config(self.api_settings)
        self.sync_translation_option_cache_to_config()
        self.restart_engine(show_error=True)
        self.log("🔑 API 설정 캐시 저장 완료")

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
            self.log("⚠️ 현재 탭에 마스크 레이어가 없습니다.")
            return

        before = self.view.get_mask_np()
        if before is None:
            before = np.zeros_like(self.magic_wand_mask, dtype=np.uint8)

        if self.view.user_mask_item:
            self.view.history.append(self.view.user_mask_item.pixmap().copy())
            if len(self.view.history) > 20:
                self.view.history.pop(0)

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
        if m != 'magic_wand':
            self.clear_magic_wand_selection()

        self.update_final_paint_option_bar_visibility()

        if m == 'final_text':
            self.log("🔤 도구: 텍스트")
        elif m == 'paste_text':
            self.log("📋 도구: 텍스트 붙여넣기 위치 지정")
        elif m == 'draw':
            self.log("🖌️ 도구: 브러시")
        elif m == 'erase':
            self.log("🧼 도구: 지우개")
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

    def table_row_color(self, checked):
        return QColor("#2b2e34") if checked else QColor("#4a2b2b")

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

    def set_table_check_state(self, row, checked):
        cb = self.get_table_checkbox(row)
        if cb is not None:
            cb.blockSignals(True)
            try:
                cb.setChecked(bool(checked))
            finally:
                cb.blockSignals(False)
        item = self.tab.item(row, 1)
        if item is not None:
            item.setCheckState(Qt.CheckState.Checked if checked else Qt.CheckState.Unchecked)

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
        color = self.table_row_color(checked)
        for c in range(self.tab.columnCount()):
            cell = self.tab.item(row, c)
            if cell:
                cell.setBackground(color)
                cell.setForeground(QColor("#f2f2f2"))
        widget = self.tab.cellWidget(row, 1)
        if widget:
            widget.setStyleSheet(f"background:{color.name()};")

    def paint_all_row_header(self):
        for c in range(self.tab.columnCount()):
            cell = self.tab.item(0, c)
            if cell:
                cell.setBackground(QColor("#31343a"))
                cell.setForeground(QColor("#f2f2f2"))
        widget = self.tab.cellWidget(0, 1)
        if widget:
            widget.setStyleSheet("background:#31343a;")

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
            self.log(f"🔄 전체 체크 상태 자동 갱신: {'ON' if is_checked else 'OFF'}")
        else:
            data_index = row - 1
            if 0 <= data_index < len(curr_data['data']):
                self.log(f"🔄 체크 상태 자동 갱신: ID {curr_data['data'][data_index].get('id')} = {'ON' if is_checked else 'OFF'}")
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

                self.tab.setItem(0, 2, QTableWidgetItem("전체 선택"))
                self.tab.setItem(0, 3, QTableWidgetItem(""))

                for c in range(4):
                    item = self.tab.item(0, c)
                    if item:
                        item.setBackground(QColor("#31343a"))
                        item.setForeground(QColor("#f2f2f2"))
                        font = item.font()
                        font.setBold(True)
                        item.setFont(font)

                widget = self.tab.cellWidget(0, 1)
                if widget:
                    widget.setStyleSheet("background:#31343a;")
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

            self.tab.setItem(0, 2, QTableWidgetItem("전체 선택"))
            self.tab.setItem(0, 3, QTableWidgetItem(""))

            for c in range(4):
                item = self.tab.item(0, c)
                if item:
                    item.setBackground(QColor("#31343a"))
                    item.setForeground(QColor("#f2f2f2"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)
            widget = self.tab.cellWidget(0, 1)
            if widget:
                widget.setStyleSheet("background:#31343a;")

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

                self.tab.setItem(row, 2, QTableWidgetItem(x.get('text', '')))
                self.tab.setItem(row, 3, QTableWidgetItem(x.get('translated_text', '')))

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

        self.commit_current_page_ui_to_data()

        target_idx = self.idx
        self.w = AnalysisWorker(self.engine, self.get_inpainting_input_path(target_idx))
        self.w.log.connect(self.log)
        self.w.finished.connect(
            lambda o, d, mm, mi, page_idx=target_idx:
                self.anal_end_for_page(page_idx, o, d, mm, mi)
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

            self.w = AnalysisWorker(
                self.engine,
                self.get_inpainting_input_path(target_idx),
                m.copy(),
                existing_data
            )
            self.w.log.connect(self.log)
            self.w.finished.connect(
                lambda o, d, mm, mi, page_idx=target_idx:
                    self.anal_end_for_page(page_idx, o, d, mm, mi)
            )
            self.w.start()

        elif mode_idx == 3:
            # 페인팅 마스크는 재분석이 아니라 현재 페이지 저장만
            self.set_active_mask(curr, m, mode_idx)
            curr['mask_toggle_enabled'] = self.mask_toggle_enabled
            self.log(f"💾 {target_idx + 1}페이지 페인팅 마스크 저장됨")
            self.auto_save_project()

    def anal_end_for_page(self, page_idx, o, d, mm, mi):
        """
        분석/재분석 결과를 시작 당시의 page_idx에만 반영한다.
        self.idx를 직접 쓰면 작업 도중 페이지 이동 시 다른 페이지를 덮어쓸 수 있다.
        """
        if page_idx < 0 or page_idx >= len(self.paths):
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
            self.data[page_idx]['mask_inpaint_off'] = None

        self.log(f"✅ {page_idx + 1}페이지 분석 결과 반영 완료")

        # 현재 보고 있는 페이지가 작업 완료된 페이지일 때만 화면 갱신
        if page_idx == self.idx:
            self.ref_tab()

            if self.cb_mode.currentIndex() != 1:
                self.cb_mode.setCurrentIndex(1)
            else:
                self.mode_chg(1)

            # ON 강제 조건 1/2: 일반 분석 또는 텍스트 마스크 재분석 완료 직후에만 켠다.
            self.set_mask_toggle_safely(True)

        # ON 강제 조건 1/2: 분석 결과가 들어온 페이지는 분석 마스크 사용 상태로 저장한다.
        # 사용자가 이후 직접 OFF로 바꾸면 다시 임의로 ON시키지 않는다.
        self.data[page_idx]['mask_toggle_enabled'] = True

        self.auto_save_project()
        self.macro_mark_current_step_done("work_analyze")

    def check_translation_api_key_or_alert(self, provider=None):
        """번역 API 키가 없을 때 원문 반환으로 조용히 넘어가지 않게 UI에서 먼저 막는다."""
        provider = (provider or self.cb_trans_provider.currentData() or "openai").lower()

        if provider == "deepseek":
            if not self.engine or self.engine.deepseek_client is None:
                msg = "DeepSeek API 키가 비어있습니다.\n옵션 > API 관리에서 DeepSeek API Key를 입력해주세요."
                self.log("❌ DeepSeek API 키가 비어있습니다.")
                QMessageBox.critical(self, "API 키 없음", msg)
                return False
        elif provider == "google":
            try:
                from manga_engine import Config
                ok = bool(getattr(Config, "GOOGLE_TRANSLATE_API_KEY", "").strip())
            except Exception:
                ok = False
            if not ok:
                msg = "Google Translate API 키가 비어있습니다.\n옵션 > API 관리에서 Google Translate API Key를 입력해주세요."
                self.log("❌ Google Translate API 키가 비어있습니다.")
                QMessageBox.critical(self, "API 키 없음", msg)
                return False
        else:
            if not self.engine or self.engine.openai_client is None:
                msg = "OpenAI API 키가 비어있습니다.\n옵션 > API 관리에서 OpenAI API Key를 입력해주세요."
                self.log("❌ OpenAI API 키가 비어있습니다.")
                QMessageBox.critical(self, "API 키 없음", msg)
                return False

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
                QMessageBox.warning(self, "번역 개수 불일치", f"요청 {len(texts)}개 / 응답 {len(res)}개\n\n밀림 방지를 위해 결과 반영을 중단했습니다.")
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

        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log(f"❌ 번역 중 에러 발생: {e}")
            QMessageBox.critical(self, "번역 오류", f"에러가 발생했습니다:\n{e}")

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
        self.iw = InpaintWorker(self.engine, input_path, inpaint_data, inpaint_mask)
        self.iw.log.connect(self.log)
        self.iw.finished.connect(self.inpaint_end)
        self.iw.start()

    def inpaint_end(self, bg):
        if not bg:
            self.log("⚠️ 식질 실패: 결과물이 비어있습니다.")
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
        self.log(f"🔄 박스 클릭 토글: ID {data_item.get('id')} = {'ON' if new_state else 'OFF'}")

    def refresh_boxes_only(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        for item in list(self.view.scene.items()):
            if item.zValue() >= 20:
                self.view.scene.removeItem(item)
        self.view.draw_static_boxes(curr.get('data', []))

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

        # 번역/원문 텍스트를 수정하면 즉시 데이터와 최종 화면에 반영한다.
        if row > 0 and col in (2, 3):
            data_index = row - 1
            if 0 <= data_index < len(curr_data['data']):
                if col == 2:
                    curr_data['data'][data_index]['text'] = item.text()
                else:
                    curr_data['data'][data_index]['translated_text'] = item.text()
                if self.cb_mode.currentIndex() == 4:
                    self.mode_chg(4)
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
        if getattr(self, "inline_text_editor", None) is not None:
            self.finish_inline_text_edit(commit=True, refresh=False)

        # 이전 마스크 탭에서 벗어나기 전에 자동 반영.
        # 단, 페이지 로딩/일괄 작업 중에는 절대 화면 마스크를 저장하지 않는다.
        if (
            not self.is_page_loading
            and not self.is_batch_running
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
        self.update_paint_toolbar_visibility()

        curr = self.data.get(self.idx)
        if not curr:
            if hasattr(self, "magic_wand_bar"):
                self.magic_wand_bar.hide()
            if hasattr(self, "final_edit_bar"):
                self.final_edit_bar.hide()
            return

        if i != 4 and getattr(self.view, "draw_mode", None) == 'paste_text':
            self.set_tool(None)

        if i not in [2, 3] and getattr(self.view, "draw_mode", None) == 'magic_wand':
            self.set_tool(None)
        elif hasattr(self, "magic_wand_bar"):
            self.magic_wand_bar.setVisible(getattr(self.view, "draw_mode", None) == 'magic_wand' and i in [2, 3])
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

    def prev(self):
        if not self.paths:
            return

        self.commit_current_page_ui_to_data()
        self.auto_save_project()

        self.idx = (self.idx - 1) % len(self.paths)
        self.load()

    def next(self):
        if not self.paths:
            return

        self.commit_current_page_ui_to_data()
        self.auto_save_project()

        self.idx = (self.idx + 1) % len(self.paths)
        self.load()

    def jump_page(self):
        if not self.paths:
            return
        num, ok = QInputDialog.getInt(self, "페이지 이동", f"페이지 (1~{len(self.paths)}):", self.idx + 1, 1, len(self.paths))
        if ok:
            self.commit_current_page_ui_to_data()
            self.auto_save_project()
            self.idx = num - 1
            self.load()

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
        p = self.engine.export_project_result(curr['data'], self.paths[self.idx], export_bg, self.cb_font.currentFont().family(), self.sb_strk.value(), self.sb_font_size.value())
        result_path = os.path.join(self.get_output_root(), "Result", f"Result_{Path(self.paths[self.idx]).stem}.png")

        # 텍스트 위 페인팅 레이어는 텍스트 렌더링 이후 최종 PNG 위에 다시 합성한다.
        if curr.get('final_paint_above') and os.path.exists(result_path):
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

        return QMessageBox.question(
            self,
            title,
            f"{title}을(를) 실행할까요?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        ) == QMessageBox.StandardButton.Yes

    def run_batch(self, mode):
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

        if mode == "translate":
            if not self.check_translation_api_key_or_alert(self.cb_trans_provider.currentData()):
                return
        if not self.confirm_batch_operation(title, f"{title}을(를) {len(self.paths)}페이지에 실행합니다."):
            self.log(f"↩️ {title} 취소")
            return

        # 일괄 시작 전 현재 페이지의 UI 상태를 한 번만 확정한다.
        # 이후 일괄 중에는 화면 마스크 자동 커밋/화면 리로드를 막는다.
        self.commit_current_page_ui_to_data(include_mask=True)
        self.auto_save_project()

        self.is_batch_running = True
        self.current_batch_mode = mode

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
                curr['final_paint'] = None
                curr['final_paint_above'] = None
                if curr.get('use_inpainted_as_source'):
                    img = self.bg_clean_to_np_image(curr.get('bg_clean'))
                    if img is not None:
                        img = self.normalize_image_to_original_size(i, img)
                        self.set_working_source_image(curr, img)

        # ON 강제 조건 3: 일괄 분석으로 결과가 들어온 페이지는 분석 마스크 사용 상태로 저장한다.
        if getattr(self, "current_batch_mode", None) == "analyze":
            self.data[i]['mask_toggle_enabled'] = True

    def on_batch_finished(self, mode):
        self.is_batch_running = False

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

        self.current_batch_mode = None
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

        # 텍스트 편집 중에는 텍스트 입력 전용 단축키가 우선이다.
        fw = QApplication.focusWidget()
        if isinstance(fw, (QTextEdit, QLineEdit)):
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
            "paint_brush", "paint_erase", "paint_move",
            "paint_zoom_out", "paint_zoom_in", "paint_reanalyze", "paint_undo",
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

        if self._event_matches_shortcut(event, "work_tab_cycle"):
            self.cycle_work_tab()
            return
        if self._event_matches_shortcut(event, "work_page_prev"):
            self.prev()
            return
        if self._event_matches_shortcut(event, "work_page_next"):
            self.next()
            return

        # 최종 화면에서 텍스트를 선택한 상태일 때만 작동하는 개별 텍스트 단축키
        if self.cb_mode.currentIndex() == 4 and self.selected_text_items():
            if self._event_matches_shortcut(event, "item_font_select"):
                font, ok = QFontDialog.getFont(QFont(self.cb_font.currentFont().family()), self, "글꼴 선택")
                if ok:
                    self.apply_style_to_selected(font_family=font.family())
                return
            if self._event_matches_shortcut(event, "item_font_inc"):
                for item in self.selected_text_items():
                    item.data['font_size'] = int(item.data.get('font_size', self.sb_font_size.value()) or self.sb_font_size.value()) + 1
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
                return
            if self._event_matches_shortcut(event, "item_font_dec"):
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
                for item in self.selected_text_items():
                    item.data['stroke_width'] = int(item.data.get('stroke_width', self.sb_strk.value()) or 0) + 1
                ids = [item.data.get('id') for item in self.selected_text_items()]
                self.mode_chg(4); self.reselect_text_items(ids); self.auto_save_project()
                return
            if self._event_matches_shortcut(event, "item_stroke_dec"):
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

        super().keyPressEvent(event)


def exception_hook(exctype, value, traceback):
    import traceback as tb
    error_msg = "".join(tb.format_exception(exctype, value, traceback))
    print(error_msg)
    msg_box = QMessageBox()
    msg_box.setIcon(QMessageBox.Icon.Critical)
    msg_box.setText("치명적인 오류 발생!")
    msg_box.setInformativeText(str(value))
    msg_box.setDetailedText(error_msg)
    msg_box.exec()
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
    app.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))

    # 여기까지 오면 PyInstaller onefile 압축 해제는 끝난 상태다.
    # 부트로더 스플래시를 닫고, 이제부터는 Qt 진행바 스플래시로 앱 초기화를 보여준다.
    close_pyinstaller_boot_splash()

    splash = make_splash_screen()
    if splash is not None:
        splash.set_progress(45, "환경 준비 중...")

    if splash is not None:
        splash.set_progress(62, "인터페이스 로딩 중...")

    w = MainWindow()

    if splash is not None:
        splash.set_progress(88, "화면 구성 마무리 중...")

    w.setWindowIcon(QIcon(resource_path("ysb_icon.ico")))
    w.show()

    if splash is not None:
        splash.set_progress(100, "시작 완료")
        splash.stop()
        QApplication.processEvents()
        QTimer.singleShot(120, lambda: splash.finish(w))

    sys.exit(app.exec())
