# -*- coding: utf-8 -*-
from __future__ import annotations

import importlib
import importlib.util
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def check_module_spec(name: str, label: str | None = None) -> None:
    label = label or name
    spec = importlib.util.find_spec(name)
    if spec is None:
        raise ModuleNotFoundError(f"No module named '{name}'")
    origin = spec.origin or "(namespace/package)"
    print(f"{label} FOUND: {origin}")


def check_import(name: str, label: str | None = None) -> None:
    label = label or name
    mod = importlib.import_module(name)
    path = getattr(mod, "__file__", "")
    print(f"{label} OK" + (f": {path}" if path else ""))


def normalize_edition(argv: list[str]) -> str:
    edition = argv[1].lower().strip() if len(argv) >= 2 else "local"
    if edition not in {"lite", "local"}:
        raise ValueError("Usage: build_probe.py [lite|local]")
    return edition


def main() -> int:
    edition = normalize_edition(sys.argv)
    print(f"Project root: {PROJECT_ROOT}")
    print(f"Python: {sys.version}")
    print(f"Build probe edition: {edition}")

    # Do not import the actual UI modules here.
    check_module_spec("ysb", "Local package ysb")
    check_module_spec("ysb.ui.main_window", "Local module ysb.ui.main_window")
    check_module_spec("ysb.core.ysb_launcher", "Local module ysb.core.ysb_launcher")

    # Common external checks.
    for name in [
        "PyQt6.QtCore",
        "PyQt6.QtGui",
        "PyQt6.QtWidgets",
        "cv2",
        "numpy",
        "requests",
        "PIL._imaging",
    ]:
        check_import(name)

    # API/Lite checks. Local also uses API translation and API fallback paths.
    for name in [
        "openai",
        "replicate",
        "google.oauth2.credentials",
        "google_auth_oauthlib.flow",
        "googleapiclient.discovery",
    ]:
        check_module_spec(name, f"API dependency {name}")

    if edition == "local":
        # Local detector dependencies are intentionally checked by spec only.
        # Importing torch here would slow every build probe.
        for name in ["torch", "torchvision", "pyclipper", "shapely", "tqdm", "yaml"]:
            check_module_spec(name, f"Local detector dependency {name}")

        for name in ["paddle", "paddleocr", "pandas", "simple_lama_inpainting"]:
            check_module_spec(name, f"Local model dependency {name}")

        vendor = PROJECT_ROOT / "third_party" / "comic_text_detector"
        model = vendor / "comic_text_detector.pt"
        if not vendor.exists():
            raise FileNotFoundError(f"comic_text_detector vendor folder not found: {vendor}")
        if not model.exists():
            raise FileNotFoundError(f"comic_text_detector model not found: {model}")
        print(f"comic_text_detector vendor OK: {vendor}")

    print("Build environment check OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
