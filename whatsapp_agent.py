"""WhatsApp Web automation via Selenium."""

from __future__ import annotations

import logging
import random
import shutil
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    NoSuchElementException,
    StaleElementReferenceException,
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

from config import Config
from utils import ensure_directories, random_delay

logger = logging.getLogger("identity_agent")

WHATSAPP_URL = "https://web.whatsapp.com"

# JavaScript: set text in WhatsApp contenteditable (reliable paste for Unicode)
_JS_SET_TEXT = """
const el = arguments[0];
const text = arguments[1];
el.focus();
el.innerHTML = '';
el.textContent = '';
el.dispatchEvent(new Event('focus', { bubbles: true }));
el.dispatchEvent(new Event('input', { bubbles: true }));
if (document.execCommand('insertText', false, text)) {
    el.dispatchEvent(new Event('input', { bubbles: true }));
} else {
    el.textContent = text;
    el.dispatchEvent(new Event('input', { bubbles: true }));
}
"""

_JS_PRESS_ENTER = """
const el = arguments[0];
el.dispatchEvent(new KeyboardEvent('keydown', {
    key: 'Enter', code: 'Enter', keyCode: 13, which: 13, bubbles: true
}));
"""


class WhatsAppAgent:
    """Automates WhatsApp Web: session, search, type, and send."""

    def __init__(self, config: Config) -> None:
        self.config = config
        self.driver: webdriver.Chrome | None = None
        ensure_directories(config.screenshots_dir, config.errors_dir)

    def _build_options(self) -> Options:
        """Configure Chrome with persistent profile."""
        options = Options()
        profile = str(self.config.chrome_profile_path.resolve())
        options.add_argument(f"--user-data-dir={profile}")
        options.add_argument("--profile-directory=Default")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--lang=en-US")
        options.add_experimental_option("excludeSwitches", ["enable-automation"])
        options.add_experimental_option("useAutomationExtension", False)
        if self.config.headless:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
        return options

    def start_browser(self) -> None:
        """Launch Chrome with webdriver-manager."""
        logger.info("Starting Chrome browser...")
        options = self._build_options()
        service = Service(ChromeDriverManager().install())
        self.driver = webdriver.Chrome(service=service, options=options)
        if not self.config.headless:
            self.driver.maximize_window()
        logger.info("Browser started")

    def open_whatsapp(self) -> None:
        """Navigate to WhatsApp Web."""
        if not self.driver:
            raise RuntimeError("Browser not started. Call start_browser() first.")
        self.driver.get(WHATSAPP_URL)
        logger.info("Opened WhatsApp Web")

    def _wait(self, timeout: int | None = None) -> WebDriverWait:
        return WebDriverWait(self.driver, timeout or self.config.wait_timeout)

    def _is_logged_in(self) -> bool:
        """Return True if WhatsApp main UI is visible (not QR screen)."""
        if not self.driver:
            return False
        # QR canvas present => not logged in
        qr_selectors = [
            "canvas[aria-label]",
            '[data-testid="qrcode"]',
        ]
        for sel in qr_selectors:
            try:
                elems = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in elems:
                    if el.is_displayed() and el.size.get("height", 0) > 100:
                        return False
            except WebDriverException:
                pass

        logged_in_markers = [
            (By.CSS_SELECTOR, "#side"),
            (By.CSS_SELECTOR, "#pane-side"),
            (By.CSS_SELECTOR, '[data-testid="chat-list"]'),
            (By.CSS_SELECTOR, "#side [contenteditable='true']"),
        ]
        for by, sel in logged_in_markers:
            try:
                el = self.driver.find_element(by, sel)
                if el.is_displayed():
                    return True
            except NoSuchElementException:
                continue
        return False

    def wait_for_login(self) -> bool:
        """
        Wait until user is logged in (chat list or search box visible).

        Returns:
            True if logged in, False on timeout.
        """
        if not self.driver:
            return False

        logger.info("Waiting for WhatsApp session (scan QR if first run)...")
        max_wait = self.config.wait_timeout * 4
        end = time.time() + max_wait
        while time.time() < end:
            if self._is_logged_in():
                logger.success("WhatsApp Session Restored")
                # Let chat list fully render before automation
                time.sleep(5)
                return True
            time.sleep(2)

        logger.error("Login timeout — scan QR code and try again")
        self.capture_screenshot("login_timeout")
        return False

    def _retry_action(self, action_name: str, func: Callable[[], None]) -> bool:
        """Execute action with retries."""
        last_error: Exception | None = None
        for attempt in range(1, self.config.retry_attempts + 1):
            try:
                func()
                return True
            except (
                TimeoutException,
                StaleElementReferenceException,
                ElementClickInterceptedException,
                WebDriverException,
            ) as e:
                last_error = e
                logger.warning(
                    "%s failed (attempt %d/%d): %s",
                    action_name,
                    attempt,
                    self.config.retry_attempts,
                    e,
                )
                self.capture_screenshot(f"{action_name}_attempt{attempt}")
                random_delay(1.0, 2.5)
        if last_error:
            logger.error("%s failed after retries: %s", action_name, last_error)
            self.capture_screenshot(action_name.replace(" ", "_"))
        return False

    def _set_contenteditable_text(self, element: object, text: str) -> None:
        """Insert text via JavaScript (avoids ChromeDriver send_keys limitations)."""
        if not self.driver:
            return
        self.driver.execute_script(_JS_SET_TEXT, element, text)
        random_delay(0.3, 0.6)

    def _safe_click(self, element: object) -> None:
        """Scroll into view and click element."""
        if not self.driver:
            return
        self.driver.execute_script(
            "arguments[0].scrollIntoView({block: 'center'});", element
        )
        random_delay(0.2, 0.4)
        try:
            element.click()
        except ElementClickInterceptedException:
            self.driver.execute_script("arguments[0].click();", element)

    def _dismiss_overlays(self) -> None:
        """Close blocking popups (updates, notifications, etc.)."""
        if not self.driver:
            return
        close_selectors = [
            'div[class*="overlay"] div[role="button"]',
            '[data-testid="x"]',
            '[data-testid="x-alt"]',
            'button[aria-label="Close"]',
        ]
        for sel in close_selectors:
            try:
                buttons = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for btn in buttons:
                    if btn.is_displayed():
                        self._safe_click(btn)
                        random_delay(0.3, 0.5)
            except WebDriverException:
                continue

    def _wait_for_sidebar(self) -> None:
        """Wait until WhatsApp left panel (chat list) is present."""
        if not self.driver:
            raise TimeoutException("Driver not ready")
        self._wait().until(
            EC.presence_of_element_located(
                (By.CSS_SELECTOR, "#pane-side, #side, [data-testid='chat-list']")
            )
        )
        random_delay(0.5, 1.0)

    def _is_chat_open(self, name: str) -> bool:
        """Return True if the named chat appears to be active."""
        if not self.driver:
            return False
        name_lower = name.lower()
        header_selectors = [
            "#main header span[dir='auto']",
            "#main header span[title]",
            "#main header [data-testid='conversation-info-header-chat-title']",
        ]
        for sel in header_selectors:
            try:
                for el in self.driver.find_elements(By.CSS_SELECTOR, sel):
                    text = (el.text or "").lower()
                    title = (el.get_attribute("title") or "").lower()
                    if name_lower in text or name_lower in title:
                        return True
            except WebDriverException:
                continue
        return False

    def _open_from_chat_list(self, name: str) -> bool:
        """Open contact from visible recent chats (no search box needed)."""
        if not self.driver:
            return False

        name_lower = name.lower()
        xpaths = [
            f'//div[@id="pane-side"]//span[@title="{name}"]',
            f'//div[@id="side"]//span[@title="{name}"]',
            f'//span[@title="{name}"]',
            (
                '//div[@id="pane-side"]//span[contains('
                'translate(@title,"ABCDEFGHIJKLMNOPQRSTUVWXYZ","abcdefghijklmnopqrstuvwxyz"), '
                f'"{name_lower}")]'
            ),
        ]
        for xpath in xpaths:
            try:
                spans = self.driver.find_elements(By.XPATH, xpath)
                for span in spans:
                    if not span.is_displayed():
                        continue
                    try:
                        row = span.find_element(
                            By.XPATH,
                            './ancestor::div[@role="listitem"][1]',
                        )
                        self._safe_click(row)
                    except NoSuchElementException:
                        self._safe_click(span)
                    random_delay(1.0, 2.0)
                    if self._is_chat_open(name):
                        return True
            except WebDriverException:
                continue
        return False

    def _activate_search_panel(self) -> None:
        """Click search icon / bar to reveal the search input."""
        if not self.driver:
            return

        activate_selectors = [
            (By.CSS_SELECTOR, 'span[data-testid="search"]'),
            (By.CSS_SELECTOR, '[data-testid="search"]'),
            (By.CSS_SELECTOR, 'button[aria-label="Search or start new chat"]'),
            (By.CSS_SELECTOR, '[title="Search or start new chat"]'),
            (By.CSS_SELECTOR, '[aria-label="Search or start new chat"]'),
            (By.CSS_SELECTOR, 'span[data-icon="search"]'),
            (By.XPATH, '//div[@id="pane-side"]//button[contains(@aria-label,"Search")]'),
            (By.XPATH, '//div[@id="side"]//button[contains(@aria-label,"Search")]'),
        ]
        for by, sel in activate_selectors:
            try:
                elements = self.driver.find_elements(by, sel)
                for el in elements:
                    if el.is_displayed():
                        try:
                            parent = el.find_element(By.XPATH, "./ancestor::button[1]")
                            self._safe_click(parent)
                        except NoSuchElementException:
                            self._safe_click(el)
                        random_delay(0.8, 1.2)
                        return
            except WebDriverException:
                continue

    def _find_search_box_js(self) -> object | None:
        """Find search input via JavaScript (handles changing WhatsApp DOM)."""
        if not self.driver:
            return None
        return self.driver.execute_script(
            """
            const roots = [
                document.querySelector('#pane-side'),
                document.querySelector('#side'),
            ].filter(Boolean);
            for (const root of roots) {
                const nodes = root.querySelectorAll(
                    '[contenteditable="true"], [role="textbox"], input[type="text"]'
                );
                for (const el of nodes) {
                    if (!el.offsetParent) continue;
                    const aria = (el.getAttribute('aria-label') || '').toLowerCase();
                    const ph = (
                        el.getAttribute('data-placeholder') ||
                        el.getAttribute('placeholder') || ''
                    ).toLowerCase();
                    const tab = el.getAttribute('data-tab');
                    if (aria.includes('search') || ph.includes('search') || tab === '3') {
                        return el;
                    }
                }
                for (const el of nodes) {
                    if (!el.offsetParent) continue;
                    if (!el.closest('[data-testid="cell-frame-container"]')) {
                        return el;
                    }
                }
            }
            return null;
            """
        )

    def _find_search_box(self) -> object:
        """Locate the sidebar search input using multiple strategies."""
        if not self.driver:
            raise TimeoutException("Driver not ready")

        self._wait_for_sidebar()
        self._activate_search_panel()
        random_delay(0.5, 1.0)

        wait = self._wait(10)

        # Strategy 1: JavaScript DOM scan
        box = self._find_search_box_js()
        if box:
            try:
                return wait.until(EC.element_to_be_clickable(box))
            except TimeoutException:
                pass

        # Strategy 2: CSS / XPath selectors
        locator_sets: list[tuple[str, str]] = [
            (By.CSS_SELECTOR, "#pane-side div[contenteditable='true'][data-tab='3']"),
            (By.CSS_SELECTOR, "#side div[contenteditable='true'][data-tab='3']"),
            (By.CSS_SELECTOR, "#pane-side div[contenteditable='true']"),
            (By.CSS_SELECTOR, "#side div[contenteditable='true']"),
            (By.CSS_SELECTOR, "#pane-side div[role='textbox']"),
            (By.CSS_SELECTOR, "#side div[role='textbox']"),
            (By.CSS_SELECTOR, 'div[title="Search input textbox"]'),
            (By.CSS_SELECTOR, '[aria-label="Search input textbox"]'),
            (By.CSS_SELECTOR, '[aria-label="Search input textbox"][contenteditable="true"]'),
            (By.XPATH, '//div[@id="pane-side"]//div[@contenteditable="true"]'),
            (By.XPATH, '//div[@id="side"]//div[@contenteditable="true"]'),
            (By.XPATH, '//*[@id="pane-side" or @id="side"]//*[@role="textbox"]'),
        ]
        for by, sel in locator_sets:
            try:
                for el in self.driver.find_elements(by, sel):
                    if el.is_displayed() and el.is_enabled():
                        return wait.until(EC.element_to_be_clickable(el))
            except (TimeoutException, StaleElementReferenceException):
                continue

        raise TimeoutException("Search box not found — is WhatsApp fully loaded?")

    def _click_contact_result(self, name: str) -> None:
        """Click matching contact/group in search results."""
        if not self.driver:
            raise TimeoutException("Driver not ready")

        wait = self._wait(15)
        name_lower = name.lower()

        # Exact title match (most reliable)
        xpaths = [
            f'//span[@title="{name}"]',
            f'//span[contains(@title, "{name}")]',
            (
                '//div[@role="listitem"]//span['
                'contains(translate(@title, "ABCDEFGHIJKLMNOPQRSTUVWXYZ", '
                '"abcdefghijklmnopqrstuvwxyz"), '
                f'"{name_lower}")]'
            ),
        ]
        for xpath in xpaths:
            try:
                el = wait.until(EC.element_to_be_clickable((By.XPATH, xpath)))
                self._safe_click(el)
                random_delay(1.0, 1.5)
                return
            except TimeoutException:
                continue

        # Fallback: scan visible list items
        items = self.driver.find_elements(By.CSS_SELECTOR, 'div[role="listitem"]')
        for item in items:
            try:
                text = (item.text or "").lower()
                title_spans = item.find_elements(By.CSS_SELECTOR, "span[title]")
                titles = [s.get_attribute("title") or "" for s in title_spans]
                if name_lower in text or any(
                    name_lower in t.lower() for t in titles
                ):
                    self._safe_click(item)
                    random_delay(1.0, 1.5)
                    return
            except StaleElementReferenceException:
                continue

        raise TimeoutException(f"Contact '{name}' not found in search results")

    def search_contact(self, name: str) -> bool:
        """
        Search and open chat for contact or group.

        Args:
            name: Display name as shown in WhatsApp.

        Returns:
            True if chat opened successfully.
        """
        if not self.driver:
            return False

        def _search() -> None:
            logger.info("Opening contact: %s", name)
            self._dismiss_overlays()
            self._wait_for_sidebar()

            # Strategy A: click Sahil directly in recent chat list (most reliable)
            if self._open_from_chat_list(name):
                logger.info("Opened chat from list: %s", name)
                return

            # Strategy B: use search bar
            logger.info("Not in recent chats — using search for: %s", name)
            search_box = self._find_search_box()
            self._safe_click(search_box)
            random_delay(0.3, 0.5)

            try:
                search_box.send_keys(Keys.CONTROL + "a")
                search_box.send_keys(Keys.BACKSPACE)
            except WebDriverException:
                pass
            random_delay(0.2, 0.4)

            self._set_contenteditable_text(search_box, name)
            logger.info("Typed search query, waiting for results...")
            random_delay(2.5, 4.0)

            self._click_contact_result(name)
            if not self._is_chat_open(name):
                raise TimeoutException(f"Chat for '{name}' did not open")
            logger.info("Opened chat via search: %s", name)

        return self._retry_action("search_contact", _search)

    def _find_message_box(self) -> object:
        """Locate the active chat message input."""
        if not self.driver:
            raise TimeoutException("Driver not ready")

        wait = self._wait()
        selectors = [
            "#main footer div[contenteditable='true']",
            "#main div[contenteditable='true'][data-tab='10']",
            '[data-testid="conversation-compose-box-input"]',
            "footer div[contenteditable='true']",
            '#main div[contenteditable="true"]',
        ]
        for sel in selectors:
            try:
                elements = self.driver.find_elements(By.CSS_SELECTOR, sel)
                for el in reversed(elements):
                    if el.is_displayed():
                        return wait.until(EC.element_to_be_clickable(el))
            except (TimeoutException, StaleElementReferenceException):
                continue
        raise TimeoutException(
            "Message input not found — open a chat first (search may have failed)"
        )

    def _click_send_button(self) -> bool:
        """Click send button if visible."""
        if not self.driver:
            return False
        send_selectors = [
            '[data-testid="send"]',
            'span[data-icon="send"]',
            'button[aria-label="Send"]',
        ]
        for sel in send_selectors:
            try:
                btn = self.driver.find_element(By.CSS_SELECTOR, sel)
                if btn.is_displayed():
                    self._safe_click(btn)
                    return True
            except NoSuchElementException:
                continue
        return False

    def send_message(self, message: str) -> bool:
        """
        Type and send message in active chat.

        Args:
            message: Text to send.

        Returns:
            True if send succeeded.
        """
        if not self.driver:
            return False

        def _send() -> None:
            # Must be exactly one word (no sentences)
            word = message.strip().split()[0]
            logger.info("Composing one word: %s", word)
            box = self._find_message_box()
            self._safe_click(box)
            random_delay(0.3, 0.5)

            # Clear any old draft text, then insert only the single word
            if self.driver:
                self.driver.execute_script(
                    "arguments[0].innerHTML=''; arguments[0].textContent='';",
                    box,
                )
            self._set_contenteditable_text(box, word)
            random_delay(0.5, 1.0)

            # Prefer Enter; fallback to send button
            try:
                box.send_keys(Keys.ENTER)
            except WebDriverException:
                self.driver.execute_script(_JS_PRESS_ENTER, box)

            random_delay(0.5, 0.8)
            if not self._click_send_button():
                logger.debug("Send button not needed or not found (Enter used)")

            random_delay(1.0, 1.5)
            logger.info("Message dispatched: %s", word)

        ok = self._retry_action("send_message", _send)
        if ok:
            logger.success("Message Sent Successfully")
        return ok

    def capture_screenshot(self, label: str) -> Path | None:
        """
        Save screenshot for debugging.

        Args:
            label: Filename prefix.

        Returns:
            Path to screenshot or None.
        """
        if not self.driver:
            return None
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = self.config.screenshots_dir / f"{label}_{ts}.png"
            self.driver.save_screenshot(str(path))
            logger.info("Screenshot saved: %s", path.name)
            error_copy = self.config.errors_dir / path.name
            if path.exists():
                shutil.copy(path, error_copy)
            return path
        except WebDriverException as e:
            logger.warning("Could not capture screenshot: %s", e)
            return None

    def run_send_flow(self, contact_name: str, message: str) -> bool:
        """
        Full flow: open WhatsApp, login, search, send.

        Args:
            contact_name: Target contact or group.
            message: Message text.

        Returns:
            True if entire flow succeeded.
        """
        success = False
        try:
            self.start_browser()
            self.open_whatsapp()
            if not self.wait_for_login():
                return False
            if not self.search_contact(contact_name):
                return False
            success = self.send_message(message)
            return success
        except WebDriverException as e:
            logger.error("WhatsApp automation error: %s", e)
            self.capture_screenshot("fatal_error")
            return False
        finally:
            if success:
                self.quit()
            else:
                logger.warning(
                    "Browser left open for debugging — close Chrome manually or re-run"
                )

    def quit(self) -> None:
        """Close browser safely."""
        if self.driver:
            try:
                self.driver.quit()
            except WebDriverException:
                pass
            self.driver = None
            logger.info("Browser closed")
