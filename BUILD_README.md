# YSB Translator Tool v2.1.0 Lite / Local Build Layout

## Placement

The source keeps the shared application code in `ysb/`, runtime assets in `assets/`, local-model placeholders in `local_models/`, and build helpers in `build_tools/`.

```text
YSBTranslator/
- main.py
- main_lite.py
- main_local.py
- ysb_launcher.py
- ysb/
- assets/
- local_models/
- requirements/
  - common.txt
  - lite.txt
  - local.txt
  - build.txt
- cloud_oauth_client.json          # optional local file, do not commit publicly
- cloud_oauth_client.example.json  # safe template for repository use
- run_lite_v2.1.0.bat
- run_local_v2.1.0.bat
- build_tools/
  - build_exe_v2.1.0.bat
  - build_pyinstaller_v2.1.0.py
  - build_probe.py
  - version_main_lite.txt
  - version_main_local.txt
  - version_launcher_v2.1.0.txt
```

## Development run

Run one of these from the project root:

```bat
run_lite_v2.1.0.bat
run_local_v2.1.0.bat
```

Both scripts create or reuse one shared virtual environment:

```text
YSBTranslator/.venv/
```

## Requirements

The old single `requirements_ysik_tool.txt` file is removed in v2.1.0.
Use the split requirements instead:

```text
requirements/common.txt    # shared runtime dependencies
requirements/lite.txt      # API/Lite dependencies
requirements/local.txt     # Local-only dependencies, currently placeholder
requirements/build.txt     # build dependencies
```

## EXE build

Run directly from the project root or from `build_tools/`:

```bat
build_tools\build_exe_v2.1.0.bat
```

The build script treats the parent folder of `build_tools/` as the project root. It reuses the root `.venv`; if `.venv` does not exist, it creates it.

## Notes

- `ysb_launcher.py` remains the official launcher entry point.
- `YSB_Launcher.exe` remains the official launcher executable name.
- Lite is built as onefile.
- Local is built as onedir.
- The existing `ysb/` code remains the common code area.
- Edition-specific slots live under `ysb/editions/`.


## v2.1.0 Local OCR 구성

- `comic_text_detector`는 OCR이 아니라 텍스트 위치/마스크 감지 계층입니다.
- Local판에서만 사용하며 Lite판에는 포함하지 않는 것을 원칙으로 합니다.
- vendored runtime은 `third_party/comic_text_detector/`에 있습니다.
- Local 빌드에는 `comic_text_detector.pt` 모델이 함께 포함됩니다.
- PaddleOCR은 Local OCR 문자 인식 엔진으로 사용합니다. comic_text_detector가 영역/마스크를 만들고, PaddleOCR이 각 영역의 원문을 읽습니다.
