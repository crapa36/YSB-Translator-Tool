# YSB Translator Tool v2.0.1 Build Layout

## Placement

The refactored source keeps the application code in `ysb/`, runtime assets in `assets/`, and build-only helper files in `build_tools/`.

```text
YSBTranslator/
- main.py
- ysb_launcher.py
- ysb/
- assets/
  - YSB_icon.ico
  - ysb_splash.png
  - ysb_splash_boot.png
  - ysb_logo.png
- requirements_ysik_tool.txt
- cloud_oauth_client.json          # optional local file, do not commit publicly
- cloud_oauth_client.example.json  # safe template for repository use
- run_main_v2.0.1.bat
- build_tools/
  - build_exe_v2.0.1.bat
  - version_main.txt
  - version_launcher.txt
```

## Development run

Run from the project root:

```bat
run_main_v2.0.1.bat
```

This creates or reuses:

```text
YSBTranslator/.venv/
```

## EXE build

Run directly from `build_tools/`:

```bat
build_tools\build_exe_v2.0.1.bat
```

The build script treats the parent folder of `build_tools/` as the project root.
It reuses the root `.venv` created by `run_main_v2.0.1.bat`; if `.venv` does not exist, it creates it.

## Build outputs

```text
dist/
- 역식붕이 툴 v2.0.1.exe
- YSB_Launcher.exe
```

## Notes

- `ysb_launcher.py` is the official launcher entry point.
- `YSB_Launcher.exe` is the official launcher executable name.
- `version_launcher.txt` is the launcher version metadata file.
- `version_opener.txt`, `YSB_FileOpener.exe`, and `YSBT Luncher.exe` are deprecated and not used in the v2.0.1 layout.
