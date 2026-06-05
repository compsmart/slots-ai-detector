# Playwright Live Validation Log

## Date
2026-06-05

## Goal
Validate real game loading behavior before scripting in-game asset scraping.

## Manual Playwright session summary
1. Opened `https://spinwizard.co.uk/slots/`.
2. Accepted cookie consent (`Allow all`).
3. Navigated directly to a game page: `https://spinwizard.co.uk/slots/tropicool-3/`.
4. Observed unlock form on page (`Unlock Demo Slot`) with consent checkbox and email input.
5. Entered email: `brad@compsmart.co.uk` and checked consent.
6. Triggered unlock action.
7. Confirmed embedded slots iframe loaded (`slotslaunch.com/iframe/...`).
8. Triggered age verification control (`VERIFY MY AGE`) in iframe.
9. Confirmed nested age-check flow loaded (`api.agechecked.com`).

## Technical findings
- Directly opening the `slotslaunch.com/iframe/...` URL outside iframe returns `403 Iframe not detected`.
- Game must be loaded in embedded context from SpinWizard page.
- Popup overlays can block user interactions; forced click/remove overlay logic is required.
- Asset collection should listen to network responses across all frames and persist image content.

## Scripting decisions implemented
- Added Playwright-driven `assets` CLI command.
- Added new DB tables for resumable asset capture and per-asset storage.
- Added popup dismissal, unlock-flow automation, age-check trigger attempt, and response-based image capture.
