#!/bin/bash
# Batch/queue runner for unattended use (see the "Automated queue processing
# on Unraid" section in readme.md). Each URL in /data/urls.txt is
# screenshotted exactly once via run.py, then removed from the queue -
# successes simply disappear, failures are logged to /data/failed.txt for
# manual review instead of retrying automatically.
#
# A queue line can optionally carry extra run.py flags after the URL, e.g.
#   https://example.com --max-pages 20 --delay 2
# which override the MAX_PAGES/CONCURRENCY/... defaults below for that one
# site only, since they're passed to run.py after (so argparse lets them win).
set -uo pipefail

DATA_DIR="/data"
OUTPUT_DIR="/output"
URLS_FILE="$DATA_DIR/urls.txt"
FAILED_FILE="$DATA_DIR/failed.txt"
SUMMARY_FILE="$OUTPUT_DIR/last-summary.txt"

MAX_PAGES="${MAX_PAGES:-50}"
CONCURRENCY="${CONCURRENCY:-3}"
DELAY="${DELAY:-0.5}"
TIMEOUT="${TIMEOUT:-30}"
SETTLE_TIME="${SETTLE_TIME:-0.8}"
IGNORE_ROBOTS="${IGNORE_ROBOTS:-false}"

RUN_PY_ARGS=(
    --output-dir "$OUTPUT_DIR"
    --timestamped-output
    --max-pages "$MAX_PAGES"
    --concurrency "$CONCURRENCY"
    --delay "$DELAY"
    --timeout "$TIMEOUT"
    --settle-time "$SETTLE_TIME"
)
if [ "$IGNORE_ROBOTS" = "true" ]; then
    RUN_PY_ARGS+=(--ignore-robots)
fi

if [ ! -f "$URLS_FILE" ]; then
    echo "No queue file found at $URLS_FILE - nothing to do."
    exit 0
fi

# last-summary.txt is a fixed path, overwritten each run - remove any old
# one up front so a night with an empty queue doesn't leave a stale summary
# behind for the host script to mistake for a fresh result and notify about.
rm -f "$SUMMARY_FILE"

# Snapshot the queue lines to process this run (ignore blank lines and #
# comments), so anything added to urls.txt while this run is in progress is
# left alone for the next run instead of being silently picked up mid-batch.
SNAPSHOT_FILE=$(mktemp)
grep -vE '^[[:space:]]*(#|$)' "$URLS_FILE" > "$SNAPSHOT_FILE" || true

if [ ! -s "$SNAPSHOT_FILE" ]; then
    echo "Queue is empty - nothing to do."
    rm -f "$SNAPSHOT_FILE"
    exit 0
fi

mkdir -p "$OUTPUT_DIR"

SUCCEEDED=0
FAILED=0
FAILED_URLS=()

while IFS= read -r line; do
    [ -z "$line" ] && continue
    url="${line%% *}"
    extra_args="${line#"$url"}"
    echo "=== Processing: $url ==="
    # extra_args is intentionally unquoted below so its whitespace-separated
    # flags (if any) are split into separate arguments, not one literal string.
    # shellcheck disable=SC2086
    if python3 run.py "$url" "${RUN_PY_ARGS[@]}" $extra_args; then
        SUCCEEDED=$((SUCCEEDED + 1))
    else
        FAILED=$((FAILED + 1))
        FAILED_URLS+=("$url")
        printf '%s\t%s\t%s\n' "$(date -Iseconds)" "$line" "run.py exited non-zero" >> "$FAILED_FILE"
    fi
done < "$SNAPSHOT_FILE"

# Remove exactly the queue lines that were just processed from the live
# queue file - preserves comment/header lines and anything appended to
# urls.txt while this run was in progress.
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
} > "$SUMMARY_FILE"

echo "Done. $SUCCEEDED succeeded, $FAILED failed."

# Only signal hard failure if literally everything failed - a couple of
# flaky sites shouldn't be treated the same as "the whole run is broken".
if [ "$FAILED" -gt 0 ] && [ "$SUCCEEDED" -eq 0 ]; then
    exit 1
fi
exit 0
