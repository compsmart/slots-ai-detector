from __future__ import annotations

import hashlib
import json
import shutil
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import unquote, urlparse

import httpx
from playwright.sync_api import BrowserContext, Page, Response, sync_playwright

from .repository import Repository

_IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".bmp", ".avif"}
_GAME_ASSET_EXT = {".png", ".webp"}
_BLACKLISTED_FILENAMES = {
    "irondog.png",
    "eclipse_glow.png",
    "eclipse.png",
    "zs0kkgxe36.png",
    "age-checked-trans.png",
    "rocket-logo.webp",
    "rocket-solo.webp",
    "18-1.png",
    "agechecked_short_logo.png",
    "1109275708-1.png",
    "comodo_secure.png",
    "cropped-spinwizard-logo.png",
    "gamcare-1.jpg",
    "gb.png",
    "load.gif",
    "pci-logo.png",
    "spinwizard-mystery-offer-500-x-1000-px-1.png",
    "fg.png",
    "logo.webp"
}
_SLOTSLAUNCH_IFRAME_RE = re.compile(r"https://slotslaunch\.com/iframe/[^\"'\s<>]+", re.IGNORECASE)


def run_asset_capture(
    repo: Repository,
    library_dir: Path,
    unlock_email: str,
    wait_seconds: float,
    max_per_game: int,
    headless: bool,
    limit: int | None = None,
    max_per_provider: int | None = None,
) -> dict[str, int]:
    rows = repo.pending_asset_capture_rows(limit=limit, max_per_provider=max_per_provider)
    processed = 0
    succeeded = 0
    failed = 0
    total_assets = 0
    logger = _CaptureLogger(library_dir.parent / "logs" / "asset_capture.log")

    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=headless)
        try:
            context = browser.new_context(viewport={"width": 1600, "height": 900})
            for row in rows:
                game_id = int(row["id"])
                game_title = str(row["title"])
                game_url = str(row["game_url"])
                provider_slug = str(row["provider_slug"])
                game_slug = str(row["game_slug"])
                cover_url = str(row["cover_url"] or "")
                game_meta = {
                    "game_id": game_id,
                    "title": game_title,
                    "provider_slug": provider_slug,
                    "game_url": game_url,
                }

                processed += 1
                repo.start_asset_capture(game_id)
                logger.log("game_start", {**game_meta, "headless": headless})

                try:
                    captured = _capture_assets_for_game(
                        context=context,
                        game_url=game_url,
                        cover_url=cover_url,
                        unlock_email=unlock_email,
                        output_dir=library_dir / provider_slug / game_slug / "assets",
                        max_per_game=max_per_game,
                        wait_seconds=wait_seconds,
                        logger=logger,
                        game_meta=game_meta,
                    )
                    for item in captured:
                        repo.save_game_asset(
                            game_id=game_id,
                            asset_url=item["asset_url"],
                            local_path=item["local_path"],
                            mime_type=item.get("mime_type"),
                            source_host=item.get("source_host"),
                            asset_kind=str(item.get("asset_kind") or "in_game_asset"),
                        )

                    repo.finish_asset_capture(game_id, captured_count=len(captured))
                    succeeded += 1
                    total_assets += len(captured)
                    logger.log("game_success", {**game_meta, "captured_assets": len(captured)})
                    print(f"asset-capture success game={game_id} title={game_title} assets={len(captured)}")
                except Exception as exc:  # noqa: BLE001
                    repo.fail_asset_capture(game_id, str(exc))
                    failed += 1
                    logger.log("game_error", {**game_meta, "error": str(exc)})
                    print(f"asset-capture failed game={game_id} title={game_title} error={exc}")
        finally:
            browser.close()

    return {
        "processed_games": processed,
        "successful_games": succeeded,
        "failed_games": failed,
        "captured_assets": total_assets,
    }


