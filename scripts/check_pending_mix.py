from collections import Counter

from slot_image_detector.config import load_settings
from slot_image_detector.repository import Repository


def main() -> None:
    settings = load_settings()
    repo = Repository(settings.db_path)
    rows = repo.pending_asset_capture_rows(limit=1000, max_per_provider=5)
    counts = Counter(str(row["provider_slug"]) for row in rows)
    print({"rows": len(rows), "providers": len(counts), "max_per_provider_seen": max(counts.values()) if counts else 0})
    print(list(counts.items())[:20])
    repo.close()


if __name__ == "__main__":
    main()
