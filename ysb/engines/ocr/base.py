# -*- coding: utf-8 -*-
"""Common OCR engine interface placeholder.

No OCR behavior is changed in v2.1.0. This interface is reserved for the next
step, where API OCR and PaddleOCR can return the same result format.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass
class OcrRequest:
    image_path: str
    language: str = "auto"
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class OcrResult:
    ok: bool
    engine: str
    lines: list[dict[str, Any]] = field(default_factory=list)
    error: str = ""
    raw: Any = None


class OcrEngine(Protocol):
    name: str

    def run(self, request: OcrRequest) -> OcrResult:
        ...
