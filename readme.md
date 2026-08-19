# Website Auto-Screenshotter 📸

An automated, Python-based web crawler that crawls a website starting from a given URL and automatically takes a full-page screenshot of every subpage it finds. Useful for visual regression checks, archiving a site's current state, or generating a quick visual overview of a website's pages.

## 🌟 Features

* **Parallel:** Crawls multiple pages at once (configurable via `--concurrency`).
* **Automatic & Complete:** Captures the entire length of the page (including scroll areas).
* **Organized Structure:** Automatically saves screenshots per domain into their own subfolders (e.g. `screenshots/example_com/`).
* **Lazy-Loading & Scroll-Reveal Support:** Automatic scrolling triggers lazily loaded images and scroll-reveal animations (fade/slide-in effects), and CSS transitions are forced to their finished state so elements aren't caught mid-animation (can be disabled with `--no-freeze-animations`).
* **Clean, Unique Filenames:** Automatically converts URLs into valid image names; query parameters are kept unique via a hash.
* **Cookie Banner Handling:** Automatically tries to accept cookie consent banners before taking the screenshot, so they don't end up in the shot (can be disabled with `--no-dismiss-cookies`).
* **Respects robots.txt:** Honors the target site's `robots.txt` by default (can be disabled with `--ignore-robots`).
* **Polite:** Small delay between requests (`--delay`) and optional blocking of tracking/ads requests, so the target site isn't put under unnecessary load.
* **Loop Protection:** Automatically detects already visited or already scheduled pages.

## 📋 Requirements

* Python 3.9 or newer
* pip

Python dependencies ([`requirements.txt`](requirements.txt)):

* [Playwright](https://playwright.dev/python/) — browser automation and screenshotting
* [Beautiful Soup](https://www.crummy.com/software/BeautifulSoup/) — HTML link extraction

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

Example with higher concurrency and more pages:

```bash
python3 run.py https://example.com --max-pages 100 --concurrency 5
```

> **Note:** Cookie banner dismissal is a best-effort heuristic (known selectors for common consent tools like OneTrust, Cookiebot, Usercentrics, plus generic "accept all" text matching in English/German). It won't catch every consent tool, especially some IAB TCF/GDPR iframe-based implementations.

> **Known limitation:** Full-page screenshots resize the page to its full height before capturing, which recalculates any CSS sized in viewport units (`vh`). Full-viewport (`position: fixed` + `height: 100vh`) decorative backgrounds — a common hero-section pattern — can render incorrectly as a result. This is a general limitation of full-page screenshot tools, not specific to this crawler.

## ⚠️ Responsible Use

Please only crawl websites you're authorized to crawl (your own sites, or sites you have permission for). The tool respects `robots.txt` by default, but this does not replace a legal review of the target site's terms of use.

## 🐛 Support

Found a bug or have a feature request? Please [open an issue](../../issues).

## 🤝 Contributing

Contributions are welcome. Feel free to open an issue to discuss a change, or submit a pull request directly.

## 📄 License

This project is licensed under the [MIT License](LICENSE).
