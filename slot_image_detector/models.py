from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class SlotRecord:
    game_id: int
    title: str
    game_url: str
    provider_name: str
    provider_url: str
    cover_url: str


@dataclass(frozen=True)
class ProviderFilter:
    value: str
    label: str


@dataclass(frozen=True)
class DetectionResult:
    top_label: str
    top_score: float
    raw_json: str