def _capture_assets_for_game(
    context: BrowserContext,
    game_url: str,
    cover_url: str,
    unlock_email: str,
    output_dir: Path,
    max_per_game: int,
    wait_seconds: float,
    logger: "_CaptureLogger",
    game_meta: dict[str, object],
) -> list[dict[str, str | None]]:
    page = context.new_page()
    captured_urls: set[str] = set()
    captured_rows: list[dict[str, str | None]] = []
    game_started = False

    output_dir.mkdir(parents=True, exist_ok=True)
    _prime_agecheck_state(context)
    cover_captured = False
    normalized_cover = _normalize_asset_url(cover_url)

    def handle_response(response: Response) -> None:
        try:
            if len(captured_rows) >= max_per_game:
                return

            url = response.url
            url_key = _normalize_asset_url(url)
            if url_key in captured_urls:
                return

            if not _looks_like_image_url(url):
                ctype = (response.headers.get("content-type") or "").lower()
                if not ctype.startswith("image/"):
                    return

            status = response.status
            if status < 200 or status >= 300:
                return

            body = response.body()
            if not body or len(body) < 1024:
                return

            asset_kind = "cover_photo" if normalized_cover and _normalize_asset_url(url) == normalized_cover else "in_game_asset"
            ext = _extension_from_response(url, response.headers.get("content-type") or "")

            if asset_kind != "cover_photo":
                if not game_started:
                    return
                if ext not in _GAME_ASSET_EXT:
                    return
                if _is_non_game_host(url):
                    return

            filename = (
                f"cover_photo{ext}"
                if asset_kind == "cover_photo"
                else _original_filename(url=url, fallback_ext=ext)
            )
            if asset_kind != "cover_photo" and filename.lower() in _BLACKLISTED_FILENAMES:
                return
            filename = _ensure_unique_filename(output_dir=output_dir, filename=filename, seed_url=url)
            local_path = output_dir / filename
            local_path.write_bytes(body)

            source_host = urlparse(url).netloc
            if asset_kind == "cover_photo":
                nonlocal cover_captured
                cover_captured = True
            captured_urls.add(url_key)
            captured_rows.append(
                {
                    "asset_url": url,
                    "local_path": str(local_path),
                    "mime_type": response.headers.get("content-type"),
                    "source_host": source_host,
                    "asset_kind": asset_kind,
                }
            )
        except Exception:  # noqa: BLE001
            return

    page.on("response", handle_response)
    logger.log("navigate", {**game_meta, "url": game_url})
    page.goto(game_url, wait_until="domcontentloaded", timeout=60000)
    resolved_cover_url = _resolve_cover_url(page, cover_url)
    logger.log("cover_resolved", {**game_meta, "cover_url": resolved_cover_url})
    normalized_cover = _normalize_asset_url(resolved_cover_url)
    _accept_cookie_consent(page)
    _dismiss_popups(page)
    _unlock_game(page, unlock_email)
    launch_attempted = _start_game(page)
    slotslaunch_loaded = _wait_for_slotslaunch_frame(page, timeout_ms=8000)

    injected_iframe_url: str | None = None
    if not slotslaunch_loaded:
        injected_iframe_url = _extract_slotslaunch_iframe_url(page)
        if injected_iframe_url:
            _inject_slotslaunch_iframe(page, injected_iframe_url)
            logger.log("launcher_iframe_injected", {**game_meta, "iframe_url": injected_iframe_url})
            slotslaunch_loaded = _wait_for_slotslaunch_frame(page, timeout_ms=8000)

    game_started = slotslaunch_loaded
    logger.log(
        "launcher_click",
        {
            **game_meta,
            "launch_attempted": launch_attempted,
            "slotslaunch_loaded": slotslaunch_loaded,
            "game_started": game_started,
        },
    )
    _log_frame_snapshot(page, logger, game_meta, "post_launch")

    # Try to pass age gate when present.
    verify_count = _click_verify_age_gate(page)
    if verify_count:
        logger.log("age_gate_click", {**game_meta, "count": verify_count})

    # Give nested frames time to request in-game asset bundles and images.
    deadline = time.time() + wait_seconds
    next_snapshot = time.time() + 4.0
    while time.time() < deadline and len(captured_rows) < max_per_game:
        verify_count = _click_verify_age_gate(page)
        if verify_count:
            logger.log("age_gate_click", {**game_meta, "count": verify_count})
        if time.time() >= next_snapshot:
            _log_frame_snapshot(page, logger, game_meta, "wait_loop")
            next_snapshot = time.time() + 4.0
        page.wait_for_timeout(500)

    if normalized_cover and not cover_captured:
        fallback = _capture_cover_photo_via_request(context, resolved_cover_url, output_dir)
        if fallback is not None:
            captured_urls.add(_normalize_asset_url(resolved_cover_url))
            cover_captured = True
            captured_rows.append(fallback)
            logger.log("cover_fallback_downloaded", {**game_meta, "cover_url": resolved_cover_url})

    if captured_rows and not any((row.get("asset_kind") == "cover_photo") for row in captured_rows):
        preferred = None
        for row in captured_rows:
            host = str(row.get("source_host") or "")
            url = str(row.get("asset_url") or "")
            if "assets.slotslaunch.com" in host and not url.lower().endswith((".gif", ".ico")):
                preferred = row
                break
        if preferred is None:
            preferred = captured_rows[0]
        preferred["asset_kind"] = "cover_photo"
        if preferred.get("local_path"):
            preferred["local_path"] = _ensure_cover_alias(output_dir, str(preferred["local_path"]))

    captured_rows = _enforce_max_rows(captured_rows, max_per_game)

    page.close()
    logger.log("capture_complete", {**game_meta, "captured_rows": len(captured_rows)})
    return captured_rows


