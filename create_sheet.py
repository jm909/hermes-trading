"""Creates a Google Sheet with trade data tabs using Playwright + existing Chrome session."""
import time
from playwright.sync_api import sync_playwright

CHROME_PROFILE = r"C:\Users\User\AppData\Local\Temp\chrome-playwright-profile"

TABS = [
    ("Trades",      "=IMPORTDATA(\"https://raw.githubusercontent.com/jm909/hermes-trading/main/state/trades.csv\")"),
    ("Reflections", "=IMPORTDATA(\"https://raw.githubusercontent.com/jm909/hermes-trading/main/state/hypotheses.csv\")"),
    ("Strategy",    "=IMPORTDATA(\"https://raw.githubusercontent.com/jm909/hermes-trading/main/state/strategy.csv\")"),
]

def main():
    with sync_playwright() as p:
        browser = p.chromium.launch_persistent_context(
            user_data_dir=CHROME_PROFILE,
            channel="chrome",
            headless=False,
            args=["--no-first-run", "--no-default-browser-check"]
        )
        page = browser.new_page()
        print("Opening new Google Sheet...")
        page.goto("https://sheets.new")
        # If redirected to sign-in, wait up to 120s for user to sign in
        if "accounts.google.com" in page.url or "signin" in page.url:
            print(">>> Google sign-in page opened in the browser window.")
            print(">>> Sign in with your Google account, then the sheet will be created automatically.")
            page.wait_for_url("**/spreadsheets/**", timeout=120000)
        else:
            page.wait_for_url("**/spreadsheets/**", timeout=30000)
        time.sleep(3)

        # Rename Sheet1 to Trades and add formula
        for i, (tab_name, formula) in enumerate(TABS):
            if i == 0:
                # Rename existing Sheet1
                tab = page.locator(".docs-sheet-tab-name").first
                tab.dbl_click()
                time.sleep(0.5)
                page.keyboard.press("Control+a")
                page.keyboard.type(tab_name)
                page.keyboard.press("Enter")
            else:
                # Add new tab
                page.locator(".docs-sheet-add").click()
                time.sleep(1)
                tab = page.locator(".docs-sheet-tab-name").last
                tab.dbl_click()
                time.sleep(0.5)
                page.keyboard.press("Control+a")
                page.keyboard.type(tab_name)
                page.keyboard.press("Enter")

            time.sleep(1)
            # Click cell A1 and enter formula
            page.locator(".docs-sheet-tab-name", has_text=tab_name).click()
            time.sleep(1)
            page.keyboard.press("Control+Home")
            time.sleep(0.5)
            page.keyboard.type(formula)
            page.keyboard.press("Enter")
            time.sleep(2)
            print(f"  Tab '{tab_name}' done")

        print(f"\nSheet created: {page.url}")
        print("Keeping browser open — close it when you're done.")
        input("Press Enter here to close...")
        browser.close()

if __name__ == "__main__":
    main()
