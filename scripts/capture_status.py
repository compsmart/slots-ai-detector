from slot_image_detector.config import load_settings
from slot_image_detector.repository import Repository


def main() -> None:
    settings = load_settings()
    repo = Repository(settings.db_path)
    rows = repo.conn.execute(
        "SELECT status, COUNT(*) AS n FROM game_asset_capture GROUP BY status ORDER BY status"
    ).fetchall()
    print([dict(x) for x in rows])
    repo.close()


if __name__ == "__main__":
    main()
