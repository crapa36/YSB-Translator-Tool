# -*- coding: utf-8 -*-
"""
YSB Translator Tool split PyInstaller build core.

Use the small edition drivers instead of building both editions together:
- build_pyinstaller_lite.py  -> Lite/API package only
- build_pyinstaller_local.py -> Local package only

Policy:
- One source tree.
- One shared builder virtual environment.
- One build invocation produces exactly one edition package.
- Lite: API-based onefile EXE.
- Local: folder-style onedir build with PaddleOCR + comic_text_detector + LaMa assets.
"""

from __future__ import annotations

import locale
import os
import shutil
import subprocess
import sys
import time
import urllib.request
import zipfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
BUILD_TOOLS_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(PROJECT_ROOT))

from ysb.version_info import (
    APP_FAMILY_ID,
    APP_VERSION,
    BUILD_LOG_FILE_NAME,
    COMPANY_NAME,
    LITE_MAIN_EXE_NAME,
    LITE_PACKAGE_FOLDER_NAME,
    LITE_PACKAGE_ZIP_NAME,
    LOCAL_MAIN_EXE_NAME,
    LOCAL_PACKAGE_FOLDER_NAME,
    LOCAL_PACKAGE_ZIP_NAME,
    PRODUCT_NAME,
    WINDOWS_VERSION_STRING,
    WINDOWS_VERSION_TUPLE,
    windows_original_filename,
)

DIST_DIR = PROJECT_ROOT / "dist"
LOG_FILE = PROJECT_ROOT / BUILD_LOG_FILE_NAME

LITE_ENTRY = PROJECT_ROOT / "main_lite.py"
LOCAL_ENTRY = PROJECT_ROOT / "main_local.py"
LAUNCHER_ENTRY = PROJECT_ROOT / "ysb_launcher.py"
YSB_PACKAGE_DIR = PROJECT_ROOT / "ysb"

ASSETS_DIR = PROJECT_ROOT / "assets"
GENERATED_ICON_DIR = BUILD_TOOLS_DIR / "_generated_icons"
ICON_FILE = ASSETS_DIR / "ysb_icon.ico"
ICON_PNG_FILE = ASSETS_DIR / "ysb_icon.png"
YSBT_FILE_ICON = ASSETS_DIR / "ysbt_file_icon.ico"
YSBT_FILE_ICON_PNG = ASSETS_DIR / "ysbt_file_icon.png"
LAUNCHER_ICON = ASSETS_DIR / "ysb_launcher_icon.ico"
LAUNCHER_ICON_PNG = ASSETS_DIR / "ysb_launcher_icon.png"
SPLASH_FILE = ASSETS_DIR / "ysb_splash.png"
BOOT_SPLASH_FILE = ASSETS_DIR / "ysb_splash_boot.png"
LOGO_FILE = ASSETS_DIR / "ysb_logo.png"
LOCAL_MODELS_DIR = PROJECT_ROOT / "local_models"
THIRD_PARTY_DIR = PROJECT_ROOT / "third_party"
COMIC_TEXT_DETECTOR_DIR = THIRD_PARTY_DIR / "comic_text_detector"
LOCAL_RUNTIME_DIR = PROJECT_ROOT / "local_runtime"
PADDLEOCR_WORKER_FILE = LOCAL_RUNTIME_DIR / "paddle_ocr_worker.py"
MANGA_OCR_WORKER_FILE = LOCAL_RUNTIME_DIR / "manga_ocr_worker.py"
GPU_PROBE_WORKER_FILE = LOCAL_RUNTIME_DIR / "gpu_probe_worker.py"
LOCAL_LAMA_WORKER_FILE = LOCAL_RUNTIME_DIR / "local_lama_worker.py"
OCR_WORKER_REQUIREMENTS = PROJECT_ROOT / "requirements" / "ocr_worker.txt"  # legacy compatibility
PADDLE_OCR_WORKER_REQUIREMENTS = PROJECT_ROOT / "requirements" / "paddle_ocr_worker.txt"
MANGA_OCR_WORKER_REQUIREMENTS = PROJECT_ROOT / "requirements" / "manga_ocr_worker.txt"
PORTABLE_PYTHON_VERSION = os.environ.get("YSB_PORTABLE_PYTHON_VERSION", "3.11.9").strip() or "3.11.9"
PORTABLE_PYTHON_ZIP_NAME = f"python-{PORTABLE_PYTHON_VERSION}-embed-amd64.zip"
PORTABLE_PYTHON_URL = f"https://www.python.org/ftp/python/{PORTABLE_PYTHON_VERSION}/{PORTABLE_PYTHON_ZIP_NAME}"
RUNTIME_CACHE_DIR = BUILD_TOOLS_DIR / "runtime_cache"
PIP_BOOTSTRAP_PACKAGE = os.environ.get("YSB_PIP_BOOTSTRAP_PACKAGE", "pip<26").strip() or "pip<26"
PADDLEOCR_MODELS_DIR = LOCAL_MODELS_DIR / "paddleocr"
LAMA_MODELS_DIR = LOCAL_MODELS_DIR / "lama"
MANGA_OCR_MODELS_DIR = LOCAL_MODELS_DIR / "manga_ocr"

VERSION_LITE_MAIN = BUILD_TOOLS_DIR / "version_main_lite.txt"
VERSION_LOCAL_MAIN = BUILD_TOOLS_DIR / "version_main_local.txt"
VERSION_LAUNCHER = BUILD_TOOLS_DIR / "version_launcher.txt"

