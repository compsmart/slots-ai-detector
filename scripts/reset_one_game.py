from pathlib import Path
import shutil

from slot_image_detector.config import load_settings
from slot_image_detector.repository import Repository


GAME_ID = 52766
ASSET_DIR = Path("data/library/elk-studios/cyber-heist-city/assets")


def main() -> None:
    settings = load_settings()
    repo = Repository(settings.db_path)
    now = repo._now()

    repo.conn.execute("DELETE FROM game_assets WHERE game_id = ?", (GAME_ID,))
    repo.conn.execute(
        """
        UPDATE game_asset_capture
        SET status='pending', last_error=NULL, captured_count=0, updated_at=?
        WHERE game_id=?
        """,
        (now, GAME_ID),
    )
    repo.conn.commit()
    repo.close()

    shutil.rmtree(ASSET_DIR, ignore_errors=True)
    print("reset complete", GAME_ID)


if __name__ == "__main__":
    main()
