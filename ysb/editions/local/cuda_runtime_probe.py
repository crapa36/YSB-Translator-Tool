# -*- coding: utf-8 -*-
"""Local CUDA/runtime diagnosis helpers for YSB Translator.

This module does not require PyTorch, PaddlePaddle, CUDA Toolkit, or any Local
OCR dependency to be importable by the main process.  It probes packaged/portable
Python runtimes by launching them as subprocesses and returning a JSON-safe
report.  The goal is to let the Local edition tell the user which engines can use
GPU without asking the user to install Python manually.
"""

from __future__ import annotations

import json
import os
import platform
import re
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

REPORT_SCHEMA_VERSION = 1
REPORT_CACHE_NAME = "local_cuda_runtime_probe.json"

TORCH_RUNTIME_ENV = "YSB_TORCH_CUDA_PYTHON"
PADDLE_RUNTIME_ENV = "YSB_PADDLE_GPU_PYTHON"
COMMON_RUNTIME_ENV = "YSB_LOCAL_PYTHON"


def _hidden_subprocess_kwargs() -> dict[str, Any]:
    """Hide internal console windows for packaged Python/pip probes on Windows."""
    if os.name != "nt":
        return {}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": startupinfo, "creationflags": subprocess.CREATE_NO_WINDOW}
    except Exception:
        return {}


def _app_root() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    try:
        return Path(__file__).resolve().parents[3]
    except Exception:
        return Path.cwd()


def runtime_mode() -> str:
    return "frozen_exe" if getattr(sys, "frozen", False) else "source_bat"


def managed_runtime_root() -> Path:
    root = _app_root()
    if runtime_mode() == "frozen_exe":
        return root / "local_runtime_exe"
    return root / "local_runtime_bat"


def _uses_target_runtime_install() -> bool:
    return runtime_mode() == "frozen_exe"


def _runtime_target_folder(role: str) -> Path:
    base = managed_runtime_root()
    role = str(role or "").lower()
    if _uses_target_runtime_install():
        folder = "paddle_gpu_runtime" if role == "paddle" else "torch_cuda_runtime" if role == "torch" else "python_runtime"
    else:
        folder = "paddle_gpu_venv" if role == "paddle" else "torch_cuda_venv" if role == "torch" else "python"
    return base / folder


def _runtime_python(role: str) -> Path:
    base = managed_runtime_root()
    role = str(role or "").lower()
    if _uses_target_runtime_install():
        # Frozen EXE mode must only look inside local_runtime_exe.  The legacy
        # local_runtime folder can exist beside the package for source/test
        # runs, but CUDA install/probe must not borrow it.
        candidates: list[Path] = []
        if role == "paddle":
            candidates.extend([
                base / "paddle" / "python" / "python.exe",
                base / "bootstrap_python" / "python.exe",
            ])
        elif role == "torch":
            candidates.extend([
                base / "manga_ocr" / "python" / "python.exe",
                base / "paddle" / "python" / "python.exe",
                base / "bootstrap_python" / "python.exe",
            ])
        else:
            candidates.append(base / "bootstrap_python" / "python.exe")
        for candidate in candidates:
            if candidate.exists():
                return candidate
        return base / "bootstrap_python" / "python.exe"
    env_root = _runtime_target_folder(role)
    if os.name == "nt":
        return env_root / "Scripts" / "python.exe"
    return env_root / "bin" / "python"

def _runtime_env(role: str) -> dict[str, str]:
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PYTHONNOUSERSITE", "1")
    if _uses_target_runtime_install():
        target = _runtime_target_folder(role)
        if target.exists():
            target_text = str(target)
            env["YSB_MANAGED_RUNTIME_TARGET"] = target_text
            env["YSB_MANAGED_RUNTIME_ROLE"] = str(role or "")
            old = env.get("PYTHONPATH")
            env["PYTHONPATH"] = target_text + (os.pathsep + old if old else "")
            path_pieces = [target_text]
            for sub in ("torch/lib", "nvidia/cublas/bin", "nvidia/cudnn/bin"):
                try:
                    sub_path = target / sub
                    if sub_path.exists():
                        path_pieces.append(str(sub_path))
                except Exception:
                    pass
            old_path = env.get("PATH") or ""
            if old_path:
                path_pieces.append(old_path)
            env["PATH"] = os.pathsep.join(path_pieces)
    return env


