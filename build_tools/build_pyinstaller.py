# -*- coding: utf-8 -*-
"""
YSB Translator Tool v2.0.0 optimized onefile build driver.

Hard constraints:
- Keep onefile.
- Keep launcher splash.
- Keep launcher lightweight.
- Avoid bundling README/demo/screenshot assets into runtime EXEs.
"""

from __future__ import annotations

import locale
import os
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_TOOLS_DIR = Path(__file__).resolve().parent
DIST_DIR = PROJECT_ROOT / "dist"
LOG_FILE = PROJECT_ROOT / "build_log.txt"

MAIN_ENTRY = PROJECT_ROOT / "main.py"
LAUNCHER_ENTRY = PROJECT_ROOT / "ysb_launcher.py"
YSB_PACKAGE_DIR = PROJECT_ROOT / "ysb"

ASSETS_DIR = PROJECT_ROOT / "assets"
ICON_FILE = ASSETS_DIR / "YSB_icon.ico"
SPLASH_FILE = ASSETS_DIR / "ysb_splash.png"
BOOT_SPLASH_FILE = ASSETS_DIR / "ysb_splash_boot.png"
LOGO_FILE = ASSETS_DIR / "ysb_logo.png"

VERSION_MAIN = BUILD_TOOLS_DIR / "version_main.txt"
VERSION_LAUNCHER = BUILD_TOOLS_DIR / "version_launcher.txt"

DATA_SEP = ";" if os.name == "nt" else ":"


def log(line: str = "") -> None:
    print(line, flush=True)
    with LOG_FILE.open("a", encoding="utf-8") as f:
        f.write(line + "\n")


def decode_subprocess_line(raw: bytes) -> str:
    candidates: list[str] = []
    preferred = locale.getpreferredencoding(False)
    if preferred:
        candidates.append(preferred)
    candidates.extend(["utf-8", "mbcs", "cp949", "euc-kr"])

    seen: set[str] = set()
    for enc in candidates:
        key = enc.lower()
        if key in seen:
            continue
        seen.add(key)
        try:
            return raw.decode(enc).rstrip("\r\n")
        except (UnicodeDecodeError, LookupError):
            continue
    return raw.decode("utf-8", errors="replace").rstrip("\r\n")


def require_file(path: Path, label: str) -> None:
    if not path.exists():
        raise FileNotFoundError(f"{label} not found: {path}")


def require_dir(path: Path, label: str) -> None:
    if not path.exists() or not path.is_dir():
        raise FileNotFoundError(f"{label} not found: {path}")


def pyinstaller_executable() -> list[str]:
    exe = PROJECT_ROOT / ".venv" / "Scripts" / "pyinstaller.exe"
    if exe.exists():
        return [str(exe)]
    return [sys.executable, "-m", "PyInstaller"]


def add_data_arg(src: Path, dest: str) -> str:
    return f"{src}{DATA_SEP}{dest}"


def run_command(args: list[str], label: str) -> None:
    log("")
    log(f"=== {label} ===")
    log(" ".join(f'"{a}"' if " " in a else a for a in args))

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")

    proc = subprocess.Popen(
        args,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        env=env,
    )

    if proc.stdout is None:
        raise RuntimeError("Failed to capture PyInstaller output.")

    for raw_line in proc.stdout:
        log(decode_subprocess_line(raw_line))

    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"{label} failed with exit code {ret}")


def hidden_import_args(modules: list[str]) -> list[str]:
    args: list[str] = []
    for mod in modules:
        args += ["--hidden-import", mod]
    return args


def exclude_module_args(modules: list[str]) -> list[str]:
    args: list[str] = []
    for mod in modules:
        args += ["--exclude-module", mod]
    return args


def copy_metadata_args(packages: list[str]) -> list[str]:
    """Include package metadata needed by libraries that call importlib.metadata.

    Replicate reads its installed package metadata at runtime. Without the
    dist-info metadata inside a PyInstaller onefile bundle, inpainting can fail
    with: "No package metadata was found for replicate".
    """
    args: list[str] = []
    for package in packages:
        args += ["--copy-metadata", package]
    return args


def base_args() -> list[str]:
    return [
        "--noconfirm",
        "--clean",
        "--onefile",
        "--windowed",
        "--log-level",
        "WARN",
        "--paths",
        str(PROJECT_ROOT),
    ]


def runtime_asset_args(include_logo: bool) -> list[str]:
    """
    Add only runtime assets.

    Do NOT add the whole assets directory, because it may contain README
    screenshots, demo images, manual media, or other files that should never be
    bundled into the onefile runtime.
    """
    files = [ICON_FILE, SPLASH_FILE, BOOT_SPLASH_FILE]
    if include_logo and LOGO_FILE.exists():
        files.append(LOGO_FILE)

    args: list[str] = []
    for f in files:
        args += ["--add-data", add_data_arg(f, "assets")]
    return args


def main_hidden_imports() -> list[str]:
    """
    Keep this minimal. PyInstaller can follow normal imports from
    ysb.ui.main_window. We only force the entry modules that may be reached
    through wrapper/run patterns.
    """
    return [
        "ysb",
        "ysb.ui.main_window",
        "ysb.core.ysb_launcher",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtPrintSupport",
        "PIL._imaging",
    ]


