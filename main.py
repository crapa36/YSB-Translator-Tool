import sys
import os
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
from shortcut_settings import ShortcutSettingsStore, ShortcutSettingsDialog, TEXT_SYMBOLS
from viewer import MuleImageViewer
from graphics_items import TypesettingItem
from delegates import MultilineDelegate
from workers import UniversalBatchWorker, AnalysisWorker, InpaintWorker
from cache_utils import get_cache_dir


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("역식붕이 툴")
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

        # 일괄 작업/페이지 로딩 중에는 화면에 남아 있는 마스크를
        # 현재 페이지 데이터에 자동 저장하면 안 된다.
        self.is_batch_running = False
        self.is_page_loading = False
        self.current_batch_mode = None

        self.last_mode = 0

        # 번역 묶음 수: 한 번의 API 요청에 몇 줄을 묶어 보낼지
        # OpenAI / DeepSeek를 각각 따로 기억한다.
        self.trans_chunk_sizes = {
            "openai": 20,
            "deepseek": 8,
        }

        self.default_text_color = "#000000"
        self.default_stroke_color = "#FFFFFF"
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
        self._tooltip_timer = QTimer(self)
        self._tooltip_timer.setSingleShot(True)
        self._tooltip_timer.timeout.connect(self._show_delayed_tooltip)
        self._tooltip_target = None
        self._tooltip_html = ""

        self.setup_actions()
        self.setup_ui()
        self.load_text_preset_cache()
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
        make_action("work_translate", "개별 번역", self.trans)
        make_action("work_inpaint", "개별 인페인팅", self.run_inpainting)
        make_action("work_inpaint_source", "인페인팅을 원본으로", self.use_inpainted_as_source)
        make_action("work_restore_original_source", "원본으로 돌아가기", self.restore_original_source)
        make_action("work_refresh_text", "텍스트 강제 갱신", self.refresh_text_only)
        make_action("work_extract_text", "개별 지문 추출", self.extract_text_current)
        make_action("work_import_translation", "개별 번역문 불러오기", self.import_translation_current)
        make_action("work_clear_translation", "번역문 내용 지우기", self.clear_translation_current)
        make_action("work_clean_text", "개별 텍스트 정리", self.clean_text_current)
        make_action("work_export", "개별 출력", self.export_result)

        # 일괄 작업
        make_action("batch_analyze", "일괄 분석", lambda: self.run_batch('analyze'))
        make_action("batch_translate", "일괄 번역", lambda: self.run_batch('translate'))
        make_action("batch_inpaint", "일괄 인페인팅", lambda: self.run_batch('inpaint'))
        make_action("batch_refresh_text", "일괄 텍스트 갱신", lambda: self.run_batch('refresh'))
        make_action("batch_extract_text", "일괄 지문 추출", self.extract_text_batch)
        make_action("batch_import_translation", "일괄 번역문 불러오기", self.import_translation_batch)
        make_action("batch_clear_translation", "일괄 번역문 내용 지우기", self.clear_translation_batch)
        make_action("batch_clean_text", "일괄 텍스트 정리", self.clean_text_batch)
        make_action("batch_export", "일괄 출력", lambda: self.run_batch('export'))

        # 토글/보조 작업
        make_action("paint_magic_fill", "마스킹 칠하기", self.fill_magic_wand_mask)
        make_action("paint_mask_toggle", "마스크 ON/OFF", self.toggle_mask_toggle)
        make_action("view_text_toggle", "텍스트 표시 ON/OFF", self.toggle_show_final_text)

    def apply_shortcuts(self):
        for key, action in self.actions.items():
            seq = self.shortcut_settings.seq(key)
            action.setShortcut(seq)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)
        if hasattr(self, "cb_show_final_text"):
            self.configure_ui_tooltips()

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

    def _tooltip_rich_text(self, title, shortcut_text=""):
        title = str(title or "")
        shortcut_text = str(shortcut_text or "").strip()
        base = 'background-color:#fff8d6; color:#000000; white-space:nowrap; padding:2px 8px;'
        if shortcut_text:
            return (
                f'<div style="{base}">'
                f'<div style="color:#000000;"><b>{title}</b></div>'
                f'<div style="margin-top:2px;color:#333333;">{shortcut_text}</div>'
                f'</div>'
            )
        return f'<div style="{base}"><b>{title}</b></div>'

    def register_delayed_tooltip(self, widget, title, shortcut_text=""):
        if widget is None:
            return
        widget.setToolTip("")
        widget.setProperty("delayed_tooltip_html", self._tooltip_rich_text(title, shortcut_text))
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
            for act, title, sk in action_info:
                try:
                    self.register_delayed_tooltip(self.tb.widgetForAction(act), title, sk)
                except Exception:
                    pass

        if hasattr(self, "mask_toggle_wrap"):
            self.register_delayed_tooltip(self.mask_toggle_wrap, "페인팅 마스크 ON/OFF", seq_text("paint_mask_toggle"))
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
        batch_menu.addAction(self.actions["batch_refresh_text"])
        batch_menu.addAction(self.actions["batch_extract_text"])
        batch_menu.addAction(self.actions["batch_import_translation"])
        batch_menu.addAction(self.actions["batch_clear_translation"])
        batch_menu.addAction(self.actions["batch_clean_text"])
        batch_menu.addAction(self.actions["batch_export"])

        option_menu = menubar.addMenu("옵션")

        act_api_settings = QAction("API 관리", self)
        act_api_settings.triggered.connect(self.open_api_settings_dialog)
        option_menu.addAction(act_api_settings)

        act_shortcut_settings = QAction("단축키 통합 관리", self)
        act_shortcut_settings.triggered.connect(self.open_shortcut_settings_dialog)
        option_menu.addAction(act_shortcut_settings)

        act_text_preset_settings = QAction("글꼴 프리셋 관리", self)
        act_text_preset_settings.triggered.connect(self.open_text_preset_dialog)
        option_menu.addAction(act_text_preset_settings)

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
        self.act_undo.triggered.connect(self.view.undo)
        tb.addAction(self.act_undo)

        self.act_magic = QAction("W", self)
        self.act_magic.triggered.connect(lambda: self.set_tool('magic_wand'))
        tb.addAction(self.act_magic)

        self.cb_mask_toggle = QCheckBox("")
        self.cb_mask_toggle.setToolTip("페인팅 마스크 ON/OFF. ON은 분석 기반, OFF는 직접 칠한 마스크를 사용합니다.")
        self.cb_mask_toggle.setFixedSize(18, 18)
        self.cb_mask_toggle.setStyleSheet("QCheckBox { padding:0px; margin:0px; } QCheckBox::indicator { width:14px; height:14px; }")
        self.cb_mask_toggle.setChecked(False)
        self.cb_mask_toggle.toggled.connect(self.on_mask_toggle_changed)

        mask_toggle_wrap = QWidget()
        self.mask_toggle_wrap = mask_toggle_wrap
        mask_toggle_wrap.setFixedSize(34, 28)
        mask_toggle_layout = QHBoxLayout(mask_toggle_wrap)
        mask_toggle_layout.setContentsMargins(0, 0, 0, 0)
        mask_toggle_layout.setSpacing(0)
        mask_toggle_layout.addStretch()
        mask_toggle_layout.addWidget(self.cb_mask_toggle, 0, Qt.AlignmentFlag.AlignCenter)
        mask_toggle_layout.addStretch()
        tb.addWidget(mask_toggle_wrap)

        self.tb = tb
        self.tb.hide()
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

        cl.addStretch()
        cl.addWidget(QPushButton("⚡ 분석", clicked=self.anal, styleSheet="background:#f55;color:white;font-weight:bold"))
        vl.addLayout(cl)
        split.addWidget(lp)

        # Right Panel
        rp = QWidget()
        rl = QVBoxLayout(rp)
        rl.setContentsMargins(6, 6, 6, 6)
        rl.setSpacing(4)
        split.addWidget(rp)

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

        # 우측 인터페이스 2줄: 자주 쓰는 작업만 남긴 압축 배치
        # 지문 추출 / 번역문 불러오기 / 인페인팅 원본 전환은 메뉴와 단축키로만 사용한다.
        al = QHBoxLayout()
        al.setContentsMargins(0, 0, 0, 0)
        al.setSpacing(6)
        self.cb_trans_provider = QComboBox()
        self.cb_trans_provider.addItem("OpenAI", "openai")
        self.cb_trans_provider.addItem("DeepSeek", "deepseek")
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

        self.tab = QTableWidget(0, 4)
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
        if hasattr(self, 'cb_mask_toggle') and self.cb_mask_toggle:
            self.cb_mask_toggle.setStyleSheet("color:#f2f2f2; padding:2px;")
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

    def current_style_snapshot(self):
        return {
            "font_family": self.cb_font.currentFont().family(),
            "font_size": int(self.sb_font_size.value()),
            "stroke_width": int(self.sb_strk.value()),
            "text_color": str(self.default_text_color or "#000000"),
            "stroke_color": str(self.default_stroke_color or "#FFFFFF"),
            "align": str(self.default_align or "center"),
        }

    def normalize_style_dict(self, style):
        style = dict(style or {})
        return {
            "font_family": str(style.get("font_family") or style.get("font") or self.cb_font.currentFont().family()),
            "font_size": int(style.get("font_size", style.get("size", self.sb_font_size.value())) or self.sb_font_size.value()),
            "stroke_width": int(style.get("stroke_width", style.get("stroke", self.sb_strk.value())) or 0),
            "text_color": str(style.get("text_color") or "#000000"),
            "stroke_color": str(style.get("stroke_color") or "#FFFFFF"),
            "align": str(style.get("align") or "center").lower() if str(style.get("align") or "center").lower() in ("left", "center", "right") else "center",
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
            with open(self.text_preset_state_path(), "w", encoding="utf-8") as f:
                json.dump({"active": active}, f, ensure_ascii=False, indent=2)
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

            active = "__last__"
            try:
                with open(self.text_preset_state_path(), "r", encoding="utf-8") as f:
                    active = str(json.load(f).get("active") or "__last__")
            except Exception:
                pass

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

    def open_text_preset_dialog(self):
        """옵션 메뉴에서 여는 글꼴 프리셋 관리창.

        프리셋 콤보에서 선택하면 즉시 현재 스타일 컨트롤에 반영된다.
        '불러오기'는 외부 JSON 프리셋을 목록에 추가하는 기능으로만 사용한다.
        '확인'은 현재 창에 보이는 스타일을 전체 페이지 텍스트에 적용하고 닫는다.
        """
        dialog = QDialog(self)
        dialog.setWindowTitle("글꼴 프리셋 관리")
        dialog.resize(620, 240)

        layout = QVBoxLayout(dialog)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setSpacing(8)

        info = QLabel(f"저장 위치: {self.text_preset_dir()}")
        info.setWordWrap(True)
        layout.addWidget(info)

        dialog_lock = {"value": False}
        dialog_text_color = {"value": self.default_text_color or "#000000"}
        dialog_stroke_color = {"value": self.default_stroke_color or "#FFFFFF"}
        dialog_align = {"value": self.default_align or "center"}
        dialog_dirty = {"value": False}

        # 프리셋 스타일 지정 옵션: 우측 인터페이스와 같은 순서로 배치한다.
        style_line = QHBoxLayout()
        style_line.setContentsMargins(0, 0, 0, 0)
        style_line.setSpacing(6)

        dlg_font = QFontComboBox(dialog)
        dlg_font.setFixedWidth(150)
        dlg_size = QSpinBox(dialog)
        dlg_size.setRange(5, 500)
        dlg_size.setSuffix(" px")
        dlg_size.setFixedWidth(74)
        dlg_stroke = QSpinBox(dialog)
        dlg_stroke.setRange(0, 100)
        dlg_stroke.setSuffix(" px")
        dlg_stroke.setFixedWidth(70)
        dlg_text_color_btn = QPushButton("", dialog)
        dlg_text_color_btn.setToolTip("문자 색상")
        dlg_stroke_color_btn = QPushButton("", dialog)
        dlg_stroke_color_btn.setToolTip("획 색상")
        dlg_align_left = QPushButton("≡◁", dialog)
        dlg_align_center = QPushButton("≡◇", dialog)
        dlg_align_right = QPushButton("▷≡", dialog)
        for b in (dlg_text_color_btn, dlg_stroke_color_btn):
            b.setFixedSize(28, 28)
        for b in (dlg_align_left, dlg_align_center, dlg_align_right):
            b.setFixedWidth(42)
            b.setMinimumHeight(26)

        style_line.addWidget(QLabel("폰트"))
        style_line.addWidget(dlg_font)
        style_line.addWidget(QLabel("크기"))
        style_line.addWidget(dlg_size)
        style_line.addWidget(dlg_text_color_btn)
        style_line.addWidget(QLabel("획"))
        style_line.addWidget(dlg_stroke)
        style_line.addWidget(dlg_stroke_color_btn)
        style_line.addWidget(dlg_align_left)
        style_line.addWidget(dlg_align_center)
        style_line.addWidget(dlg_align_right)
        style_line.addStretch()
        layout.addLayout(style_line)

        preset_line = QHBoxLayout()
        preset_line.setContentsMargins(0, 0, 0, 0)
        preset_line.setSpacing(6)
        preset_combo = QComboBox(dialog)
        btn_import = QPushButton("불러오기", dialog)
        preset_line.addWidget(QLabel("프리셋"))
        preset_line.addWidget(preset_combo, 1)
        preset_line.addWidget(btn_import)
        layout.addLayout(preset_line)

        btn_line = QHBoxLayout()
        btn_line.setContentsMargins(0, 0, 0, 0)
        btn_line.setSpacing(6)
        btn_save = QPushButton("현재 스타일 저장", dialog)
        btn_ok = QPushButton("확인", dialog)
        btn_close = QPushButton("닫기", dialog)
        btn_line.addWidget(btn_save)
        btn_line.addStretch()
        btn_line.addWidget(btn_ok)
        btn_line.addWidget(btn_close)
        layout.addLayout(btn_line)

        def refresh_color_buttons():
            dlg_text_color_btn.setStyleSheet(
                f"background:{dialog_text_color['value']}; border:1px solid #444; padding:0px;"
            )
            dlg_stroke_color_btn.setStyleSheet(
                f"background:{dialog_stroke_color['value']}; border:1px solid #444; padding:0px;"
            )
            dlg_text_color_btn.setToolTip(f"문자 색상: {dialog_text_color['value']}")
            dlg_stroke_color_btn.setToolTip(f"획 색상: {dialog_stroke_color['value']}")
            for align, btn in (("left", dlg_align_left), ("center", dlg_align_center), ("right", dlg_align_right)):
                if dialog_align["value"] == align:
                    btn.setStyleSheet("background:#dfefff; border:1px solid #448aff;")
                else:
                    btn.setStyleSheet("")

        def dialog_style_snapshot():
            return self.normalize_style_dict({
                "font_family": dlg_font.currentFont().family(),
                "font_size": int(dlg_size.value()),
                "stroke_width": int(dlg_stroke.value()),
                "text_color": dialog_text_color["value"],
                "stroke_color": dialog_stroke_color["value"],
                "align": dialog_align["value"],
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
                refresh_color_buttons()
            finally:
                dialog_lock["value"] = False

        def commit_dialog_style(active_key="__last__"):
            style = dialog_style_snapshot()
            self.apply_style_to_controls(style)
            self.save_last_text_preset(str(active_key or "__last__"))
            return style

        def preview_style_on_current_page(style, active_key="__last__"):
            """프리셋 창에서 바꾼 값을 현재 페이지에 즉시 미리보기 적용한다.

            텍스트가 없는 페이지에서도 안전하게 빠져나가도록 구성한다.
            확인 버튼을 누르기 전까지는 현재 페이지에만 반영되고,
            확인 버튼에서 전체 페이지 적용이 수행된다.
            """
            style = self.normalize_style_dict(style)
            self.apply_style_to_controls(style)
            self.save_last_text_preset(str(active_key or "__last__"))

            curr = self.data.get(self.idx) if getattr(self, "paths", None) else None
            if not curr:
                return 0

            targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
            self.apply_style_dict_to_data_items(targets, style)

            if self.cb_mode.currentIndex() == 4:
                self.mode_chg(4)
            self.auto_save_project()
            return len(targets)

        def refill_combo(select_key=None):
            self.load_text_preset_cache()
            preset_combo.blockSignals(True)
            try:
                preset_combo.clear()
                preset_combo.addItem("마지막 설정", "__last__")
                for i in range(self.cb_text_preset.count()):
                    key = self.cb_text_preset.itemData(i)
                    text = self.cb_text_preset.itemText(i)
                    if key == "__last__":
                        continue
                    preset_combo.addItem(text, key)
                key = select_key if select_key is not None else (self.cb_text_preset.currentData() or "__last__")
                idx = preset_combo.findData(key)
                preset_combo.setCurrentIndex(idx if idx >= 0 else 0)
            finally:
                preset_combo.blockSignals(False)

        def preset_style_for_key(key):
            key = key or "__last__"
            if key == "__last__":
                try:
                    with open(self.last_text_preset_path(), "r", encoding="utf-8") as f:
                        return self.normalize_style_dict(json.load(f))
                except Exception:
                    return self.current_style_snapshot()
            return self.text_presets.get(str(key)) or self.current_style_snapshot()

        def on_preset_combo_changed(*args):
            key = preset_combo.currentData() or "__last__"
            style = preset_style_for_key(key)
            apply_style_to_dialog(style)
            idx = self.cb_text_preset.findData(key)
            if idx >= 0:
                self.cb_text_preset.blockSignals(True)
                try:
                    self.cb_text_preset.setCurrentIndex(idx)
                finally:
                    self.cb_text_preset.blockSignals(False)
            preview_style_on_current_page(style, str(key))
            dialog_dirty["value"] = False
            self.log(f"🎛️ 글꼴 프리셋 로딩: {preset_combo.currentText()}")

        def on_dialog_style_changed(*args):
            if dialog_lock["value"]:
                return
            refresh_color_buttons()
            # 창에서 직접 수정한 값은 '마지막 설정'으로 자동저장한다.
            dialog_dirty["value"] = True
            preview_style_on_current_page(dialog_style_snapshot(), "__last__")

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

        def save_dialog_style_named():
            name, ok = QInputDialog.getText(self, "프리셋 저장", "저장할 프리셋 이름:")
            if not ok or not name.strip():
                return
            safe = name.strip().replace("/", "_").replace("\\", "_")
            with open(self.text_preset_path(safe), "w", encoding="utf-8") as f:
                json.dump(dialog_style_snapshot(), f, ensure_ascii=False, indent=2)
            refill_combo(safe)
            idx = self.cb_text_preset.findData(safe)
            if idx >= 0:
                self.cb_text_preset.setCurrentIndex(idx)
            commit_dialog_style(safe)
            dialog_dirty["value"] = False
            self.log(f"💾 글꼴 프리셋 저장: {safe}")

        def import_preset_to_list():
            path, _ = QFileDialog.getOpenFileName(
                self,
                "글꼴 프리셋 불러오기",
                str(self.text_preset_dir()),
                "JSON (*.json)",
            )
            if not path:
                return
            try:
                with open(path, "r", encoding="utf-8-sig") as f:
                    style = self.normalize_style_dict(json.load(f))
            except Exception as e:
                QMessageBox.warning(self, "불러오기 실패", f"프리셋 JSON을 읽지 못했습니다.\n{e}")
                return
            default_name = Path(path).stem
            name, ok = QInputDialog.getText(self, "프리셋 이름", "추가할 프리셋 이름:", text=default_name)
            if not ok or not name.strip():
                return
            safe = name.strip().replace("/", "_").replace("\\", "_")
            with open(self.text_preset_path(safe), "w", encoding="utf-8") as f:
                json.dump(style, f, ensure_ascii=False, indent=2)
            refill_combo(safe)
            apply_style_to_dialog(style)
            preview_style_on_current_page(style, safe)
            dialog_dirty["value"] = False
            self.log(f"📥 글꼴 프리셋 불러오기 완료: {safe}")

        def confirm_apply_all():
            active_key = "__last__" if dialog_dirty["value"] else (preset_combo.currentData() or "__last__")
            commit_dialog_style(active_key)
            self.apply_current_preset_to_all_pages()
            dialog.accept()

        dlg_font.currentFontChanged.connect(on_dialog_style_changed)
        dlg_size.valueChanged.connect(on_dialog_style_changed)
        dlg_stroke.valueChanged.connect(on_dialog_style_changed)
        dlg_text_color_btn.clicked.connect(lambda: pick_dialog_color("text"))
        dlg_stroke_color_btn.clicked.connect(lambda: pick_dialog_color("stroke"))
        dlg_align_left.clicked.connect(lambda: set_dialog_align("left"))
        dlg_align_center.clicked.connect(lambda: set_dialog_align("center"))
        dlg_align_right.clicked.connect(lambda: set_dialog_align("right"))
        preset_combo.currentIndexChanged.connect(on_preset_combo_changed)
        btn_import.clicked.connect(import_preset_to_list)
        btn_save.clicked.connect(save_dialog_style_named)
        btn_ok.clicked.connect(confirm_apply_all)
        btn_close.clicked.connect(dialog.reject)

        refill_combo(self.cb_text_preset.currentData())
        apply_style_to_dialog(self.current_style_snapshot())
        refresh_color_buttons()
        dialog.exec()

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
            })

    def apply_current_preset_to_data_items(self, items):
        self.apply_style_dict_to_data_items(items, self.current_style_snapshot())

    def apply_current_preset_to_page(self, page_idx, refresh=False):
        curr = self.data.get(page_idx)
        if not curr:
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
        for i in range(len(self.paths)):
            curr = self.data.get(i)
            if not curr:
                continue
            targets = [x for x in curr.get('data', []) if x.get('use_inpaint', True)]
            self.apply_current_preset_to_data_items(targets)
            total += len(targets)
        self.ref_tab()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
        self.auto_save_project()
        self.log(f"🎛️ 전체 페이지 프리셋 적용: {total}개")

    def selected_text_items(self):
        if not hasattr(self, "view"):
            return []
        return [item for item in self.view.scene.selectedItems() if isinstance(item, TypesettingItem)]

    def on_scene_selection_changed(self):
        # 개별 텍스트 스타일 작업은 우측 패널의 "선택 텍스트 스타일"에서만 한다.
        # 예전처럼 이미지 위쪽에 별도 작업바가 뜨지 않게 항상 숨긴다.
        if hasattr(self, 'final_edit_bar'):
            self.final_edit_bar.hide()

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
            self.update_color_button_styles()
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

    def apply_style_to_selected(self, keep_selection=True, **style):
        items = self.selected_text_items()
        if not items:
            return
        selected_ids = [item.data.get('id') for item in items]
        for item in items:
            for key, value in style.items():
                item.data[key] = value
        self.auto_save_project()
        if self.cb_mode.currentIndex() == 4:
            self.mode_chg(4)
            if keep_selection:
                self.reselect_text_items(selected_ids)

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
            )

    def set_global_align(self, align):
        self.default_align = align
        self.set_preset_combo_to_last()
        self.save_last_text_preset("__last__")
        selected = self.selected_text_items()
        if selected and self.cb_mode.currentIndex() == 4:
            self.apply_style_to_selected(align=align)

    def pick_color(self, target):
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

        use_inpainted_as_source=True면 curr['ori'] 자체를 인페인팅 결과로 교체해서 쓴다.
        즉 원본 파일은 보존하되, 툴 안의 '원본 탭 자리'는 인페인팅 결과가 차지한다.
        """
        curr = self.data.get(page_idx, {})

        if curr.get('use_inpainted_as_source'):
            img = curr.get('ori')
            if isinstance(img, np.ndarray):
                img = self.normalize_image_to_original_size(page_idx, img)
                curr['ori'] = img.copy() if isinstance(img, np.ndarray) else img
                return curr['ori']

            img = self.bg_clean_to_np_image(curr.get('bg_clean'))
            if img is not None:
                img = self.normalize_image_to_original_size(page_idx, img)
                curr['ori'] = img.copy()
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

        # 실제 원본 파일은 건드리지 않고, 툴 내부의 원본 이미지 자리(curr['ori'])만 교체한다.
        img = self.normalize_image_to_original_size(self.idx, img)
        curr['use_inpainted_as_source'] = True
        curr['ori'] = img.copy()
        self.log("🔁 인페인팅 결과를 원본 탭의 기준 이미지로 가져왔습니다.")
        self.auto_save_project()
        self.mode_chg(self.cb_mode.currentIndex())

    def restore_original_source(self):
        curr = self.data.get(self.idx)
        if not curr:
            return
        curr['use_inpainted_as_source'] = False
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
    def new_project_from_images(self):
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
        self.reset_mode_to_original()
        self.load()

    def open_project(self):
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
        self.log("💾 프로젝트 저장 완료")

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
        self.log(f"💾 다른 이름으로 저장 완료: {project_dir}")
        self.load()

    def auto_save_project(self):
        if self.is_loading_project or self.is_autosaving:
            return
        if not self.project_dir:
            return
        self.is_autosaving = True
        try:
            self.project_store.save(self.paths, self.data, self.idx)
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
        value = self.trans_chunk_sizes.get(provider, 8 if provider == "deepseek" else 20)

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

    def open_shortcut_settings_dialog(self):
        dlg = ShortcutSettingsDialog(self.shortcut_settings, self)
        if not dlg.exec():
            return
        self.shortcut_settings = dlg.get_settings()
        ShortcutSettingsStore.save(self.shortcut_settings)
        self.apply_shortcuts()
        self.log("⌨️ 단축키 설정 캐시 저장 완료")

    def open_api_settings_dialog(self):
        dlg = ApiSettingsDialog(self.api_settings, self)
        if not dlg.exec():
            return

        self.api_settings = dlg.get_settings()
        ApiSettingsStore.save(self.api_settings)
        apply_settings_to_config(self.api_settings)
        self.restart_engine(show_error=True)
        self.log("🔑 API 설정 캐시 저장 완료")

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
        if m == 'magic_wand' and self.cb_mode.currentIndex() not in [2, 3]:
            self.log("⚠️ 요술봉은 텍스트 마스크/페인팅 마스크 탭에서 사용하세요.")
        self.view.draw_mode = m
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag if m else QGraphicsView.DragMode.ScrollHandDrag)
        if hasattr(self, "magic_wand_bar"):
            self.magic_wand_bar.setVisible(m == 'magic_wand')
        if m != 'magic_wand':
            self.clear_magic_wand_selection()

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
        d = self.data[self.idx]['data']

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
            return

        curr = self.data[self.idx]

        img = self.bg_clean_to_np_image(bg)
        if img is not None:
            img = self.normalize_image_to_original_size(self.idx, img)
            encoded = self.encode_np_image_to_png_bytes(img)
            curr['bg_clean'] = encoded if encoded is not None else bg

            # 인페인팅을 원본으로 쓰는 상태라면, 새 결과를 다시 원본 탭의 기준 이미지로 갱신한다.
            # 이렇게 해야 1차 인페인팅 결과 위에 2차/3차 인페인팅을 계속 덧칠하는 흐름이 된다.
            if curr.get('use_inpainted_as_source'):
                curr['ori'] = img.copy()
        else:
            curr['bg_clean'] = bg

        self.auto_save_project()
        self.refresh_text_only()

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

        old_mode = self.last_mode
        keep_view_state = (old_mode == i and i == 4)
        saved_transform = self.view.transform() if keep_view_state else None
        saved_h_scroll = self.view.horizontalScrollBar().value() if keep_view_state else None
        saved_v_scroll = self.view.verticalScrollBar().value() if keep_view_state else None

        self.last_mode = i
        curr = self.data.get(self.idx)
        if not curr:
            return

        self.tb.setVisible(i in [2, 3])
        if hasattr(self, "cb_mask_toggle"):
            self.cb_mask_toggle.setVisible(i == 3)
            if i != 3:
                QToolTip.hideText()
        if i not in [2, 3] and getattr(self.view, "draw_mode", None) == 'magic_wand':
            self.set_tool(None)
        elif hasattr(self, "magic_wand_bar"):
            self.magic_wand_bar.setVisible(getattr(self.view, "draw_mode", None) == 'magic_wand' and i in [2, 3])
        self.final_edit_bar.hide()

        source_img = self.get_source_display_image(self.idx)

        if i == 0:
            self.view.set_image(source_img)
        elif i == 1:
            self.view.set_image(source_img)
            self.view.draw_static_boxes(curr['data'])
        elif i == 2:
            self.view.set_overlay(source_img, self.get_active_mask(curr, 2), QColor(255, 0, 0, 100))
            self.view.draw_static_boxes(curr['data'])
        elif i == 3:
            self.view.set_overlay(source_img, self.get_active_mask(curr, 3), QColor(0, 0, 255, 100))
            self.view.draw_static_boxes(curr['data'])
        elif i == 4:
            self.ensure_item_style_defaults_for_page(self.idx)
            self.view.set_image(curr.get('bg_clean', source_img))
            self.view.draw_movable_texts(curr['data'], self.cb_font.currentFont().family(), self.sb_font_size.value(), self.sb_strk.value(), show_text=self.cb_show_final_text.isChecked(), text_color=self.default_text_color, stroke_color=self.default_stroke_color, align=self.default_align)

            # 같은 최종 화면 안에서 텍스트만 갱신되는 경우에는
            # 사용자가 보고 있던 확대비율/스크롤 위치를 유지한다.
            if keep_view_state and saved_transform is not None:
                self.view.setTransform(saved_transform)
                if saved_h_scroll is not None:
                    self.view.horizontalScrollBar().setValue(saved_h_scroll)
                if saved_v_scroll is not None:
                    self.view.verticalScrollBar().setValue(saved_v_scroll)

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
        if not curr.get('bg_clean'):
            self.log("⚠️ 배경 없음")
            return
        self.commit_current_page_ui_to_data()
        self.ensure_item_style_defaults_for_page(self.idx)
        p = self.engine.export_project_result(curr['data'], self.paths[self.idx], curr['bg_clean'], self.cb_font.currentFont().family(), self.sb_strk.value(), self.sb_font_size.value())
        result_path = os.path.join(self.get_output_root(), "Result", f"Result_{Path(self.paths[self.idx]).stem}.png")
        self.log(f"✅ 스크립트 저장: {p}")
        self.log(f"🖼️ 최종 이미지 저장: {result_path}")
        self.auto_save_project()

    def run_batch(self, mode):
        if not self.ensure_engine_ready():
            return
        if not self.paths:
            self.log("⚠️ 파일 없음")
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
            }

        if payload:
            curr = self.data[i]
            for key, value in payload.items():
                if isinstance(value, np.ndarray):
                    curr[key] = value.copy()
                else:
                    curr[key] = value

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
        # 텍스트 편집 중에는 텍스트 입력 전용 단축키가 우선이다.
        fw = QApplication.focusWidget()
        if isinstance(fw, (QTextEdit, QLineEdit)):
            super().keyPressEvent(event)
            return

        key = event.key()
        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)

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

        if self._event_matches_shortcut(event, "paint_brush"):
            self.set_tool('draw')
            self.log("🖌️ 도구: 붓 (Draw)")
            return
        if self._event_matches_shortcut(event, "paint_erase"):
            self.set_tool('erase')
            self.log("🧼 도구: 지우개 (Erase)")
            return
        if self._event_matches_shortcut(event, "paint_move"):
            self.set_tool(None)
            self.log("✋ 도구: 이동 (Hand Grab)")
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
            if getattr(self.view, "draw_mode", None) == 'magic_wand' and getattr(self, "magic_wand_history", None):
                self.undo_magic_wand_selection()
            else:
                self.view.undo()
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
    app = QApplication(sys.argv)
    w = MainWindow()
    w.show()
    sys.exit(app.exec())
