# YSB Tool v2.1.0 Lite / Local Split

## 목적

v2.1.0은 새 기능을 추가하기 전, 기존 v2.0.1 구조를 Lite / Local 두 배포판으로 나눠 개발할 수 있게 만든 구조 패치입니다.

- Lite: 기존 API 기반 경량판
- Local: PaddleOCR 같은 로컬 엔진을 붙이기 위한 폴더형 중량판
- 기존 `ysb/core`, `ysb/ui`, `ysb/services`, `ysb/settings`, `ysb/engine`은 공통 코드로 유지
- `.ysbt` 프로젝트 파일 구조는 Lite / Local 공통 유지

## 새 진입점

```text
main.py          기본값: Lite
main_lite.py     Lite 명시 실행
main_local.py    Local 명시 실행
```

## 새 실행 BAT

```text
run_main_v2.1.0.bat    Lite 기본 실행
run_lite_v2.1.0.bat    Lite 실행
run_local_v2.1.0.bat   Local 실행
```

두 실행 BAT는 같은 `.venv`를 공유합니다.

## 새 구조

```text
ysb/editions/
  current.py              현재 배포판 선택기
  lite/
    edition_config.py     Lite 전용 설정 슬롯
  local/
    edition_config.py     Local 전용 설정 슬롯
    local_dependency_check.py
    paddle_model_manager.py

ysb/engines/ocr/
  base.py                 공통 OCR 인터페이스 자리
  api_ocr.py              API OCR 어댑터 자리
  paddle_ocr.py           PaddleOCR 어댑터 자리
  manager.py              OCR 엔진 선택 자리

requirements/
  common.txt
  lite.txt
  local.txt
  build.txt

local_models/
  .gitkeep                Local 모델 폴더 자리
```

## 빌드

```bat
build_tools\build_exe.bat
```

이 BAT는 하나의 `.venv`를 사용해서 Lite와 Local을 모두 빌드합니다.

예상 결과:

```text
dist/
  역식붕이 툴 Lite v2.1.0.exe
  역식붕이 툴 Local v2.1.0/
  YSB_Launcher.exe
  packages/
    YSB_Tool_Lite_v2.1.0.zip
    YSB_Tool_Local_v2.1.0.zip
```

## 배포 정책

- Lite는 `--onefile` 빌드입니다.
- Local은 `--onedir` 빌드입니다.
- Local용 모델/엔진 파일은 앞으로 `local_models/` 또는 Local 전용 모듈 쪽에 붙입니다.
- Lite 빌드에서는 `paddleocr`, `paddlepaddle`, `paddle`을 제외하도록 준비했습니다.

## 중요한 규칙

- 공통 파일에서 `from paddleocr import PaddleOCR`처럼 직접 import하지 않습니다.
- Local 전용 무거운 import는 Local 모듈 안에서, 가능하면 함수 내부에서 늦게 import합니다.
- 기존 OCR 기능은 아직 이동하지 않았습니다. v2.1.0은 구조 분리 패치입니다.
- 다음 단계에서 기존 OCR 흐름을 `ysb/engines/ocr/` 인터페이스에 맞춰 연결하면 됩니다.


## v2.1.0 Local comic_text_detector 준비

- `comic_text_detector`는 OCR이 아니라 텍스트 위치/마스크 감지 계층입니다.
- Local판에서만 사용하며 Lite판에는 포함하지 않는 것을 원칙으로 합니다.
- vendored runtime은 `third_party/comic_text_detector/`에 있습니다.
- Local 빌드에는 `comic_text_detector.pt` 모델이 함께 포함됩니다.
- PaddleOCR은 아직 추가하지 않았고, 나중에 detector가 잡은 crop을 읽는 OCR 엔진으로 붙이는 방향입니다.

## Local comic_text_detector mask visual test

Before connecting PaddleOCR, test whether comic_text_detector creates a usable removal mask.

```bat
pip install -r requirements/common.txt
pip install -r requirements/local.txt
python scripts/local/test_comic_text_mask.py "C:\path\to\page.png" --device cpu
```

Output folder:

```text
<image>_mask_test/
  *.comic_mask_test_report.json
  *.comic_text_mask.png
  *.comic_text_mask_refined.png
  *.mask_used.png
  *.mask_overlay.png
  *.mask_whiteout_preview.png
  *.mask_cv2_inpaint_preview.png
```

Check `*.mask_overlay.png` first. Red areas are pixels selected by the detector mask.
Then check `*.mask_cv2_inpaint_preview.png`. This is only a quick OpenCV preview, not final LaMa/API inpainting, but it shows whether the mask is covering the right text area.

If outlines are left behind, try expanding the preview mask:

```bat
python scripts/local/test_comic_text_mask.py "C:\path\to\page.png" --device cpu --dilate 2
```
