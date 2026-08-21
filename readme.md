# Website Auto-Screenshotter 📸

An automated, Python-based web crawler that crawls a website starting from a given URL and automatically takes a full-page screenshot of every subpage it finds. Useful for visual regression checks, archiving a site's current state, or generating a quick visual overview of a website's pages.

## 🌟 Features

* **Parallel:** Crawls multiple pages at once (configurable via `--concurrency`).
* **Automatic & Complete:** Captures the entire length of the page (including scroll areas).
* **Organized Structure:** Automatically saves screenshots per domain into their own subfolders (e.g. `screenshots/example_com/`).
* **Lazy-Loading & Scroll-Reveal Support:** Automatic scrolling triggers lazily loaded images and scroll-reveal animations (fade/slide-in effects). CSS transitions are forced to their finished state (can be disabled with `--no-freeze-animations`), image loading is actively waited for (not just triggered), and a configurable settle delay (`--settle-time`) gives everything time to finish before the screenshot - correctness over speed.
* **Clean, Unique Filenames:** Automatically converts URLs into valid image names; query parameters are kept unique via a hash.
* **Cookie Banner Handling:** Automatically tries to accept cookie consent banners before taking the screenshot, so they don't end up in the shot (can be disabled with `--no-dismiss-cookies`).
* **Clean Fixed/Sticky Elements:** Hides `position: fixed`/`sticky` elements (nav bars, off-canvas menus, "back to top" buttons) right before the screenshot, since full-page capture can otherwise duplicate them or place them at the wrong spot (can be disabled with `--no-hide-fixed-elements`).
* **Virtual-Scroll Site Support:** Automatically detects "smooth scroll" libraries (Locomotive Scroll, Lenis, ...) that hijack native scrolling, and falls back to driving real scroll input and stitching the resulting captures together, since a native full-page screenshot renders blank/incomplete on such sites (can be disabled with `--no-virtual-scroll-fallback`).
* **Respects robots.txt:** Honors the target site's `robots.txt` by default (can be disabled with `--ignore-robots`).
* **Polite:** Small delay between requests (`--delay`) and optional blocking of tracking/ads requests, so the target site isn't put under unnecessary load.
* **Loop Protection:** Automatically detects already visited or already scheduled pages.

## 📋 Requirements

* Python 3.9 or newer
* pip

Python dependencies ([`requirements.txt`](requirements.txt)):