def _enforce_max_rows(
    rows: list[dict[str, str | None]],
    max_per_game: int,
) -> list[dict[str, str | None]]:
    if len(rows) <= max_per_game:
        return rows

    cover_index = next((idx for idx, row in enumerate(rows) if row.get("asset_kind") == "cover_photo"), None)
    if cover_index is None:
        return rows[:max_per_game]

    # Keep cover and fill remaining slots with earliest captured assets.
    out: list[dict[str, str | None]] = [rows[cover_index]]
    for idx, row in enumerate(rows):
        if idx == cover_index:
            continue
        out.append(row)
        if len(out) >= max_per_game:
            break
    return out


def _capture_cover_photo_via_request(
    context: BrowserContext,
    cover_url: str,
    output_dir: Path,
) -> dict[str, str | None] | None:
    try:
        response = httpx.get(
            cover_url,
            timeout=30.0,
            follow_redirects=True,
            trust_env=True,
            verify=False,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 (KHTML, like Gecko) "
                    "Chrome/126.0.0.0 Safari/537.36"
                )
            },
        )
        response.raise_for_status()
        if response.status_code < 200 or response.status_code >= 300:
            return None
        body = response.content
        if not body:
            return None
        ext = _extension_from_response(cover_url, response.headers.get("content-type") or "")
        local_path = output_dir / f"cover_photo{ext}"
        local_path.write_bytes(body)
        return {
            "asset_url": cover_url,
            "local_path": str(local_path),
            "mime_type": response.headers.get("content-type"),
            "source_host": urlparse(cover_url).netloc,
            "asset_kind": "cover_photo",
        }
    except Exception:  # noqa: BLE001
        return None


def _prime_agecheck_state(context: BrowserContext) -> None:
    try:
        context.add_cookies(
            [
                {
                    "name": "av-checked",
                    "value": "1",
                    "domain": "slotslaunch.com",
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                },
                {
                    "name": "av-checked",
                    "value": "1",
                    "domain": ".slotslaunch.com",
                    "path": "/",
                    "httpOnly": False,
                    "secure": True,
                },
            ]
        )
    except Exception:  # noqa: BLE001
        return


def _normalize_asset_url(url: str) -> str:
    return url.split("?", 1)[0].strip().lower()


def _original_filename(url: str, fallback_ext: str) -> str:
    path_name = Path(unquote(urlparse(url).path)).name.strip()
    if not path_name:
        return f"asset{fallback_ext}"

    sanitized = re.sub(r"[^A-Za-z0-9._-]", "-", path_name)
    if not Path(sanitized).suffix:
        sanitized = f"{sanitized}{fallback_ext}"
    return sanitized.lower()


def _ensure_unique_filename(output_dir: Path, filename: str, seed_url: str) -> str:
    target = output_dir / filename
    if not target.exists():
        return filename

    stem = Path(filename).stem
    ext = Path(filename).suffix
    digest = hashlib.sha256(seed_url.encode("utf-8")).hexdigest()[:8]
    return f"{stem}-{digest}{ext}"


def _ensure_cover_alias(output_dir: Path, existing_path: str) -> str:
    src = Path(existing_path)
    if not src.exists():
        return existing_path
    ext = src.suffix if src.suffix else ".jpg"
    dst = output_dir / f"cover_photo{ext}"
    if src.resolve() == dst.resolve():
        return str(dst)
    shutil.copy2(src, dst)
    return str(dst)