LITE_NAME = LITE_MAIN_EXE_NAME
LOCAL_NAME = LOCAL_MAIN_EXE_NAME
LAUNCHER_NAME = "YSB_Launcher"

DATA_SEP = ";" if os.name == "nt" else ":"
VALID_EDITIONS = {"lite", "local"}

# Development/test-only optional modules must never be frozen into release builds.
# They may exist in the source tree for BAT/source-run diagnostics, but Lite/Local
# packages must not contain them.
DEV_TEST_EXCLUDE_MODULES = [
    "ysb_devtools",
    "ysb_devtools.simulation_courses",
    "ysb_devtools.simulation_panel",
    "ysb_devtools.simulation_report",
    "ysb_devtools.simulation_runner",
    "ysb_devtools.simulation_steps",
    "ysb_test_addon",
]
DEV_TEST_PACKAGE_NAMES = {"ysb_devtools", "ysb_test_addon"}


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


def _make_build_icon_from_png(src: Path, out_name: str) -> Path | None:
    """Build-time helper: allow icon assets to be kept as PNG and convert to ICO."""
    if not src.exists():
        return None
    GENERATED_ICON_DIR.mkdir(parents=True, exist_ok=True)
    dst = GENERATED_ICON_DIR / out_name
    try:
        from PIL import Image
        with Image.open(src) as im:
            im = im.convert("RGBA")
            im.save(dst, sizes=[(256, 256), (128, 128), (64, 64), (48, 48), (32, 32), (16, 16)])
        log(f"[icon] Generated {dst.name} from {src.relative_to(PROJECT_ROOT)}")
        return dst
    except Exception as exc:
        raise RuntimeError(f"Failed to convert icon PNG to ICO: {src} ({exc})") from exc


def _first_existing_icon(candidates: list[Path], generated_name: str) -> Path | None:
    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() == ".ico":
            return candidate
    for candidate in candidates:
        if candidate.exists() and candidate.suffix.lower() == ".png":
            return _make_build_icon_from_png(candidate, generated_name)
    return None


def main_build_icon() -> Path:
    icon = _first_existing_icon([ICON_FILE, ICON_PNG_FILE, ASSETS_DIR / "ysb_logo_icon.ico", ASSETS_DIR / "ysb_logo_icon.png"], "ysb_icon.ico")
    return icon or ICON_FILE


def ysbt_build_icon() -> Path | None:
    return _first_existing_icon([YSBT_FILE_ICON, YSBT_FILE_ICON_PNG], "ysbt_file_icon.ico")


def launcher_build_icon() -> Path:
    icon = _first_existing_icon([LAUNCHER_ICON, LAUNCHER_ICON_PNG], "ysb_launcher_icon.ico")
    if icon:
        return icon
    icon = ysbt_build_icon()
    if icon:
        return icon
    return main_build_icon()


def pyinstaller_executable() -> list[str]:
    # Use the current Python interpreter to launch PyInstaller.
    # This avoids stale/broken pyinstaller.exe launchers after build-tool renames
    # or virtualenv rebuilds.
    return [sys.executable, "-m", "PyInstaller"]


def add_data_arg(src: Path, dest: str) -> str:
    return f"{src}{DATA_SEP}{dest}"


def format_bytes(value: int) -> str:
    units = ["B", "KB", "MB", "GB"]
    size = float(value)
    for unit in units:
        if size < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(size)} {unit}"
            return f"{size:.1f} {unit}"
        size /= 1024
    return f"{value} B"


