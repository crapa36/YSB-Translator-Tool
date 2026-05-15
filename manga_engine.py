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
    CLOVA_API_URL = ""
    CLOVA_SECRET_KEY = ""
    
    # [설정] OpenAI & Replicate
    OPENAI_API_KEY = ""
    DEEPSEEK_API_KEY = ""
    REPLICATE_API_TOKEN = ""
    
    # [설정] 번역 모델 선택
    OPENAI_TRANSLATION_MODEL = ""
    DEEPSEEK_TRANSLATION_MODEL = ""

    # [설정] 인페인팅 모델 - api_settings/main에서 주입됨
    INPAINT_MODEL = ""
    REPAINT_MODEL = ""  # 구버전 설정 호환용

    # [설정] 마스킹 비율
    INPAINT_RATIO = 0.1
    MERGE_RATIO = 0.2  
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
            expansion = max(expansion, 5)
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
            combined_text = self._manga_sort(included_items)
            
            all_sub_vertices = [it['vertices'] for it in included_items]
            avg_stroke = sum([it['stroke_size'] for it in included_items]) / len(included_items)

            grouped_data.append({
                'id': 0, 
                'text': combined_text,
                'rect': [x, y, rw, rh],
                'vertices_list': all_sub_vertices,
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
            
            combined_text = self._manga_sort(items_in_bubble)
            all_vertices = [it['vertices'] for it in items_in_bubble]
            avg_stroke = sum([it['stroke_size'] for it in items_in_bubble]) / len(items_in_bubble)
            
            new_grouped_data.append({
                'id': 0, 'text': combined_text, 'rect': [rx, ry, rw, rh], 
                'vertices_list': all_vertices, 'avg_stroke': avg_stroke,
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

        # 번역 묶음 수
        # main.py에서 사용자가 지정한 값이 오면 그 값을 우선 사용한다.
        if chunk_size is None:
            if provider == "deepseek":
                chunk_size = 8
            else:
                chunk_size = 20
        else:
            try:
                chunk_size = int(chunk_size)
            except:
                chunk_size = 8 if provider == "deepseek" else 20
            chunk_size = max(1, min(chunk_size, 100))

        final_results = []

        for start in range(0, len(texts), chunk_size):
            chunk = texts[start:start + chunk_size]

            try:
                translated_chunk = self._translate_text_chunk(chunk, provider, start)
                final_results.extend(translated_chunk)

            except Exception as e:
                print(f"Chunk Translate Error: {e}")

                # 청크 실패 시 한 줄씩 재시도
                for offset, one_text in enumerate(chunk):
                    try:
                        one_result = self._translate_text_chunk([one_text], provider, start + offset)
                        final_results.extend(one_result)
                    except Exception as e2:
                        print(f"Single Translate Error: {e2}")
                        final_results.append(one_text)

        # 최종 안전장치
        if len(final_results) != len(texts):
            print(f"Translate Count Mismatch Fixed: input={len(texts)}, output={len(final_results)}")

            if len(final_results) < len(texts):
                final_results.extend(texts[len(final_results):])
            else:
                final_results = final_results[:len(texts)]

        return final_results

    def _translate_text_chunk(self, texts, provider="openai", base_id=0):
        prompt = r"""
You are a professional R-18 Comic Localization Expert (JP -> KR).

Your goal is to convert Japanese script data into Korean without ANY data loss.

STRICT RULES:
1. Translate Japanese into Korean naturally.
2. Do not omit, soften, summarize, or censor any meaning.
3. Translate explicit language directly without censorship.
4. Preserve the intensity, vulgarity, erotic tone, character voice, and emotional nuance of the original.
5. Kanji nouns: when a Kanji noun has a clear Sino-Korean equivalent, prefer the direct Sino-Korean / Hanja-based Korean equivalent.
6. Brackets: STRICTLY PRESERVE original Japanese brackets exactly as written.
   Examples: 「」 『』 （） 【】 《》 〈〉
7. Preserve line breaks when they exist.
8. Convert ellipsis-like expressions such as "...", "･･･", "・・・", "…..." into the single ellipsis character "…".
9. Do not add explanations, notes, comments, markdown, or extra text.

OUTPUT FORMAT RULES:
1. Input is a JSON list of objects.
2. Each object has "id" and "text".
3. Return ONLY a valid JSON object.
4. The JSON object MUST have one key: "items".
5. "items" MUST be a list of objects.
6. Each output object MUST have the same "id" and a "translation".
7. NEVER skip any id.
8. NEVER merge two ids into one translation.
9. NEVER create a new id.
10. Example output:
{"items":[{"id":0,"translation":"번역문"},{"id":1,"translation":"번역문"}]}
"""

        provider = (provider or "openai").lower()

        if provider == "deepseek":
            if self.deepseek_client is None:
                raise ValueError("DeepSeek API 키가 비어있습니다.")
            client = self.deepseek_client
            model = Config.DEEPSEEK_TRANSLATION_MODEL
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
        return self._call_lama(image_path, bin_mask)

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

                    output = replicate.run(
                        model_name,
                        input={
                            "image": img_file,
                            "mask": mask_file,
                        }
                    )
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
    def export_project_result(self, data, img_path, bg_data, font_name, stroke_size, fixed_font_size):
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

        # 프로젝트 내부 images/0001.png 형태면 프로젝트 루트를 자동 추정
        if os.path.basename(img_dir).lower() == "images":
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
                "stroke": item_stroke,
                "textColor": item_text_color,
                "strokeColor": item_stroke_color,
                "align": item_align,
            })

        # Result 폴더용 최종 이미지 렌더링. 포토샵 레이어만큼 정교하진 않아도 검수용 이미지로 바로 쓸 수 있게 저장한다.
        if bg_img is not None:
            result_img = bg_img.copy().convert('RGB')
            draw = ImageDraw.Draw(result_img)
            for d in layers_list:
                font = _get_font(d.get('font'), d.get('size', fixed_font_size))
                text = d.get('plain_text', '')
                if not text.strip():
                    continue
                x = float(d['x'])
                y = float(d['y'])
                w = float(d['w'])
                h = float(d['h'])
                align = d.get('align', 'center')
                stroke_w = int(d.get('stroke', 0) or 0)
                fill = _hex_to_rgb(d.get('textColor'), (0, 0, 0))
                stroke_fill = _hex_to_rgb(d.get('strokeColor'), (255, 255, 255))
                try:
                    bbox = draw.multiline_textbbox((0, 0), text, font=font, spacing=2, stroke_width=stroke_w)
                    tw = bbox[2] - bbox[0]
                    th = bbox[3] - bbox[1]
                except Exception:
                    tw, th = draw.multiline_textsize(text, font=font, spacing=2)
                if align == 'left':
                    tx = x
                elif align == 'right':
                    tx = x + w - tw
                else:
                    tx = x + (w - tw) / 2
                ty = y + (h - th) / 2
                draw.multiline_text(
                    (tx, ty),
                    text,
                    font=font,
                    fill=fill,
                    spacing=2,
                    align=align,
                    stroke_width=stroke_w,
                    stroke_fill=stroke_fill,
                )
            result_img.save(result_img_path)

        json_str = json.dumps(layers_list, ensure_ascii=False)
        font_name_json = json.dumps(font_name, ensure_ascii=False)

        # scripts/Script_XXXX.jsx에서 project_dir/clean/Clean_XXXX.png를 상대경로로 찾음
        jsx_content = f"""
#target photoshop
app.bringToFront(); var originalUnit = preferences.rulerUnits; preferences.rulerUnits = Units.PIXELS;
try {{
    var scriptFile = new File($.fileName); var imageFile = new File(scriptFile.parent.parent + "/clean/{clean_img_name}");
    if (imageFile.exists) {{ open(imageFile); create_text_layers(app.activeDocument); }}
    else {{ alert("이미지를 찾을 수 없습니다: " + imageFile.fsName); }}
}} catch (e) {{ alert("오류: " + e); }}
preferences.rulerUnits = originalUnit;
function resolveFont(fontName) {{
    try {{
        for (var i = 0; i < app.fonts.length; i++) {{
            var f = app.fonts[i];
            if (f.postScriptName == fontName || f.name == fontName || f.family == fontName) {{
                return f.postScriptName;
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
function create_text_layers(doc) {{
    var layers = {json_str}; var defaultFontName = {font_name_json};
    for (var i = 0; i < layers.length; i++) {{
        var d = layers[i]; var ly = doc.artLayers.add(); ly.kind = LayerKind.TEXT; ly.name = "Txt_" + (i+1);
        var ti = ly.textItem; ti.kind = TextType.POINTTEXT;
        var anchorX = d.x + d.w/2;
        if (d.align == "left") anchorX = d.x;
        if (d.align == "right") anchorX = d.x + d.w;
        ti.position = [anchorX, d.y + d.h/2];
        ti.contents = d.text; ti.size = new UnitValue(d.size, "px");
        try {{
            if (d.align == "left") ti.justification = Justification.LEFT;
            else if (d.align == "right") ti.justification = Justification.RIGHT;
            else ti.justification = Justification.CENTER;
        }} catch(e) {{}}
        try {{ ti.font = resolveFont(d.font || defaultFontName); }} catch(e) {{}}
        setTextColor(ti, d.textColor);
        if (d.stroke > 0) {{ applyStroke(d.stroke, d.strokeColor); }}
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
