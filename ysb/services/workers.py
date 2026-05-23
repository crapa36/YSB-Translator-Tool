import os
import re
import copy
import cv2
import numpy as np
import requests
import time
from PyQt6.QtCore import QThread, pyqtSignal

def _download_replicate_output(output):
    """Replicate output can be URL strings, lists, FileOutput objects, file-like objects, bytes, or local paths."""
    if output is None:
        return b""
    if isinstance(output, (list, tuple)):
        if not output:
            return b""
        output = output[0]
    if isinstance(output, (bytes, bytearray)):
        return bytes(output)
    # replicate FileOutput often supports read()
    try:
        if hasattr(output, "read") and callable(output.read):
            data = output.read()
            if isinstance(data, str):
                return data.encode("utf-8")
            return bytes(data or b"")
    except Exception:
        pass
    # some objects expose url
    try:
        if hasattr(output, "url"):
            output = output.url
    except Exception:
        pass
    text = str(output)
    if text.startswith("http://") or text.startswith("https://"):
        r = requests.get(text, timeout=180)
        r.raise_for_status()
        return r.content
    if os.path.exists(text):
        with open(text, "rb") as f:
            return f.read()
    # Last fallback: requests may know how to handle object string repr for older clients.
    r = requests.get(text, timeout=180)
    r.raise_for_status()
    return r.content


