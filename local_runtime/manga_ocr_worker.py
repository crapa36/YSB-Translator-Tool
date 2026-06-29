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


def _ysb_prepend_managed_runtime_target() -> None:
    target = os.environ.get("YSB_MANAGED_RUNTIME_TARGET") or ""
    if not target:
        return
    try:
        if os.path.isdir(target) and target not in sys.path:
            sys.path.insert(0, target)
        if os.name == "nt":
            for sub in ("", "torch/lib", "nvidia/cublas/bin", "nvidia/cudnn/bin"):
                p = os.path.join(target, sub) if sub else target
                if os.path.isdir(p):
                    try:
                        os.add_dll_directory(p)
                    except Exception:
                        pass
    except Exception:
        pass


_ysb_prepend_managed_runtime_target()

_ENGINES: dict[str, object] = {}
MODEL_ID = "kha-white/manga-ocr-base"


def _normalize_device(value: str | None) -> str:
    v = str(value or "auto").strip().lower()
    if v in ("gpu", "cuda:0", "cuda"):
        return "cuda"
    if v in ("cpu", "mps"):
        return v
    return "auto"


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


def _cache_ready(root: Path) -> bool:
    try:
        model_dir = root / "huggingface" / "hub" / "models--kha-white--manga-ocr-base"
        if not model_dir.exists():
            return False
        snapshots = model_dir / "snapshots"
        if snapshots.exists() and any(snapshots.iterdir()):
            return True
        return any(model_dir.rglob("*.safetensors")) or any(model_dir.rglob("*.bin"))
    except Exception:
        return False


def _runtime_model_cache_root() -> Path | None:
    try:
        here = Path(__file__).resolve()
        if here.parent.name == "manga_ocr" and here.parent.parent.name == "local_runtime":
            return here.parent / "model_cache"
    except Exception:
        pass
    return None


def _candidate_model_roots() -> list[Path]:
    package_root = _package_root()
    roots: list[Path] = []

    env_root = os.environ.get("YSB_MANGA_OCR_MODEL_ROOT")
    if env_root:
        roots.append(Path(env_root).expanduser())

    runtime_root = _runtime_model_cache_root()
    if runtime_root is not None:
        roots.append(runtime_root)

    # Shared/user-manageable cache.  This lets Manga OCR keep working even when
    # local_runtime/manga_ocr/model_cache was deleted but local_models/manga_ocr
    # still contains the downloaded Hugging Face model.
    roots.append(package_root / "local_models" / "manga_ocr")

    unique: list[Path] = []
    seen: set[str] = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except Exception:
            key = str(root)
        if key in seen:
            continue
        seen.add(key)
        unique.append(root)
    return unique


def _select_model_root() -> Path:
    candidates = _candidate_model_roots()
    for root in candidates:
        if _cache_ready(root):
            return root

    # If no cache is ready yet, use local_models as the download/cache target
    # instead of forcing users to put models inside the runtime folder. Runtime
    # cache is still used above when it actually contains a ready model.
    return _package_root() / "local_models" / "manga_ocr"


def _configure_local_model_cache() -> Path:
    root = _select_model_root()
    hf_home = root / "huggingface"
    hub = hf_home / "hub"
    transformers = hf_home / "transformers"
    for d in (root, hf_home, hub, transformers):
        d.mkdir(parents=True, exist_ok=True)
    os.environ["YSB_MANGA_OCR_MODEL_ROOT"] = str(root)
    os.environ["HF_HOME"] = str(hf_home)
    os.environ["HF_HUB_CACHE"] = str(hub)
    os.environ["TRANSFORMERS_CACHE"] = str(transformers)
    return root


def _model_cache_ready() -> bool:
    try:
        return _cache_ready(_configure_local_model_cache())
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

    def __init__(self, device: str = "auto"):
        self.requested_device = _normalize_device(device)
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
        selected = self.requested_device
        if selected == "cuda":
            if not torch.cuda.is_available() or torch.cuda.device_count() <= 0:
                raise RuntimeError("Manga OCR CUDA를 사용할 수 없습니다. Torch CUDA 런타임/드라이버 상태를 확인해 주세요.")
            self.model.cuda()
        elif selected == "cpu":
            self.model.to("cpu")
        elif selected == "mps":
            if getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
                self.model.to("mps")
            else:
                self.model.to("cpu")
        elif torch.cuda.is_available() and torch.cuda.device_count() > 0:
            self.model.cuda()
        elif getattr(torch.backends, "mps", None) is not None and torch.backends.mps.is_available():
            self.model.to("mps")
        else:
            self.model.to("cpu")
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


def _get_engine(device: str = "auto"):
    key = _normalize_device(device)
    engine = _ENGINES.get(key)
    if engine is None:
        engine = _DirectMangaOcr(device=key)
        _ENGINES[key] = engine
    return engine


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
    device = _normalize_device(req.get("device") or os.environ.get("YSB_MANGA_OCR_DEVICE") or "auto")
    if not image_path:
        return {"ok": False, "engine": "manga_ocr_external", "error": "image_path is empty", "lines": []}
    try:
        text = str(_get_engine(device)(image_path) or "").strip()
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
    print(json.dumps({"ready": True, "engine": "manga_ocr_external", "device": _normalize_device(os.environ.get("YSB_MANGA_OCR_DEVICE") or "auto")}, ensure_ascii=False), flush=True)
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
