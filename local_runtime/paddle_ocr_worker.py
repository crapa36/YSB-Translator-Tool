# -*- coding: utf-8 -*-
"""External PaddleOCR worker for YSB Local edition.

This file is intentionally kept outside the PyInstaller EXE.  The Local EXE
starts this script with the bundled OCR virtual environment and exchanges JSON
lines with it.  Keeping PaddleOCR/PaddleX out of the frozen EXE avoids the
PyInstaller dependency-scanning instability around Paddle/PaddleX.
"""

from __future__ import annotations

import argparse
import ast
import json
import os
import re
import sys
import traceback
from pathlib import Path
from typing import Any

# Paddle/PaddleX CPU inference is more stable in YSB with oneDNN/MKLDNN off.
os.environ.setdefault("FLAGS_use_mkldnn", "0")
os.environ.setdefault("FLAGS_use_onednn", "0")
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# Import torch before importing paddle/paddlex/paddleocr to avoid WinError 127 DLL loading conflicts on Windows
try:
    import torch
except ImportError:
    pass


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

import numpy as np

_ENGINE_CACHE: dict[tuple[Any, ...], Any] = {}


def _worker_log_path() -> Path:
    try:
        local = os.environ.get("LOCALAPPDATA") or os.environ.get("APPDATA")
        if local:
            d = Path(local) / "YSBTranslator" / "logs"
            d.mkdir(parents=True, exist_ok=True)
            return d / "ysb_paddle_ocr_worker_child.log"
    except Exception:
        pass
    try:
        d = _package_root() / "logs"
        d.mkdir(parents=True, exist_ok=True)
        return d / "ysb_paddle_ocr_worker_child.log"
    except Exception:
        return Path("ysb_paddle_ocr_worker_child.log")


def _worker_log(message: str, **fields: Any) -> None:
    try:
        import datetime
        pairs = []
        for k, v in fields.items():
            text = str(v).replace("\n", "\\n").replace("\r", "\\r")
            if len(text) > 500:
                text = text[:497] + "..."
            pairs.append(f"{k}={text!r}" if " " in text else f"{k}={text}")
        tail = (" | " + " ".join(pairs)) if pairs else ""
        with _worker_log_path().open("a", encoding="utf-8", errors="replace") as f:
            f.write(f"[{datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S.%f')[:-3]}] {message}{tail}\n")
    except Exception:
        pass


def _normalize_lang(language: str) -> str:
    lang = str(language or "ja").strip().lower()
    aliases = {
        "ja": "japan", "jp": "japan", "jpn": "japan", "japanese": "japan", "일본어": "japan",
        "en": "en", "eng": "en", "english": "en", "영어": "en",
        "ko": "korean", "kr": "korean", "kor": "korean", "korean": "korean", "한국어": "korean",
        "zh": "ch", "cn": "ch", "ch": "ch", "chi": "ch", "zho": "ch", "chinese": "ch", "zh-cn": "ch", "중국어": "ch",
    }
    return aliases.get(lang, lang or "japan")


def _normalize_device(device: str) -> str:
    dev = str(device or "auto").strip().lower()
    if dev in ("cuda", "gpu", "gpu:0", "nvidia"):
        return "gpu"
    if dev in ("cpu",):
        return "cpu"
    
    # For "auto", check if CUDA is available
    try:
        import torch
        if torch.cuda.is_available():
            return "gpu"
    except Exception:
        pass
    try:
        import paddle
        if paddle.device.is_compiled_with_cuda() and paddle.device.cuda.device_count() > 0:
            return "gpu"
    except Exception:
        pass
    return "cpu"


