import sys
import os
from pathlib import Path

import copy

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
from delegates import MultilineDelegate
from workers import UniversalBatchWorker, AnalysisWorker, InpaintWorker


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

        self.last_mode = 0

        # 번역 묶음 수: 한 번의 API 요청에 몇 줄을 묶어 보낼지
        # OpenAI / DeepSeek를 각각 따로 기억한다.
        self.trans_chunk_sizes = {
            "openai": 20,
            "deepseek": 8,
        }

        self.shortcut_settings = ShortcutSettingsStore.load()
        self.actions = {}

        self.setup_actions()
        self.setup_ui()
        self.setup_menu()
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
        make_action("work_inpaint", "개별 리페인팅", self.run_inpainting)
        make_action("work_refresh_text", "텍스트만 갱신", self.refresh_text_only)
        make_action("work_export", "개별 출력", self.export_result)

        # 일괄 작업
        make_action("batch_analyze", "일괄 분석", lambda: self.run_batch('analyze'))
        make_action("batch_translate", "일괄 번역", lambda: self.run_batch('translate'))
        make_action("batch_inpaint", "일괄 리페인팅", lambda: self.run_batch('inpaint'))
        make_action("batch_refresh_text", "일괄 텍스트 갱신", lambda: self.run_batch('refresh'))
        make_action("batch_export", "일괄 출력", lambda: self.run_batch('export'))

    def apply_shortcuts(self):
        for key, action in self.actions.items():
            seq = self.shortcut_settings.seq(key)
            action.setShortcut(seq)
            action.setShortcutContext(Qt.ShortcutContext.WindowShortcut)

    def setup_menu(self):
        menubar = self.menuBar()

        project_menu = menubar.addMenu("프로젝트")
        project_menu.addAction(self.actions["project_new"])
        project_menu.addAction(self.actions["project_open"])
        project_menu.addAction(self.actions["project_save"])
        project_menu.addAction(self.actions["project_save_as"])
        project_menu.addSeparator()

        act_temp_open = QAction("이미지 임시 열기", self)
        act_temp_open.triggered.connect(self.open_file_temp)
        project_menu.addAction(act_temp_open)

        work_menu = menubar.addMenu("작업")
        work_menu.addAction(self.actions["work_tab_cycle"])
        work_menu.addAction(self.actions["work_page_prev"])
        work_menu.addAction(self.actions["work_page_next"])
        work_menu.addSeparator()
        work_menu.addAction(self.actions["work_analyze"])
        work_menu.addAction(self.actions["work_translate"])
        work_menu.addAction(self.actions["work_inpaint"])
        work_menu.addAction(self.actions["work_refresh_text"])
        work_menu.addAction(self.actions["work_export"])

        batch_menu = menubar.addMenu("일괄 작업")
        batch_menu.addAction(self.actions["batch_analyze"])
        batch_menu.addAction(self.actions["batch_translate"])
        batch_menu.addAction(self.actions["batch_inpaint"])
        batch_menu.addAction(self.actions["batch_refresh_text"])
        batch_menu.addAction(self.actions["batch_export"])

        option_menu = menubar.addMenu("옵션")

        act_api_settings = QAction("API 관리", self)
        act_api_settings.triggered.connect(self.open_api_settings_dialog)
        option_menu.addAction(act_api_settings)

        act_shortcut_settings = QAction("단축키 통합 관리", self)
        act_shortcut_settings.triggered.connect(self.open_shortcut_settings_dialog)
        option_menu.addAction(act_shortcut_settings)

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

        tb = QToolBar(orientation=Qt.Orientation.Vertical)
        tb.setStyleSheet("background:#444;")
        tb.addAction(QAction("🖌️", self, triggered=lambda: self.set_tool('draw')))
        tb.addAction(QAction("🧼", self, triggered=lambda: self.set_tool('erase')))

        act_reanal = QAction("🔄", self)
        act_reanal.triggered.connect(self.reanalyze_mask)
        tb.addAction(act_reanal)

        act_undo = QAction("↩️", self)
        act_undo.triggered.connect(self.view.undo)
        tb.addAction(act_undo)

        self.tb = tb
        self.tb.hide()
        ll.addWidget(tb)

        vc = QWidget()
        vl = QVBoxLayout(vc)
        vl.setContentsMargins(0, 0, 0, 0)
        vl.addWidget(self.view)
        ll.addWidget(vc)

        cl = QHBoxLayout()
        cl.addWidget(QPushButton("◀", clicked=self.prev))
        self.btn_page = QPushButton("0 / 0")
        self.btn_page.setStyleSheet("border:none; font-weight:bold; color:black;")
        self.btn_page.clicked.connect(self.jump_page)
        cl.addWidget(self.btn_page)
        cl.addWidget(QPushButton("▶", clicked=self.next))

        self.cb_mode = QComboBox()
        self.cb_mode.addItems(["1. 원본", "2. 분석도", "3. 2차 마스크(영역)", "4. 1차 마스크(지우기)", "5. 최종결과"])
        self.cb_mode.currentIndexChanged.connect(self.mode_chg)
        cl.addWidget(self.cb_mode)

        cl.addStretch()
        cl.addWidget(QPushButton("⚡ 분석", clicked=self.anal, styleSheet="background:#f55;color:white;font-weight:bold"))
        vl.addLayout(cl)
        split.addWidget(lp)

        # Right Panel
        rp = QWidget()
        rl = QVBoxLayout(rp)
        split.addWidget(rp)

        gl = QHBoxLayout()
        gl.setSpacing(6)
        self.cb_font = QFontComboBox()
        self.cb_font.setMinimumWidth(220)
        self.sb_font_size = QSpinBox()
        self.sb_font_size.setRange(10, 300)
        self.sb_font_size.setValue(35)
        self.sb_font_size.setSuffix(" px")
        self.sb_strk = QSpinBox()
        self.sb_strk.setValue(3)
        self.sb_strk.setSuffix(" px")

        gl.addWidget(QLabel("폰트"))
        gl.addWidget(self.cb_font, 1)
        gl.addWidget(QLabel("크기"))
        gl.addWidget(self.sb_font_size)
        gl.addWidget(QLabel("획"))
        gl.addWidget(self.sb_strk)
        rl.addLayout(gl)

        top_action_line = QHBoxLayout()
        btn_refresh_text = QPushButton("텍스트만 갱신", clicked=self.refresh_text_only)
        top_action_line.addWidget(btn_refresh_text)
        rl.addLayout(top_action_line)

        al = QHBoxLayout()
        al.setSpacing(6)
        self.cb_trans_provider = QComboBox()
        self.cb_trans_provider.addItem("OpenAI", "openai")
        self.cb_trans_provider.addItem("DeepSeek", "deepseek")
        self.cb_trans_provider.currentIndexChanged.connect(self.on_translation_provider_changed)

        self.sb_trans_chunk = QSpinBox()
        self.sb_trans_chunk.setRange(1, 100)
        self.sb_trans_chunk.setValue(self.trans_chunk_sizes.get("openai", 20))
        self.sb_trans_chunk.setSuffix("개")
        self.sb_trans_chunk.setToolTip("한 번의 API 요청에 묶어서 보낼 텍스트 줄 수")
        self.sb_trans_chunk.valueChanged.connect(self.on_translation_chunk_changed)

        al.addWidget(QLabel("번역AI"))
        al.addWidget(self.cb_trans_provider)
        al.addWidget(QLabel("묶음"))
        al.addWidget(self.sb_trans_chunk)
        al.addWidget(QPushButton("🌐 번역", clicked=self.trans))
        al.addWidget(QPushButton("🎨 리페인팅", clicked=self.run_inpainting, styleSheet="background:#4b4;color:white"))
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
        rl.addWidget(self.tab)

        self.tab.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.tab.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Stretch)
        self.tab.setColumnWidth(0, 40)
        self.tab.setWordWrap(True)
        self.tab.verticalHeader().setSectionResizeMode(QHeaderView.ResizeMode.ResizeToContents)

        rl.addWidget(QPushButton("📤 결과물 출력", clicked=self.export_result, styleSheet="background:#48f;color:white;font-weight:bold;height:40px"))
        self.log_w = QTextEdit()
        self.log_w.setMaximumHeight(100)
        self.log_w.setReadOnly(True)
        self.log_w.setStyleSheet("background:#222;color:#0f0;")
        rl.addWidget(self.log_w)
        split.setSizes([1000, 600])

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

            check_item = self.tab.item(row, 1)
            curr['data'][data_index]['use_inpaint'] = (
                check_item is not None and check_item.checkState() == Qt.CheckState.Checked
            )

            trans_item = self.tab.item(row, 3)
            curr['data'][data_index]['translated_text'] = trans_item.text() if trans_item else ""

        # 화면 마스크 자동 저장은 평상시 현재 페이지에서만 허용.
        # 페이지 로딩/일괄 작업 중에는 이전 화면의 마스크가 다른 페이지에 섞일 수 있으므로 차단한다.
        if (not include_mask) or self.is_page_loading or self.is_batch_running:
            return

        if self.cb_mode.currentIndex() in [2, 3]:
            m = self.view.get_mask_np()
            if m is not None:
                if self.cb_mode.currentIndex() == 2:
                    curr['mask_merge'] = m.copy()
                elif self.cb_mode.currentIndex() == 3:
                    curr['mask_inpaint'] = m.copy()

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
            curr['mask_merge'] = m.copy()
            self.log("💾 2차 영역 마스크 자동 저장")
        elif mode == 3:
            curr['mask_inpaint'] = m.copy()
            self.log("💾 1차 지우기 마스크 자동 저장")
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

    def set_tool(self, m):
        self.view.draw_mode = m
        self.view.setDragMode(QGraphicsView.DragMode.NoDrag if m else QGraphicsView.DragMode.ScrollHandDrag)

    def reset_mode_to_original(self):
        """
        새 프로젝트/프로젝트 열기/임시 이미지 열기 시 이전 작업 탭 상태가 섞이지 않도록
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

    def open_file_temp(self):
        fs, _ = QFileDialog.getOpenFileNames(self, "임시 이미지 열기", "", "Images (*.png *.jpg *.jpeg *.webp *.bmp)")
        if fs:
            self.commit_current_page_ui_to_data()
            self.project_dir = None
            self.project_store = ProjectStore()
            self.paths = fs
            self.idx = 0
            self.data = {}
            self.log(f"📂 임시 이미지 {len(fs)}장 로드됨")
            self.reset_mode_to_original()
            self.load()

    # 기존 습관 호환용
    def open_file(self):
        self.open_file_temp()

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
                'bg_clean': None,
            }
        elif self.data[self.idx].get('ori') is None:
            self.data[self.idx]['ori'] = cv2.imdecode(np.fromfile(p, np.uint8), 1)

        # load() 중 mode_chg()가 실행되면 뷰어에 이전 페이지 마스크가 남아 있을 수 있다.
        # 이때 자동 저장이 끼면 다른 페이지 마스크가 덮이므로 로딩 플래그로 차단한다.
        prev_loading = self.is_page_loading
        self.is_page_loading = True
        try:
            self.ref_tab()
            self.mode_chg(self.cb_mode.currentIndex())
        finally:
            self.is_page_loading = prev_loading

    def ref_tab(self):
        d = self.data[self.idx]['data']

        self.tab.blockSignals(True)
        try:
            self.tab.setRowCount(len(d) + 1)

            self.tab.setItem(0, 0, QTableWidgetItem("ALL"))
            all_check = QTableWidgetItem()
            all_check.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
            all_checked = len(d) > 0 and all(x.get('use_inpaint', True) for x in d)
            all_check.setCheckState(Qt.CheckState.Checked if all_checked else Qt.CheckState.Unchecked)
            self.tab.setItem(0, 1, all_check)
            self.tab.setItem(0, 2, QTableWidgetItem("전체 선택"))
            self.tab.setItem(0, 3, QTableWidgetItem(""))

            for c in range(4):
                item = self.tab.item(0, c)
                if item:
                    item.setBackground(QColor("#dddddd"))
                    font = item.font()
                    font.setBold(True)
                    item.setFont(font)

            for i, x in enumerate(d):
                row = i + 1
                self.tab.setItem(row, 0, QTableWidgetItem(str(x.get('id', i + 1))))

                check_item = QTableWidgetItem()
                check_item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsUserCheckable)
                check_item.setCheckState(Qt.CheckState.Checked if x.get('use_inpaint', True) else Qt.CheckState.Unchecked)
                self.tab.setItem(row, 1, check_item)

                self.tab.setItem(row, 2, QTableWidgetItem(x.get('text', '')))
                self.tab.setItem(row, 3, QTableWidgetItem(x.get('translated_text', '')))

                row_color = QColor(Qt.GlobalColor.white) if x.get('use_inpaint', True) else QColor("#ffcccc")
                for col in range(4):
                    item = self.tab.item(row, col)
                    if item:
                        item.setBackground(row_color)
        finally:
            self.tab.blockSignals(False)

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
        self.w = AnalysisWorker(self.engine, self.paths[target_idx])
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
            # 2차 영역 마스크는 현재 페이지에만 저장
            curr['mask_merge'] = m.copy()

            # 워커에 넘길 기존 데이터는 복사본으로 넘긴다.
            # 그래야 재분석 중 기존 페이지 데이터가 직접 흔들리지 않는다.
            existing_data = copy.deepcopy(curr.get('data', []))

            self.w = AnalysisWorker(
                self.engine,
                self.paths[target_idx],
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
            # 1차 지우기 마스크는 재분석이 아니라 현재 페이지 저장만
            curr['mask_inpaint'] = m.copy()
            self.log(f"💾 {target_idx + 1}페이지 지우기 마스크 자동 저장됨")
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
                'bg_clean': None,
            }

        self.data[page_idx].update({
            'ori': o,
            'data': d,
            'mask_merge': mm,
            'mask_inpaint': mi,
        })

        self.log(f"✅ {page_idx + 1}페이지 분석 결과 반영 완료")

        # 현재 보고 있는 페이지가 작업 완료된 페이지일 때만 화면 갱신
        if page_idx == self.idx:
            self.ref_tab()

            if self.cb_mode.currentIndex() != 1:
                self.cb_mode.setCurrentIndex(1)
            else:
                self.mode_chg(1)

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
                check_item = self.tab.item(row, 1)
                is_checked = check_item is not None and check_item.checkState() == Qt.CheckState.Checked
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

    def run_inpainting(self):
        if not self.ensure_engine_ready():
            return
        curr = self.data.get(self.idx)
        if not curr:
            return
        self.commit_current_page_ui_to_data()
        self.iw = InpaintWorker(self.engine, self.paths[self.idx], curr['data'], curr['mask_inpaint'])
        self.iw.log.connect(self.log)
        self.iw.finished.connect(self.inpaint_end)
        self.iw.start()

    def inpaint_end(self, bg):
        if not bg:
            self.log("⚠️ 식질 실패: 결과물이 비어있습니다.")
            return
        self.data[self.idx]['bg_clean'] = bg
        self.auto_save_project()
        self.refresh_text_only()

    # =========================================================
    # 체크 / 박스 / 텍스트 갱신
    # =========================================================
    def paint_all_row_header(self):
        for c in range(self.tab.columnCount()):
            cell = self.tab.item(0, c)
            if cell:
                cell.setBackground(QColor("#dddddd"))

    def toggle_check_from_box(self, data_item):
        # 분석도 화면에서만 박스 클릭 토글 허용
        # 0: 원본
        # 1: 분석도
        # 2: 2차 마스크
        # 3: 1차 마스크
        # 4: 최종결과
        if self.cb_mode.currentIndex() != 1:
            return

        curr = self.data.get(self.idx)
        if not curr or 'data' not in curr:
            return

        try:
            data_index = curr['data'].index(data_item)
        except ValueError:
            return

        # 아래 기존 코드 그대로 유지

        new_state = not data_item.get('use_inpaint', True)
        data_item['use_inpaint'] = new_state
        table_row = data_index + 1

        self.tab.blockSignals(True)
        try:
            check_item = self.tab.item(table_row, 1)
            if check_item:
                check_item.setCheckState(Qt.CheckState.Checked if new_state else Qt.CheckState.Unchecked)

            row_color = QColor(Qt.GlobalColor.white) if new_state else QColor("#ffcccc")
            for c in range(self.tab.columnCount()):
                cell = self.tab.item(table_row, c)
                if cell:
                    cell.setBackground(row_color)

            all_checked = len(curr['data']) > 0 and all(x.get('use_inpaint', True) for x in curr['data'])
            all_item = self.tab.item(0, 1)
            if all_item:
                all_item.setCheckState(Qt.CheckState.Checked if all_checked else Qt.CheckState.Unchecked)
            self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)

        if self.cb_mode.currentIndex() in [1, 2, 3]:
            self.refresh_boxes_only()
        self.log(f"🔄 박스 클릭 토글: ID {data_item.get('id')} = {'ON' if new_state else 'OFF'}")
        self.auto_save_project()

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
            self.log("⚠️ 리페인팅을 먼저 해주세요.")
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
        if col != 1:
            return

        if row == 0:
            is_checked = item.checkState() == Qt.CheckState.Checked
            self.tab.blockSignals(True)
            try:
                for i, data_item in enumerate(curr_data['data']):
                    table_row = i + 1
                    data_item['use_inpaint'] = is_checked
                    check_item = self.tab.item(table_row, 1)
                    if check_item:
                        check_item.setCheckState(Qt.CheckState.Checked if is_checked else Qt.CheckState.Unchecked)
                    row_color = QColor(Qt.GlobalColor.white) if is_checked else QColor("#ffcccc")
                    for c in range(self.tab.columnCount()):
                        cell = self.tab.item(table_row, c)
                        if cell:
                            cell.setBackground(row_color)
                self.paint_all_row_header()
            finally:
                self.tab.blockSignals(False)
            if self.cb_mode.currentIndex() in [1, 2, 3]:
                self.refresh_boxes_only()
            self.log(f"🔄 전체 체크 상태 자동 갱신: {'ON' if is_checked else 'OFF'}")
            self.auto_save_project()
            return

        data_index = row - 1
        if data_index < 0 or data_index >= len(curr_data['data']):
            return
        is_checked = item.checkState() == Qt.CheckState.Checked
        curr_data['data'][data_index]['use_inpaint'] = is_checked
        row_color = QColor(Qt.GlobalColor.white) if is_checked else QColor("#ffcccc")

        self.tab.blockSignals(True)
        try:
            for c in range(self.tab.columnCount()):
                cell = self.tab.item(row, c)
                if cell:
                    cell.setBackground(row_color)
            all_checked = len(curr_data['data']) > 0 and all(x.get('use_inpaint', True) for x in curr_data['data'])
            all_item = self.tab.item(0, 1)
            if all_item:
                all_item.setCheckState(Qt.CheckState.Checked if all_checked else Qt.CheckState.Unchecked)
            self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)

        if self.cb_mode.currentIndex() in [1, 2, 3]:
            self.refresh_boxes_only()
        self.log(f"🔄 체크 상태 자동 갱신: ID {curr_data['data'][data_index].get('id')} = {'ON' if is_checked else 'OFF'}")
        self.auto_save_project()

    def upd_map(self):
        curr_data = self.data[self.idx]
        active_count = 0
        self.tab.blockSignals(True)
        try:
            for row in range(1, self.tab.rowCount()):
                data_index = row - 1
                if data_index < 0 or data_index >= len(curr_data['data']):
                    continue
                check_item = self.tab.item(row, 1)
                is_checked = check_item is not None and check_item.checkState() == Qt.CheckState.Checked
                curr_data['data'][data_index]['use_inpaint'] = is_checked
                if is_checked:
                    active_count += 1
                row_color = QColor(Qt.GlobalColor.white) if is_checked else QColor("#ffcccc")
                for c in range(self.tab.columnCount()):
                    item = self.tab.item(row, c)
                    if item:
                        item.setBackground(row_color)
            all_item = self.tab.item(0, 1)
            if all_item:
                all_item.setCheckState(Qt.CheckState.Checked if active_count == len(curr_data['data']) and len(curr_data['data']) > 0 else Qt.CheckState.Unchecked)
            self.paint_all_row_header()
        finally:
            self.tab.blockSignals(False)

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
                if self.last_mode == 2:
                    curr['mask_merge'] = m.copy()
                elif self.last_mode == 3:
                    curr['mask_inpaint'] = m.copy()
                self.auto_save_project()

        self.last_mode = i
        curr = self.data.get(self.idx)
        if not curr:
            return

        self.tb.setVisible(i in [2, 3])

        if i == 0:
            self.view.set_image(curr['ori'])
        elif i == 1:
            self.view.set_image(curr['ori'])
            self.view.draw_static_boxes(curr['data'])
        elif i == 2:
            self.view.set_overlay(curr['ori'], curr.get('mask_merge'), QColor(255, 0, 0, 100))
            self.view.draw_static_boxes(curr['data'])
        elif i == 3:
            self.view.set_overlay(curr['ori'], curr.get('mask_inpaint'), QColor(0, 0, 255, 100))
            self.view.draw_static_boxes(curr['data'])
        elif i == 4:
            self.view.set_image(curr.get('bg_clean', curr['ori']))
            self.view.draw_movable_texts(curr['data'], self.cb_font.currentFont().family(), self.sb_font_size.value(), self.sb_strk.value())

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
        p = self.engine.export_project_result(curr['data'], self.paths[self.idx], curr['bg_clean'], self.cb_font.currentFont().family(), self.sb_strk.value(), self.sb_font_size.value())
        self.log(f"✅ 저장: {p}")
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
                'bg_clean': None,
            }

        if payload:
            curr = self.data[i]
            for key, value in payload.items():
                if isinstance(value, np.ndarray):
                    curr[key] = value.copy()
                else:
                    curr[key] = value

    def on_batch_finished(self, mode):
        self.is_batch_running = False

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
            # 일괄 리페인팅 완료 후 최종결과 화면으로 이동
            if self.cb_mode.currentIndex() != 4:
                self.cb_mode.setCurrentIndex(4)
            else:
                self.mode_chg(4)

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

        if self._event_matches_shortcut(event, "work_tab_cycle"):
            self.cycle_work_tab()
            return
        if self._event_matches_shortcut(event, "work_page_prev"):
            self.prev()
            return
        if self._event_matches_shortcut(event, "work_page_next"):
            self.next()
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
