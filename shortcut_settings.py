import json
from dataclasses import dataclass, field, asdict
from typing import Dict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QDialogButtonBox,
    QTabWidget, QWidget, QPushButton, QHBoxLayout, QMessageBox, QScrollArea,
    QCheckBox
)
from PyQt6.QtGui import QKeySequence
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import QKeySequenceEdit

from cache_utils import get_cache_file

CACHE_FILE = get_cache_file("shortcut_cache.json")

TEXT_SYMBOLS = {
    "ellipsis": ("말줄임표(…)", "…"),
    "horizontal_dash": ("가로장음(―)", "―"),
    "vertical_dash": ("세로장음(│)", "│"),
    "single_corner": ("홑낫표(「」)", "「」"),
    "double_corner": ("겹낫표(『』)", "『』"),
    "white_heart": ("하얀하트(♡)", "♡"),
    "black_heart": ("검은하트(♥)", "♥"),
    "music_note": ("음표(♪)", "♪"),
    "black_circle": ("검은 동그라미(●)", "●"),
    "middle_dot": ("가운뎃점(·)", "·"),
}

DEFAULT_SHORTCUTS = {
    # 1. 그림판 옵션
    "paint_move": "M",
    "paint_brush": "B",
    "paint_erase": "E",
    "paint_zoom_in": "]",
    "paint_zoom_out": "[",
    "paint_reanalyze": "F5",
    "paint_undo": "Ctrl+Z",
    "paint_magic_select": "Ctrl+D",
    "paint_magic_expand": "Ctrl+Shift+D",
    "paint_magic_tolerance_inc": "Ctrl+'",
    "paint_magic_tolerance_dec": "Ctrl+;",
    "paint_magic_expand_inc": "Ctrl+Shift+'",
    "paint_magic_expand_dec": "Ctrl+Shift+;",
    "paint_magic_fill": "Alt+D",
    "paint_mask_toggle": "Ctrl+M",

    # 2. 텍스트 입력 옵션
    # 사용자가 'Shift'라고 적어준 항목은 실제 입력 충돌 방지를 위해 Shift+Enter로 처리
    "text_linebreak": "Shift+Return",
    "text_ellipsis": "Ctrl+Q",
    "text_horizontal_dash": "Ctrl+W",
    "text_vertical_dash": "Ctrl+E",
    "text_single_corner": "Ctrl+R",
    "text_double_corner": "Ctrl+T",
    "text_white_heart": "Ctrl+Y",
    "text_black_heart": "Ctrl+U",
    "text_music_note": "Ctrl+I",
    "text_black_circle": "Ctrl+O",
    "text_middle_dot": "Ctrl+P",

    # 3. 프로젝트 옵션
    "project_new": "Ctrl+N",
    "project_open": "Ctrl+O",
    "project_save": "Ctrl+S",
    "project_save_as": "Ctrl+Shift+S",

    # 4. 작업 옵션
    "work_tab_cycle": "Tab",
    "work_page_prev": "Alt+Left",
    "work_page_next": "Alt+Right",
    "work_analyze": "Ctrl+F5",
    "work_translate": "Ctrl+F6",
    "work_inpaint": "Ctrl+F7",
    "work_inpaint_source": "Ctrl+Shift+T",
    "work_restore_original_source": "Ctrl+Shift+R",
    "work_refresh_text": "Ctrl+F8",
    "work_extract_text": "Ctrl+L",
    "work_import_translation": "Ctrl+B",
    "work_clear_translation": "Ctrl+/",
    "work_clean_text": "Ctrl+Y",
    "work_export": "Ctrl+E",
    "view_text_toggle": "Ctrl+T",

    # 5. 일괄 작업 옵션
    "batch_analyze": "Ctrl+Shift+F5",
    "batch_translate": "Ctrl+Shift+F6",
    "batch_inpaint": "Ctrl+Shift+F7",
    "batch_refresh_text": "Ctrl+Shift+F8",
    "batch_extract_text": "Ctrl+Shift+L",
    "batch_import_translation": "Ctrl+Shift+B",
    "batch_clear_translation": "Ctrl+Shift+/",
    "batch_clean_text": "Ctrl+Shift+Y",
    "batch_export": "Ctrl+Shift+E",

    # 6. 개별 텍스트 작업 옵션
    "item_font_select": "F1",
    "item_font_inc": "=",
    "item_font_dec": "-",
    "item_align_left": "F2",
    "item_align_center": "F3",
    "item_align_right": "F4",
    "item_stroke_inc": "Ctrl+=",
    "item_stroke_dec": "Ctrl+-",
    "item_text_color": "F6",
    "item_stroke_color": "F7",
}

