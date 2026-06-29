# -*- coding: utf-8 -*-
"""Managed local CUDA runtime installer for YSB Translator.

This module is intentionally UI-agnostic.  It creates and maintains runtime
folders that are separate from the main application environment:

- source/BAT launch: <app root>/local_runtime_bat
- frozen EXE launch: <app root>/local_runtime_exe

The main .venv may be used only as a bootstrap Python while running from source.
It is not treated as a CUDA runtime candidate by the probe module.
"""

from __future__ import annotations

import os
import json
import platform
import re
import shutil
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable

ProgressCallback = Callable[[Any], None]

RUNTIME_MARKER_NAME = "ysb_runtime_install_marker.json"


def _hidden_subprocess_kwargs() -> dict[str, Any]:
    """Hide internal console windows for packaged Python/pip subprocesses on Windows."""
    if os.name != "nt":
        return {}
    try:
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = subprocess.SW_HIDE
        return {"startupinfo": startupinfo, "creationflags": subprocess.CREATE_NO_WINDOW}
    except Exception:
        return {}


PIP_BOOTSTRAP_CODE = (
    "import sys; "
    "wheel=sys.argv[1]; "
    "sys.path.insert(0, wheel); "
    "from pip._internal.cli.main import main; "
    "raise SystemExit(main(sys.argv[2:]))"
)


def _pip_bootstrap_wheel_dirs() -> list[Path]:
    root = _app_root()
    runtime_root = managed_runtime_root()
    if runtime_mode() == "frozen_exe":
        # Frozen Local EXE is intentionally self-contained.  Do not borrow
        # wheels from source/test local_runtime folders because the installed
        # CUDA runtime must be reproducible inside local_runtime_exe only.
        candidates = [
            runtime_root / "_bootstrap_wheels",
            root / "local_runtime_exe" / "_bootstrap_wheels",
        ]
    else:
        candidates = [
            runtime_root / "_bootstrap_wheels",
            root / "local_runtime_bat" / "_bootstrap_wheels",
            root / "local_runtime" / "_bootstrap_wheels",
        ]
    result: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def _find_bundled_pip_wheel() -> Path | None:
    wheels: list[Path] = []
    for folder in _pip_bootstrap_wheel_dirs():
        try:
            if folder.exists():
                wheels.extend(folder.glob("pip-*.whl"))
        except Exception:
            continue
    wheels = [w for w in wheels if w.is_file()]
    if not wheels:
        return None
    # Prefer the newest-looking wheel name. pip wheels sort correctly enough for
    # our pinned build cache names such as pip-25.3-py3-none-any.whl.
    return sorted(wheels, key=lambda p: p.name.lower())[-1]


def _pip_base_from_wheel(python: Path, wheel: Path) -> list[str]:
    return [str(python), "-c", PIP_BOOTSTRAP_CODE, str(wheel), "--disable-pip-version-check"]


def _resolve_pip_runner(python: Path, *, role: str | None = None, progress: ProgressCallback | None = None) -> dict[str, Any]:
    """Return a pip command prefix usable with bundled portable Python.

    Frozen EXE portable Python often has no pip package installed.  In that
    case we run pip straight from a bundled pip wheel by inserting the wheel
    into sys.path inside a tiny -c bootstrap command.  This keeps the user PC
    Python-free while still allowing online --target installs.
    """
    env_extra = runtime_subprocess_env(role or "", os.environ.copy()) if role else None
    direct = _run([str(python), "-m", "pip", "--version"], progress=progress, timeout=60, env_extra=env_extra)
    if direct.get("ok"):
        return {
            "ok": True,
            "mode": "python_m_pip",
            "base": [str(python), "-m", "pip", "--disable-pip-version-check"],
            "env_extra": env_extra,
            "check_result": direct,
        }

    wheel = _find_bundled_pip_wheel()
    if wheel is None:
        return {
            "ok": False,
            "mode": "missing_bundled_pip_wheel",
            "result": direct,
            "message": (
                "포터블 Python에 pip가 없고, EXE 패키지 안의 _bootstrap_wheels/pip-*.whl도 찾지 못했습니다. "
                "Local EXE를 다시 빌드해 주세요."
            ),
        }

    wheel_base = _pip_base_from_wheel(python, wheel)
    wheel_check = _run(wheel_base + ["--version"], progress=progress, timeout=60, env_extra=env_extra)
    if wheel_check.get("ok"):
        return {
            "ok": True,
            "mode": "bundled_pip_wheel",
            "wheel": str(wheel),
            "base": wheel_base,
            "env_extra": env_extra,
            "check_result": wheel_check,
            "direct_check_result": direct,
        }

    return {
        "ok": False,
        "mode": "bundled_pip_wheel_failed",
        "wheel": str(wheel),
        "result": wheel_check,
        "direct_check_result": direct,
        "message": "포터블 Python에서 내장 pip wheel을 실행하지 못했습니다. EXE 패키지의 _bootstrap_wheels 구성을 확인해 주세요.",
    }


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
    """Frozen EXE builds cannot assume that the bundled portable Python has venv.

    Source/BAT mode keeps the old managed venv layout. Frozen EXE mode installs
    CUDA packages directly into role-specific target folders and launches a
    bundled Python with PYTHONPATH pointing at that folder.
    """
    return runtime_mode() == "frozen_exe"


def runtime_env_folder(role: str) -> Path:
    role_key = str(role or "").lower().strip()
    if _uses_target_runtime_install():
        if role_key == "paddle":
            return managed_runtime_root() / "paddle_gpu_runtime"
        if role_key == "torch":
            return managed_runtime_root() / "torch_cuda_runtime"
        return managed_runtime_root() / f"{role_key or 'runtime'}_runtime"
    if role_key == "paddle":
        return managed_runtime_root() / "paddle_gpu_venv"
    if role_key == "torch":
        return managed_runtime_root() / "torch_cuda_venv"
    return managed_runtime_root() / f"{role_key or 'runtime'}_venv"


