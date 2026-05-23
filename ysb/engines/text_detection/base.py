# -*- coding: utf-8 -*-
"""Common text detection interface for Local comic detectors.

This layer only detects text positions/masks. It does not recognize text.
OCR engines can later consume the block/line crops returned here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


Point = tuple[int, int]
Polygon = list[Point]


@dataclass
class TextDetectionLine:
    polygon: Polygon
    confidence: float | None = None
    raw: Any = None


@dataclass
class TextDetectionBlock:
    bbox: tuple[int, int, int, int]
    lines: list[TextDetectionLine] = field(default_factory=list)
    language: str = "unknown"
    vertical: bool = False
    font_size: float | None = None
    angle: int = 0
    confidence: float | None = None
    raw: Any = None


@dataclass
class TextDetectionRequest:
    image_path: str
    options: dict[str, Any] = field(default_factory=dict)


@dataclass
class TextDetectionResult:
    ok: bool
    engine: str
    blocks: list[TextDetectionBlock] = field(default_factory=list)
    mask_path: str = ""
    refined_mask_path: str = ""
    error: str = ""
    raw: Any = None


class TextDetectionEngine(Protocol):
    name: str

    def detect(self, request: TextDetectionRequest) -> TextDetectionResult:
        ...
