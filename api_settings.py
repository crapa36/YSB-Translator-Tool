import json
from dataclasses import dataclass, asdict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QLineEdit,
    QDialogButtonBox, QMessageBox, QCheckBox, QPushButton, QHBoxLayout,
    QGroupBox, QRadioButton, QButtonGroup, QComboBox, QFileDialog,
    QFrame, QWidget, QScrollArea
)

from cache_utils import get_cache_file

CACHE_FILE_NAME = "api_cache.json"


def cache_file():
    return get_cache_file(CACHE_FILE_NAME)

LANG_KO = "ko"
LANG_EN = "en"

from lang_text import API_TR_KO_EN

def resolve_ui_language(widget=None):
    cur = widget
    while cur is not None:
        lang = getattr(cur, "ui_language", None) or getattr(cur, "_ui_language", None)
        if lang:
            lang = str(lang).lower()
            if lang.startswith("en"):
                return LANG_EN
            return LANG_KO
        try:
            cur = cur.parent()
        except Exception:
            break
    return LANG_KO

def tr_api(text, lang=LANG_KO):
    text = str(text)
    if str(lang).lower().startswith("en"):
        return API_TR_KO_EN.get(text, text)
    return text


@dataclass
class ApiSettings:
    # 선택 제공자
    selected_ocr_provider: str = "clova"
    selected_inpaint_provider: str = "replicate_lama"
    selected_translation_provider: str = "openai"

    # OCR API
    clova_api_url: str = ""
    clova_secret_key: str = ""
    clova_model: str = "clova_ocr_v2"
    # 과거 테스트 버전 호환용: JSON 경로 값은 로드만 유지하고 UI에서는 API Key 방식을 사용한다.
    google_vision_credential_json_path: str = ""
    google_vision_api_key: str = ""
    google_vision_model: str = "DOCUMENT_TEXT_DETECTION"
    google_vision_language_hints: str = "ja,ko,en"

    # Translation API
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    google_translate_api_key: str = ""
    gemini_api_key: str = ""
    custom_translation_api_key: str = ""
    custom_translation_base_url: str = ""
    custom_translation_model: str = ""
    custom_translation_preset_name: str = "Custom Compatible"
    openai_model: str = "gpt-4o-mini"
    deepseek_model: str = "deepseek-v4-flash"
    google_translate_model: str = "google_translate_basic_v2"
    gemini_model: str = "gemini-2.5-flash-lite"

    # Inpainting API
    # replicate_api_token은 구버전 캐시 호환용으로만 유지한다.
    # 실제 UI/실행은 LaMa와 Stable 토큰을 완전히 분리해서 사용한다.
    replicate_api_token: str = ""
    lama_replicate_api_token: str = ""
    stable_replicate_api_token: str = ""
    repaint_model: str = "allenhooo/lama:cdac78a1bec5b23c07fd29692fb70baa513ea403a39e643c48ec5edadb15fe72"
    stable_inpaint_model: str = "stability-ai/stable-diffusion-inpainting:95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3"
    stable_inpaint_prompt: str = "remove text and restore the original background"


class ApiSettingsStore:
    @staticmethod
    def load() -> ApiSettings:
        p = cache_file()
        if not p.exists():
            return ApiSettings()
        try:
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
            base = asdict(ApiSettings())
            # 과거 캐시 호환: 알 수 없는 키는 무시하고, 새 키는 기본값 유지
            base.update({k: v for k, v in data.items() if k in base})

            # v1.6 이전 캐시는 replicate_api_token 하나를 LaMa/Stable이 공유했다.
            # 새 구조에서는 두 토큰을 분리하되, 기존 사용자가 바로 깨지지 않도록 최초 로드 시 양쪽에 복사한다.
            legacy_token = str(base.get("replicate_api_token", "") or "").strip()
            if legacy_token:
                if not str(base.get("lama_replicate_api_token", "") or "").strip():
                    base["lama_replicate_api_token"] = legacy_token
                if not str(base.get("stable_replicate_api_token", "") or "").strip():
                    base["stable_replicate_api_token"] = legacy_token

            return ApiSettings(**base)
        except Exception:
            return ApiSettings()

    @staticmethod
    def save(settings: ApiSettings):
        p = cache_file()
        p.parent.mkdir(parents=True, exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)

    @staticmethod
    def cache_path() -> str:
        return str(cache_file())


