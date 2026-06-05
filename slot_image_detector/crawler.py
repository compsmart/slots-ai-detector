from __future__ import annotations

from pathlib import Path

from .repository import Repository
from .spinwizard import SpinWizardClient


def run_crawl(
    repo: Repository,
    client: SpinWizardClient,
    provider_cache_path: Path,
    force_restart: bool = False,
    max_pages: int | None = None,
) -> dict[str, int]:
    if force_restart:
        repo.set_state("crawl_provider_index", "0")
        repo.set_state("crawl_provider_last_page", "0")
        repo.set_state("crawl_finished", "0")

    providers = client.get_provider_options(cache_path=provider_cache_path, refresh=force_restart)
    if not providers:
        return {"processed_pages": 0, "upserted_games": 0, "providers": 0}

    provider_index = int(repo.get_state("crawl_provider_index", "0") or "0")
    provider_last_page = int(repo.get_state("crawl_provider_last_page", "0") or "0")
    finished = repo.get_state("crawl_finished", "0") == "1"

    if finished and not force_restart:
        return {"processed_pages": 0, "upserted_games": 0, "providers": len(providers)}

    pages_processed = 0
    games_seen = 0

    for index in range(provider_index, len(providers)):
        provider = providers[index]
        current_page = provider_last_page + 1 if index == provider_index else 1

        while True:
            if max_pages is not None and pages_processed >= max_pages:
                repo.set_state("crawl_provider_index", str(index))
                repo.set_state("crawl_provider_last_page", str(current_page - 1))
                return {
                    "processed_pages": pages_processed,
                    "upserted_games": games_seen,
                    "providers": len(providers),
                }

            page_data = client.fetch_page(
                current_page,
                provider_value=provider.value,
                provider_label=provider.label,
            )
            if not page_data.records:
                break

            for record in page_data.records:
                repo.upsert_game(record, page_seen=current_page)
                games_seen += 1

            repo.set_state("crawl_provider_index", str(index))
            repo.set_state("crawl_provider_last_page", str(current_page))
            pages_processed += 1
            current_page += 1

        repo.set_state("crawl_provider_last_page", "0")

    repo.set_state("crawl_finished", "1")
    return {"processed_pages": pages_processed, "upserted_games": games_seen, "providers": len(providers)}
