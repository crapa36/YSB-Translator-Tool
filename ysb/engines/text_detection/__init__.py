"""Text detection engine abstractions.

Text detection is separate from OCR:
- text_detection: finds where comic text exists and can produce masks/boxes.
- ocr: reads the detected text.
"""

from .base import (
    TextDetectionRequest,
    TextDetectionBlock,
    TextDetectionLine,
    TextDetectionResult,
    TextDetectionEngine,
)

__all__ = [
    "TextDetectionRequest",
    "TextDetectionBlock",
    "TextDetectionLine",
    "TextDetectionResult",
    "TextDetectionEngine",
]
