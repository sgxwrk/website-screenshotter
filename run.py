import argparse
import asyncio
import hashlib
import os
import re
import sys
import time
from urllib.parse import urljoin, urlparse
from urllib.robotparser import RobotFileParser

from bs4 import BeautifulSoup
from playwright.async_api import async_playwright

# File extensions that are not crawlable HTML pages and are skipped.
SKIP_EXTENSIONS = {
    ".pdf", ".jpg", ".jpeg", ".png", ".gif", ".svg", ".webp", ".ico",
    ".zip", ".rar", ".7z", ".mp4", ".mp3", ".avi", ".mov",
    ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".css", ".js", ".woff", ".woff2", ".ttf", ".eot", ".xml",
}

# Known tracking/ads domains whose requests get blocked (saves load time,
# without blocking images that are needed for the screenshot).
BLOCKED_RESOURCE_DOMAINS = (
    "google-analytics.com", "googletagmanager.com", "doubleclick.net",
    "facebook.net", "facebook.com/tr", "hotjar.com", "segment.com",
    "mixpanel.com", "intercom.io", "amplitude.com",
)

# CSS selectors for the "accept all" button of common cookie consent tools.
COOKIE_CONSENT_SELECTORS = (
    "#onetrust-accept-btn-handler",
    "#CybotCookiebotDialogBodyLevelButtonLevelOptinAllowAll",
    "#CybotCookiebotDialogBodyButtonAccept",
    "button[data-testid='uc-accept-all-button']",
    "#didomi-notice-agree-button",
    ".qc-cmp2-summary-buttons button[mode='primary']",
    "#truste-consent-button",
    ".cmplz-accept",
    ".cky-btn-accept",
    "._brlbs-btn-accept-all",
    ".iubenda-cs-accept-btn",
    ".cm-btn-accept-all",
    ".osano-cm-accept-all",
    "button[aria-label='Accept all']",
    "button[aria-label='Accept cookies']",
)

# Generic fallback: text of "accept" buttons across common consent banners
# (English and German), matched case-insensitively against the full button text.
COOKIE_CONSENT_TEXT_PATTERN = re.compile(
    r"^\s*(accept all( cookies)?|accept cookies?|accept|i agree|agree|allow all|"
    r"allow cookies|got it|i understand|alle akzeptieren|akzeptieren"
    r"( (und|&) schließen)?|zustimmen|einverstanden|alle (cookies )?erlauben|"
    r"verstanden)\s*$",
    re.IGNORECASE,
)


def normalize_domain(netloc: str) -> str:
    """Treats e.g. 'www.example.com' and 'example.com' as the same domain."""
    return netloc.lower().removeprefix("www.")


def normalize_url(url: str) -> str:
    return url.split("#")[0].rstrip("/")


