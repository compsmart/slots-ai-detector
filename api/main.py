from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "slot_detector.db"
LIBRARY_DIR = BASE_DIR / "data" / "library"

app = FastAPI(title="Slot Image Detector API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


if LIBRARY_DIR.exists():
    app.mount("/library", StaticFiles(directory=str(LIBRARY_DIR)), name="library")


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/api/summary")
def summary() -> dict[str, float | int]:
    conn = _connect()
    try:
        total_games = conn.execute("SELECT COUNT(*) AS c FROM games").fetchone()["c"]
        detected = conn.execute("SELECT COUNT(*) AS c FROM detections").fetchone()["c"]
        ai_count = conn.execute(
            "SELECT COUNT(*) AS c FROM detections WHERE LOWER(top_label) LIKE '%ai%'"
        ).fetchone()["c"]
        avg_conf = conn.execute("SELECT AVG(top_score) AS v FROM detections").fetchone()["v"]
        provider_count = conn.execute("SELECT COUNT(*) AS c FROM providers").fetchone()["c"]
        return {
            "total_games": int(total_games),
            "detected_games": int(detected),
            "ai_count": int(ai_count),
            "ai_share": float(ai_count) / float(detected) if detected else 0.0,
            "avg_confidence": float(avg_conf) if avg_conf is not None else 0.0,
            "provider_count": int(provider_count),
        }
    finally:
        conn.close()


@app.get("/api/providers")
def providers() -> list[dict[str, float | int | str]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
              g.provider_slug,
              g.provider_name,
              COUNT(g.id) AS total_games,
              SUM(CASE WHEN LOWER(d.top_label) LIKE '%ai%' THEN 1 ELSE 0 END) AS ai_games,
              AVG(d.top_score) AS avg_confidence
            FROM games g
            LEFT JOIN detections d ON d.game_id = g.id
            GROUP BY g.provider_slug, g.provider_name
            HAVING COUNT(g.id) > 0
            ORDER BY ai_games DESC, avg_confidence DESC
            """
        ).fetchall()
        payload = []
        for row in rows:
            total_games = int(row["total_games"])
            ai_games = int(row["ai_games"] or 0)
            payload.append(
                {
                    "provider_slug": str(row["provider_slug"]),
                    "provider_name": str(row["provider_name"]),
                    "total_games": total_games,
                    "ai_games": ai_games,
                    "ai_share": (float(ai_games) / float(total_games)) if total_games else 0.0,
                    "avg_confidence": float(row["avg_confidence"] or 0.0),
                }
            )
        return payload
    finally:
        conn.close()


@app.get("/api/games")
def games(
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    provider: str | None = None,
    ai_only: bool = False,
) -> list[dict[str, float | int | str | None]]:
    conn = _connect()
    try:
        where = []
        params: list[object] = []
        if provider:
            where.append("g.provider_slug = ?")
            params.append(provider)
        if ai_only:
            where.append("LOWER(d.top_label) LIKE '%ai%'")

        clause = f"WHERE {' AND '.join(where)}" if where else ""

        query = (
            "SELECT g.id, g.title, g.provider_slug, g.provider_name, g.cover_url, "
            "i.local_path, d.top_label, d.top_score "
            "FROM games g "
            "LEFT JOIN images i ON i.game_id = g.id "
            "LEFT JOIN detections d ON d.game_id = g.id "
            f"{clause} "
            "ORDER BY g.id DESC LIMIT ? OFFSET ?"
        )
        params.extend([limit, offset])
        rows = conn.execute(query, tuple(params)).fetchall()

        payload = []
        for row in rows:
            local_path = row["local_path"]
            library_rel = None
            if local_path:
                try:
                    library_rel = str(Path(str(local_path)).resolve().relative_to(LIBRARY_DIR.resolve())).replace("\\", "/")
                except Exception:  # noqa: BLE001
                    library_rel = None
            payload.append(
                {
                    "id": int(row["id"]),
                    "title": str(row["title"]),
                    "provider_slug": str(row["provider_slug"]),
                    "provider_name": str(row["provider_name"]),
                    "cover_url": str(row["cover_url"]),
                    "library_image": f"/library/{library_rel}" if library_rel else None,
                    "top_label": str(row["top_label"]) if row["top_label"] is not None else None,
                    "top_score": float(row["top_score"]) if row["top_score"] is not None else None,
                }
            )
        return payload
    finally:
        conn.close()


@app.get("/api/confidence-distribution")
def confidence_distribution() -> list[dict[str, int]]:
    conn = _connect()
    try:
        rows = conn.execute(
            """
            SELECT
              CASE
                WHEN top_score < 0.2 THEN '0.0-0.2'
                WHEN top_score < 0.4 THEN '0.2-0.4'
                WHEN top_score < 0.6 THEN '0.4-0.6'
                WHEN top_score < 0.8 THEN '0.6-0.8'
                ELSE '0.8-1.0'
              END AS bucket,
              COUNT(*) AS count
            FROM detections
            GROUP BY bucket
            ORDER BY bucket
            """
        ).fetchall()
        return [{"bucket": str(r["bucket"]), "count": int(r["count"])} for r in rows]
    finally:
        conn.close()
