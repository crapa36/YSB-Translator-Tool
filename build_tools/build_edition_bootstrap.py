# -*- coding: utf-8 -*-
"""Safe bootstrap driver for YSB builds.

This script intentionally moves the fragile BAT logic into Python so a double-
clicked build file does not close before showing the real error.  The BAT only
finds Python and calls this file; this file creates/uses .venv, installs the
right requirements, and calls the edition-specific PyInstaller driver.
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

VALID_EDITIONS = {"lite", "local"}
SUPPORTED_PYTHON_MIN = (3, 10)
SUPPORTED_PYTHON_MAX = (3, 12)
RECOMMENDED_PYTHON = "3.11"

BUILD_TOOLS_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BUILD_TOOLS_DIR.parent
VENV_DIR = PROJECT_ROOT / ".venv"
PY_EXE = VENV_DIR / "Scripts" / "python.exe"
PIP_EXE = VENV_DIR / "Scripts" / "pip.exe"


def load_version_info():
    sys.path.insert(0, str(PROJECT_ROOT))
    try:
        from ysb.version_info import (
            APP_VERSION,
            BUILD_LOG_FILE_NAME,
            LITE_PACKAGE_FOLDER_NAME,
            LOCAL_PACKAGE_FOLDER_NAME,
        )
        return APP_VERSION, BUILD_LOG_FILE_NAME, LITE_PACKAGE_FOLDER_NAME, LOCAL_PACKAGE_FOLDER_NAME
    except Exception:
        return "current", "build_log_current.txt", "역식붕이 툴 Lite current_package", "역식붕이 툴 Local current_package"


APP_VERSION, BUILD_LOG_FILE_NAME, LITE_PACKAGE_FOLDER_NAME, LOCAL_PACKAGE_FOLDER_NAME = load_version_info()


def build_bootstrap_log_path(edition: str) -> Path:
    # APP_VERSION already includes the leading "v" (for example, "v2.1.0").
    return PROJECT_ROOT / f"build_bootstrap_{edition}_{APP_VERSION}.log"


class Logger:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.path.write_text(
                f"YSB build bootstrap log\n"
                f"Start: {datetime.now()}\n"
                f"Project root: {PROJECT_ROOT}\n"
                f"Build tools: {BUILD_TOOLS_DIR}\n\n",
                encoding="utf-8",
            )
        except Exception:
            pass

    def write(self, text: str = "") -> None:
        print(text, flush=True)
        try:
            with self.path.open("a", encoding="utf-8") as f:
                f.write(text + "\n")
        except Exception:
            pass


def run(cmd: list[str], logger: Logger, label: str) -> None:
    logger.write("")
    logger.write(f"=== {label} ===")
    logger.write(" ".join(f'"{x}"' if " " in x else x for x in cmd))

    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PIP_NO_PYTHON_VERSION_WARNING", "1")
    env.setdefault("PIP_NO_INPUT", "1")

    proc = subprocess.Popen(
        cmd,
        cwd=str(PROJECT_ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        env=env,
    )
    assert proc.stdout is not None
    for line in proc.stdout:
        logger.write(line.rstrip("\r\n"))
    ret = proc.wait()
    if ret != 0:
        raise RuntimeError(f"{label} failed with exit code {ret}")


def python_version_tuple(executable: Path | str) -> tuple[int, int] | None:
    try:
        out = subprocess.check_output(
            [str(executable), "-c", "import sys; print(f'{sys.version_info[0]}.{sys.version_info[1]}')"],
            cwd=str(PROJECT_ROOT),
            text=True,
            encoding="utf-8",
            errors="replace",
            stderr=subprocess.STDOUT,
        ).strip()
        major, minor = out.split(".", 1)
        return int(major), int(minor)
    except Exception:
        return None


def is_supported_python(ver: tuple[int, int] | None) -> bool:
    return ver is not None and SUPPORTED_PYTHON_MIN <= ver <= SUPPORTED_PYTHON_MAX


def version_text(ver: tuple[int, int] | None) -> str:
    return "unknown" if ver is None else f"{ver[0]}.{ver[1]}"


def ensure_supported_driver_python(logger: Logger) -> None:
    driver_ver = sys.version_info[:2]
    logger.write(f"Build driver Python: {sys.executable} ({driver_ver[0]}.{driver_ver[1]})")
    if not is_supported_python((driver_ver[0], driver_ver[1])):
        raise RuntimeError(
            "Unsupported build Python version. "
            f"Use Python {SUPPORTED_PYTHON_MIN[0]}.{SUPPORTED_PYTHON_MIN[1]}-"
            f"{SUPPORTED_PYTHON_MAX[0]}.{SUPPORTED_PYTHON_MAX[1]} "
            f"(recommended {RECOMMENDED_PYTHON}). "
            "Python 3.13/3.14 makes numpy==1.26.4 build from source and fails without Visual Studio C++ tools."
        )


def ensure_venv(logger: Logger) -> None:
    if PY_EXE.exists():
        venv_ver = python_version_tuple(PY_EXE)
        if is_supported_python(venv_ver):
            logger.write(f"[1/9] Shared virtual environment found. Python {version_text(venv_ver)}")
            return
        logger.write(
            f"[1/9] Existing .venv uses unsupported Python {version_text(venv_ver)}; recreating it."
        )
        try:
            shutil.rmtree(VENV_DIR)
        except Exception as exc:
            raise RuntimeError(f"Failed to remove old .venv: {exc}") from exc

    logger.write("[1/9] Creating shared virtual environment...")
    run([sys.executable, "-m", "venv", str(VENV_DIR)], logger, "Create .venv")
    venv_ver = python_version_tuple(PY_EXE)
    logger.write(f"Created .venv Python: {version_text(venv_ver)}")
    if not is_supported_python(venv_ver):
        raise RuntimeError(
            f"Created .venv uses unsupported Python {version_text(venv_ver)}. "
            f"Install Python {RECOMMENDED_PYTHON} and run the build BAT again."
        )


def install_requirements(edition: str, logger: Logger) -> None:
    steps: list[tuple[str, Path]] = [
        ("common requirements", PROJECT_ROOT / "requirements" / "common.txt"),
    ]
    if edition == "lite":
        steps.append(("Lite/API requirements", PROJECT_ROOT / "requirements" / "lite.txt"))
    else:
        # Local still needs Lite/API requirements because translation/cloud are API based.
        steps.append(("Lite/API requirements for API translation and cloud features", PROJECT_ROOT / "requirements" / "lite.txt"))
        steps.append(("Local requirements", PROJECT_ROOT / "requirements" / "local.txt"))
    steps.append(("build requirements", PROJECT_ROOT / "requirements" / "build.txt"))

    logger.write("[2/9] Upgrading pip...")
    # Keep pip below 26 for now. Some binary-heavy local packages changed resolver/log behavior in newer pip releases.
    run([str(PY_EXE), "-m", "pip", "--disable-pip-version-check", "install", "--upgrade", "pip<26", "--prefer-binary"], logger, "Upgrade pip")

    index = 3
    for label, req in steps:
        if not req.exists():
            if label == "build requirements":
                logger.write(f"[{index}/9] {label} file missing; installing PyInstaller directly...")
                run([str(PY_EXE), "-m", "pip", "--disable-pip-version-check", "install", "--upgrade", "--prefer-binary", "pyinstaller"], logger, "Install PyInstaller")
            else:
                logger.write(f"[{index}/9] {label} file missing, skipped: {req}")
            index += 1
            continue
        logger.write(f"[{index}/9] Installing {label}...")
        run([str(PY_EXE), "-m", "pip", "--disable-pip-version-check", "install", "--prefer-binary", "-r", str(req)], logger, f"Install {label}")
        index += 1


def main(argv: list[str]) -> int:
    edition = (argv[1] if len(argv) > 1 else "").lower().strip()
    if edition not in VALID_EDITIONS:
        print("Usage: python build_edition_bootstrap.py [lite|local]")
        return 2

    logger = Logger(build_bootstrap_log_path(edition))
    package_folder = LITE_PACKAGE_FOLDER_NAME if edition == "lite" else LOCAL_PACKAGE_FOLDER_NAME
    logger.write(f"YSB Tool {APP_VERSION} {edition.capitalize()} Build")
    logger.write(f"Target output folder: {PROJECT_ROOT / 'dist' / package_folder}")

    try:
        os.chdir(PROJECT_ROOT)
        ensure_supported_driver_python(logger)
        ensure_venv(logger)
        install_requirements(edition, logger)

        logger.write("[7/9] Build environment check...")
        run([str(PY_EXE), str(BUILD_TOOLS_DIR / "build_probe.py"), edition], logger, f"Probe {edition}")

        logger.write(f"[8/9] Building {edition.capitalize()} package only...")
        driver = BUILD_TOOLS_DIR / f"build_pyinstaller_{edition}.py"
        if not driver.exists():
            raise FileNotFoundError(f"Build driver not found: {driver}")
        run([str(PY_EXE), str(driver)], logger, f"Build {edition}")

        logger.write("")
        logger.write(f"[9/9] {edition.capitalize()} build completed.")
        logger.write("Output folder:")
        logger.write(f"  {PROJECT_ROOT / 'dist' / package_folder}")
        logger.write(f"Bootstrap log:")
        logger.write(f"  {logger.path}")
        logger.write(f"PyInstaller log:")
        logger.write(f"  {PROJECT_ROOT / BUILD_LOG_FILE_NAME}")
        return 0
    except Exception as exc:
        logger.write("")
        logger.write(f"ERROR: {exc}")
        logger.write("")
        logger.write("Build stopped. Check this log first:")
        logger.write(f"  {logger.path}")
        logger.write("If PyInstaller started, also check:")
        logger.write(f"  {PROJECT_ROOT / BUILD_LOG_FILE_NAME}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