def _role_env_python(role: str) -> Path | None:
    role_key = str(role or "").lower().strip()
    env_names = []
    if role_key == "torch":
        env_names.extend(["YSB_TORCH_CUDA_PYTHON", "YSB_MANGA_OCR_PYTHON", "YSB_LOCAL_PYTHON"])
    elif role_key == "paddle":
        env_names.extend(["YSB_PADDLE_GPU_PYTHON", "YSB_PADDLEOCR_PYTHON", "YSB_LOCAL_PYTHON"])
    else:
        env_names.append("YSB_LOCAL_PYTHON")
    for name in env_names:
        value = os.environ.get(name)
        if value:
            path = Path(value).expanduser()
            if path.exists():
                return path
    return None


def runtime_python_candidates(role: str | None = None) -> list[Path]:
    root = _app_root()
    runtime_root = managed_runtime_root()
    role_key = str(role or "").lower().strip()
    candidates: list[Path] = []
    role_env = None if _uses_target_runtime_install() else _role_env_python(role_key)
    if role_env is not None:
        candidates.append(role_env)

    if _uses_target_runtime_install():
        # EXE/frozen: these are execution/installer Python candidates only.
        # CUDA packages are installed into runtime_env_folder(role), not into
        # another venv beneath these Python folders.
        if role_key == "paddle":
            candidates.extend([
                runtime_root / "paddle" / "python" / "python.exe",
                runtime_root / "bootstrap_python" / "python.exe",
            ])
        elif role_key == "torch":
            candidates.extend([
                runtime_root / "manga_ocr" / "python" / "python.exe",
                runtime_root / "paddle" / "python" / "python.exe",
                runtime_root / "bootstrap_python" / "python.exe",
            ])
        else:
            candidates.extend([
                runtime_root / "bootstrap_python" / "python.exe",
                runtime_root / "paddle" / "python" / "python.exe",
                runtime_root / "manga_ocr" / "python" / "python.exe",
            ])
    else:
        env = runtime_env_folder(role_key)
        if os.name == "nt":
            candidates.append(env / "Scripts" / "python.exe")
        else:
            candidates.append(env / "bin" / "python")
        candidates.extend([
            Path(sys.executable),
            root / ".venv" / "Scripts" / "python.exe",
            root / ".venv" / "bin" / "python",
        ])

    result: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        if path.exists():
            result.append(path)
    return result


def runtime_python_path(role: str) -> Path:
    if _uses_target_runtime_install():
        candidates = runtime_python_candidates(role)
        if candidates:
            return candidates[0]
        # Stable fallback used for status display before the packaged runtime is present.
        return managed_runtime_root() / "bootstrap_python" / "python.exe"
    env = runtime_env_folder(role)
    if os.name == "nt":
        return env / "Scripts" / "python.exe"
    return env / "bin" / "python"


def runtime_subprocess_env(role: str, base_env: dict[str, str] | None = None) -> dict[str, str]:
    """Return an environment that can import the managed runtime packages.

    In source/BAT venv mode this mostly returns *base_env*. In frozen EXE target
    mode it prepends the target package folder to PYTHONPATH so the bundled
    Python can import packages installed by pip --target.
    """
    env = dict(base_env or os.environ.copy())
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PIP_NO_PYTHON_VERSION_WARNING", "1")
    env.setdefault("PIP_NO_INPUT", "1")
    env.setdefault("PYTHONNOUSERSITE", "1")
    target = runtime_env_folder(role)
    if _uses_target_runtime_install() and target.exists():
        target_text = str(target)
        env["YSB_MANAGED_RUNTIME_TARGET"] = target_text
        env["YSB_MANAGED_RUNTIME_ROLE"] = str(role or "")
        pieces = [target_text]
        old = env.get("PYTHONPATH")
        if old:
            pieces.append(old)
        env["PYTHONPATH"] = os.pathsep.join(pieces)
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


def bootstrap_python_candidates(role: str | None = None) -> list[Path]:
    candidates: list[Path] = []
    env_value = os.environ.get("YSB_RUNTIME_BOOTSTRAP_PYTHON")
    if env_value:
        path = Path(env_value).expanduser()
        if path.exists():
            candidates.append(path)
    candidates.extend(runtime_python_candidates(role))
    result: list[Path] = []
    seen: set[str] = set()
    for path in candidates:
        try:
            key = str(path.resolve())
        except Exception:
            key = str(path)
        if key in seen:
            continue
        seen.add(key)
        result.append(path)
    return result


def select_bootstrap_python(role: str | None = None) -> Path | None:
    candidates = bootstrap_python_candidates(role)
    return candidates[0] if candidates else None


def _bytes_human(value: int | float | None) -> str:
    try:
        n = float(value or 0)
    except Exception:
        n = 0.0
    units = ["B", "KB", "MB", "GB", "TB"]
    idx = 0
    while n >= 1024 and idx < len(units) - 1:
        n /= 1024.0
        idx += 1
    if idx == 0:
        return f"{int(n)} {units[idx]}"
    return f"{n:.1f} {units[idx]}"


def _json_safe(value: Any) -> Any:
    if isinstance(value, Path):
        return str(value)
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_json_safe(v) for v in value]
    return str(value)


def _new_install_log_path(role: str) -> Path:
    try:
        log_dir = managed_runtime_root() / "_install_logs"
        log_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        return log_dir / f"local_cuda_runtime_install_{role}_{stamp}.jsonl"
    except Exception:
        return Path.cwd() / f"local_cuda_runtime_install_{role}.jsonl"


