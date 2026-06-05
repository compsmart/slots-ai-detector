from pathlib import Path
import shutil

from slot_image_detector.config import load_settings
from slot_image_detector.repository import Repository


def main() -> None:
    settings = load_settings()
    repo = Repository(settings.db_path)
    repo.initialize()
    now = repo._now()

    repo.conn.execute("DELETE FROM game_assets")
    repo.conn.execute(
        """
        UPDATE game_asset_capture
        SET status='pending', attempts=0, last_error=NULL, captured_count=0, last_run_at=NULL, updated_at=?
        """,
        (now,),
    )
    repo.conn.commit()
    repo.close()

    library = settings.library_dir
    if library.exists():
        for assets_dir in library.rglob("assets"):
            if assets_dir.is_dir():
                shutil.rmtree(assets_dir, ignore_errors=True)

    print("asset scrape state reset")


if __name__ == "__main__":
    main()
