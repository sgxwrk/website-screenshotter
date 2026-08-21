#!/bin/bash
# Template for Unraid's "User Scripts" plugin (Settings -> User Scripts ->
# Add New Script). Runs on the Unraid host, triggers a one-shot container
# run to process the URL queue, then fires a native Unraid notification
# with the result. See the "Automated queue processing on Unraid" section
# in readme.md for the full setup walkthrough.
#
# Edit the three paths below to match your setup before using this.

QUEUE_DIR="/mnt/user/appdata/website-screenshotter/queue"
OUTPUT_DIR="/mnt/user/website-screenshots"
IMAGE="website-screenshotter-batch"

docker run --rm \
    -v "$QUEUE_DIR:/data" \
    -v "$OUTPUT_DIR:/output" \
    -e "TZ=$(cat /etc/timezone 2>/dev/null || echo UTC)" \
    -e MAX_PAGES=50 \
    -e CONCURRENCY=3 \
    "$IMAGE"

SUMMARY_FILE="$OUTPUT_DIR/last-summary.txt"

# No summary means the queue was empty this run - stay quiet, don't
# notify every night if nothing was added to process.
if [ ! -f "$SUMMARY_FILE" ]; then
    echo "Nothing was queued - no notification sent."
    exit 0
fi

SUMMARY="$(cat "$SUMMARY_FILE")"

if grep -q ', 0 failed' "$SUMMARY_FILE"; then
    ICON="normal"
else
    ICON="warning"
fi

/usr/local/emhttp/webGui/scripts/notify \
    -e "Website Screenshotter" \
    -s "Nightly run complete" \
    -d "$SUMMARY" \
    -i "$ICON"