def _append_install_log(log_path: Path | None, event: str, **fields: Any) -> None:
    if log_path is None:
        return
    try:
        log_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S%z"), "event": str(event)}
        payload.update({str(k): _json_safe(v) for k, v in fields.items()})
        with log_path.open("a", encoding="utf-8", errors="replace") as f:
            f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    except Exception:
        pass


def _dir_size_bytes(path: Path) -> int:
    total = 0
    try:
        if not path.exists():
            return 0
        for item in path.rglob("*"):
            try:
                if item.is_file():
                    total += int(item.stat().st_size)
            except Exception:
                continue
    except Exception:
        return total
    return total


def _top_level_entries(path: Path, *, limit: int = 80) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    try:
        if not path.exists():
            return result
        for item in sorted(path.iterdir(), key=lambda x: x.name.lower())[:limit]:
            entry: dict[str, Any] = {"name": item.name, "is_dir": item.is_dir()}
            try:
                if item.is_file():
                    entry["size"] = int(item.stat().st_size)
                    entry["size_text"] = _bytes_human(entry["size"])
                elif item.is_dir():
                    entry["size"] = _dir_size_bytes(item)
                    entry["size_text"] = _bytes_human(entry["size"])
            except Exception as exc:
                entry["error"] = str(exc)
            result.append(entry)
    except Exception as exc:
        result.append({"error": str(exc)})
    return result


def _target_snapshot(path: Path) -> dict[str, Any]:
    size = _dir_size_bytes(path)
    return {
        "path": str(path),
        "exists": path.exists(),
        "size": size,
        "size_text": _bytes_human(size),
        "top_level": _top_level_entries(path),
    }


def _result_summary(result: dict[str, Any] | None) -> dict[str, Any]:
    r = dict(result or {})
    stdout = str(r.pop("stdout", "") or "")
    stderr = str(r.pop("stderr", "") or "")
    if stdout:
        lines = stdout.splitlines()
        r["stdout_line_count"] = len(lines)
        r["stdout_tail"] = lines[-80:]
    if stderr:
        lines = stderr.splitlines()
        r["stderr_line_count"] = len(lines)
        r["stderr_tail"] = lines[-80:]
    return r


def _purge_target_packages(target: Path, package_names: list[str], *, log_path: Path | None = None, reason: str = "purge") -> None:
    """Remove packages from a pip --target runtime folder before protected installs.

    pip --target does not behave like a normal environment: a later dependency
    install can place a CPU torch wheel into the same target folder and overwrite
    the CUDA torch files.  Before installing the protected CUDA packages, delete
    any old top-level packages and metadata so the final import state is
    deterministic.
    """
    removed: list[str] = []
    errors: list[dict[str, str]] = []
    if not target.exists():
        return
    normalized: set[str] = set()
    for name in package_names:
        n = str(name or "").strip()
        if not n:
            continue
        normalized.add(n)
        normalized.add(n.replace("-", "_"))
        normalized.add(n.replace("_", "-"))
    for name in sorted(normalized):
        # top-level package/module folders/files
        for candidate in [target / name, target / (name.replace("-", "_"))]:
            if candidate.exists():
                try:
                    if candidate.is_dir():
                        shutil.rmtree(candidate)
                    else:
                        candidate.unlink()
                    removed.append(str(candidate))
                except Exception as exc:
                    errors.append({"path": str(candidate), "error": f"{type(exc).__name__}: {exc}"})
        # dist-info/egg-info metadata can keep stale versions visible to pip/probes
        patterns = [f"{name}-*.dist-info", f"{name.replace('-', '_')}-*.dist-info", f"{name}-*.egg-info", f"{name.replace('-', '_')}-*.egg-info"]
        for pattern in patterns:
            for candidate in target.glob(pattern):
                try:
                    if candidate.is_dir():
                        shutil.rmtree(candidate)
                    else:
                        candidate.unlink()
                    removed.append(str(candidate))
                except Exception as exc:
                    errors.append({"path": str(candidate), "error": f"{type(exc).__name__}: {exc}"})
    if removed or errors:
        _append_install_log(log_path, "target_package_purge", reason=reason, packages=package_names, removed=removed, errors=errors, snapshot=_target_snapshot(target))


def _torch_runtime_cuda_ok(diagnostics: dict[str, Any]) -> tuple[bool, str]:
    try:
        torch_info = ((diagnostics or {}).get("details") or {}).get("torch") or {}
        cuda_build = str(torch_info.get("cuda_build") or "")
        cuda_available = bool(torch_info.get("cuda_available"))
        device_count = int(torch_info.get("cuda_device_count") or 0)
        torch_file = str(torch_info.get("file") or "")
        version = str(torch_info.get("version") or "")
        if cuda_build and cuda_available and device_count > 0:
            return True, ""
        return False, f"torch CUDA smoke failed: version={version}, cuda_build={cuda_build}, cuda_available={cuda_available}, device_count={device_count}, file={torch_file}"
    except Exception as exc:
        return False, f"torch CUDA smoke check error: {type(exc).__name__}: {exc}"


def _paddle_runtime_cuda_ok(diagnostics: dict[str, Any]) -> tuple[bool, str]:
    try:
        paddle_info = ((diagnostics or {}).get("details") or {}).get("paddle") or {}
        cuda_compiled = bool(paddle_info.get("cuda_compiled"))
        # The detailed probe performs the real Paddle smoke test.  The installer
        # only guarantees the CUDA build is imported from the target runtime.
        if cuda_compiled:
            return True, ""
        return False, f"paddle CUDA build check failed: file={paddle_info.get('file')}, version={paddle_info.get('version')}, cuda_compiled={cuda_compiled}"
    except Exception as exc:
        return False, f"paddle CUDA smoke check error: {type(exc).__name__}: {exc}"


