import argparse
import asyncio
import hashlib
import os
import re
import sys
import time
from datetime import datetime
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


def sanitize_filename(url: str, ext: str = "png") -> str:
    """Turns a URL path (+ query) into a valid, unique filename."""
    parsed = urlparse(url)
    path = parsed.path.strip("/")
    base = re.sub(r"[^\w\-]", "_", path) if path else "index"

    if parsed.query:
        # Short hash of the query string, so e.g. ?id=1 and ?id=2 don't
        # produce the same filename and overwrite each other.
        query_hash = hashlib.md5(parsed.query.encode()).hexdigest()[:8]
        base = f"{base}-{query_hash}"

    return f"{base}.{ext}"


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


async def hide_fixed_elements(page):
    """`position: fixed`/`sticky` elements (nav bars, off-canvas menus,
    "back to top" buttons, ...) are anchored to the viewport. Since a
    full-page screenshot renders the whole document as one oversized
    viewport, these elements can end up duplicated, badly stretched, or
    floating at a seemingly random spot mid-page instead of pinned to the
    real screen edge. A screenshot is a static record, so hiding them right
    before capture avoids these glitches entirely - a standard technique for
    full-page screenshot tools. Elements that cover almost the entire
    viewport are left alone: on 'virtual scroll' sites (Locomotive Scroll,
    Lenis, ...) that's usually the real content wrapper, not a decorative
    overlay - see detect_virtual_scroll_container()."""
    await page.evaluate(
        """() => {
        const vw = window.innerWidth, vh = window.innerHeight;
        document.querySelectorAll('*').forEach((el) => {
            const position = getComputedStyle(el).position;
            if (position !== 'fixed' && position !== 'sticky') return;
            const rect = el.getBoundingClientRect();
            const coversViewport = rect.width >= vw * 0.9 && rect.height >= vh * 0.9;
            if (!coversViewport) {
                el.style.setProperty('visibility', 'hidden', 'important');
            }
        });
    }"""
    )


async def detect_virtual_scroll_container(page):
    """Detects 'virtual scroll' sites (Locomotive Scroll, Lenis in virtual
    mode, GSAP ScrollSmoother, ...): the native document reports almost no
    scrollable height because the real content lives inside a
    viewport-covering `position:fixed` wrapper that's moved via CSS
    transform in response to wheel/touch input, instead of native scrolling.
    Returns True if such a wrapper is found, so the caller can fall back to
    scroll-and-stitch capture instead of a native full-page screenshot."""
    return await page.evaluate(
        """() => {
        const vh = window.innerHeight;
        if (document.documentElement.scrollHeight > vh * 1.5) return false;

        const vw = window.innerWidth;
        for (const el of document.querySelectorAll('*')) {
            const cs = getComputedStyle(el);
            if (cs.position !== 'fixed') continue;
            const rect = el.getBoundingClientRect();
            const coversViewport = rect.width >= vw * 0.9 && rect.height >= vh * 0.9;
            if (coversViewport && el.scrollHeight > vh * 1.5) {
                return true;
            }
        }
        return false;
    }"""
    )


def _find_vertical_shift(old_frame, new_frame, strip_height: int = 220) -> int:
    """Measures how many pixels the page visually scrolled between two same-
    size viewport screenshots (as HxWx3 numpy arrays), by locating the old
    frame's bottom strip inside the new frame - the same technique classic
    scrolling-screenshot tools (GoFullPage etc.) use. The strip is fairly
    tall on purpose: pages with repetitive layouts (list rows, card grids)
    can otherwise produce false-positive matches against the wrong row.

    For each candidate position, scanned from the largest possible shift
    downwards, the pixel difference is checked against a sequence of
    increasingly lenient thresholds; the strictest threshold that yields any
    match wins, and within that threshold the largest (i.e. first-found)
    shift is used, since virtual-scroll progress is monotonically forward -
    preferring the largest confident shift avoids locking onto a
    coincidental near-zero-shift match. Some sites still have very minor
    ambient motion (a subtly animated hero image, ...) even once otherwise
    settled, which the strictest threshold alone would mistake for 'no
    progress'; the lenient fallback thresholds accommodate that. Returns 0
    if no match is found at all even at the loosest threshold (treated by
    the caller as 'no progress')."""
    import numpy as np

    h = old_frame.shape[0]
    template = old_frame[h - strip_height:h].astype(np.int16)[:, ::8]

    diffs = []
    for y in range(0, h - strip_height + 1, 2):
        region = new_frame[y:y + strip_height].astype(np.int16)[:, ::8]
        diffs.append((y, np.abs(region - template).mean()))

    for threshold in (6.0, 15.0, 30.0, 50.0):
        for y, diff in diffs:
            if diff <= threshold:
                return h - strip_height - y
    return 0


