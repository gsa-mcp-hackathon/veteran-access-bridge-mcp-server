# Separate production image for the EXISTING Avery LiveKit worker.
# The API/MCP backend remains in deploy/ibm/Dockerfile.
FROM python:3.12-slim AS builder

WORKDIR /build
COPY pyproject.toml ./
COPY src/ ./src/
RUN pip install --no-cache-dir --prefix=/install ".[voice]"

FROM python:3.12-slim AS runtime
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin avery

WORKDIR /app
COPY --from=builder /install /usr/local

# LiveKit AgentServer exposes HTTP health at / on port 8081 in start mode.
# Code Engine must use --port 8081; PORT=8081 is informational here.
ENV PYTHONUNBUFFERED=1 \
    PORT=8081 \
    HOME=/home/avery
EXPOSE 8081

USER avery
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8081/', timeout=4)" || exit 1

# Never use the hot-reloading "dev" mode in a hosted application.
CMD ["veteran-access-voice-worker", "start"]