def _portable_python_site_packages(python: Path) -> Path | None:
    try:
        py = Path(python).resolve()
        site_packages = py.parent / "Lib" / "site-packages"
        return site_packages
    except Exception:
        return None


def _cleanup_managed_runtime_pth(python: Path, *, log_path: Path | None = None, reason: str = "cleanup") -> None:
    """Remove old YSB .pth bootstrap files from packaged portable Python.

    The previous implementation wrote an absolute target path into a .pth file.
    On Windows Korean/Japanese paths can make the portable Python site module
    read that UTF-8 file as cp949 and fail before pip/probe starts.  Runtime
    precedence is now carried only through subprocess environment variables
    (PYTHONPATH/YSB_MANAGED_RUNTIME_TARGET), so stale .pth files must be deleted.
    """
    try:
        if not python:
            return
        site_packages = _portable_python_site_packages(Path(python))
        if site_packages is None or not site_packages.exists():
            return
        removed: list[str] = []
        for pth in site_packages.glob("ysb_managed_*_runtime_prepend.pth"):
            try:
                pth.unlink()
                removed.append(str(pth))
            except Exception as exc:
                _append_install_log(log_path, "managed_pth_cleanup_delete_error", python=str(python), pth=str(pth), error=f"{type(exc).__name__}: {exc}")
        if removed:
            _append_install_log(log_path, "managed_pth_cleanup_done", python=str(python), reason=reason, removed=removed)
    except Exception as exc:
        _append_install_log(log_path, "managed_pth_cleanup_error", python=str(python), reason=reason, error=f"{type(exc).__name__}: {exc}")


def _install_target_path_bootstrap(python: Path, role: str, target: Path, *, log_path: Path | None = None) -> None:
    """Compatibility hook kept for existing call sites.

    Do not write .pth files anymore.  Import priority is provided by
    runtime_subprocess_env() and worker env variables.  This function only
    removes stale .pth files left by older builds.
    """
    _cleanup_managed_runtime_pth(python, log_path=log_path, reason=f"target_runtime_env_only:{role}")


_PROGRESS_RE = re.compile(r"Progress\s+(\d+)\s+of\s+(\d+)", re.IGNORECASE)
_COLLECTING_RE = re.compile(r"Collecting\s+([^\s]+)", re.IGNORECASE)
_DOWNLOADING_RE = re.compile(r"Downloading\s+([^\s]+)", re.IGNORECASE)


def _emit_progress(progress: ProgressCallback | None, payload: Any) -> None:
    if progress is None:
        return
    try:
        progress(payload)
    except Exception:
        try:
            progress(str(payload))
        except Exception:
            pass


def _parse_process_piece(piece: str, *, state: dict[str, Any], progress: ProgressCallback | None, output_lines: list[str]) -> None:
    text = str(piece or "").strip()
    if not text:
        return
    output_lines.append(text)
    m_pkg = _COLLECTING_RE.search(text) or _DOWNLOADING_RE.search(text)
    if m_pkg:
        state["package"] = m_pkg.group(1)
        _emit_progress(progress, {"type": "package", "package": state.get("package"), "line": text})
        return
    m = _PROGRESS_RE.search(text)
    if m:
        current = int(m.group(1))
        total = int(m.group(2))
        now = time.perf_counter()
        started = float(state.get("download_started") or now)
        if not state.get("download_started"):
            state["download_started"] = now
        pct = int(round((current / total) * 100)) if total > 0 else 0
        elapsed = max(0.001, now - started)
        speed = current / elapsed
        _emit_progress(progress, {
            "type": "download_progress",
            "current": current,
            "total": total,
            "percent": max(0, min(100, pct)),
            "current_text": _bytes_human(current),
            "total_text": _bytes_human(total),
            "speed_text": f"{_bytes_human(speed)}/s",
            "package": state.get("package") or "",
            "line": text,
        })
        return
    _emit_progress(progress, text)


def _run(args: list[str], *, cwd: Path | None = None, timeout: int | None = None, progress: ProgressCallback | None = None, env_extra: dict[str, str] | None = None) -> dict[str, Any]:
    _emit_progress(progress, {"type": "command", "text": "> " + " ".join(str(a) for a in args)})
    started = time.perf_counter()
    env = os.environ.copy()
    env.setdefault("PYTHONUTF8", "1")
    env.setdefault("PYTHONIOENCODING", "utf-8")
    env.setdefault("PIP_DISABLE_PIP_VERSION_CHECK", "1")
    env.setdefault("PIP_NO_PYTHON_VERSION_WARNING", "1")
    env.setdefault("PIP_NO_INPUT", "1")
    env.setdefault("PYTHONNOUSERSITE", "1")
    if env_extra:
        env.update({str(k): str(v) for k, v in env_extra.items()})
    try:
        # If the first argument is one of our portable Python executables, remove
        # stale YSB .pth bootstrap files before the interpreter starts.  Otherwise
        # Python can die during site initialization before our command code runs.
        if args:
            first = Path(str(args[0]))
            if first.name.lower().startswith("python"):
                _cleanup_managed_runtime_pth(first, reason="before_subprocess_run")
        proc = subprocess.Popen(
            args,
            cwd=str(cwd or _app_root()),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            text=True,
            encoding="utf-8",
            errors="replace",
            bufsize=1,
            env=env,
            **_hidden_subprocess_kwargs(),
        )
        output_lines: list[str] = []
        state: dict[str, Any] = {}
        try:
            assert proc.stdout is not None
            buf = ""
            while True:
                ch = proc.stdout.read(1)
                if ch == "" and proc.poll() is not None:
                    break
                if ch == "":
                    if timeout is not None and time.perf_counter() - started > timeout:
                        raise subprocess.TimeoutExpired(args, timeout)
                    time.sleep(0.02)
                    continue
                if ch in "\r\n":
                    if buf:
                        _parse_process_piece(buf, state=state, progress=progress, output_lines=output_lines)
                        buf = ""
                else:
                    buf += ch
                    # pip raw progress lines can be long but should not be allowed to grow forever.
                    if len(buf) > 8192:
                        _parse_process_piece(buf, state=state, progress=progress, output_lines=output_lines)
                        buf = ""
            if buf:
                _parse_process_piece(buf, state=state, progress=progress, output_lines=output_lines)
            returncode = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            proc.kill()
            returncode = proc.wait()
            output_lines.append(f"TIMEOUT after {timeout}s")
        output = "\n".join(output_lines)
        return {
            "ok": returncode == 0,
            "returncode": int(returncode),
            "stdout": output,
            "stderr": "",
            "elapsed_sec": round(time.perf_counter() - started, 3),
        }
    except Exception as exc:
        _emit_progress(progress, {"type": "error", "text": f"ERROR: {type(exc).__name__}: {exc}"})
        return {
            "ok": False,
            "returncode": None,
            "stdout": "",
            "stderr": str(exc),
            "elapsed_sec": round(time.perf_counter() - started, 3),
            "error": type(exc).__name__,
        }



