# -*- coding: utf-8 -*-
"""External Manga OCR worker for YSB Local edition.

Manga OCR is kept outside the PyInstaller EXE and runs in the portable
local_runtime/manga_ocr/python environment.  The worker uses JSON lines so the main
program can keep the same OCR interface without freezing transformers/tokenizers
into the main EXE.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import traceback
from pathlib import Path
from typing import Any

os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

_ENGINE = None
MODEL_ID = "kha-white/manga-ocr-base"


def _package_root() -> Path:
    # New layout: <package>/local_runtime/manga_ocr/manga_ocr_worker.py
    # Legacy layout: <package>/local_runtime/manga_ocr_worker.py
    try:
        here = Path(__file__).resolve()
        if here.parent.name == "manga_ocr" and here.parent.parent.name == "local_runtime":
            return here.parents[2]
        return here.parents[1]
    except Exception:
        return Path.cwd()


def _configure_local_model_cache() -> Path:
    package_root = _package_root()
    here = Path(__file__).resolve()

    # 배포판에서는 Manga OCR 런타임 폴더 안에 모델 캐시를 함께 둔다.
    #   local_runtime/manga_ocr/model_cache/huggingface
    # 소스 실행/구버전 구조에서는 기존 local_models/manga_ocr도 허용한다.
    runtime_root = None
    try:
        if here.parent.name == "manga_ocr" and here.parent.parent.name == "local_runtime":
            runtime_root = here.parent
    except Exception:
        runtime_root = None

    if runtime_root is not None:
        root = runtime_root / "model_cache"
    else:
        root = package_root / "local_models" / "manga_ocr"

    hf_home = root / "huggingface"
    hub = hf_home / "hub"
    transformers = hf_home / "transformers"
    for d in (root, hf_home, hub, transformers):
        d.mkdir(parents=True, exist_ok=True)
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HF_HUB_CACHE"] = str(hub)
    os.environ["TRANSFORMERS_CACHE"] = str(transformers)
    return root


def _model_cache_ready() -> bool:
    try:
        root = _configure_local_model_cache()
        model_dir = root / "huggingface" / "hub" / "models--kha-white--manga-ocr-base"
        if not model_dir.exists():
            return False
        snapshots = model_dir / "snapshots"
        if snapshots.exists() and any(snapshots.iterdir()):
            return True
        return any(model_dir.rglob("*.safetensors")) or any(model_dir.rglob("*.bin"))
    except Exception:
        return False


def _post_process(text: str) -> str:
    import re
    text = "".join(str(text or "").split())
    text = text.replace("…", "...")
    text = re.sub(r"['’`´]", "'", text)
    return text.strip()


class _DirectMangaOcr:
    """Small in-worker Manga OCR loader.

    This avoids older manga-ocr package builds that still call
    AutoFeatureExtractor and fail on the current manga-ocr-base
    preprocessor_config.
    """

    def __init__(self):
        _configure_local_model_cache()
        import torch
        from PIL import Image
        from transformers import AutoTokenizer, VisionEncoderDecoderModel, ViTImageProcessor
        try:
            from transformers.generation import GenerationMixin
        except Exception:
            GenerationMixin = object  # type: ignore

        class MangaOcrModel(VisionEncoderDecoderModel, GenerationMixin):  # type: ignore[misc, valid-type]
            pass

        self.torch = torch
        self.Image = Image
        local_only = _model_cache_ready()
        self.processor = ViTImageProcessor.from_pretrained(MODEL_ID, local_files_only=local_only)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_ID, local_files_only=local_only)
        self.model = MangaOcrModel.from_pretrained(MODEL_ID, local_files_only=local_only)
        if torch.cuda.is_available():
            self.model.cuda()
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            self.model.to("mps")
        self.model.eval()

    def __call__(self, img_or_path):
        if isinstance(img_or_path, (str, Path)):
            img = self.Image.open(img_or_path)
        else:
            img = img_or_path
        img = img.convert("L").convert("RGB")
        pixel_values = self.processor(img, return_tensors="pt").pixel_values
        with self.torch.no_grad():
            out = self.model.generate(pixel_values.to(self.model.device), max_length=300)[0].cpu()
        text = self.tokenizer.decode(out, skip_special_tokens=True)
        return _post_process(text)


def _get_engine():
    global _ENGINE
    if _ENGINE is None:
        _ENGINE = _DirectMangaOcr()
    return _ENGINE


def _image_size(image_path: str) -> tuple[int, int]:
    try:
        from PIL import Image
        with Image.open(image_path) as im:
            w, h = im.size
            return int(w), int(h)
    except Exception:
        return 1, 1


def run_once(req: dict[str, Any]) -> dict[str, Any]:
    image_path = str(req.get("image_path") or "")
    if not image_path:
        return {"ok": False, "engine": "manga_ocr_external", "error": "image_path is empty", "lines": []}
    try:
        text = str(_get_engine()(image_path) or "").strip()
        if not text:
            return {"ok": True, "engine": "manga_ocr_external", "lines": [], "raw": text}
        w, h = _image_size(image_path)
        return {
            "ok": True,
            "engine": "manga_ocr_external",
            "lines": [{
                "text": text,
                "confidence": 1.0,
                "points": [[0, 0], [w, 0], [w, h], [0, h]],
            }],
            "raw": text,
        }
    except Exception as e:
        return {
            "ok": False,
            "engine": "manga_ocr_external",
            "error": str(e),
            "traceback": traceback.format_exc(),
            "lines": [],
        }


def server_loop() -> int:
    _configure_local_model_cache()
    print(json.dumps({"ready": True, "engine": "manga_ocr_external"}, ensure_ascii=False), flush=True)
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except Exception as e:
            print(json.dumps({"ok": False, "error": f"invalid json: {e}", "lines": []}, ensure_ascii=False), flush=True)
            continue
        if req.get("cmd") == "shutdown":
            print(json.dumps({"ok": True, "shutdown": True}, ensure_ascii=False), flush=True)
            break
        print(json.dumps(run_once(req), ensure_ascii=False), flush=True)
    return 0


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("image", nargs="?")
    args = parser.parse_args()
    if args.server:
        return server_loop()
    if not args.image:
        print(json.dumps({"ok": False, "error": "image path required", "lines": []}, ensure_ascii=False))
        return 2
    print(json.dumps(run_once({"image_path": args.image}), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
