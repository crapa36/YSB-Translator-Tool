# -*- coding: utf-8 -*-
"""Mask-beacon based inpainting group builder.

The inpainting mask is the source of truth.  Connected mask components are
collected as beacons, then packed from top to bottom into crop groups while the
context-padded crop rectangle stays inside the work-canvas side limit.

This module is intentionally UI-free so the preview overlay and the real
inpainting worker can share the exact same grouping result.
"""

from __future__ import annotations

from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple

import cv2
import numpy as np

BBox = Tuple[int, int, int, int]
Group = Dict[str, Any]


def _safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except Exception:
        return int(default)


def _union_bbox(a: Sequence[int], b: Sequence[int]) -> BBox:
    return (
        min(_safe_int(a[0]), _safe_int(b[0])),
        min(_safe_int(a[1]), _safe_int(b[1])),
        max(_safe_int(a[2]), _safe_int(b[2])),
        max(_safe_int(a[3]), _safe_int(b[3])),
    )


def _padded_bbox(bbox: Sequence[int], pad: int, width: int, height: int) -> BBox:
    x1, y1, x2, y2 = [_safe_int(v) for v in bbox[:4]]
    pad = max(0, _safe_int(pad))
    return (
        max(0, x1 - pad),
        max(0, y1 - pad),
        min(int(width), x2 + pad),
        min(int(height), y2 + pad),
    )


def _bbox_size_ok(
    bbox: Sequence[int],
    *,
    padding: int,
    width: int,
    height: int,
    max_work_side: int,
    max_area: Optional[int] = None,
) -> bool:
    px1, py1, px2, py2 = _padded_bbox(bbox, padding, width, height)
    bw = max(0, px2 - px1)
    bh = max(0, py2 - py1)
    if bw > int(max_work_side) or bh > int(max_work_side):
        return False
    if max_area is not None:
        try:
            if bw * bh > int(max_area):
                return False
        except Exception:
            pass
    return True


def _normalize_binary_mask(mask: Any) -> Optional[np.ndarray]:
    if mask is None:
        return None
    try:
        arr = np.asarray(mask)
        if arr.size <= 0:
            return None
        if arr.ndim == 3:
            if arr.shape[2] >= 4:
                # Alpha-bearing masks may have meaningful data in alpha.
                alpha = arr[:, :, 3]
                rgb_gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
                gray = np.maximum(rgb_gray, alpha)
            else:
                gray = cv2.cvtColor(arr[:, :, :3], cv2.COLOR_RGB2GRAY)
        else:
            gray = arr
        gray = gray.astype(np.uint8, copy=False)
        _thr, bin_mask = cv2.threshold(gray, 0, 255, cv2.THRESH_BINARY)
        if int(np.count_nonzero(bin_mask)) <= 0:
            return None
        return bin_mask
    except Exception:
        return None


def _extract_components(mask: np.ndarray, min_component_area: int) -> List[Group]:
    comps: List[Group] = []
    try:
        num, _labels, stats, _cent = cv2.connectedComponentsWithStats(mask, 8)
    except Exception:
        return comps
    min_area = max(1, _safe_int(min_component_area, 1))
    for label in range(1, int(num)):
        try:
            x = int(stats[label, cv2.CC_STAT_LEFT])
            y = int(stats[label, cv2.CC_STAT_TOP])
            ww = int(stats[label, cv2.CC_STAT_WIDTH])
            hh = int(stats[label, cv2.CC_STAT_HEIGHT])
            area = int(stats[label, cv2.CC_STAT_AREA])
        except Exception:
            continue
        if ww <= 0 or hh <= 0 or area < min_area:
            continue
        comps.append({"bbox": (x, y, x + ww, y + hh), "area": area})
    comps.sort(key=lambda c: (c["bbox"][1], c["bbox"][0]))
    return comps


def _new_group_from_component(comp: Group) -> Group:
    bbox = tuple(int(v) for v in comp.get("bbox", (0, 0, 0, 0)))
    return {
        "bbox": bbox,
        "count": 1,
        "area": int(comp.get("area", 0) or 0),
        "components": [bbox],
    }


def _merge_group_into(left: Group, right: Group) -> Group:
    left_bbox = tuple(int(v) for v in left.get("bbox", (0, 0, 0, 0)))
    right_bbox = tuple(int(v) for v in right.get("bbox", (0, 0, 0, 0)))
    left["bbox"] = _union_bbox(left_bbox, right_bbox)
    left["count"] = int(left.get("count", 0) or 0) + int(right.get("count", 0) or 0)
    left["area"] = int(left.get("area", 0) or 0) + int(right.get("area", 0) or 0)
    comps = list(left.get("components", []) or [])
    comps.extend(list(right.get("components", []) or []))
    left["components"] = comps
    return left


