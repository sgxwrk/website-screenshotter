#!/bin/bash
# Batch/queue runner for unattended use (see the "Automated queue processing
# on Unraid" section in readme.md). Each URL in /data/urls.txt is
# screenshotted exactly once via run.py, then removed from the queue -
# successes simply disappear, failures are logged to /data/failed.txt for
# manual review instead of retrying automatically.
set -uo pipefail

DATA_DIR="/data"
URLS_FILE="$DATA_DIR/urls.txt"
FAILED_FILE="$DATA_DIR/failed.txt"

MAX_PAGES="${MAX_PAGES:-50}"
CONCURRENCY="${CONCURRENCY:-3}"
DELAY="${DELAY:-0.5}"
TIMEOUT="${TIMEOUT:-30}"
SETTLE_TIME="${SETTLE_TIME:-0.8}"

if [ ! -f "$URLS_FILE" ]; then
    echo "No queue file found at $URLS_FILE - nothing to do."
    exit 0
fi

# Snapshot the URLs to process this run (ignore blank lines and # comments),
# so anything added to urls.txt while this run is in progress is left alone
# for the next run instead of being silently picked up mid-batch.
SNAPSHOT_FILE=$(mktemp)
grep -vE '^[[:space:]]*(#|$)' "$URLS_FILE" > "$SNAPSHOT_FILE" || true

if [ ! -s "$SNAPSHOT_FILE" ]; then
    echo "Queue is empty - nothing to do."
    rm -f "$SNAPSHOT_FILE"
    exit 0
fi

OUTPUT_DIR="/output/$(date +%F)"
mkdir -p "$OUTPUT_DIR"

SUCCEEDED=0
FAILED=0
FAILED_URLS=()

while IFS= read -r url; do
    [ -z "$url" ] && continue
    echo "=== Processing: $url ==="
    if python3 run.py "$url" \
        --output-dir "$OUTPUT_DIR" \
        --format webp \
        --max-pages "$MAX_PAGES" \
        --concurrency "$CONCURRENCY" \
        --delay "$DELAY" \
        --timeout "$TIMEOUT" \
        --settle-time "$SETTLE_TIME"; then
        SUCCEEDED=$((SUCCEEDED + 1))
    else
        FAILED=$((FAILED + 1))
        FAILED_URLS+=("$url")
        printf '%s\t%s\t%s\n' "$(date -Iseconds)" "$url" "run.py exited non-zero" >> "$FAILED_FILE"
    fi
done < "$SNAPSHOT_FILE"

# Remove exactly the URLs that were just processed from the live queue file -
# preserves comment/header lines and anything appended to urls.txt while
# this run was in progress.
TMP_URLS=$(mktemp)
grep -v -F -x -f "$SNAPSHOT_FILE" "$URLS_FILE" > "$TMP_URLS" || true
mv "$TMP_URLS" "$URLS_FILE"
rm -f "$SNAPSHOT_FILE"

{
    echo "$SUCCEEDED succeeded, $FAILED failed"
    if [ "$FAILED" -gt 0 ]; then
        echo "Failed (see failed.txt):"
        printf '  - %s\n' "${FAILED_URLS[@]}"
    fi
} > "$OUTPUT_DIR/summary.txt"

echo "Done. $SUCCEEDED succeeded, $FAILED failed."

# Only signal hard failure if literally everything failed - a couple of
# flaky sites shouldn't be treated the same as "the whole run is broken".
if [ "$FAILED" -gt 0 ] && [ "$SUCCEEDED" -eq 0 ]; then
    exit 1
fi
exit 0
