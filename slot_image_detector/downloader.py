from __future__ import annotations

import random
import time
from pathlib import Path

import httpx

from .repository import Repository
from .utils import file_sha256


def _extension_from_url(url: str) -> str:
    clean = url.split("?")[0].strip().lower()
    if clean.endswith(".png"):
        return ".png"
    if clean.endswith(".webp"):
        return ".webp"
    return ".jpg"


def run_downloads(
    repo: Repository,
    library_dir: Path,
    timeout_seconds: float,
    max_retries: int,
    retry_base_delay: float,
    limit: int | None = None,
) -> dict[str, int]:
    pending = repo.pending_image_rows(limit=limit)
    downloaded = 0
    failed = 0
    skipped = 0

    for row in pending:
        game_id = int(row["id"])
        provider_slug = str(row["provider_slug"])
        game_slug = str(row["game_slug"])
        cover_url = str(row["cover_url"])

        ext = _extension_from_url(cover_url)
        target_dir = library_dir / provider_slug / game_slug
        target_dir.mkdir(parents=True, exist_ok=True)
        target_path = target_dir / f"cover{ext}"

        if target_path.exists() and target_path.stat().st_size > 0:
            checksum = file_sha256(target_path)
            repo.mark_image_downloaded(game_id, str(target_path), checksum)
            skipped += 1
            continue

        try:
            content = _fetch_bytes(cover_url, timeout_seconds, max_retries, retry_base_delay)
            target_path.write_bytes(content)
            checksum = file_sha256(target_path)
            repo.mark_image_downloaded(game_id, str(target_path), checksum)
            downloaded += 1
        except Exception as exc:  # noqa: BLE001
            repo.mark_image_error(game_id, str(exc))
            failed += 1

    return {"downloaded": downloaded, "failed": failed, "skipped": skipped}


def _fetch_bytes(url: str, timeout_seconds: float, max_retries: int, retry_base_delay: float) -> bytes:
    for attempt in range(max_retries):
        try:
            response = httpx.get(
                url,
                timeout=timeout_seconds,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                },
            )
            response.raise_for_status()
            return response.content
        except httpx.HTTPError:
            if attempt == max_retries - 1:
                raise
            delay = retry_base_delay * (2**attempt) + random.uniform(0, 0.3)
            time.sleep(delay)

    raise RuntimeError(f"Failed to download: {url}")