def apply_settings_to_config(settings: ApiSettings):
    """Inject cached API settings into manga_engine.Config."""
    try:
        import os as _os
        from manga_engine import Config

        # OCR
        Config.OCR_PROVIDER = (settings.selected_ocr_provider or "clova").strip() or "clova"
        Config.CLOVA_API_URL = settings.clova_api_url.strip()
        Config.CLOVA_SECRET_KEY = settings.clova_secret_key.strip()
        Config.CLOVA_MODEL = settings.clova_model.strip() or "clova_ocr_v2"
        Config.GOOGLE_VISION_CREDENTIAL_JSON_PATH = settings.google_vision_credential_json_path.strip()  # 구버전 캐시 호환
        Config.GOOGLE_VISION_API_KEY = settings.google_vision_api_key.strip()
        Config.GOOGLE_VISION_MODEL = settings.google_vision_model.strip() or "DOCUMENT_TEXT_DETECTION"
        Config.GOOGLE_VISION_LANGUAGE_HINTS = settings.google_vision_language_hints.strip() or "ja,ko,en"

        # Translation
        Config.TRANSLATION_PROVIDER = (settings.selected_translation_provider or "openai").strip() or "openai"
        Config.OPENAI_API_KEY = settings.openai_api_key.strip()
        Config.DEEPSEEK_API_KEY = settings.deepseek_api_key.strip()
        Config.GOOGLE_TRANSLATE_API_KEY = settings.google_translate_api_key.strip()
        Config.GEMINI_API_KEY = settings.gemini_api_key.strip()
        Config.CUSTOM_TRANSLATION_API_KEY = settings.custom_translation_api_key.strip()
        Config.CUSTOM_TRANSLATION_BASE_URL = settings.custom_translation_base_url.strip()
        Config.CUSTOM_TRANSLATION_MODEL = settings.custom_translation_model.strip()
        Config.CUSTOM_TRANSLATION_PRESET_NAME = settings.custom_translation_preset_name.strip() or "Custom Compatible"
        Config.OPENAI_TRANSLATION_MODEL = settings.openai_model.strip() or "gpt-4o-mini"
        Config.DEEPSEEK_TRANSLATION_MODEL = settings.deepseek_model.strip() or "deepseek-v4-flash"
        Config.GOOGLE_TRANSLATE_MODEL = settings.google_translate_model.strip() or "google_translate_basic_v2"
        Config.GEMINI_TRANSLATION_MODEL = settings.gemini_model.strip() or "gemini-2.5-flash-lite"

        # Inpainting
        Config.INPAINT_PROVIDER = (settings.selected_inpaint_provider or "replicate_lama").strip() or "replicate_lama"

        legacy_token = settings.replicate_api_token.strip()
        Config.LAMA_REPLICATE_API_TOKEN = (settings.lama_replicate_api_token.strip() or legacy_token)
        Config.STABLE_REPLICATE_API_TOKEN = (settings.stable_replicate_api_token.strip() or legacy_token)

        # 구버전 호환용 전역 토큰. 실제 호출은 각 provider 전용 토큰을 우선 사용한다.
        Config.REPLICATE_API_TOKEN = Config.STABLE_REPLICATE_API_TOKEN if Config.INPAINT_PROVIDER == "replicate_stable" else Config.LAMA_REPLICATE_API_TOKEN

        Config.INPAINT_MODEL = settings.repaint_model.strip()
        Config.REPAINT_MODEL = Config.INPAINT_MODEL  # 구버전 호환
        Config.STABLE_INPAINT_MODEL = settings.stable_inpaint_model.strip() or "stability-ai/stable-diffusion-inpainting:95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3"
        Config.STABLE_INPAINT_PROMPT = settings.stable_inpaint_prompt.strip() or "remove text and restore the original background"

        if Config.REPLICATE_API_TOKEN:
            _os.environ["REPLICATE_API_TOKEN"] = Config.REPLICATE_API_TOKEN
    except Exception:
        pass