def _verify_runtime_modules(python: Path, modules: list[str], *, progress: ProgressCallback | None = None, role: str | None = None) -> dict[str, Any]:
    code = r"""
import importlib.util, json, os, sys
target = os.environ.get('YSB_MANAGED_RUNTIME_TARGET') or ''
if target and target not in sys.path:
    sys.path.insert(0, target)
try:
    if target and os.name == 'nt':
        for sub in ('', 'torch/lib', 'nvidia/cublas/bin', 'nvidia/cudnn/bin'):
            p = os.path.join(target, sub) if sub else target
            if os.path.isdir(p):
                try:
                    os.add_dll_directory(p)
                except Exception:
                    pass
except Exception:
    pass
mods = __YSB_MODULES__
missing = []
specs = {}
for m in mods:
    spec = importlib.util.find_spec(m)
    if spec is None:
        missing.append(m)
        specs[m] = None
    else:
        locs = getattr(spec, 'submodule_search_locations', None)
        specs[m] = {'origin': str(getattr(spec, 'origin', '') or ''), 'submodule_search_locations': [str(x) for x in locs] if locs else []}
details = {}
try:
    if importlib.util.find_spec('torch') is not None:
        import torch
        details['torch'] = {'file': str(getattr(torch, '__file__', '') or ''), 'version': str(getattr(torch, '__version__', '') or ''), 'cuda_build': str(getattr(getattr(torch, 'version', None), 'cuda', '') or ''), 'cuda_available': bool(torch.cuda.is_available()), 'cuda_device_count': int(torch.cuda.device_count()) if hasattr(torch, 'cuda') else 0}
except Exception as e:
    details['torch_error'] = f'{type(e).__name__}: {e}'
try:
    if importlib.util.find_spec('paddle') is not None:
        import paddle
        details['paddle'] = {'file': str(getattr(paddle, '__file__', '') or ''), 'version': str(getattr(paddle, '__version__', '') or ''), 'cuda_compiled': bool(paddle.device.is_compiled_with_cuda())}
except Exception as e:
    details['paddle_error'] = f'{type(e).__name__}: {e}'
print(json.dumps({'missing': missing, 'target': target, 'sys_path_head': sys.path[:12], 'specs': specs, 'details': details}, ensure_ascii=False))
sys.exit(1 if missing else 0)
"""
    code = code.replace("__YSB_MODULES__", repr(modules))
    env_extra = runtime_subprocess_env(role or "", os.environ.copy()) if role else None
    result = _run([str(python), "-c", code], progress=progress, timeout=90, env_extra=env_extra)
    missing: list[str] = []
    data: dict[str, Any] = {}
    try:
        data = json.loads(str(result.get("stdout") or "{}").splitlines()[-1] if str(result.get("stdout") or "").strip() else "{}")
        missing = list(data.get("missing") or [])
    except Exception:
        if not result.get("ok"):
            missing = list(modules)
    runtime_errors: list[str] = []
    if role == "torch" and "torch" in modules and not missing:
        ok_cuda, msg = _torch_runtime_cuda_ok(data)
        if not ok_cuda:
            runtime_errors.append(msg)
    if role == "paddle" and "paddle" in modules and not missing:
        ok_cuda, msg = _paddle_runtime_cuda_ok(data)
        if not ok_cuda:
            runtime_errors.append(msg)
    if not result.get("ok") or missing or runtime_errors:
        merged_missing = list(missing)
        if runtime_errors:
            if role == "torch":
                merged_missing.append("torch_cuda_smoke_test")
            elif role == "paddle":
                merged_missing.append("paddle_cuda_smoke_test")
            data["runtime_errors"] = runtime_errors
        return {"ok": False, "missing": merged_missing, "result": result, "diagnostics": data}
    return {"ok": True, "missing": [], "result": result, "diagnostics": data}

def _cuda_capability_for_profile() -> float | None:
    try:
        from ysb.editions.local.cuda_runtime_probe import probe_nvidia_smi, _parse_float_version
        nvidia = probe_nvidia_smi()
        if not nvidia.get("available"):
            return None
        return _parse_float_version(str(nvidia.get("cuda_version") or ""))
    except Exception:
        return None


def choose_torch_profile() -> dict[str, str]:
    capability = _cuda_capability_for_profile()
    # Prefer modern PyTorch wheels when the driver can support them.  This is a
    # runtime profile label, not a guarantee; the post-install smoke test is the
    # source of truth.
    if capability is not None and capability >= 12.8:
        return {"id": "cu128", "index_url": "https://download.pytorch.org/whl/cu128"}
    if capability is not None and capability >= 12.6:
        return {"id": "cu126", "index_url": "https://download.pytorch.org/whl/cu126"}
    return {"id": "cu118", "index_url": "https://download.pytorch.org/whl/cu118"}


