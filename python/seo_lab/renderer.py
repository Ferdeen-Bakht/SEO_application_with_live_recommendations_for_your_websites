"""Render JavaScript-built pages in a real browser (Edge/Chrome via Playwright), read-only.

Many modern sites (React, Vue, ...) ship an empty HTML shell and build the page in the browser. A plain HTTP
crawler sees nothing; Google and visitors see the finished page. This module returns the finished DOM.
"""
from playwright.sync_api import Error as PlaywrightError, sync_playwright

from seo_lab.config import BROWSER_CHANNEL

BLOCKED_TYPES = {"image", "media", "font"}  # not needed to read text; <img> tags stay in the DOM


class Renderer:
    """One browser for many pages. Use as a context manager and stay on the thread that created it."""

    def __init__(self, timeout_ms: int = 30000):
        self.timeout_ms = timeout_ms
        self._pw = self._browser = self._context = None

    def __enter__(self):
        return self  # the browser itself starts on the first render() call, so raw-HTML sites never pay for it

    def _start(self):
        self._pw = sync_playwright().start()
        try:
            self._browser = self._pw.chromium.launch(channel=BROWSER_CHANNEL, headless=True)
        except PlaywrightError as exc:
            self._pw.stop()
            raise RuntimeError(f"Could not start the '{BROWSER_CHANNEL}' browser: {exc}. Set BROWSER_CHANNEL=chrome or msedge in .env.") from exc
        self._context = self._browser.new_context(user_agent="Mozilla/5.0 (compatible; AISEOLab/0.2; read-only audit)")
        self._context.route("**/*", lambda route: route.abort() if route.request.resource_type in BLOCKED_TYPES else route.continue_())

    def __exit__(self, *exc):
        for obj in (self._context, self._browser):
            try:
                obj and obj.close()
            except PlaywrightError:
                pass
        if self._pw:
            self._pw.stop()

    def render(self, url: str) -> dict:
        """Return {'html', 'status', 'final_url'} for the page after JavaScript has run."""
        if self._context is None:
            self._start()
        page = self._context.new_page()
        try:
            response = page.goto(url, wait_until="networkidle", timeout=self.timeout_ms)
            page.wait_for_timeout(800)  # let late client-side updates (titles, lazy sections) land
            return {"html": page.content(), "status": response.status if response else 0, "final_url": page.url}
        finally:
            page.close()


def looks_like_js_shell(html: str, word_count: int) -> bool:
    """True when the raw HTML has almost no readable text but an app mount point or script bundle."""
    lowered = html.lower()
    has_mount = any(m in lowered for m in ('id="root"', 'id="app"', 'id="__next"', 'id="__nuxt"', "ng-app", "<app-root"))
    return word_count < 40 and (has_mount or "<script" in lowered)