GROUPS = [
    ("그림판 옵션", [
        ("paint_move", "이동"),
        ("paint_brush", "브러시"),
        ("paint_erase", "지우개"),
        ("paint_zoom_in", "확대"),
        ("paint_zoom_out", "축소"),
        ("paint_reanalyze", "재분석"),
        ("paint_undo", "작업 취소"),
        ("paint_magic_select", "요술봉 선택"),
        ("paint_magic_expand", "요술봉 영역 확장"),
        ("paint_magic_tolerance_inc", "요술봉 허용범위 증가"),
        ("paint_magic_tolerance_dec", "요술봉 허용범위 감소"),
        ("paint_magic_expand_inc", "요술봉 확장범위 증가"),
        ("paint_magic_expand_dec", "요술봉 확장범위 감소"),
        ("paint_magic_fill", "마스킹 칠하기"),
        ("paint_mask_toggle", "페인팅 마스크 ON/OFF"),
    ]),
    ("텍스트 입력 옵션", [
        ("text_linebreak", "줄내림"),
        ("text_ellipsis", "말줄임표(…)"),
        ("text_horizontal_dash", "가로장음(―)"),
        ("text_vertical_dash", "세로장음(│)"),
        ("text_single_corner", "홑낫표(「」)"),
        ("text_double_corner", "겹낫표(『』)"),
        ("text_white_heart", "하얀하트(♡)"),
        ("text_black_heart", "검은하트(♥)"),
        ("text_music_note", "음표(♪)"),
        ("text_black_circle", "검은 동그라미(●)"),
        ("text_middle_dot", "가운뎃점(·)"),
    ]),
    ("프로젝트 옵션", [
        ("project_new", "새 프로젝트"),
        ("project_open", "프로젝트 열기"),
        ("project_save", "프로젝트 저장"),
        ("project_save_as", "다른 이름으로 저장"),
    ]),
    ("작업 옵션", [
        ("work_tab_cycle", "작업탭 변경"),
        ("work_page_prev", "이전 페이지"),
        ("work_page_next", "다음 페이지"),
        ("work_analyze", "개별 분석"),
        ("work_translate", "개별 번역"),
        ("work_inpaint", "개별 인페인팅"),
        ("work_inpaint_source", "인페인팅을 원본으로"),
        ("work_restore_original_source", "원본으로 돌아가기"),
        ("work_refresh_text", "텍스트 강제 갱신"),
        ("work_extract_text", "개별 지문 추출"),
        ("work_import_translation", "개별 번역문 불러오기"),
        ("work_clear_translation", "번역문 내용 지우기"),
        ("work_clean_text", "개별 텍스트 정리"),
        ("work_export", "개별 출력"),
        ("view_text_toggle", "텍스트 표시 ON/OFF"),
    ]),
    ("일괄 작업 옵션", [
        ("batch_analyze", "일괄 분석"),
        ("batch_translate", "일괄 번역"),
        ("batch_inpaint", "일괄 인페인팅"),
        ("batch_refresh_text", "일괄 텍스트 갱신"),
        ("batch_extract_text", "일괄 지문 추출"),
        ("batch_import_translation", "일괄 번역문 불러오기"),
        ("batch_clear_translation", "일괄 번역문 내용 지우기"),
        ("batch_clean_text", "일괄 텍스트 정리"),
        ("batch_export", "일괄 출력"),
    ]),
    ("개별 텍스트 작업 옵션", [
        ("item_font_select", "글꼴 선택"),
        ("item_font_inc", "글꼴 확대"),
        ("item_font_dec", "글꼴 축소"),
        ("item_align_left", "왼쪽 정렬"),
        ("item_align_center", "가운데 정렬"),
        ("item_align_right", "오른쪽 정렬"),
        ("item_stroke_inc", "획 확대"),
        ("item_stroke_dec", "획 축소"),
        ("item_text_color", "문자 색상 팔레트"),
        ("item_stroke_color", "획 색상 팔레트"),
    ]),
]



@dataclass
class ShortcutSettings:
    shortcuts: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))
    enabled: Dict[str, bool] = field(default_factory=lambda: {k: True for k in DEFAULT_SHORTCUTS})

    def is_enabled(self, key: str) -> bool:
        return bool(self.enabled.get(key, True))

    def seq(self, key: str) -> QKeySequence:
        if not self.is_enabled(key):
            return QKeySequence("")
        return QKeySequence(self.shortcuts.get(key, DEFAULT_SHORTCUTS.get(key, "")))

    def set_seq(self, key: str, seq: QKeySequence):
        self.shortcuts[key] = seq.toString(QKeySequence.SequenceFormat.PortableText)

    def set_enabled(self, key: str, value: bool):
        self.enabled[key] = bool(value)


