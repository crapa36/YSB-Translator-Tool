import os
import re
import json
import cv2
import numpy as np
import requests
import time
import math
import uuid
import copy
import html
import sys
import tempfile
import subprocess
import shutil
from pathlib import Path
from openai import OpenAI
try:
    from PIL import Image, ImageDraw, ImageFont, ImageFilter
    _PIL_IMPORT_ERROR = None
except Exception as _e:
    # PyInstaller onefile 빌드에서 PIL._imaging 같은 네이티브 모듈이 누락되면
    # 앱 시작 시점에 바로 죽지 않도록 지연 로드로 전환한다.
    Image = ImageDraw = ImageFont = None
    _PIL_IMPORT_ERROR = _e


def _ensure_pillow():
    """Pillow를 실제로 쓰는 순간에 로드한다.

    EXE 빌드에 PIL._imaging이 누락되어도 앱 시작 자체는 막지 않고,
    이미지 출력 기능을 사용할 때 명확한 오류로 넘긴다.
    """
    global Image, ImageDraw, ImageFont, ImageFilter, _PIL_IMPORT_ERROR
    if Image is not None and ImageDraw is not None and ImageFont is not None:
        return
    try:
        from PIL import Image as _Image, ImageDraw as _ImageDraw, ImageFont as _ImageFont, ImageFilter as _ImageFilter
        Image, ImageDraw, ImageFont = _Image, _ImageDraw, _ImageFont
        globals()["ImageFilter"] = _ImageFilter
        _PIL_IMPORT_ERROR = None
    except Exception as e:
        _PIL_IMPORT_ERROR = e
        raise RuntimeError(
            "Pillow 이미지 모듈을 불러오지 못했습니다. "
            "EXE 빌드에 Pillow 네이티브 모듈(PIL._imaging)이 누락되었을 수 있습니다. "
            "build_exe_v1.8.1_pillow_strong_bundle.bat로 다시 빌드해 주세요."
        ) from e

class Config:
    # ---------------------------------------------------------
    # [설정] 네이버 클라우드 CLOVA OCR 정보 (본인 키 입력 필수!)
    # ---------------------------------------------------------
    OCR_PROVIDER = "clova"
    CLOVA_API_URL = ""
    CLOVA_SECRET_KEY = ""
    CLOVA_MODEL = "clova_ocr_v2"
    CLOVA_OCR_LANGUAGE = "ja"
    GOOGLE_VISION_CREDENTIAL_JSON_PATH = ""
    GOOGLE_VISION_API_KEY = ""
    GOOGLE_VISION_MODEL = "DOCUMENT_TEXT_DETECTION"
    GOOGLE_VISION_OCR_LANGUAGE = "en"
    GOOGLE_VISION_LANGUAGE_HINTS = "ja,ko,en"

    # [설정] Local OCR / comic_text_detector + PaddleOCR
    LOCAL_PADDLE_MASK_DEVICE = "auto"
    LOCAL_PADDLE_OCR_LANGUAGE = "ja"
    LOCAL_MANGA_OCR_LANGUAGE = "ja"
    # comic_text_detector input_size는 사용자 원본 이미지 크기가 아니라 모델 내부 리사이즈 캔버스다.
    # UI에는 노출하지 않고 페이지 크기에 따라 자동 선택한다.
    LOCAL_PADDLE_MASK_INPUT_SIZE = "auto"
    
    # [설정] OpenAI & Replicate
    TRANSLATION_PROVIDER = "openai"
    OPENAI_API_KEY = ""
    DEEPSEEK_API_KEY = ""
    GOOGLE_TRANSLATE_API_KEY = ""
    GEMINI_API_KEY = ""
    CUSTOM_TRANSLATION_API_KEY = ""
    CUSTOM_TRANSLATION_BASE_URL = ""
    CUSTOM_TRANSLATION_MODEL = ""
    CUSTOM_TRANSLATION_PRESET_NAME = "Custom Compatible"
    REPLICATE_API_TOKEN = ""  # 구버전/선택 provider 호환용
    LAMA_REPLICATE_API_TOKEN = ""
    STABLE_REPLICATE_API_TOKEN = ""
    
    # [설정] 번역 모델 선택
    OPENAI_TRANSLATION_MODEL = ""
    DEEPSEEK_TRANSLATION_MODEL = ""
    GOOGLE_TRANSLATE_MODEL = "google_translate_basic_v2"
    GEMINI_TRANSLATION_MODEL = "gemini-2.5-flash-lite"
    CUSTOM_TRANSLATION_MODEL = ""

    # [설정] 옵션 캐시에서 주입되는 AI 번역 프롬프트 / 단어장
    # 기본값은 비어 있다. 프로그램이 깨지지 않도록 JSON 출력 규칙만 내부에서 별도로 붙인다.
    TRANSLATION_PROMPT = ""
    TRANSLATION_GLOSSARY_TEXT = ""

    # [설정] 인페인팅 모델 - api_settings/main에서 주입됨
    INPAINT_PROVIDER = "replicate_lama"
    INPAINT_MODEL = ""
    REPAINT_MODEL = ""  # 구버전 설정 호환용
    REPLICATE_LAMA_WAIT_SECONDS = 3
    STABLE_INPAINT_MODEL = "stability-ai/stable-diffusion-inpainting:95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3"
    STABLE_INPAINT_PROMPT = "remove text and restore the original background"
    STABLE_INPAINT_WAIT_SECONDS = 3
    LOCAL_LAMA_WAIT_SECONDS = 0
    GEMINI_INPAINT_MODEL = "gemini-2.5-flash-image"
    GEMINI_INPAINT_PROMPT = (
        "Remove the text only inside the white mask area and reconstruct the original manga background. "
        "Keep all characters, panel borders, screentones, line art, and unmasked areas unchanged. "
        "Return only the edited full image."
    )

    # [설정] 마스킹 비율
    INPAINT_RATIO = 0.1
    MERGE_RATIO = 0.2
    MERGE_MIN_STROKE_PX = 5
    MIN_STROKE_PX = 1
    
    # [설정] 긴 웹툰 이미지 OCR 분할
    OCR_TILE_HEIGHT = 7000
    OCR_TILE_OVERLAP = 500