def _cleanup_managed_runtime_pth(python_path: Path) -> list[str]:
    """Delete stale YSB .pth files before launching packaged portable Python.

    Older builds wrote absolute target paths into .pth files.  On non-ASCII
    install paths Windows can read those files using cp949 during site startup
    and kill Python before probe code runs.  Probe/runtime precedence now uses
    PYTHONPATH and YSB_MANAGED_RUNTIME_TARGET instead.
    """
    removed: list[str] = []
    try:
        site_packages = Path(python_path).resolve().parent / "Lib" / "site-packages"
        if not site_packages.exists():
            return removed
        for pth in site_packages.glob("ysb_managed_*_runtime_prepend.pth"):
            try:
                pth.unlink()
                removed.append(str(pth))
            except Exception:
                pass
    except Exception:
        pass
    return removed


def _norm_path(path: Path) -> str:
    try:
        return str(path.resolve())
    except Exception:
        return str(path)


def _unique_paths(paths: list[Path]) -> list[Path]:
    result: list[Path] = []
    seen: set[str] = set()
    for path in paths:
        if not path:
            continue
        key = _norm_path(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _existing_python_candidates(role: str) -> list[Path]:
    root = managed_runtime_root()
    role = str(role or "").lower()
    candidates: list[Path] = []

    # Frozen EXE diagnosis is strict: only local_runtime_exe is valid.  This
    # prevents a stale source/test local_runtime CPU Python from making CUDA
    # install/probe results look inconsistent.
    if not _uses_target_runtime_install():
        for env_name in (TORCH_RUNTIME_ENV if role == "torch" else PADDLE_RUNTIME_ENV, COMMON_RUNTIME_ENV):
            value = os.environ.get(env_name)
            if value:
                candidates.append(Path(value).expanduser())

    if role == "torch":
        candidates.extend([
            _runtime_python("torch"),
            root / "manga_ocr" / "python" / "python.exe",
            root / "paddle" / "python" / "python.exe",
            root / "bootstrap_python" / "python.exe",
        ])
        if not _uses_target_runtime_install():
            candidates.extend([
                root / "torch_cuda" / "python" / "python.exe",
                root / "torch" / "python" / "python.exe",
                root / "python" / "python.exe",
            ])
    elif role == "paddle":
        candidates.extend([
            _runtime_python("paddle"),
            root / "paddle" / "python" / "python.exe",
            root / "bootstrap_python" / "python.exe",
        ])
        if not _uses_target_runtime_install():
            candidates.extend([
                root / "paddle_gpu" / "python" / "python.exe",
                root / "paddle_ocr" / "python" / "python.exe",
                root / "python" / "python.exe",
            ])
    else:
        candidates.append(root / "bootstrap_python" / "python.exe")
        if not _uses_target_runtime_install():
            candidates.append(root / "python" / "python.exe")

    return [path for path in _unique_paths(candidates) if path.exists()]

def runtime_python_candidates(role: str) -> list[str]:
    return [_norm_path(path) for path in _existing_python_candidates(role)]


def _run_command(args: list[str], *, timeout: int = 12) -> dict[str, Any]:
    started = time.perf_counter()
    try:
        if args:
            first = Path(str(args[0]))
            if first.name.lower().startswith("python"):
                _cleanup_managed_runtime_pth(first)
        proc = subprocess.run(
            args,
            cwd=str(_app_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            **_hidden_subprocess_kwargs(),
        )
        return {
            "ok": proc.returncode == 0,
            "returncode": int(proc.returncode),
            "stdout": proc.stdout or "",
            "stderr": proc.stderr or "",
            "elapsed_sec": round(time.perf_counter() - started, 3),
        }
    except FileNotFoundError as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc), "elapsed_sec": round(time.perf_counter() - started, 3), "error": "file_not_found"}
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "returncode": None, "stdout": exc.stdout or "", "stderr": exc.stderr or str(exc), "elapsed_sec": round(time.perf_counter() - started, 3), "error": "timeout"}
    except Exception as exc:
        return {"ok": False, "returncode": None, "stdout": "", "stderr": str(exc), "elapsed_sec": round(time.perf_counter() - started, 3), "error": type(exc).__name__}


