# -*- coding: utf-8 -*-
"""YSB API diagnostics.

This module is intentionally independent from the Qt UI layer.  It performs:
- API response tests: can the configured API receive a request and return a response?
- Program apply tests: can YSB parse/decode the response and save/read a result file?
- Unicode path probes: Korean/Japanese path handling for temp/apply files.

All secrets are masked in logs.
"""
from __future__ import annotations

import base64
import copy
import json
import os
import sys
import tempfile
import time
import traceback
import uuid
from dataclasses import asdict, is_dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple
from urllib.parse import urlparse

import cv2
import numpy as np
import requests

from ysb.core.cache_utils import get_cache_dir


def _now_stamp() -> str:
    return time.strftime("%Y%m%d_%H%M%S")


def _diag_log_dir() -> Path:
    p = get_cache_dir() / "api_diagnostics"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _mask_secret(value: Any) -> str:
    s = str(value or "")
    if not s:
        return ""
    if len(s) <= 8:
        return "*" * len(s)
    return s[:4] + "…" + s[-4:]


def _settings_dict(settings: Any) -> Dict[str, Any]:
    if isinstance(settings, dict):
        return dict(settings)
    if is_dataclass(settings):
        try:
            return asdict(settings)
        except Exception:
            pass
    out = {}
    for k in dir(settings):
        if k.startswith("_"):
            continue
        try:
            v = getattr(settings, k)
        except Exception:
            continue
        if callable(v):
            continue
        if isinstance(v, (str, int, float, bool, type(None))):
            out[k] = v
    return out


def _safe_settings_for_log(settings: Dict[str, Any]) -> Dict[str, Any]:
    out = {}
    for k, v in (settings or {}).items():
        lk = str(k).lower()
        if "key" in lk or "token" in lk or "secret" in lk:
            out[k] = _mask_secret(v)
        else:
            out[k] = v
    return out


def _write_log(kind: str, provider: str, result: Dict[str, Any], lines: List[str]) -> str:
    path = _diag_log_dir() / f"{kind}_{provider}_{_now_stamp()}_{uuid.uuid4().hex[:6]}.log"
    try:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines).rstrip() + "\n\n")
            f.write("===== RESULT JSON =====\n")
            json.dump(result, f, ensure_ascii=False, indent=2)
            f.write("\n")
    except Exception:
        return ""
    return str(path)


def _step(name: str, ok: bool, detail: str = "", **extra) -> Dict[str, Any]:
    d = {"name": str(name), "ok": bool(ok), "detail": str(detail or "")}
    d.update(extra)
    return d


