from playwright.sync_api import sync_playwright


def safe_click(page, selector: str) -> None:
    try:
        loc = page.locator(selector).first
        if loc.count() > 0:
            loc.click(force=True, timeout=2000)
    except Exception:
        pass


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1600, "height": 900})
        page.goto("https://spinwizard.co.uk/slots/cyber-heist-city/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(3000)

        # Attempt unlock and launch.
        try:
            email = page.locator("input[placeholder='Enter Your Email Here...']").first
            if email.count() > 0:
                email.fill("brad@compsmart.co.uk")
        except Exception:
            pass

        try:
            cb = page.locator("input[type='checkbox']").first
            if cb.count() > 0:
                cb.click(force=True)
        except Exception:
            pass

        safe_click(page, "button:has-text('Unlock Demo Slot')")
        safe_click(page, ".slaunch-game")

        page.wait_for_timeout(4000)

        for step in range(4):
            print("=== SNAPSHOT", step, "===")
            for frame in page.frames:
                print("FRAME", frame.url)
                try:
                    buttons = frame.locator("button").all_inner_texts()
                    if buttons:
                        print("BUTTONS", buttons[:20])
                except Exception:
                    pass
            safe_click(page, "button:has-text('VERIFY MY AGE')")
            for frame in page.frames:
                try:
                    fr_btn = frame.locator("button:has-text('VERIFY MY AGE')").first
                    if fr_btn.count() > 0:
                        fr_btn.click(force=True, timeout=1000)
                except Exception:
                    pass
            page.wait_for_timeout(3000)

        browser.close()


if __name__ == "__main__":
    main()