async def capture_via_scroll_stitching(page, filepath, freeze: bool, settle_ms: int, image_format: str = "png", max_segments: int = 60):
    """Fallback full-page capture for 'virtual scroll' sites, where the
    native document height can't be trusted (see detect_virtual_scroll_container).
    Scrolls the page with real wheel events - which virtual-scroll libraries
    listen to, unlike a programmatic window.scrollBy - and stitches the
    resulting viewport screenshots into one tall image. Many such libraries
    heavily ease/damp the scroll response, so a fixed "one viewport per
    wheel event" assumption doesn't hold; instead, the actual pixel offset
    between consecutive captures is measured (see _find_vertical_shift) and
    only the genuinely new bottom slice of each frame is appended. Stops once
    a wheel event produces no measurable further progress (the bottom was
    reached), capped at max_segments as a safety net."""
    from PIL import Image
    import numpy as np
    import io

    if freeze:
        await freeze_animations(page)

    # Sites elaborate enough to use a virtual-scroll library often also run a
    # multi-second JS preloader/intro animation before the real page (and its
    # scroll listeners) are ready. Capturing too early catches that preloader
    # instead.
    await page.wait_for_timeout(max(settle_ms, 3000))

    viewport = page.viewport_size
    vw, vh = viewport["width"], viewport["height"]
    await page.mouse.move(vw / 2, vh / 2)
    await hide_fixed_elements(page)
    await wait_for_images(page)
    await page.wait_for_timeout(settle_ms)

    def _capture_array(png_bytes):
        return np.asarray(Image.open(io.BytesIO(png_bytes)).convert("RGB"))

    first_bytes = await page.screenshot(full_page=False)
    prev_frame = await asyncio.to_thread(_capture_array, first_bytes)
    stitched_slices = [prev_frame]

    for _ in range(max_segments):
        # A burst of many small wheel ticks (mimicking a real, continuous
        # scroll gesture) reliably advances virtual-scroll libraries much
        # further than a few large wheel events, which some of them heavily
        # clamp/dampen per-event regardless of the requested delta.
        for _ in range(15):
            await page.mouse.wheel(0, 120)
            await page.wait_for_timeout(30)
        await page.wait_for_timeout(max(settle_ms, 500))
        await hide_fixed_elements(page)
        await wait_for_images(page)

        new_bytes = await page.screenshot(full_page=False)
        new_frame = await asyncio.to_thread(_capture_array, new_bytes)

        if np.array_equal(new_frame, prev_frame):
            break  # wheel input produced no visual change -> bottom reached

        shift = await asyncio.to_thread(_find_vertical_shift, prev_frame, new_frame)
        if shift <= 0:
            break  # couldn't confidently measure further progress -> stop rather than corrupt the image

        stitched_slices.append(new_frame[vh - shift:vh])
        prev_frame = new_frame

    def _stitch():
        stitched = np.concatenate(stitched_slices, axis=0)
        return _save_screenshot_image(Image.fromarray(stitched), filepath, image_format)

    return await asyncio.to_thread(_stitch)


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


# libwebp hard limit: a single WebP image cannot exceed this many pixels in
# either dimension. Full-page screenshots of very long single-page sites can
# exceed it, so saving falls back to PNG (no such limit) for that one
# screenshot rather than losing it entirely.
WEBP_MAX_DIMENSION = 16383


def _save_screenshot_image(image, filepath: str, image_format: str) -> str:
    """Saves a PIL Image in the requested format, returning the filepath
    actually used - which may differ from `filepath` (a .png swapped in for
    the requested .webp) if the WEBP_MAX_DIMENSION fallback kicked in."""
    if image_format == "webp" and max(image.size) <= WEBP_MAX_DIMENSION:
        image.save(filepath, "WEBP", lossless=True)
        return filepath
    if image_format == "webp":
        filepath = os.path.splitext(filepath)[0] + ".png"
    image.save(filepath)
    return filepath


def _save_screenshot_bytes(png_bytes: bytes, filepath: str, image_format: str) -> str:
    from PIL import Image
    import io

    return _save_screenshot_image(Image.open(io.BytesIO(png_bytes)), filepath, image_format)