def _parse_cuda_version_from_nvidia_smi(text: str) -> str:
    m = re.search(r"CUDA Version:\s*([0-9]+(?:\.[0-9]+)?)", str(text or ""))
    return m.group(1) if m else ""


def _parse_float_version(value: str) -> float | None:
    try:
        parts = str(value or "").split(".")
        if not parts or not parts[0].isdigit():
            return None
        major = int(parts[0])
        minor = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
        return float(f"{major}.{minor}")
    except Exception:
        return None


def _driver_cuda_recommendation(cuda_version: str) -> dict[str, Any]:
    """Return coarse runtime tags based on the driver-reported CUDA capability.

    This is not an installer.  It deliberately returns bundle labels rather than
    a hard pip command because the packaged runtime must match the Python version
    and the exact dependency set shipped with YSB.
    """
    value = _parse_float_version(cuda_version)
    if value is None:
        return {
            "status": "unknown",
            "torch_bundle_hint": "torch_cuda_runtime_unknown",
            "paddle_bundle_hint": "paddle_gpu_runtime_unknown",
            "message_ko": "nvidia-smi의 CUDA 표시값을 읽지 못했습니다. 드라이버와 실제 런타임 스모크 테스트 결과를 우선 보세요.",
            "message_en": "Could not read the CUDA capability reported by nvidia-smi. Prefer the driver and runtime smoke-test results.",
        }
    if value >= 12.8:
        torch_hint = "torch_cuda_cu128_or_compatible"
    elif value >= 12.6:
        torch_hint = "torch_cuda_cu126_or_compatible"
    elif value >= 11.8:
        torch_hint = "torch_cuda_cu118_or_compatible"
    else:
        torch_hint = "driver_update_recommended_for_modern_torch_cuda"

    if value >= 12.9:
        paddle_hint = "paddle_gpu_cu129_or_compatible"
    elif value >= 12.6:
        paddle_hint = "paddle_gpu_cu126_or_compatible"
    elif value >= 11.8:
        paddle_hint = "paddle_gpu_cu118_or_compatible"
    else:
        paddle_hint = "driver_update_recommended_for_paddle_gpu"

    return {
        "status": "ok" if value >= 11.8 else "driver_too_old_or_unknown",
        "driver_cuda_capability": cuda_version,
        "torch_bundle_hint": torch_hint,
        "paddle_bundle_hint": paddle_hint,
        "message_ko": "표시값은 드라이버가 지원하는 CUDA 상한입니다. 실제 사용 가능 여부는 Torch/Paddle 스모크 테스트를 기준으로 판단합니다.",
        "message_en": "This is the CUDA capability reported by the driver. Actual usability is determined by the Torch/Paddle smoke tests.",
    }


