# Website Auto-Screenshotter 📸

An automated, Python-based web crawler that crawls a website starting from a given URL and automatically takes a full-page screenshot of every subpage it finds.

## 🌟 Features

* **Parallel:** Crawls multiple pages at once (configurable via `--concurrency`).
* **Automatic & Complete:** Captures the entire length of the page (including scroll areas).
* **Organized Structure:** Automatically saves screenshots per domain into their own subfolders (e.g. `screenshots/example_com/`).
* **Lazy-Loading Support:** Automatic scrolling ensures lazily loaded images are captured too.
* **Clean, Unique Filenames:** Automatically converts URLs into valid image names; query parameters are kept unique via a hash.
* **Respects robots.txt:** Honors the target site's `robots.txt` by default (can be disabled with `--ignore-robots`).
* **Polite:** Small delay between requests (`--delay`) and optional blocking of tracking/ads requests, so the target site isn't put under unnecessary load.
* **Loop Protection:** Automatically detects already visited or already scheduled pages.

## ⚠️ Note

Please only crawl websites you're authorized to crawl (your own sites, or sites you have permission for). The tool respects `robots.txt` by default, but this does not replace a legal review of the target site's terms of use.

---

## 🛠️ Installation

### 1. Open the repository

```bash
cd website-screenshotter
```

### 2. Install dependencies

```bash
python3 -m pip install -r requirements.txt
python3 -m playwright install
```

### Alternative: Use the setup script

On macOS/Linux you can instead use the included bash script `setup.sh` directly:

```bash
chmod +x setup.sh && ./setup.sh
```

## 🚀 Usage

```bash
python3 run.py https://example.com
```

### Options

| Flag | Default | Description |
|---|---|---|
| `--max-pages` | 50 | Maximum number of pages to crawl |
| `--concurrency` | 3 | Number of parallel browser tabs |
| `--delay` | 0.5 | Delay in seconds between requests per worker |
| `--timeout` | 30 | Timeout per page in seconds |
| `--output-dir` | screenshots | Base output directory |
| `--ignore-robots` | off | Ignore `robots.txt` (not recommended) |
| `--no-block-trackers` | off | Don't block known tracking/ads requests |

Example with higher concurrency and more pages:

```bash
python3 run.py https://example.com --max-pages 100 --concurrency 5
```
