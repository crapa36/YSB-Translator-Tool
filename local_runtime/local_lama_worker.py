# -*- coding: utf-8 -*-
"""External Local LaMa worker for managed Torch CUDA runtimes."""

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


def _normalize_device_request(device: str) -> str:
    req = str(device or "auto").strip().lower() or "auto"
    if req in ("gpu", "nvidia", "cuda:0"):
        return "cuda"
    if req == "cpu":
        return "cpu"
    if req == "cuda":
        return "cuda"
    return "auto"


def _install_torch_load_map_location(resolved_device: str):
    """Patch torch model loaders so CUDA-saved LaMa weights obey the requested device.

    simple-lama-inpainting may call torch.load, torch.serialization.load, or
    torch.jit.load internally.  Some CUDA-saved checkpoints crash in CPU mode
    unless map_location is forced all the way down to the internal loader.
    Because this worker is a short-lived isolated process, patching and restoring
    these loader functions around SimpleLama construction is safer than letting
    the library silently pick its own device.
    """
    try:
        import torch  # type: ignore
    except Exception:
        return None

    resolved = str(resolved_device or "cpu").strip().lower()
    if resolved.startswith("cuda"):
        map_location = "cuda:0"
        force_override = False
    else:
        map_location = "cpu"
        # CPU mode must override even an explicit CUDA map_location supplied by
        # the third-party loader; otherwise CUDA-serialized checkpoints still
        # try to deserialize onto cuda:0 while CUDA_VISIBLE_DEVICES is hidden.
        force_override = True

    originals: list[tuple[Any, str, Any]] = []

    def _apply_map_location(args, kwargs):
        args = list(args)
        if force_override:
            if len(args) >= 2:
                args[1] = map_location
            else:
                kwargs["map_location"] = map_location
        else:
            if len(args) < 2 and kwargs.get("map_location") is None:
                kwargs["map_location"] = map_location
        return tuple(args), kwargs

    def _wrap_loader(original):
        def _ysb_loader_with_map_location(*args, **kwargs):
            mapped_args, mapped_kwargs = _apply_map_location(args, dict(kwargs))
            return original(*mapped_args, **mapped_kwargs)
        try:
            _ysb_loader_with_map_location.__name__ = getattr(original, "__name__", "ysb_loader_with_map_location")
        except Exception:
            pass
        return _ysb_loader_with_map_location

    def _patch(obj, attr: str):
        try:
            original = getattr(obj, attr, None)
            if callable(original):
                setattr(obj, attr, _wrap_loader(original))
                originals.append((obj, attr, original))
        except Exception:
            pass

    _patch(torch, "load")
    try:
        serialization = getattr(torch, "serialization", None)
        if serialization is not None:
            _patch(serialization, "load")
    except Exception:
        pass
    try:
        jit = getattr(torch, "jit", None)
        if jit is not None:
            _patch(jit, "load")
    except Exception:
        pass

    return originals or None


def _restore_torch_load(original_loads):
    if not original_loads:
        return
    for obj, attr, original in list(original_loads):
        try:
            setattr(obj, attr, original)
        except Exception:
            pass


def _torch_device_info(requested_device: str) -> dict[str, Any]:
    """Return a compact, user-visible device report for the external LaMa worker."""
    info: dict[str, Any] = {
        "requested_device": requested_device or "auto",
        "resolved_device": "unknown",
        "torch_available": False,
        "cuda_available": False,
        "cuda_device_count": 0,
        "cuda_device_name": "",
        "torch_version": "",
        "torch_cuda_build": "",
        "reason": "",
    }
    try:
        import torch  # type: ignore
        info["torch_available"] = True
        info["torch_version"] = str(getattr(torch, "__version__", "") or "")
        info["torch_cuda_build"] = str(getattr(getattr(torch, "version", None), "cuda", "") or "")
        try:
            info["cuda_available"] = bool(torch.cuda.is_available())
        except Exception:
            info["cuda_available"] = False
        try:
            info["cuda_device_count"] = int(torch.cuda.device_count() or 0)
        except Exception:
            info["cuda_device_count"] = 0
        if info["cuda_available"] and info["cuda_device_count"] > 0:
            try:
                info["cuda_device_name"] = str(torch.cuda.get_device_name(0) or "")
            except Exception:
                info["cuda_device_name"] = ""
        req = str(requested_device or "auto").strip().lower() or "auto"
        if req in ("gpu", "nvidia", "cuda:0"):
            req = "cuda"
        elif req != "cpu" and req != "cuda":
            req = "auto"
        info["requested_device"] = req
        if req == "cpu":
            info["resolved_device"] = "cpu"
            info["reason"] = "forced_cpu"
        elif req == "cuda":
            if info["cuda_available"] and info["cuda_device_count"] > 0:
                info["resolved_device"] = "cuda"
                info["reason"] = "forced_cuda_available"
            else:
                info["resolved_device"] = "unavailable"
                info["reason"] = "forced_cuda_unavailable"
        else:
            if info["cuda_available"] and info["cuda_device_count"] > 0:
                info["resolved_device"] = "cuda"
                info["reason"] = "auto_cuda_available"
            else:
                info["resolved_device"] = "cpu"
                info["reason"] = "auto_cpu_fallback"
    except Exception as exc:
        info["resolved_device"] = "unknown"
        info["reason"] = f"torch_import_failed: {type(exc).__name__}: {exc}"
    return info