class ShortcutSettingsStore:
    @staticmethod
    def load() -> ShortcutSettings:
        if not CACHE_FILE.exists():
            return ShortcutSettings()
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)

            merged_shortcuts = dict(DEFAULT_SHORTCUTS)
            merged_enabled = {k: True for k in DEFAULT_SHORTCUTS}

            if isinstance(data, dict):
                raw_shortcuts = data.get("shortcuts", data)
                raw_enabled = data.get("enabled", {})

                if isinstance(raw_shortcuts, dict):
                    merged_shortcuts.update({
                        k: str(v)
                        for k, v in raw_shortcuts.items()
                        if k in merged_shortcuts
                    })

                if isinstance(raw_enabled, dict):
                    merged_enabled.update({
                        k: bool(v)
                        for k, v in raw_enabled.items()
                        if k in merged_enabled
                    })

            # 기존 캐시에 남아 있는 + 계열 단축키는 새 기준인 = 계열로 자동 보정한다.
            if merged_shortcuts.get("item_font_inc") == "+":
                merged_shortcuts["item_font_inc"] = "="
            if merged_shortcuts.get("item_stroke_inc") == "Ctrl++":
                merged_shortcuts["item_stroke_inc"] = "Ctrl+="

            # 비활성화된 단축키는 입력칸/동작에서 빠진 상태로 유지한다.
            for key in list(merged_shortcuts.keys()):
                if not merged_enabled.get(key, True):
                    merged_shortcuts[key] = ""

            return ShortcutSettings(merged_shortcuts, merged_enabled)
        except Exception:
            return ShortcutSettings()

    @staticmethod
    def save(settings: ShortcutSettings):
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)

    @staticmethod
    def cache_path() -> str:
        return str(CACHE_FILE)


