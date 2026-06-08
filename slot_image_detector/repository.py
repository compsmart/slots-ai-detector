from __future__ import annotations

import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .models import DetectionResult, SlotRecord
from .utils import safe_slug


class Repository:
    def __init__(self, db_path: Path) -> None:
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.execute("PRAGMA journal_mode=WAL;")
        self.conn.execute("PRAGMA foreign_keys=ON;")

    def close(self) -> None:
        self.conn.close()

    def initialize(self) -> None:
        self.conn.executescript(
            """
            CREATE TABLE IF NOT EXISTS providers (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                slug TEXT NOT NULL UNIQUE,
                created_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS games (
                id INTEGER PRIMARY KEY,
                title TEXT NOT NULL,
                game_slug TEXT NOT NULL,
                game_url TEXT,
                provider_id INTEGER NOT NULL,
                provider_slug TEXT NOT NULL,
                provider_name TEXT NOT NULL,
                provider_url TEXT,
                cover_url TEXT NOT NULL,
                latest_page_seen INTEGER,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(provider_id) REFERENCES providers(id)
            );

            CREATE TABLE IF NOT EXISTS images (
                game_id INTEGER PRIMARY KEY,
                local_path TEXT,
                checksum TEXT,
                status TEXT NOT NULL DEFAULT 'pending',
                last_error TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(game_id) REFERENCES games(id)
            );

            CREATE TABLE IF NOT EXISTS detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                top_label TEXT NOT NULL,
                top_score REAL NOT NULL,
                raw_json TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                UNIQUE(game_id, model_name),
                FOREIGN KEY(game_id) REFERENCES games(id)
            );

            CREATE TABLE IF NOT EXISTS crawl_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS game_asset_capture (
                game_id INTEGER PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                attempts INTEGER NOT NULL DEFAULT 0,
                last_error TEXT,
                captured_count INTEGER NOT NULL DEFAULT 0,
                last_run_at TEXT,
                updated_at TEXT NOT NULL,
                FOREIGN KEY(game_id) REFERENCES games(id)
            );

            CREATE TABLE IF NOT EXISTS game_assets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                game_id INTEGER NOT NULL,
                asset_url TEXT NOT NULL,
                local_path TEXT NOT NULL,
                mime_type TEXT,
                source_host TEXT,
                asset_kind TEXT NOT NULL DEFAULT 'in_game_asset',
                captured_at TEXT NOT NULL,
                UNIQUE(game_id, asset_url),
                FOREIGN KEY(game_id) REFERENCES games(id)
            );

            CREATE TABLE IF NOT EXISTS asset_detections (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                asset_id INTEGER NOT NULL,
                model_name TEXT NOT NULL,
                top_label TEXT NOT NULL,
                top_score REAL NOT NULL,
                raw_json TEXT NOT NULL,
                detected_at TEXT NOT NULL,
                UNIQUE(asset_id, model_name),
                FOREIGN KEY(asset_id) REFERENCES game_assets(id) ON DELETE CASCADE
            );

            CREATE INDEX IF NOT EXISTS idx_games_provider ON games(provider_slug);
            CREATE INDEX IF NOT EXISTS idx_images_status ON images(status);
            CREATE INDEX IF NOT EXISTS idx_detections_game ON detections(game_id);
            CREATE INDEX IF NOT EXISTS idx_assets_game ON game_assets(game_id);
            CREATE INDEX IF NOT EXISTS idx_asset_detections_asset ON asset_detections(asset_id);
            CREATE INDEX IF NOT EXISTS idx_asset_capture_status ON game_asset_capture(status);
            """
        )
        columns = {
            str(row["name"]) for row in self.conn.execute("PRAGMA table_info(game_assets)").fetchall()
        }
        if "asset_kind" not in columns:
            self.conn.execute(
                "ALTER TABLE game_assets ADD COLUMN asset_kind TEXT NOT NULL DEFAULT 'in_game_asset'"
            )
        self.conn.commit()

    def _now(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def get_or_create_provider(self, provider_name: str) -> tuple[int, str]:
        slug = safe_slug(provider_name)
        row = self.conn.execute(
            "SELECT id, slug FROM providers WHERE slug = ?",
            (slug,),
        ).fetchone()
        if row:
            return int(row["id"]), str(row["slug"])

        self.conn.execute(
            "INSERT INTO providers(name, slug, created_at) VALUES (?, ?, ?)",
            (provider_name, slug, self._now()),
        )
        self.conn.commit()
        row = self.conn.execute(
            "SELECT id, slug FROM providers WHERE slug = ?",
            (slug,),
        ).fetchone()
        return int(row["id"]), str(row["slug"])

    def upsert_game(self, record: SlotRecord, page_seen: int) -> None:
        provider_id, provider_slug = self.get_or_create_provider(record.provider_name)
        now = self._now()
        game_slug = safe_slug(record.title)

        self.conn.execute(
            """
            INSERT INTO games(
                id, title, game_slug, game_url, provider_id, provider_slug,
                provider_name, provider_url, cover_url, latest_page_seen,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title = excluded.title,
                game_slug = excluded.game_slug,
                game_url = excluded.game_url,
                provider_id = excluded.provider_id,
                provider_slug = excluded.provider_slug,
                provider_name = excluded.provider_name,
                provider_url = excluded.provider_url,
                cover_url = excluded.cover_url,
                latest_page_seen = excluded.latest_page_seen,
                updated_at = excluded.updated_at
            """,
            (
                record.game_id,
                record.title,
                game_slug,
                record.game_url,
                provider_id,
                provider_slug,
                record.provider_name,
                record.provider_url,
                record.cover_url,
                page_seen,
                now,
                now,
            ),
        )

        self.conn.execute(
            """
            INSERT INTO images(game_id, status, updated_at)
            VALUES (?, 'pending', ?)
            ON CONFLICT(game_id) DO NOTHING
            """,
            (record.game_id, now),
        )
        self.conn.execute(
            """
            INSERT INTO game_asset_capture(game_id, status, attempts, captured_count, updated_at)
            VALUES (?, 'pending', 0, 0, ?)
            ON CONFLICT(game_id) DO NOTHING
            """,
            (record.game_id, now),
        )
        self.conn.commit()

    def pending_asset_capture_rows(
        self,
        limit: int | None = None,
        max_per_provider: int | None = None,
    ) -> list[sqlite3.Row]:
        if max_per_provider is not None:
            sql = (
                "WITH ranked AS ("
                "  SELECT g.id, g.title, g.game_url, g.game_slug, g.provider_slug, g.cover_url, c.status, "
                "         ROW_NUMBER() OVER (PARTITION BY g.provider_slug ORDER BY g.id DESC) AS rn, "
                "         MAX(g.id) OVER (PARTITION BY g.provider_slug) AS provider_max_id "
                "  FROM games g "
                "  JOIN game_asset_capture c ON c.game_id = g.id "
                ") "
                "SELECT id, title, game_url, game_slug, provider_slug, cover_url "
                "FROM ranked WHERE rn <= ? AND status IN ('pending', 'failed') "
                "ORDER BY provider_max_id DESC, provider_slug ASC, rn ASC"
            )
            params: list[object] = [max_per_provider]
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            return list(self.conn.execute(sql, tuple(params)).fetchall())

        sql = (
            "SELECT g.id, g.title, g.game_url, g.game_slug, g.provider_slug, g.cover_url "
            "FROM games g "
            "JOIN game_asset_capture c ON c.game_id = g.id "
            "WHERE c.status IN ('pending', 'failed') "
            "ORDER BY g.id DESC"
        )
        params: tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return list(self.conn.execute(sql, params).fetchall())

    def start_asset_capture(self, game_id: int) -> None:
        self.conn.execute(
            """
            INSERT INTO game_asset_capture(game_id, status, attempts, captured_count, last_run_at, updated_at)
            VALUES (?, 'running', 1, 0, ?, ?)
            ON CONFLICT(game_id) DO UPDATE SET
                status = 'running',
                attempts = attempts + 1,
                last_error = NULL,
                last_run_at = excluded.last_run_at,
                updated_at = excluded.updated_at
            """,
            (game_id, self._now(), self._now()),
        )
        self.conn.commit()

    def save_game_asset(
        self,
        game_id: int,
        asset_url: str,
        local_path: str,
        mime_type: str | None,
        source_host: str | None,
        asset_kind: str = "in_game_asset",
    ) -> None:
        self.conn.execute(
            """
            INSERT INTO game_assets(game_id, asset_url, local_path, mime_type, source_host, asset_kind, captured_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id, asset_url) DO UPDATE SET
                local_path = excluded.local_path,
                mime_type = excluded.mime_type,
                source_host = excluded.source_host,
                asset_kind = excluded.asset_kind,
                captured_at = excluded.captured_at
            """,
            (game_id, asset_url, local_path, mime_type, source_host, asset_kind, self._now()),
        )
        self.conn.commit()

    def finish_asset_capture(self, game_id: int, captured_count: int) -> None:
        self.conn.execute(
            """
            UPDATE game_asset_capture
            SET status = 'success', captured_count = ?, last_error = NULL, last_run_at = ?, updated_at = ?
            WHERE game_id = ?
            """,
            (captured_count, self._now(), self._now(), game_id),
        )
        self.conn.commit()

    def fail_asset_capture(self, game_id: int, error: str, captured_count: int = 0) -> None:
        self.conn.execute(
            """
            UPDATE game_asset_capture
            SET status = 'failed', last_error = ?, captured_count = ?, last_run_at = ?, updated_at = ?
            WHERE game_id = ?
            """,
            (error[:2000], captured_count, self._now(), self._now(), game_id),
        )
        self.conn.commit()

    def get_state(self, key: str, default: str = "") -> str:
        row = self.conn.execute(
            "SELECT value FROM crawl_state WHERE key = ?",
            (key,),
        ).fetchone()
        return str(row["value"]) if row else default

    def set_state(self, key: str, value: str) -> None:
        self.conn.execute(
            """
            INSERT INTO crawl_state(key, value, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(key) DO UPDATE SET
                value = excluded.value,
                updated_at = excluded.updated_at
            """,
            (key, value, self._now()),
        )
        self.conn.commit()

    def pending_image_rows(
        self,
        limit: int | None = None,
        max_per_provider: int | None = None,
    ) -> list[sqlite3.Row]:
        if max_per_provider is not None:
            sql = (
                "WITH ranked AS ("
                "  SELECT g.id, g.title, g.game_slug, g.provider_slug, g.cover_url, i.status, "
                "         ROW_NUMBER() OVER (PARTITION BY g.provider_slug ORDER BY g.id DESC) AS rn, "
                "         MAX(g.id) OVER (PARTITION BY g.provider_slug) AS provider_max_id "
                "  FROM images i JOIN games g ON g.id = i.game_id "
                ") "
                "SELECT id, title, game_slug, provider_slug, cover_url "
                "FROM ranked WHERE rn <= ? AND status IN ('pending','failed') "
                "ORDER BY provider_max_id DESC, provider_slug ASC, rn ASC"
            )
            params: list[object] = [max_per_provider]
            if limit is not None:
                sql += " LIMIT ?"
                params.append(limit)
            return list(self.conn.execute(sql, tuple(params)).fetchall())

        sql = (
            "SELECT g.id, g.title, g.game_slug, g.provider_slug, g.cover_url "
            "FROM images i JOIN games g ON g.id = i.game_id "
            "WHERE i.status IN ('pending','failed') ORDER BY g.id DESC"
        )
        params: tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return list(self.conn.execute(sql, params).fetchall())

    def mark_image_downloaded(self, game_id: int, local_path: str, checksum: str) -> None:
        self.conn.execute(
            """
            UPDATE images
            SET local_path = ?, checksum = ?, status = 'downloaded', last_error = NULL, updated_at = ?
            WHERE game_id = ?
            """,
            (local_path, checksum, self._now(), game_id),
        )
        self.conn.commit()

    def mark_image_error(self, game_id: int, error: str) -> None:
        self.conn.execute(
            """
            UPDATE images
            SET status = 'failed', last_error = ?, updated_at = ?
            WHERE game_id = ?
            """,
            (error[:2000], self._now(), game_id),
        )
        self.conn.commit()

    def game_asset_rows(self, limit: int | None = None) -> list[sqlite3.Row]:
        sql = (
            "SELECT id, game_id, asset_url, local_path, asset_kind "
            "FROM game_assets "
            "WHERE asset_kind != 'cover_photo' "
            "ORDER BY id DESC"
        )
        params: tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (limit,)
        return list(self.conn.execute(sql, params).fetchall())

    def update_game_asset_kind(self, asset_id: int, asset_kind: str) -> None:
        self.conn.execute(
            """
            UPDATE game_assets
            SET asset_kind = ?
            WHERE id = ?
            """,
            (asset_kind, asset_id),
        )
        self.conn.commit()

    def pending_asset_detection_rows(self, model_name: str, limit: int | None = None) -> list[sqlite3.Row]:
        sql = (
            "SELECT a.id, a.game_id, a.local_path, a.asset_kind, g.title, g.provider_slug "
            "FROM game_assets a "
            "JOIN games g ON g.id = a.game_id "
            "WHERE a.asset_kind = 'in_game_asset' "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM asset_detections d WHERE d.asset_id = a.id AND d.model_name = ?"
            ") "
            "ORDER BY a.id DESC"
        )
        params: list[object] = [model_name]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(sql, tuple(params)).fetchall())

    def save_asset_detection(self, asset_id: int, model_name: str, result: DetectionResult) -> None:
        self.conn.execute(
            """
            INSERT INTO asset_detections(asset_id, model_name, top_label, top_score, raw_json, detected_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(asset_id, model_name) DO UPDATE SET
                top_label = excluded.top_label,
                top_score = excluded.top_score,
                raw_json = excluded.raw_json,
                detected_at = excluded.detected_at
            """,
            (
                asset_id,
                model_name,
                result.top_label,
                result.top_score,
                result.raw_json,
                self._now(),
            ),
        )
        self.conn.commit()

    def mark_image_skipped(self, game_id: int, reason: str) -> None:
        self.conn.execute(
            """
            UPDATE images
            SET status = 'skipped', last_error = ?, updated_at = ?
            WHERE game_id = ?
            """,
            (reason[:2000], self._now(), game_id),
        )
        self.conn.commit()

    def pending_detection_rows(self, model_name: str, limit: int | None = None) -> list[sqlite3.Row]:
        sql = (
            "SELECT g.id, g.title, g.provider_slug, i.local_path "
            "FROM images i JOIN games g ON g.id = i.game_id "
            "WHERE i.status = 'downloaded' AND i.local_path IS NOT NULL "
            "AND NOT EXISTS ("
            "  SELECT 1 FROM detections d WHERE d.game_id = g.id AND d.model_name = ?"
            ") ORDER BY g.id DESC"
        )
        params: list[object] = [model_name]
        if limit is not None:
            sql += " LIMIT ?"
            params.append(limit)
        return list(self.conn.execute(sql, tuple(params)).fetchall())

    def save_detection(self, game_id: int, model_name: str, result: DetectionResult) -> None:
        self.conn.execute(
            """
            INSERT INTO detections(game_id, model_name, top_label, top_score, raw_json, detected_at)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(game_id, model_name) DO UPDATE SET
                top_label = excluded.top_label,
                top_score = excluded.top_score,
                raw_json = excluded.raw_json,
                detected_at = excluded.detected_at
            """,
            (
                game_id,
                model_name,
                result.top_label,
                result.top_score,
                result.raw_json,
                self._now(),
            ),
        )
        self.conn.execute(
            "UPDATE images SET status = 'detected', updated_at = ? WHERE game_id = ?",
            (self._now(), game_id),
        )
        self.conn.commit()

    def summary(self) -> dict[str, float | int]:
        total_games = self.conn.execute("SELECT COUNT(*) AS c FROM games").fetchone()["c"]
        downloaded = self.conn.execute("SELECT COUNT(*) AS c FROM images WHERE status IN ('downloaded','detected')").fetchone()["c"]
        detected = self.conn.execute("SELECT COUNT(*) AS c FROM detections").fetchone()["c"]
        ai_count = self.conn.execute(
            "SELECT COUNT(*) AS c FROM detections WHERE LOWER(top_label) LIKE '%ai%'"
        ).fetchone()["c"]
        ai_share = (float(ai_count) / float(detected)) if detected else 0.0
        assets = self.conn.execute("SELECT COUNT(*) AS c FROM game_assets").fetchone()["c"]
        return {
            "total_games": int(total_games),
            "images_downloaded": int(downloaded),
            "detections": int(detected),
            "ai_count": int(ai_count),
            "ai_share": ai_share,
            "game_assets": int(assets),
        }
