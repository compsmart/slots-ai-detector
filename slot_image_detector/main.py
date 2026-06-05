from __future__ import annotations

import argparse

from .asset_scraper import run_asset_capture
from .config import load_settings
from .crawler import run_crawl
from .downloader import run_downloads
from .repository import Repository
from .spinwizard import SpinWizardClient


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="SpinWizard slot image detector")
    sub = parser.add_subparsers(dest="command", required=True)

    crawl = sub.add_parser("crawl", help="Crawl slot metadata")
    crawl.add_argument("--restart", action="store_true", help="Restart crawl from page 1")
    crawl.add_argument("--max-pages", type=int, default=None)

    download = sub.add_parser("download", help="Download pending images")
    download.add_argument("--limit", type=int, default=None)

    assets = sub.add_parser("assets", help="Capture in-game assets via Playwright")
    assets.add_argument("--limit", type=int, default=None)
    assets.add_argument("--wait-seconds", type=float, default=None)
    assets.add_argument("--max-per-game", type=int, default=None)
    assets.add_argument("--max-per-provider", type=int, default=5)
    assets.add_argument("--headed", action="store_true", help="Run browser in headed mode")

    detect = sub.add_parser("detect", help="Run AI detector on downloaded images")
    detect.add_argument("--limit", type=int, default=None)

    all_cmd = sub.add_parser("all", help="Run crawl, download, detect")
    all_cmd.add_argument("--restart", action="store_true")
    all_cmd.add_argument("--max-pages", type=int, default=None)
    all_cmd.add_argument("--capture-assets", action="store_true", help="Include in-game asset capture")
    all_cmd.add_argument("--max-assets-per-provider", type=int, default=5)

    sub.add_parser("stats", help="Print current summary")
    return parser


def main() -> None:
    args = build_parser().parse_args()
    settings = load_settings()

    repo = Repository(settings.db_path)
    repo.initialize()

    client = SpinWizardClient(
        endpoint=settings.endpoint,
        per_page=settings.per_page,
        timeout_seconds=settings.timeout_seconds,
        max_retries=settings.max_retries,
        retry_base_delay=settings.retry_base_delay,
    )

    try:
        if args.command == "crawl":
            result = run_crawl(
                repo,
                client,
                provider_cache_path=settings.data_dir / "provider_filters_cache.json",
                force_restart=args.restart,
                max_pages=args.max_pages,
            )
            print(result)
        elif args.command == "download":
            result = run_downloads(
                repo=repo,
                library_dir=settings.library_dir,
                timeout_seconds=settings.timeout_seconds,
                max_retries=settings.max_retries,
                retry_base_delay=settings.retry_base_delay,
                limit=args.limit,
            )
            print(result)
        elif args.command == "assets":
            result = run_asset_capture(
                repo=repo,
                library_dir=settings.library_dir,
                unlock_email=settings.unlock_email,
                wait_seconds=args.wait_seconds if args.wait_seconds is not None else settings.asset_capture_wait_seconds,
                max_per_game=args.max_per_game if args.max_per_game is not None else settings.asset_max_per_game,
                headless=(False if args.headed else settings.headless_browser),
                limit=args.limit,
                max_per_provider=args.max_per_provider,
            )
            print(result)
        elif args.command == "detect":
            from .detector import AICoverDetector, run_detection

            detector = AICoverDetector(settings.model_name)
            result = run_detection(repo=repo, detector=detector, limit=args.limit)
            print(result)
        elif args.command == "all":
            crawl_result = run_crawl(
                repo,
                client,
                provider_cache_path=settings.data_dir / "provider_filters_cache.json",
                force_restart=args.restart,
                max_pages=args.max_pages,
            )
            download_result = run_downloads(
                repo=repo,
                library_dir=settings.library_dir,
                timeout_seconds=settings.timeout_seconds,
                max_retries=settings.max_retries,
                retry_base_delay=settings.retry_base_delay,
                limit=None,
            )
            asset_result = None
            if args.capture_assets:
                asset_result = run_asset_capture(
                    repo=repo,
                    library_dir=settings.library_dir,
                    unlock_email=settings.unlock_email,
                    wait_seconds=settings.asset_capture_wait_seconds,
                    max_per_game=settings.asset_max_per_game,
                    headless=settings.headless_browser,
                    limit=None,
                    max_per_provider=args.max_assets_per_provider,
                )
            from .detector import AICoverDetector, run_detection

            detector = AICoverDetector(settings.model_name)
            detect_result = run_detection(repo=repo, detector=detector, limit=None)
            print({
                "crawl": crawl_result,
                "download": download_result,
                "assets": asset_result,
                "detect": detect_result,
            })
        elif args.command == "stats":
            print(repo.summary())
    finally:
        repo.close()


if __name__ == "__main__":
    main()
