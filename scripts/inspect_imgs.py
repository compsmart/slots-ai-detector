from playwright.sync_api import sync_playwright


def main() -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto("https://spinwizard.co.uk/slots/cyber-heist-city/", wait_until="domcontentloaded", timeout=90000)
        page.wait_for_timeout(4000)
        urls = page.evaluate(
            """
            () => Array.from(document.querySelectorAll('img'))
              .map((i) => i.src)
              .filter(Boolean)
            """
        )
        print("count", len(urls))
        print([u for u in urls if "slotslaunch" in u][:20])
        browser.close()


if __name__ == "__main__":
    main()