def probe_nvidia_smi() -> dict[str, Any]:
    base = _run_command(["nvidia-smi"], timeout=8)
    if not base.get("ok"):
        return {
            "available": False,
            "tool": "nvidia-smi",
            "error": base.get("stderr") or base.get("error") or "nvidia-smi failed",
            "raw": base,
            "gpus": [],
            "cuda_version": "",
            "recommendation": _driver_cuda_recommendation(""),
        }

    cuda_version = _parse_cuda_version_from_nvidia_smi(base.get("stdout") or "")
    query = _run_command([
        "nvidia-smi",
        "--query-gpu=name,driver_version,memory.total,compute_cap",
        "--format=csv,noheader,nounits",
    ], timeout=8)
    has_compute_cap = bool(query.get("ok"))
    if not has_compute_cap:
        query = _run_command([
            "nvidia-smi",
            "--query-gpu=name,driver_version,memory.total",
            "--format=csv,noheader,nounits",
        ], timeout=8)

    gpus: list[dict[str, Any]] = []
    if query.get("ok"):
        for line in (query.get("stdout") or "").splitlines():
            parts = [part.strip() for part in line.split(",")]
            if not parts or not parts[0]:
                continue
            item: dict[str, Any] = {
                "name": parts[0],
                "driver_version": parts[1] if len(parts) > 1 else "",
                "memory_total_mb": None,
                "compute_capability": "",
            }
            if len(parts) > 2:
                try:
                    item["memory_total_mb"] = int(float(parts[2]))
                except Exception:
                    item["memory_total_mb"] = parts[2]
            if has_compute_cap and len(parts) > 3:
                item["compute_capability"] = parts[3]
            gpus.append(item)

    return {
        "available": True,
        "tool": "nvidia-smi",
        "cuda_version": cuda_version,
        "gpus": gpus,
        "raw_query_ok": bool(query.get("ok")),
        "raw_query_error": query.get("stderr") or query.get("error") or "",
        "recommendation": _driver_cuda_recommendation(cuda_version),
    }


_TORCH_PROBE_CODE = r'''
import json, os, sys, platform
result = {
    "ok": False,
    "python": sys.executable,
    "python_version": sys.version.split()[0],
    "platform": platform.platform(),
    "module": "torch",
    "installed": False,
    "version": "",
    "cuda_build": "",
    "cuda_available": False,
    "cuda_device_count": 0,
    "devices": [],
    "smoke_ok": False,
    "module_imports": {},
    "module_paths": {},
    "lama_available": False,
    "manga_optional_available": False,
    "target": "",
    "sys_path_head": [],
    "error": "",
}
target = os.environ.get("YSB_MANAGED_RUNTIME_TARGET") or ""
result["target"] = target
if target and target not in sys.path:
    sys.path.insert(0, target)
try:
    if target and os.name == "nt":
        for _sub in ("", "torch/lib", "nvidia/cublas/bin", "nvidia/cudnn/bin"):
            _p = os.path.join(target, _sub) if _sub else target
            if os.path.isdir(_p):
                try:
                    os.add_dll_directory(_p)
                except Exception:
                    pass
except Exception:
    pass
result["sys_path_head"] = sys.path[:12]
try:
    import torch
    result["torch_file"] = str(getattr(torch, "__file__", "") or "")
    result["installed"] = True
    result["version"] = str(getattr(torch, "__version__", ""))
    result["cuda_build"] = str(getattr(getattr(torch, "version", None), "cuda", "") or "")
    result["cuda_available"] = bool(torch.cuda.is_available())
    for _mod in ["simple_lama_inpainting", "PIL", "transformers", "fugashi", "unidic_lite", "sentencepiece", "safetensors"]:
        try:
            _obj = __import__(_mod)
            result["module_imports"][_mod] = True
            result["module_paths"][_mod] = str(getattr(_obj, "__file__", "") or "")
        except Exception as _e:
            result["module_imports"][_mod] = False
            result["module_paths"][_mod] = f"{type(_e).__name__}: {_e}"
    result["lama_available"] = bool(result["module_imports"].get("simple_lama_inpainting"))
    result["manga_optional_available"] = all(bool(result["module_imports"].get(m)) for m in ["PIL", "transformers", "fugashi", "unidic_lite", "sentencepiece", "safetensors"])
    if result["cuda_available"]:
        result["cuda_device_count"] = int(torch.cuda.device_count())
        for idx in range(result["cuda_device_count"]):
            dev = {"index": idx, "name": str(torch.cuda.get_device_name(idx))}
            try:
                props = torch.cuda.get_device_properties(idx)
                dev["total_memory_mb"] = int(getattr(props, "total_memory", 0) // (1024 * 1024))
                dev["major"] = int(getattr(props, "major", 0))
                dev["minor"] = int(getattr(props, "minor", 0))
            except Exception as e:
                dev["properties_error"] = str(e)
            result["devices"].append(dev)
        x = torch.randn((8, 8), device="cuda")
        y = (x @ x).sum().item()
        torch.cuda.synchronize()
        result["smoke_ok"] = True
        result["smoke_value"] = float(y)
    result["ok"] = True
except Exception as e:
    result["error"] = f"{type(e).__name__}: {e}"
print(json.dumps(result, ensure_ascii=False))
'''


