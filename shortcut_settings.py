import json
from dataclasses import dataclass, field, asdict
from typing import Dict, List

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QDialogButtonBox,
    QTabWidget, QWidget, QPushButton, QHBoxLayout, QMessageBox, QScrollArea,
    QCheckBox, QInputDialog, QLineEdit, QListWidget, QListWidgetItem,
    QAbstractItemView
)
from PyQt6.QtGui import QKeySequence
from PyQt6.QtCore import Qt, QEvent
from PyQt6.QtWidgets import QKeySequenceEdit

from cache_utils import get_cache_file

CACHE_FILE_NAME = "shortcut_cache.json"


def cache_file():
    return get_cache_file(CACHE_FILE_NAME)

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
    "final_paint_color": "C",
    "final_paint_to_background": "Alt+P",
    "final_text_tool": "T",
    "final_paint_above_toggle": "X",
    "final_paint_opacity_inc": "Alt+S",
    "final_paint_opacity_dec": "Alt+A",

    # 1-2. 글꼴 상세 옵션
    "text_line_spacing": "Ctrl+Alt+Q",
    "text_letter_spacing": "Ctrl+Alt+W",
    "text_char_width": "Ctrl+Alt+E",
    "text_char_height": "Ctrl+Alt+R",
    "text_bold_toggle": "Ctrl+Alt+T",
    "text_italic_toggle": "Ctrl+Alt+Y",
    "text_strike_toggle": "Ctrl+Alt+U",

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

    # 3-2. 옵션
    "option_auto_save_mode": "Ctrl+Alt+1",
    "option_api_settings": "Ctrl+Alt+2",
    "option_shortcut_settings": "Ctrl+Alt+3",
    "option_macro_settings": "Ctrl+Alt+4",
    "option_text_preset_settings": "Ctrl+Alt+5",
    "option_item_text_preset_settings": "Ctrl+Alt+6",
    "option_translation_prompt": "Ctrl+Alt+7",
    "option_glossary": "Ctrl+Alt+8",
    "option_workspace_location": "Ctrl+Alt+9",
    "option_register_ysb": "Ctrl+Alt+0",
    "option_unregister_ysbt": "Ctrl+Alt+Shift+0",

    # 4. 작업 옵션
    "work_tab_cycle": "Tab",
    "work_page_prev": "Alt+Left",
    "work_page_next": "Alt+Right",
    "work_analyze": "Ctrl+F5",
    "work_text_number_width": "Ctrl+Shift+W",
    "work_translate": "Ctrl+F6",
    "work_inpaint": "Ctrl+F7",
    "work_inpaint_source": "Ctrl+Shift+T",
    "work_restore_original_source": "Ctrl+Shift+R",
    "work_extract_text": "Ctrl+L",
    "work_import_translation": "Ctrl+K",
    "work_clear_translation": "Ctrl+/",
    "work_clean_text": "Ctrl+Y",
    "work_export": "Ctrl+E",
    "view_text_toggle": "Ctrl+T",

    # 5. 자동화 작업 옵션
    "auto_text_size_current": "Ctrl+B",
    "auto_text_size_batch": "Ctrl+Shift+B",
    "auto_linebreak_current": "Ctrl+,",
    "auto_linebreak_batch": "Ctrl+Shift+,",

    # 6. 일괄 작업 옵션
    "batch_analyze": "Ctrl+Shift+F5",
    "batch_translate": "Ctrl+Shift+F6",
    "batch_inpaint": "Ctrl+Shift+F7",
    "batch_extract_text": "Ctrl+Shift+L",
    "batch_import_translation": "Ctrl+Shift+K",
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
        ("final_paint_color", "최종 페인팅 색상"),
        ("final_paint_to_background", "최종 페인팅을 배경으로 반영"),
        ("final_text_tool", "최종 텍스트 도구"),
        ("final_paint_above_toggle", "텍스트 위 페인팅 ON/OFF"),
        ("final_paint_opacity_inc", "최종 브러시 불투명도 증가"),
        ("final_paint_opacity_dec", "최종 브러시 불투명도 감소"),
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
    ("옵션", [
        ("option_auto_save_mode", "자동저장 모드"),
        ("option_api_settings", "API 관리"),
        ("option_translation_prompt", "번역 프롬프트 입력"),
        ("option_glossary", "단어장"),
        ("option_workspace_location", "작업 폴더 위치 변경"),
        ("option_register_ysb", ".ysbt 확장자 연결 등록"),
        ("option_unregister_ysbt", ".ysbt/.ysb 확장자 연결 해제"),
        ("option_shortcut_settings", "단축키 통합 관리"),
        ("option_macro_settings", "매크로 관리"),
        ("option_text_preset_settings", "페이지 글꼴 프리셋 관리"),
        ("option_item_text_preset_settings", "개별 글꼴 프리셋 관리"),
    ]),
    ("작업 옵션", [
        ("work_tab_cycle", "작업탭 변경"),
        ("work_page_prev", "이전 페이지"),
        ("work_page_next", "다음 페이지"),
        ("work_analyze", "개별 분석"),
        ("work_text_number_width", "텍스트 넘버 크기 변경"),
        ("work_translate", "개별 번역"),
        ("work_inpaint", "개별 인페인팅"),
        ("work_inpaint_source", "인페인팅을 원본으로"),
        ("work_restore_original_source", "원본으로 돌아가기"),
        ("work_extract_text", "개별 지문 추출"),
        ("work_import_translation", "개별 번역문 불러오기"),
        ("work_clear_translation", "번역문 내용 지우기"),
        ("work_clean_text", "개별 텍스트 정리"),
        ("work_export", "개별 출력"),
        ("view_text_toggle", "텍스트 표시 ON/OFF"),
    ]),
    ("자동화 작업 옵션", [
        ("auto_text_size_current", "자동 텍스트 크기 조정"),
        ("auto_text_size_batch", "일괄 자동 텍스트 크기 조정"),
        ("auto_linebreak_current", "자동 줄 내림"),
        ("auto_linebreak_batch", "일괄 자동 줄 내림"),
    ]),
    ("일괄 작업 옵션", [
        ("batch_analyze", "일괄 분석"),
        ("batch_translate", "일괄 번역"),
        ("batch_inpaint", "일괄 인페인팅"),
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




def shortcut_label_map() -> Dict[str, str]:
    result = {}
    for group_title, rows in GROUPS:
        for key, label in rows:
            result[key] = label
    return result


def shortcut_group_rows():
    rows = []
    for group_title, group_rows in GROUPS:
        for key, label in group_rows:
            rows.append((key, label, group_title))
    return rows


@dataclass
class ShortcutSettings:
    shortcuts: Dict[str, str] = field(default_factory=lambda: dict(DEFAULT_SHORTCUTS))
    enabled: Dict[str, bool] = field(default_factory=lambda: {k: True for k in DEFAULT_SHORTCUTS})
    macros: List[dict] = field(default_factory=list)

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
        p = cache_file()
        if not p.exists():
            return ShortcutSettings()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)

            merged_shortcuts = dict(DEFAULT_SHORTCUTS)
            merged_enabled = {k: True for k in DEFAULT_SHORTCUTS}

            loaded_macros = []

            if isinstance(data, dict):
                raw_shortcuts = data.get("shortcuts", data)
                raw_enabled = data.get("enabled", {})
                raw_macros = data.get("macros", [])
                if isinstance(raw_macros, list):
                    loaded_macros = []
                    valid_keys = set(DEFAULT_SHORTCUTS.keys())
                    for m in raw_macros:
                        if not isinstance(m, dict):
                            continue
                        mm = dict(m)
                        mm["actions"] = [k for k in (mm.get("actions", []) or []) if k in valid_keys]
                        loaded_macros.append(mm)

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

            # 1.2 자동화 단축키가 Ctrl+B / Ctrl+Shift+B를 사용하므로,
            # 예전 기본값으로 남아 있던 번역문 불러오기 단축키는 비워 충돌을 피한다.
            if merged_shortcuts.get("work_import_translation") == "Ctrl+B":
                merged_shortcuts["work_import_translation"] = ""
            if merged_shortcuts.get("batch_import_translation") == "Ctrl+Shift+B":
                merged_shortcuts["batch_import_translation"] = ""

            # 비활성화된 단축키는 입력칸/동작에서 빠진 상태로 유지한다.
            for key in list(merged_shortcuts.keys()):
                if not merged_enabled.get(key, True):
                    merged_shortcuts[key] = ""

            return ShortcutSettings(merged_shortcuts, merged_enabled, loaded_macros)
        except Exception:
            return ShortcutSettings()

    @staticmethod
    def save(settings: ShortcutSettings):
        p = cache_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)

    @staticmethod
    def cache_path() -> str:
        return str(cache_file())