def choose_paddle_profile() -> dict[str, str]:
    capability = _cuda_capability_for_profile()
    if capability is not None and capability >= 12.9:
        return {"id": "cu129", "index_url": "https://www.paddlepaddle.org.cn/packages/stable/cu129/"}
    if capability is not None and capability >= 12.6:
        return {"id": "cu126", "index_url": "https://www.paddlepaddle.org.cn/packages/stable/cu126/"}
    return {"id": "cu118", "index_url": "https://www.paddlepaddle.org.cn/packages/stable/cu118/"}


def _write_marker(role: str, info: dict[str, Any]) -> None:
    import json

    root = runtime_env_folder(role)
    root.mkdir(parents=True, exist_ok=True)
    marker = root / RUNTIME_MARKER_NAME
    payload = {
        "role": role,
        "runtime_mode": runtime_mode(),
        "runtime_root": str(managed_runtime_root()),
        "created_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "system": {
            "platform": platform.platform(),
            "python_version": sys.version.split()[0],
        },
    }
    payload.update(info or {})
    marker.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")




def _runtime_target_ready(role: str) -> bool:
    target = runtime_env_folder(role)
    try:
        if not target.exists():
            return False
        if (target / RUNTIME_MARKER_NAME).exists():
            return True
        return any(target.iterdir())
    except Exception:
        return False

def ensure_runtime_root() -> Path:
    root = managed_runtime_root()
    root.mkdir(parents=True, exist_ok=True)
    readme = root / "README.txt"
    if not readme.exists():
        readme.write_text(
            "YSB Translator managed local runtime folder.\n"
            "This folder is created and managed from inside the program.\n"
            "Do not install packages here manually unless you know what you are doing.\n",
            encoding="utf-8",
        )
    return root


def _check_bootstrap_pip(python: Path, *, role: str | None = None, progress: ProgressCallback | None = None) -> dict[str, Any]:
    runner = _resolve_pip_runner(python, role=role, progress=progress)
    if runner.get("ok"):
        return {
            "ok": True,
            "mode": runner.get("mode"),
            "wheel": runner.get("wheel"),
            "result": runner.get("check_result"),
            "direct_result": runner.get("direct_check_result"),
        }
    return runner