def sanitize_filename(url: str) -> str:
    """Turns a URL path (+ query) into a valid, unique filename."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    base = re.sub(r"[^\w\-]", "_", path) if path else "index"

    if parsed.query:
        # Short hash of the query string, so e.g. ?id=1 and ?id=2 don't
        # produce the same filename and overwrite each other.
        query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
        base = f"{base}-{query_hash}"

    return f"{base}.png"


def is_crawlable_link(url: str) -> bool:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        return False
    ext = os.path.splitext(parsed.path)[1].lower()
    return ext not in SKIP_EXTENSIONS


async def _try_click(locator) -> bool:
    try:
        if await locator.count() == 0:
            return False
        first = locator.first
        await first.wait_for(state="visible", timeout=800)
        await first.click(timeout=800)
        return True
    except Exception:
        return False


async def _finish_dismiss(page) -> bool:
    """After accepting, some (mostly server-rendered) cookie banners only set
    a consent cookie and keep the banner markup in the DOM until the next
    navigation. Reload once so the screenshot is guaranteed to be clean."""
    await page.wait_for_timeout(300)
    try:
        await page.reload(wait_until="load", timeout=10000)
    except Exception:
        pass
    return True


async def dismiss_cookie_banner(page, timeout_ms: int = 4000) -> bool:
    """Best-effort attempt to accept a cookie consent banner, so it doesn't
    show up in the screenshot. Checks the main page and any iframes (many
    consent tools render inside one), first via known selectors for common
    consent platforms, then via generic 'accept' button text matching.
    Silently gives up if nothing matches within the timeout - not every
    consent tool (e.g. some IAB TCF/GDPR frameworks) can be covered generically.
    """
    deadline = time.monotonic() + timeout_ms / 1000
    contexts = [page] + list(page.frames)[1:]

    for ctx in contexts:
        if time.monotonic() > deadline:
            return False
        for selector in COOKIE_CONSENT_SELECTORS:
            if await _try_click(ctx.locator(selector)):
                return await _finish_dismiss(page)

    for ctx in contexts:
        if time.monotonic() > deadline:
            return False
        try:
            button = ctx.get_by_role("button", name=COOKIE_CONSENT_TEXT_PATTERN)
            if await _try_click(button):
                return await _finish_dismiss(page)
        except Exception:
            continue

    # Broadest fallback: many custom cookie banners use a <div>/<a>/<span>
    # with a click handler instead of a semantic <button>. Since the pattern
    # is anchored (^...$), this only matches elements whose *entire* text is
    # just the accept label, not larger containers with more text.
    for ctx in contexts:
        if time.monotonic() > deadline:
            return False
        try:
            text_el = ctx.get_by_text(COOKIE_CONSENT_TEXT_PATTERN)
            if await _try_click(text_el):
                return await _finish_dismiss(page)
        except Exception:
            continue

    return False


async def fix_fixed_backgrounds(page):
    """`background-attachment: fixed` is anchored to the viewport. Since a
    full-page screenshot renders the whole document as one tall viewport
    (regardless of current scroll position), fixed backgrounds can end up
    misplaced or blank. Forcing them to scroll with the page avoids this -
    a well-known workaround for full-page screenshot tools."""
    await page.add_style_tag(
        content="*, *::before, *::after { background-attachment: scroll !important; }"
    )


async def freeze_animations(page):
    """Forces CSS transitions/animations to complete instantly. Many sites
    reveal elements on scroll (fade/slide-in) via a CSS transition that only
    starts once the element enters the viewport; without this, a screenshot
    taken right after scrolling past it can catch that transition mid-flight
    (e.g. half-faded-in) instead of its finished, fully visible state."""
    await page.add_style_tag(
        content="""
        *, *::before, *::after {
            animation-duration: 0s !important;
            animation-delay: 0s !important;
            transition-duration: 0s !important;
            transition-delay: 0s !important;
            scroll-behavior: auto !important;
        }
        """
    )


async def auto_scroll(page):
    """Scrolls the page down to trigger lazy-loaded images and scroll-reveal
    animations, then waits briefly for any JS-driven (non-CSS) animations to
    settle. Deliberately does NOT scroll back to the top afterwards: Playwright's
    full-page screenshot captures the whole document regardless of scroll
    position, and scrolling back up would make many scroll-reveal libraries
    (e.g. AOS without `data-aos-once`) hide elements again right before the
    screenshot is taken."""
    await page.evaluate(
        """async () => {
        await new Promise((resolve) => {
            let totalHeight = 0;
            const distance = 400;
            const timer = setInterval(() => {
                const scrollHeight = document.body.scrollHeight;
                window.scrollBy(0, distance);
                totalHeight += distance;
                if (totalHeight >= scrollHeight) {
                    clearInterval(timer);
                    resolve();
                }
            }, 60);
        });
    }"""
    )
    await page.wait_for_timeout(400)


class Crawler:
    def __init__(self, args):
        self.start_url = normalize_url(args.url)
        self.domain = normalize_domain(urlparse(self.start_url).netloc)
        self.max_pages = args.max_pages
        self.concurrency = args.concurrency
        self.delay = args.delay
        self.timeout_ms = args.timeout * 1000
        self.block_trackers = not args.no_block_trackers
        self.dismiss_cookies = not args.no_dismiss_cookies
        self.freeze_animations = not args.no_freeze_animations
        self.output_dir = os.path.join(
            args.output_dir, re.sub(r"[^\w.-]", "_", self.domain)
        )
        os.makedirs(self.output_dir, exist_ok=True)

        self.robot_parser = None
        if not args.ignore_robots:
            self.robot_parser = self._load_robots_txt()

        self.queue = None  # created in run() (must be created within the active event loop)
        self.lock = None
        self.scheduled = {self.start_url}
        self.visited_count = 0
        self.saved = []
        self.failed = []
        self.skipped_robots = []

    def _load_robots_txt(self):
        robots_url = urljoin(self.start_url, "/robots.txt")
        parser = RobotFileParser()
        parser.set_url(robots_url)
        try:
            parser.read()
        except Exception:
            return None  # robots.txt unreachable -> don't block
        return parser

    def _allowed_by_robots(self, url: str) -> bool:
        if self.robot_parser is None:
            return True
        try:
            return self.robot_parser.can_fetch("*", url)
        except Exception:
            return True

    async def _setup_routing(self, page):
        if not self.block_trackers:
            return

        async def handle_route(route):
            if any(d in route.request.url for d in BLOCKED_RESOURCE_DOMAINS):
                await route.abort()
            else:
                await route.continue_()

        await page.route("**/*", handle_route)

    async def _process_url(self, context, url: str):
        page = await context.new_page()
        await self._setup_routing(page)
        try:
            await page.goto(url, wait_until="load", timeout=self.timeout_ms)
            if self.dismiss_cookies:
                await dismiss_cookie_banner(page)
            await fix_fixed_backgrounds(page)
            if self.freeze_animations:
                await freeze_animations(page)
            await auto_scroll(page)

            filename = sanitize_filename(url)
            filepath = os.path.join(self.output_dir, filename)
            await page.screenshot(path=filepath, full_page=True)
            self.saved.append((url, filepath))
            print(f"  -> Saved: {filepath}")

            html = await page.content()
            soup = BeautifulSoup(html, "html.parser")

            new_links = []
            for a_tag in soup.find_all("a", href=True):
                next_url = normalize_url(urljoin(self.start_url, a_tag["href"]))
                if not is_crawlable_link(next_url):
                    continue
                if normalize_domain(urlparse(next_url).netloc) != self.domain:
                    continue
                new_links.append(next_url)
            return new_links

        except Exception as e:
            self.failed.append((url, str(e)))
            print(f"  -> Error at {url}: {e}")
            return []
        finally:
            await page.close()

    async def _worker(self, worker_id: int, context):
        while True:
            async with self.lock:
                if self.visited_count >= self.max_pages:
                    break
            try:
                url = await asyncio.wait_for(self.queue.get(), timeout=2)
            except asyncio.TimeoutError:
                if self.queue.empty():
                    break
                continue

            async with self.lock:
                if self.visited_count >= self.max_pages:
                    self.queue.task_done()
                    continue
                self.visited_count += 1
                count = self.visited_count

            if not self._allowed_by_robots(url):
                self.skipped_robots.append(url)
                print(f"[{count}/{self.max_pages}] Blocked by robots.txt: {url}")
                self.queue.task_done()
                continue

            print(f"[{count}/{self.max_pages}] Loading (worker {worker_id}): {url}")
            new_links = await self._process_url(context, url)

            async with self.lock:
                for link in new_links:
                    if link not in self.scheduled and len(self.scheduled) < self.max_pages:
                        self.scheduled.add(link)
                        await self.queue.put(link)

            self.queue.task_done()
            if self.delay:
                await asyncio.sleep(self.delay)

    async def run(self):
        self.queue = asyncio.Queue()
        self.lock = asyncio.Lock()

        print(f"Start URL: {self.start_url}")
        print(f"Output folder for this run: '{self.output_dir}'")
        print(f"Max pages: {self.max_pages} | Concurrency: {self.concurrency}\n")

        await self.queue.put(self.start_url)

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(viewport={"width": 1920, "height": 1080})

            workers = [
                asyncio.create_task(self._worker(i + 1, context))
                for i in range(self.concurrency)
            ]
            await asyncio.gather(*workers)
            await browser.close()

        print("\n--- Summary ---")
        print(f"Saved: {len(self.saved)}")
        print(f"Failed: {len(self.failed)}")
        if self.failed:
            for url, err in self.failed:
                print(f"  - {url}: {err}")
        if self.skipped_robots:
            print(f"Blocked by robots.txt: {len(self.skipped_robots)}")
        print(f"\nDone! Screenshots are in '{self.output_dir}'.")


def parse_args():
    parser = argparse.ArgumentParser(
        description="Crawls a website and takes full-page screenshots of every subpage."
    )
    parser.add_argument("url", help="Start URL, e.g. https://example.com")
    parser.add_argument("--max-pages", type=int, default=50, help="Maximum number of pages (default: 50)")
    parser.add_argument("--concurrency", type=int, default=3, help="Parallel browser tabs (default: 3)")
    parser.add_argument("--delay", type=float, default=0.5, help="Delay in seconds between requests per worker (default: 0.5)")
    parser.add_argument("--timeout", type=int, default=30, help="Timeout per page in seconds (default: 30)")
    parser.add_argument("--output-dir", default="screenshots", help="Base output directory (default: screenshots)")
    parser.add_argument("--ignore-robots", action="store_true", help="Ignore robots.txt (not recommended)")
    parser.add_argument("--no-block-trackers", action="store_true", help="Don't block known tracking/ads requests")
    parser.add_argument("--no-dismiss-cookies", action="store_true", help="Don't try to auto-accept cookie consent banners")
    parser.add_argument("--no-freeze-animations", action="store_true", help="Don't force scroll-reveal/CSS animations to their finished state before the screenshot")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.concurrency < 1:
        sys.exit("Error: --concurrency must be at least 1.")
    crawler = Crawler(args)
    asyncio.run(crawler.run())


if __name__ == "__main__":
    main()