def _iter_model_candidates(model: Any):
    """Yield likely torch modules inside SimpleLama without assuming one package layout."""
    seen: set[int] = set()

    def _yield(obj):
        if obj is None:
            return
        try:
            oid = id(obj)
            if oid in seen:
                return
            seen.add(oid)
        except Exception:
            pass
        yield obj

    for obj in _yield(model):
        yield obj
    for name in ("model", "net", "lama", "module", "inpaint_model", "generator", "network"):
        try:
            obj = getattr(model, name, None)
            for candidate in _yield(obj):
                yield candidate
        except Exception:
            pass


def _force_model_to_device(model: Any, device: str) -> None:
    """Best-effort move of SimpleLama internals to the requested device.

    simple-lama-inpainting keeps its own wrapper object, and some versions expose
    only a wrapper-level ``device`` field while the actual torch module is nested.
    CPU mode must not be rejected only because that wrapper-level field still says
    cuda after a CUDA-serialized checkpoint was loaded with map_location=cpu.
    """
    dev = str(device or "cpu").strip().lower() or "cpu"
    try:
        import torch  # type: ignore
        torch_dev = torch.device("cuda:0" if dev.startswith("cuda") else "cpu")
    except Exception:
        torch_dev = "cuda:0" if dev.startswith("cuda") else "cpu"

    for obj in list(_iter_model_candidates(model)):
        try:
            to_fn = getattr(obj, "to", None)
            if callable(to_fn):
                to_fn(torch_dev)
        except Exception:
            pass
        # Keep wrapper metadata consistent when the attribute is writable.
        try:
            if hasattr(obj, "device"):
                setattr(obj, "device", torch_dev)
        except Exception:
            try:
                if hasattr(obj, "device"):
                    setattr(obj, "device", str(torch_dev))
            except Exception:
                pass


def _actual_parameter_device_text(model: Any) -> str:
    """Return the device of real tensors only; ignore wrapper metadata."""
    for obj in list(_iter_model_candidates(model)):
        try:
            params = getattr(obj, "parameters", None)
            if callable(params):
                for param in params():
                    try:
                        return str(param.device)
                    except Exception:
                        pass
        except Exception:
            pass
        try:
            buffers = getattr(obj, "buffers", None)
            if callable(buffers):
                for buf in buffers():
                    try:
                        return str(buf.device)
                    except Exception:
                        pass
        except Exception:
            pass
    return "unknown"


def _model_device_text(model: Any, resolved_device: str = "") -> str:
    """Best-effort inspection of the device actually held by SimpleLama internals."""
    actual = _actual_parameter_device_text(model)
    if actual and actual.lower() != "unknown":
        return actual

    resolved = str(resolved_device or "").strip().lower()
    # In CPU mode, no real tensor device was found.  Treat stale wrapper metadata
    # such as ``device='cuda'`` as non-authoritative; the output image is the real
    # success criterion.
    if resolved == "cpu":
        return "cpu"

    try:
        for obj in list(_iter_model_candidates(model)):
            try:
                dev = getattr(obj, "device", None)
                if dev is not None:
                    return str(dev)
            except Exception:
                pass
    except Exception:
        pass
    return "unknown"


