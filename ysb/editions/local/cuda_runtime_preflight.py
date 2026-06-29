# -*- coding: utf-8 -*-
"""Runtime preflight checks for local CUDA-backed YSB tasks.

This module is intentionally lightweight for the main UI process.  It only
launches the existing managed-runtime probe and returns UI-friendly decisions:

- PaddleOCR with explicit CUDA requires the Paddle GPU runtime.
- Manga OCR is Torch text detector + Manga OCR, and Local LaMa is Torch-backed; when Torch CUDA is missing, the UI
  warns before the long job starts instead of failing silently after model load.
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Any


@dataclass
class PreflightDecision:
    ok: bool = True
    needed: bool = False
    level: str = "ok"  # ok / info / warn / block
    task: str = ""
    engine: str = ""
    role: str = ""
    title_ko: str = "CUDA 사전검사"
    title_en: str = "CUDA preflight"
    message_ko: str = ""
    message_en: str = ""
    can_continue_cpu: bool = False
    report: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _cfg():
    from ysb.engine.manga_engine import Config
    return Config


def _norm(value: Any) -> str:
    return str(value or "").strip().lower()


def _is_explicit_cuda_device(value: Any) -> bool:
    return _norm(value) in {"cuda", "gpu", "nvidia"}


def _run_probe() -> dict[str, Any]:
    from ysb.editions.local.cuda_runtime_probe import run_full_probe
    return run_full_probe(write_report=True)


def _runtime_selected(report: dict[str, Any], role: str) -> dict[str, Any]:
    try:
        return dict(((report or {}).get(role) or {}).get("selected") or {})
    except Exception:
        return {}


def _runtime_error_summary(report: dict[str, Any], role: str) -> str:
    selected = _runtime_selected(report, role)
    if not selected:
        if role == "paddle":
            return "Paddle GPU 런타임 후보 Python을 찾지 못했습니다."
        return "Torch CUDA 런타임 후보 Python을 찾지 못했습니다."
    if selected.get("error"):
        return str(selected.get("error"))
    if role == "paddle":
        if not selected.get("installed"):
            return "paddle 모듈이 설치되어 있지 않습니다."
        if not selected.get("cuda_compiled"):
            return "설치된 Paddle이 CUDA 빌드가 아닙니다."
        if not selected.get("gpu_available"):
            return "Paddle에서 GPU 장치를 찾지 못했습니다."
        if not selected.get("smoke_ok"):
            return "Paddle GPU 스모크 테스트가 실패했습니다."
    else:
        if not selected.get("installed"):
            return "torch 모듈이 설치되어 있지 않습니다."
        if not selected.get("cuda_available"):
            return "Torch에서 CUDA를 사용할 수 없습니다."
        if not selected.get("smoke_ok"):
            return "Torch CUDA 스모크 테스트가 실패했습니다."
        imports = dict(selected.get("module_imports") or {})
        if imports and not imports.get("simple_lama_inpainting"):
            return "LOCAL LaMa 필수 패키지(simple-lama-inpainting)가 설치되어 있지 않습니다."
    return "상세 오류는 로컬 CUDA 진단 보고서를 확인해 주세요."


def _check_paddle_explicit_cuda(task: str, report: dict[str, Any]) -> PreflightDecision:
    ready = bool(((report or {}).get("paddle") or {}).get("gpu_ready"))
    if ready:
        return PreflightDecision(
            ok=True, needed=True, level="ok", task=task, engine="PaddleOCR", role="paddle",
            message_ko="Paddle GPU 런타임 사전검사를 통과했습니다.",
            message_en="Paddle GPU runtime preflight passed.",
            report=report,
        )
    reason = _runtime_error_summary(report, "paddle")
    return PreflightDecision(
        ok=False, needed=True, level="block", task=task, engine="PaddleOCR", role="paddle",
        title_ko="PaddleOCR CUDA 실행 불가",
        title_en="PaddleOCR CUDA is not available",
        message_ko=(
            "PaddleOCR이 CUDA 장치로 설정되어 있지만 Paddle GPU 런타임을 사용할 수 없습니다.\n\n"
            f"원인: {reason}\n\n"
            "작업을 시작하지 않았습니다. 로컬 CUDA 진단에서 Paddle GPU 런타임을 설치/진단해 주세요."
        ),
        message_en=(
            "PaddleOCR is set to CUDA, but the Paddle GPU runtime is not usable.\n\n"
            f"Reason: {reason}\n\n"
            "The job was not started. Install/diagnose the Paddle GPU runtime from Local CUDA Diagnosis."
        ),
        can_continue_cpu=False,
        report=report,
    )


def _check_torch_warn(task: str, engine: str, report: dict[str, Any]) -> PreflightDecision:
    ready = bool(((report or {}).get("torch") or {}).get("gpu_ready"))
    if ready:
        return PreflightDecision(
            ok=True, needed=True, level="ok", task=task, engine=engine, role="torch",
            message_ko="Torch CUDA 런타임 사전검사를 통과했습니다.",
            message_en="Torch CUDA runtime preflight passed.",
            report=report,
        )
    reason = _runtime_error_summary(report, "torch")
    return PreflightDecision(
        ok=True, needed=True, level="warn", task=task, engine=engine, role="torch",
        title_ko=f"{engine} CUDA 확인 필요",
        title_en=f"{engine} CUDA needs attention",
        message_ko=(
            f"{engine}은 Torch 계열 로컬 엔진입니다. 현재 관리 런타임의 Torch CUDA 검사가 통과하지 않았습니다.\n\n"
            f"원인: {reason}\n\n"
            "계속하면 CPU 또는 현재 실행 환경으로 진행될 수 있어 매우 느리거나 실패할 수 있습니다."
        ),
        message_en=(
            f"{engine} is a Torch-based local engine. The managed Torch CUDA runtime did not pass preflight.\n\n"
            f"Reason: {reason}\n\n"
            "Continuing may run on CPU/current environment, which can be very slow or fail."
        ),
        can_continue_cpu=True,
        report=report,
    )



def _check_torch_explicit_cuda(task: str, engine: str, report: dict[str, Any]) -> PreflightDecision:
    ready = bool(((report or {}).get("torch") or {}).get("gpu_ready"))
    if ready:
        return PreflightDecision(
            ok=True, needed=True, level="ok", task=task, engine=engine, role="torch",
            message_ko="Torch CUDA 런타임 사전검사를 통과했습니다.",
            message_en="Torch CUDA runtime preflight passed.",
            report=report,
        )
    reason = _runtime_error_summary(report, "torch")
    return PreflightDecision(
        ok=False, needed=True, level="block", task=task, engine=engine, role="torch",
        title_ko=f"{engine} CUDA 실행 불가",
        title_en=f"{engine} CUDA is not available",
        message_ko=(
            f"{engine}이 CUDA 장치로 설정되어 있지만 Torch CUDA 런타임을 사용할 수 없습니다.\n\n"
            f"원인: {reason}\n\n"
            "작업을 시작하지 않았습니다. 로컬 CUDA 진단에서 Torch CUDA 런타임을 설치/진단해 주세요."
        ),
        message_en=(
            f"{engine} is set to CUDA, but the Torch CUDA runtime is not usable.\n\n"
            f"Reason: {reason}\n\n"
            "The job was not started. Install/diagnose the Torch CUDA runtime from Local CUDA Diagnosis."
        ),
        can_continue_cpu=False,
        report=report,
    )

def check_task_preflight(task: str) -> PreflightDecision:
    """Return a decision for starting a local OCR/inpaint job.

    task: analyze / reanalyze / ocr / quick_ocr / inpaint
    """
    task_key = _norm(task)
    try:
        Config = _cfg()
        ocr_provider = _norm(getattr(Config, "OCR_PROVIDER", ""))
        inpaint_provider = _norm(getattr(Config, "INPAINT_PROVIDER", ""))
        paddle_device = _norm(getattr(Config, "LOCAL_PADDLE_OCR_DEVICE", getattr(Config, "LOCAL_PADDLE_MASK_DEVICE", "auto")))
        manga_device = _norm(getattr(Config, "LOCAL_MANGA_OCR_DEVICE", "auto"))
        # comic_text_detector mirrors the selected Local OCR engine device.
        # LOCAL Paddle keeps the historical storage key LOCAL_PADDLE_MASK_DEVICE;
        # LOCAL Manga uses LOCAL_MANGA_OCR_DEVICE.
        detector_device = manga_device if ocr_provider == "local_manga_ocr" else paddle_device
        lama_device = _norm(getattr(Config, "LOCAL_LAMA_DEVICE", "auto"))
    except Exception:
        return PreflightDecision(ok=True, needed=False, level="info", task=task_key)

    # OCR / analysis preflight.
    if task_key in {"analyze", "reanalyze", "ocr", "quick_ocr", "batch_analyze", "batch_reanalyze"}:
        if ocr_provider == "local_paddle_ocr":
            # LOCAL Paddle analysis is a hybrid path: comic_text_detector
            # (Torch) detects masks/regions first, then PaddleOCR recognizes
            # text inside those regions.  Therefore explicit CUDA on either
            # side needs the matching runtime check.
            if _is_explicit_cuda_device(detector_device):
                report = _run_probe()
                torch_decision = _check_torch_explicit_cuda(task_key, "Torch 텍스트 디텍터", report)
                if torch_decision.level in {"block", "warn"}:
                    return torch_decision
            if _is_explicit_cuda_device(paddle_device):
                report = _run_probe()
                return _check_paddle_explicit_cuda(task_key, report)
            return PreflightDecision(ok=True, needed=False, level="ok", task=task_key)
        if ocr_provider == "local_manga_ocr":
            report = _run_probe()
            if _is_explicit_cuda_device(manga_device) or _is_explicit_cuda_device(detector_device):
                return _check_torch_explicit_cuda(task_key, "Torch 텍스트 감지 + Manga OCR", report)
            return _check_torch_warn(task_key, "Torch 텍스트 감지 + Manga OCR", report)
        return PreflightDecision(ok=True, needed=False, level="ok", task=task_key)

    # Inpainting preflight.
    if task_key in {"inpaint", "batch_inpaint"}:
        if inpaint_provider == "local_lama":
            report = _run_probe()
            if _is_explicit_cuda_device(lama_device):
                return _check_torch_explicit_cuda(task_key, "LOCAL LaMa", report)
            return _check_torch_warn(task_key, "LOCAL LaMa", report)
        return PreflightDecision(ok=True, needed=False, level="ok", task=task_key)

    return PreflightDecision(ok=True, needed=False, level="ok", task=task_key)
