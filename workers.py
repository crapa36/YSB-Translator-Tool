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
                    'bg_clean': None,
                }
            else:
                self.data_snapshot[i] = {
                    'ori': src.get('ori'),
                    'data': _copy_data_list(src.get('data', [])),
                    'mask_merge': _copy_mask(src.get('mask_merge')),
                    'mask_inpaint': _copy_mask(src.get('mask_inpaint')),
                    'bg_clean': src.get('bg_clean'),
                    'original_name': src.get('original_name'),
                }

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
                    if not curr_data.get('data'):
                        continue

                    self.progress.emit(f"{prefix} 리페인팅: {base_name}")

                    res_url = self.engine.execute_inpainting(
                        path,
                        curr_data.get('data', []),
                        curr_data.get('mask_inpaint')
                    )

                    if res_url:
                        u = res_url[0] if isinstance(res_url, list) else res_url
                        bg_bytes = requests.get(str(u)).content

                        # 중요: 워커 스냅샷 안에만 넣지 말고 payload로 main에 넘겨야 실제 페이지에 반영된다.
                        curr_data['bg_clean'] = bg_bytes
                        payload = {'bg_clean': bg_bytes}

                        self.progress.emit(f"{prefix} 리페인팅 완료")
                    else:
                        payload = {}
                        self.progress.emit(f"{prefix} ⚠️ 리페인팅 결과 없음")

                    # Replicate burst=1 제한 방지.
                    # _call_lama 내부에서도 429 재시도하지만, 장 사이 기본 간격을 둬야 일괄 성공률이 높다.
                    if i < total - 1:
                        time.sleep(5)

                elif self.mode == 'refresh':
                    self.progress.emit(f"{prefix} 텍스트 갱신: {base_name}")
                    payload = {}

                elif self.mode == 'export':
                    if not curr_data.get('bg_clean'):
                        continue
                    self.progress.emit(f"{prefix} 출력: {base_name}")
                    self.engine.export_project_result(
                        curr_data.get('data', []),
                        path,
                        curr_data.get('bg_clean'),
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
            self.log.emit("🎨 LaMa 리페인팅 시작...")
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