def _resolve_cover_url(page: Page, provided_cover_url: str) -> str:
    for _ in range(4):
        try:
            from_page = page.evaluate(
                """
                () => {
                  const slotsAssets = Array.from(document.querySelectorAll("img[src*='assets.slotslaunch.com']"));
                  if (slotsAssets.length > 0) {
                    const src = slotsAssets[0].getAttribute('src') || '';
                    if (src) return src;
                  }

                  const og = document.querySelector("meta[property='og:image']");
                  const twitter = document.querySelector("meta[name='twitter:image']");
                  const img = og || twitter;
                  return img ? (img.getAttribute('content') || '') : '';
                }
                """
            )
            if from_page and str(from_page).strip():
                return str(from_page).strip()
        except Exception:  # noqa: BLE001
            pass
        page.wait_for_timeout(1000)
    return provided_cover_url


def _dismiss_popups(page: Page) -> None:
    _accept_cookie_consent(page)

    selectors: Iterable[str] = [
        "button:has-text('Allow all')",
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "button:has-text('Allow selection')",
        "button[aria-label='Close']",
        ".sw-popup-box button",
        "#exit-popup button",
        ".sw-popup-close",
    ]
    for selector in selectors:
        _click_if_visible(page, selector)

    page.evaluate(
        """
        () => {
          const selectors = ['.exit-popup', '.exit-popup-overlay', '.sw-popup', '.sw-popup-box'];
          selectors.forEach((selector) => {
            document.querySelectorAll(selector).forEach((el) => {
              el.remove();
            });
          });
        }
        """
    )


def _accept_cookie_consent(page: Page) -> None:
    # Try in main document.
    for selector in [
        "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
        "button:has-text('Allow all')",
        "button:has-text('Allow selection')",
    ]:
        _click_if_visible(page, selector)

    # Try inside consent iframe variants.
    for frame in page.frames:
        for selector in [
            "button:has-text('Allow all')",
            "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
            "button:has-text('Allow selection')",
        ]:
            try:
                locator = frame.locator(selector).first
                if locator.count() > 0:
                    locator.click(force=True, timeout=1000)
            except Exception:  # noqa: BLE001
                continue


def _unlock_game(page: Page, unlock_email: str) -> None:
    email_input = page.locator("input[placeholder='Enter Your Email Here...']").first
    if email_input.count() > 0:
        email_input.fill(unlock_email)

    consent = page.locator("input[type='checkbox']").first
    if consent.count() > 0:
        try:
            if not consent.is_checked():
                consent.click(force=True)
        except Exception:  # noqa: BLE001
            pass

    _click_if_visible(page, "button:has-text('Unlock Demo Slot')")


def _start_game(page: Page) -> bool:
    # Explicitly click the game launcher button requested by selector.
    _dismiss_popups(page)

    launcher = page.locator(".slaunch-game").first
    if launcher.count() == 0:
        return False

    started = False
    for _ in range(12):
        try:
            _dismiss_popups(page)
            launcher.click(timeout=2000, force=True)
            started = True
            break
        except Exception:  # noqa: BLE001
            try:
                page.evaluate(
                    """
                    () => {
                      const btn = document.querySelector('.slaunch-game');
                      if (btn) { btn.click(); }
                    }
                    """
                )
                started = True
                break
            except Exception:  # noqa: BLE001
                page.wait_for_timeout(500)

    return started


def _wait_for_slotslaunch_frame(page: Page, timeout_ms: int) -> bool:
    deadline = time.time() + (timeout_ms / 1000.0)
    while time.time() < deadline:
        for frame in page.frames:
            try:
                frame_url = (frame.url or "").lower()
            except Exception:  # noqa: BLE001
                frame_url = ""
            if "slotslaunch.com" in frame_url or "api.agechecked.com" in frame_url:
                return True
        page.wait_for_timeout(300)
    return False


def _extract_slotslaunch_iframe_url(page: Page) -> str | None:
    try:
        in_dom = page.evaluate(
            """
            () => {
              const iframe = document.querySelector("iframe[src*='slotslaunch.com/iframe/']");
              return iframe ? (iframe.getAttribute('src') || '') : '';
            }
            """
        )
        if in_dom and str(in_dom).strip():
            return str(in_dom).strip()
    except Exception:  # noqa: BLE001
        pass

    try:
        html = page.content()
    except Exception:  # noqa: BLE001
        return None

    match = _SLOTSLAUNCH_IFRAME_RE.search(html)
    if match:
        return match.group(0)
    return None


