import time
from playwright.sync_api import sync_playwright, Browser, Page, Playwright
from config.settings import Settings
from utils.logger import logger

class BrowserAgent:
    """Orchestrates synchronous Playwright automation for the assistant."""
    
    def __init__(self):
        self.playwright: Playwright = None
        self.browser: Browser = None
        self.page: Page = None
        self.headless = Settings.BROWSER_HEADLESS
        self.timeout = Settings.BROWSER_TIMEOUT
        
    def start(self):
        """Starts the Playwright driver and launches a headed/headless Chromium browser."""
        if not self.browser:
            logger.info("Initializing Playwright Chromium browser session...")
            self.playwright = sync_playwright().start()
            self.browser = self.playwright.chromium.launch(
                headless=self.headless,
                args=["--disable-blink-features=AutomationControlled"]
            )
            # Create a clean context with standard viewport size
            context = self.browser.new_context(
                viewport={"width": 1280, "height": 720}
            )
            self.page = context.new_page()
            self.page.set_default_timeout(self.timeout)
            
    def navigate(self, url: str) -> str:
        """Navigates the browser to the specified URL, handles cookie dialogues, and returns status."""
        self.start()
        try:
            if not url.startswith(("http://", "https://")):
                url = "https://" + url
                
            logger.info(f"Navigating to URL: {url}")
            self.page.goto(url)
            self.page.wait_for_load_state("load")
            
            # Resilient cookie popup handler
            self.dismiss_consent_dialogs()
            
            title = self.page.title()
            return f"Successfully opened {url} (Page Title: '{title}')"
        except Exception as e:
            logger.exception(f"Error navigating to '{url}':")
            return f"Error opening URL '{url}': {str(e)}"
            
    def click(self, selector_or_text: str) -> str:
        """Clicks an element by leveraging text heuristics or standard CSS selectors."""
        self.start()
        try:
            logger.info(f"Locating and clicking element: '{selector_or_text}'")
            
            # Try text-based matching first (less brittle on modern responsive web pages)
            try:
                locator = self.page.get_by_text(selector_or_text, exact=False)
                if locator.count() > 0:
                    locator.first.click()
                    return f"Successfully clicked element with text '{selector_or_text}'"
            except Exception:
                pass
                
            # Try selector-based matching
            self.page.click(selector_or_text)
            return f"Successfully clicked CSS selector '{selector_or_text}'"
        except Exception as e:
            logger.exception(f"Error clicking element '{selector_or_text}':")
            return f"Error clicking '{selector_or_text}': {str(e)}"
            
    def type_text(self, selector_or_text: str, text: str) -> str:
        """Fills input elements using placeholder matching or standard CSS selectors."""
        self.start()
        try:
            logger.info(f"Locating input and typing text into: '{selector_or_text}'")
            
            # Try placeholder matching first
            try:
                locator = self.page.get_by_placeholder(selector_or_text, exact=False)
                if locator.count() > 0:
                    locator.first.fill(text)
                    return f"Successfully filled placeholder input '{selector_or_text}' with text"
            except Exception:
                pass
                
            # Fall back to standard CSS selectors
            self.page.fill(selector_or_text, text)
            return f"Successfully typed text into CSS selector '{selector_or_text}'"
        except Exception as e:
            logger.exception(f"Error typing in '{selector_or_text}':")
            return f"Error typing in '{selector_or_text}': {str(e)}"
            
    def close(self):
        """Safely tears down page, browser, and Playwright execution context instances."""
        if self.browser:
            logger.info("Closing browser automation session...")
            try:
                self.browser.close()
            except Exception:
                pass
            self.browser = None
            
        if self.playwright:
            try:
                self.playwright.stop()
            except Exception:
                pass
            self.playwright = None
            
        self.page = None
        
    def dismiss_consent_dialogs(self):
        """Detects and dismisses common overlay dialogue screens (Google, YouTube cookie walls)."""
        try:
            # Common European / Global cookie consent overlays buttons
            dialog_buttons = [
                "Reject all", "Accept all", "I agree", "Agree", 
                "Consent", "No thanks", "Decline"
            ]
            
            for btn_text in dialog_buttons:
                try:
                    locator = self.page.get_by_role("button", name=btn_text, exact=False)
                    if locator.count() > 0 and locator.first.is_visible():
                        logger.info(f"Auto-detected consent popup button '{btn_text}'. Dismissing dialogue...")
                        locator.first.click()
                        time.sleep(1.0)
                        break
                except Exception:
                    pass
        except Exception as e:
            logger.debug(f"Did not find or failed to close cookie dialogues: {e}")
