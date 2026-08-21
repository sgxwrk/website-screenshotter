# This base image ships the Chromium/Firefox/WebKit browser binaries for a
# specific Playwright release, but (perhaps surprisingly) not the `playwright`
# Python package itself - it's installed explicitly below, pinned to match
# the tag exactly, since the package and the pre-downloaded browsers are
# tightly version-coupled. Bump both together when upgrading.
FROM mcr.microsoft.com/playwright/python:v1.60.0-noble

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir playwright==1.60.0 \
    && grep -v '^playwright' requirements.txt > requirements-docker.txt \
    && pip install --no-cache-dir -r requirements-docker.txt

COPY run.py .
COPY docker-entrypoint.sh /usr/local/bin/docker-entrypoint.sh
RUN chmod +x /usr/local/bin/docker-entrypoint.sh

ENTRYPOINT ["docker-entrypoint.sh"]