_PADDLE_PROBE_CODE = r'''
import json, os, sys, platform
result = {
    "ok": False,
    "python": sys.executable,
    "python_version": sys.version.split()[0],
    "platform": platform.platform(),
    "module": "paddle",
    "installed": False,
    "version": "",
    "cuda_compiled": False,
    "cuda_device_count": 0,
    "gpu_available": False,
    "smoke_ok": False,
    "target": "",
    "sys_path_head": [],
    "error": "",
}
target = os.environ.get("YSB_MANAGED_RUNTIME_TARGET") or ""
result["target"] = target
if target and target not in sys.path:
    sys.path.insert(0, target)
try:
    if target and os.name == "nt":
        for _sub in ("", "nvidia/cublas/bin", "nvidia/cudnn/bin"):
            _p = os.path.join(target, _sub) if _sub else target
            if os.path.isdir(_p):
                try:
                    os.add_dll_directory(_p)
                except Exception:
                    pass
except Exception:
    pass
result["sys_path_head"] = sys.path[:12]
try:
    import paddle
    result["paddle_file"] = str(getattr(paddle, "__file__", "") or "")
    result["installed"] = True
    result["version"] = str(getattr(paddle, "__version__", ""))
    try:
        result["cuda_compiled"] = bool(paddle.device.is_compiled_with_cuda())
    except Exception as e:
        result["cuda_compiled_error"] = str(e)
    try:
        result["cuda_device_count"] = int(paddle.device.cuda.device_count())
    except Exception as e:
        result["cuda_device_count_error"] = str(e)
    result["gpu_available"] = bool(result.get("cuda_compiled") and int(result.get("cuda_device_count") or 0) > 0)
    if result["gpu_available"]:
        paddle.set_device("gpu:0")
        x = paddle.randn([8, 8], dtype="float32")
        y = paddle.sum(paddle.matmul(x, x)).numpy().tolist()
        result["smoke_ok"] = True
        result["smoke_value"] = y
    result["ok"] = True
except Exception as e:
    result["error"] = f"{type(e).__name__}: {e}"
print(json.dumps(result, ensure_ascii=False))
'''


def _probe_python_runtime(python_path: Path, code: str, *, timeout: int = 35, role: str | None = None) -> dict[str, Any]:
    started = time.perf_counter()
    cleaned_pth = _cleanup_managed_runtime_pth(python_path)
    try:
        proc = subprocess.run(
            [str(python_path), "-c", code],
            cwd=str(_app_root()),
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
            env=_runtime_env(role or ""),
            **_hidden_subprocess_kwargs(),
        )
        stdout = (proc.stdout or "").strip()
        parsed: dict[str, Any]
        try:
            parsed = json.loads(stdout.splitlines()[-1] if stdout else "{}")
        except Exception:
            parsed = {"ok": False, "parse_error": "probe output was not valid JSON", "stdout": stdout}
        parsed["returncode"] = int(proc.returncode)
        parsed["stderr"] = proc.stderr or ""
        parsed["elapsed_sec"] = round(time.perf_counter() - started, 3)
        parsed["candidate_python"] = _norm_path(python_path)
        if cleaned_pth:
            parsed["cleaned_managed_pth"] = cleaned_pth
        if proc.returncode != 0 and not parsed.get("error"):
            parsed["error"] = (proc.stderr or stdout or f"probe returned {proc.returncode}").strip()
        return parsed
    except subprocess.TimeoutExpired as exc:
        return {
            "ok": False,
            "candidate_python": _norm_path(python_path),
            "returncode": None,
            "elapsed_sec": round(time.perf_counter() - started, 3),
            "error": "timeout",
            "stdout": exc.stdout or "",
            "stderr": exc.stderr or "",
        }
    except Exception as exc:
        return {
            "ok": False,
            "candidate_python": _norm_path(python_path),
            "returncode": None,
            "elapsed_sec": round(time.perf_counter() - started, 3),
            "error": f"{type(exc).__name__}: {exc}",
        }


