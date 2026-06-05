from __future__ import annotations

import json
import random
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

from .models import SlotRecord


@dataclass
class SlotsPage:
    page: int
    total_returned: int
    total_found: int
    records: list[SlotRecord]


@dataclass(frozen=True)
class ProviderOption:
    value: str
    label: str


class SpinWizardClient:
    def __init__(
        self,
        endpoint: str,
        per_page: int,
        timeout_seconds: float,
        max_retries: int,
        retry_base_delay: float,
    ) -> None:
        self.endpoint = endpoint
        self.per_page = per_page
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.retry_base_delay = retry_base_delay

    def fetch_page(
        self,
        page: int,
        provider_value: str = "",
        provider_label: str | None = None,
    ) -> SlotsPage:
        params = {
            "action": "sl_get_slots",
            "sl-page": page,
            "sl-provider": provider_value,
            "sl-theme": "",
            "sl-type": "slots",
            "sl-sort": "new",
            "sl-name": "",
            "per_page": self.per_page,
        }

        payload: dict[str, Any] | None = None
        last_error: Exception | None = None
        for attempt in range(self.max_retries):
            try:
                response = httpx.get(
                    self.endpoint,
                    params=params,
                    timeout=self.timeout_seconds,
                    trust_env=True,
                    verify=False,
                    headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0.0.0 Safari/537.36"
                        ),
                        "Referer": "https://spinwizard.co.uk/slots/",
                    },
                )
                response.raise_for_status()
                payload = response.json()
                break
            except (httpx.HTTPError, ValueError) as exc:
                last_error = exc
                if attempt == self.max_retries - 1:
                    break
                delay = self.retry_base_delay * (2**attempt) + random.uniform(0, 0.3)
                time.sleep(delay)

        if payload is None:
            payload = self._fetch_page_via_playwright(params=params)

        if payload is None:
            dom_fallback = self._fetch_page_via_browser_dom(
                page=page,
                provider_value=provider_value,
                provider_label=provider_label,
            )
            if dom_fallback is not None:
                return dom_fallback

        if payload is None:
            raise RuntimeError(f"No payload received from SpinWizard endpoint: {last_error}")

        data = payload.get("data") or {}
        slots = data.get("slots") or []
        records = [
            self._parse_slot(slot, provider_value=provider_value, provider_label=provider_label)
            for slot in slots
        ]
        records.sort(key=lambda item: item.game_id, reverse=True)
        return SlotsPage(
            page=int(data.get("page") or page),
            total_returned=int(data.get("total") or len(records)),
            total_found=int(data.get("found") or 0),
            records=records,
        )

    def get_provider_options(self, cache_path: Path, refresh: bool = False) -> list[ProviderOption]:
        if cache_path.exists() and not refresh:
            cached = self._load_provider_cache(cache_path)
            if cached:
                return cached

        providers = self._fetch_provider_options_via_playwright()
        if not providers:
            providers = self._fetch_provider_options_via_http()
        if not providers:
            raise RuntimeError("Could not fetch provider options from SpinWizard")

        payload = {
            "source_url": "https://spinwizard.co.uk/slots/",
            "fetched_at": datetime.now(timezone.utc).isoformat(),
            "providers": [{"value": p.value, "label": p.label} for p in providers],
        }
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        cache_path.write_text(json.dumps(payload, indent=2, ensure_ascii=True), encoding="utf-8")
        return providers

    def _load_provider_cache(self, cache_path: Path) -> list[ProviderOption]:
        try:
            payload = json.loads(cache_path.read_text(encoding="utf-8"))
            items = payload.get("providers") or []
            providers = [
                ProviderOption(value=str(item.get("value") or "").strip(), label=str(item.get("label") or "").strip())
                for item in items
            ]
            return [p for p in providers if p.value]
        except Exception:  # noqa: BLE001
            return []

    def _fetch_provider_options_via_http(self) -> list[ProviderOption]:
        try:
            response = httpx.get(
                "https://spinwizard.co.uk/slots/",
                timeout=self.timeout_seconds,
                trust_env=True,
                verify=False,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                        "AppleWebKit/537.36 (KHTML, like Gecko) "
                        "Chrome/126.0.0.0 Safari/537.36"
                    ),
                },
            )
            response.raise_for_status()
        except Exception:  # noqa: BLE001
            return []

        html = response.text
        soup = BeautifulSoup(html, "html.parser")
        values: set[tuple[str, str]] = set()

        for option in soup.select("select[name='sl-provider'] option"):
            value = (option.get("value") or "").strip()
            label = option.get_text(strip=True) or value
            if value:
                values.add((value, label))

        for anchor in soup.select("a[href*='sl-provider=']"):
            href = anchor.get("href") or ""
            marker = "sl-provider="
            if marker not in href:
                continue
            value = href.split(marker, 1)[1].split("&", 1)[0].strip()
            label = anchor.get_text(strip=True) or value
            if value:
                values.add((value, label))

        return [ProviderOption(value=v, label=l) for v, l in sorted(values, key=lambda x: x[0])]

    def _fetch_provider_options_via_playwright(self) -> list[ProviderOption]:
        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                page = browser.new_page(viewport={"width": 1600, "height": 900})
                page.goto("https://spinwizard.co.uk/slots/", wait_until="domcontentloaded", timeout=90000)
                page.wait_for_timeout(2500)

                providers = page.evaluate(
                    """
                    () => {
                      const out = new Map();

                      const select = document.querySelector("select[name='sl-provider']");
                      if (select) {
                        for (const opt of Array.from(select.querySelectorAll('option'))) {
                          const value = (opt.getAttribute('value') || '').trim();
                          const label = (opt.textContent || '').trim() || value;
                          if (value) out.set(value, label);
                        }

                        const root = select.closest('.choices') || document.querySelector('.choices');
                        if (root) {
                          for (const item of Array.from(root.querySelectorAll('.choices__item--choice[data-value]'))) {
                            const value = (item.getAttribute('data-value') || '').trim();
                            const label = (item.textContent || '').trim() || value;
                            if (value) out.set(value, label);
                          }
                        }
                      }

                      for (const a of Array.from(document.querySelectorAll("a[href*='sl-provider=']"))) {
                        const href = a.getAttribute('href') || '';
                        const idx = href.indexOf('sl-provider=');
                        if (idx === -1) continue;
                        const value = href.slice(idx + 'sl-provider='.length).split('&')[0].trim();
                        const label = (a.textContent || '').trim() || value;
                        if (value) out.set(value, label);
                      }

                      return Array.from(out.entries()).map(([value, label]) => ({ value, label }));
                    }
                    """
                )

                result = [
                    ProviderOption(value=str(item.get("value") or "").strip(), label=str(item.get("label") or "").strip())
                    for item in (providers or [])
                    if str(item.get("value") or "").strip()
                ]
                result.sort(key=lambda item: item.value)
                return result
            finally:
                browser.close()

    def _parse_slot(
        self,
        slot: dict[str, Any],
        provider_value: str = "",
        provider_label: str | None = None,
    ) -> SlotRecord:
        game_id = int(slot.get("id"))

        title_anchor = BeautifulSoup(slot.get("title") or "", "html.parser").find("a")
        img_tag = BeautifulSoup(slot.get("img") or "", "html.parser").find("img")

        title = (title_anchor.get_text(strip=True) if title_anchor else "").strip() or f"game-{game_id}"
        game_url = title_anchor.get("href") if title_anchor else ""
        cover_url = img_tag.get("src") if img_tag else ""

        if provider_value:
            provider_name = provider_value.strip().lower()
            provider_url = f"https://spinwizard.co.uk/slots?sl-provider={provider_value.strip()}"
        else:
            provider_name = (slot.get("provider_name") or provider_label or "unknown").strip().lower()
            provider_url = (slot.get("provider_url") or "").strip()

        return SlotRecord(
            game_id=game_id,
            title=title,
            game_url=game_url,
            provider_name=provider_name,
            provider_url=provider_url,
            cover_url=cover_url,
        )

    def _fetch_page_via_playwright(self, params: dict[str, Any]) -> dict[str, Any] | None:
        try:
            with sync_playwright() as pw:
                request_context = pw.request.new_context(
                    ignore_https_errors=True,
                    extra_http_headers={
                        "User-Agent": (
                            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                            "AppleWebKit/537.36 (KHTML, like Gecko) "
                            "Chrome/126.0.0.0 Safari/537.36"
                        ),
                        "Referer": "https://spinwizard.co.uk/slots/",
                    }
                )
                try:
                    response = request_context.get(self.endpoint, params=params, timeout=self.timeout_seconds * 1000)
                    if not response.ok:
                        return None
                    return response.json()
                finally:
                    request_context.dispose()
        except Exception:  # noqa: BLE001
            return None

    def _fetch_page_via_browser_dom(
        self,
        page: int,
        provider_value: str = "",
        provider_label: str | None = None,
    ) -> SlotsPage | None:
        if page != 1:
            return None

        with sync_playwright() as pw:
            browser = pw.chromium.launch(headless=True)
            try:
                browser_page = browser.new_page(viewport={"width": 1600, "height": 900})
                browser_page.goto("https://spinwizard.co.uk/slots/", wait_until="domcontentloaded", timeout=90000)
                browser_page.evaluate(
                    """
                    () => {
                      const allow = document.querySelector("button#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll");
                      if (allow) allow.click();
                      const closeButtons = Array.from(document.querySelectorAll('button')).filter((btn) => /close|deny|x/i.test((btn.textContent||'').trim()));
                      closeButtons.slice(0, 6).forEach((btn) => btn.click());
                    }
                    """
                )
                browser_page.wait_for_timeout(3000)
                rows = browser_page.evaluate(
                    """
                    (providerFilter) => {
                      const byId = new Map();
                      const links = Array.from(document.querySelectorAll('a.slotsl-url[data-sid]'));
                      for (const link of links) {
                        const sid = Number(link.getAttribute('data-sid'));
                        if (!sid) continue;
                        const text = (link.textContent || '').trim();
                        if (/play demo/i.test(text)) continue;

                        const container = link.closest('article, .slotslaunch-post, .slotslaunch-item, .slotsl-item, .slots-item, .sl-item, .slotslaunch-box') || link.parentElement;
                        const img = (container ? container.querySelector('img') : null) || link.querySelector('img');
                        const providerLink = container ? container.querySelector("a[href*='sl-provider=']") : null;
                        const providerName = providerFilter || (providerLink ? (providerLink.textContent || '').trim().toLowerCase() : 'unknown');
                        const providerUrl = providerLink ? providerLink.getAttribute('href') || '' : '';

                        byId.set(sid, {
                          id: sid,
                          title: text || `game-${sid}`,
                          game_url: link.getAttribute('href') || '',
                          provider_name: providerName || 'unknown',
                          provider_url: providerUrl,
                          cover_url: img ? (img.getAttribute('src') || '') : ''
                        });
                      }
                      return Array.from(byId.values()).sort((a, b) => b.id - a.id);
                    }
                                        """,
                                        provider_value,
                )
                if not rows:
                    return None

                records = [
                    SlotRecord(
                        game_id=int(row["id"]),
                        title=str(row["title"]),
                        game_url=str(row["game_url"]),
                        provider_name=str(provider_value or row["provider_name"]),
                        provider_url=str(row["provider_url"]),
                        cover_url=str(row["cover_url"]),
                    )
                    for row in rows[: self.per_page]
                    if row.get("game_url")
                ]
                if not records:
                    return None
                return SlotsPage(
                    page=1,
                    total_returned=len(records),
                    total_found=len(records),
                    records=records,
                )
            finally:
                browser.close()