class ApiSettingsDialog(QDialog):
    def __init__(self, settings: ApiSettings, parent=None):
        super().__init__(parent)
        self._ui_language = resolve_ui_language(parent)
        self.setWindowTitle(tr_api("API 관리", self._ui_language))
        self.resize(880, 560)
        self.setMinimumSize(760, 420)
        self.setSizeGripEnabled(True)
        self.settings = settings
        self.edits = {}
        self.combos = {}
        self.buttons = {}
        self.button_groups = {}

        layout = QVBoxLayout(self)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        content = QWidget(self)
        content_layout = QVBoxLayout(content)
        content_layout.setContentsMargins(6, 6, 6, 6)
        scroll.setWidget(content)
        layout.addWidget(scroll, 1)

        info = QLabel(
            tr_api(
                "API 정보는 사용자 설정 캐시 파일에 저장됩니다.\n"
                "OCR / 인페인팅 / 번역 API는 분류별로 하나씩 선택해 사용합니다.\n"
                "캐시 위치: ",
                self._ui_language
            ) + ApiSettingsStore.cache_path()
        )
        info.setWordWrap(True)
        content_layout.addWidget(info)

        self._add_api_section(content_layout, "OCR API", [
            {
                "provider": "clova",
                "title": "CLOVA OCR",
                "fields": [
                    ("Model", "clova_model", False, "clova_ocr_v2"),
                    ("Invoke URL", "clova_api_url", False, "CLOVA OCR Invoke URL"),
                    ("Secret Key", "clova_secret_key", True, "CLOVA OCR Secret Key"),
                ],
            },
            {
                "provider": "google_vision",
                "title": "Google Vision OCR",
                "fields": [
                    ("Model / Mode", "google_vision_model", False, "DOCUMENT_TEXT_DETECTION"),
                    ("API Key", "google_vision_api_key", True, "Google Cloud Vision API Key"),
                    ("Language Hints", "google_vision_language_hints", False, "ja,ko,en"),
                ],
            },
        ], "selected_ocr_provider")

        self._add_api_section(content_layout, tr_api("인페인팅 API", self._ui_language), [
            {
                "provider": "replicate_lama",
                "title": "Replicate LaMa",
                "fields": [
                    ("Model", "repaint_model", False, "owner/model:version"),
                    ("API Token", "lama_replicate_api_token", True, "LaMa Replicate API Token"),
                ],
            },
            {
                "provider": "replicate_stable",
                "title": "Replicate Stable Diffusion Inpainting",
                "fields": [
                    ("Model", "stable_inpaint_model", False, "stability-ai/stable-diffusion-inpainting:95b72231..."),
                    ("Prompt", "stable_inpaint_prompt", False, "remove text and restore the original background"),
                    ("API Token", "stable_replicate_api_token", True, "Stable Replicate API Token"),
                ],
            },
        ], "selected_inpaint_provider")

        self._add_api_section(content_layout, tr_api("번역 API", self._ui_language), [
            {
                "provider": "openai",
                "title": "OpenAI",
                "fields": [
                    ("Model", "openai_model", False, "gpt-4o-mini"),
                    ("API Key", "openai_api_key", True, "OpenAI API Key"),
                ],
            },
            {
                "provider": "deepseek",
                "title": "DeepSeek",
                "fields": [
                    ("Model", "deepseek_model", False, "deepseek-chat"),
                    ("API Key", "deepseek_api_key", True, "DeepSeek API Key"),
                ],
            },
            {
                "provider": "google",
                "title": "Google Translate",
                "fields": [
                    ("Model", "google_translate_model", False, "google_translate_basic_v2"),
                    ("API Key", "google_translate_api_key", True, "Google Translate API Key"),
                ],
            },
            {
                "provider": "gemini",
                "title": "Gemini / Google AI Studio",
                "fields": [
                    ("Model", "gemini_model", False, "gemini-2.5-flash-lite"),
                    ("API Key", "gemini_api_key", True, "Google AI Studio Gemini API Key"),
                ],
            },
            {
                "provider": "custom",
                "title": "Custom / OpenAI-Compatible",
                "description": "OpenAI Chat Completions 호환 API만 사용할 수 있습니다. Base URL, Model, API Key를 입력하세요.\n호환 예시: OpenRouter, Groq, xAI Grok, Together, LM Studio, vLLM, Ollama OpenAI 호환 서버",
                "fields": [
                    ("Preset Name", "custom_translation_preset_name", False, "OpenRouter / Groq / xAI"),
                    ("Base URL", "custom_translation_base_url", False, "https://api.x.ai/v1"),
                    ("Model", "custom_translation_model", False, "grok-4.3"),
                    ("API Key", "custom_translation_api_key", True, "OpenAI-compatible API Key"),
                ],
            },
        ], "selected_translation_provider")

        content_layout.addStretch(1)

        option_line = QHBoxLayout()
        self.show_keys = QCheckBox(tr_api("키 보이기", self._ui_language))
        self.show_keys.toggled.connect(self.toggle_key_visibility)
        option_line.addWidget(self.show_keys)

        btn_clear = QPushButton(tr_api("입력칸 비우기", self._ui_language))
        btn_clear.clicked.connect(self.clear_all)
        option_line.addWidget(btn_clear)
        option_line.addStretch()
        content_layout.addLayout(option_line)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.button(QDialogButtonBox.StandardButton.Ok).setText(tr_api("확인", self._ui_language))
        buttons.button(QDialogButtonBox.StandardButton.Cancel).setText(tr_api("닫기", self._ui_language))
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def _add_separator(self, layout):
        line = QFrame(self)
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)

    def _add_api_section(self, parent_layout, section_title, cards, selected_attr):
        self._add_separator(parent_layout)
        title = QLabel(section_title)
        title.setStyleSheet("font-weight:bold; font-size:14px;")
        parent_layout.addWidget(title)

        group = QButtonGroup(self)
        group.setExclusive(True)
        self.button_groups[selected_attr] = group
        selected_value = str(getattr(self.settings, selected_attr, "") or "")
        data = asdict(self.settings)

        for card in cards:
            provider = card["provider"]
            row_widget = QWidget(self)
            row_layout = QHBoxLayout(row_widget)
            row_layout.setContentsMargins(0, 2, 0, 2)
            row_layout.setSpacing(8)

            radio = QRadioButton()
            radio.setToolTip(f"{section_title} {tr_api('제공자를 사용합니다.', self._ui_language)}" if self._ui_language == LANG_EN else f"이 {section_title} 제공자를 사용합니다.")
            group.addButton(radio)
            self.buttons[provider] = radio
            row_layout.addWidget(radio)

            box = QGroupBox(card["title"])
            grid = QGridLayout(box)
            grid.setHorizontalSpacing(8)
            grid.setVerticalSpacing(5)

            start_row = 0
            desc = str(card.get("description", "") or "").strip()
            if desc:
                desc_label = QLabel(tr_api(desc, self._ui_language))
                desc_label.setWordWrap(True)
                grid.addWidget(desc_label, 0, 0, 1, 2)
                start_row = 1

            for r, field in enumerate(card["fields"], start=start_row):
                label, key, secret, placeholder = field[:4]
                field_type = field[4] if len(field) >= 5 else "text"
                grid.addWidget(QLabel(label), r, 0)
                edit = QLineEdit()
                # 같은 키가 여러 카드에 나타날 수 있으므로 같은 위젯을 재사용하지 않고 동기화 저장만 한다.
                edit.setText(str(data.get(key, "")))
                edit.setPlaceholderText(placeholder)
                if secret:
                    edit.setEchoMode(QLineEdit.EchoMode.Password)
                if field_type == "file":
                    file_row = QHBoxLayout()
                    file_row.setContentsMargins(0, 0, 0, 0)
                    file_row.addWidget(edit, 1)
                    btn_browse = QPushButton(tr_api("찾아보기", self._ui_language))
                    btn_browse.clicked.connect(lambda _=False, e=edit: self.browse_json_file(e))
                    file_row.addWidget(btn_browse)
                    grid.addLayout(file_row, r, 1)
                else:
                    grid.addWidget(edit, r, 1)
                self.edits.setdefault(key, []).append(edit)

            row_layout.addWidget(box, 1)
            parent_layout.addWidget(row_widget)
            if provider == selected_value:
                radio.setChecked(True)

        # 과거 캐시값이 비었거나 잘못된 경우 첫 카드 선택
        if not any(btn.isChecked() for btn in group.buttons()) and group.buttons():
            group.buttons()[0].setChecked(True)

    def browse_json_file(self, edit: QLineEdit):
        path, _ = QFileDialog.getOpenFileName(
            self,
            tr_api("JSON 파일 선택", self._ui_language),
            edit.text().strip() or "",
            "JSON Files (*.json);;All Files (*.*)"
        )
        if path:
            edit.setText(path)

    def toggle_key_visibility(self, checked: bool):
        secret_keys = [
            "clova_secret_key", "google_vision_api_key", "openai_api_key",
            "deepseek_api_key", "google_translate_api_key", "gemini_api_key",
            "custom_translation_api_key", "replicate_api_token"
        ]
        for key in secret_keys:
            for edit in self.edits.get(key, []):
                edit.setEchoMode(QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password)

    def clear_all(self):
        if QMessageBox.question(self, tr_api("입력칸 비우기", self._ui_language), tr_api("입력칸을 전부 비울까요?", self._ui_language)) != QMessageBox.StandardButton.Yes:
            return
        seen = set()
        for key, edits in self.edits.items():
            for edit in edits:
                if id(edit) in seen:
                    continue
                seen.add(id(edit))
                edit.clear()

    def _selected_provider_for(self, attr_name: str, default: str) -> str:
        group = self.button_groups.get(attr_name)
        if not group:
            return default
        for provider, btn in self.buttons.items():
            if btn.isChecked() and group.id(btn) != -1:
                # 다른 그룹 버튼도 self.buttons에 섞여 있으므로, 이 그룹 소속인지 확인
                if btn in group.buttons():
                    return provider
        for btn in group.buttons():
            if btn.isChecked():
                for provider, candidate in self.buttons.items():
                    if candidate is btn:
                        return provider
        return default

    def _first_edit_text(self, key: str) -> str:
        edits = self.edits.get(key, [])
        if not edits:
            return ""
        # 같은 키가 여러 카드에 중복 표시될 수 있다.
        # 사용자가 어느 칸에 입력해도 저장되도록 비어있지 않은 값을 우선 사용한다.
        for edit in edits:
            value = edit.text().strip()
            if value:
                return value
        return edits[0].text().strip()

    def get_settings(self) -> ApiSettings:
        return ApiSettings(
            selected_ocr_provider=self._selected_provider_for("selected_ocr_provider", "clova"),
            selected_inpaint_provider=self._selected_provider_for("selected_inpaint_provider", "replicate_lama"),
            selected_translation_provider=self._selected_provider_for("selected_translation_provider", "openai"),
            clova_api_url=self._first_edit_text("clova_api_url"),
            clova_secret_key=self._first_edit_text("clova_secret_key"),
            clova_model=self._first_edit_text("clova_model") or "clova_ocr_v2",
            google_vision_credential_json_path=self.settings.google_vision_credential_json_path,
            google_vision_api_key=self._first_edit_text("google_vision_api_key"),
            google_vision_model=self._first_edit_text("google_vision_model") or "DOCUMENT_TEXT_DETECTION",
            google_vision_language_hints=self._first_edit_text("google_vision_language_hints") or "ja,ko,en",
            openai_api_key=self._first_edit_text("openai_api_key"),
            deepseek_api_key=self._first_edit_text("deepseek_api_key"),
            google_translate_api_key=self._first_edit_text("google_translate_api_key"),
            gemini_api_key=self._first_edit_text("gemini_api_key"),
            custom_translation_api_key=self._first_edit_text("custom_translation_api_key"),
            custom_translation_base_url=self._first_edit_text("custom_translation_base_url"),
            custom_translation_model=self._first_edit_text("custom_translation_model"),
            custom_translation_preset_name=self._first_edit_text("custom_translation_preset_name") or "Custom Compatible",
            openai_model=self._first_edit_text("openai_model") or "gpt-4o-mini",
            deepseek_model=self._first_edit_text("deepseek_model") or "deepseek-v4-flash",
            google_translate_model=self._first_edit_text("google_translate_model") or "google_translate_basic_v2",
            gemini_model=self._first_edit_text("gemini_model") or "gemini-2.5-flash-lite",
            # 구버전 캐시 호환: replicate_api_token은 UI에서 더 이상 직접 쓰지 않는다.
            replicate_api_token=self.settings.replicate_api_token,
            lama_replicate_api_token=self._first_edit_text("lama_replicate_api_token") or self.settings.replicate_api_token,
            stable_replicate_api_token=self._first_edit_text("stable_replicate_api_token") or self.settings.replicate_api_token,
            repaint_model=self._first_edit_text("repaint_model") or "allenhooo/lama:cdac78a1bec5b23c07fd29692fb70baa513ea403a39e643c48ec5edadb15fe72",
            stable_inpaint_model=self._first_edit_text("stable_inpaint_model") or "stability-ai/stable-diffusion-inpainting:95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3",
            stable_inpaint_prompt=self._first_edit_text("stable_inpaint_prompt") or "remove text and restore the original background",
        )
