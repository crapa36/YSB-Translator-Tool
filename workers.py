import os
import copy
import cv2
import numpy as np
import requests
import time
from PyQt6.QtCore import QThread, pyqtSignal


def _imread_unicode(path: str):
    arr = np.fromfile(path, np.uint8)
    return cv2.imdecode(arr, cv2.IMREAD_COLOR)


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
    # page index, payload dict
    # payload는 메인 스레드에서 self.data[i]에 반영된다.
    finished_item = pyqtSignal(int, object)
    finished_all = pyqtSignal()

    def __init__(self, main_window, mode):
        super().__init__()
        self.main = main_window
        self.mode = mode
        self.engine = main_window.engine
        self.is_running = True

        # 스레드 안에서 UI 위젯을 직접 읽지 않도록 시작 시점 값만 복사
        self.paths = list(main_window.paths)
        self.provider = main_window.cb_trans_provider.currentData()
        self.font_family = main_window.cb_font.currentFont().family()
        self.stroke_size = main_window.sb_strk.value()
        self.font_size = main_window.sb_font_size.value()
        self.mask_toggle_enabled = bool(getattr(main_window, "mask_toggle_enabled", False))
        self.project_dir = getattr(main_window, "project_dir", None)

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

    def run(self):
        total = len(self.paths)

        for i, path in enumerate(self.paths):
            if not self.is_running:
                break

            curr_data = self.data_snapshot.get(i, {})
            base_name = os.path.basename(path)
            prefix = f"[{i + 1}/{total}]"

            try:
                payload = {}

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
                        continue

                    self.progress.emit(f"{prefix} 번역: {base_name}")
                    new_data = _copy_data_list(curr_data.get('data', []))
                    target_items = [item for item in new_data if item.get('use_inpaint', True)]

                    if not target_items:
                        self.progress.emit(f"{prefix} 번역 건너뜀: 체크된 항목 없음")
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
                        continue
                    if (not self.mask_toggle_enabled) and inpaint_mask is None:
                        self.progress.emit(f"{prefix} 인페인팅 건너뜀: OFF 페인팅 마스크 없음")
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
                        bg_bytes = requests.get(str(u)).content

                        # 중요: 워커 스냅샷 안에만 넣지 말고 payload로 main에 넘겨야 실제 페이지에 반영된다.
                        curr_data['bg_clean'] = bg_bytes
                        payload = {'bg_clean': bg_bytes}

                        self.progress.emit(f"{prefix} 인페인팅 완료")
                    else:
                        payload = {}
                        self.progress.emit(f"{prefix} ⚠️ 인페인팅 결과 없음")

                    # Replicate burst=1 제한 방지.
                    # _call_lama 내부에서도 429 재시도하지만, 장 사이 기본 간격을 둬야 일괄 성공률이 높다.
                    if i < total - 1:
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
                    )
                    payload = {}

                self.finished_item.emit(i, payload)

            except Exception as e:
                self.progress.emit(f"{prefix} ❌ 에러: {e}")

        self.progress.emit(f"✅ 일괄 {self.mode} 완료!")
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

    def run(self):
        try:
            if self.mask is not None:
                self.log.emit("🔄 CLOVA OCR로 영역 재분석 중...")
                o, d, mm, mi = self.engine.reanalyze_from_manual_mask(self.path, self.mask, self.data)
            else:
                self.log.emit("🚀 CLOVA 전체 분석 시작...")
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

    def run(self):
        try:
            self.log.emit("🎨 LaMa 인페인팅 시작...")
            res = self.engine.execute_inpainting(self.path, self.data, self.mask)
            if res:
                u = res[0] if isinstance(res, list) else res
                img_data = requests.get(str(u)).content
                self.finished.emit(img_data)
            else:
                self.log.emit("❌ 실패: LaMa 서버에서 응답이 없습니다. (API 토큰 확인 필요)")
                self.finished.emit(b"")
        except Exception as e:
            self.log.emit(f"❌ 오류 발생: {e}")
            self.finished.emit(b"")