def _inject_slotslaunch_iframe(page: Page, iframe_url: str) -> None:
    page.evaluate(
        """
        (src) => {
          let iframe = document.querySelector("iframe[data-copilot-slotslaunch='1']");
          if (!iframe) {
            iframe = document.createElement('iframe');
            iframe.setAttribute('data-copilot-slotslaunch', '1');
                        iframe.style.width = '100vw';
                        iframe.style.height = '100vh';
                        iframe.style.position = 'fixed';
                        iframe.style.left = '0';
                        iframe.style.top = '0';
                        iframe.style.border = '0';
                        iframe.style.zIndex = '2147483000';
                        iframe.style.background = '#000';
            document.body.appendChild(iframe);
          }
          iframe.src = src;
        }
        """,
        iframe_url,
    )


def _log_frame_snapshot(page: Page, logger: "_CaptureLogger", game_meta: dict[str, object], label: str) -> None:
    urls: list[str] = []
    for frame in page.frames:
        try:
            urls.append(frame.url or "")
        except Exception:  # noqa: BLE001
            urls.append("")
    logger.log("frame_snapshot", {**game_meta, "label": label, "frame_urls": urls})


def _click_verify_age_gate(page: Page) -> int:
    clicked = 0
    selectors = [
        "button:has-text('VERIFY MY AGE')",
        "button:has-text('Verify my age')",
        "button:has-text('I am over 18')",
        "button:has-text('I\'m over 18')",
        "button:has-text('Continue')",
    ]
    for frame in page.frames:
        for selector in selectors:
            try:
                frame.evaluate(
                    """
                    () => {
                      try { localStorage.setItem('av-checked', '1'); } catch (_) {}
                      document.cookie = 'av-checked=1; path=/';
                    }
                    """
                )
                locator = frame.locator(selector).first
                if locator.count() > 0:
                    try:
                        locator.scroll_into_view_if_needed(timeout=1000)
                        locator.click(timeout=1000, force=True)
                        clicked += 1
                    except Exception:  # noqa: BLE001
                        # Some age-check overlays render outside viewport; click via DOM API as fallback.
                        did_click = frame.evaluate(
                            """
                            (sel) => {
                              const btn = document.querySelector(sel)
                                || document.querySelector('#age-check')
                                || Array.from(document.querySelectorAll('button')).find((b) =>
                                  (b.textContent || '').toUpperCase().includes('VERIFY MY AGE')
                                );
                              if (!btn) return false;
                              btn.click();
                              return true;
                            }
                            """,
                            selector,
                        )
                        if did_click:
                            clicked += 1
            except Exception:  # noqa: BLE001
                continue
    return clicked


def _click_if_visible(page: Page, selector: str) -> None:
    locator = page.locator(selector).first
    if locator.count() == 0:
        return
    try:
        locator.click(timeout=2000, force=True)
    except Exception:  # noqa: BLE001
        return


def _looks_like_image_url(url: str) -> bool:
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _IMAGE_EXT)


def _is_non_game_host(url: str) -> bool:
    host = urlparse(url).netloc.lower()
    blocked_hosts = (
        "spinwizard.co.uk",
        "optassets.ontraport.com",
        "cdn.webpushr.com",
        "consentcdn.cookiebot.com",
        "www.googletagmanager.com",
        "www.google-analytics.com",
    )
    return any(host.endswith(blocked) for blocked in blocked_hosts)


def _extension_from_response(url: str, content_type: str) -> str:
    path = urlparse(url).path.lower()
    for ext in _IMAGE_EXT:
        if path.endswith(ext):
            return ext

    ctype = content_type.lower()
    mapping = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/avif": ".avif",
        "image/bmp": ".bmp",
    }
    for key, ext in mapping.items():
        if ctype.startswith(key):
            return ext

    match = re.search(r"\.([a-z0-9]{3,4})$", path)
    if match:
        return f".{match.group(1)}"
    return ".bin"


class _CaptureLogger:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def log(self, event: str, payload: dict[str, object]) -> None:
        record = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "event": event,
            **payload,
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(record, ensure_ascii=True) + "\n")
