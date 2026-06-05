# Game Asset Automation Workflow

## Objective
Capture more than just cover images by loading each slot game page with Playwright, triggering the embedded game flow, and storing in-game image assets to the local library with resumable state.

## What is automated now
1. Crawl slot metadata from the public JSON endpoint (newest to oldest).
2. Download cover images.
3. Open each game page in Playwright.
4. Auto-dismiss common popups.
5. Fill unlock email and trigger demo unlock.
6. Trigger play/age gate controls where visible.
7. Capture image assets from network responses across frames.
8. Save assets to provider/game/assets folders.
9. Persist capture status and errors for resume-safe reruns.

## Storage layout
- Covers: `data/library/<provider_slug>/<game_slug>/cover.*`
- In-game assets: `data/library/<provider_slug>/<game_slug>/assets/asset-<hash>.<ext>`

## Resume behavior
- Each game has a row in `game_asset_capture` with status:
  - `pending`
  - `running`
  - `success`
  - `failed`
- Reruns process only `pending` + `failed` games by default.
- Asset dedupe key is `(game_id, asset_url)` in `game_assets`.

## Commands
1. Crawl:
   - `python -m slot_image_detector.main crawl`
2. Download covers:
   - `python -m slot_image_detector.main download`
3. Capture in-game assets:
   - `python -m slot_image_detector.main assets --limit 50`
4. Full pipeline with assets:
   - `python -m slot_image_detector.main all --capture-assets`

## Tunables
Environment variables:
- `SLOT_UNLOCK_EMAIL` (default: `brad@compsmart.co.uk`)
- `ASSET_CAPTURE_WAIT_SECONDS` (default: `20`)
- `ASSET_MAX_PER_GAME` (default: `120`)
- `PLAYWRIGHT_HEADLESS` (`true` or `false`)

CLI overrides:
- `assets --wait-seconds <n>`
- `assets --max-per-game <n>`
- `assets --headed`

## Notes on blockers
Some games are protected behind age-check/verification layers inside third-party iframes. The scraper still logs attempts and captures any image assets that load before or during gate flow. Failed games remain resumable and can be retried later.

## Required setup
1. Install Python dependencies:
   - `python -m pip install -r requirements.txt`
2. Install Playwright browser binaries:
   - `python -m playwright install chromium`
