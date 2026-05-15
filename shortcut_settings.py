import json
from dataclasses import dataclass, field, asdict
from typing import Dict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QDialogButtonBox,
    QTabWidget, QWidget, QPushButton, QHBoxLayout, QMessageBox, QScrollArea
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
    "work_refresh_text": "Ctrl+F8",
    "work_export": "Ctrl+E",

    # 5. 일괄 작업 옵션
    "batch_analyze": "Ctrl+Shift+F5",
    "batch_translate": "Ctrl+Shift+F6",
    "batch_inpaint": "Ctrl+Shift+F7",
    "batch_refresh_text": "Ctrl+Shift+F8",
    "batch_export": "Ctrl+Shift+E",
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
        ("work_inpaint", "개별 리페인팅"),
        ("work_refresh_text", "텍스트만 갱신"),
        ("work_export", "개별 출력"),
    ]),
    ("일괄 작업 옵션", [
        ("batch_analyze", "일괄 분석"),
        ("batch_translate", "일괄 번역"),
        ("batch_inpaint", "일괄 리페인팅"),
        ("batch_refresh_text", "일괄 텍스트 갱신"),
        ("batch_export", "일괄 출력"),
    ]),
]


@dataclass
class ShortcutSettings:
    shortcuts: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))

    def seq(self, key: str) -> QKeySequence:
        return QKeySequence(self.shortcuts.get(key, DEFAULT_SHORTCUTS.get(key, "")))

    def set_seq(self, key: str, seq: QKeySequence):
        self.shortcuts[key] = seq.toString(QKeySequence.SequenceFormat.PortableText)


class ShortcutSettingsStore:
    @staticmethod
    def load() -> ShortcutSettings:
        if not CACHE_FILE.exists():
            return ShortcutSettings()
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            merged = dict(DEFAULT_SHORTCUTS)
            if isinstance(data, dict):
                raw = data.get("shortcuts", data)
                if isinstance(raw, dict):
                    merged.update({k: str(v) for k, v in raw.items() if k in merged})
            return ShortcutSettings(merged)
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
        self.resize(640, 720)
        self.settings = ShortcutSettings(dict(settings.shortcuts))
        self.edits = {}

        layout = QVBoxLayout(self)
        info = QLabel(
            "단축키는 프로그램 폴더의 캐시 파일에 저장됩니다.\n"
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
            grid.setColumnStretch(1, 1)
            grid.setHorizontalSpacing(10)
            grid.setVerticalSpacing(6)

            for r, (key, label) in enumerate(rows):
                grid.addWidget(QLabel(label), r, 0)
                edit = QKeySequenceEdit()
                edit.setKeySequence(self.settings.seq(key))
                grid.addWidget(edit, r, 1)
                self.edits[key] = edit

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

    def reset_defaults(self):
        if QMessageBox.question(self, "기본값 복구", "단축키를 전부 기본값으로 돌릴까요?") != QMessageBox.StandardButton.Yes:
            return
        for key, value in DEFAULT_SHORTCUTS.items():
            if key in self.edits:
                self.edits[key].setKeySequence(QKeySequence(value))

    def accept(self):
        # 텍스트 입력 옵션은 텍스트 편집칸 한정이라 전역 단축키와 일부 중복 허용.
        # 같은 그룹 안의 완전 중복만 경고한다.
        for title, rows in GROUPS:
            seen = {}
            for key, label in rows:
                seq = self.edits[key].keySequence()
                if seq.isEmpty():
                    continue
                text = seq.toString(QKeySequence.SequenceFormat.PortableText)
                if text in seen:
                    QMessageBox.warning(self, "중복 단축키", f"[{title}] {seen[text]} 와 {label} 의 단축키가 같습니다:\n{text}")
                    return
                seen[text] = label

        for key, edit in self.edits.items():
            self.settings.set_seq(key, edit.keySequence())
        super().accept()

    def get_settings(self) -> ShortcutSettings:
        return self.settings