def _select_best_torch(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    gpu = [c for c in candidates if c.get("ok") and c.get("installed") and c.get("cuda_available") and c.get("smoke_ok")]
    if gpu:
        return gpu[0]
    installed = [c for c in candidates if c.get("ok") and c.get("installed")]
    if installed:
        return installed[0]
    return candidates[0] if candidates else None


def _select_best_paddle(candidates: list[dict[str, Any]]) -> dict[str, Any] | None:
    gpu = [c for c in candidates if c.get("ok") and c.get("installed") and c.get("gpu_available") and c.get("smoke_ok")]
    if gpu:
        return gpu[0]
    installed = [c for c in candidates if c.get("ok") and c.get("installed")]
    if installed:
        return installed[0]
    return candidates[0] if candidates else None


def probe_torch_runtimes() -> dict[str, Any]:
    candidates = _existing_python_candidates("torch")
    results = [_probe_python_runtime(path, _TORCH_PROBE_CODE, timeout=40, role="torch") for path in candidates]
    selected = _select_best_torch(results)
    return {
        "role": "torch",
        "candidate_count": len(candidates),
        "candidates": results,
        "selected": selected,
        "gpu_ready": bool(selected and selected.get("cuda_available") and selected.get("smoke_ok")),
        "installed": bool(selected and selected.get("installed")),
    }


def probe_paddle_runtimes() -> dict[str, Any]:
    candidates = _existing_python_candidates("paddle")
    results = [_probe_python_runtime(path, _PADDLE_PROBE_CODE, timeout=40, role="paddle") for path in candidates]
    selected = _select_best_paddle(results)
    return {
        "role": "paddle",
        "candidate_count": len(candidates),
        "candidates": results,
        "selected": selected,
        "gpu_ready": bool(selected and selected.get("gpu_available") and selected.get("smoke_ok")),
        "installed": bool(selected and selected.get("installed")),
    }


def _engine_status(torch_report: dict[str, Any], paddle_report: dict[str, Any]) -> dict[str, str]:
    torch_gpu = bool(torch_report.get("gpu_ready"))
    torch_installed = bool(torch_report.get("installed"))
    torch_selected = dict(torch_report.get("selected") or {})
    torch_modules = dict(torch_selected.get("module_imports") or {})
    lama_ok = bool(torch_selected.get("lama_available") or torch_modules.get("simple_lama_inpainting"))
    manga_ok = bool(torch_selected.get("manga_optional_available"))
    paddle_gpu = bool(paddle_report.get("gpu_ready"))
    paddle_installed = bool(paddle_report.get("installed"))
    return {
        "lama_inpaint": ("gpu_available" if torch_gpu and lama_ok else ("lama_package_missing" if torch_installed and not lama_ok else ("cpu_runtime_available" if torch_installed else "torch_runtime_missing"))),
        "manga_ocr": ("gpu_available" if torch_gpu and manga_ok else ("manga_package_missing" if torch_installed and not manga_ok else ("cpu_runtime_available" if torch_installed else "torch_runtime_missing"))),
        "comic_text_detector": "gpu_available" if torch_gpu else ("cpu_runtime_available" if torch_installed else "torch_runtime_missing"),
        "paddle_ocr": "gpu_available" if paddle_gpu else ("cpu_runtime_available" if paddle_installed else "paddle_runtime_missing"),
    }


def _build_recommendations(nvidia: dict[str, Any], torch_report: dict[str, Any], paddle_report: dict[str, Any]) -> list[dict[str, str]]:
    recs: list[dict[str, str]] = []
    if not nvidia.get("available"):
        recs.append({
            "level": "info",
            "ko": "NVIDIA GPU/nvidia-smi가 감지되지 않았습니다. CUDA 엔진은 CPU 모드 또는 비활성 상태로 두세요.",
            "en": "No NVIDIA GPU/nvidia-smi was detected. Keep CUDA engines on CPU mode or disabled.",
        })
        return recs

    hint = nvidia.get("recommendation") or {}
    if not torch_report.get("gpu_ready"):
        recs.append({
            "level": "action",
            "ko": f"Torch CUDA 런타임이 아직 GPU 스모크 테스트를 통과하지 못했습니다. 후보 번들: {hint.get('torch_bundle_hint', 'torch_cuda_runtime')}",
            "en": f"Torch CUDA runtime did not pass the GPU smoke test yet. Candidate bundle: {hint.get('torch_bundle_hint', 'torch_cuda_runtime')}",
        })
    else:
        selected = dict((torch_report or {}).get("selected") or {})
        imports = dict(selected.get("module_imports") or {})
        if not imports.get("simple_lama_inpainting"):
            recs.append({
                "level": "action",
                "ko": "Torch CUDA는 가능하지만 LOCAL LaMa 필수 패키지(simple-lama-inpainting)가 없습니다. Torch CUDA 런타임 설치/복구를 다시 실행해 주세요.",
                "en": "Torch CUDA is available, but the required LOCAL LaMa package (simple-lama-inpainting) is missing. Run Torch CUDA runtime install/repair again.",
            })
    if not paddle_report.get("gpu_ready"):
        recs.append({
            "level": "action",
            "ko": f"Paddle GPU 런타임이 아직 GPU 스모크 테스트를 통과하지 못했습니다. 후보 번들: {hint.get('paddle_bundle_hint', 'paddle_gpu_runtime')}",
            "en": f"Paddle GPU runtime did not pass the GPU smoke test yet. Candidate bundle: {hint.get('paddle_bundle_hint', 'paddle_gpu_runtime')}",
        })
    if torch_report.get("gpu_ready") and paddle_report.get("gpu_ready"):
        recs.append({
            "level": "ok",
            "ko": "Torch/Paddle GPU 스모크 테스트가 모두 통과했습니다. 로컬 인페인팅과 OCR GPU 실행을 시도할 수 있습니다.",
            "en": "Both Torch/Paddle GPU smoke tests passed. Local inpainting and OCR GPU execution can be attempted.",
        })
    return recs


def report_path() -> Path:
    try:
        from ysb.core.cache_utils import get_cache_file
        return Path(get_cache_file(REPORT_CACHE_NAME))
    except Exception:
        return _app_root() / REPORT_CACHE_NAME


def save_report(report: dict[str, Any], path: str | Path | None = None) -> str:
    target = Path(path) if path else report_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return str(target)


def run_full_probe(*, write_report: bool = True) -> dict[str, Any]:
    started = time.perf_counter()
    nvidia = probe_nvidia_smi()
    torch_report = probe_torch_runtimes()
    paddle_report = probe_paddle_runtimes()
    report: dict[str, Any] = {
        "schema_version": REPORT_SCHEMA_VERSION,
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "elapsed_sec": 0.0,
        "app_root": _norm_path(_app_root()),
        "runtime_mode": runtime_mode(),
        "runtime_root": _norm_path(managed_runtime_root()),
        "strict_managed_runtime": True,
        "main_python": sys.executable,
        "frozen": bool(getattr(sys, "frozen", False)),
        "system": {
            "platform": platform.platform(),
            "machine": platform.machine(),
            "python_version": sys.version.split()[0],
        },
        "nvidia": nvidia,
        "torch": torch_report,
        "paddle": paddle_report,
        "ysb_engines": _engine_status(torch_report, paddle_report),
        "recommendations": _build_recommendations(nvidia, torch_report, paddle_report),
    }
    report["elapsed_sec"] = round(time.perf_counter() - started, 3)
    if write_report:
        try:
            report["report_path"] = save_report(report)
        except Exception as exc:
            report["report_save_error"] = str(exc)
    return report


def _main() -> int:
    report = run_full_probe(write_report=True)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(_main())
