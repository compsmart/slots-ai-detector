from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class SpriteSheetAnalysis:
    is_sprite_sheet: bool
    reason: str
    width: int
    height: int
    transparent_ratio: float
    opaque_component_count: int
    opaque_coverage_ratio: float
    power_of_two_like: bool


def analyze_sprite_sheet(image_path: Path) -> SpriteSheetAnalysis:
    with Image.open(image_path) as image:
        rgba = image.convert("RGBA")
        width, height = rgba.size
        alpha = np.asarray(rgba.getchannel("A"))

    transparent_ratio = float(np.mean(alpha < 16))
    opaque_mask = alpha >= 16
    opaque_coverage_ratio = float(np.mean(opaque_mask))
    component_count = _count_opaque_components(opaque_mask)
    power_of_two_like = _is_power_of_two_like(width) and _is_power_of_two_like(height)

    is_sheet = False
    reasons: list[str] = []

    if width >= 512 and height >= 512 and transparent_ratio >= 0.20 and component_count >= 8:
        is_sheet = True
        reasons.append("many separated transparent sprites")

    if width >= 1024 and height >= 512 and transparent_ratio >= 0.35 and component_count >= 4:
        is_sheet = True
        reasons.append("large transparent packed atlas")

    if power_of_two_like and width >= 512 and height >= 512 and transparent_ratio >= 0.25 and opaque_coverage_ratio <= 0.80:
        is_sheet = True
        reasons.append("power-of-two atlas with transparency")

    return SpriteSheetAnalysis(
        is_sprite_sheet=is_sheet,
        reason=", ".join(reasons) if reasons else "not sprite-sheet-like",
        width=width,
        height=height,
        transparent_ratio=transparent_ratio,
        opaque_component_count=component_count,
        opaque_coverage_ratio=opaque_coverage_ratio,
        power_of_two_like=power_of_two_like,
    )


def is_likely_sprite_sheet(image_path: Path) -> bool:
    try:
        return analyze_sprite_sheet(image_path).is_sprite_sheet
    except Exception:  # noqa: BLE001
        return False


def _count_opaque_components(mask: np.ndarray) -> int:
    if mask.size == 0:
        return 0

    max_side = max(mask.shape)
    if max_side > 768:
        scale = 768 / float(max_side)
        new_width = max(1, int(mask.shape[1] * scale))
        new_height = max(1, int(mask.shape[0] * scale))
        image = Image.fromarray(mask.astype(np.uint8) * 255, mode="L")
        mask = np.asarray(image.resize((new_width, new_height), Image.Resampling.NEAREST)) > 0

    visited = np.zeros(mask.shape, dtype=bool)
    height, width = mask.shape
    min_area = max(16, int(mask.size * 0.00025))
    components = 0

    for y in range(height):
        for x in range(width):
            if not mask[y, x] or visited[y, x]:
                continue
            area = _flood_fill_area(mask, visited, x, y)
            if area >= min_area:
                components += 1
                if components >= 32:
                    return components

    return components


def _flood_fill_area(mask: np.ndarray, visited: np.ndarray, start_x: int, start_y: int) -> int:
    height, width = mask.shape
    stack = [(start_x, start_y)]
    visited[start_y, start_x] = True
    area = 0

    while stack:
        x, y = stack.pop()
        area += 1
        for nx, ny in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if nx < 0 or ny < 0 or nx >= width or ny >= height:
                continue
            if visited[ny, nx] or not mask[ny, nx]:
                continue
            visited[ny, nx] = True
            stack.append((nx, ny))

    return area


def _is_power_of_two_like(value: int) -> bool:
    powers = (256, 512, 1024, 2048, 4096)
    return any(abs(value - power) <= 8 for power in powers)