def _imread_unicode(path: str):
    arr = np.fromfile(path, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


PAGE_DISPLAY_MODE_ORIGINAL = "original_name"
PAGE_DISPLAY_MODE_PAGE_ORIGINAL = "1p_original_name"
PAGE_DISPLAY_MODE_PAGE_NUMBER = "page001"
DEFAULT_PAGE_DISPLAY_MODE = PAGE_DISPLAY_MODE_PAGE_ORIGINAL


def _normalize_page_display_mode(value):
    value = str(value or DEFAULT_PAGE_DISPLAY_MODE).strip()
    if value in (PAGE_DISPLAY_MODE_ORIGINAL, PAGE_DISPLAY_MODE_PAGE_ORIGINAL, PAGE_DISPLAY_MODE_PAGE_NUMBER):
        return value
    return DEFAULT_PAGE_DISPLAY_MODE


def _safe_page_file_stem(value, fallback="page"):
    stem = os.path.splitext(os.path.basename(str(value or fallback)))[0].strip() or fallback
    stem = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", stem).strip(" .")
    return stem or fallback


def _copy_mask(mask):
    if mask is None:
        return None
    return np.array(mask, dtype=np.uint8).copy()


def _copy_data_list(data_list):
    return copy.deepcopy(data_list or [])


def _clip_mask_to_checked_text_boxes(mask, data):
    """
    일괄 인페인팅용 ON 마스크 제한:
    분석 기반 페인팅 마스크는 체크된 텍스트 박스 내부만 남긴다.
    """
    if mask is None:
        return None

    if mask.ndim == 3:
        gray = cv2.cvtColor(mask, cv2.COLOR_RGB2GRAY)
    else:
        gray = mask.copy()

    h, w = gray.shape[:2]
    allowed = np.zeros((h, w), dtype=np.uint8)

    for item in data or []:
        if not item.get('use_inpaint', True):
            continue
        rect = item.get('rect')
        if not rect or len(rect) < 4:
            continue
        try:
            rx, ry, rw, rh = [int(v) for v in rect[:4]]
        except Exception:
            continue

        x1 = max(0, rx)
        y1 = max(0, ry)
        x2 = min(w, rx + max(0, rw))
        y2 = min(h, ry + max(0, rh))
        if x2 > x1 and y2 > y1:
            allowed[y1:y2, x1:x2] = 255

    return cv2.bitwise_and(gray, allowed)


def _build_inpainting_payload(mask_toggle_enabled, curr_data):
    """
    - ON: 분석 기반 페인팅 마스크를 체크된 텍스트 박스 영역 안으로 제한.
    - OFF: 수동 OFF 페인팅 마스크를 그대로 사용하고, 텍스트 박스/체크 상태는 무시.
    """
    data = _copy_data_list(curr_data.get('data', []))
    if mask_toggle_enabled:
        mask = _copy_mask(curr_data.get('mask_inpaint'))
        if mask is not None:
            mask = _clip_mask_to_checked_text_boxes(mask, data)
        return data, mask

    return [], _copy_mask(curr_data.get('mask_inpaint_off'))


class UniversalBatchWorker(QThread):
    progress = pyqtSignal(str)
    # page index, mode
    # 메인 UI가 현재 처리 중인 페이지로 따라가게 한다.
    active_item = pyqtSignal(int, str)
    # page index, payload dict
    # payload는 메인 스레드에서 self.data[i]에 반영된다.
    finished_item = pyqtSignal(int, object)
    finished_all = pyqtSignal()

    def __init__(self, main_window, mode, page_indices=None):
        super().__init__()
        self.main = main_window
        self.mode = mode
        self.engine = main_window.engine
        self.is_running = True

        # 스레드 안에서 UI 위젯을 직접 읽지 않도록 시작 시점 값만 복사
        self.paths = list(main_window.paths)
        if page_indices is None:
            self.page_indices = list(range(len(self.paths)))
        else:
            clean_indices = []
            seen_indices = set()
            for raw_idx in page_indices:
                try:
                    page_idx = int(raw_idx)
                except Exception:
                    continue
                if 0 <= page_idx < len(self.paths) and page_idx not in seen_indices:
                    clean_indices.append(page_idx)
                    seen_indices.add(page_idx)
            self.page_indices = clean_indices or list(range(len(self.paths)))
        self.provider = main_window.cb_trans_provider.currentData()
        self.font_family = main_window.cb_font.currentFont().family()
        self.stroke_size = main_window.sb_strk.value()
        self.font_size = main_window.sb_font_size.value()
        self.mask_toggle_enabled = bool(getattr(main_window, "mask_toggle_enabled", False))
        self.project_dir = getattr(main_window, "project_dir", None)
        self.output_display_name_mode = _normalize_page_display_mode(getattr(main_window, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))

        # 시작 시점의 페이지 데이터를 스냅샷으로 복사한다.
        # 이렇게 해야 일괄 작업 중 화면/현재 페이지 상태가 다른 페이지에 섞이지 않는다.
        self.data_snapshot = {}
        for i, path in enumerate(self.paths):
            src = main_window.data.get(i)
            if src is None:
                self.data_snapshot[i] = {
                    'ori': _imread_unicode(path),
                    'data': [],
                    'mask_merge': None,
                    'mask_inpaint': None,
                    'mask_merge_off': None,
                    'mask_inpaint_off': None,
                    'mask_toggle_enabled': False,
                    'use_inpainted_as_source': False,
                    'bg_clean': None,
                }
            else:
                self.data_snapshot[i] = {
                    'ori': src.get('ori'),
                    'data': _copy_data_list(src.get('data', [])),
                    'mask_merge': _copy_mask(src.get('mask_merge')),
                    'mask_inpaint': _copy_mask(src.get('mask_inpaint')),
                    'mask_merge_off': _copy_mask(src.get('mask_merge_off')),
                    'mask_inpaint_off': _copy_mask(src.get('mask_inpaint_off')),
                    'mask_toggle_enabled': bool(src.get('mask_toggle_enabled', False)),
                    'use_inpainted_as_source': bool(src.get('use_inpainted_as_source', False)),
                    'bg_clean': src.get('bg_clean'),
                    'original_name': src.get('original_name'),
                }

    def _write_bg_clean_as_source(self, page_idx, curr_data, fallback_path):
        if not curr_data.get('use_inpainted_as_source') or not curr_data.get('bg_clean'):
            return fallback_path
        root = self.project_dir or os.path.dirname(os.path.abspath(fallback_path))
        clean_dir = os.path.join(root, "clean")
        os.makedirs(clean_dir, exist_ok=True)
        out_path = os.path.join(clean_dir, f"batch_inpaint_source_{page_idx + 1:04d}.png")
        bg = curr_data.get('bg_clean')
        try:
            if isinstance(bg, (bytes, bytearray)):
                with open(out_path, "wb") as f:
                    f.write(bg)
                return out_path
            if isinstance(bg, np.ndarray):
                cv2.imwrite(out_path, bg)
                return out_path
            if isinstance(bg, str) and os.path.exists(bg):
                return bg
        except Exception:
            return fallback_path
        return fallback_path

    def _output_display_stem(self, page_idx, path, curr_data):
        original = ""
        if isinstance(curr_data, dict):
            original = curr_data.get("original_name") or ""
        if not original:
            original = os.path.basename(str(path or f"page{page_idx + 1:03d}.png"))
        stem = _safe_page_file_stem(original, fallback=f"page{page_idx + 1:03d}")
        mode = _normalize_page_display_mode(getattr(self, "output_display_name_mode", DEFAULT_PAGE_DISPLAY_MODE))
        if mode == PAGE_DISPLAY_MODE_ORIGINAL:
            return stem
        if mode == PAGE_DISPLAY_MODE_PAGE_NUMBER:
            return f"page{page_idx + 1:03d}"
        return f"{page_idx + 1}p_{stem}"

    def _path_for_output_display(self, page_idx, path, curr_data):
        ext = os.path.splitext(str(path or ""))[1] or ".png"
        return os.path.join(os.path.dirname(os.path.abspath(str(path or os.getcwd()))), self._output_display_stem(page_idx, path, curr_data) + ext)

    def run(self):
        selected_indices = list(getattr(self, "page_indices", None) or range(len(self.paths)))
        total = len(selected_indices)

        visual_modes = {"analyze", "translate", "inpaint"}

        for order_idx, i in enumerate(selected_indices):
            if not self.is_running:
                break
            if i < 0 or i >= len(self.paths):
                continue

            path = self.paths[i]
            curr_data = self.data_snapshot.get(i, {})
            base_name = os.path.basename(path)
            prefix = f"[{order_idx + 1}/{total}]"

            try:
                payload = {}
                if self.mode in visual_modes:
                    self.active_item.emit(i, self.mode)

                if self.mode == 'analyze':
                    self.progress.emit(f"{prefix} 분석: {base_name}")
                    o, d, mm, mi = self.engine.analyze_image(path)
                    payload = {
                        'ori': o,
                        'data': _copy_data_list(d),
                        'mask_merge': _copy_mask(mm),
                        'mask_inpaint': _copy_mask(mi),
                    }

                elif self.mode == 'translate':
                    if not curr_data.get('data'):
                        self.progress.emit(f"{prefix} 번역 건너뜀: 분석 데이터 없음")
                        self.finished_item.emit(i, {})
                        continue

                    self.progress.emit(f"{prefix} 번역: {base_name}")
                    new_data = _copy_data_list(curr_data.get('data', []))
                    target_items = [item for item in new_data if item.get('use_inpaint', True)]

                    if not target_items:
                        self.progress.emit(f"{prefix} 번역 건너뜀: 체크된 항목 없음")
                        self.finished_item.emit(i, {})
                        continue

                    texts = [item.get('text', '') for item in target_items]
                    trans = self.engine.translate_text_batch(texts, provider=self.provider)

                    if len(trans) != len(target_items):
                        raise ValueError(f"번역 개수 불일치: 요청 {len(target_items)}개 / 응답 {len(trans)}개")

                    for item, t in zip(target_items, trans):
                        item['translated_text'] = str(t) if t is not None else ''

                    payload = {'data': new_data}

                elif self.mode == 'inpaint':
                    inpaint_data, inpaint_mask = _build_inpainting_payload(self.mask_toggle_enabled, curr_data)

                    if self.mask_toggle_enabled and not inpaint_data and inpaint_mask is None:
                        self.progress.emit(f"{prefix} 인페인팅 건너뜀: ON 분석/선택 마스크 없음")
                        self.finished_item.emit(i, {})
                        continue
                    if (not self.mask_toggle_enabled) and inpaint_mask is None:
                        self.progress.emit(f"{prefix} 인페인팅 건너뜀: OFF 페인팅 마스크 없음")
                        self.finished_item.emit(i, {})
                        continue

                    self.progress.emit(f"{prefix} 인페인팅: {base_name}")

                    source_path = self._write_bg_clean_as_source(i, curr_data, path)
                    res_url = self.engine.execute_inpainting(
                        source_path,
                        inpaint_data,
                        inpaint_mask
                    )

                    if res_url:
                        u = res_url[0] if isinstance(res_url, list) else res_url
                        bg_bytes = _download_replicate_output(res_url)

                        # 중요: 워커 스냅샷 안에만 넣지 말고 payload로 main에 넘겨야 실제 페이지에 반영된다.
                        curr_data['bg_clean'] = bg_bytes
                        payload = {'bg_clean': bg_bytes}

                        self.progress.emit(f"{prefix} 인페인팅 완료")
                    else:
                        payload = {}
                        self.progress.emit(f"{prefix} ⚠️ 인페인팅 결과 없음")

                    # Replicate burst=1 제한 방지. Local LaMa는 API 제한이 없으므로 대기하지 않는다.
                    try:
                        from ysb.engine.manga_engine import Config
                        _provider = str(getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama").lower()
                    except Exception:
                        _provider = "replicate_lama"
                    if order_idx < total - 1 and _provider != "local_lama":
                        time.sleep(5)

                elif self.mode == 'refresh':
                    self.progress.emit(f"{prefix} 텍스트 갱신: {base_name}")
                    payload = {}

                elif self.mode == 'export':
                    self.progress.emit(f"{prefix} 출력: {base_name}")
                    export_bg = curr_data.get('bg_clean')
                    if export_bg is None:
                        export_bg = path
                    self.engine.export_project_result(
                        curr_data.get('data', []),
                        path,
                        export_bg,
                        self.font_family,
                        self.stroke_size,
                        self.font_size,
                        output_root=self.project_dir,
                        output_name_stem=self._output_display_stem(i, path, curr_data),
                    )
                    payload = {}

                self.finished_item.emit(i, payload)
                if self.mode in visual_modes and order_idx < total - 1 and self.is_running:
                    # 결과가 화면에 반영되는 것을 사용자가 확인할 수 있도록
                    # 다음 페이지로 넘어가기 전 짧게 멈춘다.
                    time.sleep(1.0)

            except Exception as e:
                self.progress.emit(f"{prefix} ❌ 에러: {e}")

        if self.is_running:
            self.progress.emit(f"✅ 일괄 {self.mode} 완료!")
        else:
            self.progress.emit(f"⏹️ 일괄 {self.mode} 취소 요청 반영: 현재 항목 완료 후 중단")
        self.finished_all.emit()

    def stop(self):
        self.is_running = False


class AnalysisWorker(QThread):
    finished = pyqtSignal(object, object, object, object)
    log = pyqtSignal(str)

    def __init__(self, engine, path, mask=None, data=None):
        super().__init__()
        self.engine = engine
        self.path = path
        self.mask = _copy_mask(mask)
        self.data = _copy_data_list(data)
        self.cancel_requested = False

    def stop(self):
        self.cancel_requested = True

    def run(self):
        try:
            try:
                from ysb.engine.manga_engine import Config
                provider = str(getattr(Config, "OCR_PROVIDER", "clova") or "clova")
                if provider == "google_vision":
                    provider_name = "Google Vision"
                elif provider == "local_paddle_ocr":
                    provider_name = "LOCAL Paddle OCR"
                else:
                    provider_name = "CLOVA"
            except Exception:
                provider_name = "OCR"

            if self.mask is not None:
                self.log.emit(f"🔄 {provider_name} OCR로 영역 재분석 중...")
                o, d, mm, mi = self.engine.reanalyze_from_manual_mask(self.path, self.mask, self.data)
            else:
                self.log.emit(f"🚀 {provider_name} 전체 분석 시작...")
                o, d, mm, mi = self.engine.analyze_image(self.path)
            self.log.emit(f"✅ 완료 ({len(d)}개)")
            self.finished.emit(o, d, _copy_mask(mm), _copy_mask(mi))
        except Exception as e:
            import traceback
            traceback.print_exc()
            self.log.emit(f"❌ 오류: {e}")


class InpaintWorker(QThread):
    finished = pyqtSignal(bytes)
    log = pyqtSignal(str)

    def __init__(self, engine, path, data, mask):
        super().__init__()
        self.engine = engine
        self.path = path
        self.data = _copy_data_list(data)
        self.mask = _copy_mask(mask)
        self.cancel_requested = False

    def stop(self):
        self.cancel_requested = True

    def run(self):
        try:
            try:
                from ysb.engine.manga_engine import Config
                provider = str(getattr(Config, "INPAINT_PROVIDER", "replicate_lama") or "replicate_lama")
                if provider == "replicate_stable":
                    provider_name = "Stable Diffusion"
                elif provider == "gemini_inpaint":
                    provider_name = "Gemini"
                elif provider == "local_lama":
                    provider_name = "LOCAL LaMa"
                else:
                    provider_name = "LaMa"
            except Exception:
                provider_name = "인페인팅"
            self.log.emit(f"🎨 {provider_name} 인페인팅 시작...")
            res = self.engine.execute_inpainting(self.path, self.data, self.mask)
            if res:
                u = res[0] if isinstance(res, list) else res
                img_data = _download_replicate_output(res)
                self.finished.emit(img_data)
            else:
                self.log.emit("❌ 실패: 인페인팅 서버에서 응답이 없습니다. (API 토큰/모델 설정 확인 필요)")
                self.finished.emit(b"")
        except Exception as e:
            self.log.emit(f"❌ 오류 발생: {e}")
            self.finished.emit(b"")


class TranslationWorker(QThread):
    progress = pyqtSignal(str, int, int)  # detail, current, total
    finished = pyqtSignal(object)
    error = pyqtSignal(str)
    canceled = pyqtSignal(object)

    def __init__(self, engine, texts, provider="openai", chunk_size=20):
        super().__init__()
        self.engine = engine
        self.texts = [str(t or "") for t in (texts or [])]
        self.provider = provider or "openai"
        try:
            self.chunk_size = max(1, min(int(chunk_size or 20), 100))
        except Exception:
            self.chunk_size = 20
        self.cancel_requested = False

    def stop(self):
        self.cancel_requested = True

    def run(self):
        total = len(self.texts)
        results = []
        try:
            if total <= 0:
                self.finished.emit([])
                return
            for start in range(0, total, self.chunk_size):
                if self.cancel_requested:
                    self.canceled.emit(results)
                    return
                end = min(total, start + self.chunk_size)
                self.progress.emit(f"번역 중: {start + 1}-{end} / {total}", start, total)
                chunk = self.texts[start:end]
                translated = self.engine.translate_text_batch(
                    chunk,
                    provider=self.provider,
                    chunk_size=len(chunk),
                )
                if translated is None:
                    translated = []
                translated = list(translated)
                if len(translated) < len(chunk):
                    translated.extend(chunk[len(translated):])
                elif len(translated) > len(chunk):
                    translated = translated[:len(chunk)]
                results.extend(translated)
                self.progress.emit(f"번역 완료: {end} / {total}", end, total)
                if self.cancel_requested:
                    self.canceled.emit(results)
                    return
            self.finished.emit(results)
        except Exception as e:
            self.error.emit(str(e))
