# =============================================================================
# Stage 1 — builder
# Installs the package and its runtime dependencies into /install.
# No dev tools, no test dependencies, no secrets.
# =============================================================================
FROM python:3.12-slim AS builder

WORKDIR /build

# Copy only what is needed to build the package.
COPY pyproject.toml ./
COPY src/ ./src/

# Install into a prefix so Stage 2 can copy cleanly.
RUN pip install --no-cache-dir --prefix=/install .


# =============================================================================
# Stage 2 — runtime
# Minimal image: only the installed package + runtime interpreter.
# =============================================================================
FROM python:3.12-slim AS runtime

# Non-root user for least-privilege operation.
RUN useradd --no-create-home --shell /bin/false appuser

WORKDIR /app

# Copy installed package from builder.
COPY --from=builder /install /usr/local

# Patient-local appointment rendering must also work in the minimal runtime.
RUN python -c "from zoneinfo import ZoneInfo; ZoneInfo('America/Chicago'); ZoneInfo('America/Los_Angeles')"

# IBM Code Engine sets PORT automatically.
# Locally, the app defaults to 8080 when PORT is unset.
ENV PORT=8080
# Bind to all interfaces so Code Engine's ingress can reach the container.
ENV VAB_DEMO_HOST=0.0.0.0
# Local default: stdio MCP transport.
# Override with VAB_MCP_TRANSPORT=streamable-http for remote MCP.
ENV VAB_MCP_TRANSPORT=stdio

EXPOSE 8080

USER appuser

# Unified ASGI entry point — serves demo UI, /api/*, /health, and optionally /mcp.
CMD ["veteran-access-demo"]