class MangaProcessEngine:
    
    def __init__(self):
        print(">>> [System] 엔진 시동: Ultimate Integrated Version")

        if getattr(Config, 'REPLICATE_API_TOKEN', ""):
            os.environ['REPLICATE_API_TOKEN'] = Config.REPLICATE_API_TOKEN

        self.openai_client = None
        if getattr(Config, "OPENAI_API_KEY", ""):
            self.openai_client = OpenAI(
                api_key=Config.OPENAI_API_KEY
            )

        self.deepseek_client = None
        if getattr(Config, "DEEPSEEK_API_KEY", ""):
            self.deepseek_client = OpenAI(
                api_key=Config.DEEPSEEK_API_KEY,
                base_url="https://api.deepseek.com"
            )

        self.custom_translation_client = None
        custom_base_url = str(getattr(Config, "CUSTOM_TRANSLATION_BASE_URL", "") or "").strip()
        custom_api_key = str(getattr(Config, "CUSTOM_TRANSLATION_API_KEY", "") or "").strip()
        if custom_api_key and custom_base_url:
            self.custom_translation_client = OpenAI(
                api_key=custom_api_key,
                base_url=custom_base_url.rstrip("/")
            )

    # ---------------------------------------------------------
    # [CORE] CLOVA OCR 호출
    # ---------------------------------------------------------
    def _call_clova_ocr(self, image_path):
        if not Config.CLOVA_API_URL or not Config.CLOVA_SECRET_KEY:
            raise ValueError("CLOVA OCR API URL 또는 SECRET KEY가 비어있습니다.")
            
        request_json = {
            'images': [{'format': 'jpg', 'name': 'demo'}],
            'requestId': str(uuid.uuid4()), 'version': 'V2', 'timestamp': int(round(time.time() * 1000))
        }
        payload = {'message': json.dumps(request_json).encode('UTF-8')}
        files = [('file', open(image_path,'rb'))]
        headers = {'X-OCR-SECRET': Config.CLOVA_SECRET_KEY}
        try:
            res = requests.post(Config.CLOVA_API_URL, headers=headers, data=payload, files=files)
            if res.status_code != 200: 
                print(f"CLOVA Error: {res.text}")
                return None
            return res.json()
        except Exception as e:
            print(f"Connection Error: {e}")
            return None

    # ---------------------------------------------------------
    # [CORE] Google Vision OCR 호출
    # ---------------------------------------------------------
    def _format_google_vision_error(self, status_code, text_or_data):
        """Google Vision 오류를 작업자가 바로 이해할 수 있는 문장으로 정리한다."""
        message = ""
        code = status_code
        try:
            if isinstance(text_or_data, dict):
                err = text_or_data.get("error", {}) if isinstance(text_or_data.get("error", {}), dict) else {}
                message = str(err.get("message", "") or text_or_data)
                code = int(err.get("code", status_code) or status_code)
            else:
                data = json.loads(str(text_or_data))
                err = data.get("error", {}) if isinstance(data.get("error", {}), dict) else {}
                message = str(err.get("message", "") or text_or_data)
                code = int(err.get("code", status_code) or status_code)
        except Exception:
            message = str(text_or_data)

        lower = message.lower()
        if code == 403 and ("billing" in lower or "permission_denied" in lower):
            return (
                "Google Vision OCR Error: 403 / Cloud Vision API는 결제 사용 설정이 필요합니다. "
                "Google Cloud Console에서 해당 프로젝트의 결제 계정을 연결하고 Cloud Vision API가 활성화되어 있는지 확인해 주세요. "
                "방금 설정했다면 몇 분 뒤 다시 시도하세요."
            )
        if code == 403 and ("disabled" in lower or "has not been used" in lower):
            return (
                "Google Vision OCR Error: 403 / Cloud Vision API가 아직 활성화되지 않았거나 전파 대기 중입니다. "
                "Google Cloud Console에서 Cloud Vision API를 활성화한 뒤 몇 분 후 다시 시도하세요."
            )
        if code == 400 and ("api key" in lower or "key" in lower):
            return "Google Vision OCR Error: 400 / API Key가 올바른지, Cloud Vision API 사용 권한이 있는 프로젝트의 키인지 확인해 주세요."
        return f"Google Vision OCR Error: {code} / {message[:500]}"

    def _call_google_vision_ocr(self, image_path):
        import base64

        api_key = str(getattr(Config, "GOOGLE_VISION_API_KEY", "") or "").strip()
        if not api_key:
            raise ValueError("Google Vision OCR API Key가 비어있습니다.")

        model = str(getattr(Config, "GOOGLE_VISION_MODEL", "DOCUMENT_TEXT_DETECTION") or "DOCUMENT_TEXT_DETECTION").strip().upper()
        if model not in ("TEXT_DETECTION", "DOCUMENT_TEXT_DETECTION"):
            model = "DOCUMENT_TEXT_DETECTION"

        # Google Vision의 언어 힌트는 사용자가 직접 문자열로 입력하지 않는다.
        # API 설정창의 OCR 언어 콤보박스 값만 사용해서 동작을 확정한다.
        lang = self._normalize_ocr_language(getattr(Config, "GOOGLE_VISION_OCR_LANGUAGE", "en"))
        hints = [lang] if lang in ("en", "ja", "zh", "ko") else []

        with open(image_path, "rb") as f:
            content = base64.b64encode(f.read()).decode("ascii")

        req = {
            "requests": [
                {
                    "image": {"content": content},
                    "features": [{"type": model, "maxResults": 2000}],
                }
            ]
        }
        if hints:
            req["requests"][0]["imageContext"] = {"languageHints": hints}

        url = "https://vision.googleapis.com/v1/images:annotate"
        r = requests.post(url, params={"key": api_key}, json=req, timeout=90)
        if r.status_code != 200:
            raise ValueError(self._format_google_vision_error(r.status_code, r.text))
        data = r.json()
        responses = data.get("responses", [])
        if responses and responses[0].get("error"):
            raise ValueError(self._format_google_vision_error(responses[0].get("error", {}).get("code", 400), {"error": responses[0].get("error", {})}))
        return data

    def _google_vertices_to_points(self, vertices, offset_x=0, offset_y=0):
        pts = []
        for v in vertices or []:
            try:
                pts.append([int(v.get("x", 0)) + offset_x, int(v.get("y", 0)) + offset_y])
            except Exception:
                pass
        return pts

    def _append_google_raw_item(self, raw_items, text, vertices, offset_x=0, offset_y=0, locale="", detected_break="", order_index=None):
        text = str(text or "").strip()
        if not text:
            return
        detected_break = str(detected_break or "").strip()
        pts = self._google_vertices_to_points(vertices, offset_x, offset_y)
        if len(pts) < 3:
            return

        pts_arr = np.array(pts, dtype=np.int32)
        rect_rot = cv2.minAreaRect(pts_arr)
        (cx, cy), (rw, rh), angle = rect_rot
        stroke_size = min(rw, rh) if min(rw, rh) > 0 else max(rw, rh)
        bx, by, bw, bh = cv2.boundingRect(pts_arr)
        compact = ''.join(ch for ch in text if not ch.isspace())
        char_count = max(1, len(compact))

        raw_items.append({
            'text': text,
            'vertices': pts,
            'stroke_size': stroke_size,
            'cx': cx,
            'cy': cy,
            'rect': [bx, by, bw, bh],
            'char_count': char_count,
            'source_provider': 'google_vision',
            'locale': locale,
            'detected_break': detected_break,
            'order_index': order_index,
        })

    def _google_symbol_break_type(self, symbol):
        """Google Vision symbol.property.detectedBreak.type 추출."""
        try:
            return str(
                ((symbol or {}).get("property") or {})
                .get("detectedBreak", {})
                .get("type", "")
                or ""
            ).strip()
        except Exception:
            return ""

    def _google_word_text_and_break(self, word):
        """word 안의 symbol을 조립하고, 마지막 symbol의 detectedBreak를 보존한다."""
        symbols = (word or {}).get("symbols", []) or []
        chars = []
        last_break = ""
        for sym in symbols:
            chars.append(str((sym or {}).get("text", "") or ""))
            b = self._google_symbol_break_type(sym)
            if b:
                last_break = b
        return ''.join(chars).strip(), last_break

    def _google_word_locale(self, word, fallback=""):
        try:
            langs = ((word or {}).get("property") or {}).get("detectedLanguages", []) or []
            if langs:
                return str((langs[0] or {}).get("languageCode", "") or fallback)
        except Exception:
            pass
        return str(fallback or "")

    def _normalize_ocr_language(self, value):
        """API 설정창의 OCR 언어 값을 내부 정렬 코드(en/ja/ko/zh)로 정규화한다."""
        lang = str(value or "").strip().lower()
        aliases = {
            "jp": "ja", "jpn": "ja", "japanese": "ja", "일본어": "ja",
            "en-us": "en", "en-gb": "en", "eng": "en", "english": "en", "영어": "en",
            "kr": "ko", "kor": "ko", "korean": "ko", "한국어": "ko",
            "cn": "zh", "chi": "zh", "zho": "zh", "chinese": "zh", "중국어": "zh",
            "zh-cn": "zh", "zh-tw": "zh", "zh-hans": "zh", "zh-hant": "zh",
        }
        return aliases.get(lang, lang if lang in ("en", "ja", "ko", "zh") else "ja")

    def _current_ocr_language(self):
        provider = str(getattr(Config, "OCR_PROVIDER", "clova") or "clova").strip().lower()
        if provider == "google_vision":
            return self._normalize_ocr_language(getattr(Config, "GOOGLE_VISION_OCR_LANGUAGE", "en"))
        if provider == "local_paddle_ocr":
            return self._normalize_ocr_language(getattr(Config, "LOCAL_PADDLE_OCR_LANGUAGE", "ja"))
        if provider == "local_manga_ocr":
            return "ja"
        return self._normalize_ocr_language(getattr(Config, "CLOVA_OCR_LANGUAGE", "ja"))

    def _google_vision_response_to_raw_items(self, ocr_res, offset_x=0, offset_y=0):
        """
        Google Vision OCR 결과를 기존 엔진 raw_items 구조로 변환한다.

        CLOVA와 달리 Google Vision은 fullTextAnnotation 안에
        page > block > paragraph > word > symbol 구조를 준다.
        textAnnotations[1:]만 쓰면 일본어 세로문/여러 줄에서 좌표 단위가 흔들릴 수 있어서,
        가능하면 fullTextAnnotation의 word 단위를 우선 사용한다.
        """
        raw_items = []
        responses = ocr_res.get("responses", []) if isinstance(ocr_res, dict) else []
        if not responses:
            return raw_items

        res0 = responses[0] or {}
        full = res0.get("fullTextAnnotation") or {}
        pages = full.get("pages", []) or []

        for page in pages:
            page_locale = ""
            try:
                page_locale = str((page.get("property", {}).get("detectedLanguages", []) or [{}])[0].get("languageCode", "") or "")
            except Exception:
                page_locale = ""
            order_index = 0
            for block in page.get("blocks", []) or []:
                block_locale = str(((block.get("property", {}) or {}).get("detectedLanguages", []) or [{}])[0].get("languageCode", "") or page_locale)
                for para in block.get("paragraphs", []) or []:
                    para_locale = str(((para.get("property", {}) or {}).get("detectedLanguages", []) or [{}])[0].get("languageCode", "") or block_locale)
                    for word in para.get("words", []) or []:
                        text, detected_break = self._google_word_text_and_break(word)
                        if not text:
                            continue
                        vertices = (word.get("boundingBox") or {}).get("vertices", []) or []
                        locale = self._google_word_locale(word, para_locale)
                        self._append_google_raw_item(
                            raw_items,
                            text,
                            vertices,
                            offset_x,
                            offset_y,
                            locale,
                            detected_break=detected_break,
                            order_index=order_index,
                        )
                        order_index += 1

        # fullTextAnnotation이 비어 있거나 word 단위가 안 잡힌 경우만 textAnnotations fallback 사용.
        if not raw_items:
            annotations = res0.get("textAnnotations", []) or []
            # 0번은 전체 텍스트라 보통 너무 큰 박스다. 개별 조각만 사용한다.
            for ann in annotations[1:]:
                text = str(ann.get("description", "") or "").strip()
                vertices = ann.get("boundingPoly", {}).get("vertices", []) or []
                locale = str(ann.get("locale", "") or "")
                self._append_google_raw_item(raw_items, text, vertices, offset_x, offset_y, locale)

        return self._dedupe_ocr_items(raw_items)

    # ---------------------------------------------------------
    # [LOGIC] 1. 말풍선 내부 텍스트 정렬 (형태 기반 단순화)
    # ---------------------------------------------------------
    def _is_latin_ocr_items(self, items):
        """영어권 OCR처럼 단어 사이 공백 복원이 필요한 조각인지 대략 판정한다."""
        text = ''.join(str(it.get('text', '') or '') for it in (items or []))
        letters = [ch for ch in text if ch.isalpha()]
        if not letters:
            return False
        ascii_letters = [ch for ch in letters if ('A' <= ch <= 'Z') or ('a' <= ch <= 'z')]
        ascii_ratio = len(ascii_letters) / max(1, len(letters))
        locale_text = ' '.join(str(it.get('locale', '') or '').lower() for it in (items or []))
        provider_text = ' '.join(str(it.get('source_provider', '') or '') for it in (items or []))
        return ascii_ratio >= 0.65 or ('en' in locale_text and 'google_vision' in provider_text)

    def _english_spacing_words(self):
        """Local PaddleOCR 영어 후처리용 보수적 단어 사전.

        PaddleOCR은 만화 말풍선의 세로/좁은 영어 텍스트에서
        afterleaving, theoperationsthe, backof 같은 붙은 단어를 자주 만든다.
        외부 패키지 없이 안전하게 복원하기 위해 짧은 공통 단어 중심으로만 쓴다.
        """
        return {
            "a", "an", "the", "and", "or", "but", "if", "then", "than", "that", "this", "these", "those",
            "i", "me", "my", "mine", "you", "your", "he", "him", "his", "she", "her", "we", "our", "they", "them", "their",
            "am", "is", "are", "was", "were", "be", "been", "being", "have", "has", "had", "do", "does", "did",
            "will", "would", "can", "could", "should", "may", "might", "must", "need", "not", "no", "yes",
            "to", "of", "in", "on", "at", "by", "for", "from", "with", "without", "into", "onto", "over", "under",
            "after", "before", "back", "front", "behind", "inside", "outside", "through", "until", "again", "still",
            "even", "so", "just", "simply", "only", "also", "too", "very", "really", "almost", "never", "ever",
            "go", "goes", "going", "went", "gone", "run", "runs", "running", "ran", "leave", "leaves", "leaving", "left",
            "look", "looks", "looking", "find", "found", "stop", "stops", "stopped", "move", "moves", "moving", "forward",
            "know", "knows", "knew", "think", "thinks", "thought", "feel", "feels", "felt", "hear", "heard", "rang", "ring",
            "mind", "reason", "away", "hero", "afraid", "alarm", "room", "operations", "operation", "sortie", "gate",
            "open", "opens", "opening", "opened", "online", "begin", "begins", "beginning", "seconds", "second", "thirty",
            "target", "identified", "identify", "tenma", "spiritual", "pressure", "rising", "transfer", "beep", "clack", "whirr",
            "let", "lets", "let's", "im", "i'm", "ill", "i'll", "dont", "don't", "cant", "can't", "wont", "won't",
            "its", "it's", "thats", "that's", "theres", "there's", "here", "there", "what", "where", "when", "why", "how",
        }

    def _restore_english_segment_case(self, segment, original_slice, is_first=False):
        try:
            if original_slice.isupper() and len(original_slice) > 1:
                return segment.upper()
            if original_slice[:1].isupper() or is_first:
                if segment in ("i",):
                    return "I"
                if segment in ("i'm", "im"):
                    return "I'm"
                return segment[:1].upper() + segment[1:]
        except Exception:
            pass
        if segment == "i":
            return "I"
        if segment in ("i'm", "im"):
            return "I'm"
        return segment

    def _segment_english_compound_token(self, token):
        """붙어버린 영어 알파벳 토큰을 공통 단어 기준으로 보수적으로 나눈다."""
        token = str(token or "")
        if len(token) < 8:
            return token
        # 약어/효과음 대문자는 건드리지 않는다.
        if token.isupper() and len(token) <= 12:
            return token

        # CamelCase는 먼저 끊는다. 예: TargetidentifiedTenma -> Target identified Tenma
        camel = re.sub(r"(?<=[a-z])(?=[A-Z])", " ", token)
        if camel != token:
            parts = [self._segment_english_compound_token(part) for part in camel.split()]
            return " ".join(part for part in parts if part)

        # apostrophe가 들어간 토큰은 아래 사전 분할이 오히려 위험해서 대표 패턴만 처리한다.
        token = re.sub(r"^(I['’]m)(?=[A-Za-z])", r"\1 ", token)
        token = re.sub(r"^(I['’]ll)(?=[A-Za-z])", r"\1 ", token)
        if " " in token:
            return " ".join(self._segment_english_compound_token(part) for part in token.split())

        if not re.fullmatch(r"[A-Za-z]+", token):
            return token

        lower = token.lower()
        words = self._english_spacing_words()
        if lower in words:
            return token

        n = len(lower)
        # 너무 짧은 조각으로 과분할하지 않도록 1글자 단어는 i/a만 허용한다.
        allowed_one = {"i", "a"}
        inf = 10 ** 9
        dp = [(inf, []) for _ in range(n + 1)]
        dp[0] = (0.0, [])
        max_word_len = 18

        for i in range(n):
            if dp[i][0] >= inf:
                continue
            for j in range(i + 1, min(n, i + max_word_len) + 1):
                part = lower[i:j]
                if part in words and (len(part) >= 2 or part in allowed_one):
                    # 긴 단어를 조금 더 선호한다.
                    cost = 1.0 + max(0, 6 - len(part)) * 0.08
                    new_cost = dp[i][0] + cost
                    if new_cost < dp[j][0]:
                        dp[j] = (new_cost, dp[i][1] + [(i, j, part)])

        if dp[n][0] >= inf:
            return token

        segments = dp[n][1]
        if len(segments) <= 1:
            return token

        # 너무 많은 1~2글자 조각으로 쪼개진 결과는 위험하므로 취소한다.
        short_count = sum(1 for _i, _j, part in segments if len(part) <= 2)
        if short_count >= max(3, len(segments) // 2 + 1):
            return token

        out = []
        for idx, (i, j, part) in enumerate(segments):
            out.append(self._restore_english_segment_case(part, token[i:j], is_first=(idx == 0 and token[:1].isupper())))
        return " ".join(out)

    def _normalize_latin_spacing(self, text):
        """영어 OCR 결과의 기본 공백/문장부호만 정리한다.

        v2.1.0 Local OCR에서는 PaddleOCR의 언어 설정을 우선 신뢰한다.
        별도 사전 기반 강제 띄어쓰기 복원은 정상 영어 OCR 결과를 망가뜨릴 수 있어 사용하지 않는다.
        """
        text = str(text or "").replace("’", "'")
        text = re.sub(r"\s+([,\.\!\?;:…])", r"\1", text)
        text = re.sub(r"([,\.\!\?;:])(?=[A-Za-z])", r"\1 ", text)
        text = re.sub(r"([\(\[\{])\s+", r"\1", text)
        text = re.sub(r"\s+([\)\]\}])", r"\1", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _manga_sort_latin_words(self, items):
        """Google Vision 영어 OCR용: word 단위 박스를 줄 단위로 묶고 공백을 복원한다."""
        items = list(items or [])
        if not items:
            return ""

        def rect_h(it):
            try:
                return max(1.0, float(it.get('rect', [0, 0, 1, 1])[3]))
            except Exception:
                return 1.0

        heights = sorted(rect_h(it) for it in items)
        median_h = heights[len(heights) // 2] if heights else 12.0
        line_tol = max(6.0, median_h * 0.65)

        sorted_items = sorted(items, key=lambda it: (float(it.get('cy', 0) or 0), float(it.get('cx', 0) or 0)))
        lines = []

        for it in sorted_items:
            cy = float(it.get('cy', 0) or 0)
            placed = False
            for line in lines:
                if abs(cy - line['cy']) <= line_tol:
                    line['items'].append(it)
                    line['cy'] = (line['cy'] * (len(line['items']) - 1) + cy) / len(line['items'])
                    placed = True
                    break
            if not placed:
                lines.append({'cy': cy, 'items': [it]})

        lines.sort(key=lambda line: line['cy'])

        out_lines = []
        for line in lines:
            words = sorted(line['items'], key=lambda it: float(it.get('cx', 0) or 0))
            parts = []
            for it in words:
                word = str(it.get('text', '') or '').strip()
                if not word:
                    continue
                b = str(it.get('detected_break', '') or '').upper()
                no_space_before = bool(re.match(r"^[\.,!\?;:\)\]\}…、。！？・』」）］｝]+", word))
                if parts and not parts[-1].endswith('-') and not no_space_before:
                    parts.append(' ')
                parts.append(word)
                if b == 'HYPHEN' and not word.endswith('-'):
                    parts.append('-')
            line_text = ''.join(parts).strip()
            if line_text:
                out_lines.append(line_text)

        # 번역 API에는 줄바꿈보다 공백이 더 안정적이다.
        # OCR 박스는 줄 단위로 잡되, 최종 원문은 한 문장처럼 공백으로 이어준다.
        return self._normalize_latin_spacing(" ".join(out_lines).strip())

    def _cluster_ocr_items(self, items, axis="y", tol=8.0):
        """중심 좌표 기준으로 OCR 조각을 줄/열 단위로 묶는다."""
        items = list(items or [])
        if not items:
            return []
        key = 'cy' if axis == "y" else 'cx'
        ordered = sorted(items, key=lambda it: float(it.get(key, 0) or 0))
        clusters = []
        for it in ordered:
            value = float(it.get(key, 0) or 0)
            placed = False
            for cluster in clusters:
                if abs(value - cluster['value']) <= tol:
                    cluster['items'].append(it)
                    cluster['value'] = (cluster['value'] * (len(cluster['items']) - 1) + value) / len(cluster['items'])
                    placed = True
                    break
            if not placed:
                clusters.append({'value': value, 'items': [it]})
        return clusters

    def _ocr_bounds(self, items):
        xs, ys, xe, ye = [], [], [], []
        for it in items or []:
            try:
                x, y, w, h = it.get('rect', [0, 0, 1, 1])
                xs.append(float(x)); ys.append(float(y)); xe.append(float(x) + float(w)); ye.append(float(y) + float(h))
            except Exception:
                pass
        if not xs:
            return 0.0, 0.0, 1.0, 1.0
        x1, y1, x2, y2 = min(xs), min(ys), max(xe), max(ye)
        return x1, y1, max(1.0, x2 - x1), max(1.0, y2 - y1)

    def _median_item_size(self, items):
        widths, heights = [], []
        for it in items or []:
            try:
                x, y, w, h = it.get('rect', [0, 0, 1, 1])
                widths.append(max(1.0, float(w)))
                heights.append(max(1.0, float(h)))
            except Exception:
                pass
        widths.sort(); heights.sort()
        mw = widths[len(widths) // 2] if widths else 8.0
        mh = heights[len(heights) // 2] if heights else 8.0
        return mw, mh

    def _join_cjk_texts(self, items):
        return "".join(str(it.get('text', '') or '').strip() for it in (items or []) if str(it.get('text', '') or '').strip())

    def _item_rect_edges(self, item):
        try:
            x, y, w, h = item.get('rect', [0, 0, 1, 1])
            return float(x), float(y), float(x) + float(w), float(y) + float(h)
        except Exception:
            return 0.0, 0.0, 1.0, 1.0

    def _normalize_korean_spacing(self, text):
        """한국어 OCR 결과의 기본 공백/문장부호만 정리한다.

        한국어 자동 띄어쓰기는 별도 모델 없이는 위험하므로 Local OCR 단계에서는
        사용자가 선택한 OCR 언어 모델의 결과를 우선 보존한다.
        """
        text = str(text or '')
        text = re.sub(r"\s+", " ", text).strip()
        text = re.sub(r"\s+([,\.\!\?;:…、。！？・』」）］｝])", r"\1", text)
        text = re.sub(r"([\(\[\{『「（［｛])\s+", r"\1", text)
        text = re.sub(r"([,\.\!\?;:])(?=[A-Za-z가-힣])", r"\1 ", text)
        text = re.sub(r"\s+", " ", text).strip()
        return text

    def _manga_sort_korean_horizontal(self, items):
        """한국어 OCR용: 줄은 위→아래, 줄 안은 왼쪽→오른쪽, 단어 공백은 보존/복원한다."""
        items = list(items or [])
        if not items:
            return ""

        mw, mh = self._median_item_size(items)
        line_tol = max(6.0, mh * 0.70)
        gap_space_threshold = max(3.0, mw * 0.35)
        lines = self._cluster_ocr_items(items, axis="y", tol=line_tol)
        lines.sort(key=lambda line: line['value'])

        out_lines = []
        for line in lines:
            ordered = sorted(line['items'], key=lambda it: float(it.get('cx', 0) or 0))
            pieces = []
            prev = None

            for it in ordered:
                word = str(it.get('text', '') or '').strip()
                if not word:
                    continue

                if pieces and prev is not None:
                    prev_break = str(prev.get('detected_break', '') or '').upper()
                    no_space_before = bool(re.match(r"^[,\.\!\?;:…、。！？・』」）］｝]+", word))
                    prev_text = str(prev.get('text', '') or '')
                    no_space_after_prev = bool(re.search(r"[『「（［｛\(\[\{]$", prev_text))

                    if not no_space_before and not no_space_after_prev:
                        px1, py1, px2, py2 = self._item_rect_edges(prev)
                        cx1, cy1, cx2, cy2 = self._item_rect_edges(it)
                        gap = cx1 - px2
                        force_space = prev_break in ("SPACE", "SURE_SPACE", "EOL_SURE_SPACE", "LINE_BREAK")
                        # CLOVA는 break 정보가 비는 경우가 많아서 실제 OCR 박스 간격으로 한 번 더 판단한다.
                        if force_space or gap >= gap_space_threshold:
                            pieces.append(' ')

                pieces.append(word)
                prev = it

            line_text = self._normalize_korean_spacing(''.join(pieces))
            if line_text:
                out_lines.append(line_text)

        # 번역 API에는 줄바꿈보다 공백으로 이어진 한 문장이 더 안정적이다.
        return self._normalize_korean_spacing(' '.join(out_lines))

    def _manga_sort_cjk_horizontal(self, items):
        """일본어/중국어 가로문용: 위→아래, 왼쪽→오른쪽으로 공백 없이 결합한다."""
        items = list(items or [])
        if not items:
            return ""
        _, mh = self._median_item_size(items)
        line_tol = max(6.0, mh * 0.70)
        lines = self._cluster_ocr_items(items, axis="y", tol=line_tol)
        lines.sort(key=lambda line: line['value'])
        out_lines = []
        for line in lines:
            ordered = sorted(line['items'], key=lambda it: float(it.get('cx', 0) or 0))
            line_text = self._join_cjk_texts(ordered)
            if line_text:
                out_lines.append(line_text)
        return "".join(out_lines).strip()

    def _manga_sort_cjk_vertical(self, items):
        """일본어/중국어 세로문용: 오른쪽 열→왼쪽 열, 각 열은 위→아래로 결합한다."""
        items = list(items or [])
        if not items:
            return ""

        mw, mh = self._median_item_size(items)

        # 일본어 세로문은 "열"이 읽기 단위다.
        # CLOVA가 한 열을 긴 조각으로 주는 경우가 많으므로 x축 허용치는 너무 좁지 않게 둔다.
        col_tol = max(7.0, min(28.0, mw * 1.05))
        cols = self._cluster_ocr_items(items, axis="x", tol=col_tol)
        cols.sort(key=lambda col: -col['value'])

        out_cols = []
        for col in cols:
            ordered = sorted(col['items'], key=lambda it: float(it.get('cy', 0) or 0))
            col_text = self._join_cjk_texts(ordered)
            if col_text:
                out_cols.append(col_text)

        return "".join(out_cols).strip()

    def _looks_like_cjk_vertical(self, items):
        """사용자 옵션 없이 일본어/중국어 안에서 세로문/가로문을 내부 판정한다.

        일본어 만화 OCR에서는 CLOVA가 세로문 한 열을 긴 조각 하나로 주는 경우가 많다.
        이때 기존의 row_count > col_count 기준만 쓰면 세로문을 가로문으로 오판해서
        왼쪽 조각부터 결합될 수 있다. 일본어/중국어 선택 상태에서는 세로문 판정을
        조금 더 강하게 가져가되, 명확히 가로로 긴 효과음/영문은 가로문으로 남긴다.
        """
        items = list(items or [])
        if len(items) <= 1:
            return False

        _, _, bw, bh = self._ocr_bounds(items)
        mw, mh = self._median_item_size(items)
        row_count = len(self._cluster_ocr_items(items, axis="y", tol=max(6.0, mh * 0.70)))
        col_count = len(self._cluster_ocr_items(items, axis="x", tol=max(6.0, mw * 0.80)))

        joined_text = "".join(str(it.get('text', '') or '') for it in items)
        has_cjk = bool(re.search(r"[ぁ-ゟ゠-ヿ一-龯]", joined_text))
        ascii_letters = len(re.findall(r"[A-Za-z]", joined_text))
        cjk_letters = len(re.findall(r"[ぁ-ゟ゠-ヿ一-龯]", joined_text))

        # 명확히 가로로 긴 라틴/효과음 후보는 가로문으로 둔다.
        if bw > bh * 1.45 and row_count <= 2 and col_count >= row_count:
            return False
        if ascii_letters > 0 and ascii_letters >= cjk_letters:
            return False

        # OCR 조각 자체가 세로로 긴 경우. CLOVA 일본어 세로문에서 가장 흔하다.
        tall_items = 0
        for it in items:
            try:
                _x, _y, iw, ih = it.get('rect', [0, 0, 1, 1])
                if float(ih) >= max(1.0, float(iw)) * 1.15:
                    tall_items += 1
            except Exception:
                pass
        tall_ratio = tall_items / max(1, len(items))

        if has_cjk and tall_ratio >= 0.45 and bh >= mh * 1.30:
            return True

        # 세로문은 보통 열 수보다 행/글자층이 많다. 반대로 2줄 가로문은 행 수가 적고 열 수가 많다.
        if row_count >= col_count and bh >= mh * 1.60:
            return True

        # 한 열짜리 또는 짧은 여러 열 세로문 대응.
        if has_cjk and col_count <= 3 and bh > bw * 0.90 and row_count >= 2:
            return True

        # 말풍선 내부의 여러 세로열이 하나의 contour로 잡힌 경우:
        # 전체 박스가 아주 세로로 길지 않아도, CJK 조각들이 세로형이면 오른쪽→왼쪽 열 정렬이 안전하다.
        if has_cjk and len(items) >= 2 and tall_ratio >= 0.35 and bh >= bw * 0.65:
            return True

        return False

    def _manga_sort_japanese_or_chinese(self, items):
        """일본어/중국어 선택 시: 세로문은 만화식, 가로문은 일반 가로문으로 결합한다."""
        if self._looks_like_cjk_vertical(items):
            return self._manga_sort_cjk_vertical(items)
        return self._manga_sort_cjk_horizontal(items)

    def _manga_sort(self, items):
        if not items:
            return ""
        items = list(items or [])
        lang = self._current_ocr_language()

        if lang == "en":
            return self._manga_sort_latin_words(items)
        if lang == "ko":
            return self._manga_sort_korean_horizontal(items)
        if lang in ("ja", "zh"):
            return self._manga_sort_japanese_or_chinese(items)

        # 캐시/구버전 값이 섞였을 때의 안전장치.
        if self._is_latin_ocr_items(items):
            return self._manga_sort_latin_words(items)
        return self._manga_sort_japanese_or_chinese(items)


    def _make_ocr_item_payload(self, item):
        """
        그룹 데이터 안에 보존할 CLOVA OCR 조각 정보.

        main.py의 자동 텍스트 크기 조정은 이 ocr_items를 읽어서
        원문 글자 간 좌표 차이 / 단일 조각 길이 ÷ 글자 수로 font_size를 추정한다.
        """
        try:
            rect = item.get('rect', [0, 0, 1, 1])
            rect = [int(rect[0]), int(rect[1]), int(rect[2]), int(rect[3])]
        except Exception:
            rect = [0, 0, 1, 1]

        vertices = []
        for p in item.get('vertices', []) or []:
            try:
                vertices.append([int(p[0]), int(p[1])])
            except Exception:
                try:
                    vertices.append([int(p.get('x', 0)), int(p.get('y', 0))])
                except Exception:
                    pass

        text = str(item.get('text', '') or '')
        try:
            char_count = int(item.get('char_count') or len(''.join(ch for ch in text if not ch.isspace())) or 1)
        except Exception:
            char_count = max(1, len(''.join(ch for ch in text if not ch.isspace())))

        return {
            'text': text,
            'vertices': vertices,
            'rect': rect,
            'cx': float(item.get('cx', rect[0] + rect[2] / 2)),
            'cy': float(item.get('cy', rect[1] + rect[3] / 2)),
            'stroke_size': float(item.get('stroke_size', 0) or 0),
            'char_count': max(1, char_count),
            'source_provider': str(item.get('source_provider', '') or item.get('source', '') or ''),
            'locale': str(item.get('locale', '') or ''),
            'detected_break': str(item.get('detected_break', '') or ''),
            'order_index': item.get('order_index'),
        }

    def _make_ocr_items_payload(self, items):
        """그룹에 포함된 OCR 조각들을 읽기 순서 기준으로 보존한다."""
        return [self._make_ocr_item_payload(it) for it in (items or [])]

    def _ocr_item_size_score(self, item):
        """OCR 조각의 대략적인 글자 크기 점수."""
        try:
            x, y, w, h = item.get('rect', [0, 0, 1, 1])
            w = max(1.0, float(w))
            h = max(1.0, float(h))
            text = str(item.get('text', '') or '')
            char_count = max(1, len(''.join(ch for ch in text if not ch.isspace())))
            per_char_area = (w * h / char_count) ** 0.5
            stroke = float(item.get('stroke_size', 0) or 0)
            minor = min(w, h)
            return max(per_char_area, stroke, minor)
        except Exception:
            return 1.0

    def _split_main_and_ruby_items(self, items):
        """
        OCR 조각 중 후리가나/첨자처럼 작은 조각을 본문 조각에서 제외한다.

        - 마스크/인페인팅용 vertices_list는 전체 OCR 조각을 유지한다.
        - 번역 원문 text와 자동 크기 조정용 ocr_items는 본문 조각만 사용한다.
        """
        items = list(items or [])
        if len(items) <= 1:
            return items, []

        scores = [self._ocr_item_size_score(it) for it in items]
        if not scores:
            return items, []

        sorted_scores = sorted(scores)
        q75 = sorted_scores[int((len(sorted_scores) - 1) * 0.75)]
        med = sorted_scores[len(sorted_scores) // 2]
        ref = max(q75, med, 1.0)

        main_items = []
        ruby_items = []

        for item, score in zip(items, scores):
            text = str(item.get('text', '') or '')
            compact_len = max(1, len(''.join(ch for ch in text if not ch.isspace())))

            is_small = score < ref * 0.65
            if compact_len >= 2 and score < ref * 0.72:
                is_small = True

            if is_small:
                ruby_items.append(item)
            else:
                main_items.append(item)

        if not main_items:
            return items, []

        if len(main_items) == 1 and len(items) >= 3:
            main_score = self._ocr_item_size_score(main_items[0])
            if main_score < ref * 0.95:
                return items, []

        return main_items, ruby_items


    # ---------------------------------------------------------
    # [LOGIC] 2. 전체 블록 ID 순서 (우상단 -> 좌하단)
    # ---------------------------------------------------------
    def _organize_blocks(self, data_list):
        if not data_list: return []
        lang = self._current_ocr_language()
        right_to_left_rows = lang in ("ja", "zh")
        
        # Y좌표(상단) 기준으로 1차 정렬
        data_list.sort(key=lambda x: x['rect'][1])
        
        rows = []
        current_row = []
        
        if data_list:
            current_row.append(data_list[0])
            for i in range(1, len(data_list)):
                curr = data_list[i]
                prev = current_row[-1]
                
                # 높이 차이가 100px 이내면 '같은 줄(Row)'로 간주
                if abs(curr['rect'][1] - prev['rect'][1]) < 100:
                    current_row.append(curr)
                else:
                    # 일본어/중국어 만화는 오른쪽->왼쪽, 영어/한국어는 왼쪽->오른쪽으로 정렬
                    current_row.sort(key=lambda x: -x['rect'][0] if right_to_left_rows else x['rect'][0])
                    rows.append(current_row)
                    current_row = [curr]
            
            # 마지막 줄 처리
            current_row.sort(key=lambda x: -x['rect'][0] if right_to_left_rows else x['rect'][0])
            rows.append(current_row)
        
        final_list = []
        for row in rows: final_list.extend(row)
        for i, d in enumerate(final_list): d['id'] = i + 1
            
        return final_list

    # ---------------------------------------------------------
    # [CORE] 전체 분석 (rect 계산 추가됨)
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # [CORE] 전체 분석 - 긴 웹툰 이미지 세로 분할 OCR 지원
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # [CORE] 전체 분석 - 공용 타일 OCR 사용
    # ---------------------------------------------------------
    def _ocr_regions_to_mask(self, regions, w, h):
        """저장된 OCR 분석 범위 목록을 0/255 마스크로 변환한다.

        regions가 비어 있으면 None을 반환하며, 기존 전체 분석과 동일하게 동작한다.
        """
        if not regions:
            return None
        mask = np.zeros((int(h), int(w)), dtype=np.uint8)
        for region in regions or []:
            if not isinstance(region, dict):
                continue
            shape = str(region.get("shape") or "rect")
            if shape == "free":
                pts = []
                for pt in region.get("points_norm") or []:
                    if not isinstance(pt, (list, tuple)) or len(pt) < 2:
                        continue
                    x = max(0, min(int(w) - 1, int(round(float(pt[0]) * int(w)))))
                    y = max(0, min(int(h) - 1, int(round(float(pt[1]) * int(h)))))
                    pts.append([x, y])
                if len(pts) >= 3:
                    cv2.fillPoly(mask, [np.array(pts, dtype=np.int32)], 255)
            else:
                r = region.get("rect_norm") or []
                if len(r) < 4:
                    continue
                try:
                    x1, y1, x2, y2 = [float(v) for v in r[:4]]
                except Exception:
                    continue
                x1 = max(0, min(int(w) - 1, int(round(x1 * int(w)))))
                y1 = max(0, min(int(h) - 1, int(round(y1 * int(h)))))
                x2 = max(0, min(int(w) - 1, int(round(x2 * int(w)))))
                y2 = max(0, min(int(h) - 1, int(round(y2 * int(h)))))
                if x2 > x1 and y2 > y1:
                    cv2.rectangle(mask, (x1, y1), (x2, y2), 255, thickness=-1)
        if cv2.countNonZero(mask) <= 0:
            return None
        return mask

    def _filter_raw_items_by_mask(self, raw_items, mask):
        if mask is None:
            return raw_items or []
        h, w = mask.shape[:2]
        out = []
        for item in raw_items or []:
            try:
                cx = max(0, min(w - 1, int(round(float(item.get('cx', 0))))))
                cy = max(0, min(h - 1, int(round(float(item.get('cy', 0))))))
                if mask[cy, cx] > 0:
                    out.append(item)
            except Exception:
                continue
        return out

    def analyze_image(self, image_path, analysis_regions=None):
        print(f">>> [Analysis] 전체 분석: {os.path.basename(image_path)}")

        img_array = np.fromfile(image_path, np.uint8)
        ori_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if ori_img is None:
            raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")

        h, w, _ = ori_img.shape

        provider = str(getattr(Config, "OCR_PROVIDER", "clova") or "clova").strip().lower()
        analysis_mask = self._ocr_regions_to_mask(analysis_regions, w, h)

        if provider in ("local_paddle_ocr", "local_manga_ocr"):
            return self.analyze_image_local_paddle_mask(image_path, ori_img=ori_img, analysis_mask=analysis_mask)

        # 짧은 이미지든 긴 웹툰 이미지든 여기서 자동 처리
        # h <= OCR_TILE_HEIGHT면 단일 OCR
        # h > OCR_TILE_HEIGHT면 세로 분할 OCR
        if analysis_mask is not None:
            raw_items = []
            contours, _ = cv2.findContours(analysis_mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours or []:
                if cnt is None or cv2.contourArea(cnt) < 4:
                    continue
                x, y, rw, rh = cv2.boundingRect(cnt)
                pad = 4
                x1 = max(0, x - pad); y1 = max(0, y - pad)
                x2 = min(w, x + rw + pad); y2 = min(h, y + rh + pad)
                crop = ori_img[y1:y2, x1:x2]
                if crop.size <= 0:
                    continue
                raw_items.extend(self._ocr_image_region_tiled(crop, offset_x=x1, offset_y=y1))
            raw_items = self._filter_raw_items_by_mask(self._dedupe_ocr_items(raw_items), analysis_mask)
        else:
            raw_items = self._ocr_image_region_tiled(
                ori_img,
                offset_x=0,
                offset_y=0
            )

        grouped_data, mask_merge = self._group_text_blocks_by_ratio(raw_items, w, h)
        mask_inpaint = self._create_ratio_mask(grouped_data, w, h)

        return ori_img, grouped_data, mask_merge, mask_inpaint

    def _normalize_local_detector_mask(self, mask, w, h, *, dilate_px=0):
        """comic_text_detector 마스크를 YSB 내부 0/255 단일 채널 마스크로 정규화한다.

        주의: v2.1.0 Local 테스트에서는 detector의 raw segmentation mask를
        최종 인페인팅 마스크로 직접 사용하지 않는다. 이 함수는 디버그/호환용으로
        남겨두고, 실제 LOCAL Paddle OCR 마스크는 _create_detector_candidate_mask()의
        block/line 게이트를 통과한 안전 마스크를 사용한다.
        """
        from ysb.engines.text_detection.mask_preview import ensure_uint8_mask
        clean = ensure_uint8_mask(mask, dilate_px=max(0, int(dilate_px or 0)))
        if clean.shape[:2] != (h, w):
            clean = cv2.resize(clean, (w, h), interpolation=cv2.INTER_NEAREST)
        return clean

    def _clamp_detector_box(self, bbox, w, h):
        try:
            x1, y1, x2, y2 = [int(round(float(v))) for v in bbox[:4]]
        except Exception:
            return None
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        x1 = max(0, min(w - 1, x1))
        y1 = max(0, min(h - 1, y1))
        x2 = max(0, min(w, x2))
        y2 = max(0, min(h, y2))
        if x2 <= x1 or y2 <= y1:
            return None
        return x1, y1, x2, y2

    def _detector_block_is_reasonable(self, bbox, w, h):
        """너무 크거나 너무 작은 detector block을 기본 마스크 후보에서 제외한다."""
        box = self._clamp_detector_box(bbox, w, h)
        if box is None:
            return False
        x1, y1, x2, y2 = box
        bw = x2 - x1
        bh = y2 - y1
        area = bw * bh
        page_area = max(1, int(w) * int(h))
        if bw < 3 or bh < 3 or area < 9:
            return False
        # detector가 그림/배경을 큰 덩어리로 오검출했을 때 전체 페이지가 오염되는 걸 막는다.
        # 말풍선 전체를 지우는 도구가 아니라 '텍스트 제거 마스크' 테스트이므로 1차 안전값은 낮게 둔다.
        if area / page_area > 0.18:
            return False
        return True

    def _local_detector_auto_input_size(self, w, h):
        """comic_text_detector 모델 입력 크기를 페이지 크기에 맞춰 자동 선택한다.

        여기서 말하는 input_size는 원본 이미지 크기가 아니라 detector가 내부적으로
        이미지를 letterbox 리사이즈할 때 쓰는 추론 캔버스 크기다. 결과 좌표는 detector가
        다시 원본 이미지 좌표로 되돌려주므로, 사용자가 페이지마다 직접 맞출 값이 아니다.
        """
        try:
            configured = getattr(Config, "LOCAL_PADDLE_MASK_INPUT_SIZE", "auto")
            if configured is None:
                configured = "auto"
            configured_s = str(configured).strip().lower()
            if configured_s and configured_s not in ("auto", "자동"):
                value = int(float(configured_s))
                # comic_text_detector는 stride 64 계열이므로 64 배수로 정리한다.
                value = max(512, min(2048, int(round(value / 64.0)) * 64))
                return value
        except Exception:
            pass

        max_side = max(int(w or 0), int(h or 0))
        # 너무 크게 잡으면 CPU 환경에서 재분석이 무거워지므로 안전한 단계값만 사용한다.
        if max_side >= 3000:
            return 1536
        if max_side >= 2000:
            return 1280
        return 1024

    def _normalize_detector_source_mask(self, source_mask, w, h):
        """comic_text_detector의 raw/refined mask를 원본 크기 단일 채널 0/255 마스크로 정규화한다."""
        if source_mask is None:
            return None
        try:
            arr = np.asarray(source_mask)
            if arr.ndim == 3:
                arr = cv2.cvtColor(arr, cv2.COLOR_BGR2GRAY)
            if arr.shape[:2] != (int(h), int(w)):
                arr = cv2.resize(arr, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
            arr = np.where(arr > 0, 255, 0).astype(np.uint8)
            if cv2.countNonZero(arr) <= 0:
                return None
            return arr
        except Exception:
            return None

    def _polygon_to_mask(self, pts, w, h, *, clamp_box=None):
        """line polygon을 이미지 범위 안으로 정리한 뒤 마스크와 polygon 배열을 만든다."""
        if not pts or len(pts) < 3:
            return None, None
        if clamp_box is not None:
            x1, y1, x2, y2 = clamp_box
        else:
            x1, y1, x2, y2 = 0, 0, int(w) - 1, int(h) - 1
        poly = []
        for x, y in pts:
            px = max(x1, min(x2, int(round(float(x)))))
            py = max(y1, min(y2, int(round(float(y)))))
            poly.append([px, py])
        arr = np.array(poly, dtype=np.int32)
        if arr.shape[0] < 3 or abs(cv2.contourArea(arr)) < 4:
            return None, None
        line_mask = np.zeros((int(h), int(w)), dtype=np.uint8)
        cv2.fillPoly(line_mask, [arr], 255)
        return line_mask, arr

    def _close_line_mask_component(self, clipped_mask, poly_arr, w, h, *, close_px=0):
        """line polygon 안에서만 detector 문자 마스크를 원본 크기로 되돌린다.

        v2.1.0 Local detector 테스트에서는 내부 보정 확장값을 두지 않는다.
        실제 작업 마스크의 확장은 옵션 > 분석 마스크 확장 비율 설정으로만 적용한다.
        """
        try:
            if clipped_mask is None or cv2.countNonZero(clipped_mask) <= 0:
                return None
            x, y, ww, hh = cv2.boundingRect(poly_arr)
            x = max(0, min(int(w) - 1, x))
            y = max(0, min(int(h) - 1, y))
            ww = max(1, min(int(w) - x, ww))
            hh = max(1, min(int(h) - y, hh))
            crop = clipped_mask[y:y + hh, x:x + ww].copy()
            if crop.size <= 0 or cv2.countNonZero(crop) <= 0:
                return None

            close_px = max(0, int(close_px or 0))
            if close_px > 0:
                # 현재 close_px는 내부 기본값으로 쓰지 않는다.
                # 향후 필요할 경우 옵션 > 분석 마스크 확장 비율 또는 별도 고급 옵션과 연결할 수 있도록 함수만 남긴다.
                if hh >= ww * 1.35:
                    kx = max(1, min(7, close_px * 2 + 1))
                    ky = max(3, min(21, close_px * 4 + 1))
                elif ww >= hh * 1.35:
                    kx = max(3, min(21, close_px * 4 + 1))
                    ky = max(1, min(7, close_px * 2 + 1))
                else:
                    kx = ky = max(3, min(15, close_px * 2 + 1))
                kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kx, ky))
                crop = cv2.morphologyEx(crop, cv2.MORPH_CLOSE, kernel, iterations=1)

            out = np.zeros((int(h), int(w)), dtype=np.uint8)
            out[y:y + hh, x:x + ww] = crop
            return out
        except Exception:
            return None

    def _create_detector_candidate_mask(self, blocks, w, h, *, source_mask=None):
        """comic_text_detector 후보를 YSB용 안전 마스크로 만든다.

        v2: raw/refined segmentation mask를 그대로 쓰지 않고, block/line 후보로 게이트를 건다.
        - line polygon이 있으면 source mask를 line 안에서만 잘라서 문자 모양에 가깝게 합친다.
        - source mask가 없거나 line 내부 픽셀이 비어 있으면 line polygon 채움으로만 fallback한다.
        - line이 없는 block은 bbox 전체보다 source mask∩bbox를 우선 사용한다.
        """
        mask = np.zeros((int(h), int(w)), dtype=np.uint8)
        used_blocks = 0
        used_lines = 0
        used_line_merged = 0
        fallback_lines = 0

        src = self._normalize_detector_source_mask(source_mask, w, h)
        # 내부 확장/closing 기본값은 두지 않는다.
        # 실제 마스크 확장은 옵션 > 분석 마스크 확장 비율 설정으로만 처리한다.
        close_px = 0

        for block in blocks or []:
            bbox = getattr(block, 'bbox', None) or (0, 0, 0, 0)
            box = self._clamp_detector_box(bbox, w, h)
            if box is None or not self._detector_block_is_reasonable(box, w, h):
                continue

            x1, y1, x2, y2 = box
            block_line_count = 0
            block_used_any = False

            for line in getattr(block, 'lines', []) or []:
                pts = getattr(line, 'polygon', None) or []
                line_region, arr = self._polygon_to_mask(pts, w, h, clamp_box=box)
                if line_region is None or arr is None:
                    continue

                line_mask_to_add = None
                if src is not None:
                    clipped = cv2.bitwise_and(src, line_region)
                    if cv2.countNonZero(clipped) >= 4:
                        line_mask_to_add = self._close_line_mask_component(clipped, arr, w, h, close_px=close_px)
                        if line_mask_to_add is not None and cv2.countNonZero(line_mask_to_add) > 0:
                            # closing/dilation이 line 영역 밖으로 번지지 않도록 다시 한 번 게이트한다.
                            line_mask_to_add = cv2.bitwise_and(line_mask_to_add, line_region)
                            used_line_merged += 1

                if line_mask_to_add is None or cv2.countNonZero(line_mask_to_add) <= 0:
                    # source mask가 비어 있는 줄은 이전 안전 방식으로 fallback한다.
                    # detector가 line을 잡았다는 사실은 활용하되, raw mask 전체 오염은 사용하지 않는다.
                    line_mask_to_add = line_region
                    fallback_lines += 1

                mask = cv2.bitwise_or(mask, line_mask_to_add)
                block_line_count += 1
                block_used_any = True

            if block_line_count <= 0:
                block_mask_to_add = None
                if src is not None:
                    bbox_region = np.zeros((int(h), int(w)), dtype=np.uint8)
                    cv2.rectangle(bbox_region, (x1, y1), (max(x1, x2 - 1), max(y1, y2 - 1)), 255, thickness=-1)
                    clipped = cv2.bitwise_and(src, bbox_region)
                    if cv2.countNonZero(clipped) >= 4:
                        # line 정보가 없는 block은 bbox 안의 문자 segmentation만 사용한다.
                        block_mask_to_add = clipped
                if block_mask_to_add is None:
                    # 마지막 fallback. line도 source mask도 없을 때만 bbox를 쓴다.
                    block_mask_to_add = np.zeros((int(h), int(w)), dtype=np.uint8)
                    cv2.rectangle(block_mask_to_add, (x1, y1), (max(x1, x2 - 1), max(y1, y2 - 1)), 255, thickness=-1)
                mask = cv2.bitwise_or(mask, block_mask_to_add)
                block_used_any = True
            else:
                used_lines += block_line_count

            if block_used_any:
                used_blocks += 1

        stats = {
            "used_blocks": int(used_blocks),
            "used_lines": int(used_lines),
            "used_line_merged": int(used_line_merged),
            "fallback_lines": int(fallback_lines),
        }
        return mask, stats

    def _estimate_detector_mask_expand_px(self, blocks, w, h, *, ratio=0.0, min_px=0):
        """기존 '분석 마스크 확장 비율' 설정을 Local detector 마스크에 적용하기 위한 px 산출.

        일반 API OCR 경로는 OCR 조각의 stroke_size를 기준으로 확장량을 잡는다.
        Local detector 경로는 OCR 조각이 아직 없으므로, detector line polygon/bbox의 짧은 변을
        stroke 후보로 보고 같은 ratio/min_px 규칙을 적용한다.
        """
        try:
            ratio = max(0.0, float(ratio or 0.0))
        except Exception:
            ratio = 0.0
        try:
            min_px = max(0, int(min_px or 0))
        except Exception:
            min_px = 0

        if ratio <= 0 and min_px <= 0:
            return 0

        samples = []
        for block in blocks or []:
            block_has_line = False
            for line in getattr(block, 'lines', []) or []:
                pts = getattr(line, 'polygon', None) or []
                if len(pts) < 3:
                    continue
                try:
                    arr = np.array(pts, dtype=np.int32).reshape((-1, 1, 2))
                    _x, _y, rw, rh = cv2.boundingRect(arr)
                    stroke = min(rw, rh) if min(rw, rh) > 0 else max(rw, rh)
                    if stroke > 0:
                        samples.append(float(stroke))
                        block_has_line = True
                except Exception:
                    continue
            if not block_has_line:
                try:
                    box = self._clamp_detector_box(getattr(block, 'bbox', None), w, h)
                    if box is not None:
                        x1, y1, x2, y2 = box
                        rw = max(1, x2 - x1)
                        rh = max(1, y2 - y1)
                        stroke = min(rw, rh) if min(rw, rh) > 0 else max(rw, rh)
                        if stroke > 0:
                            samples.append(float(stroke))
                except Exception:
                    continue

        if samples:
            # 평균보다 중앙값이 큰 효과음/긴 말풍선에 덜 흔들린다.
            stroke_ref = float(np.median(np.array(samples, dtype=np.float32)))
        else:
            stroke_ref = 0.0

        px = int(stroke_ref * ratio) if ratio > 0 else 0
        if min_px > 0:
            px = max(px, min_px)
        return max(0, int(px))

    def _expand_detector_analysis_mask(self, base_mask, blocks, w, h, *, ratio=0.0, min_px=0):
        """Local detector 기준 마스크에 기존 분석 마스크 확장 설정을 적용한다.

        - 텍스트 마스크는 Config.MERGE_RATIO / MERGE_MIN_STROKE_PX
        - 페인팅 마스크는 Config.INPAINT_RATIO / MIN_STROKE_PX
        를 각각 사용한다.
        API 관리에는 별도 마스크 확장값을 두지 않는다.
        """
        if base_mask is None:
            return np.zeros((int(h), int(w)), dtype=np.uint8)
        try:
            mask = np.asarray(base_mask).copy()
            if mask.ndim == 3:
                mask = cv2.cvtColor(mask, cv2.COLOR_BGR2GRAY)
            if mask.shape[:2] != (int(h), int(w)):
                mask = cv2.resize(mask, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
            mask = np.where(mask > 0, 255, 0).astype(np.uint8)
        except Exception:
            return np.zeros((int(h), int(w)), dtype=np.uint8)

        expand_px = self._estimate_detector_mask_expand_px(blocks, w, h, ratio=ratio, min_px=min_px)
        if expand_px <= 0:
            return mask

        kernel_size = expand_px * 2 + 1
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (kernel_size, kernel_size))
        return cv2.dilate(mask, kernel, iterations=1)

    def _normalize_binary_work_mask(self, mask, w, h):
        """YSB 작업 마스크를 원본 크기 0/255 단일 채널로 정규화한다."""
        if mask is None:
            return np.zeros((int(h), int(w)), dtype=np.uint8)
        try:
            src = np.asarray(mask)
            if src.ndim == 3:
                src = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
            if src.shape[:2] != (int(h), int(w)):
                src = cv2.resize(src, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
            return np.where(src > 0, 255, 0).astype(np.uint8)
        except Exception:
            return np.zeros((int(h), int(w)), dtype=np.uint8)

    def _rect_mask_for_group(self, group, w, h):
        """group의 현재 rect/vertices를 작은 마스크로 만든다."""
        region = np.zeros((int(h), int(w)), dtype=np.uint8)
        try:
            x, y, rw, rh = [int(round(float(v))) for v in group.get('rect', [0, 0, 0, 0])[:4]]
            x1 = max(0, min(int(w), x))
            y1 = max(0, min(int(h), y))
            x2 = max(0, min(int(w), x + max(0, rw)))
            y2 = max(0, min(int(h), y + max(0, rh)))
            if x2 > x1 and y2 > y1:
                cv2.rectangle(region, (x1, y1), (x2 - 1, y2 - 1), 255, thickness=-1)
        except Exception:
            pass

        for v_list in group.get('vertices_list', []) or []:
            try:
                pts = np.array(v_list, dtype=np.int32).reshape((-1, 1, 2))
                if pts.shape[0] >= 3:
                    cv2.fillPoly(region, [pts], 255)
            except Exception:
                continue
        return region

    def _align_local_groups_to_text_mask(self, grouped_data, text_mask, w, h):
        """LOCAL OCR 분석 박스/OCR crop 기준을 실제 텍스트 마스크 기준으로 보정한다.

        Local detector/OCR 경로의 분석 영역은 detector 글자 bbox가 아니라 실제로 생성된
        텍스트 마스크의 연결 성분을 기준으로 만든다. OCR이 일부 실패하거나 detector block이
        좁게 잡혀도, 마스크가 존재하면 그 마스크 성분은 반드시 하나의 텍스트 영역으로 표시되어야 한다.
        """
        mask = self._normalize_binary_work_mask(text_mask, w, h)
        if cv2.countNonZero(mask) <= 0:
            return grouped_data or []

        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        components = []
        for cnt in contours or []:
            if cnt is None or abs(cv2.contourArea(cnt)) < 1:
                continue
            x, y, rw, rh = cv2.boundingRect(cnt)
            if rw <= 0 or rh <= 0:
                continue
            comp_mask = np.zeros((int(h), int(w)), dtype=np.uint8)
            cv2.drawContours(comp_mask, [cnt], -1, 255, thickness=-1)
            components.append({
                'rect': [int(x), int(y), int(rw), int(rh)],
                'mask': comp_mask,
                'area': int(cv2.countNonZero(comp_mask)),
            })
        if not components:
            return grouped_data or []

        # 각 기존 detector/OCR 그룹의 영역을 미리 계산한다. 다만 최종 분석 영역은
        # 기존 그룹 수가 아니라 텍스트 마스크 연결 성분 수를 기준으로 새로 만든다.
        group_regions = []
        for group in grouped_data or []:
            try:
                group_regions.append((group, self._rect_mask_for_group(group, w, h)))
            except Exception:
                group_regions.append((group, np.zeros((int(h), int(w)), dtype=np.uint8)))

        updated = []
        matched_groups = set()
        for comp_idx, comp in enumerate(components):
            best_group = None
            best_group_idx = -1
            best_overlap = 0
            for group_idx, (group, group_region) in enumerate(group_regions):
                try:
                    ov = cv2.countNonZero(cv2.bitwise_and(group_region, comp['mask']))
                except Exception:
                    ov = 0
                if int(ov) > best_overlap:
                    best_overlap = int(ov)
                    best_group = group
                    best_group_idx = group_idx

            if best_group is not None and best_overlap > 0:
                item = copy.deepcopy(best_group)
                matched_groups.add(best_group_idx)
            else:
                item = {
                    'id': int(comp_idx),
                    'text': '',
                    'translated_text': '',
                    'ocr_items': [],
                    'ocr_items_all': [],
                    'ruby_ocr_items': [],
                    'ocr_lang': 'local_mask',
                    'avg_stroke': 0.0,
                    'use_inpaint': True,
                    'x_off': 0,
                    'y_off': 0,
                    'local_detector_only': True,
                    'detector_engine': 'text_mask_component',
                    'detector_group_count': 0,
                }

            x, y, rw, rh = comp['rect']
            rect = [int(x), int(y), int(rw), int(rh)]
            try:
                avg_stroke = float(item.get('avg_stroke', 0) or 0)
            except Exception:
                avg_stroke = 0.0
            if avg_stroke <= 0:
                avg_stroke = max(1.0, min(float(rw), float(rh)) * 0.1)

            item['rect'] = rect
            item['mask_rect'] = rect
            item['text_mask_rect'] = rect
            item['ocr_crop_rect'] = rect
            item['local_mask_aligned_rect'] = True
            item['avg_stroke'] = avg_stroke
            # 분석도/선택 영역/최종 인페인팅 클리핑 기준도 실제 텍스트 마스크 성분의 외접 사각형으로 통일한다.
            item['vertices_list'] = [[[int(x), int(y)], [int(x + rw), int(y)], [int(x + rw), int(y + rh)], [int(x), int(y + rh)]]]
            updated.append(item)

        print(
            f">>> [Local OCR] text-mask component based OCR/analysis rects: "
            f"groups={len(updated)}, components={len(components)}, matched_groups={len(matched_groups)}"
        )
        return self._organize_blocks(updated) if updated else []

    def _create_grouped_data_analysis_mask(self, grouped_data, w, h, *, ratio=0.0, min_px=0):
        """분석 데이터(vertices_list)를 기준으로 텍스트/페인트 실제 작업 마스크를 만든다.

        Local detector 재분석에서는 기존 데이터와 새 detector 데이터를 섞어 최종 data를 만든다.
        이때 화면에 보이는 텍스트/페인트 마스크가 실제 작업 마스크와 다르면 수정이 불가능해지므로,
        최종 grouped_data에서 각 설정값을 적용해 실제 표시/작업 마스크를 다시 만든다.
        """
        mask = np.zeros((int(h), int(w)), dtype=np.uint8)
        try:
            ratio = max(0.0, float(ratio or 0.0))
        except Exception:
            ratio = 0.0
        try:
            min_px = max(0, int(min_px or 0))
        except Exception:
            min_px = 0

        for group in grouped_data or []:
            try:
                avg_stroke = float(group.get('avg_stroke', 0) or 0)
            except Exception:
                avg_stroke = 0.0
            pad = int(avg_stroke * ratio) if ratio > 0 else 0
            if min_px > 0:
                pad = max(pad, min_px)

            for v_list in group.get('vertices_list', []) or []:
                try:
                    pts = np.array(v_list, np.int32).reshape((-1, 1, 2))
                    if pts.shape[0] < 3 or abs(cv2.contourArea(pts)) < 1:
                        continue
                    cv2.fillPoly(mask, [pts], 255)
                    if pad > 0:
                        cv2.polylines(mask, [pts], True, 255, thickness=pad * 2, lineType=cv2.LINE_AA)
                except Exception:
                    continue
        return mask

    def _detector_blocks_to_grouped_data_by_mask(self, blocks, w, h, *, grouping_mask=None, source_mask=None):
        """comic_text_detector block들을 기존 분석 data 형식으로 변환한다.

        단순히 block 하나당 박스 하나를 만들면, 실제 텍스트/페인트 마스크가 서로 붙었는데도
        분석도에는 여러 박스로 남는다. 기존 API OCR 경로처럼 마스크가 연결된 후보는 하나의
        분석 박스로 합치기 위해, 최종 텍스트 마스크의 연결 성분을 기준으로 block을 union한다.
        """
        blocks = list(blocks or [])
        if not blocks:
            return []

        n = len(blocks)
        parent = list(range(n))

        def find(i):
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        def union(a, b):
            ra, rb = find(a), find(b)
            if ra != rb:
                parent[rb] = ra

        mask_for_grouping = None
        if grouping_mask is not None:
            try:
                mask_for_grouping = np.asarray(grouping_mask)
                if mask_for_grouping.ndim == 3:
                    mask_for_grouping = cv2.cvtColor(mask_for_grouping, cv2.COLOR_BGR2GRAY)
                if mask_for_grouping.shape[:2] != (int(h), int(w)):
                    mask_for_grouping = cv2.resize(mask_for_grouping, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
                mask_for_grouping = np.where(mask_for_grouping > 0, 255, 0).astype(np.uint8)
            except Exception:
                mask_for_grouping = None

        if mask_for_grouping is not None and cv2.countNonZero(mask_for_grouping) > 0 and n > 1:
            block_masks = []
            for block in blocks:
                try:
                    bm, _stats = self._create_detector_candidate_mask([block], w, h, source_mask=source_mask)
                    block_masks.append(bm)
                except Exception:
                    block_masks.append(None)

            contours, _ = cv2.findContours(mask_for_grouping, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for cnt in contours or []:
                if cnt is None or cv2.contourArea(cnt) < 1:
                    continue
                component = np.zeros((int(h), int(w)), dtype=np.uint8)
                cv2.drawContours(component, [cnt], -1, 255, thickness=-1)
                included = []
                for idx, bm in enumerate(block_masks):
                    if bm is None:
                        continue
                    try:
                        if cv2.countNonZero(cv2.bitwise_and(bm, component)) > 0:
                            included.append(idx)
                    except Exception:
                        continue
                if len(included) >= 2:
                    first = included[0]
                    for other in included[1:]:
                        union(first, other)

        buckets = {}
        for idx, block in enumerate(blocks):
            buckets.setdefault(find(idx), []).append(block)

        grouped_data = []
        for group_blocks in buckets.values():
            item = self._detector_blocks_group_to_group_data(group_blocks, len(grouped_data))
            if item is not None:
                grouped_data.append(item)

        return self._organize_blocks(grouped_data) if grouped_data else []

    def _detector_blocks_group_to_group_data(self, blocks, index=0):
        """여러 detector block을 하나의 분석 박스로 합친다."""
        blocks = list(blocks or [])
        if not blocks:
            return None

        vertices_list = []
        xs = []
        ys = []
        stroke_samples = []

        for block in blocks:
            box = self._clamp_detector_box(getattr(block, 'bbox', None), 10**9, 10**9)
            if box is not None:
                x1, y1, x2, y2 = box
                xs.extend([x1, x2])
                ys.extend([y1, y2])

            line_count = 0
            for line in getattr(block, "lines", []) or []:
                pts = getattr(line, "polygon", None) or []
                if len(pts) >= 3:
                    poly = []
                    for x, y in pts:
                        try:
                            x = int(round(float(x)))
                            y = int(round(float(y)))
                            poly.append([x, y])
                            xs.append(x)
                            ys.append(y)
                        except Exception:
                            pass
                    if len(poly) >= 3:
                        vertices_list.append(poly)
                        line_count += 1
                        try:
                            arr = np.array(poly, dtype=np.int32).reshape((-1, 1, 2))
                            _x, _y, rw, rh = cv2.boundingRect(arr)
                            stroke_samples.append(float(min(rw, rh) if min(rw, rh) > 0 else max(rw, rh)))
                        except Exception:
                            pass

            if line_count <= 0 and box is not None:
                x1, y1, x2, y2 = box
                vertices_list.append([[x1, y1], [x2, y1], [x2, y2], [x1, y2]])
                stroke_samples.append(float(min(max(1, x2 - x1), max(1, y2 - y1))))

        if not xs or not ys or not vertices_list:
            return None

        x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
        rw = max(1, int(x2 - x1))
        rh = max(1, int(y2 - y1))
        avg_stroke = float(np.median(np.array(stroke_samples, dtype=np.float32))) if stroke_samples else max(1.0, min(rw, rh) * 0.1)

        return {
            'id': int(index),
            'text': '',
            'translated_text': '',
            'rect': [int(x1), int(y1), rw, rh],
            'vertices_list': vertices_list,
            'ocr_items': [],
            'ocr_items_all': [],
            'ruby_ocr_items': [],
            'ocr_lang': 'local_mask',
            'avg_stroke': avg_stroke,
            'use_inpaint': True,
            'x_off': 0,
            'y_off': 0,
            'local_detector_only': True,
            'detector_engine': 'comic_text_detector',
            'detector_group_count': len(blocks),
        }

    def _detector_block_to_group(self, block, index=0):
        """comic_text_detector block을 기존 분석 데이터 형식으로 변환한다.

        현재 단계는 OCR 문자 인식 전 마스크 검증용이므로 text는 비워둔다.
        대신 rect/vertices_list/use_inpaint를 채워 분석도와 마스크 슬롯에서 바로 확인할 수 있게 한다.
        """
        try:
            x1, y1, x2, y2 = [int(v) for v in block.bbox[:4]]
        except Exception:
            x1 = y1 = x2 = y2 = 0
        if x2 < x1:
            x1, x2 = x2, x1
        if y2 < y1:
            y1, y2 = y2, y1
        rw = max(1, x2 - x1)
        rh = max(1, y2 - y1)

        vertices_list = []
        for line in getattr(block, "lines", []) or []:
            pts = getattr(line, "polygon", None) or []
            if len(pts) >= 3:
                vertices_list.append([[int(x), int(y)] for x, y in pts])
        if not vertices_list:
            vertices_list = [[[x1, y1], [x2, y1], [x2, y2], [x1, y2]]]

        font_size = getattr(block, "font_size", None)
        try:
            avg_stroke = float(font_size) if font_size is not None and float(font_size) > 0 else max(1.0, min(rw, rh) * 0.1)
        except Exception:
            avg_stroke = max(1.0, min(rw, rh) * 0.1)

        return {
            'id': int(index),
            'text': '',
            'translated_text': '',
            'rect': [x1, y1, rw, rh],
            'vertices_list': vertices_list,
            'ocr_items': [],
            'ocr_items_all': [],
            'ruby_ocr_items': [],
            'ocr_lang': 'local_mask',
            'avg_stroke': avg_stroke,
            'use_inpaint': True,
            'x_off': 0,
            'y_off': 0,
            'local_detector_only': True,
            'detector_engine': 'comic_text_detector',
        }


    def _crop_group_for_paddle_ocr(self, ori_img, group, w, h):
        """PaddleOCR 입력 crop을 만든다.

        Local detector 경로에서는 detector 문자 bbox보다 실제 텍스트 마스크 기준 rect가
        더 믿을 만하다. _align_local_groups_to_text_mask()가 넣어둔 ocr_crop_rect를 우선 사용한다.
        """
        rect_source = group.get('ocr_crop_rect') or group.get('text_mask_rect') or group.get('mask_rect') or group.get('rect', [0, 0, 1, 1])
        try:
            x, y, rw, rh = [int(round(float(v))) for v in rect_source[:4]]
        except Exception:
            return None, 0, 0
        if rw <= 0 or rh <= 0:
            return None, 0, 0
        try:
            stroke = float(group.get('avg_stroke', 0) or 0)
        except Exception:
            stroke = 0.0

        # 텍스트 마스크 rect는 이미 사용자가 설정한 확장값이 반영된 작업 영역이다.
        # OCR에는 가장자리 잘림 방지를 위한 작은 여백만 추가한다.
        if group.get('ocr_crop_rect') or group.get('text_mask_rect') or group.get('mask_rect'):
            pad = max(2, min(8, int(stroke * 0.15)))
        else:
            pad = max(4, int(stroke * 0.35))
        x1 = max(0, x - pad)
        y1 = max(0, y - pad)
        x2 = min(int(w), x + rw + pad)
        y2 = min(int(h), y + rh + pad)
        if x2 <= x1 or y2 <= y1:
            return None, 0, 0
        crop = ori_img[y1:y2, x1:x2].copy()
        if crop.size <= 0:
            return None, 0, 0
        return crop, x1, y1

    def _paddle_ocr_lines_to_raw_items(self, lines, offset_x=0, offset_y=0, *, locale='ja'):
        """PaddleOCR wrapper 결과를 YSB raw_items 형식으로 변환한다."""
        raw_items = []
        for order_index, line in enumerate(lines or []):
            try:
                text = str(line.get('text', '') or '').strip()
                if not text:
                    continue
                pts = []
                for p in line.get('points', []) or []:
                    try:
                        pts.append([int(p[0]) + int(offset_x), int(p[1]) + int(offset_y)])
                    except Exception:
                        pass
                if len(pts) < 3:
                    continue
                pts_arr = np.array(pts, dtype=np.int32)
                rect_rot = cv2.minAreaRect(pts_arr)
                (_cx, _cy), (rw, rh), _angle = rect_rot
                stroke_size = min(rw, rh) if min(rw, rh) > 0 else max(rw, rh)
                bx, by, bw, bh = cv2.boundingRect(pts_arr)
                compact = ''.join(ch for ch in text if not ch.isspace())
                raw_items.append({
                    'text': text,
                    'vertices': pts,
                    'stroke_size': float(stroke_size or 0),
                    'cx': float(bx + bw / 2),
                    'cy': float(by + bh / 2),
                    'rect': [int(bx), int(by), int(bw), int(bh)],
                    'char_count': max(1, len(compact)),
                    'source_provider': 'local_paddle_ocr',
                    'locale': str(locale or ''),
                    'detected_break': '',
                    'order_index': order_index,
                    'confidence': float(line.get('confidence', 0.0) or 0.0),
                })
            except Exception:
                continue
        return self._dedupe_ocr_items(raw_items)

    def _apply_full_page_paddle_ocr_fallback(self, ori_img, grouped_data, paddle_engine, lang, device):
        """Crop OCR가 모두 빈 결과일 때 전체 페이지 OCR 결과를 detector 그룹에 배정한다.

        PaddleOCR은 너무 타이트한 세로 crop보다 전체 페이지/넓은 문맥에서 더 잘 읽는
        경우가 있다. 특히 frozen Local 빌드에서 crop 단위 인식이 빈 결과로 떨어지면,
        detector 박스는 유지한 채 전체 페이지 OCR 조각을 각 박스에 나눠 넣어 원문 칸이
        통째로 비는 상황을 막는다.
        """
        if ori_img is None or not grouped_data:
            return grouped_data or [], 0, ''
        try:
            from ysb.engines.ocr.base import OcrRequest
            res = paddle_engine.run(OcrRequest(
                image_path='',
                language=lang,
                options={
                    'image_bgr': ori_img,
                    'device': device,
                    'scale': 1.5,
                },
            ))
            if not res.ok:
                return grouped_data, 0, str(res.error or '')
            raw_items = self._paddle_ocr_lines_to_raw_items(res.lines, 0, 0, locale=lang)
            if not raw_items:
                return grouped_data, 0, ''

            assigned = []
            changed = 0
            for group in grouped_data or []:
                item = copy.deepcopy(group)
                if str(item.get('text', '') or '').strip():
                    assigned.append(item)
                    continue
                try:
                    x, y, rw, rh = [int(round(float(v))) for v in item.get('rect', [0, 0, 1, 1])[:4]]
                except Exception:
                    assigned.append(item)
                    continue
                try:
                    stroke = float(item.get('avg_stroke', 0) or 0)
                except Exception:
                    stroke = 0.0
                pad = max(8, int(stroke * 0.8), int(min(max(rw, 1), max(rh, 1)) * 0.08))
                x1, y1 = x - pad, y - pad
                x2, y2 = x + rw + pad, y + rh + pad
                hits = []
                for raw in raw_items:
                    try:
                        cx = float(raw.get('cx', 0))
                        cy = float(raw.get('cy', 0))
                    except Exception:
                        continue
                    if x1 <= cx <= x2 and y1 <= cy <= y2:
                        hits.append(raw)

                if not hits:
                    assigned.append(item)
                    continue

                main_text_items, ruby_items = self._split_main_and_ruby_items(hits)
                new_text = self._manga_sort(main_text_items).strip()
                if not new_text:
                    assigned.append(item)
                    continue

                item['text'] = new_text
                item['ocr_items'] = self._make_ocr_items_payload(main_text_items)
                item['ocr_items_all'] = self._make_ocr_items_payload(hits)
                item['ruby_ocr_items'] = self._make_ocr_items_payload(ruby_items)
                item['ocr_lang'] = lang
                item['local_detector_only'] = False
                item['ocr_engine'] = 'paddleocr_fullpage_fallback'
                item['detector_engine'] = item.get('detector_engine') or 'comic_text_detector'
                try:
                    item['avg_stroke'] = float(np.median(np.array([it.get('stroke_size', 0) for it in hits], dtype=np.float32)))
                except Exception:
                    pass
                changed += 1
                assigned.append(item)

            return assigned, changed, ''
        except Exception as e:
            return grouped_data, 0, str(e)

    def _apply_local_paddle_ocr_to_groups(self, ori_img, grouped_data):
        """Local detector가 만든 영역을 PaddleOCR로 읽어 text/ocr_items를 채운다.

        마스크와 박스 기준은 comic_text_detector 결과를 유지하고, PaddleOCR은 문자 인식만 담당한다.
        인식 실패 시 기존 text/translated_text는 보존한다.
        """
        if ori_img is None or not grouped_data:
            return grouped_data or []
        h, w = ori_img.shape[:2]
        lang = self._current_ocr_language()
        device = str(getattr(Config, 'LOCAL_PADDLE_MASK_DEVICE', 'auto') or 'auto')

        try:
            from ysb.engines.ocr.base import OcrRequest
            from ysb.engines.ocr.paddle_ocr import PaddleOcrEngine
            paddle_engine = PaddleOcrEngine(language=lang, device=device)
        except Exception as e:
            print(f">>> [Local OCR] PaddleOCR 준비 실패: {e}")
            return grouped_data

        updated = []
        ok_count = 0
        err_count = 0
        sample_errors = []
        for group in grouped_data or []:
            item = copy.deepcopy(group)
            crop, ox, oy = self._crop_group_for_paddle_ocr(ori_img, item, w, h)
            if crop is None:
                updated.append(item)
                continue
            try:
                res = paddle_engine.run(OcrRequest(
                    image_path='',
                    language=lang,
                    options={
                        'image_bgr': crop,
                        'device': device,
                        # 만화 작은 글자/세로문은 2배 확대가 초반 안정성이 좋다.
                        'scale': 2.0,
                    },
                ))
                if not res.ok:
                    err_count += 1
                    item['local_paddle_ocr_error'] = res.error
                    if res.error and len(sample_errors) < 3:
                        sample_errors.append(str(res.error))
                    updated.append(item)
                    continue

                raw_items = self._paddle_ocr_lines_to_raw_items(res.lines, ox, oy, locale=lang)
                if not raw_items:
                    updated.append(item)
                    continue

                main_text_items, ruby_items = self._split_main_and_ruby_items(raw_items)
                new_text = self._manga_sort(main_text_items).strip()
                old_text = str(item.get('text', '') or '').strip()
                if new_text:
                    item['text'] = new_text
                    item['ocr_items'] = self._make_ocr_items_payload(main_text_items)
                    item['ocr_items_all'] = self._make_ocr_items_payload(raw_items)
                    item['ruby_ocr_items'] = self._make_ocr_items_payload(ruby_items)
                    item['ocr_lang'] = lang
                    item['local_detector_only'] = False
                    item['ocr_engine'] = 'paddleocr'
                    item['detector_engine'] = item.get('detector_engine') or 'comic_text_detector'
                    if old_text and old_text != new_text:
                        # 원문이 바뀌면 기존 번역은 더 이상 신뢰하기 어렵다.
                        item['translated_text'] = ''
                    try:
                        item['avg_stroke'] = float(np.median(np.array([it.get('stroke_size', 0) for it in raw_items], dtype=np.float32)))
                    except Exception:
                        pass
                    ok_count += 1
                updated.append(item)
            except Exception as e:
                err_count += 1
                item['local_paddle_ocr_error'] = str(e)
                if str(e) and len(sample_errors) < 3:
                    sample_errors.append(str(e))
                updated.append(item)

        if ok_count <= 0 and updated:
            fallback_updated, fallback_count, fallback_error = self._apply_full_page_paddle_ocr_fallback(
                ori_img, updated, paddle_engine, lang, device
            )
            if fallback_count > 0:
                updated = fallback_updated
                ok_count = fallback_count
                print(f">>> [Local OCR] PaddleOCR full-page fallback applied: ok={fallback_count}")
            elif fallback_error:
                print(f">>> [Local OCR] PaddleOCR full-page fallback failed: {fallback_error}")

        print(f">>> [Local OCR] PaddleOCR text recognition: ok={ok_count}, errors={err_count}, groups={len(updated)}")
        if sample_errors:
            print(f">>> [Local OCR] PaddleOCR sample errors: {' | '.join(sample_errors)}")
        return updated

    def _manga_ocr_lines_to_raw_items(self, lines, offset_x=0, offset_y=0, *, locale='ja'):
        """Convert Manga OCR recognition-only output to one YSB OCR item per crop."""
        raw_items = []
        for order_index, line in enumerate(lines or []):
            try:
                text = str(line.get('text', '') or '').strip()
                if not text:
                    continue
                pts = []
                for p in line.get('points', []) or []:
                    try:
                        pts.append([int(p[0]) + int(offset_x), int(p[1]) + int(offset_y)])
                    except Exception:
                        pass
                if len(pts) < 3:
                    continue
                pts_arr = np.array(pts, dtype=np.int32)
                bx, by, bw, bh = cv2.boundingRect(pts_arr)
                compact = ''.join(ch for ch in text if not ch.isspace())
                raw_items.append({
                    'text': text,
                    'vertices': pts,
                    'stroke_size': float(max(1, min(bw, bh) * 0.18)),
                    'cx': float(bx + bw / 2),
                    'cy': float(by + bh / 2),
                    'rect': [int(bx), int(by), int(bw), int(bh)],
                    'char_count': max(1, len(compact)),
                    'source_provider': 'local_manga_ocr',
                    'locale': str(locale or 'ja'),
                    'detected_break': '',
                    'order_index': order_index,
                    'confidence': float(line.get('confidence', 1.0) or 1.0),
                })
            except Exception:
                continue
        return self._dedupe_ocr_items(raw_items)

    def _apply_local_manga_ocr_to_groups(self, ori_img, grouped_data):
        """comic_text_detector 영역/마스크를 유지하고 Manga OCR로 crop 원문만 읽는다."""
        if ori_img is None or not grouped_data:
            return grouped_data or []
        h, w = ori_img.shape[:2]
        try:
            from ysb.engines.ocr.base import OcrRequest
            from ysb.engines.ocr.manga_ocr import MangaOcrEngine
            manga_engine = MangaOcrEngine(language='ja')
        except Exception as e:
            print(f">>> [Local OCR] Manga OCR 준비 실패: {e}")
            return grouped_data

        updated = []
        ok_count = 0
        err_count = 0
        sample_errors = []
        for group in grouped_data or []:
            item = copy.deepcopy(group)
            crop, ox, oy = self._crop_group_for_paddle_ocr(ori_img, item, w, h)
            if crop is None:
                updated.append(item)
                continue
            try:
                res = manga_engine.run(OcrRequest(
                    image_path='',
                    language='ja',
                    options={
                        'image_bgr': crop,
                        # manga-ocr는 말풍선/세로문 crop에서 확대 입력이 안정적인 편이다.
                        'scale': 2.0,
                    },
                ))
                if not res.ok:
                    err_count += 1
                    item['local_manga_ocr_error'] = res.error
                    if res.error and len(sample_errors) < 3:
                        sample_errors.append(str(res.error))
                    updated.append(item)
                    continue

                raw_items = self._manga_ocr_lines_to_raw_items(res.lines, ox, oy, locale='ja')
                new_text = ''
                if raw_items:
                    new_text = str(raw_items[0].get('text', '') or '').strip()
                old_text = str(item.get('text', '') or '').strip()
                if new_text:
                    item['text'] = new_text
                    item['ocr_items'] = self._make_ocr_items_payload(raw_items)
                    item['ocr_items_all'] = self._make_ocr_items_payload(raw_items)
                    item['ruby_ocr_items'] = []
                    item['ocr_lang'] = 'ja'
                    item['local_detector_only'] = False
                    item['ocr_engine'] = 'manga_ocr'
                    item['detector_engine'] = item.get('detector_engine') or 'comic_text_detector'
                    if old_text and old_text != new_text:
                        item['translated_text'] = ''
                    ok_count += 1
                updated.append(item)
            except Exception as e:
                err_count += 1
                item['local_manga_ocr_error'] = str(e)
                if str(e) and len(sample_errors) < 3:
                    sample_errors.append(str(e))
                updated.append(item)
        print(f">>> [Local OCR] Manga OCR text recognition: ok={ok_count}, errors={err_count}, groups={len(updated)}")
        if sample_errors:
            print(f">>> [Local OCR] Manga OCR sample errors: {' | '.join(sample_errors)}")
        return updated

    def _apply_current_local_ocr_engine_to_groups(self, ori_img, grouped_data):
        """Apply the single supported Local OCR reader.

        v2.1.0 Local OCR keeps only the stable path:
        comic_text_detector for masks/regions + PaddleOCR for text recognition.
        Experimental OCR readers tested earlier are intentionally removed from
        the regular Local build.
        """
        provider = str(getattr(Config, "OCR_PROVIDER", "local_paddle_ocr") or "local_paddle_ocr").strip().lower()
        if provider == "local_manga_ocr":
            return self._apply_local_manga_ocr_to_groups(ori_img, grouped_data)
        return self._apply_local_paddle_ocr_to_groups(ori_img, grouped_data)

    def analyze_image_local_paddle_mask(self, image_path, ori_img=None, analysis_mask=None):
        """LOCAL Paddle OCR 선택 시 실행되는 Local 분석 경로.

        comic_text_detector로 텍스트 영역/마스크를 만들고, PaddleOCR로
        각 영역의 원문을 읽는다.
        """
        print(f">>> [Local OCR] comic_text_detector 마스크 분석: {os.path.basename(image_path)}")

        if ori_img is None:
            img_array = np.fromfile(image_path, np.uint8)
            ori_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if ori_img is None:
            raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")
        h, w = ori_img.shape[:2]

        from ysb.engines.text_detection.base import TextDetectionRequest
        from ysb.engines.text_detection.manager import detect_with_default_engine

        input_size = self._local_detector_auto_input_size(w, h)
        device = str(getattr(Config, "LOCAL_PADDLE_MASK_DEVICE", "auto") or "auto")

        result = detect_with_default_engine(TextDetectionRequest(
            image_path=image_path,
            options={
                "input_size": input_size,
                "device": device,
                "save_masks": False,
                "keep_undetected_mask": True,
            },
        ))
        if not result.ok:
            raise ValueError(f"comic_text_detector 마스크 분석 실패: {result.error}")

        # 1순위 개선: detector의 raw/refined segmentation mask를 직접 쓰지 않는다.
        # raw mask는 머리카락·옷 주름·배경선까지 과하게 잡을 수 있으므로,
        # block/line 후보를 게이트로 삼은 안전 마스크만 YSB 마스크 슬롯에 넣는다.
        blocks = list(result.blocks or [])
        safe_blocks = [
            block for block in blocks
            if self._detector_block_is_reasonable(getattr(block, 'bbox', (0, 0, 0, 0)), w, h)
        ]
        if analysis_mask is not None:
            try:
                _am = np.asarray(analysis_mask)
                if _am.ndim == 3:
                    _am = cv2.cvtColor(_am, cv2.COLOR_BGR2GRAY)
                if _am.shape[:2] != (h, w):
                    _am = cv2.resize(_am, (w, h), interpolation=cv2.INTER_NEAREST)
                _am = np.where(_am > 0, 255, 0).astype(np.uint8)
                _filtered = []
                for block in safe_blocks:
                    box = self._clamp_detector_box(getattr(block, 'bbox', (0, 0, 0, 0)), w, h)
                    if not box:
                        continue
                    x1, y1, x2, y2 = box
                    if cv2.countNonZero(_am[y1:max(y1 + 1, y2 + 1), x1:max(x1 + 1, x2 + 1)]) > 0:
                        _filtered.append(block)
                safe_blocks = _filtered
                analysis_mask = _am
            except Exception:
                analysis_mask = None
        raw_payload = result.raw if isinstance(result.raw, dict) else {}
        source_mask = raw_payload.get("mask_refined")
        if source_mask is None:
            source_mask = raw_payload.get("mask")

        # detector는 확장 전 기준 후보 마스크만 만든다.
        # 실제 텍스트/페인트 마스크 확장은 옵션 > 분석 마스크 확장 비율 창의 값을 사용한다.
        # 같은 기능을 API 관리와 분석 옵션에 중복 배치하지 않기 위한 구조다.
        base_mask, base_stats = self._create_detector_candidate_mask(
            safe_blocks, w, h, source_mask=source_mask
        )
        if analysis_mask is not None and base_mask is not None:
            base_mask = cv2.bitwise_and(base_mask, analysis_mask)

        mask_merge = self._expand_detector_analysis_mask(
            base_mask, safe_blocks, w, h,
            ratio=getattr(Config, 'MERGE_RATIO', 0.2),
            min_px=getattr(Config, 'MERGE_MIN_STROKE_PX', 5),
        )
        mask_inpaint = self._expand_detector_analysis_mask(
            base_mask, safe_blocks, w, h,
            ratio=getattr(Config, 'INPAINT_RATIO', 0.1),
            min_px=getattr(Config, 'MIN_STROKE_PX', 1),
        )
        if analysis_mask is not None:
            if mask_merge is not None:
                mask_merge = cv2.bitwise_and(mask_merge, analysis_mask)
            if mask_inpaint is not None:
                mask_inpaint = cv2.bitwise_and(mask_inpaint, analysis_mask)

        # 분석도 박스도 실제 텍스트 마스크의 연결 상태를 반영한다.
        # 가까운 텍스트 마스크가 확장 후 서로 붙으면 기존 API OCR 그룹화처럼 하나의 박스로 합친다.
        grouped_data = self._detector_blocks_to_grouped_data_by_mask(
            safe_blocks, w, h,
            grouping_mask=mask_merge,
            source_mask=source_mask,
        )
        grouped_data = self._align_local_groups_to_text_mask(grouped_data, mask_merge, w, h)
        grouped_data = self._apply_current_local_ocr_engine_to_groups(ori_img, grouped_data)

        merge_pixels = int(cv2.countNonZero(mask_merge)) if mask_merge is not None else 0
        inpaint_pixels = int(cv2.countNonZero(mask_inpaint)) if mask_inpaint is not None else 0
        print(
            f">>> [Local OCR] comic_text_detector blocks={len(grouped_data)}, "
            f"safe_blocks={base_stats.get('used_blocks', 0)}, "
            f"safe_lines={base_stats.get('used_lines', 0)}, "
            f"line_merged={base_stats.get('used_line_merged', 0)}, "
            f"fallback_lines={base_stats.get('fallback_lines', 0)}, "
            f"text_mask_pixels={merge_pixels}, paint_mask_pixels={inpaint_pixels}, "
            f"raw_mask=line_gated, expand=analysis_mask_settings, input_size={input_size}"
        )
        return ori_img, grouped_data, mask_merge, mask_inpaint

    def _ocr_image_region(self, img_bgr, offset_x=0, offset_y=0):
        """
        img_bgr 일부 영역을 임시 파일로 저장해서 CLOVA OCR 호출.
        OCR 좌표는 원본 이미지 기준 좌표로 보정해서 반환.
        """
        temp_path = f"temp_ocr_tile_{uuid.uuid4().hex}.jpg"

        try:
            cv2.imwrite(temp_path, img_bgr)

            provider = str(getattr(Config, "OCR_PROVIDER", "clova") or "clova").lower()

            if provider in ("local_paddle_ocr", "local_manga_ocr"):
                # Local OCR 경로는 전체 분석/마스크 기준 재분석에서 별도 처리한다.
                # 타일 OCR API 경로로 떨어지지 않도록 빈 OCR 결과를 반환한다.
                return []

            if provider == "google_vision":
                ocr_res = self._call_google_vision_ocr(temp_path)
                return self._google_vision_response_to_raw_items(ocr_res, offset_x, offset_y)

            ocr_res = self._call_clova_ocr(temp_path)

            raw_items = []

            if (
                ocr_res and
                'images' in ocr_res and
                len(ocr_res['images']) > 0 and
                ocr_res['images'][0].get('inferResult') == 'SUCCESS'
            ):
                for field in ocr_res['images'][0].get('fields', []):
                    text = field.get('inferText', '')
                    poly = field.get('boundingPoly', {}).get('vertices', [])

                    if not poly:
                        continue

                    # 타일 내부 좌표 → 원본 전체 좌표로 변환
                    pts = [
                        [int(p['x']) + offset_x, int(p['y']) + offset_y]
                        for p in poly
                    ]

                    pts_arr = np.array(pts)

                    rect_rot = cv2.minAreaRect(pts_arr)
                    (cx, cy), (rw, rh), angle = rect_rot

                    stroke_size = min(rw, rh) if min(rw, rh) > 0 else max(rw, rh)

                    bx, by, bw, bh = cv2.boundingRect(pts_arr)

                    raw_items.append({
                        'text': text,
                        'vertices': pts,
                        'stroke_size': stroke_size,
                        'cx': cx,
                        'cy': cy,
                        'rect': [bx, by, bw, bh],
                        'char_count': max(1, len(''.join(ch for ch in str(text or '') if not ch.isspace()))),
                        'source_provider': 'clova',
                        'locale': self._current_ocr_language(),
                        'detected_break': '',
                        'order_index': None,
                    })

            return raw_items

        finally:
            if os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except:
                    pass

    def _ocr_image_region_tiled(self, img_bgr, offset_x=0, offset_y=0):
        """
        긴 crop 영역도 CLOVA OCR 높이 제한에 걸리지 않도록 세로 분할해서 OCR.
        반환 좌표는 원본 전체 이미지 기준으로 보정됨.
        """
        h, w = img_bgr.shape[:2]

        tile_h = getattr(Config, "OCR_TILE_HEIGHT", 3000)
        overlap = getattr(Config, "OCR_TILE_OVERLAP", 250)

        # 짧으면 기존 단일 OCR
        if h <= tile_h:
            return self._ocr_image_region(img_bgr, offset_x, offset_y)

        print(f">>> [OCR Tile] 긴 재분석 영역 감지: {w}x{h}, tile={tile_h}, overlap={overlap}")

        raw_items = []
        y = 0
        tile_index = 0

        while y < h:
            y1 = y
            y2 = min(h, y + tile_h)

            crop = img_bgr[y1:y2, 0:w]

            print(f">>> [OCR Tile] 재분석 타일 {tile_index + 1}: y={offset_y + y1}~{offset_y + y2}")

            tile_items = self._ocr_image_region(
                crop,
                offset_x,
                offset_y + y1
            )

            # 겹침 구간 중복 방지
            if tile_index > 0:
                safe_top = offset_y + y1 + overlap // 2
                tile_items = [
                    item for item in tile_items
                    if item["cy"] >= safe_top
                ]

            raw_items.extend(tile_items)

            if y2 >= h:
                break

            y += tile_h - overlap
            tile_index += 1

        return self._dedupe_ocr_items(raw_items)

    def _dedupe_ocr_items(self, items):
        """
        타일 overlap 때문에 같은 글자가 중복 인식되는 것을 대충 제거.
        text가 같고 중심점이 가까우면 중복으로 판단.
        """
        if not items:
            return []

        deduped = []

        for item in items:
            duplicated = False

            for old in deduped:
                if item.get("text") != old.get("text"):
                    continue

                dx = abs(item["cx"] - old["cx"])
                dy = abs(item["cy"] - old["cy"])

                if dx < 20 and dy < 20:
                    duplicated = True
                    break

            if not duplicated:
                deduped.append(item)

        return deduped
 
    def quick_ocr_image_region(self, image_path, rect_norm, provider=None, language=None):
        """드래그한 단일 영역만 OCR해서 문자열로 반환한다.

        rect_norm: [x1, y1, x2, y2] normalized by current page size.
        """
        img_array = np.fromfile(image_path, np.uint8)
        ori_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        if ori_img is None:
            raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")
        h, w = ori_img.shape[:2]
        if not rect_norm or len(rect_norm) < 4:
            return ""
        x1, y1, x2, y2 = [float(v) for v in rect_norm[:4]]
        x1 = max(0, min(w - 1, int(round(x1 * w))))
        y1 = max(0, min(h - 1, int(round(y1 * h))))
        x2 = max(0, min(w, int(round(x2 * w))))
        y2 = max(0, min(h, int(round(y2 * h))))
        if x2 <= x1 or y2 <= y1:
            return ""
        crop = ori_img[y1:y2, x1:x2]
        if crop.size <= 0:
            return ""

        provider = str(provider or getattr(Config, "OCR_PROVIDER", "clova") or "clova").strip().lower()
        language = self._normalize_ocr_language(language or "") if language else ""

        old_provider = getattr(Config, "OCR_PROVIDER", "clova")
        old_clova_lang = getattr(Config, "CLOVA_OCR_LANGUAGE", "ja")
        old_google_lang = getattr(Config, "GOOGLE_VISION_OCR_LANGUAGE", "en")
        old_local_lang = getattr(Config, "LOCAL_PADDLE_OCR_LANGUAGE", "ja")
        old_manga_lang = getattr(Config, "LOCAL_MANGA_OCR_LANGUAGE", "ja")
        try:
            Config.OCR_PROVIDER = provider
            if language:
                if provider == "google_vision":
                    Config.GOOGLE_VISION_OCR_LANGUAGE = language
                elif provider == "local_paddle_ocr":
                    Config.LOCAL_PADDLE_OCR_LANGUAGE = language
                elif provider == "local_manga_ocr":
                    Config.LOCAL_MANGA_OCR_LANGUAGE = "ja"
                else:
                    Config.CLOVA_OCR_LANGUAGE = language

            if provider == "local_paddle_ocr":
                try:
                    from ysb.engines.ocr.base import OcrRequest
                    from ysb.engines.ocr.paddle_ocr import PaddleOcrEngine
                    lang = language or self._current_ocr_language()
                    device = str(getattr(Config, "LOCAL_PADDLE_OCR_DEVICE", getattr(Config, "LOCAL_PADDLE_MASK_DEVICE", "auto")) or "auto")
                    res = PaddleOcrEngine(language=lang, device=device).run(OcrRequest(
                        image_path='',
                        language=lang,
                        options={
                            'image_bgr': crop,
                            'device': device,
                            'scale': 1.5,
                        },
                    ))
                    if not res.ok:
                        raise ValueError(res.error or "PaddleOCR quick OCR failed")
                    raw_items = self._paddle_ocr_lines_to_raw_items(res.lines, x1, y1, locale=lang)
                except Exception:
                    raise
            elif provider == "local_manga_ocr":
                from ysb.engines.ocr.base import OcrRequest
                from ysb.engines.ocr.manga_ocr import MangaOcrEngine
                res = MangaOcrEngine(language="ja").run(OcrRequest(
                    image_path='',
                    language="ja",
                    options={
                        'image_bgr': crop,
                        'scale': 2.0,
                    },
                ))
                if not res.ok:
                    raise ValueError(res.error or "Manga OCR quick OCR failed")
                raw_items = self._manga_ocr_lines_to_raw_items(res.lines, x1, y1, locale="ja")
            else:
                raw_items = self._ocr_image_region_tiled(crop, offset_x=x1, offset_y=y1)

            raw_items = self._dedupe_ocr_items(raw_items)
            if not raw_items:
                return ""
            main_text_items, _ruby = self._split_main_and_ruby_items(raw_items)
            return self._manga_sort(main_text_items or raw_items).strip()
        finally:
            Config.OCR_PROVIDER = old_provider
            Config.CLOVA_OCR_LANGUAGE = old_clova_lang
            Config.GOOGLE_VISION_OCR_LANGUAGE = old_google_lang
            Config.LOCAL_PADDLE_OCR_LANGUAGE = old_local_lang
            Config.LOCAL_MANGA_OCR_LANGUAGE = old_manga_lang

    # ---------------------------------------------------------
    # [LOGIC] 그룹화 (스마트 정렬 적용)
    # ---------------------------------------------------------
    def _group_text_blocks_by_ratio(self, raw_items, w, h):
        if not raw_items: return [], np.zeros((h,w), dtype=np.uint8)

        merge_map = np.zeros((h, w), dtype=np.uint8)
        ratio = Config.MERGE_RATIO
        
        for item in raw_items:
            pts = np.array(item['vertices'], np.int32).reshape((-1, 1, 2))
            expansion = int(item['stroke_size'] * ratio)
            expansion = max(expansion, getattr(Config, 'MERGE_MIN_STROKE_PX', 5))
            cv2.fillPoly(merge_map, [pts], 255)
            cv2.polylines(merge_map, [pts], True, 255, thickness=expansion*2) 

        contours, _ = cv2.findContours(merge_map, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        grouped_data = []
        
        for idx, cnt in enumerate(contours):
            x, y, rw, rh = cv2.boundingRect(cnt)
            included_items = []
            for item in raw_items:
                if cv2.pointPolygonTest(cnt, (item['cx'], item['cy']), False) >= 0:
                    included_items.append(item)
            
            if not included_items: continue
            
            # 만화 정렬 적용
            # 마스크는 전체 OCR 조각을 유지하되, 번역/크기 추정용 텍스트는 본문 조각만 사용한다.
            main_text_items, ruby_items = self._split_main_and_ruby_items(included_items)
            combined_text = self._manga_sort(main_text_items)

            all_sub_vertices = [it['vertices'] for it in included_items]
            avg_stroke = sum([it['stroke_size'] for it in included_items]) / len(included_items)
            ocr_items = self._make_ocr_items_payload(main_text_items)
            ocr_items_all = self._make_ocr_items_payload(included_items)
            ruby_ocr_items = self._make_ocr_items_payload(ruby_items)

            grouped_data.append({
                'id': 0, 
                'text': combined_text,
                'rect': [x, y, rw, rh],
                'vertices_list': all_sub_vertices,
                'ocr_items': ocr_items,
                'ocr_items_all': ocr_items_all,
                'ruby_ocr_items': ruby_ocr_items,
                'ocr_lang': self._current_ocr_language(),
                'avg_stroke': avg_stroke,
                'use_inpaint': True,
                'x_off': 0, 'y_off': 0
            })
            
        grouped_data = self._organize_blocks(grouped_data)
        return grouped_data, merge_map

    # ---------------------------------------------------------
    # [LOGIC] 비율 기반 마스크 생성
    # ---------------------------------------------------------
    def _create_ratio_mask(self, grouped_data, w, h):
        mask = np.zeros((h, w), dtype=np.uint8)
        ratio = Config.INPAINT_RATIO
        min_p = Config.MIN_STROKE_PX
        for group in grouped_data:
            for v_list in group['vertices_list']:
                pts = np.array(v_list, np.int32).reshape((-1, 1, 2))
                rect_rot = cv2.minAreaRect(pts)
                (cx, cy), (rw, rh), angle = rect_rot
                stroke_size = min(rw, rh) if min(rw, rh) > 0 else max(rw, rh)
                pad = int(stroke_size * ratio)
                pad = max(pad, min_p)
                cv2.fillPoly(mask, [pts], 255)
                if pad > 0:
                    cv2.polylines(mask, [pts], True, 255, thickness=pad*2, lineType=cv2.LINE_AA)
        return mask

    def _mask_components_to_local_grouped_data(self, mask, w, h, *, existing_data=None):
        """현재 텍스트 마스크 자체를 기준으로 Local 분석 박스를 다시 만든다.

        LOCAL Paddle OCR 재분석은 detector를 다시 돌려
        마스크를 새로 만드는 작업이 아니다. 사용자가 지금 화면에서 보고 수정한 텍스트
        마스크가 source of truth이므로, 그 마스크의 연결 성분을 기준으로 분석 영역만 다시
        구성한다.
        """
        try:
            src = np.asarray(mask)
            if src.ndim == 3:
                src = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
            if src.shape[:2] != (int(h), int(w)):
                src = cv2.resize(src, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
            src = np.where(src > 0, 255, 0).astype(np.uint8)
        except Exception:
            return []

        contours, _ = cv2.findContours(src, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        grouped_data = []

        # 기존 data와 겹치면 텍스트/번역을 가능한 한 보존한다. 현재 단계는 마스크 검증용이라
        # 새 OCR 텍스트는 없지만, 수동 편집/기존 번역이 불필요하게 날아가는 것을 줄인다.
        existing = list(existing_data or [])

        def overlap_area(rect_a, rect_b):
            try:
                ax, ay, aw, ah = [int(v) for v in rect_a]
                bx, by, bw, bh = [int(v) for v in rect_b]
                ax2, ay2 = ax + aw, ay + ah
                bx2, by2 = bx + bw, by + bh
                ix1, iy1 = max(ax, bx), max(ay, by)
                ix2, iy2 = min(ax2, bx2), min(ay2, by2)
                if ix2 <= ix1 or iy2 <= iy1:
                    return 0
                return int((ix2 - ix1) * (iy2 - iy1))
            except Exception:
                return 0

        for cnt in contours or []:
            if cnt is None:
                continue
            area = abs(cv2.contourArea(cnt))
            if area < 2:
                continue
            x, y, rw, rh = cv2.boundingRect(cnt)
            if rw <= 0 or rh <= 0:
                continue

            rect = [int(x), int(y), int(rw), int(rh)]

            # 분석 박스는 연결된 현재 마스크 성분의 외접 박스로 둔다.
            # 실제 텍스트 마스크는 아래 reanalysis 반환값에서 user_mask_bin을 그대로 보존한다.
            vertices_list = [[[int(x), int(y)], [int(x + rw), int(y)], [int(x + rw), int(y + rh)], [int(x), int(y + rh)]]]
            avg_stroke = float(max(1, min(rw, rh)))

            best_old = None
            best_overlap = 0
            for old in existing:
                ov = overlap_area(rect, old.get('rect', [0, 0, 0, 0]))
                if ov > best_overlap:
                    best_overlap = ov
                    best_old = old

            text = ''
            translated_text = ''
            ocr_items = []
            ocr_items_all = []
            ruby_ocr_items = []
            if best_old is not None and best_overlap > 0:
                text = str(best_old.get('text', '') or '')
                translated_text = str(best_old.get('translated_text', '') or '')
                ocr_items = copy.deepcopy(best_old.get('ocr_items', []) or [])
                ocr_items_all = copy.deepcopy(best_old.get('ocr_items_all', []) or [])
                ruby_ocr_items = copy.deepcopy(best_old.get('ruby_ocr_items', []) or [])
                try:
                    avg_stroke = float(best_old.get('avg_stroke', avg_stroke) or avg_stroke)
                except Exception:
                    pass

            grouped_data.append({
                'id': 0,
                'text': text,
                'translated_text': translated_text,
                'rect': rect,
                'mask_rect': rect,
                'text_mask_rect': rect,
                'ocr_crop_rect': rect,
                'vertices_list': vertices_list,
                'ocr_items': ocr_items,
                'ocr_items_all': ocr_items_all,
                'ruby_ocr_items': ruby_ocr_items,
                'ocr_lang': 'local_mask',
                'avg_stroke': avg_stroke,
                'use_inpaint': True,
                'x_off': 0,
                'y_off': 0,
                'local_detector_only': True,
                'detector_engine': 'manual_mask_component',
                'detector_group_count': 1,
            })

        return self._organize_blocks(grouped_data) if grouped_data else []

    def _rect_overlap_area(self, rect_a, rect_b):
        """[x, y, w, h] 두 사각형의 겹친 면적을 반환한다."""
        try:
            ax, ay, aw, ah = [int(v) for v in rect_a]
            bx, by, bw, bh = [int(v) for v in rect_b]
            ax2, ay2 = ax + aw, ay + ah
            bx2, by2 = bx + bw, by + bh
            ix1, iy1 = max(ax, bx), max(ay, by)
            ix2, iy2 = min(ax2, bx2), min(ay2, by2)
            if ix2 <= ix1 or iy2 <= iy1:
                return 0
            return int((ix2 - ix1) * (iy2 - iy1))
        except Exception:
            return 0

    def _best_existing_group_for_rect(self, rect, existing_data):
        """현재 마스크 성분과 가장 많이 겹치는 기존 분석 그룹을 찾는다."""
        best_old = None
        best_overlap = 0
        for old in list(existing_data or []):
            ov = self._rect_overlap_area(rect, old.get('rect', [0, 0, 0, 0]))
            if ov > best_overlap:
                best_overlap = ov
                best_old = old
        return best_old, best_overlap

    def _pad_from_stroke_settings(self, stroke_ref, *, ratio=0.0, min_px=0):
        """분석 마스크 확장 비율/최소 px 설정을 실제 확장 px로 환산한다."""
        try:
            stroke_ref = float(stroke_ref or 0.0)
        except Exception:
            stroke_ref = 0.0
        try:
            ratio = max(0.0, float(ratio or 0.0))
        except Exception:
            ratio = 0.0
        try:
            min_px = max(0, int(min_px or 0))
        except Exception:
            min_px = 0

        px = int(stroke_ref * ratio) if ratio > 0 and stroke_ref > 0 else 0
        if min_px > 0:
            px = max(px, min_px)
        return max(0, int(px))

    def _estimate_reanalysis_component_stroke(self, rect, existing_data):
        """Local 재분석용 stroke 기준값을 추정한다.

        전체 분석 때 detector가 만든 avg_stroke가 남아 있으면 그 값을 우선 사용한다.
        없으면 현재 마스크 성분의 짧은 변을 보수적인 fallback으로 사용한다.
        """
        best_old, best_overlap = self._best_existing_group_for_rect(rect, existing_data)
        if best_old is not None and best_overlap > 0:
            try:
                old_stroke = float(best_old.get('avg_stroke', 0) or 0)
                if old_stroke > 0:
                    return old_stroke
            except Exception:
                pass
        try:
            _x, _y, rw, rh = [int(v) for v in rect]
            return float(max(1, min(rw, rh)))
        except Exception:
            return 1.0

    def _erode_component_safely(self, component, erode_px):
        """텍스트 마스크 확장분을 되돌리기 위해 성분을 침식한다.

        침식으로 성분이 완전히 사라지면 사용자가 칠한 마스크를 잃지 않도록 원본 성분을 반환한다.
        """
        try:
            erode_px = max(0, int(erode_px or 0))
        except Exception:
            erode_px = 0
        if erode_px <= 0:
            return component.copy()
        k = max(1, erode_px * 2 + 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        core = cv2.erode(component, kernel, iterations=1)
        if cv2.countNonZero(core) <= 0:
            return component.copy()
        return core

    def _dilate_component_safely(self, component, dilate_px):
        """성분을 지정 px만큼 확장한다."""
        try:
            dilate_px = max(0, int(dilate_px or 0))
        except Exception:
            dilate_px = 0
        if dilate_px <= 0:
            return component.copy()
        k = max(1, dilate_px * 2 + 1)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
        return cv2.dilate(component, kernel, iterations=1)

    def _local_detector_base_mask_for_reanalysis(self, image_path, w, h):
        """Local 재분석 페인트 마스크용 detector 기준 마스크를 다시 얻는다.

        재분석의 텍스트 마스크는 사용자가 보고 수정한 작업 마스크라서 이미 텍스트 마스크
        확장값이 들어가 있을 수 있다. 페인트 마스크를 이 마스크에서 기하학적으로 되돌리면
        원래 detector의 글자 획/라인 정보가 손실되어 부정확해진다. 따라서 원본 이미지에
        comic_text_detector를 다시 실행하고, 이후 현재 텍스트 마스크 안쪽에서만 사용할 기준
        마스크를 만든다.
        """
        from ysb.engines.text_detection.base import TextDetectionRequest
        from ysb.engines.text_detection.manager import detect_with_default_engine

        input_size = self._local_detector_auto_input_size(w, h)
        device = str(getattr(Config, "LOCAL_PADDLE_MASK_DEVICE", "auto") or "auto")

        result = detect_with_default_engine(TextDetectionRequest(
            image_path=image_path,
            options={
                "input_size": input_size,
                "device": device,
                "save_masks": False,
                "keep_undetected_mask": True,
            },
        ))
        if not result.ok:
            return None, [], {}, f"comic_text_detector 재분석 실패: {result.error}"

        blocks = list(result.blocks or [])
        safe_blocks = [
            block for block in blocks
            if self._detector_block_is_reasonable(getattr(block, 'bbox', (0, 0, 0, 0)), w, h)
        ]
        raw_payload = result.raw if isinstance(result.raw, dict) else {}
        source_mask = raw_payload.get("mask_refined")
        if source_mask is None:
            source_mask = raw_payload.get("mask")

        base_mask, stats = self._create_detector_candidate_mask(
            safe_blocks, w, h, source_mask=source_mask
        )
        return base_mask, safe_blocks, stats, ""

    def _filter_detector_blocks_by_mask_overlap(self, blocks, gate_mask, w, h):
        """현재 텍스트 마스크와 겹치는 detector block만 남긴다."""
        if not blocks:
            return []
        try:
            gate = np.asarray(gate_mask)
            if gate.ndim == 3:
                gate = cv2.cvtColor(gate, cv2.COLOR_BGR2GRAY)
            if gate.shape[:2] != (int(h), int(w)):
                gate = cv2.resize(gate, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
            gate = np.where(gate > 0, 255, 0).astype(np.uint8)
        except Exception:
            gate = None
        if gate is None or cv2.countNonZero(gate) <= 0:
            return []

        filtered = []
        for block in blocks:
            try:
                x1, y1, x2, y2 = self._normalize_box(getattr(block, 'bbox', (0, 0, 0, 0)), w, h)
            except Exception:
                continue
            if x2 <= x1 or y2 <= y1:
                continue
            roi = gate[y1:y2, x1:x2]
            if roi.size > 0 and cv2.countNonZero(roi) > 0:
                filtered.append(block)
        return filtered

    def _paint_mask_from_detector_inside_manual_text_mask(self, image_path, text_mask, w, h, *, existing_data=None):
        """현재 텍스트 마스크 영역 안에서 detector 기준 마스크를 다시 찾아 페인트 마스크를 만든다.

        원칙:
        - 텍스트 마스크는 사용자가 수정한 현재 작업 마스크이므로 그대로 보존한다.
        - 페인팅 마스크는 현재 텍스트 마스크를 그대로 확장/축소해서 만들지 않는다.
        - 원본 이미지에 detector를 다시 돌려 실제 글자 후보 마스크를 얻고,
          그중 현재 텍스트 마스크 안쪽과 겹치는 부분만 기준으로 삼는다.
        - 이후 페인트 마스크 확장 비율/최소 확장 크기만 적용한다.
        - 최종 결과는 현재 텍스트 마스크 바깥으로 튀어나가지 않게 한 번 더 자른다.
        """
        if text_mask is None:
            return np.zeros((int(h), int(w)), dtype=np.uint8), "empty_text_mask"
        try:
            gate = np.asarray(text_mask)
            if gate.ndim == 3:
                gate = cv2.cvtColor(gate, cv2.COLOR_BGR2GRAY)
            if gate.shape[:2] != (int(h), int(w)):
                gate = cv2.resize(gate, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
            gate = np.where(gate > 0, 255, 0).astype(np.uint8)
        except Exception:
            return np.zeros((int(h), int(w)), dtype=np.uint8), "invalid_text_mask"

        if cv2.countNonZero(gate) <= 0:
            return np.zeros((int(h), int(w)), dtype=np.uint8), "empty_text_mask"

        base_mask, safe_blocks, stats, err = self._local_detector_base_mask_for_reanalysis(image_path, w, h)
        if base_mask is None or err:
            fallback = self._paint_mask_from_reanalysis_text_mask(gate, w, h, existing_data=existing_data)
            return cv2.bitwise_and(fallback, gate), "fallback_erode:" + str(err or "no_base_mask")

        # detector block이 현재 텍스트 마스크와 겹치는 것만 사용한다.
        overlap_blocks = self._filter_detector_blocks_by_mask_overlap(safe_blocks, gate, w, h)
        if overlap_blocks:
            # 전체 base_mask를 그대로 쓰지 않고, 겹친 block만 다시 기준 마스크로 만든다.
            # source_mask는 이미 base_mask에 반영되어 있으므로 여기서는 block 후보와 base_mask를 교차시킨다.
            block_gate = np.zeros((int(h), int(w)), dtype=np.uint8)
            for block in overlap_blocks:
                try:
                    x1, y1, x2, y2 = self._normalize_box(getattr(block, 'bbox', (0, 0, 0, 0)), w, h)
                    if x2 > x1 and y2 > y1:
                        cv2.rectangle(block_gate, (x1, y1), (max(x1, x2 - 1), max(y1, y2 - 1)), 255, thickness=-1)
                except Exception:
                    continue
            detector_core = cv2.bitwise_and(base_mask, block_gate)
        else:
            detector_core = base_mask.copy()

        # 현재 사용자가 승인한 텍스트 마스크 안쪽만 기준으로 삼는다.
        detector_core = cv2.bitwise_and(detector_core, gate)

        if cv2.countNonZero(detector_core) <= 0:
            # detector 기준 마스크가 현재 수동 마스크 안에서 비면, 완전히 빈 페인트 마스크를 만들면
            # 사용자가 당황할 수 있으므로 마지막 호환 fallback을 사용한다. 그래도 gate 밖은 잘라낸다.
            fallback = self._paint_mask_from_reanalysis_text_mask(gate, w, h, existing_data=existing_data)
            return cv2.bitwise_and(fallback, gate), "fallback_erode:empty_detector_overlap"

        paint = self._expand_detector_analysis_mask(
            detector_core, overlap_blocks or safe_blocks, w, h,
            ratio=getattr(Config, 'INPAINT_RATIO', 0.1),
            min_px=getattr(Config, 'MIN_STROKE_PX', 1),
        )
        # 최종 인페인트 마스크는 현재 텍스트 마스크 바깥으로 튀어나가지 않게 제한한다.
        paint = cv2.bitwise_and(paint, gate)
        return paint, f"detector_core:{int(cv2.countNonZero(detector_core))},blocks={len(overlap_blocks or safe_blocks)},stats={stats}"

    def _paint_mask_from_reanalysis_text_mask(self, text_mask, w, h, *, existing_data=None):
        """현재 텍스트 마스크를 기준으로 Local 재분석용 페인팅 마스크를 다시 만든다.

        중요:
        - 재분석의 입력 text_mask는 이미 '텍스트 마스크 확장 비율'이 적용된 실제 작업 마스크다.
        - 이 마스크에 페인트 확장값을 또 더하면, 페인팅 마스크가 텍스트 마스크 확장값까지
          그대로 물려받는 문제가 생긴다.
        - 따라서 성분별로 텍스트 확장분을 먼저 되돌린 뒤, 페인트 마스크 확장값으로 다시 그린다.
        """
        if text_mask is None:
            return np.zeros((int(h), int(w)), dtype=np.uint8)
        try:
            src = np.asarray(text_mask)
            if src.ndim == 3:
                src = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
            if src.shape[:2] != (int(h), int(w)):
                src = cv2.resize(src, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
            src = np.where(src > 0, 255, 0).astype(np.uint8)
        except Exception:
            return np.zeros((int(h), int(w)), dtype=np.uint8)

        contours, _ = cv2.findContours(src, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = np.zeros((int(h), int(w)), dtype=np.uint8)

        text_ratio = getattr(Config, 'MERGE_RATIO', 0.2)
        text_min_px = getattr(Config, 'MERGE_MIN_STROKE_PX', 5)
        paint_ratio = getattr(Config, 'INPAINT_RATIO', 0.1)
        paint_min_px = getattr(Config, 'MIN_STROKE_PX', 1)

        for cnt in contours or []:
            if cnt is None:
                continue
            area = abs(cv2.contourArea(cnt))
            if area < 1:
                continue
            x, y, rw, rh = cv2.boundingRect(cnt)
            if rw <= 0 or rh <= 0:
                continue

            rect = [int(x), int(y), int(rw), int(rh)]
            component = np.zeros((int(h), int(w)), dtype=np.uint8)
            cv2.drawContours(component, [cnt], -1, 255, thickness=-1)

            stroke_ref = self._estimate_reanalysis_component_stroke(rect, existing_data)
            text_pad = self._pad_from_stroke_settings(
                stroke_ref,
                ratio=text_ratio,
                min_px=text_min_px,
            )
            paint_pad = self._pad_from_stroke_settings(
                stroke_ref,
                ratio=paint_ratio,
                min_px=paint_min_px,
            )

            # 현재 텍스트 마스크에 이미 반영된 텍스트 확장분을 제거한 뒤,
            # 페인트 설정값만 다시 적용한다.
            core = self._erode_component_safely(component, text_pad)
            painted = self._dilate_component_safely(core, paint_pad)
            out = cv2.bitwise_or(out, painted)

        return out

    def _expand_mask_components_for_analysis(self, base_mask, w, h, *, ratio=0.0, min_px=0):
        """현재 마스크를 단순 확장한다.

        기존 호환용 함수다. Local detector 재분석의 페인팅 마스크는
        _paint_mask_from_reanalysis_text_mask()를 사용해 텍스트 확장분을 되돌린 뒤 다시 만든다.
        """
        if base_mask is None:
            return np.zeros((int(h), int(w)), dtype=np.uint8)
        try:
            src = np.asarray(base_mask)
            if src.ndim == 3:
                src = cv2.cvtColor(src, cv2.COLOR_BGR2GRAY)
            if src.shape[:2] != (int(h), int(w)):
                src = cv2.resize(src, (int(w), int(h)), interpolation=cv2.INTER_NEAREST)
            src = np.where(src > 0, 255, 0).astype(np.uint8)
        except Exception:
            return np.zeros((int(h), int(w)), dtype=np.uint8)

        try:
            ratio = max(0.0, float(ratio or 0.0))
        except Exception:
            ratio = 0.0
        try:
            min_px = max(0, int(min_px or 0))
        except Exception:
            min_px = 0

        if ratio <= 0 and min_px <= 0:
            return src.copy()

        contours, _ = cv2.findContours(src, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = np.zeros((int(h), int(w)), dtype=np.uint8)
        for cnt in contours or []:
            if cnt is None:
                continue
            area = abs(cv2.contourArea(cnt))
            if area < 1:
                continue
            x, y, rw, rh = cv2.boundingRect(cnt)
            if rw <= 0 or rh <= 0:
                continue
            component = np.zeros((int(h), int(w)), dtype=np.uint8)
            cv2.drawContours(component, [cnt], -1, 255, thickness=-1)
            stroke_ref = float(max(1, min(rw, rh)))
            pad = self._pad_from_stroke_settings(stroke_ref, ratio=ratio, min_px=min_px)
            component = self._dilate_component_safely(component, pad)
            out = cv2.bitwise_or(out, component)
        return out

    def _reanalyze_local_detector_from_manual_mask(self, image_path, ori_img, user_mask_bin, existing_data):
        """LOCAL Paddle OCR용 재분석.

        재분석은 '현재 텍스트 마스크를 detector로 다시 따는 작업'이 아니라,
        사용자가 지금 화면에서 수정한 텍스트 마스크를 그대로 기준으로 삼아 분석 영역을
        다시 구성하는 작업이다. detector를 처음부터 다시 돌려 현재 마스크를 덮어쓰지 않는다.
        이후 PaddleOCR은 재구성된 각 영역의 원문만 다시 인식한다.
        """
        print(">>> [Re-Scan][Local OCR] 현재 텍스트 마스크 기준으로 분석 영역 재구성")
        h, w = ori_img.shape[:2]

        if user_mask_bin is None:
            final_data = self._organize_blocks(copy.deepcopy(existing_data or [])) if existing_data else []
            mask_merge = np.zeros((h, w), dtype=np.uint8)
            mask_inpaint = self._create_grouped_data_analysis_mask(
                final_data, w, h,
                ratio=getattr(Config, 'INPAINT_RATIO', 0.1),
                min_px=getattr(Config, 'MIN_STROKE_PX', 1),
            )
            return ori_img, final_data, mask_merge, mask_inpaint

        try:
            if user_mask_bin.ndim == 3:
                user_mask_bin = cv2.cvtColor(user_mask_bin, cv2.COLOR_RGB2GRAY)
        except Exception:
            pass
        user_mask_bin = np.where(np.asarray(user_mask_bin) > 0, 255, 0).astype(np.uint8)
        if user_mask_bin.shape[:2] != (h, w):
            user_mask_bin = cv2.resize(user_mask_bin, (w, h), interpolation=cv2.INTER_NEAREST)

        final_data = self._mask_components_to_local_grouped_data(
            user_mask_bin, w, h,
            existing_data=existing_data,
        )
        # 텍스트 마스크는 사용자가 보고 수정한 현재 마스크를 그대로 유지한다.
        mask_merge = user_mask_bin.copy()
        # 페인팅 마스크는 현재 텍스트 마스크를 그대로 확장/축소해서 만들지 않는다.
        # 원본 이미지에 detector를 다시 돌리고, 현재 텍스트 마스크 안쪽에서만 실제 글자 후보를
        # 다시 찾은 뒤 페인트 마스크 확장 비율만 적용한다.
        mask_inpaint, paint_source = self._paint_mask_from_detector_inside_manual_text_mask(
            image_path, user_mask_bin, w, h,
            existing_data=existing_data,
        )
        final_data = self._apply_current_local_ocr_engine_to_groups(ori_img, final_data)

        print(
            f">>> [Re-Scan][Local OCR] manual_mask_components={len(final_data)}, "
            f"text_mask_pixels={int(cv2.countNonZero(mask_merge))}, "
            f"paint_mask_pixels={int(cv2.countNonZero(mask_inpaint))}, "
            f"paint_source={paint_source}"
        )
        return ori_img, final_data, mask_merge, mask_inpaint

    # ---------------------------------------------------------
    # [CORE] 재분석 (최종 완전체)
    # - 가위질(Erode) + Threshold 강화
    # - API 1회 호출
    # - Best Fit 독점 배정
    # - 면적 기반(Overlap) 기존 데이터 삭제
    # ---------------------------------------------------------
    def reanalyze_from_manual_mask(self, image_path, user_mask_rgb, existing_data):
        print(">>> [Re-Scan] 재분석: 완전체 V3 (면적 삭제 + Best Fit + 가위질)")
        
        img_array = np.fromfile(image_path, np.uint8)
        ori_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
        h, w, _ = ori_img.shape

        if user_mask_rgb.ndim == 3: gray_mask = cv2.cvtColor(user_mask_rgb, cv2.COLOR_RGB2GRAY)
        else: gray_mask = user_mask_rgb
        
        # 1. 마스크 전처리
        _, user_mask_bin = cv2.threshold(gray_mask, 127, 255, cv2.THRESH_BINARY)

        provider = str(getattr(Config, "OCR_PROVIDER", "clova") or "clova").strip().lower()
        if provider in ("local_paddle_ocr", "local_manga_ocr"):
            # Local detector는 마스크/영역 기준 재분석을 사용한다.
            # 기존 API OCR 재분석 경로로 보내면 빈 OCR 결과 때문에 분석도가 날아갈 수 있다.
            return self._reanalyze_local_detector_from_manual_mask(
                image_path, ori_img, user_mask_bin, existing_data
            )

        kernel = np.ones((3,3), np.uint8)
        user_mask_bin_eroded = cv2.erode(user_mask_bin, kernel, iterations=1) 
        
        contours, _ = cv2.findContours(user_mask_bin_eroded, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        if not contours: 
            return ori_img, existing_data, user_mask_bin, self._create_ratio_mask(existing_data, w, h)

        # 2. 통합 영역 계산
        all_points = np.vstack(contours)
        bx, by, bw, bh = cv2.boundingRect(all_points)
        
        pad = 50
        cx = max(0, bx - pad); cy = max(0, by - pad)
        cw = min(w - cx, bw + 2*pad); ch = min(h - cy, bh + 2*pad)
        
        crop_img = ori_img[cy:cy+ch, cx:cx+cw]

        # 긴 재분석 영역도 세로 분할 OCR로 처리
        all_raw_items = self._ocr_image_region_tiled(
            crop_img,
            offset_x=cx,
            offset_y=cy
        )

        # 3. 배정 로직 (Best Fit)
        mask_buckets = [[] for _ in range(len(contours))]
        for item in all_raw_items:
            best_mask_idx = -1; max_score = -99999 
            for idx, cnt in enumerate(contours):
                score = cv2.pointPolygonTest(cnt, (item['cx'], item['cy']), True)
                if score > max_score: max_score = score; best_mask_idx = idx
            if best_mask_idx != -1 and max_score > -5.0:
                mask_buckets[best_mask_idx].append(item)

        new_grouped_data = []
        for idx, items_in_bubble in enumerate(mask_buckets):
            cnt = contours[idx]
            rx, ry, rw, rh = cv2.boundingRect(cnt)
            if not items_in_bubble: continue
            
            # 마스크는 전체 OCR 조각을 유지하되, 번역/크기 추정용 텍스트는 본문 조각만 사용한다.
            main_text_items, ruby_items = self._split_main_and_ruby_items(items_in_bubble)
            combined_text = self._manga_sort(main_text_items)
            all_vertices = [it['vertices'] for it in items_in_bubble]
            avg_stroke = sum([it['stroke_size'] for it in items_in_bubble]) / len(items_in_bubble)
            ocr_items = self._make_ocr_items_payload(main_text_items)
            ocr_items_all = self._make_ocr_items_payload(items_in_bubble)
            ruby_ocr_items = self._make_ocr_items_payload(ruby_items)

            new_grouped_data.append({
                'id': 0, 'text': combined_text, 'rect': [rx, ry, rw, rh], 
                'vertices_list': all_vertices,
                'ocr_items': ocr_items,
                'ocr_items_all': ocr_items_all,
                'ruby_ocr_items': ruby_ocr_items,
                'ocr_lang': self._current_ocr_language(),
                'avg_stroke': avg_stroke,
                'use_inpaint': True, 'x_off': 0, 'y_off': 0
            })

        # 4. 기존 데이터 삭제 (면적 기반)
        final_data = []
        for item in existing_data:
            ix, iy, iw, ih = item['rect']
            y1, y2 = max(0, iy), min(h, iy+ih)
            x1, x2 = max(0, ix), min(w, ix+iw)
            
            if x2 <= x1 or y2 <= y1:
                final_data.append(item)
                continue

            mask_roi = user_mask_bin[y1:y2, x1:x2]
            if cv2.countNonZero(mask_roi) > 10: 
                continue # 10픽셀 이상 겹치면 삭제
            
            final_data.append(item)
            
        final_data.extend(new_grouped_data)
        final_data = self._organize_blocks(final_data)
            
        mask_inpaint = self._create_ratio_mask(final_data, w, h)
        return ori_img, final_data, user_mask_bin, mask_inpaint

    # ---------------------------------------------------------
    # [CORE] 번역
    # ---------------------------------------------------------
    # ---------------------------------------------------------
    # [CORE] 번역
    # ---------------------------------------------------------
    def translate_text_batch(self, texts, provider="openai", chunk_size=None):
        if not texts:
            return []

        provider = (provider or "openai").lower()

        # API 키가 없으면 청크 실패 -> 단일 재시도 -> 원문 반환으로 흘러가면 안 된다.
        # 이 경우는 즉시 상위 UI로 올려서 경고창을 띄우게 한다.
        if provider == "deepseek":
            if self.deepseek_client is None:
                raise ValueError("DeepSeek API 키가 비어있습니다.")
        elif provider == "google":
            if not getattr(Config, "GOOGLE_TRANSLATE_API_KEY", ""):
                raise ValueError("Google Translate API 키가 비어있습니다.")
        elif provider == "gemini":
            if not getattr(Config, "GEMINI_API_KEY", ""):
                raise ValueError("Gemini API 키가 비어있습니다.")
        elif provider == "custom":
            if self.custom_translation_client is None or not getattr(Config, "CUSTOM_TRANSLATION_MODEL", ""):
                raise ValueError("Custom 번역 API 설정이 비어있습니다. Base URL, Model, API Key를 확인해주세요.")
        elif provider in ("local_argos", "local_hf_jako", "local_hf_enko", "local_nllb"):
            provider = "openai"
            if self.openai_client is None:
                raise ValueError("OpenAI API 키가 비어있습니다.")
        else:
            if self.openai_client is None:
                raise ValueError("OpenAI API 키가 비어있습니다.")

        # 번역 묶음 수
        # main.py에서 사용자가 지정한 값이 오면 그 값을 우선 사용한다.
        if chunk_size is None:
            if provider == "deepseek":
                chunk_size = 8
            elif provider == "google":
                chunk_size = 50
            elif provider == "gemini":
                chunk_size = 10
            else:
                chunk_size = 20
        else:
            try:
                chunk_size = int(chunk_size)
            except:
                chunk_size = 8 if provider == "deepseek" else (50 if provider == "google" else (10 if provider == "gemini" else 20))
            chunk_size = max(1, min(chunk_size, 100))

        final_results = []

        for start in range(0, len(texts), chunk_size):
            chunk = texts[start:start + chunk_size]

            try:
                translated_chunk = self._translate_text_chunk(chunk, provider, start)
                final_results.extend(translated_chunk)

            except Exception as e:
                print(f"Chunk Translate Error: {e}")
                if "API 키가 비어" in str(e):
                    raise

                # 청크 실패 시 한 줄씩 재시도
                for offset, one_text in enumerate(chunk):
                    try:
                        one_result = self._translate_text_chunk([one_text], provider, start + offset)
                        final_results.extend(one_result)
                    except Exception as e2:
                        print(f"Single Translate Error: {e2}")
                        if "API 키가 비어" in str(e2):
                            raise
                        final_results.append(one_text)

        # 최종 안전장치
        if len(final_results) != len(texts):
            print(f"Translate Count Mismatch Fixed: input={len(texts)}, output={len(final_results)}")

            if len(final_results) < len(texts):
                final_results.extend(texts[len(final_results):])
            else:
                final_results = final_results[:len(texts)]

        return final_results



    def _translate_text_chunk_google(self, texts):
        """Google Cloud Translation Basic v2 API."""
        key = str(getattr(Config, "GOOGLE_TRANSLATE_API_KEY", "") or "").strip()
        if not key:
            raise ValueError("Google Translate API 키가 비어있습니다.")

        url = "https://translation.googleapis.com/language/translate/v2"
        payload = {
            "q": [str(t or "") for t in texts],
            "source": "ja",
            "target": "ko",
            "format": "text",
        }
        r = requests.post(url, params={"key": key}, json=payload, timeout=60)
        if r.status_code != 200:
            raise ValueError(f"Google Translate Error: {r.status_code} / {r.text[:300]}")

        data = r.json()
        translations = data.get("data", {}).get("translations", [])
        results = []
        for i, original in enumerate(texts):
            if i < len(translations):
                translated = str(translations[i].get("translatedText", "") or "")
                results.append(html.unescape(translated))
            else:
                results.append(str(original or ""))
        return results

    def _translate_text_chunk_gemini(self, texts, base_id=0):
        """Google AI Studio Gemini API 번역."""
        key = str(getattr(Config, "GEMINI_API_KEY", "") or "").strip()
        if not key:
            raise ValueError("Gemini API 키가 비어있습니다.")

        model = str(getattr(Config, "GEMINI_TRANSLATION_MODEL", "gemini-2.5-flash-lite") or "gemini-2.5-flash-lite").strip()
        prompt = self._build_translation_system_prompt()

        input_items = []
        for i, text in enumerate(texts):
            input_items.append({"id": base_id + i, "text": text})

        user_text = prompt.strip() + "\n\nINPUT JSON:\n" + json.dumps(input_items, ensure_ascii=False)
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [
                {"role": "user", "parts": [{"text": user_text}]}
            ],
            "generationConfig": {
                "temperature": 0.2,
                "responseMimeType": "application/json"
            }
        }

        r = requests.post(url, params={"key": key}, json=payload, timeout=90)
        if r.status_code != 200:
            err_text = r.text[:800]
            try:
                err = r.json().get("error", {})
                msg = str(err.get("message", "") or err_text)
                code = int(err.get("code", r.status_code) or r.status_code)
            except Exception:
                msg = err_text
                code = r.status_code

            if code == 429:
                raise ValueError(
                    "Gemini Translate Error: 429 / Gemini API 할당량 또는 속도 제한을 초과했습니다. "
                    "AI Studio의 Rate limits와 결제 설정을 확인해 주세요. 무료 등급에서 limit: 0으로 표시되면 "
                    "해당 프로젝트에 사용 가능한 무료 할당량이 없거나 결제 설정이 필요한 상태일 수 있습니다. "
                    f"원문: {msg[:400]}"
                )
            if code == 404:
                raise ValueError(
                    f"Gemini Translate Error: 404 / Gemini 모델명을 찾을 수 없습니다. 현재 모델명 '{model}'을 확인해 주세요. "
                    "예: gemini-2.5-flash-lite"
                )
            raise ValueError(f"Gemini Translate Error: {code} / {msg[:500]}")

        data = r.json()
        candidates = data.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini 번역 응답이 비어있습니다.")

        parts = candidates[0].get("content", {}).get("parts", [])
        content = "".join(str(part.get("text", "")) for part in parts).strip()
        if not content:
            raise ValueError("Gemini 번역 텍스트가 비어있습니다.")

        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        parsed = json.loads(content.strip())
        if isinstance(parsed, dict):
            items = parsed.get("items", [])
        elif isinstance(parsed, list):
            items = parsed
        else:
            raise ValueError("Gemini 번역 응답 JSON 형식이 올바르지 않습니다.")

        by_id = {}
        for item in items:
            if isinstance(item, dict):
                try:
                    by_id[int(item.get("id"))] = str(item.get("translation", ""))
                except Exception:
                    pass

        results = []
        missing_ids = []
        for i in range(len(texts)):
            item_id = base_id + i
            if item_id in by_id:
                results.append(by_id[item_id])
            else:
                missing_ids.append(item_id)

        if missing_ids:
            raise ValueError(f"Gemini 번역 누락 ID 발생: {missing_ids}")
        return results

    def _build_translation_system_prompt(self):
        """
        사용자가 옵션에서 입력한 프롬프트/단어장만 번역 지침으로 사용한다.
        단, 프로그램 파서 보호를 위해 JSON 출력 형식 규칙은 항상 붙인다.
        """
        custom_prompt = str(getattr(Config, "TRANSLATION_PROMPT", "") or "").strip()
        glossary_text = str(getattr(Config, "TRANSLATION_GLOSSARY_TEXT", "") or "").strip()

        parts = []
        if custom_prompt:
            parts.append(custom_prompt)

        if glossary_text:
            parts.append(
                "번역 참고 자료/단어장입니다. 아래 내용을 우선 참고해서 번역하세요.\n"
                "배경 설명, 단어 해설, 1대1 대체 규칙이 섞여 있을 수 있습니다.\n\n"
                + glossary_text
            )

        output_rules = """
OUTPUT FORMAT RULES FOR THIS PROGRAM:
1. Input is a JSON list of objects.
2. Each object has "id" and "text".
3. Return ONLY a valid JSON object.
4. The JSON object MUST have one key: "items".
5. "items" MUST be a list of objects.
6. Each output object MUST have the same "id" and a "translation".
7. NEVER skip any id.
8. NEVER merge two ids into one translation.
9. NEVER create a new id.
10. Do not add explanations, notes, comments, markdown, or extra text.
11. Example output:
{"items":[{"id":0,"translation":"번역문"},{"id":1,"translation":"번역문"}]}
""".strip()
        parts.append(output_rules)

        return "\n\n".join(parts).strip()

    def _translate_text_chunk(self, texts, provider="openai", base_id=0):
        prompt = self._build_translation_system_prompt()

        provider = (provider or "openai").lower()

        if provider == "google":
            return self._translate_text_chunk_google(texts)
        if provider == "gemini":
            return self._translate_text_chunk_gemini(texts, base_id)
        if provider in ("local_argos", "local_hf_jako", "local_hf_enko", "local_nllb"):
            provider = "openai"

        if provider == "deepseek":
            if self.deepseek_client is None:
                raise ValueError("DeepSeek API 키가 비어있습니다.")
            client = self.deepseek_client
            model = Config.DEEPSEEK_TRANSLATION_MODEL
        elif provider == "custom":
            if self.custom_translation_client is None:
                raise ValueError("Custom 번역 API 설정이 비어있습니다. Base URL, Model, API Key를 확인해주세요.")
            client = self.custom_translation_client
            model = str(getattr(Config, "CUSTOM_TRANSLATION_MODEL", "") or "").strip()
            if not model:
                raise ValueError("Custom 번역 모델명이 비어있습니다.")
        else:
            if self.openai_client is None:
                raise ValueError("OpenAI API 키가 비어있습니다.")
            client = self.openai_client
            model = Config.OPENAI_TRANSLATION_MODEL

        input_items = []
        for i, text in enumerate(texts):
            input_items.append({
                "id": base_id + i,
                "text": text
            })

        r = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": prompt.strip()},
                {"role": "user", "content": json.dumps(input_items, ensure_ascii=False)}
            ],
            temperature=0.2
        )

        content = r.choices[0].message.content.strip()

        if content.startswith("```json"):
            content = content[7:]
        if content.startswith("```"):
            content = content[3:]
        if content.endswith("```"):
            content = content[:-3]

        parsed = json.loads(content.strip())

        # 정상 형식: {"items": [...]}
        if isinstance(parsed, dict):
            items = parsed.get("items", [])
        # 혹시 리스트로 튀어나온 경우도 방어
        elif isinstance(parsed, list):
            items = parsed
        else:
            raise ValueError("번역 응답 JSON 형식이 올바르지 않습니다.")

        by_id = {}

        for item in items:
            if isinstance(item, dict):
                item_id = item.get("id")
                trans = item.get("translation", "")

                if item_id is not None:
                    try:
                        item_id = int(item_id)
                        by_id[item_id] = str(trans)
                    except:
                        pass

        results = []
        missing_ids = []

        for i in range(len(texts)):
            item_id = base_id + i

            if item_id in by_id:
                results.append(by_id[item_id])
            else:
                missing_ids.append(item_id)

        if missing_ids:
            raise ValueError(f"번역 누락 ID 발생: {missing_ids}")

        return results

    # ---------------------------------------------------------
    # [CORE] 식질 (Windows 파일 잠금 해결)
    # ---------------------------------------------------------
    def execute_inpainting(self, image_path, analyzed_data, mask_1st):
        import replicate
        if mask_1st is not None:
            final_mask = mask_1st.copy()
        else:
            img_array = np.fromfile(image_path, np.uint8)
            base_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)
            if base_img is None:
                raise ValueError(f"이미지 파일을 읽을 수 없습니다: {image_path}")
            final_mask = self._create_ratio_mask(analyzed_data, *base_img.shape[:2][::-1])
        for d in analyzed_data:
            if not d.get('use_inpaint', True):
                rx, ry, rw, rh = d['rect']
                cv2.rectangle(final_mask, (rx, ry), (rx+rw, ry+rh), 0, -1)
        _, bin_mask = cv2.threshold(final_mask, 10, 255, cv2.THRESH_BINARY)
        try:
            if int(cv2.countNonZero(bin_mask)) <= 0:
                raise ValueError("인페인팅 마스크가 최종 처리 후 비어 있습니다. 체크박스/마스크 겹침을 확인해 주세요.")
        except ValueError:
            raise
        except Exception:
            pass
        provider = str(getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama").lower()
        if provider == "replicate_stable":
            return self._call_stable_inpaint(image_path, bin_mask)
        if provider == "gemini_inpaint":
            return self._call_gemini_inpaint(image_path, bin_mask)
        if provider == "local_lama":
            return self._call_local_lama(image_path, bin_mask)
        return self._call_lama(image_path, bin_mask)


    def _find_local_lama_model_path(self):
        """프로젝트 local_models 안의 LaMa torchscript 모델 파일을 찾는다.

        simple-lama-inpainting은 환경변수 LAMA_MODEL에 로컬 모델 경로를 주면 자동 다운로드 대신
        그 파일을 torch.jit.load()로 읽는다. 지원 기본 파일명은 big-lama.pt다.
        """
        roots = []
        try:
            roots.append(Path.cwd())
        except Exception:
            pass
        try:
            roots.append(Path(__file__).resolve().parents[2])
        except Exception:
            pass
        try:
            exe_dir = Path(getattr(sys, "executable", "")).resolve().parent
            roots.append(exe_dir)
        except Exception:
            pass
        try:
            meipass = getattr(sys, "_MEIPASS", "")
            if meipass:
                roots.append(Path(meipass))
        except Exception:
            pass

        # 중복 제거. PyInstaller onedir/source 양쪽에서 local_models를 찾기 위한 후보들이다.
        uniq_roots = []
        seen = set()
        for root in roots:
            try:
                r = Path(root).resolve()
                if r not in seen:
                    seen.add(r)
                    uniq_roots.append(r)
            except Exception:
                continue

        candidates = []
        for base in uniq_roots:
            candidates.extend([
                base / "local_models" / "lama" / "big-lama.pt",
                base / "local_models" / "lama" / "simple_lama" / "big-lama.pt",
                base / "local_models" / "simple_lama" / "big-lama.pt",
                base / "local_models" / "big-lama.pt",
            ])
        for path in candidates:
            try:
                if path.exists() and path.is_file() and path.stat().st_size > 1024:
                    return str(path)
            except Exception:
                continue
        return ""

    def _ascii_safe_local_lama_model_path(self, src_path):
        """Return a model path that torch.jit.load can open safely on Windows.

        일부 Windows/PyTorch 조합에서는 torchscript 모델 경로에 한글 같은 비 ASCII 문자가
        들어가면 C++ fopen 단계에서 errno 42(Illegal byte sequence)가 발생할 수 있다.
        프로젝트 경로가 한글이어도 LOCAL LaMa가 동작하도록, local_models/lama/big-lama.pt를
        ASCII 경로의 사용자 캐시로 복사한 뒤 그 경로를 LAMA_MODEL에 넘긴다.
        """
        if not src_path:
            return ""
        try:
            src = Path(src_path)
            if not src.exists() or not src.is_file():
                return str(src_path)
        except Exception:
            return str(src_path)

        try:
            str(src).encode("ascii")
            return str(src)
        except Exception:
            pass

        import shutil

        candidates = []
        local_appdata = os.environ.get("LOCALAPPDATA")
        if local_appdata:
            candidates.append(Path(local_appdata) / "YSBTranslator" / "local_models" / "lama" / "big-lama.pt")

        # 최후 fallback: 드라이브 루트의 ASCII 폴더. 권한 문제 가능성이 있어 두 번째 후보로만 사용한다.
        try:
            drive = Path(src.anchor or "C:/")
            candidates.append(drive / "YSBTranslatorCache" / "local_models" / "lama" / "big-lama.pt")
        except Exception:
            candidates.append(Path("C:/YSBTranslatorCache/local_models/lama/big-lama.pt"))

        last_error = None
        for dst in candidates:
            try:
                dst.parent.mkdir(parents=True, exist_ok=True)
                need_copy = True
                if dst.exists():
                    try:
                        need_copy = (dst.stat().st_size != src.stat().st_size)
                    except Exception:
                        need_copy = True
                if need_copy:
                    shutil.copy2(str(src), str(dst))
                str(dst).encode("ascii")
                print(f">>> [Local Inpaint] Staged LaMa model to ASCII path: {dst}")
                return str(dst)
            except Exception as e:
                last_error = e
                continue

        print(f">>> [Local Inpaint] WARN: failed to stage LaMa model to ASCII path: {last_error}")
        return str(src)

    def _call_local_lama(self, image_path, mask_img):
        """Run local LaMa inpainting using simple-lama-inpainting.

        Returns PNG bytes so the existing inpainting workers can reuse the same
        result pipeline used for API providers.
        """
        from io import BytesIO
        from PIL import Image
        import numpy as np

        # simple-lama-inpainting은 LAMA_MODEL 환경변수를 지원한다.
        # local_models/lama/big-lama.pt가 있으면 자동 다운로드/cache 대신 그 파일을 사용한다.
        local_model_path = self._find_local_lama_model_path()
        if local_model_path:
            safe_model_path = self._ascii_safe_local_lama_model_path(local_model_path)
            os.environ["LAMA_MODEL"] = safe_model_path
            if safe_model_path != local_model_path:
                print(f">>> [Local Inpaint] LOCAL LaMa model: {local_model_path}")
                print(f">>> [Local Inpaint] LOCAL LaMa safe path: {safe_model_path}")
            else:
                print(f">>> [Local Inpaint] LOCAL LaMa model: {safe_model_path}")
        else:
            print(">>> [Local Inpaint] LOCAL LaMa model not found in local_models; using simple-lama cache/auto-download.")

        try:
            from simple_lama_inpainting import SimpleLama
        except Exception as e:
            raise ValueError(
                "LOCAL LaMa를 사용할 수 없습니다. setup_local_core_venv_v2_1_0.bat를 먼저 실행해 주세요. "
                f"원문 오류: {e}"
            )

        if not image_path or not os.path.exists(str(image_path)):
            raise ValueError("LOCAL LaMa 입력 이미지 파일을 찾을 수 없습니다.")

        image = Image.open(image_path).convert("RGB")
        mask_arr = np.asarray(mask_img)
        if mask_arr.ndim == 3:
            mask_arr = cv2.cvtColor(mask_arr, cv2.COLOR_BGR2GRAY)
        mask_arr = np.where(mask_arr > 10, 255, 0).astype("uint8")
        if mask_arr.shape[:2] != (image.height, image.width):
            mask_arr = cv2.resize(mask_arr, (image.width, image.height), interpolation=cv2.INTER_NEAREST)
        if int(np.count_nonzero(mask_arr)) <= 0:
            raise ValueError("LOCAL LaMa 인페인팅 마스크가 비어 있습니다.")
        mask = Image.fromarray(mask_arr, mode="L")

        model = getattr(self, "_local_lama_model", None)
        if model is None:
            print(">>> [Local Inpaint] Loading SimpleLaMa model...")
            model = SimpleLama()
            self._local_lama_model = model

        print(">>> [Local Inpaint] Running LOCAL LaMa...")
        result = model(image, mask)

        if isinstance(result, Image.Image):
            out_img = result.convert("RGB")
        else:
            arr = np.asarray(result)
            if arr.ndim == 3 and arr.shape[0] in (3, 4) and arr.shape[-1] not in (3, 4):
                arr = np.transpose(arr, (1, 2, 0))
            if arr.dtype != np.uint8:
                if arr.max() <= 1.5:
                    arr = arr * 255.0
                arr = np.clip(arr, 0, 255).astype("uint8")
            out_img = Image.fromarray(arr).convert("RGB")

        bio = BytesIO()
        out_img.save(bio, format="PNG")
        return bio.getvalue()

    def _call_gemini_inpaint(self, image_path, mask_img):
        """Gemini image model을 이용한 테스트용 인페인팅.

        Gemini는 LaMa처럼 별도 mask 파라미터를 가진 전용 인페인팅 API가 아니라,
        원본 이미지 + 마스크 이미지 + 프롬프트를 함께 주고 이미지 편집 결과를 받는 방식이다.
        그래서 결과 품질은 모델/프롬프트/원본에 따라 달라질 수 있다.
        """
        import base64

        key = str(getattr(Config, "GEMINI_API_KEY", "") or "").strip()
        if not key:
            raise ValueError("Gemini API Key가 비어있습니다.")

        model = str(getattr(Config, "GEMINI_INPAINT_MODEL", "") or "gemini-2.5-flash-image").strip()
        # gemini-2.5-flash-image-preview has been shut down; keep old cache/config from breaking.
        if model == "gemini-2.5-flash-image-preview":
            model = "gemini-2.5-flash-image"
        prompt = str(getattr(Config, "GEMINI_INPAINT_PROMPT", "") or "").strip()
        if not prompt:
            prompt = (
                "Remove the text only inside the white mask area and reconstruct the original manga background. "
                "Keep all characters, panel borders, screentones, line art, and unmasked areas unchanged. "
                "Return only the edited full image."
            )

        def _file_part(path):
            ext = os.path.splitext(str(path))[1].lower()
            mime = "image/png"
            if ext in (".jpg", ".jpeg"):
                mime = "image/jpeg"
            elif ext == ".webp":
                mime = "image/webp"
            with open(path, "rb") as f:
                data = base64.b64encode(f.read()).decode("ascii")
            return {"inlineData": {"mimeType": mime, "data": data}}

        ok, mask_png = cv2.imencode(".png", mask_img)
        if not ok:
            raise ValueError("Gemini 인페인팅용 마스크 PNG 생성 실패")
        mask_part = {
            "inlineData": {
                "mimeType": "image/png",
                "data": base64.b64encode(mask_png.tobytes()).decode("ascii"),
            }
        }

        instruction = (
            prompt
            + "\n\nThe first image is the source manga page. The second image is a black-and-white mask. "
            + "White pixels mark the exact area to edit. Black pixels must remain unchanged. "
            + "Return a full-size edited image, not a crop."
        )

        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": instruction},
                        _file_part(image_path),
                        mask_part,
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
            },
        }

        r = requests.post(url, params={"key": key}, json=payload, timeout=180)
        if r.status_code != 200:
            err_text = r.text[:800]
            try:
                err = r.json().get("error", {})
                msg = str(err.get("message", "") or err_text)
                code = int(err.get("code", r.status_code) or r.status_code)
            except Exception:
                msg = err_text
                code = r.status_code
            if code == 404 and "gemini-2.5-flash-image-preview" in msg:
                raise ValueError(
                    "Gemini Inpaint Error: 404 / gemini-2.5-flash-image-preview 모델은 더 이상 사용할 수 없습니다. "
                    "API 설정의 Gemini 인페인팅 모델을 gemini-2.5-flash-image로 바꿔주세요. "
                    f"원문: {msg[:400]}"
                )
            raise ValueError(f"Gemini Inpaint Error: {code} / {msg[:500]}")

        data = r.json()
        parts = []
        try:
            parts = data.get("candidates", [])[0].get("content", {}).get("parts", []) or []
        except Exception:
            parts = []

        text_notes = []
        for part in parts:
            inline = part.get("inlineData") or part.get("inline_data") or {}
            image_b64 = inline.get("data")
            if image_b64:
                return base64.b64decode(image_b64)
            if part.get("text"):
                text_notes.append(str(part.get("text") or ""))

        raise ValueError("Gemini 인페인팅 이미지 응답이 비어있습니다. " + " ".join(text_notes)[:300])

    def _normalize_stable_model_name(self, model_name):
        model_name = str(model_name or "").strip()
        # 버전 없는 slug만 입력하면 Replicate 클라이언트/환경에 따라 404가 날 수 있어
        # 공식 최신 버전 해시를 기본으로 붙인다.
        if model_name == "stability-ai/stable-diffusion-inpainting":
            return "stability-ai/stable-diffusion-inpainting:95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3"
        return model_name

    def _replicate_run_isolated(self, model_name, input_payload, api_token):
        """Replicate 호출을 provider별 토큰으로 분리해서 실행한다.

        과거에는 REPLICATE_API_TOKEN 환경변수 하나를 LaMa/Stable이 공유했다.
        이 함수는 각 호출 시점에 LaMa 토큰 또는 Stable 토큰을 명시해서 사용하므로,
        한쪽 API 설정이 다른 쪽 인페인팅에 섞이지 않는다.
        """
        import replicate
        api_token = str(api_token or "").strip()
        if api_token:
            try:
                client = replicate.Client(api_token=api_token)
                return client.run(model_name, input=input_payload)
            except TypeError:
                # 매우 구버전 replicate 클라이언트 대비 fallback
                pass
            except AttributeError:
                pass

            old_token = os.environ.get("REPLICATE_API_TOKEN")
            os.environ["REPLICATE_API_TOKEN"] = api_token
            try:
                return replicate.run(model_name, input=input_payload)
            finally:
                if old_token is None:
                    os.environ.pop("REPLICATE_API_TOKEN", None)
                else:
                    os.environ["REPLICATE_API_TOKEN"] = old_token

        return replicate.run(model_name, input=input_payload)

    def _call_stable_inpaint(self, image_path, mask_img):
        import replicate
        model_name = self._normalize_stable_model_name(getattr(Config, "STABLE_INPAINT_MODEL", ""))
        if not model_name:
            raise ValueError("Stable Diffusion 인페인팅 모델명이 비어있습니다.")
        prompt = str(getattr(Config, "STABLE_INPAINT_PROMPT", "") or "remove text and restore the original background")
        temp_mask = f"temp_mask_stable_{uuid.uuid4().hex}.png"
        cv2.imwrite(temp_mask, mask_img)

        def _run_with_input(extra_input):
            with open(image_path, "rb") as img_file, open(temp_mask, "rb") as mask_file:
                base_input = {
                    "image": img_file,
                    "mask": mask_file,
                    "prompt": prompt,
                }
                base_input.update(extra_input or {})
                token = str(getattr(Config, "STABLE_REPLICATE_API_TOKEN", "") or getattr(Config, "REPLICATE_API_TOKEN", "") or "").strip()
                return self._replicate_run_isolated(model_name, base_input, token)

        try:
            try:
                return _run_with_input({
                    "num_outputs": 1,
                    "num_inference_steps": 30,
                    "guidance_scale": 7.5,
                    "disable_safety_checker": True,
                })
            except Exception as e:
                err_text = str(e)
                # 입력 스키마가 모델 버전에 따라 다를 수 있으므로, 입력값 불일치 계열이면 최소 입력으로 한 번 더 시도한다.
                input_schema_error = any(token in err_text.lower() for token in [
                    "invalid input", "is not a valid", "unknown", "extra", "schema", "422"
                ])
                if input_schema_error:
                    return _run_with_input({})
                if "404" in err_text or "not found" in err_text.lower():
                    raise ValueError(
                        "Stable Diffusion 인페인팅 모델을 찾을 수 없습니다. "
                        "모델명을 stability-ai/stable-diffusion-inpainting:95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3 형식으로 입력해 주세요. "
                        f"원문 오류: {err_text[:300]}"
                    )
                raise
        finally:
            if os.path.exists(temp_mask):
                try:
                    os.remove(temp_mask)
                except Exception:
                    pass

    def _call_lama(self, image_path, mask_img):
        import time
        import re

        model_name = str(getattr(Config, "INPAINT_MODEL", "") or getattr(Config, "REPAINT_MODEL", "") or "").strip()
        if not model_name:
            raise ValueError("인페인팅 모델명이 비어있습니다. 옵션 > API 관리에서 모델명을 입력해 주세요.")

        if mask_img is None:
            raise ValueError("LaMa 인페인팅 마스크가 없습니다.")
        try:
            if int(cv2.countNonZero(mask_img)) <= 0:
                raise ValueError("LaMa 인페인팅 마스크가 비어 있습니다.")
        except ValueError:
            raise
        except Exception:
            pass

        def _write_temp_mask(mask_arr):
            temp_mask_path = os.path.join(tempfile.gettempdir(), f"temp_mask_lama_{uuid.uuid4().hex}.png")
            ok = cv2.imwrite(temp_mask_path, mask_arr)
            if not ok or not os.path.exists(temp_mask_path):
                raise ValueError("LaMa 임시 마스크 파일을 저장하지 못했습니다.")
            return temp_mask_path

        def _write_oom_resized_request(src_path, src_mask, *, max_side, max_pixels):
            img_arr = cv2.imdecode(np.fromfile(str(src_path), np.uint8), cv2.IMREAD_COLOR)
            if img_arr is None:
                return None, None, None
            h, w = img_arr.shape[:2]
            total_pixels = int(w) * int(h)
            scale = 1.0
            if max_side and max(w, h) > int(max_side):
                scale = min(scale, float(max_side) / float(max(w, h)))
            if max_pixels and total_pixels > int(max_pixels):
                scale = min(scale, float(int(max_pixels) / float(total_pixels)) ** 0.5)
            if scale >= 0.999:
                return None, None, None

            tw = max(1, int(round(w * scale)))
            th = max(1, int(round(h * scale)))
            resized = cv2.resize(img_arr, (tw, th), interpolation=cv2.INTER_AREA)
            out_path = os.path.join(tempfile.gettempdir(), f"ysb_lama_oom_retry_{uuid.uuid4().hex}_{tw}x{th}.jpg")
            ok, buf = cv2.imencode(".jpg", resized, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
            if not ok:
                return None, None, None
            buf.tofile(out_path)

            resized_mask = src_mask
            if src_mask is not None:
                try:
                    resized_mask = cv2.resize(src_mask, (tw, th), interpolation=cv2.INTER_NEAREST)
                except Exception:
                    resized_mask = src_mask
            return out_path, resized_mask, (w, h, tw, th)

        # Replicate 저크레딧/무료 상태에서는 burst=1 제한이 자주 걸린다.
        # 개별 인페인팅은 한 번만 보내서 괜찮지만, 일괄은 연속 호출이라 429가 나기 쉽다.
        max_retries = 6
        base_wait_seconds = 12
        last_error = None
        token = str(getattr(Config, "LAMA_REPLICATE_API_TOKEN", "") or getattr(Config, "REPLICATE_API_TOKEN", "") or "").strip()

        current_image_path = str(image_path)
        current_mask_img = mask_img
        temp_request_paths = []
        oom_retry_count = 0

        try:
            attempt = 1
            while attempt <= max_retries:
                temp_mask = None
                mask_file = None
                img_file = None

                try:
                    temp_mask = _write_temp_mask(current_mask_img)
                    mask_file = open(temp_mask, "rb")
                    img_file = open(current_image_path, "rb")

                    lama_input = {
                        "image": img_file,
                        "mask": mask_file,
                    }
                    output = self._replicate_run_isolated(model_name, lama_input, token)
                    if not output:
                        raise ValueError("Replicate LaMa가 빈 결과를 반환했습니다.")
                    return output

                except Exception as e:
                    last_error = e
                    err_text = str(e)
                    err_lower = err_text.lower()
                    print(f"LaMa Error attempt {attempt}/{max_retries}: {err_text}")

                    is_rate_limit = (
                        "429" in err_text
                        or "throttled" in err_lower
                        or "rate limit" in err_lower
                    )
                    is_cuda_oom = (
                        "cuda out of memory" in err_lower
                        or "outofmemoryerror" in err_lower
                        or ("out of memory" in err_lower and "cuda" in err_lower)
                    )

                    if is_cuda_oom and oom_retry_count < 2:
                        # Replicate T4 공유 GPU에서 2k~3k 입력도 OOM이 날 수 있다.
                        # 원본 프로젝트는 건드리지 않고, LaMa 요청용 파일만 한 번 더 줄여 재시도한다.
                        oom_retry_count += 1
                        target_side = 2200 if oom_retry_count == 1 else 1800
                        target_pixels = 4_000_000 if oom_retry_count == 1 else 2_800_000
                        resized_path, resized_mask, shape_info = _write_oom_resized_request(
                            current_image_path,
                            current_mask_img,
                            max_side=target_side,
                            max_pixels=target_pixels,
                        )
                        if resized_path and resized_mask is not None and shape_info:
                            temp_request_paths.append(resized_path)
                            current_image_path = resized_path
                            current_mask_img = resized_mask
                            ow, oh, nw, nh = shape_info
                            print(f"LaMa CUDA OOM fallback resize: {ow}x{oh} -> {nw}x{nh}")
                            attempt += 1
                            continue

                    if is_rate_limit and attempt < max_retries:
                        # Replicate 메시지에 "resets in ~5s" 같은 값이 있으면 그보다 조금 더 기다린다.
                        wait_seconds = base_wait_seconds + (attempt - 1) * 8
                        m = re.search(r"resets in ~?(\d+)s", err_text)
                        if m:
                            wait_seconds = max(wait_seconds, int(m.group(1)) + 4)

                        print(f"LaMa Rate Limit: {wait_seconds}s 대기 후 재시도")
                        time.sleep(wait_seconds)
                        attempt += 1
                        continue

                    raise ValueError(f"Replicate LaMa 인페인팅 실패: {err_text}") from e

                finally:
                    if mask_file:
                        try:
                            mask_file.close()
                        except Exception:
                            pass
                    if img_file:
                        try:
                            img_file.close()
                        except Exception:
                            pass
                    if temp_mask and os.path.exists(temp_mask):
                        try:
                            os.remove(temp_mask)
                        except Exception:
                            pass

            if last_error is not None:
                raise ValueError(f"Replicate LaMa 인페인팅 실패: {last_error}") from last_error
            raise ValueError("Replicate LaMa 인페인팅 실패: 알 수 없는 오류")

        finally:
            for path in temp_request_paths:
                try:
                    if path and os.path.exists(path):
                        os.remove(path)
                except Exception:
                    pass

    # ---------------------------------------------------------
    # [CORE] 출력
    # ---------------------------------------------------------
    def export_project_result(self, data, img_path, bg_data, font_name, stroke_size, fixed_font_size, output_root=None, output_name_stem=None, clean_name_stem=None, output_image_format=None, clean_image_format=None, output_image_quality=95, clean_image_quality=95):
        """
        결과 출력:
        - project_dir/clean/Clean_XXXX.png: 인페인팅된 배경
        - project_dir/result/Result_XXXX.png: 최종 화면 이미지(텍스트 포함)
        - project_dir/scripts/Script_XXXX.jsx: 포토샵 텍스트 레이어 생성 스크립트
        - Photoshop 실행 완료 알림(alert)은 띄우지 않음
        """
        import io
        _ensure_pillow()

        def _hex_to_rgb(value, fallback=(0, 0, 0)):
            value = str(value or '').strip()
            if value.startswith('#'):
                value = value[1:]
            try:
                if len(value) == 6:
                    return tuple(int(value[i:i+2], 16) for i in (0, 2, 4))
            except Exception:
                pass
            return fallback

        def _load_pil_image(src):
            if src is None:
                return None
            try:
                if isinstance(src, (bytes, bytearray)):
                    if len(src) == 0:
                        return None
                    return Image.open(io.BytesIO(src)).convert('RGB')
                if isinstance(src, np.ndarray):
                    if src.size == 0:
                        return None
                    if src.ndim == 2:
                        return Image.fromarray(src).convert('RGB')
                    return Image.fromarray(cv2.cvtColor(src, cv2.COLOR_BGR2RGB)).convert('RGB')
                if isinstance(src, str) and os.path.exists(src):
                    return Image.open(src).convert('RGB')
            except Exception:
                return None
            return None

        def _font_key(value):
            return ''.join(ch for ch in str(value or '').lower() if ch.isalnum() or ('가' <= ch <= '힣') or ('ぁ' <= ch <= 'ヿ') or ('一' <= ch <= '龯'))

        def _font_dirs():
            dirs = []
            env_keys = ["WINDIR", "SystemRoot", "LOCALAPPDATA", "HOME"]
            for key in env_keys:
                base = os.environ.get(key)
                if not base:
                    continue
                if key in ("WINDIR", "SystemRoot"):
                    dirs.append(os.path.join(base, "Fonts"))
                elif key == "LOCALAPPDATA":
                    dirs.append(os.path.join(base, "Microsoft", "Windows", "Fonts"))
                elif key == "HOME":
                    dirs.extend([
                        os.path.join(base, ".fonts"),
                        os.path.join(base, "Library", "Fonts"),
                    ])
            dirs.extend([
                r"C:\Windows\Fonts",
                "/System/Library/Fonts",
                "/Library/Fonts",
                "/usr/share/fonts",
                "/usr/local/share/fonts",
            ])
            out = []
            for d in dirs:
                if d and d not in out and os.path.isdir(d):
                    out.append(d)
            return out

        def _iter_font_files():
            exts = ('.ttf', '.ttc', '.otf')
            for root in _font_dirs():
                try:
                    for dirpath, _dirnames, filenames in os.walk(root):
                        for fn in filenames:
                            if fn.lower().endswith(exts):
                                yield os.path.join(dirpath, fn)
                except Exception:
                    continue

        def _find_font_file(name):
            raw = str(name or '').strip()
            if raw and os.path.exists(raw):
                return raw

            wanted = _font_key(raw)
            alias_files = {
                # Windows Korean/CJK fonts
                '맑은고딕': ['malgun.ttf', 'malgunbd.ttf', 'malgunsl.ttf'],
                'malgungothic': ['malgun.ttf', 'malgunbd.ttf', 'malgunsl.ttf'],
                'malgun': ['malgun.ttf', 'malgunbd.ttf', 'malgunsl.ttf'],
                '굴림': ['gulim.ttc'],
                'gulim': ['gulim.ttc'],
                'gulimgothic': ['gulim.ttc'],
                '돋움': ['gulim.ttc'],
                'dotum': ['gulim.ttc'],
                '바탕': ['batang.ttc'],
                'batang': ['batang.ttc'],
                '궁서': ['batang.ttc'],
                'gungsuh': ['batang.ttc'],
                # Windows Japanese fonts
                'msgothic': ['msgothic.ttc'],
                'mspgothic': ['msgothic.ttc'],
                'msuigothic': ['msgothic.ttc'],
                'meiryo': ['meiryo.ttc', 'meiryob.ttc'],
                'yugothic': ['YuGothM.ttc', 'YuGothR.ttc', 'YuGothB.ttc', 'YuGothL.ttc'],
                'yu gothic': ['YuGothM.ttc', 'YuGothR.ttc', 'YuGothB.ttc', 'YuGothL.ttc'],
                # Common CJK fonts
                'notosanscjk': ['NotoSansCJK-Regular.ttc', 'NotoSansCJKkr-Regular.otf', 'NotoSansCJKjp-Regular.otf'],
                'notosanskr': ['NotoSansCJKkr-Regular.otf'],
                'notosansjp': ['NotoSansCJKjp-Regular.otf'],
            }

            # 1) Known family aliases → known filenames
            for key, filenames in alias_files.items():
                if wanted and (wanted == _font_key(key) or wanted in _font_key(key) or _font_key(key) in wanted):
                    for root in _font_dirs():
                        for fn in filenames:
                            path = os.path.join(root, fn)
                            if os.path.exists(path):
                                return path

            # 2) Filename fuzzy search
            if wanted:
                for path in _iter_font_files():
                    stem = _font_key(os.path.splitext(os.path.basename(path))[0])
                    if wanted == stem or wanted in stem or stem in wanted:
                        return path

            # 3) CJK-capable fallback fonts. Avoid Arial because it often renders CJK as □.
            fallback_names = [
                'malgun.ttf', 'gulim.ttc', 'msgothic.ttc', 'meiryo.ttc',
                'YuGothM.ttc', 'YuGothR.ttc', 'NotoSansCJK-Regular.ttc',
                'NotoSansCJKkr-Regular.otf', 'NotoSansCJKjp-Regular.otf',
                'AppleGothic.ttf', 'Hiragino Sans GB.ttc',
            ]
            for root in _font_dirs():
                for fn in fallback_names:
                    path = os.path.join(root, fn)
                    if os.path.exists(path):
                        return path
            return raw or None

        def _get_font(name, size):
            font_path = _find_font_file(name)
            try:
                if font_path:
                    return ImageFont.truetype(str(font_path), int(size))
            except Exception:
                pass
            # 마지막 안전장치: 시스템 폰트 중 CJK 가능성이 높은 파일을 순회한다.
            for path in _iter_font_files():
                if _font_key(os.path.basename(path)) in ('malgun', 'gulim', 'msgothic', 'meiryo'):
                    try:
                        return ImageFont.truetype(path, int(size))
                    except Exception:
                        continue
            return ImageFont.load_default()

        abs_img_path = os.path.abspath(img_path)
        img_dir = os.path.dirname(abs_img_path)

        # 출력 위치는 가능하면 호출자가 넘긴 실제 프로젝트 폴더를 우선한다.
        # 자동저장 OFF 상태에서는 self.paths가 작업 캐시(work_sessions) 내부 images를 가리킬 수 있다.
        # 이때 img_path 기준으로 출력 폴더를 추정하면 Result/scripts가 작업 캐시에 생겨 사용자가 찾지 못한다.
        # 따라서 main/worker에서 output_root=self.project_dir을 넘겨 실제 프로젝트 폴더에 출력한다.
        if output_root:
            project_dir = os.path.abspath(str(output_root))
        elif os.path.basename(img_dir).lower() == "images":
            project_dir = os.path.abspath(os.path.join(img_dir, ".."))
        else:
            project_dir = os.path.abspath(os.path.join(os.getcwd(), "Project_Result"))

        clean_dir = os.path.join(project_dir, "clean")
        result_dir = os.path.join(project_dir, "result")
        scripts_dir = os.path.join(project_dir, "scripts")
        os.makedirs(clean_dir, exist_ok=True)
        os.makedirs(result_dir, exist_ok=True)
        os.makedirs(scripts_dir, exist_ok=True)

        def _norm_fmt(v):
            v = str(v or "png").strip().lower().lstrip(".")
            if v in ("jpeg", "jpe"):
                v = "jpg"
            if v in ("wep", "wbp"):
                v = "webp"
            return v if v in ("png", "jpg", "webp") else "png"

        def _ext_for_fmt(v):
            v = _norm_fmt(v)
            if v == "jpg":
                return ".jpg"
            if v == "webp":
                return ".webp"
            return ".png"

        def _pil_fmt(v):
            v = _norm_fmt(v)
            if v == "jpg":
                return "JPEG"
            if v == "webp":
                return "WEBP"
            return "PNG"

        def _quality(v):
            try:
                q = int(v)
            except Exception:
                q = 95
            return max(1, min(100, q))

        def _remove_same_stem_variants(folder, stem, prefix=""):
            try:
                for ext in (".png", ".jpg", ".jpeg", ".webp"):
                    p = os.path.join(folder, f"{prefix}{stem}{ext}")
                    if os.path.exists(p):
                        try:
                            os.remove(p)
                        except Exception:
                            pass
            except Exception:
                pass

        def _save_pil_for_output(img, path, fmt, quality):
            fmt = _norm_fmt(fmt)
            q = _quality(quality)
            out = img
            params = {}
            if fmt == "jpg":
                if out.mode in ("RGBA", "LA") or (out.mode == "P" and "transparency" in getattr(out, "info", {})):
                    bg = Image.new("RGB", out.size, (255, 255, 255))
                    try:
                        bg.paste(out, mask=out.getchannel("A"))
                    except Exception:
                        bg.paste(out.convert("RGB"))
                    out = bg
                else:
                    out = out.convert("RGB")
                params.update({"quality": q, "subsampling": 0, "optimize": True})
            elif fmt == "webp":
                if out.mode == "P":
                    out = out.convert("RGBA")
                params.update({"quality": q, "method": 6})
            else:
                params.update({"optimize": True})
            out.save(path, _pil_fmt(fmt), **params)

        output_fmt = _norm_fmt(output_image_format)
        clean_fmt = _norm_fmt(clean_image_format)
        output_quality = _quality(output_image_quality)
        clean_quality = _quality(clean_image_quality)

        # img_path는 실제 존재하는 원본 이미지 경로로 쓴다.
        # Result 파일명은 사용자가 정한 출력 표시명(output_name_stem)을 따른다.
        # Clean 파일명은 반드시 원본 페이지 파일명 stem을 따르되, 클린본임을 알 수 있게 clean_ 접두사를 붙인다.
        # 예: 원본 001.png + 클린 형식 webp => clean/clean_001.webp
        result_stem = str(output_name_stem or "").strip()
        if not result_stem:
            result_stem = os.path.splitext(os.path.basename(img_path))[0]
        result_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", result_stem).strip(" .") or "output"

        clean_source_stem = str(clean_name_stem or "").strip()
        if not clean_source_stem:
            clean_source_stem = os.path.splitext(os.path.basename(img_path))[0]
        clean_source_stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", clean_source_stem).strip(" .") or "clean"
        clean_stem = clean_source_stem if clean_source_stem.lower().startswith("clean_") else f"clean_{clean_source_stem}"

        clean_img_name = f"{clean_stem}{_ext_for_fmt(clean_fmt)}"
        result_img_name = f"Result_{result_stem}{_ext_for_fmt(output_fmt)}"
        clean_img_path = os.path.join(clean_dir, clean_img_name)
        result_img_path = os.path.join(result_dir, result_img_name)

        # 출력 형식을 바꿔 다시 출력하면 같은 stem의 기존 PNG/JPG/WebP는 중복 보관하지 않고
        # 새 형식 파일 하나로 갈아탄다.
        _remove_same_stem_variants(clean_dir, clean_stem, "")
        _remove_same_stem_variants(result_dir, result_stem, "Result_")
        # 직전 버전에서 잘못 생성된 접두사 없는 원본명 클린본과 Clean_출력명 클린본도 같이 정리한다.
        _remove_same_stem_variants(clean_dir, clean_source_stem, "")
        _remove_same_stem_variants(clean_dir, result_stem, "Clean_")

        bg_img = _load_pil_image(bg_data)
        if bg_img is None:
            bg_img = _load_pil_image(img_path)
        if bg_img is not None:
            _save_pil_for_output(bg_img, clean_img_path, clean_fmt, clean_quality)

        def _font_candidates_for_js(name):
            raw = str(name or '').strip()
            candidates = []

            def add(v):
                v = str(v or '').strip()
                if v and v not in candidates:
                    candidates.append(v)

            add(raw)
            # Qt/Windows font combo strings may contain style hints such as "(OTF)" or trailing numbers.
            cleaned = raw
            if '(' in cleaned:
                cleaned = cleaned.split('(')[0].strip()
            # Remove trailing standalone numeric/style fragments often added by font display names.
            parts = cleaned.split()
            while parts and parts[-1].isdigit():
                parts.pop()
            cleaned = ' '.join(parts).strip()
            add(cleaned)

            compact = cleaned.replace(' ', '').replace('-', '').replace('_', '')
            add(compact)

            key = _font_key(cleaned or raw)
            alias = {
                '맑은고딕': ['Malgun Gothic', 'MalgunGothic', 'MalgunGothicRegular', 'MalgunGothicBold'],
                'malgungothic': ['Malgun Gothic', 'MalgunGothic', 'MalgunGothicRegular', 'MalgunGothicBold'],
                'malgun': ['Malgun Gothic', 'MalgunGothic', 'MalgunGothicRegular', 'MalgunGothicBold'],
                '굴림': ['Gulim', 'GulimChe'],
                'gulim': ['Gulim', 'GulimChe'],
                '돋움': ['Dotum', 'DotumChe'],
                'dotum': ['Dotum', 'DotumChe'],
                '바탕': ['Batang', 'BatangChe'],
                'batang': ['Batang', 'BatangChe'],
                '궁서': ['Gungsuh', 'GungsuhChe'],
                'gungsuh': ['Gungsuh', 'GungsuhChe'],
                'msgothic': ['MSGothic', 'MS Gothic', 'MS-Gothic'],
                'mspgothic': ['MSPGothic', 'MS PGothic', 'MS-PGothic'],
                'meiryo': ['Meiryo', 'MeiryoUI'],
                'yugothic': ['YuGothic', 'Yu Gothic', 'YuGothic-Regular'],
                'notosanskr': ['NotoSansCJKkr-Regular', 'Noto Sans CJK KR'],
                'notosansjp': ['NotoSansCJKjp-Regular', 'Noto Sans CJK JP'],
            }
            for k, vals in alias.items():
                if key and (key == _font_key(k) or key in _font_key(k) or _font_key(k) in key):
                    for v in vals:
                        add(v)
            return candidates

        layers_list = []
        for d in data:
            if not d.get('use_inpaint', True):
                continue
            # 번역문이 비어 있으면 최종 화면/스크립트 모두 텍스트를 만들지 않는다.
            text = str(d.get('translated_text', '') or '')
            if not text.strip():
                continue
            item_font = d.get('font_family') or font_name
            item_size = int(d.get('font_size', fixed_font_size) or fixed_font_size)
            item_stroke = int(d.get('stroke_width', stroke_size) or 0)
            item_text_color = d.get('text_color') or '#000000'
            item_stroke_color = d.get('stroke_color') or '#FFFFFF'
            item_align = str(d.get('align') or 'center').lower()
            if item_align not in ('left', 'center', 'right'):
                item_align = 'center'
            wrapped = text.replace('\n', '\r')
            layers_list.append({
                "text": wrapped,
                "plain_text": text,
                "x": d['rect'][0] + d.get('x_off', 0),
                "y": d['rect'][1] + d.get('y_off', 0),
                "w": d['rect'][2],
                "h": d['rect'][3],
                "size": item_size,
                "font": item_font,
                "fontCandidates": _font_candidates_for_js(item_font),
                "stroke": item_stroke,
                "textColor": item_text_color,
                "strokeColor": item_stroke_color,
                "align": item_align,
                "lineSpacing": int(d.get('line_spacing', 100) or 100),
                "letterSpacing": int(d.get('letter_spacing', 0) or 0),
                "charWidth": int(d.get('char_width', 100) or 100),
                "charHeight": int(d.get('char_height', 100) or 100),
                "bold": bool(d.get('bold', False)),
                "italic": bool(d.get('italic', False)),
                "strike": bool(d.get('strike', False)),
                "rotation": float(d.get('rotation', 0) or 0),
                "shadowEnabled": bool(d.get('text_shadow_enabled', False)),
                "shadowColor": d.get('text_shadow_color') or '#000000',
                "shadowOpacity": int(d.get('text_shadow_opacity', 45) or 45),
                "shadowOffsetX": int(d.get('text_shadow_offset_x', 3) or 3),
                "shadowOffsetY": int(d.get('text_shadow_offset_y', 3) or 3),
                "shadowBlur": int(d.get('text_shadow_blur', 4) or 4),
                "glowEnabled": bool(d.get('text_glow_enabled', False)),
                "glowColor": d.get('text_glow_color') or '#FFFFFF',
                "glowOpacity": int(d.get('text_glow_opacity', 35) or 35),
                "glowOffsetX": int(d.get('text_glow_offset_x', 0) or 0),
                "glowOffsetY": int(d.get('text_glow_offset_y', 0) or 0),
                "glowSize": int(d.get('text_glow_size', 3) or 3),
                "glowBlur": int(d.get('text_glow_blur', 8) or 8),
            })

        # Result 폴더용 최종 이미지 렌더링. 포토샵 레이어만큼 정교하진 않아도 검수용 이미지로 바로 쓸 수 있게 저장한다.
        def _text_bbox_single(draw_obj, text_value, font_obj, stroke_w=0):
            try:
                return draw_obj.textbbox((0, 0), text_value, font=font_obj, stroke_width=stroke_w)
            except Exception:
                w, h = draw_obj.textsize(text_value, font=font_obj)
                return (0, 0, w, h)

        def _synthetic_bold_offsets_for_font(font_obj, bold=False):
            if not bold:
                return [(0, 0)]
            try:
                size = int(getattr(font_obj, 'size', 24) or 24)
            except Exception:
                size = 24
            # G단계: 출력 이미지에서도 B 버튼이 켜지면 확실히 두꺼워지도록
            # 원형에 가까운 대칭 오프셋을 사용한다.
            radius = max(1, min(10, int(round(size * 0.095))))
            offsets = [(0, 0)]
            for r in range(1, radius + 1):
                offsets.extend([(r, 0), (-r, 0), (0, r), (0, -r)])
                if r <= max(1, radius // 2):
                    offsets.extend([(r, r), (-r, r), (r, -r), (-r, -r)])
            seen = set()
            unique = []
            for item in offsets:
                if item in seen:
                    continue
                seen.add(item)
                unique.append(item)
            return unique

        def _draw_text_line(draw_obj, pos, line_text, font_obj, fill, stroke_w, stroke_fill, letter_spacing=0, bold=False):
            x0, y0 = pos
            offsets = _synthetic_bold_offsets_for_font(font_obj, bold)
            if not letter_spacing:
                for ox, oy in offsets:
                    draw_obj.text((x0 + ox, y0 + oy), line_text, font=font_obj, fill=fill,
                                  stroke_width=stroke_w, stroke_fill=stroke_fill)
                try:
                    box = draw_obj.textbbox((x0, y0), line_text, font=font_obj, stroke_width=stroke_w)
                    return box[2] - box[0]
                except Exception:
                    return draw_obj.textsize(line_text, font=font_obj)[0]

            cursor_x = x0
            for ch in line_text:
                for ox, oy in offsets:
                    draw_obj.text((cursor_x + ox, y0 + oy), ch, font=font_obj, fill=fill,
                                  stroke_width=stroke_w, stroke_fill=stroke_fill)
                try:
                    box = draw_obj.textbbox((0, 0), ch, font=font_obj, stroke_width=stroke_w)
                    char_w = box[2] - box[0]
                except Exception:
                    char_w = draw_obj.textsize(ch, font=font_obj)[0]
                cursor_x += char_w + int(letter_spacing)
            return cursor_x - x0

        def _measure_line(draw_obj, line_text, font_obj, stroke_w=0, letter_spacing=0):
            if not line_text:
                return 0
            if not letter_spacing:
                try:
                    box = draw_obj.textbbox((0, 0), line_text, font=font_obj, stroke_width=stroke_w)
                    return box[2] - box[0]
                except Exception:
                    return draw_obj.textsize(line_text, font=font_obj)[0]
            total = 0
            for i, ch in enumerate(line_text):
                try:
                    box = draw_obj.textbbox((0, 0), ch, font=font_obj, stroke_width=stroke_w)
                    total += box[2] - box[0]
                except Exception:
                    total += draw_obj.textsize(ch, font=font_obj)[0]
                if i < len(line_text) - 1:
                    total += int(letter_spacing)
            return total

        def _rgba_from_hex(value, opacity_pct=100, fallback=(255, 255, 255)):
            rgb = _hex_to_rgb(value, fallback)
            try:
                alpha = max(0, min(255, int(round(float(opacity_pct or 0) * 255.0 / 100.0))))
            except Exception:
                alpha = 255
            return rgb + (alpha,)

        def _apply_text_post_effects(base_layer, shadow_spec=None, glow_spec=None):
            shadow_spec = shadow_spec or {}
            glow_spec = glow_spec or {}
            base_w, base_h = base_layer.size
            pad_left = pad_top = pad_right = pad_bottom = 0

            if bool(glow_spec.get('enabled', False)):
                glow_dx = int(glow_spec.get('dx', 0) or 0)
                glow_dy = int(glow_spec.get('dy', 0) or 0)
                glow_size = max(0, int(glow_spec.get('size', 0) or 0))
                glow_blur = max(0, int(glow_spec.get('blur', 0) or 0))
                extra = glow_size + glow_blur * 2 + 4
                pad_left = max(pad_left, max(0, -glow_dx) + extra)
                pad_top = max(pad_top, max(0, -glow_dy) + extra)
                pad_right = max(pad_right, max(0, glow_dx) + extra)
                pad_bottom = max(pad_bottom, max(0, glow_dy) + extra)

            if bool(shadow_spec.get('enabled', False)):
                dx = int(shadow_spec.get('dx', 0) or 0)
                dy = int(shadow_spec.get('dy', 0) or 0)
                blur = max(0, int(shadow_spec.get('blur', 0) or 0))
                pad_left = max(pad_left, max(0, -dx) + blur * 2 + 4)
                pad_top = max(pad_top, max(0, -dy) + blur * 2 + 4)
                pad_right = max(pad_right, max(0, dx) + blur * 2 + 4)
                pad_bottom = max(pad_bottom, max(0, dy) + blur * 2 + 4)

            if pad_left <= 0 and pad_top <= 0 and pad_right <= 0 and pad_bottom <= 0:
                return base_layer, 0, 0, base_w, base_h

            canvas = Image.new('RGBA', (base_w + pad_left + pad_right, base_h + pad_top + pad_bottom), (0, 0, 0, 0))
            alpha = base_layer.getchannel('A')

            if bool(glow_spec.get('enabled', False)):
                blur_radius = max(0.0, float(glow_spec.get('blur', 0) or 0) + float(glow_spec.get('size', 0) or 0) * 0.6)
                glow_alpha = alpha
                if blur_radius > 0:
                    glow_alpha = glow_alpha.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                glow_img = Image.new('RGBA', base_layer.size, _rgba_from_hex(glow_spec.get('color'), glow_spec.get('opacity', 35), (255, 255, 255)))
                glow_img.putalpha(glow_alpha.point(lambda a, s=max(0, min(255, _rgba_from_hex(glow_spec.get('color'), glow_spec.get('opacity', 35))[3])): int(a * s / 255)))
                glow_dx = int(glow_spec.get('dx', 0) or 0)
                glow_dy = int(glow_spec.get('dy', 0) or 0)
                canvas.alpha_composite(glow_img, (pad_left + glow_dx, pad_top + glow_dy))

            if bool(shadow_spec.get('enabled', False)):
                dx = int(shadow_spec.get('dx', 0) or 0)
                dy = int(shadow_spec.get('dy', 0) or 0)
                blur_radius = max(0.0, float(shadow_spec.get('blur', 0) or 0))
                shadow_alpha = alpha
                if blur_radius > 0:
                    shadow_alpha = shadow_alpha.filter(ImageFilter.GaussianBlur(radius=blur_radius))
                shadow_img = Image.new('RGBA', base_layer.size, _rgba_from_hex(shadow_spec.get('color'), shadow_spec.get('opacity', 45), (0, 0, 0)))
                shadow_img.putalpha(shadow_alpha.point(lambda a, s=max(0, min(255, _rgba_from_hex(shadow_spec.get('color'), shadow_spec.get('opacity', 45), (0,0,0))[3])): int(a * s / 255)))
                canvas.alpha_composite(shadow_img, (pad_left + dx, pad_top + dy))

            canvas.alpha_composite(base_layer, (pad_left, pad_top))
            return canvas, pad_left, pad_top, base_w, base_h

        if bg_img is not None:
            result_img = bg_img.copy().convert('RGB')
            for d in layers_list:
                font = _get_font(d.get('font'), d.get('size', fixed_font_size))
                text = d.get('plain_text', '')
                if not text.strip():
                    continue

                x = float(d['x'])
                y = float(d['y'])
                w = float(d['w'])
                align = d.get('align', 'center')
                stroke_w = int(d.get('stroke', 0) or 0)
                fill = _hex_to_rgb(d.get('textColor'), (0, 0, 0))
                stroke_fill = _hex_to_rgb(d.get('strokeColor'), (255, 255, 255))
                line_spacing_pct = max(50, min(300, int(d.get('lineSpacing', 100) or 100)))
                letter_spacing = int(d.get('letterSpacing', 0) or 0)
                char_w_pct = max(10, min(300, int(d.get('charWidth', 100) or 100)))
                char_h_pct = max(10, min(300, int(d.get('charHeight', 100) or 100)))
                bold = bool(d.get('bold', False))
                strike = bool(d.get('strike', False))
                italic = bool(d.get('italic', False))

                tmp_draw_probe = ImageDraw.Draw(result_img)
                lines = text.split('\n')
                try:
                    ascent, descent = font.getmetrics()
                    base_line_h = ascent + descent
                except Exception:
                    bbox = _text_bbox_single(tmp_draw_probe, "가A", font, stroke_w)
                    base_line_h = max(1, bbox[3] - bbox[1])
                    ascent = int(base_line_h * 0.8)

                line_h = max(1, int(base_line_h * (line_spacing_pct / 100.0)))
                widths = [_measure_line(tmp_draw_probe, line, font, stroke_w, letter_spacing) for line in lines]
                raw_w = max(widths or [1]) + stroke_w * 4 + 8
                raw_h = line_h * max(1, len(lines)) + stroke_w * 4 + 8

                layer = Image.new("RGBA", (max(1, int(raw_w)), max(1, int(raw_h))), (0, 0, 0, 0))
                draw = ImageDraw.Draw(layer)
                for idx_line, line in enumerate(lines):
                    line_w = widths[idx_line] if idx_line < len(widths) else 0
                    if align == 'left':
                        lx = stroke_w * 2 + 4
                    elif align == 'right':
                        lx = raw_w - line_w - stroke_w * 2 - 4
                    else:
                        lx = (raw_w - line_w) / 2
                    ly = stroke_w * 2 + 4 + idx_line * line_h
                    _draw_text_line(draw, (lx, ly), line, font, fill, stroke_w, stroke_fill, letter_spacing, bold)
                    if strike:
                        sy = ly + max(1, int(ascent * 0.45))
                        draw.line((lx, sy, lx + line_w, sy), fill=fill + (255,), width=max(1, int(d.get('size', fixed_font_size) * 0.06)))

                scaled_w = max(1, int(layer.width * (char_w_pct / 100.0)))
                scaled_h = max(1, int(layer.height * (char_h_pct / 100.0)))
                if scaled_w != layer.width or scaled_h != layer.height:
                    resample = getattr(Image, "Resampling", Image).LANCZOS
                    layer = layer.resize((scaled_w, scaled_h), resample)

                if italic:
                    shear = -0.18
                    new_w = int(layer.width + abs(shear) * layer.height)
                    resampling = getattr(Image, "Resampling", Image)
                    layer = layer.transform(
                        (new_w, layer.height),
                        Image.Transform.AFFINE,
                        (1, shear, abs(shear) * layer.height if shear < 0 else 0, 0, 1, 0),
                        resample=resampling.BICUBIC
                    )

                rotation = float(d.get('rotation', 0) or 0)
                if abs(rotation) > 0.001:
                    resample = getattr(Image, "Resampling", Image).BICUBIC
                    layer = layer.rotate(-rotation, expand=True, resample=resample)

                content_w = layer.width
                content_h = layer.height
                layer, effect_pad_left, effect_pad_top, content_w, content_h = _apply_text_post_effects(
                    layer,
                    shadow_spec={
                        'enabled': bool(d.get('shadowEnabled', False)),
                        'color': d.get('shadowColor') or '#000000',
                        'opacity': int(d.get('shadowOpacity', 45) or 45),
                        'dx': int(d.get('shadowOffsetX', 3) or 3),
                        'dy': int(d.get('shadowOffsetY', 3) or 3),
                        'blur': int(d.get('shadowBlur', 4) or 4),
                    },
                    glow_spec={
                        'enabled': bool(d.get('glowEnabled', False)),
                        'color': d.get('glowColor') or '#FFFFFF',
                        'opacity': int(d.get('glowOpacity', 35) or 35),
                        'dx': int(d.get('glowOffsetX', 0) or 0),
                        'dy': int(d.get('glowOffsetY', 0) or 0),
                        'size': int(d.get('glowSize', 3) or 3),
                        'blur': int(d.get('glowBlur', 8) or 8),
                    },
                )

                if align == 'left':
                    tx = x - effect_pad_left
                elif align == 'right':
                    tx = x + w - content_w - effect_pad_left
                else:
                    tx = x + (w - content_w) / 2 - effect_pad_left
                ty = y - effect_pad_top

                result_img = result_img.convert("RGBA")
                result_img.alpha_composite(layer, (int(round(tx)), int(round(ty))))
                result_img = result_img.convert("RGB")

            _save_pil_for_output(result_img, result_img_path, output_fmt, output_quality)


        json_str = json.dumps(layers_list, ensure_ascii=False)
        font_name_json = json.dumps(font_name, ensure_ascii=False)

        # scripts/Script_XXXX.jsx에서 project_dir/clean/{원본파일명}.png를 상대경로로 찾음
        jsx_content = f"""
#target photoshop
app.bringToFront();
var originalUnit = preferences.rulerUnits;
preferences.rulerUnits = Units.PIXELS;
try {{
    var scriptFile = new File($.fileName);
    var imageFile = new File(scriptFile.parent.parent + "/clean/{clean_img_name}");
    if (imageFile.exists) {{
        open(imageFile);
        create_text_layers(app.activeDocument);
    }} else {{
        alert("이미지를 찾을 수 없습니다: " + imageFile.fsName);
    }}
}} catch (e) {{
    alert("오류: " + e);
}}
preferences.rulerUnits = originalUnit;

function normFontKey(s) {{
    try {{
        s = String(s || "").toLowerCase();
        s = s.replace(/\\([^\\)]*\\)/g, "");
        s = s.replace(/[\\s_\\-\\.]/g, "");
        s = s.replace(/[0-9]+$/g, "");
        return s;
    }} catch(e) {{ return ""; }}
}}
function uniquePush(arr, v) {{
    v = String(v || "");
    if (!v) return;
    for (var i=0; i<arr.length; i++) if (arr[i] == v) return;
    arr.push(v);
}}
function fontAliasCandidates(fontName) {{
    var out = [];
    uniquePush(out, fontName);
    var cleaned = String(fontName || "").replace(/\\([^\\)]*\\)/g, "").replace(/\\s+[0-9]+$/g, "");
    uniquePush(out, cleaned);
    var key = normFontKey(cleaned || fontName);
    var aliases = {{
        "맑은고딕": ["Malgun Gothic", "MalgunGothic", "MalgunGothicRegular", "MalgunGothicBold"],
        "malgungothic": ["Malgun Gothic", "MalgunGothic", "MalgunGothicRegular", "MalgunGothicBold"],
        "malgun": ["Malgun Gothic", "MalgunGothic", "MalgunGothicRegular", "MalgunGothicBold"],
        "굴림": ["Gulim", "GulimChe"],
        "gulim": ["Gulim", "GulimChe"],
        "돋움": ["Dotum", "DotumChe"],
        "dotum": ["Dotum", "DotumChe"],
        "바탕": ["Batang", "BatangChe"],
        "batang": ["Batang", "BatangChe"],
        "궁서": ["Gungsuh", "GungsuhChe"],
        "gungsuh": ["Gungsuh", "GungsuhChe"],
        "msgothic": ["MSGothic", "MS Gothic", "MS-Gothic"],
        "mspgothic": ["MSPGothic", "MS PGothic", "MS-PGothic"],
        "meiryo": ["Meiryo", "MeiryoUI"],
        "yugothic": ["YuGothic", "Yu Gothic", "YuGothic-Regular"]
    }};
    for (var a in aliases) {{
        var ak = normFontKey(a);
        if (key == ak || key.indexOf(ak) >= 0 || ak.indexOf(key) >= 0) {{
            for (var j=0; j<aliases[a].length; j++) uniquePush(out, aliases[a][j]);
        }}
    }}
    return out;
}}
function resolveFont(fontName, extraCandidates) {{
    var candidates = [];
    if (extraCandidates && extraCandidates.length) {{
        for (var i=0; i<extraCandidates.length; i++) uniquePush(candidates, extraCandidates[i]);
    }}
    var alias = fontAliasCandidates(fontName);
    for (var a=0; a<alias.length; a++) uniquePush(candidates, alias[a]);

    try {{
        // Exact match first.
        for (var c=0; c<candidates.length; c++) {{
            for (var i=0; i<app.fonts.length; i++) {{
                var f = app.fonts[i];
                if (f.postScriptName == candidates[c] || f.name == candidates[c] || f.family == candidates[c]) {{
                    return f.postScriptName;
                }}
            }}
        }}
        // Fuzzy match for localized/custom font names.
        for (var c2=0; c2<candidates.length; c2++) {{
            var ck = normFontKey(candidates[c2]);
            if (!ck) continue;
            for (var j=0; j<app.fonts.length; j++) {{
                var ff = app.fonts[j];
                var keys = [normFontKey(ff.postScriptName), normFontKey(ff.name), normFontKey(ff.family)];
                for (var k=0; k<keys.length; k++) {{
                    if (keys[k] && (keys[k] == ck || keys[k].indexOf(ck) >= 0 || ck.indexOf(keys[k]) >= 0)) {{
                        return ff.postScriptName;
                    }}
                }}
            }}
        }}
    }} catch(e) {{}}
    return fontName;
}}
function hexToRgb(hex, fallback) {{
    try {{
        if (!hex) return fallback;
        hex = String(hex).replace("#", "");
        if (hex.length != 6) return fallback;
        return [parseInt(hex.substr(0,2),16), parseInt(hex.substr(2,2),16), parseInt(hex.substr(4,2),16)];
    }} catch(e) {{ return fallback; }}
}}
function setTextColor(ti, hex) {{
    var rgb = hexToRgb(hex, [0,0,0]);
    var c = new SolidColor();
    c.rgb.red = rgb[0]; c.rgb.green = rgb[1]; c.rgb.blue = rgb[2];
    try {{ ti.color = c; }} catch(e) {{}}
}}
function unitToPx(v) {{
    try {{ return Number(v.as("px")); }} catch(e) {{
        try {{ return Number(v); }} catch(e2) {{ return 0; }}
    }}
}}
function layerBoundsPx(layer) {{
    var b = layer.bounds;
    var left = unitToPx(b[0]);
    var top = unitToPx(b[1]);
    var right = unitToPx(b[2]);
    var bottom = unitToPx(b[3]);
    return {{ left:left, top:top, right:right, bottom:bottom, width:(right-left), height:(bottom-top) }};
}}
function alignLayerToBox(layer, d) {{
    try {{
        var b = layerBoundsPx(layer);
        if (!isFinite(b.left) || !isFinite(b.top) || !isFinite(b.width) || !isFinite(b.height)) return;
        var boxX = Number(d.x || 0);
        var boxY = Number(d.y || 0);
        var boxW = Number(d.w || 0);
        var targetX = boxX;
        if (d.align == "right") targetX = boxX + boxW - b.width;
        else if (d.align != "left") targetX = boxX + (boxW - b.width) / 2.0;
        var targetY = boxY;
        layer.translate(targetX - b.left, targetY - b.top);
    }} catch(e) {{}}
}}
function create_text_layers(doc) {{
    var layers = {json_str};
    var defaultFontName = {font_name_json};
    for (var i = 0; i < layers.length; i++) {{
        var d = layers[i];
        var ly = doc.artLayers.add();
        doc.activeLayer = ly;
        ly.kind = LayerKind.TEXT;
        ly.name = "Txt_" + (d.id || (i+1));
        var ti = ly.textItem;

        // Photoshop 문단 텍스트는 박스 안에서 줄바꿈/행간/기준선을 다시 계산해서
        // YSB 미리보기와 어긋나기 쉽다. 그래서 POINTTEXT로 만들고, 생성 후 실제 bounds로 박스에 재정렬한다.
        try {{ ti.kind = TextType.POINTTEXT; }} catch(e) {{}}
        try {{ ti.position = [new UnitValue(0, "px"), new UnitValue(0, "px")]; }} catch(e) {{ ti.position = [0, 0]; }}

        try {{ ti.font = resolveFont(d.font || defaultFontName, d.fontCandidates || []); }} catch(e) {{}}
        try {{ ti.size = new UnitValue(d.size, "px"); }} catch(e) {{ ti.size = d.size; }}
        try {{ ti.contents = d.text; }} catch(e) {{ ti.contents = String(d.text || ""); }}
        setTextColor(ti, d.textColor);

        // 포토샵 출력용 레이어는 후편집을 우선한다.
        // YSB의 자간/행간/문자 너비/문자 높이 값은 포토샵의 문자 엔진과 1:1 대응되지 않아 여기서는 적용하지 않는다.
        try {{ ti.fauxBold = !!d.bold; }} catch(e) {{}}
        try {{ ti.fauxItalic = !!d.italic; }} catch(e) {{}}
        try {{ ti.strikeThru = !!d.strike; }} catch(e) {{}}
        try {{
            if (d.align == "left") ti.justification = Justification.LEFT;
            else if (d.align == "right") ti.justification = Justification.RIGHT;
            else ti.justification = Justification.CENTER;
        }} catch(e) {{}}

        doc.activeLayer = ly;
        if (Number(d.stroke || 0) > 0) {{ applyStroke(Number(d.stroke), d.strokeColor); }}
        try {{ if (Math.abs(Number(d.rotation || 0)) > 0.001) ly.rotate(Number(d.rotation), AnchorPosition.MIDDLECENTER); }} catch(e) {{}}
        alignLayerToBox(ly, d);
    }}
}}
function applyStroke(size, colorHex) {{
    var rgb = hexToRgb(colorHex, [255,255,255]);
    var desc1 = new ActionDescriptor(); var ref1 = new ActionReference();
    ref1.putProperty(charIDToTypeID("Prpr"), charIDToTypeID("Lefx"));
    ref1.putEnumerated(charIDToTypeID("Lyr "), charIDToTypeID("Ordn"), charIDToTypeID("Trgt"));
    desc1.putReference(charIDToTypeID("null"), ref1);
    var desc2 = new ActionDescriptor(); var desc3 = new ActionDescriptor();
    desc3.putBoolean(charIDToTypeID("enab"), true);
    desc3.putEnumerated(charIDToTypeID("Styl"), charIDToTypeID("FStl"), charIDToTypeID("OutF"));
    desc3.putEnumerated(charIDToTypeID("Pstn"), charIDToTypeID("Pstn"), charIDToTypeID("OutF"));
    desc3.putUnitDouble(charIDToTypeID("Sz  "), charIDToTypeID("Pxlt"), size);
    desc3.putDouble(charIDToTypeID("Opct"), 100.0);
    var c = new ActionDescriptor();
    c.putDouble(charIDToTypeID("Rd  "), rgb[0]); c.putDouble(charIDToTypeID("Grn "), rgb[1]); c.putDouble(charIDToTypeID("Bl  "), rgb[2]);
    desc3.putObject(charIDToTypeID("Clr "), charIDToTypeID("RGBC"), c);
    desc2.putObject(charIDToTypeID("FrFX"), charIDToTypeID("FrFX"), desc3);
    desc1.putObject(charIDToTypeID("T   "), charIDToTypeID("Lefx"), desc2);
    executeAction(charIDToTypeID("setd"), desc1, DialogModes.NO);
}}
"""
        script_path = os.path.join(scripts_dir, f"Script_{result_stem}.jsx")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(jsx_content)
        return script_path
