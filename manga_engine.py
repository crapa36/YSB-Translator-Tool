import os
import json
import cv2
import numpy as np
import requests
import time
import math
import uuid
from openai import OpenAI
from PIL import Image, ImageDraw, ImageFont

class Config:
    # ---------------------------------------------------------
    # [설정] 네이버 클라우드 CLOVA OCR 정보 (본인 키 입력 필수!)
    # ---------------------------------------------------------
    OCR_PROVIDER = "clova"
    CLOVA_API_URL = ""
    CLOVA_SECRET_KEY = ""
    CLOVA_MODEL = "clova_ocr_v2"
    GOOGLE_VISION_CREDENTIAL_JSON_PATH = ""
    GOOGLE_VISION_API_KEY = ""
    GOOGLE_VISION_MODEL = "DOCUMENT_TEXT_DETECTION"
    GOOGLE_VISION_LANGUAGE_HINTS = "ja,ko,en"
    
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
    STABLE_INPAINT_MODEL = "stability-ai/stable-diffusion-inpainting:95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3"
    STABLE_INPAINT_PROMPT = "remove text and restore the original background"

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

        hints_raw = str(getattr(Config, "GOOGLE_VISION_LANGUAGE_HINTS", "") or "")
        hints = [x.strip() for x in hints_raw.replace(";", ",").split(",") if x.strip()]

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

    def _append_google_raw_item(self, raw_items, text, vertices, offset_x=0, offset_y=0, locale=""):
        text = str(text or "").strip()
        if not text:
            return
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
        })

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
            for block in page.get("blocks", []) or []:
                for para in block.get("paragraphs", []) or []:
                    for word in para.get("words", []) or []:
                        symbols = word.get("symbols", []) or []
                        text = ''.join(str(sym.get("text", "") or "") for sym in symbols).strip()
                        if not text:
                            continue
                        vertices = (word.get("boundingBox") or {}).get("vertices", []) or []
                        self._append_google_raw_item(raw_items, text, vertices, offset_x, offset_y, page_locale)

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
    def _manga_sort(self, items):
        if not items: return ""
        
        # 말풍선 형태 판단 (세로형 vs 가로형)
        avg_w = sum([it['rect'][2] for it in items]) / len(items)
        avg_h = sum([it['rect'][3] for it in items]) / len(items)
        is_vertical = avg_h > avg_w

        if is_vertical:
            # [세로형] 오른쪽 -> 왼쪽 (X 내림차순), 그 다음 위 -> 아래
            items.sort(key=lambda v: (-v['cx'], v['cy']))
        else:
            # [가로형] 위 -> 아래 (Y 오름차순), 그 다음 왼쪽 -> 오른쪽
            items.sort(key=lambda v: (v['cy'], v['cx']))

        return "".join([it['text'] for it in items])

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
                    # 줄이 바뀌면, 이전 줄을 '오른쪽->왼쪽' 정렬
                    current_row.sort(key=lambda x: -x['rect'][0])
                    rows.append(current_row)
                    current_row = [curr]
            
            # 마지막 줄 처리
            current_row.sort(key=lambda x: -x['rect'][0])
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
    def analyze_image(self, image_path):
        print(f">>> [Analysis] 전체 분석: {os.path.basename(image_path)}")

        img_array = np.fromfile(image_path, np.uint8)
        ori_img = cv2.imdecode(img_array, cv2.IMREAD_COLOR)

        if ori_img is None:
            raise ValueError(f"이미지를 읽을 수 없습니다: {image_path}")

        h, w, _ = ori_img.shape

        # 짧은 이미지든 긴 웹툰 이미지든 여기서 자동 처리
        # h <= OCR_TILE_HEIGHT면 단일 OCR
        # h > OCR_TILE_HEIGHT면 세로 분할 OCR
        raw_items = self._ocr_image_region_tiled(
            ori_img,
            offset_x=0,
            offset_y=0
        )

        grouped_data, mask_merge = self._group_text_blocks_by_ratio(raw_items, w, h)
        mask_inpaint = self._create_ratio_mask(grouped_data, w, h)

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
                        'rect': [bx, by, bw, bh]
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
        key = getattr(Config, "GOOGLE_TRANSLATE_API_KEY", "").strip()
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
                results.append(str(translations[i].get("translatedText", "")))
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
        items = parsed.get("items", []) if isinstance(parsed, dict) else parsed
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
        if mask_1st is not None: final_mask = mask_1st.copy()
        else: final_mask = self._create_ratio_mask(analyzed_data, *cv2.imread(image_path).shape[:2][::-1])
        for d in analyzed_data:
            if not d.get('use_inpaint', True):
                rx, ry, rw, rh = d['rect']
                cv2.rectangle(final_mask, (rx, ry), (rx+rw, ry+rh), 0, -1)
        _, bin_mask = cv2.threshold(final_mask, 10, 255, cv2.THRESH_BINARY)
        provider = str(getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama").lower()
        if provider == "replicate_stable":
            return self._call_stable_inpaint(image_path, bin_mask)
        return self._call_lama(image_path, bin_mask)

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
        import replicate
        import time
        import re

        model_name = str(getattr(Config, "INPAINT_MODEL", "") or getattr(Config, "REPAINT_MODEL", "") or "").strip()
        if not model_name:
            raise ValueError("인페인팅 모델명이 비어있습니다. 옵션 > API 관리에서 모델명을 입력해 주세요.")

        temp_mask = f"temp_mask_lama_{uuid.uuid4().hex}.png"
        cv2.imwrite(temp_mask, mask_img)

        # Replicate 저크레딧/무료 상태에서는 burst=1 제한이 자주 걸린다.
        # 개별 인페인팅은 한 번만 보내서 괜찮지만, 일괄은 연속 호출이라 429가 나기 쉽다.
        max_retries = 6
        base_wait_seconds = 12

        try:
            for attempt in range(1, max_retries + 1):
                mask_file = None
                img_file = None

                try:
                    mask_file = open(temp_mask, "rb")
                    img_file = open(image_path, "rb")

                    lama_input = {
                        "image": img_file,
                        "mask": mask_file,
                    }
                    token = str(getattr(Config, "LAMA_REPLICATE_API_TOKEN", "") or getattr(Config, "REPLICATE_API_TOKEN", "") or "").strip()
                    output = self._replicate_run_isolated(model_name, lama_input, token)
                    return output

                except Exception as e:
                    err_text = str(e)
                    print(f"LaMa Error attempt {attempt}/{max_retries}: {err_text}")

                    is_rate_limit = (
                        "429" in err_text
                        or "throttled" in err_text.lower()
                        or "rate limit" in err_text.lower()
                    )

                    if is_rate_limit and attempt < max_retries:
                        # Replicate 메시지에 "resets in ~5s" 같은 값이 있으면 그보다 조금 더 기다린다.
                        wait_seconds = base_wait_seconds + (attempt - 1) * 8
                        m = re.search(r"resets in ~?(\d+)s", err_text)
                        if m:
                            wait_seconds = max(wait_seconds, int(m.group(1)) + 4)

                        print(f"LaMa Rate Limit: {wait_seconds}s 대기 후 재시도")
                        time.sleep(wait_seconds)
                        continue

                    return None

                finally:
                    if mask_file:
                        try:
                            mask_file.close()
                        except:
                            pass
                    if img_file:
                        try:
                            img_file.close()
                        except:
                            pass

            return None

        finally:
            if os.path.exists(temp_mask):
                try:
                    os.remove(temp_mask)
                except:
                    pass

    # ---------------------------------------------------------
    # [CORE] 출력
    # ---------------------------------------------------------
    def export_project_result(self, data, img_path, bg_data, font_name, stroke_size, fixed_font_size, output_root=None):
        """
        결과 출력:
        - project_dir/clean/Clean_XXXX.png: 인페인팅된 배경
        - project_dir/Result/Result_XXXX.png: 최종 화면 이미지(텍스트 포함)
        - project_dir/scripts/Script_XXXX.jsx: 포토샵 텍스트 레이어 생성 스크립트
        - Photoshop 실행 완료 알림(alert)은 띄우지 않음
        """
        import io

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
        result_dir = os.path.join(project_dir, "Result")
        scripts_dir = os.path.join(project_dir, "scripts")
        os.makedirs(clean_dir, exist_ok=True)
        os.makedirs(result_dir, exist_ok=True)
        os.makedirs(scripts_dir, exist_ok=True)

        name_no_ext = os.path.splitext(os.path.basename(img_path))[0]
        clean_img_name = f"Clean_{name_no_ext}.png"
        result_img_name = f"Result_{name_no_ext}.png"
        clean_img_path = os.path.join(clean_dir, clean_img_name)
        result_img_path = os.path.join(result_dir, result_img_name)

        bg_img = _load_pil_image(bg_data)
        if bg_img is None:
            bg_img = _load_pil_image(img_path)
        if bg_img is not None:
            bg_img.save(clean_img_path)

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
            })

        # Result 폴더용 최종 이미지 렌더링. 포토샵 레이어만큼 정교하진 않아도 검수용 이미지로 바로 쓸 수 있게 저장한다.
        def _text_bbox_single(draw_obj, text_value, font_obj, stroke_w=0):
            try:
                return draw_obj.textbbox((0, 0), text_value, font=font_obj, stroke_width=stroke_w)
            except Exception:
                w, h = draw_obj.textsize(text_value, font=font_obj)
                return (0, 0, w, h)

        def _draw_text_line(draw_obj, pos, line_text, font_obj, fill, stroke_w, stroke_fill, letter_spacing=0, bold=False):
            x0, y0 = pos
            if not letter_spacing:
                offsets = [(0, 0)]
                if bold:
                    offsets += [(1, 0), (0, 1), (1, 1)]
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
                offsets = [(0, 0)]
                if bold:
                    offsets += [(1, 0), (0, 1), (1, 1)]
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

                if align == 'left':
                    tx = x
                elif align == 'right':
                    tx = x + w - layer.width
                else:
                    tx = x + (w - layer.width) / 2
                ty = y

                result_img = result_img.convert("RGBA")
                result_img.alpha_composite(layer, (int(round(tx)), int(round(ty))))
                result_img = result_img.convert("RGB")

            result_img.save(result_img_path)


        json_str = json.dumps(layers_list, ensure_ascii=False)
        font_name_json = json.dumps(font_name, ensure_ascii=False)

        # scripts/Script_XXXX.jsx에서 project_dir/clean/Clean_XXXX.png를 상대경로로 찾음
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
        script_path = os.path.join(scripts_dir, f"Script_{name_no_ext}.jsx")
        with open(script_path, "w", encoding="utf-8") as f:
            f.write(jsx_content)
        return script_path