def install_runtime(role: str, *, progress: ProgressCallback | None = None) -> dict[str, Any]:
    role_key = str(role or "").lower().strip()
    if role_key not in {"torch", "paddle"}:
        raise ValueError(f"unsupported runtime role: {role}")

    install_log_path = _new_install_log_path(role_key)
    original_progress = progress

    def _tee_progress(payload: Any) -> None:
        _append_install_log(install_log_path, "progress", payload=payload)
        if original_progress is not None:
            try:
                original_progress(payload)
            except Exception:
                try:
                    original_progress(str(payload))
                except Exception:
                    pass

    progress = _tee_progress

    runtime_root = ensure_runtime_root()
    _append_install_log(install_log_path, "install_begin", role=role_key, runtime_mode=runtime_mode(), runtime_root=str(runtime_root), app_root=str(_app_root()))
    target = runtime_env_folder(role_key)
    target_python = runtime_python_path(role_key)
    bootstrap = select_bootstrap_python(role_key)
    if bootstrap is None:
        msg = (
            "내장 설치용 Python을 찾지 못했습니다. EXE 배포판에서는 local_runtime_exe 안의 포터블 Python을 확인해 주세요."
            if runtime_mode() == "frozen_exe"
            else "현재 실행 Python을 찾지 못했습니다."
        )
        if progress:
            progress(msg)
        return {"ok": False, "error": "bootstrap_python_missing", "message": msg, "runtime_root": str(runtime_root)}

    target_python = bootstrap if _uses_target_runtime_install() else runtime_python_path(role_key)
    install_style = "pip_target" if _uses_target_runtime_install() else "venv"
    _append_install_log(install_log_path, "runtime_paths", role=role_key, install_style=install_style, runtime_root=str(runtime_root), target=str(target), target_python=str(target_python), bootstrap=str(bootstrap), python_candidates=[str(p) for p in runtime_python_candidates(role_key)])

    if progress:
        progress({"type": "stage", "current": 1, "total": 6, "text": f"Runtime mode: {runtime_mode()} / install: {install_style}"})
        progress(f"Runtime root: {runtime_root}")
        progress(f"Target: {target}")
        progress(f"Bootstrap Python: {bootstrap}")

    if _uses_target_runtime_install():
        # Frozen EXE path: never call python -m venv. The packaged Python is a
        # runtime/installer Python and may not include venv. Install packages
        # directly into the managed target folder and import them through
        # PYTHONPATH when probing/running workers.
        target.mkdir(parents=True, exist_ok=True)
        _append_install_log(install_log_path, "target_snapshot_initial", snapshot=_target_snapshot(target))
        _install_target_path_bootstrap(target_python, role_key, target, log_path=install_log_path)
        if progress:
            progress({"type": "stage", "current": 2, "total": 6, "text": "포터블 런타임 pip 확인 중..."})
        pip_runner = _resolve_pip_runner(bootstrap, role=role_key, progress=progress)
        if not pip_runner.get("ok"):
            return {
                "ok": False,
                "stage": "check_pip",
                "install_style": install_style,
                "result": pip_runner.get("result") or pip_runner,
                "pip_mode": pip_runner.get("mode"),
                "pip_wheel": pip_runner.get("wheel"),
                "runtime_root": str(runtime_root),
                "target": str(target),
                "python": str(bootstrap),
                "message": pip_runner.get("message") or "포터블 Python에서 pip를 실행할 수 없습니다. EXE 패키지의 _bootstrap_wheels 구성을 확인해 주세요.",
            }
        if progress:
            if pip_runner.get("mode") == "bundled_pip_wheel":
                progress(f"내장 pip wheel 사용: {pip_runner.get('wheel')}")
            else:
                progress("포터블 Python의 pip를 사용합니다.")
        pip_base = list(pip_runner.get("base") or [])
        install_env = pip_runner.get("env_extra")
    else:
        if not target_python.exists():
            target.parent.mkdir(parents=True, exist_ok=True)
            if progress:
                progress({"type": "stage", "current": 2, "total": 6, "text": "가상환경 생성 중..."})
            result = _run([str(bootstrap), "-m", "venv", str(target)], progress=progress, timeout=300)
            if not result.get("ok"):
                return {"ok": False, "stage": "create_venv", "install_style": install_style, "result": result, "runtime_root": str(runtime_root), "target": str(target)}
        else:
            if progress:
                progress("Existing runtime venv found. Package install/upgrade will continue in that folder.")

        pip_base = [str(target_python), "-m", "pip", "--disable-pip-version-check"]
        if progress:
            progress({"type": "stage", "current": 3, "total": 6, "text": "pip/setuptools/wheel 업데이트 중..."})
        result = _run(pip_base + ["install", "--progress-bar", "raw", "--upgrade", "pip", "setuptools", "wheel"], progress=progress, timeout=900)
        if not result.get("ok"):
            return {"ok": False, "stage": "upgrade_pip", "install_style": install_style, "result": result, "runtime_root": str(runtime_root), "target": str(target)}

    install_prefix: list[str] = []
    if not _uses_target_runtime_install():
        install_env = None
    if _uses_target_runtime_install():
        install_prefix = ["--target", str(target), "--upgrade", "--ignore-installed", "--no-user"]
        if install_env is None:
            install_env = runtime_subprocess_env(role_key, os.environ.copy())

    if role_key == "torch":
        profile = choose_torch_profile()
        if _uses_target_runtime_install():
            _purge_target_packages(target, ["torch", "torchvision", "torchaudio"], log_path=install_log_path, reason="before_torch_cuda_main_install")
        install_cmd = pip_base + ["install", "--progress-bar", "raw", "--no-warn-conflicts", "--prefer-binary"] + install_prefix + ["torch", "torchvision", "--index-url", profile["index_url"]]
    else:
        profile = choose_paddle_profile()
        if _uses_target_runtime_install():
            _purge_target_packages(target, ["paddle", "paddlepaddle", "paddlepaddle-gpu"], log_path=install_log_path, reason="before_paddle_gpu_main_install")
        install_cmd = pip_base + ["install", "--progress-bar", "raw", "--no-warn-conflicts", "--prefer-binary"] + install_prefix + ["paddlepaddle-gpu==3.2.2", "-i", profile["index_url"]]

    if progress:
        progress({"type": "stage", "current": 4, "total": 6, "text": f"{role_key} CUDA 패키지 다운로드/설치 중..."})
    _append_install_log(install_log_path, "target_snapshot_before_main_install", snapshot=_target_snapshot(target), command=install_cmd, env_pythonpath=(install_env or {}).get("PYTHONPATH"), env_target=(install_env or {}).get("YSB_MANAGED_RUNTIME_TARGET"))
    result = _run(install_cmd, progress=progress, timeout=3600, env_extra=install_env)
    _append_install_log(install_log_path, "target_snapshot_after_main_install", snapshot=_target_snapshot(target), result=_result_summary(result))
    if not result.get("ok"):
        return {"ok": False, "stage": "install_package", "install_style": install_style, "profile": profile, "result": result, "runtime_root": str(runtime_root), "target": str(target), "python": str(target_python), "install_log": str(install_log_path)}

    extra_result = None
    if role_key == "torch":
        if progress:
            progress({"type": "stage", "current": 5, "total": 6, "text": "Torch 계열 보조 패키지(LaMa/Manga OCR) 설치 중..."})
        # Do not let simple-lama-inpainting pull a CPU torch/torchvision wheel
        # from PyPI after the CUDA torch wheel has been installed.  Install the
        # support stack first, then install simple-lama-inpainting with --no-deps.
        support_cmd = pip_base + [
            "install", "--progress-bar", "raw", "--no-warn-conflicts", "--prefer-binary", "--upgrade",
        ] + install_prefix + [
            "pillow", "numpy", "opencv-python",
            "transformers", "huggingface-hub", "tokenizers", "regex", "requests", "tqdm", "packaging", "filelock", "pyyaml",
            "fugashi", "unidic-lite", "sentencepiece", "safetensors", "fire", "termcolor",
        ]
        _append_install_log(install_log_path, "target_snapshot_before_extra_support_install", snapshot=_target_snapshot(target), command=support_cmd)
        support_result = _run(support_cmd, progress=progress, timeout=1800, env_extra=install_env)
        _append_install_log(install_log_path, "target_snapshot_after_extra_support_install", snapshot=_target_snapshot(target), result=_result_summary(support_result))
        if not support_result.get("ok"):
            return {"ok": False, "stage": "install_lama_support_packages", "install_style": install_style, "profile": profile, "result": support_result, "runtime_root": str(runtime_root), "target": str(target), "python": str(target_python), "install_log": str(install_log_path)}
        simple_lama_cmd = pip_base + [
            "install", "--progress-bar", "raw", "--no-warn-conflicts", "--prefer-binary", "--upgrade", "--no-deps",
        ] + install_prefix + ["simple-lama-inpainting"]
        _append_install_log(install_log_path, "target_snapshot_before_simple_lama_nodeps_install", snapshot=_target_snapshot(target), command=simple_lama_cmd)
        extra_result = _run(simple_lama_cmd, progress=progress, timeout=900, env_extra=install_env)
        _append_install_log(install_log_path, "target_snapshot_after_simple_lama_nodeps_install", snapshot=_target_snapshot(target), result=_result_summary(extra_result))
        if not extra_result.get("ok"):
            return {"ok": False, "stage": "install_simple_lama_nodeps", "install_style": install_style, "profile": profile, "result": extra_result, "runtime_root": str(runtime_root), "target": str(target), "python": str(target_python), "install_log": str(install_log_path)}
    elif role_key == "paddle":
        if progress:
            progress({"type": "stage", "current": 5, "total": 6, "text": "PaddleOCR 패키지 설치 중..."})
        extra_cmd = pip_base + ["install", "--progress-bar", "raw", "--no-warn-conflicts", "--prefer-binary"] + install_prefix + ["paddleocr"]
        _append_install_log(install_log_path, "target_snapshot_before_extra_install", snapshot=_target_snapshot(target), command=extra_cmd)
        extra_result = _run(extra_cmd, progress=progress, timeout=1800, env_extra=install_env)
        _append_install_log(install_log_path, "target_snapshot_after_extra_install", snapshot=_target_snapshot(target), result=_result_summary(extra_result))
        if not extra_result.get("ok"):
            return {"ok": False, "stage": "install_paddleocr", "install_style": install_style, "profile": profile, "result": extra_result, "runtime_root": str(runtime_root), "target": str(target), "python": str(target_python), "install_log": str(install_log_path)}

    verify_modules = ["torch"] if role_key == "torch" else ["paddle", "paddleocr"]
    if role_key == "torch":
        verify_modules += ["simple_lama_inpainting", "PIL", "transformers", "fugashi", "unidic_lite", "sentencepiece", "safetensors"]
    if progress:
        progress({"type": "stage", "current": 6, "total": 6, "text": "설치 결과 검증 중..."})
    _install_target_path_bootstrap(target_python, role_key, target, log_path=install_log_path)
    verify_env = runtime_subprocess_env(role_key, os.environ.copy())
    _append_install_log(install_log_path, "verify_begin", python=str(target_python), modules=verify_modules, target=str(target), target_snapshot=_target_snapshot(target), env_pythonpath=verify_env.get("PYTHONPATH"), env_path_head=(verify_env.get("PATH") or "").split(os.pathsep)[:12])
    verify = _verify_runtime_modules(target_python, verify_modules, progress=progress, role=role_key)
    _append_install_log(install_log_path, "verify_done", ok=verify.get("ok"), missing=verify.get("missing"), diagnostics=verify.get("diagnostics"), result=_result_summary(verify.get("result") if isinstance(verify.get("result"), dict) else {}), target_snapshot=_target_snapshot(target))
    if not verify.get("ok"):
        return {
            "ok": False,
            "stage": "verify_runtime_modules",
            "install_style": install_style,
            "profile": profile,
            "missing": verify.get("missing", []),
            "result": verify.get("result"),
            "runtime_root": str(runtime_root),
            "target": str(target),
            "python": str(target_python),
            "message": "설치는 끝났지만 필수 모듈 검증에 실패했습니다: " + ", ".join(verify.get("missing") or []),
            "install_log": str(install_log_path),
            "verify_diagnostics": verify.get("diagnostics"),
        }
    if progress:
        progress("필수 모듈 검증 완료: " + ", ".join(verify_modules))
    _write_marker(role_key, {
        "profile": profile,
        "python": str(target_python),
        "target": str(target),
        "install_style": install_style,
        "extra_install_ok": bool(extra_result.get("ok")) if isinstance(extra_result, dict) else True,
        "verified_modules": verify_modules,
    })
    return {
        "ok": True,
        "role": role_key,
        "profile": profile,
        "runtime_mode": runtime_mode(),
        "install_style": install_style,
        "runtime_root": str(runtime_root),
        "target": str(target),
        "python": str(target_python),
        "install_log": str(install_log_path),
    }

