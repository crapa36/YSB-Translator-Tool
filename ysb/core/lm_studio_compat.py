"""LM Studio JSON compatibility helpers for YSB Translator.

These helpers are intentionally small and dependency-light so the settings dialog
and the translation engine can share the same compatibility judgement.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, List, Tuple

import requests


_REASONING_MARKERS = (
    "<|channel>",
    "<channel|>",
    "<|start|>",
    "<|end|>",
    "<think>",
    "</think>",
    "thought\n",
    "analysis\n",
)


def normalize_lm_studio_base_url(base_url: str) -> str:
    base = str(base_url or "").strip().rstrip("/")
    if not base:
        return ""
    lowered = base.lower()
    for suffix in ("/v1/chat/completions", "/chat/completions", "/v1/models", "/models"):
        if lowered.endswith(suffix):
            base = base[: -len(suffix)].rstrip("/")
            lowered = base.lower()
            break
    if lowered.endswith("/v1"):
        return base
    return base + "/v1"


def lm_studio_models_url(base_url: str) -> str:
    base = normalize_lm_studio_base_url(base_url)
    return (base + "/models") if base else ""


def lm_studio_chat_url(base_url: str) -> str:
    base = normalize_lm_studio_base_url(base_url)
    return (base + "/chat/completions") if base else ""


def strip_json_code_fence(content: str) -> Tuple[str, bool]:
    text = str(content or "").strip()
    had_fence = False
    if text.startswith("```json"):
        text = text[7:].strip()
        had_fence = True
    elif text.startswith("```"):
        text = text[3:].strip()
        had_fence = True
    if text.endswith("```"):
        text = text[:-3].strip()
        had_fence = True
    return text, had_fence


def _contains_reasoning_marker(text: str) -> bool:
    low = str(text or "").lower()
    return any(marker in low for marker in _REASONING_MARKERS)


def _find_first_json_object(text: str) -> str:
    """Best-effort extraction of the first balanced JSON object/array.

    This is only for diagnostics. The translator remains strict so reasoning text
    is not silently accepted as a final answer.
    """
    s = str(text or "")
    starts = [idx for idx in (s.find("{"), s.find("[")) if idx >= 0]
    if not starts:
        return ""
    start = min(starts)
    opener = s[start]
    closer = "}" if opener == "{" else "]"
    depth = 0
    in_str = False
    escape = False
    for i in range(start, len(s)):
        ch = s[i]
        if in_str:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_str = False
            continue
        if ch == '"':
            in_str = True
        elif ch == opener:
            depth += 1
        elif ch == closer:
            depth -= 1
            if depth == 0:
                return s[start : i + 1]
    return ""


def validate_translation_items_payload(parsed: Any, require_translation: bool = True) -> Tuple[bool, str, List[Dict[str, Any]]]:
    if isinstance(parsed, dict):
        items = parsed.get("items")
    elif isinstance(parsed, list):
        items = parsed
    else:
        return False, "응답 최상위가 JSON 객체나 배열이 아닙니다.", []
    if not isinstance(items, list):
        return False, "응답 JSON에 items 배열이 없습니다.", []
    if not items:
        return False, "items 배열이 비어 있습니다.", []
    normalized: List[Dict[str, Any]] = []
    for index, item in enumerate(items):
        if not isinstance(item, dict):
            return False, f"items[{index}]가 객체가 아닙니다.", []
        if "id" not in item:
            return False, f"items[{index}]에 id가 없습니다.", []
        if require_translation and "translation" not in item:
            return False, f"items[{index}]에 translation이 없습니다.", []
        normalized.append(item)
    return True, "", normalized


def analyze_lm_studio_json_content(content: str) -> Dict[str, Any]:
    raw = str(content or "")
    stripped, had_code_fence = strip_json_code_fence(raw)
    starts_like_json = stripped.startswith("{") or stripped.startswith("[")
    has_reasoning_marker = _contains_reasoning_marker(raw)
    result: Dict[str, Any] = {
        "ok": False,
        "level": "error",
        "reason": "",
        "raw_excerpt": raw[:500],
        "had_code_fence": had_code_fence,
        "starts_like_json": starts_like_json,
        "has_reasoning_marker": has_reasoning_marker,
        "recoverable_json_found": False,
        "item_count": 0,
    }

    if not stripped:
        result["reason"] = "LM Studio 응답 content가 비어 있습니다."
        return result

    if not starts_like_json:
        extracted = _find_first_json_object(stripped)
        if extracted:
            try:
                parsed_extract = json.loads(extracted)
                valid, msg, items = validate_translation_items_payload(parsed_extract)
                if valid:
                    result.update({
                        "recoverable_json_found": True,
                        "item_count": len(items),
                        "reason": "응답 앞뒤에 JSON이 아닌 텍스트나 reasoning/channel 토큰이 섞여 있습니다.",
                    })
                    return result
                result["reason"] = msg or "응답 속 JSON 블록의 형식이 올바르지 않습니다."
                return result
            except Exception:
                pass
        if has_reasoning_marker:
            result["reason"] = "응답 content에 reasoning/channel 토큰이 섞여 있어 순수 JSON으로 파싱할 수 없습니다."
        else:
            result["reason"] = "응답 content가 JSON으로 시작하지 않습니다."
        return result

    try:
        parsed = json.loads(stripped)
    except Exception as exc:
        result["reason"] = f"JSON 파싱 실패: {exc}"
        return result

    valid, msg, items = validate_translation_items_payload(parsed)
    if not valid:
        result["reason"] = msg
        return result

    result.update({
        "ok": True,
        "level": "ok",
        "reason": "LM Studio 응답이 YSB 번역 JSON 형식과 호환됩니다.",
        "item_count": len(items),
    })
    if had_code_fence:
        result["level"] = "warning"
        result["reason"] = "JSON 코드블록으로 감싸져 있지만 YSB가 제거해서 읽을 수 있습니다. 순수 JSON 모델이 더 안정적입니다."
    return result


def parse_translation_items_strict(content: str) -> List[Dict[str, Any]]:
    analysis = analyze_lm_studio_json_content(content)
    if not analysis.get("ok"):
        reason = analysis.get("reason") or "번역 응답 JSON 형식이 올바르지 않습니다."
        if analysis.get("recoverable_json_found"):
            reason += " JSON 블록은 보이지만, YSB는 reasoning/설명문이 섞인 응답을 최종 번역으로 자동 채택하지 않습니다."
        raise ValueError(f"LM Studio 응답이 YSB JSON 형식과 호환되지 않습니다. {reason}")
    stripped, _ = strip_json_code_fence(content)
    parsed = json.loads(stripped)
    _, _, items = validate_translation_items_payload(parsed)
    return items


def run_lm_studio_json_compatibility_test(
    base_url: str,
    model: str,
    api_key: str = "",
    timeout: int = 45,
) -> Dict[str, Any]:
    base_url = str(base_url or "").strip()
    model = str(model or "").strip()
    api_key = str(api_key or "").strip() or "lm-studio"
    if not base_url:
        return {"ok": False, "level": "error", "reason": "Base URL이 비어 있습니다."}
    if not model:
        return {"ok": False, "level": "error", "reason": "Model이 비어 있습니다."}

    chat_url = lm_studio_chat_url(base_url)
    models_url = lm_studio_models_url(base_url)
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}
    payload = {
        "model": model,
        "messages": [
            {
                "role": "system",
                "content": (
                    "You are a strict manga translation JSON API. "
                    "Return ONLY valid JSON. No markdown. No reasoning. No comments. "
                    "Schema: {\"items\":[{\"id\":0,\"translation\":\"Korean translation\"}]}"
                ),
            },
            {"role": "user", "content": json.dumps([{"id": 0, "text": "さっさと起きな"}], ensure_ascii=False)},
        ],
        "temperature": 0,
        "max_tokens": 256,
    }

    try:
        resp = requests.post(chat_url, headers=headers, json=payload, timeout=timeout)
    except Exception as exc:
        return {
            "ok": False,
            "level": "error",
            "reason": f"LM Studio 서버에 연결할 수 없습니다: {exc}",
            "chat_url": chat_url,
            "models_url": models_url,
        }

    if resp.status_code < 200 or resp.status_code >= 300:
        excerpt = ""
        try:
            excerpt = resp.text[:500]
        except Exception:
            excerpt = ""
        return {
            "ok": False,
            "level": "error",
            "reason": f"LM Studio 요청 실패: HTTP {resp.status_code}",
            "chat_url": chat_url,
            "models_url": models_url,
            "raw_excerpt": excerpt,
        }

    try:
        data = resp.json()
    except Exception as exc:
        return {
            "ok": False,
            "level": "error",
            "reason": f"LM Studio 응답이 JSON이 아닙니다: {exc}",
            "chat_url": chat_url,
            "models_url": models_url,
            "raw_excerpt": resp.text[:500],
        }

    content = ""
    try:
        content = str(data.get("choices", [{}])[0].get("message", {}).get("content", "") or "")
    except Exception:
        content = ""
    analysis = analyze_lm_studio_json_content(content)
    analysis.update({
        "chat_url": chat_url,
        "models_url": models_url,
        "model": model,
    })
    return analysis