def make_windows_version_text(*, description: str, internal_name: str, original_filename: str, role: str, edition: str) -> str:
    version_tuple = tuple(int(x) for x in WINDOWS_VERSION_TUPLE)
    return f"""# UTF-8
VSVersionInfo(
  ffi=FixedFileInfo(
    filevers={version_tuple},
    prodvers={version_tuple},
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '040904B0',
        [
          StringStruct('CompanyName', {COMPANY_NAME!r}),
          StringStruct('FileDescription', {description!r}),
          StringStruct('FileVersion', {WINDOWS_VERSION_STRING!r}),
          StringStruct('InternalName', {internal_name!r}),
          StringStruct('OriginalFilename', {original_filename!r}),
          StringStruct('ProductName', {PRODUCT_NAME!r}),
          StringStruct('ProductVersion', {WINDOWS_VERSION_STRING!r}),
          StringStruct('YSBAppFamilyId', {APP_FAMILY_ID!r}),
          StringStruct('YSBAppRole', {role!r}),
          StringStruct('YSBEdition', {edition!r})
        ]
      )
    ]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


def generate_version_files() -> None:
    VERSION_LITE_MAIN.write_text(
        make_windows_version_text(
            description="YSB Translator Tool Lite Main",
            internal_name="YSB_MAIN",
            original_filename=windows_original_filename("lite"),
            role="YSB_MAIN",
            edition="lite",
        ),
        encoding="utf-8",
    )
    VERSION_LOCAL_MAIN.write_text(
        make_windows_version_text(
            description="YSB Translator Tool Local Main",
            internal_name="YSB_MAIN",
            original_filename=windows_original_filename("local"),
            role="YSB_MAIN",
            edition="local",
        ),
        encoding="utf-8",
    )
    VERSION_LAUNCHER.write_text(
        make_windows_version_text(
            description="YSB Launcher",
            internal_name="YSB_LAUNCHER",
            original_filename="YSB_Launcher.exe",
            role="YSB_LAUNCHER",
            edition="common",
        ),
        encoding="utf-8",
    )



def _tail_file(path: Path, lines: int = 120) -> list[str]:
    try:
        if not path.exists() or not path.is_file():
            return []
        text = path.read_text(encoding="utf-8", errors="replace").splitlines()
        return text[-lines:]
    except Exception as exc:
        return [f"[failed to read {path}: {exc}]"]


def _dump_pyinstaller_diagnostics(label: str) -> None:
    """Write likely PyInstaller diagnostic files into the build log.

    Some PyInstaller failures do not print a helpful final traceback to stdout,
    especially when a Windows GUI build exits during analysis.  Dumping the
    generated warn/xref-like files makes the next failure actionable.
    """
    log("")
    log(f"--- PyInstaller diagnostics after failure: {label} ---")
    candidates: list[Path] = []

    build_dir = PROJECT_ROOT / "build"
    if build_dir.exists():
        for pattern in (
            "**/warn-*.txt",
            "**/*.log",
            "**/*.toc",
        ):
            try:
                candidates.extend(build_dir.glob(pattern))
            except Exception:
                pass

    # PyInstaller may write spec files in the project root before failing.
    try:
        candidates.extend(PROJECT_ROOT.glob("*.spec"))
    except Exception:
        pass

    seen: set[Path] = set()
    useful = [p for p in candidates if p.exists() and p.is_file() and p not in seen and not seen.add(p)]
    if not useful:
        log("No extra PyInstaller diagnostic files were found.")
        return

    for path in useful[:12]:
        log("")
        log(f"[diagnostic file] {path}")
        # .toc and .spec files can be huge; only tail them.
        for line in _tail_file(path, lines=80):
            log(line)

def run_command(args: list[str], label: str) -> None:
    log("")
    log(f"=== {label} ===")
    log(" ".join(f'\"{a}\"' if " " in a else a for a in args))

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PIP_NO_PYTHON_VERSION_WARNING", "1")
    env.setdefault("PIP_NO_INPUT", "1")

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
        _dump_pyinstaller_diagnostics(label)
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
    args: list[str] = []
    for package in packages:
        args += ["--copy-metadata", package]
    return args


def collect_data_args(packages: list[str]) -> list[str]:
    args: list[str] = []
    for package in packages:
        args += ["--collect-data", package]
    return args


def collect_binary_args(packages: list[str]) -> list[str]:
    args: list[str] = []
    for package in packages:
        args += ["--collect-binaries", package]
    return args


def base_args(onefile: bool) -> list[str]:
    args = [
        "--noconfirm",
        "--clean",
        "--windowed",
        "--noupx",
        "--log-level",
        os.environ.get("YSB_PYINSTALLER_LOG_LEVEL", "INFO"),
        "--paths",
        str(PROJECT_ROOT),
    ]
    args.append("--onefile" if onefile else "--onedir")
    return args


def runtime_asset_args(include_logo: bool) -> list[str]:
    files = [main_build_icon(), SPLASH_FILE, BOOT_SPLASH_FILE]
    ysbt_icon = ysbt_build_icon()
    launcher_icon = _first_existing_icon([LAUNCHER_ICON, LAUNCHER_ICON_PNG], "ysb_launcher_icon.ico")
    if ysbt_icon is not None:
        files.append(ysbt_icon)
    if launcher_icon is not None:
        files.append(launcher_icon)
    if include_logo and LOGO_FILE.exists():
        files.append(LOGO_FILE)

    args: list[str] = []
    for f in files:
        args += ["--add-data", add_data_arg(f, "assets")]
    return args


def common_main_hidden_imports() -> list[str]:
    return [
        "ysb",
        "ysb.ui.main_window",
        "ysb.core.ysb_launcher",
        "ysb.editions.current",
        "ysb.utils.crash_guard",
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "PyQt6.QtPrintSupport",
        "PIL._imaging",
    ]


def local_hidden_imports() -> list[str]:
    return [
        # YSB Local adapters
        "ysb.engines.ocr.base",
        "ysb.engines.ocr.paddle_ocr",
        "ysb.engines.ocr.manga_ocr",
        "ysb.engines.text_detection",
        "ysb.engines.text_detection.manager",
        "ysb.engines.text_detection.comic_text_detector",
        "ysb.editions.local.comic_model_manager",
        "ysb.editions.local.paddle_model_manager",
        "ysb.editions.local.local_dependency_check",

        # LOCAL PaddleOCR is intentionally NOT bundled into the PyInstaller
        # EXE.  It runs through local_runtime/paddle_ocr_worker.py using the
        # packaged OCR virtual environment.  This avoids Paddle/PaddleX frozen
        # import instability while keeping comic_text_detector and LaMa in EXE.

        # LOCAL comic_text_detector
        "torch",
        "torchvision",
        "pyclipper",
        "shapely",
        "yaml",
        "tqdm",
        "pkg_resources",

        # LOCAL LaMa
        "simple_lama_inpainting",
        "fire",
        "omegaconf",
        "einops",
        "safetensors",
        "huggingface_hub",
    ]


def common_heavy_excludes() -> list[str]:
    return [
        "matplotlib",
        # Do not exclude pandas globally. PaddleOCR/PaddleX imports pandas at
        # runtime even when the app only uses OCR inference. Excluding it from
        # the Local package makes PaddleOCR return empty text with
        # "No module named 'pandas'". Lite/launcher still exclude pandas below.
        "scipy",
        "sklearn",
        "tensorflow",
        "seaborn",
        "IPython",
        "notebook",
        "pytest",
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


def dev_test_excludes() -> list[str]:
    """Modules that are allowed in the source tree but forbidden in release builds."""
    return list(DEV_TEST_EXCLUDE_MODULES)


def lite_excludes() -> list[str]:
    return common_heavy_excludes() + dev_test_excludes() + [
        "pandas",
        "tkinter",
        "_tkinter",
        "tcl",
        "tk",
        # Local edition packages must not leak into Lite.
        "paddleocr",
        "paddlepaddle",
        "paddle",
        "torch",
        "torchvision",
        "pyclipper",
        "shapely",
        "wandb",
        "torchsummary",
        "simple_lama_inpainting",
        "fire",
        "omegaconf",
        "einops",
        "yaml",
        "transformers",
        "huggingface_hub",
        "tokenizers",
        "sentencepiece",
        "safetensors",
        "paddlex",
        "ppocr",
        "fugashi",
        "unidic_lite",
    ]


def local_excludes() -> list[str]:
    return common_heavy_excludes() + dev_test_excludes() + [
        "tkinter",
        "_tkinter",
        "tcl",
        "tk",
        # PaddleOCR 3.x no longer exposes the old ppocr top-level package in
        # some installs.  Keeping it as a hidden import produces noisy build
        # warnings, so explicitly ignore it.
        "ppocr",
        # PaddleOCR/PaddleX/Paddle/pandas are served by the external OCR worker
        # and should not be frozen into the main Local EXE.
        "paddleocr",
        "paddlepaddle",
        "paddle",
        "paddlex",
        "pandas",
        "modelscope",
        "aistudio_sdk",
        "pypdfium2",
        # Paddle/PaddleX branches that are not needed for YSB local inference.
        # In particular, importing paddle.jit.sot inside PyInstaller's isolated
        # dependency scanner can terminate the child process on Windows
        # (exit code 3221225477).  The OCR path uses PaddleOCR inference, not
        # SOT/JIT training/distributed tooling.
        "paddle.jit.sot",
        "paddle.jit.sot.utils",
        "paddle.jit.sot.opcode_translator",
        "paddle.jit.sot.opcode_translator.executor",
        "paddle.jit.sot.opcode_translator.instruction_utils",
        "paddle.jit.sot.symbolic_shape",
        "paddle.jit.sot.profiler",
        "paddle.distributed",
        "paddle.distributed.auto_parallel",
        "paddle.distributed.fleet",
        "paddle.distributed.launch",
        "paddle.distributed.ps",
        "paddle.distributed.rpc",
        "paddle.distributed.flex_checkpoint",
        "paddle.incubate",
        "paddle.incubate.distributed",
        "paddle.incubate.jit",
        "paddle.incubate.optimizer",
        "paddle.incubate.passes",
        "paddle.profiler",
        "paddle.utils.cpp_extension",
        "paddle.dataset",
        "paddle.hapi",
        "paddle.vision",
        "paddle.static.quantization",
        "paddle.quantization",
        # Removed experimental/local translation OCR stacks.
        "transformers",
        "tokenizers",
        "sentencepiece",
        "fugashi",
        "unidic_lite",
        "ctranslate2",
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
    return dev_test_excludes() + [
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
        "paddleocr",
        "paddlepaddle",
        "paddle",
        "torch",
        "torchvision",
        "pyclipper",
        "shapely",
        "wandb",
        "torchsummary",
        "simple_lama_inpainting",
        "fire",
        "omegaconf",
        "einops",
        "yaml",
        "paddlex",
        "ppocr",
        "matplotlib",
        "pandas",
        "scipy",
        "sklearn",
        "tensorflow",
        "seaborn",
        "IPython",
        "notebook",
        "pytest",
    ]


def main_args(entry: Path, *, edition: str, onefile: bool) -> list[str]:
    args = base_args(onefile=onefile)
    args += hidden_import_args(common_main_hidden_imports())
    if edition == "local":
        args += hidden_import_args(local_hidden_imports())
    args += exclude_module_args(lite_excludes() if edition == "lite" else local_excludes())

    # Replicate is still used by the API/Lite path and as an optional API fallback.
    args += copy_metadata_args(["replicate"])
    if edition == "local":
        # Keep LaMa metadata in the frozen EXE. PaddleOCR is deliberately
        # externalized to local_runtime/python and is not collected here.
        args += copy_metadata_args(["simple-lama-inpainting"])

    args += runtime_asset_args(include_logo=True)

    oauth_client = PROJECT_ROOT / "cloud_oauth_client.json"
    if oauth_client.exists():
        args += ["--add-data", add_data_arg(oauth_client, ".")]

    if edition == "local":
        # Bundle only supported Local assets. Do not add the whole local_models
        # folder, because old experimental test folders must not leak into the
        # Local package.
        if PADDLEOCR_MODELS_DIR.exists():
            args += ["--add-data", add_data_arg(PADDLEOCR_MODELS_DIR, "local_models/paddleocr")]
        else:
            log(f"[WARN] PaddleOCR local model folder not found, skipped: {PADDLEOCR_MODELS_DIR}")
        if LAMA_MODELS_DIR.exists():
            args += ["--add-data", add_data_arg(LAMA_MODELS_DIR, "local_models/lama")]
        else:
            log(f"[WARN] LaMa local model folder not found, skipped: {LAMA_MODELS_DIR}")
        if COMIC_TEXT_DETECTOR_DIR.exists():
            args += ["--add-data", add_data_arg(COMIC_TEXT_DETECTOR_DIR, "third_party/comic_text_detector")]
        else:
            log(f"[WARN] comic_text_detector vendor folder not found, skipped: {COMIC_TEXT_DETECTOR_DIR}")

    return args


def launcher_args() -> list[str]:
    args = base_args(onefile=True)
    args += hidden_import_args(launcher_hidden_imports())
    args += exclude_module_args(launcher_excludes())
    args += runtime_asset_args(include_logo=False)
    return args


def build_lite() -> None:
    args = pyinstaller_executable() + main_args(LITE_ENTRY, edition="lite", onefile=True) + [
        "--name",
        LITE_NAME,
        "--icon",
        str(main_build_icon()),
        "--version-file",
        str(VERSION_LITE_MAIN),
        str(LITE_ENTRY),
    ]
    run_command(args, "Building Lite onefile EXE")


def build_local() -> None:
    args = pyinstaller_executable() + main_args(LOCAL_ENTRY, edition="local", onefile=False) + [
        "--name",
        LOCAL_NAME,
        "--icon",
        str(main_build_icon()),
        "--version-file",
        str(VERSION_LOCAL_MAIN),
        str(LOCAL_ENTRY),
    ]
    run_command(args, "Building Local onedir EXE")


def build_launcher() -> None:
    launcher_icon = launcher_build_icon()
    log(f"[icon] Launcher build icon: {launcher_icon.relative_to(PROJECT_ROOT) if launcher_icon.is_relative_to(PROJECT_ROOT) else launcher_icon}")
    args = pyinstaller_executable() + launcher_args() + [
        "--name",
        LAUNCHER_NAME,
        "--icon",
        str(launcher_icon),
        "--version-file",
        str(VERSION_LAUNCHER),
        str(LAUNCHER_ENTRY),
    ]
    run_command(args, "Building shared launcher onefile EXE")


def folder_size(path: Path) -> int:
    if not path.exists():
        return 0
    if path.is_file():
        return path.stat().st_size
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except OSError:
                pass
    return total


def remove_path(path: Path) -> None:
    if not path.exists():
        return
    if path.is_dir():
        shutil.rmtree(path)
    else:
        path.unlink()


def clean_for_edition(edition: str) -> None:
    # PyInstaller's build folder is shared and safe to clean before each run.
    remove_path(PROJECT_ROOT / "build")

    # Remove intermediate PyInstaller outputs from previous builds.  Final user
    # output must be only these package folders in dist/:
    # - 역식붕이 툴 Lite vX.Y.Z_package
    # - 역식붕이 툴 Local vX.Y.Z_package
    remove_path(DIST_DIR / f"{LAUNCHER_NAME}.exe")
    remove_path(DIST_DIR / f"{LITE_NAME}.exe")
    remove_path(DIST_DIR / LOCAL_NAME)
    remove_path(DIST_DIR / "packages")
    remove_path(DIST_DIR / LITE_PACKAGE_ZIP_NAME)
    remove_path(DIST_DIR / LOCAL_PACKAGE_ZIP_NAME)

    # Rebuilding a selected edition should replace only that edition's final
    # package folder and keep the other edition folder for comparison/use.
    if edition == "lite":
        remove_path(DIST_DIR / LITE_PACKAGE_FOLDER_NAME)
    elif edition == "local":
        remove_path(DIST_DIR / LOCAL_PACKAGE_FOLDER_NAME)

    for spec in PROJECT_ROOT.glob("*.spec"):
        remove_path(spec)


def cleanup_intermediate_outputs() -> None:
    """Leave only final *_package folders under dist/."""
    remove_path(DIST_DIR / f"{LAUNCHER_NAME}.exe")
    remove_path(DIST_DIR / f"{LITE_NAME}.exe")
    remove_path(DIST_DIR / LOCAL_NAME)
    remove_path(DIST_DIR / "packages")
    remove_path(DIST_DIR / LITE_PACKAGE_ZIP_NAME)
    remove_path(DIST_DIR / LOCAL_PACKAGE_ZIP_NAME)
    for spec in PROJECT_ROOT.glob("*.spec"):
        remove_path(spec)


RUNTIME_LEFTOVER_NAMES = {
    "ysb_startup_stage.log",
    "ysb_startup_crash.log",
    "ysb_startup_faulthandler.log",
    "ysb_runtime_debug.log",
    "ysb_paddle_ocr_worker.log",
    "ysb_manga_ocr_worker.log",
}


def cleanup_runtime_leftovers(package_dir: Path) -> None:
    """Remove release-package diagnostic leftovers before final output.

    These files may be created during local test runs, but final Lite/Local
    packages should only contain user-facing executables and required runtime
    files.
    """
    if not package_dir.exists():
        return
    for name in RUNTIME_LEFTOVER_NAMES:
        remove_path(package_dir / name)
    for pattern in ("ysb_startup_*.log", "ysb_runtime_debug*.log"):
        for path in package_dir.glob(pattern):
            remove_path(path)
    for local_runtime in (package_dir / "local_runtime", package_dir / "local_runtime_exe"):
        if local_runtime.exists():
            for name in RUNTIME_LEFTOVER_NAMES:
                remove_path(local_runtime / name)
            for pattern in ("ysb_startup_*.log", "ysb_runtime_debug*.log", "ysb_paddle_ocr_worker*.log", "ysb_manga_ocr_worker*.log"):
                for path in local_runtime.glob(pattern):
                    remove_path(path)


def cleanup_dev_test_artifacts(package_dir: Path) -> None:
    """Remove optional source-only dev/test packages from release folders.

    PyInstaller is already told to exclude these modules.  This second pass is
    a safety net for onedir builds or accidental data-copy rules.
    """
    if not package_dir.exists():
        return
    for path in list(package_dir.rglob("*")):
        if path.name in DEV_TEST_PACKAGE_NAMES:
            remove_path(path)


def assert_no_dev_test_artifacts(package_dir: Path) -> None:
    if not package_dir.exists():
        return
    leaked = []
    for path in package_dir.rglob("*"):
        if path.name in DEV_TEST_PACKAGE_NAMES:
            leaked.append(path)
    if leaked:
        rels = ", ".join(str(p.relative_to(package_dir)) for p in leaked[:10])
        raise RuntimeError(f"Development/test package leaked into release build: {rels}")


def prepare_lite_package() -> None:
    lite_exe = DIST_DIR / f"{LITE_NAME}.exe"
    launcher_exe = DIST_DIR / f"{LAUNCHER_NAME}.exe"
    require_file(lite_exe, "Built Lite EXE")
    require_file(launcher_exe, "Built launcher EXE")

    lite_stage = DIST_DIR / LITE_PACKAGE_FOLDER_NAME
    remove_path(lite_stage)
    lite_stage.mkdir(parents=True, exist_ok=True)

    shutil.copy2(lite_exe, lite_stage / lite_exe.name)
    shutil.copy2(launcher_exe, lite_stage / launcher_exe.name)
    cleanup_runtime_leftovers(lite_stage)
    cleanup_dev_test_artifacts(lite_stage)
    assert_no_dev_test_artifacts(lite_stage)

    cleanup_intermediate_outputs()

    log("")
    log("Lite package prepared:")
    log(f"Lite package folder: {lite_stage}")
    log(f"Lite package size: {format_bytes(folder_size(lite_stage))}")



def _download_file(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(dest.suffix + ".tmp")
    log(f"Downloading portable Python runtime:")
    log(f"  {url}")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as f:
        shutil.copyfileobj(resp, f)
    tmp.replace(dest)


def _ensure_portable_python_zip() -> Path:
    env_zip = os.environ.get("YSB_PORTABLE_PYTHON_ZIP", "").strip()
    if env_zip:
        candidate = Path(env_zip).expanduser()
        require_file(candidate, "YSB_PORTABLE_PYTHON_ZIP")
        return candidate

    zip_path = RUNTIME_CACHE_DIR / PORTABLE_PYTHON_ZIP_NAME
    if zip_path.exists() and zip_path.stat().st_size > 1024 * 1024:
        return zip_path

    try:
        _download_file(PORTABLE_PYTHON_URL, zip_path)
    except Exception as exc:
        raise RuntimeError(
            "Failed to download portable Python embeddable runtime. "
            f"Download {PORTABLE_PYTHON_ZIP_NAME} manually from python.org and set "
            "YSB_PORTABLE_PYTHON_ZIP to that ZIP path, or place it in "
            f"{RUNTIME_CACHE_DIR}. Original error: {exc}"
        ) from exc
    return zip_path


def _configure_embeddable_python_path(portable_python_dir: Path) -> None:
    # Windows embeddable Python is isolated by pythonXY._pth.  Add Lib and
    # Lib\site-packages so packages installed with pip --target are visible.
    pth_files = list(portable_python_dir.glob("python*._pth"))
    if not pth_files:
        return
    pth = pth_files[0]
    lines = []
    existing = set()
    for raw in pth.read_text(encoding="utf-8", errors="replace").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line == "import site":
            continue
        if line not in existing:
            lines.append(line)
            existing.add(line)
    for line in [".", "Lib", "Lib\\site-packages", "import site"]:
        if line == "import site" or line not in existing:
            lines.append(line)
            existing.add(line)
    pth.write_text("\n".join(lines) + "\n", encoding="utf-8")


def _prune_runtime_tree(path: Path) -> None:
    patterns = {"__pycache__", "tests", "test"}
    for child in list(path.rglob("*")):
        try:
            if child.is_dir() and child.name in patterns:
                shutil.rmtree(child, ignore_errors=True)
            elif child.is_file() and child.suffix.lower() in {".pyc", ".pyo"}:
                child.unlink(missing_ok=True)
        except Exception:
            pass


def _install_worker_dependencies(requirements_file: Path, target_site_packages: Path, label: str) -> None:
    require_file(requirements_file, f"{label} requirements")
    target_site_packages.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable,
        "-m",
        "pip",
        "--disable-pip-version-check",
        "install",
        "--upgrade",
        "--no-warn-script-location",
        "--no-warn-conflicts",
        "--prefer-binary",
        "--target",
        str(target_site_packages),
        "-r",
        str(requirements_file),
    ]
    run_command(args, f"Installing portable {label} dependencies")




def _prepare_pip_bootstrap_wheels(runtime_stage: Path) -> None:
    """Bundle a pip wheel for Python-free online runtime installs.

    Local EXE portable worker Pythons intentionally do not need pip installed in
    their site-packages.  CUDA runtime repair/install uses this wheel as a small
    bootstrap tool and then downloads heavy packages online into --target
    folders such as local_runtime_exe/torch_cuda_runtime.
    """
    wheel_dir = runtime_stage / "_bootstrap_wheels"
    remove_path(wheel_dir)
    wheel_dir.mkdir(parents=True, exist_ok=True)
    args = [
        sys.executable,
        "-m",
        "pip",
        "--disable-pip-version-check",
        "download",
        "--only-binary=:all:",
        "--no-deps",
        "--dest",
        str(wheel_dir),
        PIP_BOOTSTRAP_PACKAGE,
    ]
    run_command(args, "Downloading bundled pip bootstrap wheel")
    wheels = sorted(wheel_dir.glob("pip-*.whl"), key=lambda p: p.name.lower())
    if not wheels:
        raise RuntimeError(f"Bundled pip bootstrap wheel was not created in {wheel_dir}")
    log(f"Bundled pip bootstrap wheel: {wheels[-1].name}")

def _prepare_portable_worker_runtime(runtime_root: Path, worker_file: Path, requirements_file: Path, label: str) -> None:
    """Prepare one isolated portable Python runtime for a Local OCR worker.

    Paddle OCR and Manga OCR intentionally use separate external runtimes.
    This keeps the heavy dependency stacks replaceable and prevents one OCR
    engine's packages from bloating or destabilizing the other.
    """
    remove_path(runtime_root)
    runtime_root.mkdir(parents=True, exist_ok=True)

    require_file(worker_file, f"External {label} worker")
    shutil.copy2(worker_file, runtime_root / worker_file.name)

    portable_python_dir = runtime_root / "python"
    portable_python_dir.mkdir(parents=True, exist_ok=True)

    log("")
    log(f"Preparing portable {label} Python runtime...")
    start = time.perf_counter()
    embed_zip = _ensure_portable_python_zip()
    log(f"Portable Python ZIP: {embed_zip}")
    with zipfile.ZipFile(embed_zip, "r") as zf:
        zf.extractall(portable_python_dir)
    _configure_embeddable_python_path(portable_python_dir)

    site_packages = portable_python_dir / "Lib" / "site-packages"
    _install_worker_dependencies(requirements_file, site_packages, label)
    _prune_runtime_tree(site_packages)

    python_exe = portable_python_dir / "python.exe"
    require_file(python_exe, f"Portable {label} Python executable")
    elapsed = time.perf_counter() - start
    log(f"Portable {label} Python runtime prepared: {portable_python_dir}")
    log(f"Portable {label} Python runtime size: {format_bytes(folder_size(portable_python_dir))}")
    log(f"Portable {label} Python runtime prepare time: {elapsed:.1f}s")


def copy_local_ocr_runtime(local_stage: Path) -> None:
    """Copy external OCR workers and their isolated portable runtimes.

    The main Local EXE keeps comic_text_detector and LaMa frozen, but OCR
    engines with large/dynamic dependency stacks run outside PyInstaller.

    Final Local EXE layout:
    - local_runtime_exe/gpu_probe_worker.py
    - local_runtime_exe/paddle/paddle_ocr_worker.py
    - local_runtime_exe/paddle/python/python.exe
    - local_runtime_exe/manga_ocr/manga_ocr_worker.py
    - local_runtime_exe/manga_ocr/python/python.exe
    
    The legacy local_runtime folder is reserved for source/test runs.  Frozen
    Local packages keep all managed install/probe targets in local_runtime_exe.
    """
    runtime_stage = local_stage / "local_runtime_exe"
    remove_path(runtime_stage)
    runtime_stage.mkdir(parents=True, exist_ok=True)

    _prepare_pip_bootstrap_wheels(runtime_stage)

    if GPU_PROBE_WORKER_FILE.exists():
        shutil.copy2(GPU_PROBE_WORKER_FILE, runtime_stage / GPU_PROBE_WORKER_FILE.name)
    if LOCAL_LAMA_WORKER_FILE.exists():
        shutil.copy2(LOCAL_LAMA_WORKER_FILE, runtime_stage / LOCAL_LAMA_WORKER_FILE.name)

    _prepare_portable_worker_runtime(
        runtime_stage / "paddle",
        PADDLEOCR_WORKER_FILE,
        PADDLE_OCR_WORKER_REQUIREMENTS,
        "Paddle OCR worker",
    )
    _prepare_portable_worker_runtime(
        runtime_stage / "manga_ocr",
        MANGA_OCR_WORKER_FILE,
        MANGA_OCR_WORKER_REQUIREMENTS,
        "Manga OCR worker",
    )



def copy_optional_local_model_folder(src: Path, local_stage: Path, relative_dest: str, label: str) -> None:
    """Copy optional Local model folders to the package root.

    Keep large model caches outside the PyInstaller internal data bundle so they
    remain easy to replace/delete and can be excluded from lighter packages.
    """
    if not src.exists() or not src.is_dir():
        log(f"[WARN] {label} folder not found, skipped: {src}")
        return
    dst = local_stage / relative_dest
    remove_path(dst)
    dst.parent.mkdir(parents=True, exist_ok=True)
    log(f"Copying {label} folder: {src} -> {dst}")
    shutil.copytree(src, dst)
    log(f"{label} folder size: {format_bytes(folder_size(dst))}")




def copy_manga_ocr_model_cache_to_runtime(local_stage: Path) -> None:
    """Copy Manga OCR model cache into local_runtime_exe/manga_ocr/model_cache.

    The development/source tree keeps the downloaded model under
    local_models/manga_ocr, but the packaged Local build should not expose a
    separate local_models folder just for Manga OCR.  The runtime and its model
    travel together.
    """
    src = MANGA_OCR_MODELS_DIR
    runtime_root = local_stage / "local_runtime_exe" / "manga_ocr"
    dst = runtime_root / "model_cache"
    remove_path(dst)

    if not src.exists() or not src.is_dir():
        raise RuntimeError(
            "Manga OCR model cache not found. "
            f"Expected: {src}. "
            "Run setup_manga_ocr_v2_2_0.bat first, then build the Local package again."
        )

    dst.parent.mkdir(parents=True, exist_ok=True)
    log(f"Copying Manga OCR model cache into runtime: {src} -> {dst}")
    shutil.copytree(src, dst)
    log(f"Manga OCR runtime model cache size: {format_bytes(folder_size(dst))}")

def prepare_local_package() -> None:
    local_dir = DIST_DIR / LOCAL_NAME
    launcher_exe = DIST_DIR / f"{LAUNCHER_NAME}.exe"
    require_dir(local_dir, "Built Local folder")
    require_file(launcher_exe, "Built launcher EXE")

    local_stage = DIST_DIR / LOCAL_PACKAGE_FOLDER_NAME
    remove_path(local_stage)
    local_stage.mkdir(parents=True, exist_ok=True)

    for item in local_dir.iterdir():
        dst = local_stage / item.name
        if item.is_dir():
            shutil.copytree(item, dst)
        else:
            shutil.copy2(item, dst)
    shutil.copy2(launcher_exe, local_stage / launcher_exe.name)

    copy_local_ocr_runtime(local_stage)

    # Manga OCR is a default Local OCR engine. Keep its model cache inside the
    # Manga OCR runtime folder, just like an engine-private runtime asset:
    #   local_runtime_exe/manga_ocr/model_cache/huggingface/...
    # Do not create a separate local_models folder in the final package.
    # If the model cache is missing, fail the Local build instead of creating
    # a half-working package.
    copy_manga_ocr_model_cache_to_runtime(local_stage)

    cleanup_runtime_leftovers(local_stage)
    cleanup_dev_test_artifacts(local_stage)
    assert_no_dev_test_artifacts(local_stage)

    cleanup_intermediate_outputs()

    log("")
    log("Local package prepared:")
    log(f"Local package folder: {local_stage}")
    log(f"Local package size: {format_bytes(folder_size(local_stage))}")


def validate_layout(edition: str) -> None:
    require_file(LITE_ENTRY, "Lite entry")
    require_file(LOCAL_ENTRY, "Local entry")
    require_file(LAUNCHER_ENTRY, "Launcher entry")
    require_dir(YSB_PACKAGE_DIR, "ysb package directory")
    require_file(YSB_PACKAGE_DIR / "__init__.py", "ysb package __init__.py")
    require_file(YSB_PACKAGE_DIR / "editions" / "current.py", "edition selector")
    require_file(YSB_PACKAGE_DIR / "ui" / "main_window.py", "ysb.ui.main_window")
    require_file(YSB_PACKAGE_DIR / "core" / "ysb_launcher.py", "ysb.core.ysb_launcher")
    require_file(main_build_icon(), "Icon file")
    require_file(SPLASH_FILE, "Splash file")
    require_file(BOOT_SPLASH_FILE, "Boot splash file")
    require_file(VERSION_LAUNCHER, "Launcher version file")

    if edition == "lite":
        require_file(VERSION_LITE_MAIN, "Lite main version file")
    elif edition == "local":
        require_file(VERSION_LOCAL_MAIN, "Local main version file")
        require_file(YSB_PACKAGE_DIR / "engines" / "ocr" / "base.py", "OCR base")
        require_file(YSB_PACKAGE_DIR / "engines" / "ocr" / "paddle_ocr.py", "PaddleOCR adapter")
        require_file(PADDLEOCR_WORKER_FILE, "External PaddleOCR worker")
        require_file(MANGA_OCR_WORKER_FILE, "External Manga OCR worker")
        require_file(PADDLE_OCR_WORKER_REQUIREMENTS, "Paddle OCR worker requirements")
        require_file(MANGA_OCR_WORKER_REQUIREMENTS, "Manga OCR worker requirements")
        require_file(YSB_PACKAGE_DIR / "engines" / "text_detection" / "base.py", "text detection base")
        require_file(YSB_PACKAGE_DIR / "engines" / "text_detection" / "comic_text_detector.py", "comic_text_detector adapter")


def build_edition(edition: str) -> int:
    edition = edition.lower().strip()
    if edition not in VALID_EDITIONS:
        raise ValueError(f"Unknown edition: {edition!r}. Expected one of {sorted(VALID_EDITIONS)}")

    if LOG_FILE.exists():
        LOG_FILE.unlink()

    log(f"YSB Translator Tool {APP_VERSION} {edition.capitalize()} build driver")
    log(f"Project root: {PROJECT_ROOT}")
    log(f"Build tools:  {BUILD_TOOLS_DIR}")
    log(f"Build policy: single edition package folder only ({edition})")

    generate_version_files()
    validate_layout(edition)
    DIST_DIR.mkdir(exist_ok=True)
    clean_for_edition(edition)

    if edition == "lite":
        build_lite()
        build_launcher()
        prepare_lite_package()
    else:
        build_local()
        build_launcher()
        prepare_local_package()

    log("")
    log(f"{edition.capitalize()} build completed successfully.")
    return 0
