# YSB Translator source layout

This build keeps `main.py` as a small entry point and moves the application code into the `ysb/` package.

## Folders

- `ysb/ui/`: main window, launcher/home screen, viewer, delegates, and UI mixins
- `ysb/engine/`: manga/OCR/layout/image-rendering related engine code
- `ysb/services/`: worker threads and long-running task services
- `ysb/core/`: project/package/workspace/cache/launcher/file-association utilities
- `ysb/settings/`: API and shortcut setting windows/stores
- `ysb/i18n/`: Korean/English UI text dictionaries
- `ysb/utils/`: small shared helpers
- `assets/`: icons, splash images, README images, screenshots
- `build_tools/`: PyInstaller build scripts and Windows version metadata files

## Main entry points

- `main.py`: run the main application
- `ysb_launcher.py`: official launcher entry point for `.yspt` / `.ysbt` double-click launching

The old giant `main.py` was split into `ysb/ui/main_window.py` plus feature-specific mixins.

## Launcher policy

- Official launcher module: `ysb/core/ysb_launcher.py`
- Official root entry: `ysb_launcher.py`
- Preferred Windows EXE name: `YSB_Launcher.exe`
- Deprecated old names: `ysb_file_opener.py`, `YSB_FileOpener.exe`, `YSBT Luncher.exe`, `YSBT Launcher.exe`

If a Windows file association still points to an old opener executable, unregister the association in the app and register it again so it points to `YSB_Launcher.exe`.

## Build layout

Build helper files are grouped under `build_tools/`.

```text
build_tools/build_exe_v2.0.0.bat
build_tools/version_main.txt
build_tools/version_launcher.txt
```

The build script treats the parent directory of `build_tools/` as the project root and uses the root `.venv`.

## MainWindow split update

`ysb/ui/main_window.py` now keeps the main `MainWindow` entry class and startup hooks.
Large feature groups were moved into mixin modules under `ysb/ui/`:

- `main_window_support.py`: shared imports, constants, helper functions, and dialog/widget support classes
- `main_window_interaction_mixin.py`: actions, shortcuts, tooltips, launcher/editor switching
- `main_window_cloud_mixin.py`: Google Drive cloud backup/restore and OAuth flow
- `main_window_settings_theme_mixin.py`: settings dialogs, menus, language, theme, and main UI setup
- `main_window_text_layout_mixin.py`: text presets, text styling, auto layout, and table/text item editing
- `main_window_project_pages_mixin.py`: page tabs, project/workspace/file management, import/save workflows
- `main_window_history_mixin.py`: final-paint helpers, logging, macros, view state, undo/redo history
- `main_window_operations_mixin.py`: API/settings entry points, magic wand, analysis, translation, inpainting, export/batch, keyboard handling
