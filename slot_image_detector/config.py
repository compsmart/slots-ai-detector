from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    base_dir: Path
    data_dir: Path
    db_path: Path
    library_dir: Path
    model_name: str = "umm-maybe/AI-image-detector"
    endpoint: str = "https://spinwizard.co.uk/wp-admin/admin-ajax.php"
    per_page: int = 52
    timeout_seconds: float = 30.0
    max_retries: int = 5
    retry_base_delay: float = 1.0
    unlock_email: str = "brad@compsmart.co.uk"
    asset_capture_wait_seconds: float = 20.0
    asset_max_per_game: int = 120
    headless_browser: bool = True


def load_settings() -> Settings:
    base_dir = Path(__file__).resolve().parent.parent
    data_dir = base_dir / "data"
    db_path = data_dir / "slot_detector.db"
    library_dir = data_dir / "library"
    data_dir.mkdir(parents=True, exist_ok=True)
    library_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        base_dir=base_dir,
        data_dir=data_dir,
        db_path=db_path,
        library_dir=library_dir,
        unlock_email=os.getenv("SLOT_UNLOCK_EMAIL", "brad@compsmart.co.uk"),
        asset_capture_wait_seconds=float(os.getenv("ASSET_CAPTURE_WAIT_SECONDS", "20")),
        asset_max_per_game=int(os.getenv("ASSET_MAX_PER_GAME", "120")),
        headless_browser=os.getenv("PLAYWRIGHT_HEADLESS", "true").lower() != "false",
    )