async def wait_for_images(page, timeout_ms: int = 8000):
    """Waits for every currently-present <img> to actually finish loading
    (not just be triggered), so lazily-loaded images end up fully rendered
    instead of caught half-loaded or as broken-image placeholders. Capped by
    timeout_ms so one slow/broken image can't stall the whole crawl."""
    try:
        await page.evaluate(
            """(timeoutMs) => Promise.race([
                Promise.all(
                    Array.from(document.images)
                        .filter((img) => !img.complete)
                        .map((img) => new Promise((resolve) => {
                            img.addEventListener('load', resolve, { once: true });
                            img.addEventListener('error', resolve, { once: true });
                        }))
                ),
                new Promise((resolve) => setTimeout(resolve, timeoutMs)),
            ])""",
            timeout_ms,
        )
    except Exception:
        pass


async def auto_scroll(page, settle_ms: int = 800):
    """Scrolls the page down to trigger lazy-loaded images and scroll-reveal
    animations, waits for images to actually finish loading, then waits a bit
    longer for any JS-driven (non-CSS) animations to settle. Deliberately does
    NOT scroll back to the top afterwards: Playwright's full-page screenshot
    captures the whole document regardless of scroll position, and scrolling
    back up would make many scroll-reveal libraries (e.g. AOS without
    `data-aos-once`) hide elements again right before the screenshot is taken."""
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
    await wait_for_images(page)
    await page.wait_for_timeout(settle_ms)


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
        self.settle_ms = int(args.settle_time * 1000)
        self.hide_fixed = not args.no_hide_fixed_elements
        self.virtual_scroll_fallback = not args.no_virtual_scroll_fallback
        self.image_format = args.format
        self.output_dir = os.path.join(
            args.output_dir, re.sub(r"[^\w.-]", "_", self.domain)
        )
        if args.timestamped_output:
            # Groups repeated runs of the same site under it (domain first),
            # each in its own timestamped subfolder - so re-running the same
            # URL later never overwrites a previous run's screenshots, even
            # if it happens more than once on the same day.
            self.output_dir = os.path.join(self.output_dir, datetime.now().strftime("%Y-%m-%d_%H-%M-%S"))
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

            filename = sanitize_filename(url, ext=self.image_format)
            filepath = os.path.join(self.output_dir, filename)

            is_virtual_scroll = self.virtual_scroll_fallback and await detect_virtual_scroll_container(page)
            if is_virtual_scroll:
                print(f"     (virtual-scroll site detected, using scroll-and-stitch capture)")
                filepath = await capture_via_scroll_stitching(
                    page, filepath, freeze=self.freeze_animations, settle_ms=self.settle_ms,
                    image_format=self.image_format,
                )
            else:
                if self.freeze_animations:
                    await freeze_animations(page)
                await auto_scroll(page, settle_ms=self.settle_ms)
                if self.hide_fixed:
                    await hide_fixed_elements(page)
                if self.image_format == "webp":
                    screenshot_bytes = await page.screenshot(full_page=True)
                    filepath = await asyncio.to_thread(_save_screenshot_bytes, screenshot_bytes, filepath, self.image_format)
                else:
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
    parser.add_argument("--settle-time", type=float, default=0.8, help="Seconds to wait after scrolling for animations/lazy content to settle before the screenshot (default: 0.8)")
    parser.add_argument("--no-hide-fixed-elements", action="store_true", help="Don't hide position:fixed/sticky elements (nav bars, overlays) before the screenshot")
    parser.add_argument("--no-virtual-scroll-fallback", action="store_true", help="Don't use scroll-and-stitch capture for 'virtual scroll' sites (Locomotive Scroll, Lenis, ...)")
    parser.add_argument("--format", choices=["png", "webp"], default="png", help="Screenshot image format (default: png). webp is saved lossless.")
    parser.add_argument("--timestamped-output", action="store_true", help="Save under <output-dir>/<domain>/<timestamp>/ instead of <output-dir>/<domain>/ - so repeated runs of the same site don't overwrite each other")
    return parser.parse_args()


def main():
    args = parse_args()
    if args.concurrency < 1:
        sys.exit("Error: --concurrency must be at least 1.")
    crawler = Crawler(args)
    asyncio.run(crawler.run())
    if not crawler.saved:
        sys.exit(1)


if __name__ == "__main__":
    main()
