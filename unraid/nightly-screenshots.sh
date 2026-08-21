#!/bin/bash
# Template for Unraid's "User Scripts" plugin (Settings -> User Scripts ->
# Add New Script). Runs on the Unraid host, triggers a one-shot container
# run to process the URL queue. Every run is appended to a log file;
# an Unraid notification only fires when the whole run failed (every
# queued URL failed), to keep routine runs quiet. See the "Automated
# queue processing on Unraid" section in readme.md for the full setup
# walkthrough.
#
# Edit the three paths below to match your setup before using this.

QUEUE_DIR="/mnt/user/appdata/website-screenshotter/queue"
OUTPUT_DIR="/mnt/user/website-screenshots"
IMAGE="website-screenshotter-batch"
LOG_FILE="$QUEUE_DIR/run-log.txt"

docker run --rm \
    -v "$QUEUE_DIR:/data" \
    -v "$OUTPUT_DIR:/output" \
    -e "TZ=$(cat /etc/timezone 2>/dev/null || echo UTC)" \
    -e MAX_PAGES=50 \
    -e CONCURRENCY=3 \
    -e IGNORE_ROBOTS=true \
    "$IMAGE"
DOCKER_EXIT_CODE=$?

SUMMARY_FILE="$OUTPUT_DIR/last-summary.txt"

# No summary means the queue was empty this run - nothing to log.
if [ ! -f "$SUMMARY_FILE" ]; then
    exit 0
fi

SUMMARY="$(cat "$SUMMARY_FILE")"

{
    echo "=== $(date -Iseconds) ==="
    echo "$SUMMARY"
    echo ""
} >> "$LOG_FILE"

# Only notify Unraid if the entire run failed (every queued URL failed,
# e.g. a broken image or a Docker/network problem) - routine successes and
# partial failures are quiet by design; check $LOG_FILE (or queue/failed.txt
# for which specific URLs failed) whenever you want to look.
if [ "$DOCKER_EXIT_CODE" -ne 0 ]; then
    /usr/local/emhttp/webGui/scripts/notify \
        -e "Website Screenshotter" \
        -s "Nightly run failed" \
        -d "$SUMMARY" \
        -i "alert"
fi