def main_excludes() -> list[str]:
    return [
        # Main app does not use tkinter; launcher does.
        "tkinter",
        "_tkinter",
        "tcl",
        "tk",

        # Common heavy scientific / notebook packages that may be pulled by hooks.
        "matplotlib",
        "pandas",
        "scipy",
        "sklearn",
        "torch",
        "tensorflow",
        "seaborn",
        "IPython",
        "notebook",
        "pytest",

        # Qt modules not used by this app.
        "PyQt6.QtWebEngineCore",
        "PyQt6.QtWebEngineWidgets",
        "PyQt6.QtWebEngineQuick",
        "PyQt6.QtQml",
        "PyQt6.QtQuick",
        "PyQt6.QtQuickWidgets",
        "PyQt6.QtMultimedia",
        "PyQt6.QtMultimediaWidgets",
        "PyQt6.QtBluetooth",
        "PyQt6.QtNetworkAuth",
        "PyQt6.QtPositioning",
        "PyQt6.QtSensors",
        "PyQt6.QtSerialPort",
        "PyQt6.QtSql",
        "PyQt6.QtTest",
        "PyQt6.QtXml",
    ]


def launcher_hidden_imports() -> list[str]:
    return [
        "ysb",
        "ysb.core",
        "ysb.core.ysb_launcher",
        "tkinter",
        "tkinter.ttk",
    ]


def launcher_excludes() -> list[str]:
    return [
        # Keep launcher from dragging the full application stack.
        "PyQt6",
        "cv2",
        "numpy",
        "PIL",
        "Pillow",
        "openai",
        "replicate",
        "requests",
        "google",
        "googleapiclient",
        "google_auth_oauthlib",
        "matplotlib",
        "pandas",
        "scipy",
        "sklearn",
        "torch",
        "tensorflow",
        "seaborn",
        "IPython",
        "notebook",
        "pytest",
    ]


def main_args() -> list[str]:
    args = base_args()
    args += hidden_import_args(main_hidden_imports())
    args += exclude_module_args(main_excludes())

    # Inpainting uses the Replicate SDK at runtime. PyInstaller can include the
    # code but omit package metadata, which breaks replicate's metadata lookup.
    args += copy_metadata_args(["replicate"])

    args += runtime_asset_args(include_logo=True)

    oauth_client = PROJECT_ROOT / "cloud_oauth_client.json"
    if oauth_client.exists():
        args += ["--add-data", add_data_arg(oauth_client, ".")]

    return args


def launcher_args() -> list[str]:
    args = base_args()
    args += hidden_import_args(launcher_hidden_imports())
    args += exclude_module_args(launcher_excludes())
    args += runtime_asset_args(include_logo=False)
    return args


def build_main() -> None:
    args = pyinstaller_executable() + main_args() + [
        "--name",
        "역식붕이 툴 v2.0.0",
        "--icon",
        str(ICON_FILE),
        "--version-file",
        str(VERSION_MAIN),
        str(MAIN_ENTRY),
    ]
    run_command(args, "Building main onefile EXE")


def build_launcher() -> None:
    args = pyinstaller_executable() + launcher_args() + [
        "--name",
        "YSB_Launcher",
        "--icon",
        str(ICON_FILE),
        "--version-file",
        str(VERSION_LAUNCHER),
        str(LAUNCHER_ENTRY),
    ]
    run_command(args, "Building lightweight launcher onefile EXE")


def main() -> int:
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    log("YSB Translator Tool v2.0.0 optimized onefile build driver")
    log(f"Project root: {PROJECT_ROOT}")
    log(f"Build tools:  {BUILD_TOOLS_DIR}")
    log("Build policy: onefile kept, launcher splash kept, runtime assets only")

    require_file(MAIN_ENTRY, "Main entry")
    require_file(LAUNCHER_ENTRY, "Launcher entry")
    require_dir(YSB_PACKAGE_DIR, "ysb package directory")
    require_file(YSB_PACKAGE_DIR / "__init__.py", "ysb package __init__.py")
    require_file(YSB_PACKAGE_DIR / "ui" / "main_window.py", "ysb.ui.main_window")
    require_file(YSB_PACKAGE_DIR / "core" / "ysb_launcher.py", "ysb.core.ysb_launcher")
    require_file(ICON_FILE, "Icon file")
    require_file(SPLASH_FILE, "Splash file")
    require_file(BOOT_SPLASH_FILE, "Boot splash file")
    require_file(VERSION_MAIN, "Main version file")
    require_file(VERSION_LAUNCHER, "Launcher version file")

    DIST_DIR.mkdir(exist_ok=True)

    for spec in PROJECT_ROOT.glob("*.spec"):
        try:
            spec.unlink()
        except OSError:
            pass

    build_main()
    build_launcher()

    main_exe = DIST_DIR / "역식붕이 툴 v2.0.0.exe"
    launcher_exe = DIST_DIR / "YSB_Launcher.exe"

    require_file(main_exe, "Built main EXE")
    require_file(launcher_exe, "Built launcher EXE")

    log("")
    log("Build completed successfully.")
    log(f"Main EXE:     {main_exe}")
    log(f"Launcher EXE: {launcher_exe}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        log("")
        log(f"ERROR: {exc}")
        raise SystemExit(1)