def _run(req: dict[str, Any]) -> dict[str, Any]:
    device_info: dict[str, Any] = {}
    model_device = "unknown"
    try:
        image_path = str(req.get("image_path") or "")
        mask_path = str(req.get("mask_path") or "")
        output_path = str(req.get("output_path") or "")
        model_path = str(req.get("model_path") or "")
        device = _normalize_device_request(str(req.get("device") or "auto"))
        if device == "cpu":
            os.environ["CUDA_VISIBLE_DEVICES"] = ""
        if model_path:
            os.environ["LAMA_MODEL"] = model_path
        if not image_path or not Path(image_path).exists():
            raise RuntimeError(f"input image not found: {image_path}")
        if not mask_path or not Path(mask_path).exists():
            raise RuntimeError(f"mask image not found: {mask_path}")
        if not output_path:
            raise RuntimeError("output_path is empty")

        import numpy as np
        from PIL import Image
        device_info = _torch_device_info(device)
        resolved_device = str(device_info.get("resolved_device") or "unknown").strip().lower()
        if device == "cuda" and resolved_device != "cuda":
            raise RuntimeError(
                "LOCAL LaMa CUDA를 요청했지만 worker에서 CUDA 장치를 사용할 수 없습니다. "
                f"cuda_available={device_info.get('cuda_available')}, "
                f"device_count={device_info.get('cuda_device_count')}, "
                f"worker_python={sys.executable}"
            )
        if resolved_device not in ("cuda", "cpu"):
            resolved_device = "cpu"

        original_torch_load = _install_torch_load_map_location(resolved_device)
        try:
            from simple_lama_inpainting import SimpleLama
        except Exception:
            _restore_torch_load(original_torch_load)
            raise

        image = Image.open(image_path).convert("RGB")
        mask = Image.open(mask_path).convert("L")
        if mask.size != image.size:
            mask = mask.resize(image.size, Image.Resampling.NEAREST)
        arr = np.asarray(mask)
        arr = np.where(arr > 10, 255, 0).astype("uint8")
        if int(np.count_nonzero(arr)) <= 0:
            raise RuntimeError("LaMa mask is empty")
        mask = Image.fromarray(arr, mode="L")

        try:
            model = SimpleLama()
        except Exception as exc:
            _restore_torch_load(original_torch_load)
            if "Attempting to deserialize object on CUDA device" in str(exc):
                raise RuntimeError(
                    "LOCAL LaMa 모델 로딩 실패: CUDA 저장 모델을 현재 worker 장치로 매핑하지 못했습니다. "
                    f"requested={device}, resolved={resolved_device}, worker_python={sys.executable}. "
                    f"원문 오류: {exc}"
                ) from exc
            raise
        finally:
            _restore_torch_load(original_torch_load)
        _force_model_to_device(model, resolved_device)
        model_device = _model_device_text(model, resolved_device)
        if device == "cuda" and not str(model_device or "").lower().startswith("cuda"):
            raise RuntimeError(
                "LOCAL LaMa CUDA requested but SimpleLaMa model is not on CUDA "
                f"(model_device={model_device or 'unknown'})."
            )
        if device == "cpu" and str(model_device or "").lower() == "unknown":
            model_device = "cpu"
        result = model(image, mask)
        if isinstance(result, Image.Image):
            out_img = result.convert("RGB")
        else:
            out_arr = np.asarray(result)
            if out_arr.ndim == 3 and out_arr.shape[0] in (3, 4) and out_arr.shape[-1] not in (3, 4):
                out_arr = np.transpose(out_arr, (1, 2, 0))
            if out_arr.dtype != np.uint8:
                if out_arr.size and out_arr.max() <= 1.5:
                    out_arr = out_arr * 255.0
                out_arr = np.clip(out_arr, 0, 255).astype("uint8")
            out_img = Image.fromarray(out_arr).convert("RGB")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        out_img.save(output_path, format="PNG")
        return {
            "ok": True,
            "output_path": output_path,
            "error": "",
            "device_info": device_info,
            "model_device": model_device,
        }
    except Exception as exc:
        return {
            "ok": False,
            "output_path": "",
            "error": f"{type(exc).__name__}: {exc}",
            "traceback": traceback.format_exc(),
            "device_info": device_info,
            "model_device": model_device,
        }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-json", required=True)
    parser.add_argument("--output-json", required=True)
    args = parser.parse_args()
    with open(args.input_json, "r", encoding="utf-8") as f:
        req = json.load(f)
    res = _run(req)
    with open(args.output_json, "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    return 0 if res.get("ok") else 1


if __name__ == "__main__":
    raise SystemExit(main())
