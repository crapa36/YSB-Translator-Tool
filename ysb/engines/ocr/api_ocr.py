# -*- coding: utf-8 -*-
"""API OCR adapter placeholder.

The existing OCR implementation is not moved in v2.1.0. This file is the future
Lite/API engine slot.
"""

from __future__ import annotations

from .base import OcrRequest, OcrResult


class ApiOcrEngine:
    name = "api"

    def run(self, request: OcrRequest) -> OcrResult:
        return OcrResult(
            ok=False,
            engine=self.name,
            error="ApiOcrEngine is a v2.1.0 structure placeholder. Existing OCR flow is still used.",
        )
