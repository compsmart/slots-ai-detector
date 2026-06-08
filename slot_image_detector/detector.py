from __future__ import annotations

import json
from pathlib import Path

from transformers import pipeline

from .models import DetectionResult
from .repository import Repository
from .sprite_sheet import analyze_sprite_sheet


class AICoverDetector:
    def __init__(self, model_name: str) -> None:
        self.model_name = model_name
        self._pipe = None

    @property
    def pipe(self):
        if self._pipe is None:
            self._pipe = pipeline("image-classification", model=self.model_name)
        return self._pipe

    def classify(self, image_path: Path) -> DetectionResult:
        raw = self.pipe(str(image_path))
        top = raw[0] if raw else {"label": "unknown", "score": 0.0}
        return DetectionResult(
            top_label=str(top.get("label", "unknown")),
            top_score=float(top.get("score", 0.0)),
            raw_json=json.dumps(raw, ensure_ascii=True),
        )


def run_detection(repo: Repository, detector: AICoverDetector, limit: int | None = None) -> dict[str, int]:
    rows = repo.pending_detection_rows(model_name=detector.model_name, limit=limit)
    processed = 0
    failed = 0
    skipped_sprite_sheets = 0

    for row in rows:
        game_id = int(row["id"])
        local_path = Path(str(row["local_path"]))
        if not local_path.exists():
            repo.mark_image_error(game_id, f"Missing image path: {local_path}")
            failed += 1
            continue

        try:
            sprite_sheet = analyze_sprite_sheet(local_path)
            if sprite_sheet.is_sprite_sheet:
                repo.mark_image_skipped(game_id, f"sprite sheet: {sprite_sheet.reason}")
                skipped_sprite_sheets += 1
                continue

            result = detector.classify(local_path)
            repo.save_detection(game_id=game_id, model_name=detector.model_name, result=result)
            processed += 1
        except Exception as exc:  # noqa: BLE001
            repo.mark_image_error(game_id, str(exc))
            failed += 1

    return {"processed": processed, "failed": failed, "skipped_sprite_sheets": skipped_sprite_sheets}


def run_asset_detection(repo: Repository, detector: AICoverDetector, limit: int | None = None) -> dict[str, int]:
    rows = repo.pending_asset_detection_rows(model_name=detector.model_name, limit=limit)
    processed = 0
    failed = 0
    skipped_sprite_sheets = 0
    missing = 0

    for row in rows:
        asset_id = int(row["id"])
        image_path = Path(str(row["local_path"]))
        if not image_path.exists():
            missing += 1
            continue

        try:
            sprite_sheet = analyze_sprite_sheet(image_path)
            if sprite_sheet.is_sprite_sheet:
                repo.update_game_asset_kind(asset_id, "sprite_sheet")
                skipped_sprite_sheets += 1
                continue

            result = detector.classify(image_path)
            repo.save_asset_detection(asset_id=asset_id, model_name=detector.model_name, result=result)
            processed += 1
        except Exception:  # noqa: BLE001
            failed += 1

    return {
        "processed": processed,
        "failed": failed,
        "missing": missing,
        "skipped_sprite_sheets": skipped_sprite_sheets,
    }


def tag_sprite_sheet_assets(repo: Repository, limit: int | None = None) -> dict[str, int]:
    rows = repo.game_asset_rows(limit=limit)
    checked = 0
    tagged = 0
    missing = 0

    for row in rows:
        asset_id = int(row["id"])
        image_path = Path(str(row["local_path"]))
        if not image_path.exists():
            missing += 1
            continue

        checked += 1
        analysis = analyze_sprite_sheet(image_path)
        if analysis.is_sprite_sheet:
            repo.update_game_asset_kind(asset_id, "sprite_sheet")
            tagged += 1

    return {"checked": checked, "tagged_sprite_sheets": tagged, "missing": missing}
