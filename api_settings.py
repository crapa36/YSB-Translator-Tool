import json
from dataclasses import dataclass, asdict

from PyQt6.QtWidgets import (
    QDialog, QVBoxLayout, QGridLayout, QLabel, QLineEdit,
    QDialogButtonBox, QMessageBox, QCheckBox, QPushButton, QHBoxLayout
)

from cache_utils import get_cache_file

CACHE_FILE = get_cache_file("api_cache.json")


@dataclass
class ApiSettings:
    clova_api_url: str = ""
    clova_secret_key: str = ""
    openai_api_key: str = ""
    deepseek_api_key: str = ""
    google_translate_api_key: str = ""
    replicate_api_token: str = ""
    openai_model: str = "gpt-4o-mini"
    deepseek_model: str = "deepseek-v4-flash"
    google_translate_model: str = "google_translate_basic_v2"
    repaint_model: str = "allenhooo/lama:cdac78a1bec5b23c07fd29692fb70baa513ea403a39e643c48ec5edadb15fe72"


class ApiSettingsStore:
    @staticmethod
    def load() -> ApiSettings:
        if not CACHE_FILE.exists():
            return ApiSettings()
        try:
            with open(CACHE_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            base = asdict(ApiSettings())
            base.update({k: v for k, v in data.items() if k in base})
            return ApiSettings(**base)
        except Exception:
            return ApiSettings()

    @staticmethod
    def save(settings: ApiSettings):
        CACHE_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(asdict(settings), f, ensure_ascii=False, indent=2)

    @staticmethod
    def cache_path() -> str:
        return str(CACHE_FILE)


def apply_settings_to_config(settings: ApiSettings):
    """Inject cached API settings into manga_engine.Config."""
    try:
        import os as _os
        from manga_engine import Config

        Config.CLOVA_API_URL = settings.clova_api_url.strip()
        Config.CLOVA_SECRET_KEY = settings.clova_secret_key.strip()
        Config.OPENAI_API_KEY = settings.openai_api_key.strip()
        Config.DEEPSEEK_API_KEY = settings.deepseek_api_key.strip()
        Config.GOOGLE_TRANSLATE_API_KEY = settings.google_translate_api_key.strip()
        Config.REPLICATE_API_TOKEN = settings.replicate_api_token.strip()
        Config.OPENAI_TRANSLATION_MODEL = settings.openai_model.strip() or "gpt-4o-mini"
        Config.DEEPSEEK_TRANSLATION_MODEL = settings.deepseek_model.strip() or "deepseek-v4-flash"
        Config.GOOGLE_TRANSLATE_MODEL = settings.google_translate_model.strip() or "google_translate_basic_v2"
        Config.INPAINT_MODEL = settings.repaint_model.strip()
        Config.REPAINT_MODEL = Config.INPAINT_MODEL  # 구버전 호환

        if Config.REPLICATE_API_TOKEN:
            _os.environ["REPLICATE_API_TOKEN"] = Config.REPLICATE_API_TOKEN
    except Exception:
        pass


class ApiSettingsDialog(QDialog):
    def __init__(self, settings: ApiSettings, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API 관리")
        self.resize(760, 430)
        self.settings = settings
        self.edits = {}

        layout = QVBoxLayout(self)

        info = QLabel(
            "입력한 API 정보는 프로그램 폴더의 로컬 캐시 파일에 저장되고, 다음 실행 때 자동으로 불러옵니다.\n"
            "캐시 위치: " + ApiSettingsStore.cache_path()
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        grid = QGridLayout()
        grid.setHorizontalSpacing(8)
        grid.setVerticalSpacing(6)
        layout.addLayout(grid)

        rows = [
            ("CLOVA API URL", "clova_api_url", False),
            ("CLOVA SECRET KEY", "clova_secret_key", True),
            ("OpenAI API Key", "openai_api_key", True),
            ("DeepSeek API Key", "deepseek_api_key", True),
            ("Google Translate API Key", "google_translate_api_key", True),
            ("Replicate API Token", "replicate_api_token", True),
            ("OpenAI 번역 모델", "openai_model", False),
            ("DeepSeek 번역 모델", "deepseek_model", False),
            ("Google Translate 모델", "google_translate_model", False),
            ("인페인팅 모델", "repaint_model", False),
        ]

        data = asdict(settings)
        for r, (label, key, secret) in enumerate(rows):
            grid.addWidget(QLabel(label), r, 0)
            edit = QLineEdit()
            edit.setText(str(data.get(key, "")))
            if key == "repaint_model":
                edit.setPlaceholderText("owner/model:version 형식의 Replicate 모델명")
            elif key == "google_translate_model":
                edit.setPlaceholderText("기본값: google_translate_basic_v2")
            elif key in ("openai_model", "deepseek_model"):
                edit.setPlaceholderText("사용할 모델명을 입력")
            if secret:
                edit.setEchoMode(QLineEdit.EchoMode.Password)
            grid.addWidget(edit, r, 1)
            self.edits[key] = edit

        option_line = QHBoxLayout()
        self.show_keys = QCheckBox("키 보이기")
        self.show_keys.toggled.connect(self.toggle_key_visibility)
        option_line.addWidget(self.show_keys)

        btn_clear = QPushButton("입력칸 비우기")
        btn_clear.clicked.connect(self.clear_all)
        option_line.addWidget(btn_clear)
        option_line.addStretch()
        layout.addLayout(option_line)

        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def toggle_key_visibility(self, checked: bool):
        secret_keys = ["clova_secret_key", "openai_api_key", "deepseek_api_key", "google_translate_api_key", "replicate_api_token"]
        for key in secret_keys:
            self.edits[key].setEchoMode(
                QLineEdit.EchoMode.Normal if checked else QLineEdit.EchoMode.Password
            )

    def clear_all(self):
        if QMessageBox.question(self, "입력칸 비우기", "입력칸을 전부 비울까요?") != QMessageBox.StandardButton.Yes:
            return
        for edit in self.edits.values():
            edit.clear()

    def get_settings(self) -> ApiSettings:
        kwargs = {key: edit.text().strip() for key, edit in self.edits.items()}
        return ApiSettings(**kwargs)