def delete_runtime(role: str | None = None) -> dict[str, Any]:
    if role:
        target = runtime_env_folder(role)
    else:
        target = managed_runtime_root()
    if target.exists():
        shutil.rmtree(target)
        return {"ok": True, "deleted": str(target)}
    return {"ok": True, "deleted": "", "message": "target did not exist"}


def runtime_status() -> dict[str, Any]:
    root = managed_runtime_root()
    return {
        "runtime_mode": runtime_mode(),
        "runtime_root": str(root),
        "root_exists": root.exists(),
        "install_style": "pip_target" if _uses_target_runtime_install() else "venv",
        "torch_target": str(runtime_env_folder("torch")),
        "torch_target_exists": runtime_env_folder("torch").exists(),
        "torch_runtime_ready": _runtime_target_ready("torch"),
        "torch_python": str(runtime_python_path("torch")),
        "torch_python_exists": runtime_python_path("torch").exists(),
        "torch_exists": _runtime_target_ready("torch") if _uses_target_runtime_install() else runtime_python_path("torch").exists(),
        "paddle_target": str(runtime_env_folder("paddle")),
        "paddle_target_exists": runtime_env_folder("paddle").exists(),
        "paddle_runtime_ready": _runtime_target_ready("paddle"),
        "paddle_python": str(runtime_python_path("paddle")),
        "paddle_python_exists": runtime_python_path("paddle").exists(),
        "paddle_exists": _runtime_target_ready("paddle") if _uses_target_runtime_install() else runtime_python_path("paddle").exists(),
        "bootstrap_candidates": [str(p) for p in bootstrap_python_candidates()],
    }
