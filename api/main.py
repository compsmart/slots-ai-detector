from __future__ import annotations

import sqlite3
from pathlib import Path

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from slot_image_detector.repository import Repository

BASE_DIR = Path(__file__).resolve().parent.parent
DB_PATH = BASE_DIR / "data" / "slot_detector.db"
LIBRARY_DIR = BASE_DIR / "data" / "library"
AI_THRESHOLD = 0.8

app = FastAPI(title="Slot Image Detector API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


if LIBRARY_DIR.exists():
    app.mount("/library", StaticFiles(directory=str(LIBRARY_DIR)), name="library")


repo = Repository(DB_PATH)
repo.initialize()
repo.close()


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _library_url(local_path: str | None) -> str | None:
    if not local_path:
        return None
    try:
        library_rel = str(Path(local_path).resolve().relative_to(LIBRARY_DIR.resolve())).replace("\\", "/")
    except Exception:  # noqa: BLE001
        return None
    return f"/library/{library_rel}"


def _ai_status(label: str | None, score: float | None) -> str:
    if label is None or score is None:
        return "pending"
    if label.lower() == "artificial" and score >= AI_THRESHOLD:
        return "ai_detected"
    return "not_ai"


def _status_filter_clause(alias: str, ai_status: str | None) -> str:
    if ai_status == "ai":
        return f"{alias}.ai_games > 0"
    if ai_status == "not_ai":
        return f"{alias}.detected_games > 0 AND {alias}.ai_games = 0"
    if ai_status == "pending":
        return f"{alias}.detected_games = 0"
    return "1 = 1"


def _asset_filter(alias: str) -> str:
    return f"{alias}.asset_kind != 'sprite_sheet'"


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


@app.get("/api/results/summary")
def results_summary() -> dict[str, float | int]:
    conn = _connect()
    try:
        row = conn.execute(
            f"""
            WITH game_rollup AS (
              SELECT
                g.id AS game_id,
                CASE WHEN COUNT(ad.id) > 0 THEN 1 ELSE 0 END AS detected,
                MAX(CASE WHEN LOWER(ad.top_label) = 'artificial' AND ad.top_score >= ? THEN 1 ELSE 0 END) AS ai_detected
              FROM games g
              JOIN game_assets a ON a.game_id = g.id AND {_asset_filter("a")}
              LEFT JOIN asset_detections ad ON ad.asset_id = a.id
              GROUP BY g.id
            )
            SELECT
              COUNT(*) AS total_games,
              COUNT(DISTINCT g.provider_slug) AS provider_count,
              (SELECT COUNT(*) FROM game_assets a WHERE {_asset_filter("a")}) AS asset_count,
              (
                SELECT COUNT(*)
                FROM asset_detections ad
                JOIN game_assets a ON a.id = ad.asset_id
                WHERE {_asset_filter("a")}
              ) AS detected_assets,
              SUM(gr.detected) AS detected_games,
              SUM(gr.ai_detected) AS ai_games
            FROM game_rollup gr
            JOIN games g ON g.id = gr.game_id
            """,
            (AI_THRESHOLD,),
        ).fetchone()
        total_games = int(row["total_games"] or 0)
        detected_games = int(row["detected_games"] or 0)
        ai_games = int(row["ai_games"] or 0)
        asset_count = int(row["asset_count"] or 0)
        detected_assets = int(row["detected_assets"] or 0)
        return {
            "total_games": total_games,
            "provider_count": int(row["provider_count"] or 0),
            "asset_count": asset_count,
            "detected_assets": detected_assets,
            "detected_games": detected_games,
            "ai_games": ai_games,
            "ai_share": (float(ai_games) / float(detected_games)) if detected_games else 0.0,
            "asset_coverage": (float(detected_assets) / float(asset_count)) if asset_count else 0.0,
        }
    finally:
        conn.close()


@app.get("/api/results/providers")
def result_providers(
    search: str = "",
    ai_status: str | None = Query(default=None, pattern="^(ai|not_ai|pending)$"),
) -> list[dict[str, float | int | str | None]]:
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            WITH game_rollup AS (
              SELECT
                g.id AS game_id,
                g.provider_slug,
                g.provider_name,
                COUNT(a.id) AS asset_count,
                COUNT(ad.id) AS detected_assets,
                MAX(CASE WHEN LOWER(ad.top_label) = 'artificial' AND ad.top_score >= ? THEN 1 ELSE 0 END) AS ai_detected,
                MAX(ad.top_score) AS max_confidence
              FROM games g
              JOIN game_assets a ON a.game_id = g.id AND {_asset_filter("a")}
              LEFT JOIN asset_detections ad ON ad.asset_id = a.id
              GROUP BY g.id
            ),
            provider_rollup AS (
              SELECT
                provider_slug,
                provider_name,
                COUNT(game_id) AS total_games,
                SUM(CASE WHEN detected_assets > 0 THEN 1 ELSE 0 END) AS detected_games,
                SUM(ai_detected) AS ai_games,
                SUM(asset_count) AS asset_count,
                SUM(detected_assets) AS detected_assets,
                MAX(max_confidence) AS max_confidence
              FROM game_rollup
              GROUP BY provider_slug, provider_name
            )
            SELECT * FROM provider_rollup p
            WHERE (? = '' OR LOWER(provider_name) LIKE ? OR LOWER(provider_slug) LIKE ?)
              AND p.asset_count > 0
              AND {_status_filter_clause("p", ai_status)}
            ORDER BY ai_games DESC, max_confidence DESC, provider_name ASC
            """,
            (AI_THRESHOLD, search.lower(), f"%{search.lower()}%", f"%{search.lower()}%"),
        ).fetchall()
        payload = []
        for row in rows:
            detected_games = int(row["detected_games"] or 0)
            ai_games = int(row["ai_games"] or 0)
            payload.append(
                {
                    "provider_slug": str(row["provider_slug"]),
                    "provider_name": str(row["provider_name"]),
                    "total_games": int(row["total_games"] or 0),
                    "detected_games": detected_games,
                    "ai_games": ai_games,
                    "ai_share": (float(ai_games) / float(detected_games)) if detected_games else 0.0,
                    "asset_count": int(row["asset_count"] or 0),
                    "detected_assets": int(row["detected_assets"] or 0),
                    "max_confidence": float(row["max_confidence"]) if row["max_confidence"] is not None else None,
                    "status": "ai_detected" if ai_games else ("not_ai" if detected_games else "pending"),
                }
            )
        return payload
    finally:
        conn.close()


@app.get("/api/results/games")
def result_games(
    provider: str = "",
    search: str = "",
    ai_status: str | None = Query(default=None, pattern="^(ai|not_ai|pending)$"),
) -> list[dict[str, float | int | str | None]]:
    conn = _connect()
    try:
        rows = conn.execute(
            f"""
            WITH game_rollup AS (
              SELECT
                g.id,
                g.title,
                g.provider_slug,
                g.provider_name,
                COUNT(a.id) AS asset_count,
                COUNT(ad.id) AS detected_assets,
                CASE WHEN COUNT(ad.id) > 0 THEN 1 ELSE 0 END AS detected_games,
                MAX(CASE WHEN LOWER(ad.top_label) = 'artificial' AND ad.top_score >= ? THEN 1 ELSE 0 END) AS ai_games,
                MAX(ad.top_score) AS max_confidence
              FROM games g
              JOIN game_assets a ON a.game_id = g.id AND {_asset_filter("a")}
              LEFT JOIN asset_detections ad ON ad.asset_id = a.id
              GROUP BY g.id
            )
            SELECT * FROM game_rollup gr
            WHERE (? = '' OR provider_slug = ?)
              AND (? = '' OR LOWER(title) LIKE ? OR LOWER(provider_name) LIKE ?)
              AND gr.asset_count > 0
              AND {_status_filter_clause("gr", ai_status)}
            ORDER BY ai_games DESC, max_confidence DESC, id DESC
            """,
            (
                AI_THRESHOLD,
                provider,
                provider,
                search.lower(),
                f"%{search.lower()}%",
                f"%{search.lower()}%",
            ),
        ).fetchall()
        payload = []
        for row in rows:
            detected_assets = int(row["detected_assets"] or 0)
            ai_games = int(row["ai_games"] or 0)
            payload.append(
                {
                    "id": int(row["id"]),
                    "title": str(row["title"]),
                    "provider_slug": str(row["provider_slug"]),
                    "provider_name": str(row["provider_name"]),
                    "asset_count": int(row["asset_count"] or 0),
                    "detected_assets": detected_assets,
                    "ai_images": ai_games,
                    "max_confidence": float(row["max_confidence"]) if row["max_confidence"] is not None else None,
                    "status": "ai_detected" if ai_games else ("not_ai" if detected_assets else "pending"),
                }
            )
        return payload
    finally:
        conn.close()


@app.get("/api/results/images")
def result_images(
    provider: str = "",
    game_id: int | None = None,
    search: str = "",
    ai_status: str | None = Query(default=None, pattern="^(ai|not_ai|pending)$"),
) -> list[dict[str, float | int | str | None]]:
    conn = _connect()
    try:
        status_clause = "1 = 1"
        if ai_status == "ai":
            status_clause = "LOWER(ad.top_label) = 'artificial' AND ad.top_score >= :threshold"
        elif ai_status == "not_ai":
            status_clause = "ad.id IS NOT NULL AND NOT (LOWER(ad.top_label) = 'artificial' AND ad.top_score >= :threshold)"
        elif ai_status == "pending":
            status_clause = "ad.id IS NULL"

        rows = conn.execute(
            f"""
            SELECT
              a.id,
              a.game_id,
              a.asset_kind,
              a.local_path,
              a.source_host,
              g.title,
              g.provider_slug,
              g.provider_name,
              ad.top_label,
              ad.top_score
            FROM game_assets a
            JOIN games g ON g.id = a.game_id
            LEFT JOIN asset_detections ad ON ad.asset_id = a.id
            WHERE {_asset_filter("a")}
              AND (:provider = '' OR g.provider_slug = :provider)
              AND (:game_id IS NULL OR g.id = :game_id)
              AND (:search = '' OR LOWER(g.title) LIKE :search_like OR LOWER(g.provider_name) LIKE :search_like OR LOWER(a.local_path) LIKE :search_like)
              AND {status_clause}
            ORDER BY ad.top_score DESC, a.id DESC
            """,
            {
                "threshold": AI_THRESHOLD,
                "provider": provider,
                "game_id": game_id,
                "search": search.lower(),
                "search_like": f"%{search.lower()}%",
            },
        ).fetchall()
        payload = []
        for row in rows:
            top_label = str(row["top_label"]) if row["top_label"] is not None else None
            top_score = float(row["top_score"]) if row["top_score"] is not None else None
            payload.append(
                {
                    "id": int(row["id"]),
                    "game_id": int(row["game_id"]),
                    "title": str(row["title"]),
                    "provider_slug": str(row["provider_slug"]),
                    "provider_name": str(row["provider_name"]),
                    "asset_kind": str(row["asset_kind"]),
                    "source_host": str(row["source_host"]) if row["source_host"] is not None else None,
                    "image_url": _library_url(str(row["local_path"])),
                    "top_label": top_label,
                    "top_score": top_score,
                    "status": _ai_status(top_label, top_score),
                }
            )
        return payload
    finally:
        conn.close()
