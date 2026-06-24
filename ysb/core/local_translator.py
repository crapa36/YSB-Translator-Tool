import os
import torch
from transformers import AutoModelForSeq2SeqLM, AutoTokenizer

class LocalTranslator:
    _instance = None

    def __init__(self, base_path="./local_models/translate_models/"):
        self.base_path = os.path.abspath(base_path)
        os.makedirs(self.base_path, exist_ok=True)
        self.device = "cuda" if torch.cuda.is_available() else "cpu"
        self.tokenizer = None
        self.model = None
        self.loaded_model_path = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def get_available_models(self) -> list:
        """/local_models/translate_models/ 폴더 내부의 다운로드된 로컬 모델 목록 스캔"""
        if not os.path.exists(self.base_path):
            return []
        return [
            d for d in os.listdir(self.base_path)
            if os.path.isdir(os.path.join(self.base_path, d))
        ]

    def _get_selected_model_path(self) -> str:
        """기존 UI/API 설정 파일에서 활성화된 로컬 모델 디렉토리명 쿼리"""
        selected_model_name = None
        try:
            from ysb.settings.api_settings import get_api_settings
            settings = get_api_settings()
            selected_model_name = getattr(settings, "local_translation_model", None)
        except ImportError:
            pass

        available_models = self.get_available_models()
        if not available_models:
            raise ValueError(f"No local translation models found in base path: {self.base_path}")

        if not selected_model_name or selected_model_name not in available_models:
            selected_model_name = available_models[0]

        return os.path.join(self.base_path, selected_model_name)

    def load_model(self):
        target_path = self._get_selected_model_path()
        if self.model is None or self.loaded_model_path != target_path:
            self.tokenizer = AutoTokenizer.from_pretrained(target_path)
            self.model = AutoModelForSeq2SeqLM.from_pretrained(target_path).to(self.device)
            self.loaded_model_path = target_path

    def translate(self, text: str, src_lang: str = "jpn_Jpan", tgt_lang: str = "kor_Hang") -> str:
        try:
            self.load_model()
            # Normalize target language code if it is not directly in mapping (e.g. "kor_K视觉")
            if tgt_lang not in self.tokenizer.lang_code_to_id:
                if "kor" in tgt_lang.lower() or "视觉" in tgt_lang:
                    tgt_lang = "kor_Hang"
                elif "jpn" in tgt_lang.lower():
                    tgt_lang = "jpn_Jpan"
            if src_lang not in self.tokenizer.lang_code_to_id:
                if "kor" in src_lang.lower() or "视觉" in src_lang:
                    src_lang = "kor_Hang"
                elif "jpn" in src_lang.lower():
                    src_lang = "jpn_Jpan"

            inputs = self.tokenizer(text, return_tensors="pt").to(self.device)
            translated_tokens = self.model.generate(
                **inputs,
                forced_bos_token_id=self.tokenizer.lang_code_to_id[tgt_lang],
                max_length=256
            )
            result = self.tokenizer.batch_decode(translated_tokens, skip_special_tokens=True)
            return result[0]
        except Exception as e:
            print(f">>> [Local Translator] Error during translation: {e}")
            return text
