from __future__ import annotations

"""Shared text-layout data structures.

The engines still return plain dictionaries for compatibility with the legacy
YSB code paths, but these dataclasses document the target contract: glyph/path
creation is shared, while horizontal layout, vertical layout and editor mapping
stay separate modules.
"""

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from PyQt6.QtCore import QPointF, QRectF
from PyQt6.QtGui import QPainterPath


@dataclass
class LayoutToken:
    kind: str
    text: str
    display_index: int
    path: QPainterPath = field(default_factory=QPainterPath)
    rect: QRectF = field(default_factory=QRectF)
    flow_start: QPointF = field(default_factory=QPointF)
    flow_end: QPointF = field(default_factory=QPointF)
    style: Dict[str, Any] = field(default_factory=dict)
    token_len: int = 1


@dataclass
class TextLayoutResult:
    path: QPainterPath = field(default_factory=QPainterPath)
    line_rects: List[QRectF] = field(default_factory=list)
    tokens: List[LayoutToken] = field(default_factory=list)
    char_slots: List[Dict[str, Any]] = field(default_factory=list)
    display_caret_map: Dict[int, QPointF] = field(default_factory=dict)
    content_rect: QRectF = field(default_factory=QRectF)
    meta: Dict[str, Any] = field(default_factory=dict)
