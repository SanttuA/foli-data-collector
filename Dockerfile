FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV PATH="/app/.venv/bin:$PATH"

WORKDIR /app

COPY --from=ghcr.io/astral-sh/uv:0.9.30 /uv /uvx /bin/

COPY pyproject.toml uv.lock README.md LICENSE ./
COPY foli_harvester ./foli_harvester
RUN uv sync --frozen --no-dev

VOLUME ["/app/data"]

HEALTHCHECK --interval=60s --timeout=20s --start-period=90s --retries=3 \
  CMD foli-harvester healthcheck

CMD ["foli-harvester", "collect"]