def _canonical_resolved_device(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text.startswith("gpu") or text.startswith("cuda"):
        return "cuda"
    if text.startswith("cpu"):
        return "cpu"
    if text in ("error", "unavailable"):
        return text
    return "unknown"


def _probe_paddle_runtime_device(info: dict[str, Any], *, stage: str = "") -> dict[str, Any]:
    """Refresh Paddle's real selected device and store a user-readable report.

    Paddle/PaddleOCR can accept a CUDA request but later choose CPU internally.
    The parent process must not guess from success/failure alone, so every worker
    response carries this runtime probe result.
    """
    try:
        import paddle  # type: ignore
        try:
            current = str(paddle.device.get_device() or "")
        except Exception:
            current = ""
        actual = _canonical_resolved_device(current)
        info["paddle_current_device"] = current
        info["actual_device"] = actual
        info["device_probe_stage"] = stage
        info["worker_python"] = sys.executable
        try:
            info["cuda_compiled"] = bool(paddle.device.is_compiled_with_cuda())
        except Exception:
            pass
        try:
            info["cuda_device_count"] = int(paddle.device.cuda.device_count())
        except Exception:
            pass
        req = _normalize_device(str(info.get("requested_device") or "auto"))
        if req == "gpu":
            # Explicit CUDA is strict: only a real Paddle GPU/CUDA device is valid.
            info["resolved_device"] = "cuda" if actual == "cuda" else actual
        elif req == "cpu":
            info["resolved_device"] = "cpu"
        elif actual in ("cuda", "cpu"):
            info["resolved_device"] = actual
    except Exception as exc:
        info["device_probe_error"] = str(exc)
        info.setdefault("worker_python", sys.executable)
    return info


def _prepare_paddle_device(requested: str) -> dict[str, Any]:
    """Select Paddle device and enforce explicit CUDA strictly.

    PaddleOCR/PaddleX may otherwise print "Switching to CPU instead" and keep
    going.  In YSB, Device=CUDA means CUDA-only: if GPU cannot be selected, the
    worker must fail before OCR starts.
    """
    req = _normalize_device(requested)
    info: dict[str, Any] = {
        "requested_device": req,
        "resolved_device": "unknown",
        "cuda_compiled": False,
        "cuda_device_count": 0,
        "cuda_device_name": "",
        "fallback_reason": "",
        "actual_device": "unknown",
        "paddle_current_device": "",
        "device_probe_stage": "",
        "worker_python": sys.executable,
    }
    try:
        import paddle  # type: ignore
        try:
            info["cuda_compiled"] = bool(paddle.device.is_compiled_with_cuda())
        except Exception:
            info["cuda_compiled"] = False
        try:
            info["cuda_device_count"] = int(paddle.device.cuda.device_count())
        except Exception:
            info["cuda_device_count"] = 0
        if req == "gpu":
            if not info["cuda_compiled"] or int(info["cuda_device_count"] or 0) <= 0:
                raise RuntimeError(
                    "PaddleOCR CUDA requested but Paddle GPU is unavailable "
                    f"(cuda_compiled={info['cuda_compiled']}, device_count={info['cuda_device_count']}). "
                    "Install/repair the Paddle GPU runtime."
                )
            try:
                paddle.set_device("gpu:0")
            except Exception as exc:
                raise RuntimeError(f"PaddleOCR CUDA requested but paddle.set_device('gpu:0') failed: {exc}")
            info["resolved_device"] = "cuda"
            try:
                info["cuda_device_name"] = str(paddle.device.cuda.get_device_name(0) or "")
            except Exception:
                info["cuda_device_name"] = ""
            return _probe_paddle_runtime_device(info, stage="after_set_cuda")
        if req == "cpu":
            try:
                paddle.set_device("cpu")
            except Exception:
                pass
            info["resolved_device"] = "cpu"
            return _probe_paddle_runtime_device(info, stage="after_set_cpu")
        # Auto mode may fall back to CPU, but it must be explicit in the result.
        if info["cuda_compiled"] and int(info["cuda_device_count"] or 0) > 0:
            try:
                paddle.set_device("gpu:0")
                info["resolved_device"] = "cuda"
                try:
                    info["cuda_device_name"] = str(paddle.device.cuda.get_device_name(0) or "")
                except Exception:
                    pass
                return _probe_paddle_runtime_device(info, stage="after_auto_set_cuda")
            except Exception as exc:
                info["fallback_reason"] = f"auto_gpu_set_device_failed: {exc}"
        try:
            paddle.set_device("cpu")
        except Exception:
            pass
        info["resolved_device"] = "cpu"
        if not info.get("fallback_reason"):
            info["fallback_reason"] = "auto_cpu_fallback"
        return _probe_paddle_runtime_device(info, stage="after_auto_set_cpu")
    except Exception:
        if req == "gpu":
            raise
        info["resolved_device"] = "cpu"
        info["fallback_reason"] = "paddle_device_probe_failed_cpu_fallback"
        return info


def _package_root() -> Path:
    # Worker normally lives in <package>/local_runtime/paddle_ocr_worker.py
    try:
        return Path(__file__).resolve().parents[1]
    except Exception:
        return Path.cwd()


def _is_model_dir(path: Path) -> bool:
    try:
        if not path.exists() or not path.is_dir():
            return False
        markers = (
            "inference.yml", "inference.json", "model.pdmodel", "model.pdiparams",
            "inference.pdmodel", "inference.pdiparams",
        )
        if any((path / name).exists() for name in markers):
            return True
        for child in path.iterdir():
            if child.is_file() and child.suffix.lower() in (".pdmodel", ".pdiparams", ".json", ".yml", ".yaml"):
                return True
        return any(path.iterdir())
    except Exception:
        return False


def _local_model_roots() -> list[Path]:
    candidates: list[Path] = []
    env_root = os.environ.get("YSB_PADDLEOCR_MODEL_DIR") or os.environ.get("YSB_LOCAL_MODEL_DIR")
    if env_root:
        candidates.append(Path(env_root).expanduser())
    base = _package_root()
    candidates.append(base)
    candidates.append(Path.cwd())

    roots: list[Path] = []
    seen: set[str] = set()
    for item in candidates:
        # If the env var already points to local_models/paddleocr, accept it directly.
        for root in (item, item / "local_models" / "paddleocr", item / "local_models"):
            try:
                key = str(root.resolve()).lower()
            except Exception:
                key = str(root).lower()
            if key not in seen:
                seen.add(key)
                roots.append(root)

    cache_root = Path.home() / ".paddlex" / "official_models"
    try:
        key = str(cache_root.resolve()).lower()
    except Exception:
        key = str(cache_root).lower()
    if key not in seen:
        roots.append(cache_root)
    return roots


def _find_named_model(names: tuple[str, ...]) -> Path | None:
    for root in _local_model_roots():
        for name in names:
            for candidate in (root / name, root / f"{name}_infer"):
                if _is_model_dir(candidate):
                    return candidate
    return None


def _discover_paddle_model_dirs() -> dict[str, str]:
    textline = _find_named_model(("PP-LCNet_x1_0_textline_ori", "PP-LCNet_x1_0_doc_ori"))
    det = _find_named_model(("PP-OCRv5_server_det", "PP-OCRv5_mobile_det", "PP-OCRv4_server_det", "PP-OCRv4_mobile_det"))
    rec = _find_named_model(("PP-OCRv5_server_rec", "PP-OCRv5_mobile_rec", "japan_PP-OCRv3_mobile_rec", "PP-OCRv4_server_rec", "PP-OCRv4_mobile_rec"))
    dirs: dict[str, str] = {}
    if textline:
        dirs["textline_orientation_model_dir"] = str(textline)
        dirs["cls_model_dir"] = str(textline)
    if det:
        dirs["text_detection_model_dir"] = str(det)
        dirs["det_model_dir"] = str(det)
    if rec:
        dirs["text_recognition_model_dir"] = str(rec)
        dirs["rec_model_dir"] = str(rec)
    return dirs


def _as_points(value: Any) -> list[list[int]]:
    if value is None:
        return []
    if isinstance(value, str):
        s = value.strip()
        try:
            value = ast.literal_eval(s)
        except Exception:
            nums = [float(x) for x in re.findall(r"-?\d+(?:\.\d+)?", s)]
            if len(nums) >= 8:
                value = [[nums[i], nums[i + 1]] for i in range(0, min(len(nums), 8), 2)]
            elif len(nums) >= 4:
                x1, y1, x2, y2 = nums[:4]
                value = [[x1, y1], [x2, y1], [x2, y2], [x1, y2]]
            else:
                return []
    try:
        arr = np.asarray(value, dtype=np.float32)
        if arr.ndim == 1 and arr.size >= 4:
            x1, y1, x2, y2 = arr[:4].tolist()
            arr = np.array([[x1, y1], [x2, y1], [x2, y2], [x1, y2]], dtype=np.float32)
        elif arr.ndim >= 3:
            arr = arr.reshape((-1, 2))
        elif arr.ndim == 2 and arr.shape[1] >= 2:
            arr = arr[:, :2]
        else:
            return []
        pts: list[list[int]] = []
        for x, y in arr[:16]:
            pts.append([int(round(float(x))), int(round(float(y)))])
        return pts if len(pts) >= 3 else []
    except Exception:
        return []


def _result_obj_to_dict(obj: Any) -> dict[str, Any]:
    if isinstance(obj, dict):
        if isinstance(obj.get("res"), dict):
            return obj["res"]
        return obj
    if isinstance(obj, str):
        try:
            val = json.loads(obj)
            if isinstance(val, dict):
                if isinstance(val.get("res"), dict):
                    return val["res"]
                return val
        except Exception:
            return {}
    for attr in ("res", "data", "result"):
        try:
            val = getattr(obj, attr)
            if isinstance(val, dict):
                if isinstance(val.get("res"), dict):
                    return val["res"]
                return val
            if isinstance(val, str):
                parsed = _result_obj_to_dict(val)
                if parsed:
                    return parsed
        except Exception:
            pass
    for meth in ("to_dict", "json", "to_json"):
        try:
            fn = getattr(obj, meth)
            val = fn() if callable(fn) else fn
            if isinstance(val, dict):
                if isinstance(val.get("res"), dict):
                    return val["res"]
                return val
            if isinstance(val, str):
                parsed = _result_obj_to_dict(val)
                if parsed:
                    return parsed
        except Exception:
            pass
    return {}


def _first_present(data: dict[str, Any], *keys: str, default: Any = None) -> Any:
    for key in keys:
        if key in data:
            val = data.get(key)
            if val is not None:
                return val
    return default


def _safe_len(value: Any) -> int:
    try:
        return len(value) if value is not None else 0
    except Exception:
        return 0


def _safe_get_seq(value: Any, index: int, default: Any = None) -> Any:
    try:
        if value is None:
            return default
        if index < len(value):
            return value[index]
    except Exception:
        return default
    return default


def _app_root() -> Path:
    try:
        p = Path(__file__).resolve()
        if p.parent.name == "paddle":
            return p.parents[2]
        return p.parents[1]
    except Exception:
        return Path.cwd()


def _find_paddleocr_paths() -> tuple[str, str]:
    app_root = _app_root()
    candidates = [
        app_root / "local_models",
        Path.cwd() / "local_models"
    ]
    local_models_dir = None
    for c in candidates:
        if c.exists() and c.is_dir():
            local_models_dir = c
            break
    if local_models_dir is None:
        local_models_dir = Path("local_models")

    paddle_dir = None
    if local_models_dir.exists():
        for item in local_models_dir.iterdir():
            if item.is_dir() and item.name.lower() == "paddleocr-vl":
                paddle_dir = item
                break

    if paddle_dir is None:
        paddle_dir = local_models_dir / "PaddleOCR-VL"

    layout_dir = None
    if paddle_dir.exists():
        doc_layout = paddle_dir / "PP-DocLayoutV2"
        if doc_layout.exists() and doc_layout.is_dir():
            layout_dir = doc_layout
        else:
            for item in paddle_dir.iterdir():
                if item.is_dir():
                    if item.name.lower() == "layout":
                        layout_dir = item
                        break
                    try:
                        if any(f.suffix == ".pdmodel" for f in item.iterdir() if f.is_file()):
                            layout_dir = item
                            break
                    except Exception:
                        pass

    if layout_dir is None:
        layout_dir = paddle_dir / "PP-DocLayoutV2"

    return str(layout_dir.resolve()), str(paddle_dir.resolve())


def _build_engine(language: str, device: str):
    lang = _normalize_lang(language)
    dev = _normalize_device(device)
    device_info = _prepare_paddle_device(dev)
    resolved = _canonical_resolved_device(device_info.get("resolved_device") or device_info.get("actual_device") or "cpu")
    device_arg = "gpu" if resolved == "cuda" else "cpu"
    use_gpu = resolved == "cuda"
    model_dirs_all = _discover_paddle_model_dirs()
    cache_key = (
        lang,
        device_arg,
        model_dirs_all.get("text_detection_model_dir", ""),
        model_dirs_all.get("text_recognition_model_dir", ""),
        model_dirs_all.get("textline_orientation_model_dir", ""),
    )
    if cache_key in _ENGINE_CACHE:
        device_info = _probe_paddle_runtime_device(device_info, stage="cache_hit")
        if dev == "gpu" and _canonical_resolved_device(device_info.get("resolved_device") or device_info.get("actual_device")) != "cuda":
            raise RuntimeError(
                "PaddleOCR CUDA requested but cached engine is not on a CUDA device "
                f"(current={device_info.get('paddle_current_device') or 'unknown'})."
            )
        return _ENGINE_CACHE[cache_key], device_info

    from paddleocr import PaddleOCR

    attempts: list[dict[str, Any]] = [
        {"lang": lang, "use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": True, "device": device_arg, "enable_mkldnn": False, "cpu_threads": 1, **model_dirs_v3},
        {"lang": lang, "use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": True, "device": device_arg, "enable_mkldnn": False, "cpu_threads": 1, **{k: v for k, v in model_dirs_v3.items() if k != "textline_orientation_model_dir"}},
        {"lang": lang, "use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": False, "device": device_arg, "enable_mkldnn": False, "cpu_threads": 1, **{k: v for k, v in model_dirs_v3.items() if k != "textline_orientation_model_dir"}},
        {"lang": lang, "use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": True, "device": device_arg, "enable_mkldnn": False, "cpu_threads": 1},
        {"lang": lang, "use_doc_orientation_classify": False, "use_doc_unwarping": False, "use_textline_orientation": False, "device": device_arg, "enable_mkldnn": False, "cpu_threads": 1},
        {"lang": lang, "use_angle_cls": True, "use_gpu": use_gpu, "show_log": False, "enable_mkldnn": False, **model_dirs_v2},
        {"lang": lang, "use_angle_cls": True, "use_gpu": use_gpu, "show_log": False, "enable_mkldnn": False},
        {"lang": lang},
    ]
    if use_gpu:
        # If CUDA was selected/resolved, every PaddleOCR constructor attempt must
        # explicitly request GPU.  A generic final fallback can silently create a
        # CPU engine and make CUDA testing meaningless.
        attempts = [
            kw for kw in attempts
            if str(kw.get("device", "")).lower().startswith("gpu") or bool(kw.get("use_gpu")) is True
        ]
    last_err: Exception | None = None
    for kwargs in attempts:
        try:
            engine = PaddleOCR(**kwargs)
            device_info = _probe_paddle_runtime_device(device_info, stage="after_engine_init")
            if dev == "gpu" and _canonical_resolved_device(device_info.get("resolved_device") or device_info.get("actual_device")) != "cuda":
                raise RuntimeError(
                    "PaddleOCR CUDA requested but engine initialized on a non-CUDA device "
                    f"(current={device_info.get('paddle_current_device') or 'unknown'})."
                )
            _ENGINE_CACHE[cache_key] = engine
            return engine, device_info
        except TypeError as e:
            last_err = e
            continue
        except Exception as e:
            last_err = e
            continue
    raise RuntimeError(f"PaddleOCR initialization failed: {last_err}")


def _parse_old_ocr_result(result: Any) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    if result is None:
        return lines
    pages = result if isinstance(result, list) else [result]
    candidate = pages[0] if len(pages) == 1 and isinstance(pages[0], list) else pages
    if candidate and isinstance(candidate[0], list) and candidate[0] and isinstance(candidate[0][0], (list, tuple, np.ndarray)) and len(candidate[0]) != 2:
        flat = []
        for page in candidate:
            if isinstance(page, list):
                flat.extend(page)
        candidate = flat
    for row in candidate or []:
        try:
            if not isinstance(row, (list, tuple)) or len(row) < 2:
                continue
            pts = _as_points(row[0])
            rec = row[1]
            text = ""
            score = 0.0
            if isinstance(rec, (list, tuple)) and rec:
                text = str(rec[0] or "").strip()
                if len(rec) > 1:
                    score = float(rec[1] or 0.0)
            else:
                text = str(rec or "").strip()
            if text and pts:
                lines.append({"text": text, "confidence": score, "points": pts})
        except Exception:
            continue
    return lines


def _parse_predict_result(result: Any) -> list[dict[str, Any]]:
    lines: list[dict[str, Any]] = []
    for obj in (result if isinstance(result, list) else [result]):
        data = _result_obj_to_dict(obj)
        if not data:
            continue
        
        # VLM 파싱 결과 지원
        parsing_res_list = data.get("parsing_res_list")
        if isinstance(parsing_res_list, list):
            for block in parsing_res_list:
                if block is None:
                    continue
                if not isinstance(block, dict):
                    text = str(getattr(block, "content", "") or "").strip()
                    if not text:
                        text = str(getattr(block, "block_content", "") or "").strip()
                    if not text:
                        continue
                    score = float(getattr(block, "confidence", 1.0) or 1.0)
                    bbox = getattr(block, "bbox", None)
                    if bbox is None:
                        bbox = getattr(block, "block_bbox", None)
                else:
                    text = str(block.get("block_content") or block.get("content") or "").strip()
                    if not text:
                        continue
                    score = float(block.get("confidence", 1.0) or 1.0)
                    bbox = block.get("block_bbox") or block.get("bbox")
                
                pts = _as_points(bbox)
                if text and pts:
                    lines.append({"text": text, "confidence": score, "points": pts})
            continue

        texts = _first_present(data, "rec_texts", "texts", default=[])
        scores = _first_present(data, "rec_scores", "scores", default=[])
        polys = _first_present(data, "rec_polys", "dt_polys", "polys", default=[])
        boxes = _first_present(data, "rec_boxes", "boxes", default=[])
        max_len = max(_safe_len(texts), _safe_len(polys), _safe_len(boxes))
        for i in range(max_len):
            try:
                text = str(_safe_get_seq(texts, i, "") or "").strip()
                if not text:
                    continue
                score_raw = _safe_get_seq(scores, i, 0.0)
                try:
                    score = float(score_raw if score_raw is not None else 0.0)
                except Exception:
                    score = 0.0
                pts = _as_points(_safe_get_seq(polys, i, None))
                if not pts:
                    pts = _as_points(_safe_get_seq(boxes, i, None))
                if pts:
                    lines.append({"text": text, "confidence": score, "points": pts})
            except Exception:
                continue
    return lines


def run_ocr_request(req: dict[str, Any]) -> dict[str, Any]:
    try:
        image_path = str(req.get("image_path") or "")
        try:
            stat_size = Path(image_path).stat().st_size if image_path else 0
        except Exception:
            stat_size = 0
        _worker_log("CHILD OCR REQUEST", image_path=image_path, file_size=stat_size, language=req.get("language"), device=req.get("device"))
        if not image_path:
            return {"ok": False, "engine": "paddleocr_external", "error": "image_path is empty", "lines": []}
        language = str(req.get("language") or "ja")
        device = str(req.get("device") or "auto")
        use_layout_detection = bool(req.get("use_layout_detection", True))
        engine, device_info = _build_engine(language, device)
        lines: list[dict[str, Any]] = []
        if hasattr(engine, "predict"):
            try:
                result = engine.predict(input=image_path, use_layout_detection=use_layout_detection)
            except TypeError:
                result = engine.predict(image_path, use_layout_detection=use_layout_detection)
            lines = _parse_predict_result(result)
        if not lines and hasattr(engine, "ocr"):
            try:
                result = engine.ocr(image_path, cls=True)
            except TypeError:
                result = engine.ocr(image_path)
            lines = _parse_old_ocr_result(result)
        device_info = _probe_paddle_runtime_device(device_info, stage="after_ocr")
        if _normalize_device(device) == "gpu" and _canonical_resolved_device(device_info.get("resolved_device") or device_info.get("actual_device")) != "cuda":
            raise RuntimeError(
                "PaddleOCR CUDA requested but OCR finished on a non-CUDA device "
                f"(current={device_info.get('paddle_current_device') or 'unknown'})."
            )
        _worker_log(
            "CHILD OCR DONE",
            image_path=image_path,
            line_count=len(lines),
            requested_device=device_info.get("requested_device"),
            resolved_device=device_info.get("resolved_device"),
            actual_device=device_info.get("actual_device"),
            paddle_current_device=device_info.get("paddle_current_device"),
            cuda_count=device_info.get("cuda_device_count"),
            fallback_reason=device_info.get("fallback_reason"),
        )
        return {"ok": True, "engine": "paddleocr_external", "lines": lines, "error": "", "device_info": device_info}
    except Exception as e:
        _worker_log("CHILD OCR EXCEPTION", error=repr(e), traceback=traceback.format_exc())
        return {
            "ok": False,
            "engine": "paddleocr_external",
            "lines": [],
            "error": str(e),
            "traceback": traceback.format_exc(),
            "device_info": {"requested_device": _normalize_device(str(req.get("device") or "auto")), "resolved_device": "error", "worker_python": sys.executable},
        }


def serve() -> int:
    _worker_log("CHILD SERVER START", executable=sys.executable, cwd=os.getcwd())
    # Keep protocol stdout clean.  Redirect ordinary prints/Paddle logs to stderr.
    protocol_out = sys.stdout
    sys.stdout = sys.stderr
    protocol_out.write(json.dumps({"ready": True}, ensure_ascii=False) + "\n")
    protocol_out.flush()
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
            if req.get("cmd") == "shutdown":
                _worker_log("CHILD SERVER SHUTDOWN")
                protocol_out.write(json.dumps({"ok": True, "bye": True}, ensure_ascii=False) + "\n")
                protocol_out.flush()
                return 0
            res = run_ocr_request(req)
        except Exception as e:
            res = {"ok": False, "engine": "paddleocr_external", "lines": [], "error": str(e), "traceback": traceback.format_exc()}
        protocol_out.write(json.dumps(res, ensure_ascii=False) + "\n")
        protocol_out.flush()
    _worker_log("CHILD SERVER STDIN CLOSED")
    return 0


def run_once(input_json: str, output_json: str) -> int:
    with open(input_json, "r", encoding="utf-8") as f:
        req = json.load(f)
    res = run_ocr_request(req)
    with open(output_json, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False)
    return 0 if res.get("ok") else 1


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--server", action="store_true")
    parser.add_argument("--input-json")
    parser.add_argument("--output-json")
    args = parser.parse_args()
    if args.server:
        return serve()
    if args.input_json and args.output_json:
        return run_once(args.input_json, args.output_json)
    print("Use --server or --input-json/--output-json", file=sys.stderr)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