def _merge_component_into(group: Group, comp: Group) -> Group:
    return _merge_group_into(group, _new_group_from_component(comp))


def _coalesce_adjacent_groups(
    groups: List[Group],
    *,
    padding: int,
    width: int,
    height: int,
    max_work_side: int,
    max_area: Optional[int] = None,
) -> List[Group]:
    """Repeat one-pass adjacent merges until no more groups can be packed.

    The order is intentionally kept top-to-bottom.  This gives a webtoon-safe
    result and avoids surprising cross-page jumps while still minimizing the
    group count when a previous greedy boundary can be removed.
    """
    if len(groups) <= 1:
        return groups
    changed = True
    while changed:
        changed = False
        merged: List[Group] = []
        for group in groups:
            if merged:
                prev = merged[-1]
                candidate = _union_bbox(prev.get("bbox", (0, 0, 0, 0)), group.get("bbox", (0, 0, 0, 0)))
                if _bbox_size_ok(
                    candidate,
                    padding=padding,
                    width=width,
                    height=height,
                    max_work_side=max_work_side,
                    max_area=max_area,
                ):
                    _merge_group_into(prev, group)
                    changed = True
                    continue
            merged.append(group)
        groups = merged
    return groups


def build_inpaint_mask_groups(
    mask: Any,
    *,
    max_work_side: int = 2800,
    context_padding: Optional[int] = None,
    min_component_area: Optional[int] = None,
    max_area: Optional[int] = None,
) -> List[Group]:
    """Build inpainting crop groups from a binary/gray/RGBA mask.

    Rules:
    - The mask is the beacon source.
    - Components are sorted top-to-bottom, then left-to-right.
    - Distance between components is not a split condition.
    - A merge is allowed when the union bbox after context padding fits inside
      max_work_side x max_work_side, and optional max_area.
    - The returned rect is the padded crop rect; mask_bbox is the raw beacon bbox.
    """
    bin_mask = _normalize_binary_mask(mask)
    if bin_mask is None:
        return []

    h, w = bin_mask.shape[:2]
    if h <= 0 or w <= 0:
        return []

    try:
        max_work_side = max(256, int(max_work_side or 2800))
    except Exception:
        max_work_side = 2800

    if context_padding is None:
        # Width-based padding keeps webtoon strips from being split too eagerly.
        context_padding = min(384, max(96, int(round(float(w) * 0.08))))
    else:
        context_padding = max(0, int(context_padding or 0))

    if min_component_area is None:
        # Keep the default conservative.  Tiny punctuation/hand-painted mask
        # fragments can be meaningful in manga/webtoon lettering.
        min_component_area = 1

    comps = _extract_components(bin_mask, min_component_area=min_component_area)
    if not comps:
        return []

    groups: List[Group] = []
    current: Optional[Group] = None

    for comp in comps:
        if current is None:
            current = _new_group_from_component(comp)
            continue
        candidate = _union_bbox(current["bbox"], comp["bbox"])
        if _bbox_size_ok(
            candidate,
            padding=context_padding,
            width=w,
            height=h,
            max_work_side=max_work_side,
            max_area=max_area,
        ):
            _merge_component_into(current, comp)
        else:
            groups.append(current)
            current = _new_group_from_component(comp)

    if current is not None:
        groups.append(current)

    groups = _coalesce_adjacent_groups(
        groups,
        padding=context_padding,
        width=w,
        height=h,
        max_work_side=max_work_side,
        max_area=max_area,
    )

    out: List[Group] = []
    for idx, group in enumerate(groups, 1):
        px1, py1, px2, py2 = _padded_bbox(group["bbox"], context_padding, w, h)
        if px2 <= px1 or py2 <= py1:
            continue
        mask_bbox = [int(v) for v in group.get("bbox", (0, 0, 0, 0))]
        component_bboxes = [[int(v) for v in bbox] for bbox in group.get("components", []) or []]
        out.append({
            "index": int(idx),
            "rect_norm": [px1 / float(w), py1 / float(h), px2 / float(w), py2 / float(h)],
            "rect": [int(px1), int(py1), int(px2), int(py2)],
            "mask_bbox": mask_bbox,
            "component_bboxes": component_bboxes,
            "mask_count": int(group.get("count", 0) or 0),
            "mask_area": int(group.get("area", 0) or 0),
            "width": int(px2 - px1),
            "height": int(py2 - py1),
            "padding": int(context_padding),
            "max_side": int(max_work_side),
            "max_area": int(max_area) if max_area is not None else None,
        })
    return out