def _sample_png_bytes(width=96, height=64, text="YSB") -> bytes:
    img = np.full((int(height), int(width), 3), 255, dtype=np.uint8)
    cv2.rectangle(img, (8, 8), (width - 8, height - 8), (230, 230, 230), 1)
    cv2.putText(img, str(text), (12, max(28, height // 2)), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 0, 0), 2, cv2.LINE_AA)
    ok, buf = cv2.imencode(".png", img)
    if not ok:
        raise ValueError("샘플 PNG 생성 실패")
    return bytes(buf.tobytes())


def _sample_inpaint_image_and_mask() -> Tuple[np.ndarray, np.ndarray]:
    img = np.full((96, 128, 3), 246, dtype=np.uint8)
    cv2.rectangle(img, (8, 8), (120, 88), (215, 215, 215), 1)
    cv2.rectangle(img, (40, 30), (92, 58), (255, 255, 255), -1)
    cv2.putText(img, "TEXT", (43, 50), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 2, cv2.LINE_AA)
    mask = np.zeros((96, 128), dtype=np.uint8)
    cv2.rectangle(mask, (38, 26), (96, 62), 255, -1)
    return img, mask


def _encode_png_b64_from_array(arr: np.ndarray) -> str:
    ok, buf = cv2.imencode(".png", np.ascontiguousarray(arr))
    if not ok:
        raise ValueError("PNG 인코딩 실패")
    return base64.b64encode(buf.tobytes()).decode("ascii")


def _unicode_path_probe() -> Dict[str, Any]:
    out = {"ok": False, "path": "", "cv2_imwrite_ok": False, "safe_write_ok": False, "read_ok": False, "error": ""}
    try:
        temp_root = Path(tempfile.gettempdir()) / f"YSB_API_TEST_한글_日本語_{uuid.uuid4().hex[:8]}"
        temp_root.mkdir(parents=True, exist_ok=True)
        out["path"] = str(temp_root)
        img = np.full((32, 48, 3), 255, dtype=np.uint8)
        cv2.putText(img, "OK", (4, 22), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 1, cv2.LINE_AA)
        cv2_path = temp_root / "cv2_테스트_日本語.png"
        safe_path = temp_root / "safe_테스트_日本語.png"
        try:
            out["cv2_imwrite_ok"] = bool(cv2.imwrite(str(cv2_path), img))
        except Exception as e:
            out["cv2_imwrite_error"] = repr(e)
        ok, buf = cv2.imencode(".png", img)
        if ok:
            buf.tofile(str(safe_path))
            out["safe_write_ok"] = bool(safe_path.exists() and safe_path.stat().st_size > 0)
        try:
            arr = np.fromfile(str(safe_path), np.uint8)
            img2 = cv2.imdecode(arr, cv2.IMREAD_COLOR)
            out["read_ok"] = img2 is not None and img2.size > 0
        except Exception as e:
            out["read_error"] = repr(e)
        out["ok"] = bool(out["safe_write_ok"] and out["read_ok"])
    except Exception as e:
        out["error"] = repr(e)
    return out


def _http_error_detail(response) -> str:
    status = getattr(response, "status_code", 0)
    text = str(getattr(response, "text", "") or "")[:1500]
    try:
        data = response.json()
        err = data.get("error", {}) if isinstance(data, dict) else {}
        msg = err.get("message") if isinstance(err, dict) else ""
        if msg:
            text = str(msg)
    except Exception:
        pass
    if int(status or 0) == 401:
        return f"HTTP 401 인증 실패: API Key/Token이 틀렸거나 해당 서버가 인증을 요구합니다. 원문: {text[:500]}"
    if int(status or 0) == 403:
        return f"HTTP 403 권한/결제/활성화 문제: API 권한, 결제, 프로젝트 활성화를 확인하세요. 원문: {text[:500]}"
    if int(status or 0) == 404:
        return f"HTTP 404: URL 또는 모델명을 찾지 못했습니다. 원문: {text[:500]}"
    if int(status or 0) == 429:
        return f"HTTP 429: 할당량/속도 제한 초과입니다. 원문: {text[:500]}"
    return f"HTTP {status}: {text[:700]}"


_PLACEHOLDER_SECRET_VALUES = {
    "your_api_key",
    "your api key",
    "your_key",
    "your_token",
    "api_key",
    "api token",
    "token",
    "secret",
    "sk-...",
    "r8_...",
    "paste_your_key_here",
    "여기에 입력",
    "여기에 api key 입력",
    "여기에 토큰 입력",
}


def _secret_missing_reason(value: Any, label: str = "API Key/Token") -> str:
    s = str(value or "").strip()
    if not s:
        return f"{label}이(가) 비어 있습니다."
    compact = s.strip().lower()
    if compact in _PLACEHOLDER_SECRET_VALUES:
        return f"{label}이(가) 예시값/placeholder로 보입니다. 실제 값을 입력해야 합니다."
    if "your_" in compact or "your-" in compact or "paste" in compact:
        return f"{label}이(가) 예시값/placeholder로 보입니다. 실제 값을 입력해야 합니다."
    if len(s) < 8:
        return f"{label}이(가) 너무 짧습니다. 값을 다시 확인하세요."
    return ""


def _value_missing_reason(value: Any, label: str) -> str:
    s = str(value or "").strip()
    if not s:
        return f"{label}이(가) 비어 있습니다."
    return ""


# ---------------------------------------------------------------------------
# Lightweight preflight helpers
# ---------------------------------------------------------------------------
def _url_missing_or_invalid_reason(value: Any, label: str, *, allow_local: bool = False) -> str:
    s = str(value or "").strip()
    if not s:
        return f"{label}이(가) 비어 있습니다."
    parsed = urlparse(s)
    if parsed.scheme not in ("http", "https"):
        return f"{label}은(는) http:// 또는 https:// 로 시작해야 합니다."
    if not parsed.netloc:
        return f"{label}의 호스트가 비어 있습니다."
    if not allow_local:
        host = (parsed.hostname or "").lower()
        if host in ("localhost", "127.0.0.1", "::1"):
            return f"{label}이(가) 로컬 주소입니다. 이 provider에서 의도한 값인지 확인하세요."
    return ""


def _append_required_url_step(steps: List[Dict[str, Any]], value: Any, label: str, *, stage: str = "URL_CHECK", allow_local: bool = False) -> str:
    reason = _url_missing_or_invalid_reason(value, label, allow_local=allow_local)
    if reason:
        steps.append(_step("필수값 검사", False, reason, stage=stage, request_sent=False))
    else:
        steps.append(_step("필수값 검사", True, f"{label} 형식 확인 완료", stage=stage, request_sent=False))
    return reason


def _auth_error_from_response(response) -> str:
    status = int(getattr(response, "status_code", 0) or 0)
    text = str(getattr(response, "text", "") or "")
    lower = text.lower()
    auth_markers = (
        "api key not valid",
        "invalid api key",
        "invalid key",
        "unauthorized",
        "permission denied",
        "forbidden",
        "authentication",
        "access denied",
        "api has not been used",
        "billing",
        "quota",
        "not have permission",
    )
    if status in (401, 403):
        return _http_error_detail(response)
    if status == 400 and any(m in lower for m in auth_markers):
        return _http_error_detail(response)
    return ""


def _models_url_from_openai_base(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""
    if base.endswith("/chat/completions"):
        base = base[: -len("/chat/completions")]
    if base.endswith("/completions"):
        base = base[: -len("/completions")]
    if base.endswith("/models"):
        return base
    return base + "/models"


def _summarize_models_payload(data: Any, model: str = "") -> Dict[str, Any]:
    out = {"model_count": None, "model_found": None, "first_models": []}
    names: List[str] = []
    try:
        if isinstance(data, dict):
            arr = data.get("data") or data.get("models") or data.get("results") or []
        elif isinstance(data, list):
            arr = data
        else:
            arr = []
        for item in arr or []:
            if isinstance(item, str):
                names.append(item)
            elif isinstance(item, dict):
                names.append(str(item.get("id") or item.get("name") or item.get("model") or ""))
        names = [x for x in names if x]
        out["model_count"] = len(names)
        out["first_models"] = names[:8]
        if model:
            out["model_found"] = str(model) in names if names else None
    except Exception:
        pass
    return out


def _test_openai_compatible_preflight(base_url: str, model: str, api_key: str = "", *, provider: str = "custom", timeout: int = 30, require_api_key: bool = True, strict_models_endpoint: bool = True) -> Dict[str, Any]:
    reason = _append_reason_only(_value_missing_reason(base_url, "Base URL"))
    if reason:
        raise ValueError(reason)
    reason = _value_missing_reason(model, "Model")
    if reason:
        raise ValueError(reason)
    if require_api_key:
        reason = _secret_missing_reason(api_key, "API Key")
        if reason:
            raise ValueError(reason)
    url = _models_url_from_openai_base(base_url)
    url_reason = _url_missing_or_invalid_reason(url, "Models URL", allow_local=(provider == "lm_studio"))
    if url_reason:
        raise ValueError(url_reason)
    headers = {"Accept": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    try:
        r = requests.get(url, headers=headers, timeout=timeout)
    except requests.RequestException as e:
        raise ValueError(f"연결 실패: {e}")
    if r.status_code != 200:
        auth = _auth_error_from_response(r)
        if auth:
            raise ValueError(auth)
        if strict_models_endpoint:
            raise ValueError(_http_error_detail(r))
        return {
            "url": url,
            "text": str(r.text)[:700],
            "json": {},
            "warning": f"/models 엔드포인트가 200을 반환하지 않았습니다. HTTP {r.status_code}. 일부 호환 서버는 models 조회를 지원하지 않을 수 있습니다.",
            "http_status": r.status_code,
        }
    try:
        data = r.json()
    except Exception:
        data = {"raw": str(r.text)[:1500]}
    summary = _summarize_models_payload(data, model)
    return {"url": url, "json": data, "text": str(r.text)[:700], **summary}


def _append_reason_only(reason: str) -> str:
    return str(reason or "")


def _test_gemini_model_preflight(api_key: str, model: str, *, label: str = "Gemini", timeout: int = 30) -> Dict[str, Any]:
    reason = _secret_missing_reason(api_key, f"{label} API Key")
    if reason:
        raise ValueError(reason)
    reason = _value_missing_reason(model, f"{label} 모델명")
    if reason:
        raise ValueError(reason)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}"
    r = requests.get(url, params={"key": api_key}, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    return {"url": url, "json": data, "text": str(r.text)[:700], "model_name": data.get("name", "") if isinstance(data, dict) else ""}


def _test_google_translate_preflight(api_key: str, *, target: str = "ko", timeout: int = 30) -> Dict[str, Any]:
    reason = _secret_missing_reason(api_key, "Google Translate API Key")
    if reason:
        raise ValueError(reason)
    url = "https://translation.googleapis.com/language/translate/v2/languages"
    r = requests.get(url, params={"key": api_key, "target": target or "ko"}, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    count = 0
    try:
        count = len(data.get("data", {}).get("languages", []) or [])
    except Exception:
        pass
    return {"url": url, "json": data, "text": str(r.text)[:700], "language_count": count}


def _test_google_vision_preflight(api_key: str, model: str = "DOCUMENT_TEXT_DETECTION", *, timeout: int = 30) -> Dict[str, Any]:
    reason = _secret_missing_reason(api_key, "Google Vision API Key")
    if reason:
        raise ValueError(reason)
    reason = _value_missing_reason(model, "Google Vision Model")
    if reason:
        raise ValueError(reason)
    url = "https://vision.googleapis.com/v1/images:annotate"
    # Deliberately send an empty request list: this validates endpoint/key without uploading an image.
    r = requests.post(url, params={"key": api_key}, json={"requests": []}, timeout=timeout)
    if r.status_code == 200:
        data = r.json()
        return {"url": url, "json": data, "text": str(r.text)[:700], "empty_request_supported": True}
    auth = _auth_error_from_response(r)
    if auth:
        raise ValueError(auth)
    # Some Google endpoints reject empty requests with 400. That still confirms the endpoint was reached without image upload.
    if r.status_code == 400:
        return {
            "url": url,
            "json": {},
            "text": str(r.text)[:700],
            "empty_request_supported": False,
            "warning": "이미지를 업로드하지 않는 빈 요청은 거부되었지만, 인증 오류 응답은 아닙니다. 실제 OCR은 본 작업에서 확인됩니다.",
            "http_status": r.status_code,
        }
    raise ValueError(_http_error_detail(r))


def _test_clova_preflight(url: str, secret: str) -> Dict[str, Any]:
    reason = _url_missing_or_invalid_reason(url, "CLOVA OCR Invoke URL")
    if reason:
        raise ValueError(reason)
    reason = _secret_missing_reason(secret, "CLOVA OCR Secret Key")
    if reason:
        raise ValueError(reason)
    return {
        "url": url,
        "json": {},
        "text": "CLOVA OCR은 이미지 업로드 없이 인증/응답을 확인할 수 있는 가벼운 엔드포인트가 없어서 URL/Secret 형식만 점검했습니다.",
        "request_sent": False,
    }


def _local_worker_probe(worker_name: str) -> Dict[str, Any]:
    root = Path(__file__).resolve().parents[2]
    path = root / "local_runtime" / worker_name
    return {
        "url": "",
        "json": {"worker_path": str(path), "exists": path.exists()},
        "text": f"LOCAL worker 확인: {path} exists={path.exists()}",
        "worker_path": str(path),
        "exists": path.exists(),
    }


def _translation_mock_apply_probe(provider: str) -> Dict[str, Any]:
    source = ["こんにちは。", "これはテストです。"]
    translated = ["안녕하세요.", "이것은 테스트입니다."]
    items = []
    for i, (src, dst) in enumerate(zip(source, translated), 1):
        items.append({"id": i, "original_text": src, "translated_text": dst})
    ok = len(items) == len(source) and all(x.get("translated_text") for x in items)
    return {"ok": ok, "provider": provider, "input_count": len(source), "output_count": len(items), "items": items}


def _ocr_mock_apply_probe(provider: str) -> Dict[str, Any]:
    item = {
        "id": 1,
        "original_text": "TEST",
        "translated_text": "",
        "rect": [10, 13, 62, 23],
        "vertices_list": [[[10, 13], [72, 13], [72, 36], [10, 36]]],
    }
    ok = bool(item["original_text"] and len(item["rect"]) == 4 and item["vertices_list"])
    return {"ok": ok, "provider": provider, "data_count": 1, "items": [item]}


def _inpaint_mock_apply_probe() -> Dict[str, Any]:
    img, _mask = _sample_inpaint_image_and_mask()
    b64 = _encode_png_b64_from_array(img)
    image_bytes = base64.b64decode(b64)
    save_probe = _save_and_read_image_probe(image_bytes, expected_shape=(int(img.shape[0]), int(img.shape[1])))
    return {"ok": bool(save_probe.get("ok")), "save_probe": save_probe, "result_kind": "mock_image"}


def _append_required_secret_step(steps: List[Dict[str, Any]], value: Any, label: str, *, stage: str = "REQUIRED_SECRET") -> str:
    reason = _secret_missing_reason(value, label)
    if reason:
        steps.append(_step("필수값 검사", False, reason, stage=stage, request_sent=False))
    else:
        steps.append(_step("필수값 검사", True, f"{label} 확인 완료", stage=stage, request_sent=False))
    return reason


def _append_required_value_step(steps: List[Dict[str, Any]], value: Any, label: str, *, stage: str = "REQUIRED_VALUE") -> str:
    reason = _value_missing_reason(value, label)
    if reason:
        steps.append(_step("필수값 검사", False, reason, stage=stage, request_sent=False))
    else:
        steps.append(_step("필수값 검사", True, f"{label} 확인 완료", stage=stage, request_sent=False))
    return reason


def _encode_png_data_uri_from_array(arr: np.ndarray) -> str:
    return "data:image/png;base64," + _encode_png_b64_from_array(arr)


def _replicate_headers(token: str) -> Dict[str, str]:
    return {
        "Authorization": f"Token {token}",
        "Content-Type": "application/json",
    }


STABLE_DIFFUSION_INPAINTING_DEFAULT_VERSION = "95b7223104132402a9ae91cc677285bc5eb997834bd2349fa486f53910fd68b3"


def _normalize_replicate_stable_model_ref(model_ref: str) -> Tuple[str, bool]:
    """Return a runnable Stable Diffusion Inpainting ref and whether it was auto-versioned."""
    raw = str(model_ref or "").strip()
    if raw == "stability-ai/stable-diffusion-inpainting":
        return f"{raw}:{STABLE_DIFFUSION_INPAINTING_DEFAULT_VERSION}", True
    return raw, False


def _parse_replicate_model_ref(model_ref: str) -> Tuple[str, str, str]:
    """Return (owner/name, version, model_ref).  version may be empty."""
    raw = str(model_ref or "").strip()
    if not raw:
        raise ValueError("Replicate 모델명이 비어 있습니다.")
    if ":" in raw:
        slug, version = raw.split(":", 1)
        return slug.strip(), version.strip(), raw
    return raw, "", raw


def _test_replicate_connection(token: str, *, timeout=45) -> Dict[str, Any]:
    reason = _secret_missing_reason(token, "Replicate API Token")
    if reason:
        raise ValueError(reason)
    url = "https://api.replicate.com/v1/models"
    r = requests.get(url, headers={"Authorization": f"Token {token}"}, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    count = 0
    try:
        count = len(data.get("results", []) or []) if isinstance(data, dict) else 0
    except Exception:
        count = 0
    return {"url": url, "json": data, "text": str(r.text)[:500], "result_count": count}


def _replicate_output_candidates(output: Any) -> List[str]:
    out: List[str] = []
    if output is None:
        return out
    if isinstance(output, str):
        out.append(output)
    elif isinstance(output, list):
        for x in output:
            out.extend(_replicate_output_candidates(x))
    elif isinstance(output, dict):
        preferred = (
            "image",
            "output",
            "result",
            "url",
            "uri",
            "file",
            "path",
        )
        for key in preferred:
            if key in output:
                out.extend(_replicate_output_candidates(output.get(key)))
        for v in output.values():
            if isinstance(v, (str, list, dict)):
                out.extend(_replicate_output_candidates(v))
    # Preserve order, remove duplicates.
    seen = set()
    uniq = []
    for x in out:
        sx = str(x or "").strip()
        if not sx or sx in seen:
            continue
        seen.add(sx)
        uniq.append(sx)
    return uniq


def _download_image_bytes_from_url_or_data(value: str, *, timeout=90) -> Tuple[bytes, str]:
    s = str(value or "").strip()
    if not s:
        raise ValueError("결과 이미지 URL/base64가 비어 있습니다.")
    if s.startswith("data:image") and "," in s:
        return base64.b64decode(s.split(",", 1)[1]), "data-uri"
    if s.startswith("http://") or s.startswith("https://"):
        r = requests.get(s, timeout=timeout)
        if r.status_code != 200:
            raise ValueError(_http_error_detail(r))
        ctype = str(r.headers.get("Content-Type", "") or "")
        data = bytes(r.content or b"")
        if not data:
            raise ValueError("결과 이미지 다운로드는 성공했지만 content가 비어 있습니다.")
        return data, f"url:{ctype}"
    # Some APIs return raw base64 without data-uri prefix.
    try:
        return base64.b64decode(s, validate=True), "base64"
    except Exception:
        pass
    raise ValueError("지원하지 않는 결과 이미지 형식입니다: " + s[:120])


def _extract_replicate_image_bytes(prediction: Dict[str, Any], *, timeout=90) -> Tuple[bytes, Dict[str, Any]]:
    output = prediction.get("output") if isinstance(prediction, dict) else None
    candidates = _replicate_output_candidates(output)
    errors: List[str] = []
    for cand in candidates:
        try:
            data, source = _download_image_bytes_from_url_or_data(cand, timeout=timeout)
            # Decode once here so a text URL or JSON blob does not look like success.
            _decode_image_bytes(data)
            return data, {"source": source, "candidate": cand[:500], "candidate_count": len(candidates)}
        except Exception as e:
            errors.append(str(e)[:500])
    raise ValueError("Replicate 결과에서 디코드 가능한 이미지 출력을 찾지 못했습니다. candidates=" + str(candidates[:5]) + " errors=" + str(errors[:3]))


def _run_replicate_inpaint_prediction(
    token: str,
    model_ref: str,
    provider: str,
    image_bgr: np.ndarray,
    mask: np.ndarray,
    *,
    prompt: str = "",
    wait_timeout: int = 90,
) -> Dict[str, Any]:
    reason = _secret_missing_reason(token, "Replicate API Token")
    if reason:
        raise ValueError(reason)
    slug, version, raw_ref = _parse_replicate_model_ref(model_ref)
    if "/" not in slug and not version:
        raise ValueError("Replicate 모델명은 owner/model 또는 owner/model:version 형식이어야 합니다.")

    image_uri = _encode_png_data_uri_from_array(image_bgr)
    mask_u8 = np.asarray(mask)
    if mask_u8.ndim == 3:
        mask_u8 = cv2.cvtColor(mask_u8, cv2.COLOR_BGR2GRAY)
    mask_u8 = np.where(mask_u8 > 0, 255, 0).astype(np.uint8)
    mask_uri = _encode_png_data_uri_from_array(mask_u8)

    input_payload: Dict[str, Any] = {
        "image": image_uri,
        "mask": mask_uri,
    }
    if str(provider or "") == "replicate_stable":
        input_payload["prompt"] = str(prompt or "remove text and restore the original background")

    headers = _replicate_headers(token)
    if version:
        url = "https://api.replicate.com/v1/predictions"
        payload = {"version": version, "input": input_payload}
    else:
        url = f"https://api.replicate.com/v1/models/{slug}/predictions"
        payload = {"input": input_payload}

    r = requests.post(url, headers=headers, json=payload, timeout=90)
    if r.status_code not in (200, 201):
        raise ValueError(_http_error_detail(r))
    pred = r.json()
    pred_id = pred.get("id") if isinstance(pred, dict) else ""
    get_url = ""
    try:
        get_url = pred.get("urls", {}).get("get", "") if isinstance(pred.get("urls"), dict) else ""
    except Exception:
        get_url = ""

    status = str(pred.get("status") or "") if isinstance(pred, dict) else ""
    started = time.time()
    polls = 0
    wait_timeout = max(15, min(240, int(wait_timeout or 90)))
    last_pred = pred
    while status in ("starting", "processing", "queued") and (time.time() - started) < wait_timeout:
        polls += 1
        time.sleep(2.0)
        if not get_url:
            break
        gr = requests.get(get_url, headers={"Authorization": f"Token {token}"}, timeout=45)
        if gr.status_code != 200:
            raise ValueError(_http_error_detail(gr))
        last_pred = gr.json()
        status = str(last_pred.get("status") or "")

    if status in ("starting", "processing", "queued"):
        raise ValueError(f"Replicate prediction 대기 시간 초과: status={status}, id={pred_id}, wait_timeout={wait_timeout}s")
    if status != "succeeded":
        err = ""
        try:
            err = str(last_pred.get("error") or last_pred.get("logs") or "")[:1000]
        except Exception:
            pass
        raise ValueError(f"Replicate prediction 실패: status={status}, id={pred_id}, error={err}")

    image_bytes, output_info = _extract_replicate_image_bytes(last_pred)
    return {
        "api": "predictions",
        "url": url,
        "get_url": get_url,
        "model_ref": raw_ref,
        "model_slug": slug,
        "version": version,
        "prediction_id": pred_id,
        "status": status,
        "polls": polls,
        "output_info": output_info,
        "image_bytes": image_bytes,
        "json_excerpt": json.dumps({k: v for k, v in last_pred.items() if k != "output"}, ensure_ascii=False)[:1500],
    }


def _extract_text_from_chat_completion(data: Dict[str, Any]) -> str:
    try:
        choices = data.get("choices", [])
        if choices:
            msg = choices[0].get("message", {})
            return str(msg.get("content", "") or "")
    except Exception:
        pass
    return ""


def _test_openai_compatible(base_url: str, model: str, api_key: str, *, provider="custom", timeout=45) -> Dict[str, Any]:
    if not base_url:
        raise ValueError("Base URL이 비어 있습니다.")
    if not model:
        raise ValueError("Model이 비어 있습니다.")
    url = base_url.rstrip("/")
    if not url.endswith("/chat/completions"):
        url += "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    payload = {
        "model": model,
        "messages": [{"role": "user", "content": "Reply with exactly: OK"}],
        "temperature": 0,
        "max_tokens": 16,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    text = _extract_text_from_chat_completion(data)
    if not text:
        raise ValueError("응답은 왔지만 choices[0].message.content가 비어 있습니다.")
    return {"url": url, "text": text[:500], "json": data}


def _test_gemini_text(api_key: str, model: str, timeout=45) -> Dict[str, Any]:
    if not api_key:
        raise ValueError("Gemini API Key가 비어 있습니다.")
    if not model:
        raise ValueError("Gemini 모델명이 비어 있습니다.")
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"contents": [{"role": "user", "parts": [{"text": "Reply with exactly: OK"}]}]}
    r = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", []) if isinstance(data, dict) else []
    text = "".join(str(p.get("text", "")) for p in parts if isinstance(p, dict))
    if not text:
        raise ValueError("Gemini 응답은 왔지만 텍스트 part가 비어 있습니다.")
    return {"url": url, "text": text[:500], "json": data}


def extract_gemini_image_bytes(data: Any) -> Tuple[bytes | None, List[str], str]:
    """Extract first image bytes from Interactions or generateContent response."""
    notes: List[str] = []
    source = ""
    if not isinstance(data, dict):
        return None, notes, source

    # Interactions API: steps[].content[].type == image
    for step in data.get("steps", []) or []:
        if not isinstance(step, dict):
            continue
        if step.get("type") and step.get("type") != "model_output":
            continue
        for block in step.get("content", []) or []:
            if not isinstance(block, dict):
                continue
            if block.get("type") == "text" and block.get("text"):
                notes.append(str(block.get("text") or ""))
            if block.get("type") == "image" and block.get("data"):
                try:
                    return base64.b64decode(str(block.get("data"))), notes, "interactions.steps.content.image"
                except Exception as e:
                    notes.append(f"image base64 decode error: {e!r}")

    # GenerateContent: candidates[].content.parts[].inlineData
    for cand in data.get("candidates", []) or []:
        if not isinstance(cand, dict):
            continue
        content = cand.get("content", {}) if isinstance(cand.get("content", {}), dict) else {}
        for part in content.get("parts", []) or []:
            if not isinstance(part, dict):
                continue
            if part.get("text"):
                notes.append(str(part.get("text") or ""))
            inline = part.get("inlineData") or part.get("inline_data") or {}
            if isinstance(inline, dict) and inline.get("data"):
                try:
                    return base64.b64decode(str(inline.get("data"))), notes, "generateContent.inlineData"
                except Exception as e:
                    notes.append(f"inlineData decode error: {e!r}")

    # Other defensive shapes used by some SDK wrappers.
    for key in ("generatedImages", "generated_images", "images"):
        arr = data.get(key)
        if not isinstance(arr, list):
            continue
        for item in arr:
            if not isinstance(item, dict):
                continue
            b64 = item.get("data") or item.get("imageBytes") or item.get("image_bytes")
            if b64:
                try:
                    return base64.b64decode(str(b64)), notes, key
                except Exception as e:
                    notes.append(f"{key} decode error: {e!r}")
    return None, notes, source


def _gemini_image_model_normalize(model: str) -> str:
    m = str(model or "").strip()
    if not m:
        return "gemini-3.1-flash-image"
    old = {
        "gemini-2.5-flash-image",
        "gemini-2.5-flash-image-preview",
        "gemini-2.0-flash-exp-image-generation",
    }
    if m in old:
        return "gemini-3.1-flash-image"
    return m


def _gemini_inpaint_prompt(prompt: str) -> str:
    base = str(prompt or "").strip() or (
        "Remove the text only inside the white mask area and reconstruct the original manga background. "
        "Keep all characters, panel borders, screentones, line art, and unmasked areas unchanged. "
        "Return only the edited full image."
    )
    return (
        base
        + "\n\nYou are given two images. Image 1 is the source manga page. Image 2 is a binary mask. "
        + "White pixels in the mask are the exact area to edit/remove. Black pixels must remain unchanged. "
        + "Return one edited full-size image only. Do not return a crop."
    )


def call_gemini_inpaint_api(api_key: str, model: str, image_bgr: np.ndarray, mask: np.ndarray, prompt: str, *, timeout=180) -> Dict[str, Any]:
    if not api_key:
        raise ValueError("Gemini API Key가 비어 있습니다.")
    model = _gemini_image_model_normalize(model)
    instruction = _gemini_inpaint_prompt(prompt)

    image_b64 = _encode_png_b64_from_array(image_bgr)
    mask_u8 = np.asarray(mask)
    if mask_u8.ndim == 3:
        mask_u8 = cv2.cvtColor(mask_u8, cv2.COLOR_BGR2GRAY)
    mask_u8 = np.where(mask_u8 > 0, 255, 0).astype(np.uint8)
    mask_b64 = _encode_png_b64_from_array(mask_u8)

    attempts = []

    def _interactions():
        url = "https://generativelanguage.googleapis.com/v1beta/interactions"
        payload = {
            "model": model,
            "input": [
                {"type": "image", "mime_type": "image/png", "data": image_b64},
                {"type": "image", "mime_type": "image/png", "data": mask_b64},
                {"type": "text", "text": instruction},
            ],
            "response_format": [{"type": "image"}, {"type": "text"}],
        }
        r = requests.post(url, headers={"x-goog-api-key": api_key, "Content-Type": "application/json"}, json=payload, timeout=timeout)
        if r.status_code != 200:
            raise ValueError(_http_error_detail(r))
        data = r.json()
        img_bytes, notes, source = extract_gemini_image_bytes(data)
        if not img_bytes:
            raise ValueError("Interactions 응답에서 이미지 데이터를 찾지 못했습니다. " + " ".join(notes)[:500])
        return {"api": "interactions", "url": url, "model": model, "image_bytes": img_bytes, "notes": notes, "source": source, "json_excerpt": str(data)[:1500]}

    def _generate_content():
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
        payload = {
            "contents": [
                {
                    "role": "user",
                    "parts": [
                        {"text": instruction},
                        {"inlineData": {"mimeType": "image/png", "data": image_b64}},
                        {"inlineData": {"mimeType": "image/png", "data": mask_b64}},
                    ],
                }
            ],
            "generationConfig": {
                "temperature": 0.1,
                "responseModalities": ["IMAGE", "TEXT"],
            },
        }
        r = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
        if r.status_code != 200:
            raise ValueError(_http_error_detail(r))
        data = r.json()
        img_bytes, notes, source = extract_gemini_image_bytes(data)
        if not img_bytes:
            raise ValueError("generateContent 응답에서 이미지 데이터를 찾지 못했습니다. " + " ".join(notes)[:500])
        return {"api": "generateContent", "url": url, "model": model, "image_bytes": img_bytes, "notes": notes, "source": source, "json_excerpt": str(data)[:1500]}

    # Current image-editing docs use Interactions API.  Try it first, then legacy
    # generateContent as a compatibility fallback.
    for name, func in (("interactions", _interactions), ("generateContent", _generate_content)):
        try:
            out = func()
            out["attempts"] = attempts
            return out
        except Exception as e:
            attempts.append({"api": name, "error": str(e)[:800]})
            continue
    raise ValueError("Gemini 인페인팅 API가 모두 실패했습니다. " + " | ".join(f"{a['api']}: {a['error']}" for a in attempts))


def _decode_image_bytes(image_bytes: bytes) -> np.ndarray:
    arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(arr, cv2.IMREAD_COLOR)
    if img is None or img.size <= 0:
        raise ValueError("이미지 bytes 디코드 실패")
    return img


def _save_and_read_image_probe(image_bytes: bytes, expected_shape: Tuple[int, int] | None = None) -> Dict[str, Any]:
    out = {
        "ok": False,
        "path": "",
        "decoded": False,
        "saved": False,
        "read_back": False,
        "shape": "",
        "same_size_as_input": None,
        "expected_hw": list(expected_shape) if expected_shape else None,
        "error": "",
    }
    try:
        img = _decode_image_bytes(image_bytes)
        out["decoded"] = True
        out["shape"] = str(getattr(img, "shape", ""))
        if expected_shape:
            try:
                out["same_size_as_input"] = (int(img.shape[0]) == int(expected_shape[0]) and int(img.shape[1]) == int(expected_shape[1]))
            except Exception:
                out["same_size_as_input"] = False
        temp_root = Path(tempfile.gettempdir()) / f"YSB_APPLY_TEST_한글_日本語_{uuid.uuid4().hex[:8]}"
        temp_root.mkdir(parents=True, exist_ok=True)
        path = temp_root / "result_적용_日本語.png"
        ok, buf = cv2.imencode(".png", img)
        if not ok:
            raise ValueError("결과 이미지 PNG 재인코딩 실패")
        buf.tofile(str(path))
        out["saved"] = path.exists() and path.stat().st_size > 0
        out["path"] = str(path)
        read = cv2.imdecode(np.fromfile(str(path), np.uint8), cv2.IMREAD_COLOR)
        out["read_back"] = read is not None and read.size > 0
        out["ok"] = bool(out["decoded"] and out["saved"] and out["read_back"])
    except Exception as e:
        out["error"] = repr(e)
    return out



# ---------------------------------------------------------------------------
# Practical test asset helpers
# ---------------------------------------------------------------------------
def _project_root_from_module() -> Path:
    try:
        return Path(__file__).resolve().parents[2]
    except Exception:
        return Path.cwd()


def _runtime_root_candidates() -> List[Path]:
    roots: List[Path] = []
    try:
        meipass = getattr(sys, "_MEIPASS", "")
        if meipass:
            roots.append(Path(meipass))
    except Exception:
        pass
    roots.append(_project_root_from_module())
    try:
        roots.append(Path.cwd())
    except Exception:
        pass
    unique: List[Path] = []
    seen = set()
    for root in roots:
        try:
            key = str(root.resolve())
        except Exception:
            key = str(root)
        if key not in seen:
            unique.append(root)
            seen.add(key)
    return unique


def _api_test_assets_dir() -> Path:
    rels = [
        Path("ysb") / "test_assets" / "api_diagnostics",
        Path("test_assets") / "api_diagnostics",
    ]
    checked: List[str] = []
    for root in _runtime_root_candidates():
        for rel in rels:
            cand = root / rel
            checked.append(str(cand))
            if cand.exists():
                return cand
    raise FileNotFoundError("API 실전 테스트 샘플 폴더를 찾지 못했습니다. 확인 경로: " + " | ".join(checked[:8]))


def _read_json_file(path: Path) -> Dict[str, Any]:
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    return data if isinstance(data, dict) else {}


def _load_practical_sample(lang: str = "ja") -> Dict[str, Any]:
    lang = str(lang or "ja").lower()
    assets = _api_test_assets_dir()
    image_path = assets / "images" / f"{lang}_sample.png"
    mask_path = assets / "masks" / f"{lang}_sample_mask.png"
    meta_path = assets / "meta" / f"{lang}_sample.json"
    if not image_path.exists():
        raise FileNotFoundError(f"샘플 이미지가 없습니다: {image_path}")
    if not mask_path.exists():
        raise FileNotFoundError(f"샘플 마스크가 없습니다: {mask_path}")
    meta = _read_json_file(meta_path) if meta_path.exists() else {"key": lang, "lines": []}
    img = cv2.imdecode(np.fromfile(str(image_path), np.uint8), cv2.IMREAD_COLOR)
    mask = cv2.imdecode(np.fromfile(str(mask_path), np.uint8), cv2.IMREAD_GRAYSCALE)
    if img is None or img.size <= 0:
        raise ValueError(f"샘플 이미지를 읽지 못했습니다: {image_path}")
    if mask is None or mask.size <= 0:
        raise ValueError(f"샘플 마스크를 읽지 못했습니다: {mask_path}")
    ok1, img_buf = cv2.imencode(".png", img)
    ok2, mask_buf = cv2.imencode(".png", mask)
    if not ok1 or not ok2:
        raise ValueError("샘플 이미지/마스크 PNG 인코딩 실패")
    return {
        "lang": lang,
        "assets_dir": str(assets),
        "image_path": str(image_path),
        "mask_path": str(mask_path),
        "meta_path": str(meta_path),
        "meta": meta,
        "image_bgr": img,
        "mask": mask,
        "image_bytes": bytes(img_buf.tobytes()),
        "mask_bytes": bytes(mask_buf.tobytes()),
        "shape": list(img.shape),
        "lines": list(meta.get("lines") or []),
    }


def _diagnostic_artifact_dir(provider: str, category: str, test_kind: str) -> Path:
    root = _diag_log_dir() / "artifacts" / f"{_now_stamp()}_{category}_{provider}_{test_kind}_{uuid.uuid4().hex[:6]}"
    root.mkdir(parents=True, exist_ok=True)
    return root


def _safe_write_image(path: Path, image: np.ndarray) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    ok, buf = cv2.imencode(path.suffix or ".png", np.ascontiguousarray(image))
    if not ok:
        return False
    buf.tofile(str(path))
    return bool(path.exists() and path.stat().st_size > 0)


def _write_bytes(path: Path, data: bytes) -> bool:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "wb") as f:
        f.write(data or b"")
    return bool(path.exists() and path.stat().st_size > 0)


def _save_practical_assets(artifact_dir: Path, sample: Dict[str, Any], *, output_bytes: bytes | None = None, overlay_bgr: np.ndarray | None = None) -> Dict[str, Any]:
    out: Dict[str, Any] = {"artifact_dir": str(artifact_dir)}
    try:
        input_path = artifact_dir / "input.png"
        mask_path = artifact_dir / "mask.png"
        in_img = sample["image_bgr"]
        out["input_shape"] = str(getattr(in_img, "shape", ""))
        out["input_hw"] = [int(in_img.shape[0]), int(in_img.shape[1])] if hasattr(in_img, "shape") and len(in_img.shape) >= 2 else None
        out["input_saved"] = _safe_write_image(input_path, in_img)
        out["mask_saved"] = _safe_write_image(mask_path, sample["mask"])
        out["input_path"] = str(input_path)
        out["mask_path"] = str(mask_path)
        if output_bytes:
            output_path = artifact_dir / "output.png"
            img = _decode_image_bytes(output_bytes)
            out["output_decoded"] = True
            out["output_shape"] = str(getattr(img, "shape", ""))
            out["output_hw"] = [int(img.shape[0]), int(img.shape[1])] if hasattr(img, "shape") and len(img.shape) >= 2 else None
            same_size = bool(int(img.shape[0]) == int(sample["image_bgr"].shape[0]) and int(img.shape[1]) == int(sample["image_bgr"].shape[1]))
            out["same_size_as_input"] = same_size
            out["output_saved"] = _safe_write_image(output_path, img)
            out["output_path"] = str(output_path)
            if not same_size:
                resized_path = artifact_dir / "output_resized.png"
                resized = cv2.resize(img, (int(sample["image_bgr"].shape[1]), int(sample["image_bgr"].shape[0])), interpolation=cv2.INTER_AREA)
                out["resized_output_saved"] = _safe_write_image(resized_path, resized)
                out["resized_output_path"] = str(resized_path)
                out["resized_output_shape"] = str(getattr(resized, "shape", ""))
        if overlay_bgr is not None:
            overlay_path = artifact_dir / "ocr_overlay.png"
            out["overlay_saved"] = _safe_write_image(overlay_path, overlay_bgr)
            out["overlay_path"] = str(overlay_path)
    except Exception as e:
        out["error"] = repr(e)
    return out


def _draw_ocr_overlay(sample: Dict[str, Any], items: List[Dict[str, Any]]) -> np.ndarray:
    img = np.ascontiguousarray(sample["image_bgr"].copy())
    for idx, item in enumerate(items or [], 1):
        try:
            rect = item.get("rect") or [0, 0, 0, 0]
            x, y, w, h = [int(round(float(v))) for v in rect[:4]]
            cv2.rectangle(img, (x, y), (x + w, y + h), (0, 200, 255), 3)
            cv2.putText(img, str(idx), (x, max(20, y - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 200, 255), 2, cv2.LINE_AA)
        except Exception:
            continue
    return img


def _vertices_to_rect(vertices: Any) -> Tuple[List[int], List[List[int]]]:
    pts: List[List[int]] = []
    try:
        for v in vertices or []:
            if isinstance(v, dict):
                pts.append([int(round(float(v.get("x", 0)))), int(round(float(v.get("y", 0))))])
            elif isinstance(v, (list, tuple)) and len(v) >= 2:
                pts.append([int(round(float(v[0]))), int(round(float(v[1])))])
    except Exception:
        pts = []
    if not pts:
        return [0, 0, 0, 0], []
    xs = [p[0] for p in pts]
    ys = [p[1] for p in pts]
    x1, y1, x2, y2 = min(xs), min(ys), max(xs), max(ys)
    return [x1, y1, max(1, x2 - x1), max(1, y2 - y1)], pts


def _parse_clova_ocr_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    try:
        images = data.get("images") or []
        for image in images:
            for field in image.get("fields") or []:
                text = str(field.get("inferText") or "")
                vertices = (((field.get("boundingPoly") or {}).get("vertices")) or [])
                rect, pts = _vertices_to_rect(vertices)
                if text:
                    items.append({"original_text": text, "rect": rect, "vertices_list": [pts] if pts else [], "confidence": field.get("inferConfidence")})
    except Exception:
        pass
    return items


def _parse_google_vision_items(data: Dict[str, Any]) -> List[Dict[str, Any]]:
    items: List[Dict[str, Any]] = []
    try:
        responses = data.get("responses") or []
        for resp in responses:
            annotations = resp.get("textAnnotations") or []
            # textAnnotations[0] is full text. Use individual annotations after that when present.
            source = annotations[1:] if len(annotations) > 1 else annotations[:1]
            for ann in source:
                text = str(ann.get("description") or "").strip()
                vertices = (((ann.get("boundingPoly") or {}).get("vertices")) or [])
                rect, pts = _vertices_to_rect(vertices)
                if text:
                    items.append({"original_text": text, "rect": rect, "vertices_list": [pts] if pts else [], "confidence": None})
    except Exception:
        pass
    return items


def _run_clova_ocr_practical(url: str, secret: str, sample: Dict[str, Any], *, timeout=60) -> Dict[str, Any]:
    reason = _url_missing_or_invalid_reason(url, "CLOVA OCR Invoke URL")
    if reason:
        raise ValueError(reason)
    reason = _secret_missing_reason(secret, "CLOVA OCR Secret Key")
    if reason:
        raise ValueError(reason)
    payload = {
        "version": "V2",
        "requestId": uuid.uuid4().hex,
        "timestamp": int(time.time() * 1000),
        "images": [{"format": "png", "name": f"ysb_{sample['lang']}_sample", "data": base64.b64encode(sample["image_bytes"]).decode("ascii")}],
    }
    headers = {"Content-Type": "application/json", "X-OCR-SECRET": secret}
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    items = _parse_clova_ocr_items(data)
    return {
        "url": url,
        "json": data,
        "text": str(r.text)[:1000],
        "items": items,
        "detected_count": len(items),
        "first_text": items[0].get("original_text", "") if items else "",
    }


def _run_google_vision_ocr_practical(api_key: str, model: str, sample: Dict[str, Any], *, language_hints: str = "", timeout=60) -> Dict[str, Any]:
    reason = _secret_missing_reason(api_key, "Google Vision API Key")
    if reason:
        raise ValueError(reason)
    reason = _value_missing_reason(model, "Google Vision Model")
    if reason:
        raise ValueError(reason)
    url = "https://vision.googleapis.com/v1/images:annotate"
    hints = [x.strip() for x in str(language_hints or "").split(",") if x.strip()]
    request = {
        "image": {"content": base64.b64encode(sample["image_bytes"]).decode("ascii")},
        "features": [{"type": str(model or "DOCUMENT_TEXT_DETECTION")}],
    }
    if hints:
        request["imageContext"] = {"languageHints": hints}
    r = requests.post(url, params={"key": api_key}, json={"requests": [request]}, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    items = _parse_google_vision_items(data)
    return {
        "url": url,
        "json": data,
        "text": str(r.text)[:1000],
        "items": items,
        "detected_count": len(items),
        "first_text": items[0].get("original_text", "") if items else "",
    }


def _build_translation_prompt(lines: List[str], target: str = "ko") -> str:
    src = "\n".join(f"{i+1}. {line}" for i, line in enumerate(lines or []))
    target = str(target or "ko")
    return (
        "Translate the following numbered lines into the target language.\n"
        f"Target language: {target}\n"
        "Return only the translated numbered lines, preserving the numbers.\n\n"
        f"{src}"
    )


def _parse_translated_lines(text: str, expected_count: int) -> List[str]:
    raw_lines = [x.strip() for x in str(text or "").splitlines() if x.strip()]
    out: List[str] = []
    for line in raw_lines:
        s = line.strip()
        # Remove common numeric prefixes like 1. / 1) / [1]
        for prefix in (".", ")", "]", "：", ":"):
            pass
        import re
        s = re.sub(r"^\s*[\[\(]?\d+[\]\)\.\:\：\-]\s*", "", s).strip()
        if s:
            out.append(s)
    if len(out) == expected_count:
        return out
    if expected_count == 1 and str(text or "").strip():
        return [str(text or "").strip()]
    return out


def _run_openai_compatible_translation_practical(base_url: str, model: str, api_key: str, lines: List[str], *, provider: str, target: str = "ko", require_api_key: bool = True, timeout=90) -> Dict[str, Any]:
    reason = _url_missing_or_invalid_reason(base_url, "Base URL", allow_local=(provider == "lm_studio"))
    if reason:
        raise ValueError(reason)
    reason = _value_missing_reason(model, "Model")
    if reason:
        raise ValueError(reason)
    if require_api_key:
        reason = _secret_missing_reason(api_key, "API Key")
        if reason:
            raise ValueError(reason)
    base = str(base_url or "").rstrip("/")
    if base.endswith("/chat/completions"):
        url = base
    else:
        url = base + "/chat/completions"
    headers = {"Content-Type": "application/json"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    prompt = _build_translation_prompt(lines, target)
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a precise manga translation test engine."},
            {"role": "user", "content": prompt},
        ],
        "temperature": 0.1,
    }
    r = requests.post(url, headers=headers, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    content = ""
    try:
        content = data["choices"][0]["message"]["content"]
    except Exception:
        content = str(data)[:1000]
    outputs = _parse_translated_lines(content, len(lines))
    return {
        "url": url,
        "json": data,
        "text": content,
        "input_count": len(lines),
        "output_count": len(outputs),
        "outputs": outputs,
        "pairs": [{"src": s, "dst": outputs[i] if i < len(outputs) else ""} for i, s in enumerate(lines)],
    }


def _run_google_translate_practical(api_key: str, lines: List[str], *, target: str = "ko", timeout=60) -> Dict[str, Any]:
    reason = _secret_missing_reason(api_key, "Google Translate API Key")
    if reason:
        raise ValueError(reason)
    url = "https://translation.googleapis.com/language/translate/v2"
    params = {"key": api_key}
    payload = {"q": lines, "target": target or "ko", "format": "text"}
    r = requests.post(url, params=params, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    translations = (((data.get("data") or {}).get("translations")) or [])
    outputs = [str(x.get("translatedText") or "") for x in translations if isinstance(x, dict)]
    return {
        "url": url,
        "json": data,
        "text": "\n".join(outputs),
        "input_count": len(lines),
        "output_count": len(outputs),
        "outputs": outputs,
        "pairs": [{"src": s, "dst": outputs[i] if i < len(outputs) else ""} for i, s in enumerate(lines)],
    }


def _run_gemini_text_practical(api_key: str, model: str, lines: List[str], *, target: str = "ko", timeout=90) -> Dict[str, Any]:
    reason = _secret_missing_reason(api_key, "Gemini API Key")
    if reason:
        raise ValueError(reason)
    reason = _value_missing_reason(model, "Gemini Model")
    if reason:
        raise ValueError(reason)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    payload = {"contents": [{"role": "user", "parts": [{"text": _build_translation_prompt(lines, target)}]}]}
    r = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    content = ""
    try:
        parts = data["candidates"][0]["content"]["parts"]
        content = "\n".join(str(p.get("text") or "") for p in parts if isinstance(p, dict) and p.get("text"))
    except Exception:
        content = str(data)[:1000]
    outputs = _parse_translated_lines(content, len(lines))
    return {
        "url": url,
        "json": data,
        "text": content,
        "input_count": len(lines),
        "output_count": len(outputs),
        "outputs": outputs,
        "pairs": [{"src": s, "dst": outputs[i] if i < len(outputs) else ""} for i, s in enumerate(lines)],
    }


def _extract_gemini_image_bytes(data: Dict[str, Any]) -> Tuple[bytes, Dict[str, Any]]:
    candidates = data.get("candidates") or []
    for cand in candidates:
        content = cand.get("content") or {}
        for part in content.get("parts") or []:
            if not isinstance(part, dict):
                continue
            inline = part.get("inlineData") or part.get("inline_data") or {}
            if isinstance(inline, dict):
                b64 = inline.get("data")
                mime = inline.get("mimeType") or inline.get("mime_type") or ""
                if b64 and str(mime).startswith("image/"):
                    return base64.b64decode(b64), {"response_format": "inline_data", "mime_type": mime}
            file_data = part.get("fileData") or part.get("file_data") or {}
            uri = file_data.get("fileUri") or file_data.get("file_uri") if isinstance(file_data, dict) else ""
            if uri:
                data_bytes, source = _download_image_bytes_from_url_or_data(uri)
                return data_bytes, {"response_format": "file_uri", "source": source}
    raise ValueError("Gemini 응답에서 이미지 데이터를 찾지 못했습니다.")


def _run_gemini_inpaint_practical(api_key: str, model: str, sample: Dict[str, Any], *, prompt: str = "", timeout=120) -> Dict[str, Any]:
    reason = _secret_missing_reason(api_key, "Gemini API Key")
    if reason:
        raise ValueError(reason)
    reason = _value_missing_reason(model, "Gemini Image Model")
    if reason:
        raise ValueError(reason)
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
    input_h = int(sample["image_bgr"].shape[0])
    input_w = int(sample["image_bgr"].shape[1])
    user_prompt = str(prompt or "").strip()
    if not user_prompt:
        user_prompt = "Remove the visible text only inside the white mask area and reconstruct the original background."

    full_prompt = (
        "You are performing a strict inpainting/editing test for YSB Translator.\n"
        "\n"
        "CRITICAL RULES:\n"
        "1. Edit the FIRST image only. Do not create a new scene, new panel, or new manga page.\n"
        "2. The SECOND image is a white-on-black mask for the FIRST image.\n"
        "3. White pixels in the mask are the ONLY editable area.\n"
        "4. Black pixels in the mask must remain unchanged.\n"
        "5. Remove only the visible text/stroke inside the white mask area.\n"
        "6. Reconstruct the original black background inside the mask.\n"
        f"7. Keep the canvas size exactly {input_w}x{input_h}. Do not crop, resize, pad, rotate, or change aspect ratio.\n"
        "8. Return only the full edited image. Do not return explanations or a redesigned image.\n"
        "\n"
        "User inpainting instruction:\n"
        f"{user_prompt}"
    )

    payload = {
        "contents": [{
            "role": "user",
            "parts": [
                {"text": full_prompt},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(sample["image_bytes"]).decode("ascii")}},
                {"inline_data": {"mime_type": "image/png", "data": base64.b64encode(sample["mask_bytes"]).decode("ascii")}},
            ],
        }]
    }
    r = requests.post(url, params={"key": api_key}, json=payload, timeout=timeout)
    if r.status_code != 200:
        raise ValueError(_http_error_detail(r))
    data = r.json()
    image_bytes, info = _extract_gemini_image_bytes(data)
    info = dict(info or {})
    info.update({
        "prompt_used": True,
        "prompt_excerpt": full_prompt[:900],
        "input_size": [input_w, input_h],
        "input_shape": list(getattr(sample.get("image_bgr"), "shape", [])),
        "mask_shape": list(getattr(sample.get("mask"), "shape", [])),
    })
    return {"url": url, "json": data, "text": json.dumps(info, ensure_ascii=False), "image_bytes": image_bytes, "output_info": info}


def _run_practical_diagnostic(settings: Dict[str, Any], category: str, provider: str) -> Dict[str, Any]:
    """Run an explicit real-world sample test using bundled diagnostic assets.

    This path intentionally sends bundled sample text/images to the selected provider.
    It should only be called from the dedicated "실전 테스트" button.
    """
    category = str(category or "").lower()
    provider = str(provider or "").lower()
    artifact_dir = _diagnostic_artifact_dir(provider, category, "practical")
    if category == "ocr":
        sample = _load_practical_sample("ja")
        response: Dict[str, Any]
        if provider == "clova":
            response = _run_clova_ocr_practical(settings.get("clova_api_url") or "", settings.get("clova_secret_key") or "", sample)
        elif provider == "google_vision":
            response = _run_google_vision_ocr_practical(settings.get("google_vision_api_key") or "", settings.get("google_vision_model") or "DOCUMENT_TEXT_DETECTION", sample, language_hints=settings.get("google_vision_language_hints") or "ja,en,zh")
        elif provider in ("local_paddle_ocr", "local_paddle", "local_manga_ocr", "local_manga"):
            raise ValueError("LOCAL OCR 실전 테스트는 현재 외부 API 진단 버튼에서 직접 실행하지 않습니다. Local판 본 작업의 OCR 실행으로 확인하세요.")
        else:
            raise ValueError(f"지원하지 않는 OCR 실전 테스트 provider입니다: {provider}")
        items = response.get("items") or []
        overlay = _draw_ocr_overlay(sample, items)
        artifacts = _save_practical_assets(artifact_dir, sample, overlay_bgr=overlay)
        response["artifacts"] = artifacts
        response["program_apply"] = {"ok": bool(items), "data_count": len(items), "items": items[:10]}
        ok = bool(items)
        detail = "OCR 실전 테스트 통과" if ok else "OCR 응답은 받았지만 감지된 텍스트가 없습니다."
        return {"ok": ok, "detail": detail, "result_kind": "ocr_result", "request_sent": True, "response_payload": response, "artifact_dir": str(artifact_dir)}

    if category == "translation":
        sample = _load_practical_sample("ja")
        lines = list(sample.get("lines") or [])[:3]
        if not lines:
            raise ValueError("번역 실전 테스트용 샘플 문장을 찾지 못했습니다.")
        target = settings.get("translation_target_language") or "ko"
        if provider == "openai":
            response = _run_openai_compatible_translation_practical("https://api.openai.com/v1", settings.get("openai_model") or "gpt-4o-mini", settings.get("openai_api_key") or "", lines, provider=provider, target=target, require_api_key=True)
        elif provider == "deepseek":
            response = _run_openai_compatible_translation_practical("https://api.deepseek.com", settings.get("deepseek_model") or "deepseek-chat", settings.get("deepseek_api_key") or "", lines, provider=provider, target=target, require_api_key=True)
        elif provider == "google":
            response = _run_google_translate_practical(settings.get("google_translate_api_key") or "", lines, target=target)
        elif provider == "gemini":
            response = _run_gemini_text_practical(settings.get("gemini_api_key") or "", settings.get("gemini_model") or "gemini-2.5-flash-lite", lines, target=target)
        elif provider == "gemini_deferred":
            key = settings.get("gemini_delayed_api_key") or settings.get("gemini_api_key") or ""
            response = _run_gemini_text_practical(key, settings.get("gemini_delayed_model") or "gemini-2.5-flash-lite", lines, target=target)
        elif provider == "custom":
            response = _run_openai_compatible_translation_practical(settings.get("custom_translation_base_url") or "", settings.get("custom_translation_model") or "", settings.get("custom_translation_api_key") or "", lines, provider=provider, target=target, require_api_key=True)
        elif provider == "lm_studio":
            response = _run_openai_compatible_translation_practical(settings.get("lm_studio_base_url") or "http://localhost:1234/v1", settings.get("lm_studio_model") or "", settings.get("lm_studio_api_key") or "", lines, provider=provider, target=target, require_api_key=False)
        else:
            raise ValueError(f"지원하지 않는 번역 실전 테스트 provider입니다: {provider}")
        outputs = response.get("outputs") or []
        response["program_apply"] = {"ok": len(outputs) == len(lines) and all(outputs), "input_count": len(lines), "output_count": len(outputs), "pairs": response.get("pairs") or []}
        (artifact_dir / "translation_result.json").write_text(json.dumps(response["program_apply"], ensure_ascii=False, indent=2), encoding="utf-8")
        ok = bool(response["program_apply"]["ok"])
        detail = "번역 실전 테스트 통과" if ok else "번역 응답은 받았지만 입력/출력 개수 또는 내용이 기대와 다릅니다."
        return {"ok": ok, "detail": detail, "result_kind": "translation_result", "request_sent": True, "response_payload": response, "artifact_dir": str(artifact_dir)}

    if category == "inpaint":
        sample = _load_practical_sample("ja")
        base_artifacts = _save_practical_assets(artifact_dir, sample)
        response: Dict[str, Any] = {"artifacts": base_artifacts}
        request_sent = False
        try:
            if provider == "replicate_lama":
                token = settings.get("lama_replicate_api_token") or settings.get("replicate_api_token") or ""
                request_sent = True
                response = _run_replicate_inpaint_prediction(token, settings.get("repaint_model") or "", provider, sample["image_bgr"], sample["mask"], wait_timeout=max(30, int(settings.get("replicate_lama_wait_seconds") or 3) * 30))
            elif provider == "replicate_stable":
                token = settings.get("stable_replicate_api_token") or settings.get("replicate_api_token") or ""
                stable_ref, auto_versioned = _normalize_replicate_stable_model_ref(settings.get("stable_inpaint_model") or "")
                request_sent = True
                response = _run_replicate_inpaint_prediction(token, stable_ref, provider, sample["image_bgr"], sample["mask"], prompt=settings.get("stable_inpaint_prompt") or "", wait_timeout=max(30, int(settings.get("stable_inpaint_wait_seconds") or 3) * 30))
                response["stable_model_auto_versioned"] = bool(auto_versioned)
                response["stable_model_used"] = stable_ref
            elif provider == "gemini_inpaint":
                request_sent = True
                response = _run_gemini_inpaint_practical(settings.get("gemini_api_key") or "", _gemini_image_model_normalize(settings.get("gemini_inpaint_model") or "gemini-3.1-flash-image"), sample, prompt=settings.get("gemini_inpaint_prompt") or "")
            elif provider == "local_lama":
                raise ValueError("LOCAL LaMA 실전 테스트는 현재 외부 API 진단 버튼에서 직접 실행하지 않습니다. Local판 본 작업의 인페인팅 실행으로 확인하세요.")
            else:
                raise ValueError(f"지원하지 않는 인페인팅 실전 테스트 provider입니다: {provider}")
        except Exception as e:
            msg = str(e)
            failed_stage = "PRACTICAL_RUN"
            if "HTTP 404" in msg and str(provider) == "replicate_stable":
                failed_stage = "REPLICATE_MODEL_NOT_FOUND"
                msg += "\n현재 Stable Diffusion Inpainting 모델명이 버전 없는 owner/model 형식이면 실행 엔드포인트에서 404가 날 수 있습니다. version hash가 붙은 모델명을 사용하세요."
            elif "HTTP 404" in msg:
                failed_stage = "MODEL_NOT_FOUND"
            elif "HTTP 401" in msg or "HTTP 403" in msg:
                failed_stage = "AUTH"
            err = {"ok": False, "failed_stage": failed_stage, "error": msg, "artifacts": base_artifacts}
            try:
                (artifact_dir / "request_error.json").write_text(json.dumps(err, ensure_ascii=False, indent=2), encoding="utf-8")
            except Exception:
                pass
            return {"ok": False, "detail": msg, "failed_stage": failed_stage, "result_kind": "error", "request_sent": bool(request_sent), "response_payload": err, "artifact_dir": str(artifact_dir)}

        image_bytes = response.get("image_bytes") or b""
        artifacts = _save_practical_assets(artifact_dir, sample, output_bytes=image_bytes)
        response["artifacts"] = artifacts

        output_saved = bool(artifacts.get("output_saved"))
        same_size = artifacts.get("same_size_as_input")
        failed_stage = ""
        warning_stage = ""
        if not image_bytes:
            ok = False
            failed_stage = "IMAGE_RESPONSE_EMPTY"
            detail = "인페인팅 API 응답에서 결과 이미지 데이터를 찾지 못했습니다."
        elif not output_saved:
            ok = False
            failed_stage = "IMAGE_SAVE"
            detail = "인페인팅 결과 이미지를 받았지만 디코드/저장/재읽기에 실패했습니다."
        elif same_size is False:
            # Gemini-style image models often return a nearby generated canvas size.
            # For a practical test, receiving and saving an image is meaningful success,
            # so keep it as OK with warning and save output_resized.png for apply-path checks.
            ok = True
            warning_stage = "IMAGE_SIZE_MISMATCH"
            detail = (
                "인페인팅 결과 이미지를 받았고 저장했습니다. 다만 원본 크기와 달라 리사이즈본을 함께 저장했습니다. "
                f"input_hw={artifacts.get('input_hw')}, output_hw={artifacts.get('output_hw')}, resized={artifacts.get('resized_output_saved')}"
            )
        else:
            ok = True
            detail = "인페인팅 실전 테스트 통과"

        response["program_apply"] = {
            "ok": bool(ok),
            "failed_stage": failed_stage,
            "warning_stage": warning_stage,
            "artifacts": artifacts,
            "output_info": response.get("output_info") or {},
        }
        # Do not keep raw bytes in result JSON/log.
        if "image_bytes" in response:
            response["image_bytes"] = f"<{len(image_bytes)} bytes>"
        return {"ok": ok, "detail": detail, "failed_stage": failed_stage, "warning_stage": warning_stage, "result_kind": "image", "request_sent": True, "response_payload": response, "artifact_dir": str(artifact_dir)}

    raise ValueError(f"알 수 없는 실전 테스트 category입니다: {category}")

def _provider_label(provider: str, category: str) -> str:
    return f"{category}:{provider}"


def run_api_diagnostic(settings: Any, category: str, provider: str, test_kind: str = "response") -> Dict[str, Any]:
    """Run a lightweight preflight diagnostic.

    Important policy:
    - response/API tests do not send real user images, real translation text, or real inpainting jobs.
      They only validate required values and, where possible, call a lightweight metadata/auth endpoint.
    - apply/program tests do not call external APIs. They use mock/minimal internal payloads to check
      YSB parsing, mapping, Unicode path save/read, and image decode routes.
    - practical tests are opt-in real execution tests. They send bundled sample assets/text to the provider.
    """
    settings = _settings_dict(settings)
    category = str(category or "").lower()
    provider = str(provider or "").lower()
    test_kind = str(test_kind or "response").lower()
    steps: List[Dict[str, Any]] = []
    lines: List[str] = []
    ok = False
    detail = ""
    data_excerpt = ""
    failed_stage = ""
    request_sent = False
    result_kind = ""
    log_kind = "api_response_test" if test_kind == "response" else ("api_practical_test" if test_kind == "practical" else "api_apply_test")

    lines.append("YSB API DIAGNOSTIC")
    lines.append(f"kind={test_kind}")
    lines.append(f"category={category}")
    lines.append(f"provider={provider}")
    lines.append(f"time={time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append("")
    lines.append("===== SETTINGS (masked) =====")
    lines.append(json.dumps(_safe_settings_for_log(settings), ensure_ascii=False, indent=2))
    lines.append("")

    def _fail(stage: str, message: str):
        nonlocal failed_stage
        failed_stage = stage or failed_stage or "CHECK"
        raise ValueError(message)

    def _add_required_secret(value: Any, label: str, stage: str = "TOKEN_CHECK"):
        reason = _append_required_secret_step(steps, value, label, stage=stage)
        if reason:
            _fail(stage, reason)

    def _add_required_value(value: Any, label: str, stage: str = "MODEL_CHECK"):
        reason = _append_required_value_step(steps, value, label, stage=stage)
        if reason:
            _fail(stage, reason)

    def _add_required_url(value: Any, label: str, stage: str = "URL_CHECK", *, allow_local: bool = False):
        reason = _append_required_url_step(steps, value, label, stage=stage, allow_local=allow_local)
        if reason:
            _fail(stage, reason)

    try:
        steps.append(_step("설정 로드", True, "현재 입력칸 값 기준으로 사전 점검합니다."))

        if test_kind == "apply":
            probe = _unicode_path_probe()
            steps.append(_step("한글/일본어 경로 저장·재읽기", bool(probe.get("ok")), json.dumps(probe, ensure_ascii=False), stage="UNICODE_PATH", request_sent=False))
            if not probe.get("ok"):
                _fail("UNICODE_PATH", "한글/일본어 경로 저장·재읽기 검사 실패: " + str(probe.get("error") or probe))

        response_payload: Dict[str, Any] = {}

        if test_kind == "practical":
            practical = _run_practical_diagnostic(settings, category, provider)
            ok = bool(practical.get("ok"))
            detail = str(practical.get("detail") or "")
            request_sent = bool(practical.get("request_sent"))
            result_kind = str(practical.get("result_kind") or "practical_result")
            practical_stage = str(practical.get("failed_stage") or "PRACTICAL_RUN")
            response_payload = practical.get("response_payload") if isinstance(practical.get("response_payload"), dict) else {}
            artifact_dir = str(practical.get("artifact_dir") or "")
            warning_stage = str(practical.get("warning_stage") or "")
            steps.append(_step("실전 테스트", ok, detail, stage=practical_stage if not ok else (warning_stage or "PRACTICAL_RUN"), request_sent=request_sent, result_kind=result_kind, warning_stage=warning_stage))
            if artifact_dir:
                steps.append(_step("결과 파일 저장", True, artifact_dir, stage="ARTIFACT_SAVE", request_sent=False))
            data_excerpt = json.dumps({
                "artifact_dir": artifact_dir,
                "summary": response_payload.get("program_apply") or {},
                "artifacts": response_payload.get("artifacts") or {},
                "output_info": response_payload.get("output_info") or {},
                "warning_stage": warning_stage,
                "detected_count": response_payload.get("detected_count"),
                "first_text": response_payload.get("first_text"),
                "pairs": (response_payload.get("pairs") or response_payload.get("program_apply", {}).get("pairs") or [])[:5] if isinstance(response_payload, dict) else [],
            }, ensure_ascii=False)[:2000]
            if not ok:
                _fail(practical_stage, detail or "실전 테스트 실패")

        elif category == "translation":
            result_kind = "program_mock" if test_kind == "apply" else "connection"
            if provider == "openai":
                _add_required_secret(settings.get("openai_api_key") or "", "OpenAI API Key")
                _add_required_value(settings.get("openai_model") or "", "OpenAI Model")
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_openai_compatible_preflight(
                        "https://api.openai.com/v1",
                        settings.get("openai_model") or "gpt-4o-mini",
                        settings.get("openai_api_key") or "",
                        provider=provider,
                        require_api_key=True,
                        strict_models_endpoint=True,
                    )
            elif provider == "deepseek":
                _add_required_secret(settings.get("deepseek_api_key") or "", "DeepSeek API Key")
                _add_required_value(settings.get("deepseek_model") or "", "DeepSeek Model")
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_openai_compatible_preflight(
                        "https://api.deepseek.com",
                        settings.get("deepseek_model") or "deepseek-chat",
                        settings.get("deepseek_api_key") or "",
                        provider=provider,
                        require_api_key=True,
                        strict_models_endpoint=True,
                    )
            elif provider == "google":
                _add_required_secret(settings.get("google_translate_api_key") or "", "Google Translate API Key")
                _add_required_value(settings.get("google_translate_model") or "", "Google Translate Model")
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_google_translate_preflight(
                        settings.get("google_translate_api_key") or "",
                        target=settings.get("translation_target_language") or "ko",
                    )
            elif provider in ("gemini", "gemini_deferred"):
                key = settings.get("gemini_api_key") if provider == "gemini" else (settings.get("gemini_delayed_api_key") or settings.get("gemini_api_key"))
                model = settings.get("gemini_model") if provider == "gemini" else settings.get("gemini_delayed_model")
                label = "Gemini" if provider == "gemini" else "Gemini Flex/Batch"
                _add_required_secret(key or "", f"{label} API Key")
                _add_required_value(model or "", f"{label} Model")
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_gemini_model_preflight(key or "", model or "gemini-2.5-flash-lite", label=label)
            elif provider == "custom":
                _add_required_url(settings.get("custom_translation_base_url") or "", "Custom Base URL", allow_local=True)
                _add_required_value(settings.get("custom_translation_model") or "", "Custom Model")
                _add_required_secret(settings.get("custom_translation_api_key") or "", "Custom/OpenAI-Compatible API Key")
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_openai_compatible_preflight(
                        settings.get("custom_translation_base_url") or "",
                        settings.get("custom_translation_model") or "",
                        settings.get("custom_translation_api_key") or "",
                        provider=provider,
                        require_api_key=True,
                        strict_models_endpoint=False,
                    )
            elif provider == "lm_studio":
                _add_required_url(settings.get("lm_studio_base_url") or "http://localhost:1234/v1", "LM Studio Base URL", allow_local=True)
                _add_required_value(settings.get("lm_studio_model") or "", "LM Studio Model")
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_openai_compatible_preflight(
                        settings.get("lm_studio_base_url") or "http://localhost:1234/v1",
                        settings.get("lm_studio_model") or "",
                        settings.get("lm_studio_api_key") or "",
                        provider=provider,
                        require_api_key=False,
                        strict_models_endpoint=False,
                    )
            else:
                _fail("UNSUPPORTED_PROVIDER", f"지원하지 않는 번역 provider입니다: {provider}")

            if test_kind == "response":
                steps.append(_step("API 사전 점검", True, "실제 번역 문장을 보내지 않고 연결/인증/모델 조회를 확인했습니다.", url=response_payload.get("url", ""), request_sent=bool(request_sent), model_found=response_payload.get("model_found")))
                detail = "번역 API 사전 점검 통과"
            else:
                apply_probe = _translation_mock_apply_probe(provider)
                steps.append(_step("프로그램 내부 점검", bool(apply_probe.get("ok")), json.dumps(apply_probe, ensure_ascii=False), stage="PROGRAM_APPLY", request_sent=False))
                if not apply_probe.get("ok"):
                    _fail("PROGRAM_APPLY", "번역 mock 결과를 내부 데이터에 적용하지 못했습니다.")
                response_payload = {"json": apply_probe, "text": json.dumps(apply_probe, ensure_ascii=False)[:700]}
                detail = "번역 프로그램 내부 점검 통과"
            ok = True

        elif category == "inpaint":
            result_kind = "program_mock_image" if test_kind == "apply" else "connection"
            if provider in ("replicate_lama", "replicate_stable"):
                token = settings.get("lama_replicate_api_token") if provider == "replicate_lama" else settings.get("stable_replicate_api_token")
                token = token or settings.get("replicate_api_token") or ""
                _add_required_secret(token, "Replicate API Token")
                model_ref = settings.get("repaint_model") if provider == "replicate_lama" else settings.get("stable_inpaint_model")
                model_label = "Replicate LaMA 모델명" if provider == "replicate_lama" else "Replicate Stable 모델명"
                _add_required_value(model_ref, model_label)
                try:
                    _parse_replicate_model_ref(str(model_ref or ""))
                    steps.append(_step("모델명 형식 검사", True, "owner/model 또는 owner/model:version 형식 확인 완료", stage="MODEL_FORMAT", request_sent=False))
                except Exception as e:
                    _fail("MODEL_FORMAT", str(e))
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_replicate_connection(token)
                    steps.append(_step("API 사전 점검", True, "실제 인페인팅 prediction을 만들지 않고 Replicate 연결/인증만 확인했습니다.", api="models", url=response_payload.get("url", ""), request_sent=True, result_count=response_payload.get("result_count", 0)))
                    detail = "Replicate 연결/인증 사전 점검 통과"
            elif provider == "gemini_inpaint":
                key = settings.get("gemini_api_key") or ""
                model = _gemini_image_model_normalize(settings.get("gemini_inpaint_model") or "gemini-3.1-flash-image")
                _add_required_secret(key, "Gemini API Key")
                _add_required_value(model, "Gemini Image Model")
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_gemini_model_preflight(key, model, label="Gemini Image")
                    steps.append(_step("API 사전 점검", True, "실제 이미지를 보내지 않고 Gemini 이미지 모델 조회만 확인했습니다.", url=response_payload.get("url", ""), request_sent=True))
                    detail = "Gemini 이미지 모델 사전 점검 통과"
            elif provider == "local_lama":
                response_payload = _local_worker_probe("local_lama_worker.py")
                if not response_payload.get("exists"):
                    _fail("LOCAL_WORKER_CHECK", "LOCAL LaMA worker 파일을 찾지 못했습니다: " + str(response_payload.get("worker_path") or ""))
                steps.append(_step("LOCAL 구성 점검", True, response_payload.get("text", ""), stage="LOCAL_WORKER_CHECK", request_sent=False))
                detail = "LOCAL LaMA 구성 사전 점검 통과"
            else:
                _fail("UNSUPPORTED_PROVIDER", f"지원하지 않는 인페인팅 provider입니다: {provider}")

            if test_kind == "apply":
                apply_probe = _inpaint_mock_apply_probe()
                steps.append(_step("프로그램 내부 점검", bool(apply_probe.get("ok")), json.dumps(apply_probe, ensure_ascii=False), stage="PROGRAM_APPLY", request_sent=False))
                if not apply_probe.get("ok"):
                    _fail("PROGRAM_APPLY", "인페인팅 mock 이미지 결과를 디코드/저장/재읽기하지 못했습니다.")
                response_payload = {"json": apply_probe, "text": json.dumps(apply_probe, ensure_ascii=False)[:700]}
                detail = "인페인팅 프로그램 내부 점검 통과"
            ok = True
            if not detail:
                detail = "인페인팅 API 사전 점검 통과"

        elif category == "ocr":
            result_kind = "program_mock_ocr" if test_kind == "apply" else "connection"
            if provider == "clova":
                _add_required_url(settings.get("clova_api_url") or "", "CLOVA OCR Invoke URL")
                _add_required_secret(settings.get("clova_secret_key") or "", "CLOVA OCR Secret Key")
                if test_kind == "response":
                    response_payload = _test_clova_preflight(settings.get("clova_api_url") or "", settings.get("clova_secret_key") or "")
                    steps.append(_step("API 사전 점검", True, "실제 이미지를 보내지 않고 CLOVA URL/Secret 형식만 확인했습니다. CLOVA 인증은 실제 OCR 실행 때 최종 확인됩니다.", url=response_payload.get("url", ""), request_sent=False))
                    detail = "CLOVA OCR 사전 점검 통과"
            elif provider == "google_vision":
                key = settings.get("google_vision_api_key") or ""
                model = settings.get("google_vision_model") or "DOCUMENT_TEXT_DETECTION"
                _add_required_secret(key, "Google Vision API Key")
                _add_required_value(model, "Google Vision Model")
                if test_kind == "response":
                    request_sent = True
                    response_payload = _test_google_vision_preflight(key, model)
                    steps.append(_step("API 사전 점검", True, "실제 이미지를 보내지 않고 Google Vision 빈 요청/인증 응답만 확인했습니다.", url=response_payload.get("url", ""), request_sent=True, warning=response_payload.get("warning", "")))
                    detail = "Google Vision OCR 사전 점검 통과"
            elif provider in ("local_paddle_ocr", "local_paddle"):
                response_payload = _local_worker_probe("paddle_ocr_worker.py")
                if not response_payload.get("exists"):
                    _fail("LOCAL_WORKER_CHECK", "LOCAL Paddle OCR worker 파일을 찾지 못했습니다: " + str(response_payload.get("worker_path") or ""))
                steps.append(_step("LOCAL 구성 점검", True, response_payload.get("text", ""), stage="LOCAL_WORKER_CHECK", request_sent=False))
                detail = "LOCAL Paddle OCR 구성 사전 점검 통과"
            elif provider in ("local_manga_ocr", "local_manga"):
                response_payload = _local_worker_probe("manga_ocr_worker.py")
                if not response_payload.get("exists"):
                    _fail("LOCAL_WORKER_CHECK", "LOCAL Manga OCR worker 파일을 찾지 못했습니다: " + str(response_payload.get("worker_path") or ""))
                steps.append(_step("LOCAL 구성 점검", True, response_payload.get("text", ""), stage="LOCAL_WORKER_CHECK", request_sent=False))
                detail = "LOCAL Manga OCR 구성 사전 점검 통과"
            else:
                _fail("UNSUPPORTED_PROVIDER", f"지원하지 않는 OCR provider입니다: {provider}")

            if test_kind == "apply":
                apply_probe = _ocr_mock_apply_probe(provider)
                steps.append(_step("프로그램 내부 점검", bool(apply_probe.get("ok")), json.dumps(apply_probe, ensure_ascii=False), stage="PROGRAM_APPLY", request_sent=False))
                if not apply_probe.get("ok"):
                    _fail("PROGRAM_APPLY", "OCR mock 결과를 내부 데이터에 적용하지 못했습니다.")
                response_payload = {"json": apply_probe, "text": json.dumps(apply_probe, ensure_ascii=False)[:700]}
                detail = "OCR 프로그램 내부 점검 통과"
            ok = True
            if not detail:
                detail = "OCR API 사전 점검 통과"

        else:
            _fail("UNKNOWN_CATEGORY", f"알 수 없는 API category입니다: {category}")

        if not data_excerpt:
            data_excerpt = str(response_payload.get("json_excerpt") or response_payload.get("text") or response_payload.get("json") or "")[:1500]

    except Exception as e:
        ok = False
        detail = str(e)
        if not failed_stage:
            try:
                for st in reversed(steps):
                    if isinstance(st, dict) and not st.get("ok") and st.get("stage"):
                        failed_stage = str(st.get("stage") or "")
                        break
            except Exception:
                pass
        if not failed_stage:
            failed_stage = "PRACTICAL_RUN" if test_kind == "practical" else "EXCEPTION"
        steps.append(_step("실패 지점", False, detail, stage=failed_stage, request_sent=request_sent))
        lines.append("===== ERROR TRACE =====")
        lines.append(traceback.format_exc())

    summary = {
        "overall": "OK" if ok else "FAIL",
        "category": category,
        "provider": provider,
        "test_kind": test_kind,
        "failed_stage": failed_stage,
        "request_sent": bool(request_sent),
        "result_kind": result_kind,
        "detail": detail,
    }

    result = {
        "ok": bool(ok),
        "category": category,
        "provider": provider,
        "test_kind": test_kind,
        "detail": detail,
        "failed_stage": failed_stage,
        "request_sent": bool(request_sent),
        "result_kind": result_kind,
        "summary": summary,
        "steps": steps,
        "data_excerpt": data_excerpt,
        "settings_masked": _safe_settings_for_log(settings),
    }

    lines.append("===== SUMMARY =====")
    lines.append(json.dumps(summary, ensure_ascii=False, indent=2))
    lines.append("")
    lines.append("===== STEPS =====")
    for st in steps:
        lines.append(json.dumps(st, ensure_ascii=False))
    if data_excerpt:
        lines.append("")
        lines.append("===== RESPONSE EXCERPT =====")
        lines.append(data_excerpt[:2000])
    log_path = _write_log(log_kind, provider, result, lines)
    result["log_path"] = log_path
    return result
