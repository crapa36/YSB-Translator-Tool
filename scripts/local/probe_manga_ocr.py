# -*- coding: utf-8 -*-
r"""Probe Manga OCR source/test environment for YSB Local.

Usage:
    .venv\Scripts\python.exe scripts\local\probe_manga_ocr.py
    .venv\Scripts\python.exe scripts\local\probe_manga_ocr.py path\to\crop.png
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def has_module(name: str) -> bool:
    return importlib.util.find_spec(name) is not None


def main() -> int:
    print("YSB Manga OCR probe")
    print("root:", ROOT)
    print("python:", sys.executable)
    print("frozen:", getattr(sys, "frozen", False))

    modules = ["torch", "PIL", "transformers", "fugashi", "unidic_lite"]
    missing = [m for m in modules if not has_module(m)]
    print("required modules:", "OK" if not missing else "MISSING " + ", ".join(missing))

    from ysb.engines.ocr import manga_ocr as mo
    print("app_root:", mo._app_root())
    print("selected_model_root:", mo.manga_ocr_model_root())
    print("model_exists:", mo.manga_ocr_model_exists())
    print("use_external_worker:", mo._should_use_external_worker())

    if missing:
        print("Install dependencies with setup_manga_ocr_v2_2_1.bat")
        return 2
    if not mo.manga_ocr_model_exists():
        print("Model cache not found under local_models/manga_ocr or runtime model_cache.")
        return 3

    if len(sys.argv) >= 2:
        image = Path(sys.argv[1])
        print("test_image:", image)
        from ysb.engines.ocr.base import OcrRequest
        from ysb.engines.ocr.manga_ocr import MangaOcrEngine
        res = MangaOcrEngine(language="ja").run(OcrRequest(image_path=str(image), language="ja", options={}))
        print("ok:", res.ok)
        print("error:", res.error)
        print("lines:", res.lines)
        return 0 if res.ok else 4

    print("Probe OK. Pass an image path to test actual recognition.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
