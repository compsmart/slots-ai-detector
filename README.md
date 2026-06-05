# Slot Image Detector

Pipeline to crawl SpinWizard slot covers, detect likely AI-generated images, and visualize provider-level analytics.

## Remote inference

If this machine cannot run ML inference, use the remote execution strategy documented in `REMOTE_INFERENCE_PLAN.md`.

## Quick start

1. Create a Python virtual environment and install dependencies:
   - `python -m venv .venv`
   - `.venv\\Scripts\\Activate.ps1`
   - `pip install -r requirements.txt`
2. Run the pipeline:
   - `python -m slot_image_detector.main crawl`
   - `python -m slot_image_detector.main download`
   - `python -m slot_image_detector.main assets`
   - `python -m slot_image_detector.main detect`
3. Run API:
   - `uvicorn api.main:app --reload`
4. Run dashboard:
   - `cd dashboard`
   - `npm install`
   - `npm run dev`

## Commands

- `crawl`: Pull game metadata from SpinWizard JSON endpoint (newest to oldest), resumable.
- `download`: Download missing cover images into provider/game folders.
- `assets`: Load game pages with Playwright and capture in-game image assets.
- `detect`: Run Hugging Face classifier on missing detections.
- `all`: Run crawl + download + detect in sequence.
- `stats`: Print summary metrics.

## Playwright setup

- Install browser binaries once:
   - `python -m playwright install chromium`

See `GAME_ASSET_AUTOMATION.md` and `GAME_LOADING_PLAYWRIGHT_LOG.md` for the end-to-end asset process and live validation notes.