class ShortcutSettingsDialog(QDialog):
    def __init__(self, settings: ShortcutSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("단축키 통합 관리")
        self.resize(760, 760)
        self.setStyleSheet("""
            QDialog, QWidget {
                background-color: #1f1f22;
                color: #f2f2f2;
            }
            QLabel {
                color: #f2f2f2;
            }
            QTabWidget::pane {
                border: 1px solid #5a5d66;
                background: #1f1f22;
                top: -1px;
            }
            QTabBar::tab {
                background: #2d3038;
                color: #f2f2f2;
                border: 1px solid #5a5d66;
                border-bottom: none;
                padding: 7px 14px;
                min-width: 100px;
            }
            QTabBar::tab:selected {
                background: #3d414d;
                color: #ffffff;
                font-weight: bold;
            }
            QTabBar::tab:!selected {
                background: #25272d;
                color: #bfc3cc;
            }
            QTabBar::tab:hover {
                background: #464b58;
                color: #ffffff;
            }
            QScrollArea {
                background: #1f1f22;
                border: 1px solid #5a5d66;
            }
            QKeySequenceEdit {
                background-color: #2d2f34;
                color: #f5f5f5;
                border: 1px solid #53565f;
                padding: 3px;
            }
            QCheckBox {
                color: #f2f2f2;
                spacing: 6px;
            }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border: 1px solid #72757f;
                background: #2d2f34;
            }
            QCheckBox::indicator:checked {
                background: #5da9ff;
            }
            QPushButton {
                background-color: #353841;
                color: #f2f2f2;
                border: 1px solid #5a5d66;
                padding: 5px 10px;
            }
            QPushButton:hover {
                background-color: #424652;
            }
        """)

        self.settings = ShortcutSettings(
            dict(settings.shortcuts),
            {k: bool(settings.enabled.get(k, True)) for k in DEFAULT_SHORTCUTS},
        )
        self.edits = {}
        self.checks = {}
        self.labels = {}
        self.last_sequences = {}
        self.disabled_backup = {}
        self._handling_change = False

        layout = QVBoxLayout(self)
        info = QLabel(
            "단축키는 프로그램 폴더의 캐시 파일에 저장됩니다.\n"
            "같은 단축키를 지정하면 기존 항목과 서로 교체됩니다.\n"
            "체크를 끄면 해당 단축키는 사용하지 않으며 입력칸이 비워집니다.\n"
            "캐시 위치: " + ShortcutSettingsStore.cache_path()
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        tabs = QTabWidget()
        layout.addWidget(tabs)

        for title, rows in GROUPS:
            page = QWidget()
            page_layout = QVBoxLayout(page)
            scroll = QScrollArea()
            scroll.setWidgetResizable(True)
            inner = QWidget()
            grid = QGridLayout(inner)
            grid.setColumnStretch(2, 1)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)

            for r, (key, label) in enumerate(rows):
                chk = QCheckBox()
                chk.setChecked(self.settings.is_enabled(key))
                grid.addWidget(chk, r, 0)

                label_w = QLabel(label)
                grid.addWidget(label_w, r, 1)

                edit = QKeySequenceEdit()
                edit.setKeySequence(self.settings.seq(key))
                grid.addWidget(edit, r, 2)

                self.checks[key] = chk
                self.labels[key] = label_w
                self.edits[key] = edit
                self.last_sequences[key] = edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)

                chk.toggled.connect(lambda checked, k=key: self.on_enabled_toggled(k, checked))
                edit.editingFinished.connect(lambda k=key: self.on_editing_finished(k))

                self.apply_enabled_state(key, chk.isChecked())

            scroll.setWidget(inner)
            page_layout.addWidget(scroll)
            tabs.addTab(page, title)

        btn_line = QHBoxLayout()
        reset_btn = QPushButton("기본값 복구")
        reset_btn.clicked.connect(self.reset_defaults)
        btn_line.addWidget(reset_btn)
        btn_line.addStretch()
        layout.addLayout(btn_line)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def sequence_text(self, edit: QKeySequenceEdit) -> str:
        return edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)

    def apply_enabled_state(self, key: str, enabled: bool):
        edit = self.edits[key]
        label = self.labels.get(key)

        edit.setEnabled(enabled)
        if label:
            label.setEnabled(enabled)

        if enabled:
            edit.setStyleSheet("")
        else:
            edit.setStyleSheet(
                "QKeySequenceEdit {"
                "background:#4a2f2f;"
                "color:#bdbdbd;"
                "border:1px solid #8a5555;"
                "}"
            )

    def on_enabled_toggled(self, key: str, checked: bool):
        if self._handling_change:
            return

        edit = self.edits[key]
        self._handling_change = True
        try:
            if checked:
                restore = self.disabled_backup.get(key) or DEFAULT_SHORTCUTS.get(key, "")
                edit.setKeySequence(QKeySequence(restore))
                self.last_sequences[key] = edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
            else:
                current = self.sequence_text(edit)
                if current:
                    self.disabled_backup[key] = current
                edit.clear()
                self.last_sequences[key] = ""
        finally:
            self._handling_change = False

        self.apply_enabled_state(key, checked)

        if checked:
            self.swap_if_conflict(key)

    def swap_if_conflict(self, key: str, notify=True):
        if self._handling_change:
            return

        if not self.checks[key].isChecked():
            return

        edit = self.edits[key]
        new_text = self.sequence_text(edit)
        old_text = self.last_sequences.get(key, "")

        if not new_text:
            self.last_sequences[key] = ""
            return

        if new_text == old_text:
            return

        other_key = None
        for k, other_edit in self.edits.items():
            if k == key:
                continue
            if not self.checks[k].isChecked():
                continue
            if self.sequence_text(other_edit) == new_text:
                other_key = k
                break

        self._handling_change = True
        try:
            if other_key:
                other_edit = self.edits[other_key]
                # 기본 동작은 중복 경고가 아니라 서로 교체.
                if old_text:
                    other_edit.setKeySequence(QKeySequence(old_text))
                else:
                    other_edit.clear()
                self.last_sequences[other_key] = old_text

            self.last_sequences[key] = new_text
        finally:
            self._handling_change = False

        if other_key and notify:
            new_label = self.labels.get(key).text() if self.labels.get(key) else key
            old_label = self.labels.get(other_key).text() if self.labels.get(other_key) else other_key
            old_text_display = old_text if old_text else "비어 있음"
            QMessageBox.information(
                self,
                "단축키 교체",
                f"이미 사용 중인 단축키라 서로 교체했습니다.\n\n"
                f"{new_label}: {new_text}\n"
                f"{old_label}: {old_text_display}"
            )

    def on_editing_finished(self, key: str):
        self.swap_if_conflict(key, notify=True)

    def reset_defaults(self):
        if QMessageBox.question(self, "기본값 복구", "단축키를 전부 기본값으로 돌릴까요?") != QMessageBox.StandardButton.Yes:
            return

        self._handling_change = True
        try:
            self.disabled_backup.clear()
            for key, value in DEFAULT_SHORTCUTS.items():
                if key in self.checks:
                    self.checks[key].setChecked(True)
                if key in self.edits:
                    self.edits[key].setKeySequence(QKeySequence(value))
                    self.last_sequences[key] = self.edits[key].keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                    self.apply_enabled_state(key, True)
        finally:
            self._handling_change = False

    def accept(self):
        for key, edit in self.edits.items():
            enabled = self.checks[key].isChecked()
            self.settings.set_enabled(key, enabled)
            if enabled:
                self.settings.set_seq(key, edit.keySequence())
            else:
                self.settings.shortcuts[key] = ""
        super().accept()

    def get_settings(self) -> ShortcutSettings:
        return self.settings
