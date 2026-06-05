from slot_image_detector.config import load_settings
from slot_image_detector.repository import Repository


def main() -> None:
    settings = load_settings()
    repo = Repository(settings.db_path)
    now = repo._now()

    repo.conn.execute(
        """
        WITH ranked AS (
                    SELECT g.id AS game_id,
                                 c.status AS status,
                 ROW_NUMBER() OVER (PARTITION BY g.provider_slug ORDER BY g.id DESC) AS rn
                    FROM games g
                    JOIN game_asset_capture c ON c.game_id = g.id
        )
        UPDATE game_asset_capture
        SET status='pending',
            last_error=NULL,
            captured_count=0,
            updated_at=?
                WHERE game_id IN (
                    SELECT game_id
                    FROM ranked
                    WHERE rn <= 5 AND status != 'success'
                )
        """,
        (now,),
    )
    repo.conn.commit()

    rows = repo.conn.execute(
        """
        WITH ranked AS (
          SELECT g.provider_slug,
                 g.id AS game_id,
                 ROW_NUMBER() OVER (PARTITION BY g.provider_slug ORDER BY g.id DESC) AS rn
          FROM games g
        )
        SELECT provider_slug, COUNT(*) AS n
        FROM ranked
        WHERE rn <= 5
        GROUP BY provider_slug
        ORDER BY provider_slug
        """
    ).fetchall()

    print({"providers": len(rows), "queued_games": sum(int(x["n"]) for x in rows)})
    repo.close()


if __name__ == "__main__":
    main()