* [Playwright](https://playwright.dev/python/) — browser automation and screenshotting
* [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) — HTML link extraction
* [Pillow](https://python-pillow.org/) & [NumPy](https://numpy.org/) — stitching screenshots together for virtual-scroll sites, and WebP output

Docker is only needed for the optional [automated Unraid queue setup](#-automated-queue-processing-on-unraid) below - running `run.py` directly needs just Python.

## 🚀 Getting Started

### 1. Clone the repository

```bash
git clone https://github.com/sgxwrk/website-screenshotter.git
cd website-screenshotter
```

### 2. Install dependencies

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install
```

Alternatively, on macOS/Linux you can use the included setup script, which runs the same two steps:

```bash
chmod +x setup.sh && ./setup.sh
```

### 3. Run it

```bash
python3 run.py https://example.com
```

Screenshots are saved to `screenshots/<domain>/`.

## ⚙️ Configuration

All options are passed as command-line flags to `run.py`:

| Flag | Default | Description |
|---|---|---|
| `--max-pages` | 50 | Maximum number of pages to crawl |
| `--concurrency` | 3 | Number of parallel browser tabs |
| `--delay` | 0.5 | Delay in seconds between requests per worker |
| `--timeout` | 30 | Timeout per page in seconds |
| `--output-dir` | screenshots | Base output directory |
| `--ignore-robots` | off | Ignore `robots.txt` (not recommended) |
| `--no-block-trackers` | off | Don't block known tracking/ads requests |
| `--no-dismiss-cookies` | off | Don't try to auto-accept cookie consent banners |
| `--no-freeze-animations` | off | Don't force scroll-reveal/CSS animations to their finished state before the screenshot |
| `--settle-time` | 0.8 | Seconds to wait after scrolling for animations/lazy content to settle before the screenshot |
| `--no-hide-fixed-elements` | off | Don't hide `position: fixed`/`sticky` elements (nav bars, overlays) before the screenshot |
| `--no-virtual-scroll-fallback` | off | Don't use scroll-and-stitch capture for "virtual scroll" sites (Locomotive Scroll, Lenis, ...) |
| `--format` | png | Screenshot image format: `png` or `webp` (saved lossless - same quality, typically 20-30% smaller files) |

Example with higher concurrency and more pages:

```bash
python3 run.py https://example.com --max-pages 100 --concurrency 5
```

> **Tip:** If screenshots still catch animations mid-flight or lazy content missing on a particular site, increase `--settle-time` (e.g. `--settle-time 2`). This is especially relevant with `--no-freeze-animations`, where real CSS transitions need genuine wall-clock time to finish.

> **Note:** Cookie banner dismissal is a best-effort heuristic (known selectors for common consent tools like OneTrust, Cookiebot, Usercentrics, plus generic "accept all" text matching in English/German). It won't catch every consent tool, especially some IAB TCF/GDPR iframe-based implementations.

> **Note:** Full-page screenshots resize the page to its full height before capturing, which recalculates any CSS sized in viewport units (`vh`) and repositions `position: fixed`/`sticky` elements relative to that oversized viewport - a general quirk of full-page screenshot tools. Rather than risk misplaced or stretched nav overlays and decorative backgrounds, fixed/sticky elements are hidden for the shot by default (see `--no-hide-fixed-elements` above).

> **Note:** Virtual-scroll capture (see above) measures real scroll progress between captures instead of assuming a fixed step size, since these libraries often ease/damp scrolling unpredictably. On sites with unusually heavy damping or non-deterministic scroll behavior, this can occasionally duplicate a small section (e.g. a footer) in the final image rather than losing content - a deliberate "prefer a harmless repeat over silently dropping content" tradeoff.

## 🤖 Automated queue processing on Unraid

Besides running `run.py` directly, this repo also includes a Docker setup for unattended, scheduled processing on a home server (e.g. Unraid): drop URLs into a queue file, and each one is screenshotted once and then removed from the queue - a one-shot list, not a recurring watch list. Screenshots are saved under a **dated subfolder per run** (`screenshots/<domain>/<date>/...`), so re-adding the same URL later creates a new snapshot alongside the previous one instead of overwriting it. Output is saved as lossless **WebP** (same quality as PNG, meaningfully smaller) to keep long-term storage in check. This is entirely additive - running `run.py` directly (as above) is unaffected and needs no Docker at all.

### 1. Get the project onto the server

```bash
mkdir -p /mnt/user/appdata/website-screenshotter
cd /mnt/user/appdata/website-screenshotter
git clone https://github.com/sgxwrk/website-screenshotter.git .
```
(No `git` on the host? Copy the repo files over via the network share instead, e.g. `\\<server-ip>\appdata\website-screenshotter\`.)

### 2. Build the Docker image once

```bash
cd /mnt/user/appdata/website-screenshotter
docker build -t website-screenshotter-batch .
```
Re-run this manually after pulling code updates.

### 3. Create the queue and output locations

- In the Unraid WebGUI: **Shares → Add Share**, name it e.g. `website-screenshots` - this is where finished screenshots land, browsable over SMB.
- Set up the queue folder with the included template:
  ```bash
  mkdir -p /mnt/user/appdata/website-screenshotter/queue
  cp /mnt/user/appdata/website-screenshotter/urls.txt /mnt/user/appdata/website-screenshotter/queue/urls.txt
  ```

### 4. Install the "User Scripts" plugin

Apps tab → search "User Scripts" → Install (skip if you already have it).

### 5. Add the nightly script

- Settings → User Scripts → **Add New Script**, name it `nightly-screenshots`.
- Paste in the contents of [`unraid/nightly-screenshots.sh`](unraid/nightly-screenshots.sh), editing the `QUEUE_DIR`/`OUTPUT_DIR` paths at the top to match step 3.

### 6. Test it manually before scheduling

- Add one test URL to `queue/urls.txt`.
- In User Scripts, click **Run in Background** - its log streams live in the WebGUI.
- Confirm: a dated folder with a `.webp` screenshot appears under the `website-screenshots` share, `urls.txt` is back to just its comment lines, and a native Unraid notification (bell icon) appeared.

### 7. Set the nightly schedule

In the script's settings, use the schedule dropdown - pick **Custom** and enter a cron expression, e.g. `0 2 * * *` for 2:00 AM nightly - then **Apply**.

### 8. Day-to-day use

Add URLs to `queue/urls.txt` whenever (edit over the network share, or via Unraid's file manager). Each one is picked up, screenshotted, and removed from the list at the next scheduled run. Failures are logged to `queue/failed.txt` (with a timestamp and reason) instead of being retried automatically - check back on it occasionally.

Batch-wide settings (`MAX_PAGES`, `CONCURRENCY`, `DELAY`, `TIMEOUT`, `SETTLE_TIME` - matching the `run.py` flags of the same name) are set as environment variables on the `docker run` call in `unraid/nightly-screenshots.sh`.

## ⚠️ Responsible Use

Please only crawl websites you're authorized to crawl (your own sites, or sites you have permission for). The tool respects `robots.txt` by default, but this does not replace a legal review of the target site's terms of use.

## 🐛 Support

Found a bug or have a feature request? Please [open an issue](../../issues).

## 🤝 Contributing

Contributions are welcome. Feel free to open an issue to discuss a change, or submit a pull request directly.

## 📄 License

This project is licensed under the [MIT License](LICENSE).