class MacroFunctionSelectDialog(QDialog):
    def __init__(self, current_actions=None, settings: ShortcutSettings = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("매크로 기능 선택")
        self.resize(720, 720)

        self.settings = settings or ShortcutSettings()
        self.label_map = shortcut_label_map()
        self.current_actions = list(current_actions or [])
        self.rows = shortcut_group_rows()
        self.shortcut_to_key = {}
        self._refreshing_search = False

        layout = QVBoxLayout(self)

        title = QLabel("현재 매크로 기능")
        title.setStyleSheet("font-weight:bold;")
        layout.addWidget(title)

        self.current_box = QScrollArea()
        self.current_box.setWidgetResizable(True)
        self.current_box.setMinimumHeight(92)
        self.current_inner = QWidget()
        self.current_grid = QGridLayout(self.current_inner)
        self.current_grid.setContentsMargins(6, 6, 6, 6)
        self.current_grid.setSpacing(6)
        self.current_grid.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        self.current_box.setWidget(self.current_inner)
        layout.addWidget(self.current_box)

        help_label = QLabel("기능을 더블클릭하거나, 선택 후 [기능 추가]를 누르면 창을 닫지 않고 계속 추가됩니다. 검색창/목록에 포커스를 둔 상태에서 실제 단축키를 누르면 즉시 추가됩니다. 단축키 OFF/없음은 단축키 상태 표시일 뿐, 매크로 실행에는 영향 없습니다.")
        help_label.setWordWrap(True)
        layout.addWidget(help_label)

        self.search = QLineEdit()
        self.search.setPlaceholderText("기능명 / 그룹 / 단축키 검색  예: 자동 줄 내림, Ctrl+B")
        layout.addWidget(self.search)

        self.list_widget = QListWidget()
        self.list_widget.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        layout.addWidget(self.list_widget, 1)

        btn_line = QHBoxLayout()
        self.btn_add_selected = QPushButton("기능 추가")
        self.btn_close = QPushButton("닫기")
        btn_line.addStretch()
        btn_line.addWidget(self.btn_add_selected)
        btn_line.addWidget(self.btn_close)
        layout.addLayout(btn_line)

        self.btn_add_selected.clicked.connect(self.add_selected)
        self.btn_close.clicked.connect(self.accept)
        self.search.textChanged.connect(self.refill)
        self.search.returnPressed.connect(self.add_exact_shortcut_from_search)
        self.list_widget.itemDoubleClicked.connect(lambda item: self.add_key(item.data(Qt.ItemDataRole.UserRole)))

        # 검색창에서 Ctrl+F5/F5/Alt+D처럼 실제 단축키를 누르면 즉시 기능으로 추가한다.
        # QLineEdit가 키를 문자로 처리하기 전에 잡아야 하므로 eventFilter를 붙인다.
        self.search.installEventFilter(self)
        self.list_widget.installEventFilter(self)

        self.build_shortcut_index()
        self.refill()
        self.refresh_current_actions()

    def normalize_shortcut_text(self, value):
        value = str(value or "").strip()
        if not value:
            return ""

        # QKeySequence가 구두점 단축키(Ctrl+, / Ctrl+; 등)를
        # 환경에 따라 빈 문자열/다른 표기로 바꾸는 경우가 있어 수동 정규화도 같이 한다.
        compact = (
            value.replace(" ", "")
            .replace("Control+", "Ctrl+")
            .replace("control+", "ctrl+")
            .replace("CTRL+", "Ctrl+")
        )
        try:
            converted = QKeySequence(compact).toString(QKeySequence.SequenceFormat.PortableText)
            if converted:
                compact = converted.replace(" ", "")
        except Exception:
            pass
        return compact.lower()

    def key_token_from_event(self, event):
        key_code = event.key()

        punct = {
            Qt.Key.Key_Comma: ",",
            Qt.Key.Key_Period: ".",
            Qt.Key.Key_Semicolon: ";",
            Qt.Key.Key_Apostrophe: "'",
            Qt.Key.Key_Slash: "/",
            Qt.Key.Key_Backslash: "\\",
            Qt.Key.Key_BracketLeft: "[",
            Qt.Key.Key_BracketRight: "]",
            Qt.Key.Key_Minus: "-",
            Qt.Key.Key_Equal: "=",
            Qt.Key.Key_Plus: "+",
            Qt.Key.Key_QuoteDbl: '"',
            Qt.Key.Key_Colon: ":",
        }
        if key_code in punct:
            return punct[key_code]

        # F1~F35
        try:
            key_int = int(key_code)
        except Exception:
            try:
                key_int = key_code.value
            except Exception:
                key_int = 0

        for n in range(1, 36):
            if key_code == getattr(Qt.Key, f"Key_F{n}", None):
                return f"F{n}"

        # 문자/숫자
        txt = event.text()
        if txt and len(txt) == 1 and txt.isprintable():
            return txt.upper()

        return QKeySequence(key_code).toString(QKeySequence.SequenceFormat.PortableText)

    def shortcut_candidates_from_event(self, event):
        key_code = event.key()
        if key_code in (
            Qt.Key.Key_Control,
            Qt.Key.Key_Shift,
            Qt.Key.Key_Alt,
            Qt.Key.Key_Meta,
            Qt.Key.Key_unknown,
        ):
            return set()

        try:
            mods_value = event.modifiers().value
        except AttributeError:
            mods_value = int(event.modifiers())

        candidates = set()

        # Qt 기본 변환 후보
        try:
            pressed = QKeySequence(mods_value | key_code)
            portable = pressed.toString(QKeySequence.SequenceFormat.PortableText)
            native = pressed.toString(QKeySequence.SequenceFormat.NativeText)
            if portable:
                candidates.add(self.normalize_shortcut_text(portable))
            if native:
                candidates.add(self.normalize_shortcut_text(native))
        except Exception:
            pass

        # 구두점/특수키 수동 변환 후보
        mods = event.modifiers()
        parts = []
        if mods & Qt.KeyboardModifier.ControlModifier:
            parts.append("Ctrl")
        if mods & Qt.KeyboardModifier.AltModifier:
            parts.append("Alt")
        if mods & Qt.KeyboardModifier.ShiftModifier:
            parts.append("Shift")
        if mods & Qt.KeyboardModifier.MetaModifier:
            parts.append("Meta")

        token = self.key_token_from_event(event)
        if token:
            manual = "+".join(parts + [token]) if parts else token
            candidates.add(self.normalize_shortcut_text(manual))

        return {c for c in candidates if c}

    def is_shortcut_enabled_for_key(self, key):
        return bool(self.settings.enabled.get(key, True))

    def display_shortcut_for_key(self, key):
        if not self.is_shortcut_enabled_for_key(key):
            return ""
        seq = self.settings.seq(key)
        if not seq or seq.isEmpty():
            return ""
        return seq.toString(QKeySequence.SequenceFormat.NativeText)

    def portable_shortcut_for_key(self, key):
        if not self.is_shortcut_enabled_for_key(key):
            return ""
        seq = self.settings.seq(key)
        if not seq or seq.isEmpty():
            return ""
        return seq.toString(QKeySequence.SequenceFormat.PortableText)

    def status_text_for_key(self, key):
        # 이 상태는 "기능 실행 가능 여부"가 아니라 "단축키 등록 상태"만 의미한다.
        # 매크로는 기능 key를 직접 실행하므로 단축키 OFF여도 매크로 안에서는 실행된다.
        if not self.is_shortcut_enabled_for_key(key):
            return "단축키 OFF"
        if not self.display_shortcut_for_key(key):
            return "단축키 없음"
        return "단축키 ON"

    def build_shortcut_index(self):
        self.shortcut_to_key = {}
        for key, label, group_title in self.rows:
            portable = self.portable_shortcut_for_key(key)
            norm = self.normalize_shortcut_text(portable)
            if norm:
                self.shortcut_to_key[norm] = key

    def refresh_current_actions(self):
        while self.current_grid.count():
            item = self.current_grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()

        if not self.current_actions:
            lab = QLabel("아직 추가된 기능이 없습니다.")
            lab.setStyleSheet("color:#bfc3cc;")
            self.current_grid.addWidget(lab, 0, 0)
            return

        max_cols = 3
        for i, key in enumerate(self.current_actions):
            label = self.label_map.get(key, key)
            sk = self.display_shortcut_for_key(key)
            status = self.status_text_for_key(key)
            extra = f" / {sk}" if sk else f" / {status}"
            btn = QPushButton(f"{i + 1}. {label}{extra}  ×")
            btn.setToolTip("클릭하면 이 기능을 매크로에서 제거합니다.")

            if status == "단축키 ON":
                bg = "#2f425f"
                border = "#6d93d8"
                hover = "#4b5f86"
                color = "#ffffff"
            elif status == "단축키 OFF":
                bg = "#3b3a30"
                border = "#8a7d55"
                hover = "#514f3f"
                color = "#efe5bd"
            else:
                bg = "#34363c"
                border = "#70737d"
                hover = "#464953"
                color = "#d8d8d8"

            btn.setStyleSheet(
                "QPushButton {"
                f"background:{bg};"
                f"border:1px solid {border};"
                "border-radius:8px;"
                "padding:5px 9px;"
                f"color:{color};"
                "}"
                f"QPushButton:hover {{ background:{hover}; }}"
            )
            btn.clicked.connect(lambda checked=False, idx=i: self.remove_action_at(idx))
            self.current_grid.addWidget(btn, i // max_cols, i % max_cols)

    def remove_action_at(self, index):
        if 0 <= index < len(self.current_actions):
            removed = self.current_actions.pop(index)
            self.refresh_current_actions()

    def refill(self):
        query = self.search.text().strip().lower()
        self.list_widget.clear()

        for key, label, group_title in self.rows:
            native_shortcut = self.display_shortcut_for_key(key)
            portable_shortcut = self.portable_shortcut_for_key(key)
            status = self.status_text_for_key(key)
            hay = f"{label} {key} {group_title} {native_shortcut} {portable_shortcut} {status}".lower()
            if query and query not in hay:
                continue

            shortcut_part = f" / {native_shortcut}" if native_shortcut else ""
            item = QListWidgetItem(f"[{status}] [{group_title}] {label}{shortcut_part}  ({key})")
            item.setData(Qt.ItemDataRole.UserRole, key)
            if status != "단축키 ON":
                item.setForeground(Qt.GlobalColor.gray)
            self.list_widget.addItem(item)

        if self.list_widget.count() > 0:
            self.list_widget.setCurrentRow(0)

    def key_from_key_event(self, event):
        candidates = self.shortcut_candidates_from_event(event)
        if not candidates:
            return None

        # 실제 현재 단축키 설정과 1:1로 비교한다.
        # Ctrl+, / Ctrl+; 같은 구두점 단축키는 Qt matches만으로 놓치는 경우가 있어
        # PortableText/NativeText/수동 후보를 모두 비교한다.
        for key, label, group_title in self.rows:
            if not self.settings.enabled.get(key, True):
                continue
            seq = self.settings.seq(key)
            if not seq or seq.isEmpty():
                continue

            try:
                pressed = QKeySequence(event.modifiers().value | event.key())
                if pressed.matches(seq) == QKeySequence.SequenceMatch.ExactMatch:
                    return key
            except Exception:
                pass

            seq_candidates = {
                self.normalize_shortcut_text(seq.toString(QKeySequence.SequenceFormat.PortableText)),
                self.normalize_shortcut_text(seq.toString(QKeySequence.SequenceFormat.NativeText)),
            }
            if candidates.intersection(seq_candidates):
                return key

        return None

    def handle_shortcut_key_event(self, event):
        key = self.key_from_key_event(event)
        if not key:
            return False
        self.add_key(key)
        self.search.clear()
        return True

    def eventFilter(self, obj, event):
        if event.type() == QEvent.Type.ShortcutOverride:
            if self.key_from_key_event(event):
                event.accept()
                return True

        if event.type() == QEvent.Type.KeyPress:
            if self.handle_shortcut_key_event(event):
                return True

        return super().eventFilter(obj, event)

    def add_exact_shortcut_from_search(self):
        # Enter는 "현재 선택된 첫 항목"을 멋대로 추가하지 않는다.
        # 검색어가 정확히 단축키로 인식될 때만 추가해서 이동 같은 엉뚱한 블록이 쌓이는 문제를 막는다.
        text = self.search.text().strip()
        norm = self.normalize_shortcut_text(text)
        key = self.shortcut_to_key.get(norm)
        if key:
            self.add_key(key)
            self.search.clear()
            return True

        QMessageBox.information(self, "기능 추가", "정확히 일치하는 단축키가 없습니다. 기능명 검색 후 더블클릭하거나 [기능 추가]를 눌러주세요.")
        return False

    def add_selected(self):
        item = self.list_widget.currentItem()
        if not item:
            QMessageBox.information(self, "기능 추가", "추가할 기능을 선택해주세요.")
            return
        self.add_key(item.data(Qt.ItemDataRole.UserRole))

    def add_key(self, key):
        if not key:
            return
        self.current_actions.append(key)
        self.refresh_current_actions()

    def closeEvent(self, event):
        self.accept()
        event.accept()

    def get_actions(self):
        return list(self.current_actions)


class MacroSettingsDialog(QDialog):
    def __init__(self, settings: ShortcutSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("매크로 관리")
        self.resize(900, 560)
        self.settings = ShortcutSettings(
            dict(settings.shortcuts),
            {k: bool(settings.enabled.get(k, True)) for k in DEFAULT_SHORTCUTS},
            [dict(m) for m in getattr(settings, "macros", [])],
        )
        self.label_map = shortcut_label_map()
        self.rows = []
        self._handling = False

        self.setStyleSheet("""
            QDialog, QWidget { background-color: #1f1f22; color: #f2f2f2; }
            QLabel { color: #f2f2f2; }
            QLineEdit, QKeySequenceEdit {
                background-color: #2d2f34;
                color: #f5f5f5;
                border: 1px solid #53565f;
                padding: 3px;
            }
            QPushButton {
                background-color: #353841;
                color: #f2f2f2;
                border: 1px solid #5a5d66;
                padding: 5px 10px;
            }
            QPushButton:hover { background-color: #424652; }
            QCheckBox::indicator {
                width: 15px;
                height: 15px;
                border: 1px solid #72757f;
                background: #2d2f34;
            }
            QCheckBox::indicator:checked { background: #5da9ff; }
        """)

        root = QVBoxLayout(self)
        info = QLabel(
            "매크로는 여러 기능을 추가한 순서대로 연속 실행합니다.\n"
            "매크로 단축키가 기존 단축키와 겹치면, 확인 후 기존 단축키를 비활성화합니다."
        )
        info.setWordWrap(True)
        root.addWidget(info)

        add_btn = QPushButton("매크로 추가")
        add_btn.clicked.connect(self.add_macro)
        root.addWidget(add_btn, 0, Qt.AlignmentFlag.AlignLeft)

        self.scroll = QScrollArea()
        self.scroll.setWidgetResizable(True)
        self.inner = QWidget()
        self.grid = QGridLayout(self.inner)
        self.grid.setColumnStretch(2, 1)
        self.grid.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.scroll.setWidget(self.inner)
        root.addWidget(self.scroll, 1)

        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        root.addWidget(buttons)

        self.refill()

    def macro_label(self, actions):
        names = [self.label_map.get(k, k) for k in actions]
        return " + ".join(names) if names else "기능 없음"

    def normalized_macros(self):
        result = []
        for row in self.rows:
            name = row["name"].text().strip() or "새 매크로"
            enabled = bool(row["enabled"].isChecked())
            seq = row["seq"].keySequence().toString(QKeySequence.SequenceFormat.PortableText) if enabled else ""
            actions = list(row.get("actions", []))
            result.append({
                "enabled": enabled,
                "name": name,
                "shortcut": seq,
                "actions": actions,
            })
        return result

    def refill(self):
        while self.grid.count():
            item = self.grid.takeAt(0)
            w = item.widget()
            if w:
                w.deleteLater()
        self.rows = []

        headers = ["사용", "이름", "기능", "단축키", ""]
        for c, h in enumerate(headers):
            lab = QLabel(h)
            lab.setStyleSheet("font-weight:bold;")
            self.grid.addWidget(lab, 0, c)

        macros = getattr(self.settings, "macros", []) or []
        for macro in macros:
            self.add_macro_row(macro)

    def add_macro(self):
        name, ok = QInputDialog.getText(self, "매크로 추가", "매크로 이름:")
        if not ok:
            return
        name = name.strip() or "새 매크로"
        self.add_macro_row({"enabled": True, "name": name, "shortcut": "", "actions": []})

    def apply_macro_row_enabled_state(self, row_data, enabled):
        for key in ("name", "function_btn", "seq"):
            w = row_data.get(key)
            if w:
                w.setEnabled(enabled)

        seq = row_data.get("seq")
        if seq:
            if enabled:
                seq.setStyleSheet("")
            else:
                seq.setStyleSheet(
                    "QKeySequenceEdit {"
                    "background:#4a2f2f;"
                    "color:#bdbdbd;"
                    "border:1px solid #8a5555;"
                    "}"
                )

        name = row_data.get("name")
        function_btn = row_data.get("function_btn")
        if name:
            name.setStyleSheet("" if enabled else "QLineEdit { background:#3b3030; color:#bdbdbd; border:1px solid #6a4a4a; }")
        if function_btn:
            function_btn.setStyleSheet("" if enabled else "QPushButton { background:#3b3030; color:#bdbdbd; border:1px solid #6a4a4a; }")

    def on_macro_enabled_toggled(self, row_data, checked):
        if self._handling:
            return

        seq_edit = row_data.get("seq")
        self._handling = True
        try:
            if checked:
                restore = row_data.get("backup_shortcut", "")
                if restore:
                    seq_edit.setKeySequence(QKeySequence(restore))
            else:
                current = seq_edit.keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                if current:
                    row_data["backup_shortcut"] = current
                seq_edit.clear()
                row_data["last_shortcut"] = ""
        finally:
            self._handling = False

        self.apply_macro_row_enabled_state(row_data, checked)

        if checked:
            # setKeySequence 직후 editingFinished가 한 번 더 들어올 수 있어서
            # 실제 충돌 검사는 on_macro_shortcut_edited의 last_shortcut 가드가 담당한다.
            self.on_macro_shortcut_edited(row_data)

    def eventFilter(self, obj, event):
        if isinstance(obj, QLineEdit) and event.type() == QEvent.Type.KeyPress:
            if event.key() == Qt.Key.Key_F2:
                obj.setFocus()
                obj.selectAll()
                return True
        return super().eventFilter(obj, event)

    def add_macro_row(self, macro):
        row_num = len(self.rows) + 1
        enabled = QCheckBox()
        enabled.setChecked(bool(macro.get("enabled", True)))

        name = QLineEdit(str(macro.get("name", "새 매크로")))
        name.setPlaceholderText("매크로 이름")
        name.installEventFilter(self)

        actions = list(macro.get("actions", []) or [])
        function_btn = QPushButton(self.macro_label(actions))
        function_btn.setMinimumWidth(360)

        seq = QKeySequenceEdit()
        seq.setKeySequence(QKeySequence(str(macro.get("shortcut", ""))))

        delete_btn = QPushButton("삭제")

        initial_shortcut = seq.keySequence().toString(QKeySequence.SequenceFormat.PortableText) if enabled.isChecked() else ""
        row_data = {
            "enabled": enabled,
            "name": name,
            "actions": actions,
            "function_btn": function_btn,
            "seq": seq,
            "delete_btn": delete_btn,
            "backup_shortcut": str(macro.get("shortcut", "") or ""),
            "last_shortcut": initial_shortcut,
            "_shortcut_checking": False,
        }
        if not enabled.isChecked():
            seq.clear()
        self.rows.append(row_data)

        function_btn.clicked.connect(lambda checked=False, r=row_data: self.add_function_to_macro(r))
        delete_btn.clicked.connect(lambda checked=False, r=row_data: self.delete_macro_row(r))
        seq.editingFinished.connect(lambda r=row_data: self.on_macro_shortcut_edited(r))
        enabled.toggled.connect(lambda checked, r=row_data: self.on_macro_enabled_toggled(r, checked))
        self.apply_macro_row_enabled_state(row_data, enabled.isChecked())

        self.grid.addWidget(enabled, row_num, 0)
        self.grid.addWidget(name, row_num, 1)
        self.grid.addWidget(function_btn, row_num, 2)
        self.grid.addWidget(seq, row_num, 3)
        self.grid.addWidget(delete_btn, row_num, 4)

    def add_function_to_macro(self, row_data):
        dlg = MacroFunctionSelectDialog(row_data.get("actions", []), self.settings, self)
        dlg.exec()
        row_data["actions"] = dlg.get_actions()
        row_data["function_btn"].setText(self.macro_label(row_data["actions"]))

    def delete_macro_row(self, row_data):
        ans = QMessageBox.question(self, "매크로 삭제", f"'{row_data['name'].text()}' 매크로를 삭제할까요?")
        if ans != QMessageBox.StandardButton.Yes:
            return
        if row_data in self.rows:
            self.rows.remove(row_data)
        self.settings.macros = self.normalized_macros()
        self.refill()

    def on_macro_shortcut_edited(self, row_data):
        # QKeySequenceEdit는 키 입력 완료/포커스 이동/메시지박스 표시 과정에서
        # editingFinished가 중복으로 들어올 수 있다.
        # 그래서 같은 단축키는 한 번만 검사하도록 last_shortcut으로 방어한다.
        if self._handling or row_data.get("_shortcut_checking"):
            return
        if not row_data["enabled"].isChecked():
            return

        seq_text = row_data["seq"].keySequence().toString(QKeySequence.SequenceFormat.PortableText)
        old_text = row_data.get("last_shortcut", "")

        if not seq_text:
            row_data["last_shortcut"] = ""
            return

        if seq_text == old_text:
            return

        row_data["_shortcut_checking"] = True

        def restore_previous_shortcut():
            self._handling = True
            try:
                if old_text:
                    row_data["seq"].setKeySequence(QKeySequence(old_text))
                else:
                    row_data["seq"].clear()
                row_data["last_shortcut"] = old_text
            finally:
                self._handling = False

        try:
            # 다른 매크로 중복은 후입 우선으로 기존 매크로를 비활성화한다.
            for other in self.rows:
                if other is row_data:
                    continue
                if not other["enabled"].isChecked():
                    continue
                other_seq = other["seq"].keySequence().toString(QKeySequence.SequenceFormat.PortableText)
                if other_seq == seq_text:
                    ans = QMessageBox.question(
                        self,
                        "매크로 단축키 중복",
                        f"'{other['name'].text()}' 매크로가 같은 단축키를 사용 중입니다.\n"
                        f"기존 매크로를 비활성화하고 사용할까요?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if ans != QMessageBox.StandardButton.Yes:
                        restore_previous_shortcut()
                        return

                    self._handling = True
                    try:
                        other["backup_shortcut"] = other_seq
                        other["enabled"].setChecked(False)
                        other["seq"].clear()
                        other["last_shortcut"] = ""
                    finally:
                        self._handling = False
                    self.apply_macro_row_enabled_state(other, False)

            # 기존 일반 단축키와 충돌하면 일반 단축키를 토글 OFF 한다.
            for key, shortcut in list(self.settings.shortcuts.items()):
                if not self.settings.enabled.get(key, True):
                    continue
                if shortcut and QKeySequence(shortcut).toString(QKeySequence.SequenceFormat.PortableText) == seq_text:
                    label = self.label_map.get(key, key)
                    ans = QMessageBox.question(
                        self,
                        "기존 단축키 비활성화 확인",
                        f"'{label}' 기능이 같은 단축키를 사용 중입니다.\n\n"
                        f"기존 단축키를 비활성화하고 이 매크로에 지정할까요?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No,
                    )
                    if ans != QMessageBox.StandardButton.Yes:
                        restore_previous_shortcut()
                        return
                    self.settings.enabled[key] = False
                    self.settings.shortcuts[key] = ""
                    break

            row_data["last_shortcut"] = seq_text
            row_data["backup_shortcut"] = seq_text

        finally:
            row_data["_shortcut_checking"] = False

    def accept(self):
        self.settings.macros = self.normalized_macros()
        super().accept()

    def get_settings(self) -> ShortcutSettings:
        return self.settings


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
            [dict(m) for m in getattr(settings, "macros", [])],
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
                # 여기서 last_sequences를 바로 갱신하면 swap_if_conflict가
                # "변경 없음"으로 판단해서 매크로 단축키 충돌 검사를 건너뛴다.
                # 따라서 토글 ON 직후 충돌 검사는 swap_if_conflict가 담당하게 둔다.
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

        # 매크로 단축키와도 서로 감시한다.
        for macro in getattr(self.settings, "macros", []) or []:
            if not macro.get("enabled", True):
                continue
            macro_seq = str(macro.get("shortcut", "") or "")
            if not macro_seq:
                continue
            if QKeySequence(macro_seq).toString(QKeySequence.SequenceFormat.PortableText) == new_text:
                label = self.labels.get(key).text() if self.labels.get(key) else key
                macro_name = str(macro.get("name", "매크로"))
                ans = QMessageBox.question(
                    self,
                    "매크로 단축키 비활성화 확인",
                    f"'{macro_name}' 매크로가 같은 단축키를 사용 중입니다.\n\n"
                    f"매크로 단축키를 비활성화하고 '{label}'에 지정할까요?",
                    QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                    QMessageBox.StandardButton.No,
                )
                if ans != QMessageBox.StandardButton.Yes:
                    self._handling_change = True
                    try:
                        if old_text:
                            edit.setKeySequence(QKeySequence(old_text))
                        else:
                            edit.clear()
                        self.last_sequences[key] = old_text
                    finally:
                        self._handling_change = False
                    return
                macro["enabled"] = False
                macro["shortcut"] = ""
                break

        other_key = None
        for k, other_edit in self.edits.items():
            if k == key:
                continue
            if not self.checks[k].isChecked():
                continue
            if self.sequence_text(other_edit) == new_text:
                other_key = k
                break

        if other_key and notify:
            new_label = self.labels.get(key).text() if self.labels.get(key) else key
            old_label = self.labels.get(other_key).text() if self.labels.get(other_key) else other_key
            old_text_display = old_text if old_text else "비어 있음"
            ans = QMessageBox.question(
                self,
                "단축키 교체 확인",
                f"이미 사용 중인 단축키입니다.\n\n"
                f"{new_label}: {new_text}\n"
                f"{old_label}: {old_text_display}\n\n"
                f"서로 교체해서 사용할까요?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ans != QMessageBox.StandardButton.Yes:
                self._handling_change = True
                try:
                    if old_text:
                        edit.setKeySequence(QKeySequence(old_text))
                    else:
                        edit.clear()
                    self.last_sequences[key] = old_text
                finally:
                    self._handling_change = False
                return

        self._handling_change = True
        try:
            if other_key:
                other_edit = self.edits[other_key]
                if old_text:
                    other_edit.setKeySequence(QKeySequence(old_text))
                else:
                    other_edit.clear()
                self.last_sequences[other_key] = old_text

            self.last_sequences[key] = new_text
        finally:
            self._handling_change = False

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
