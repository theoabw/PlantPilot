# PlantPilot
#
# One image serves the built room view and the API from FastAPI on port 8000.
# The scene artifacts are not baked in: the capture and the pipeline output are
# supplied and generated data, not repository content, so they arrive as a
# mounted volume at /app/data (see "Run it" in README.md for what it holds).
#
#   docker build -t plantpilot .
#   docker run --rm -p 8000:8000 -v "$PWD/data:/app/data:ro" plantpilot

FROM node:24-bookworm-slim AS web

WORKDIR /src/app/web
COPY app/web/package.json app/web/package-lock.json ./
RUN npm ci
COPY app/web/ ./
RUN npm run build


FROM python:3.13-slim AS runtime

# The plate OCR gate shells out to tesseract, and PDF ingest shells out to
# pdftotext. CI installs the same pair, so the image behaves like the tested
# one instead of failing on the scan endpoints.
RUN apt-get update \
 && apt-get install -y --no-install-recommends tesseract-ocr poppler-utils \
 && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.12.10 /uv /uvx /bin/

WORKDIR /app
ENV PYTHONUNBUFFERED=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy

# Dependency layer first: it changes only when the lock file does. The project
# itself is installed from app/server/src, the package path in pyproject.toml,
# and main.py resolves the repository root from that nesting, so the layout
# inside the image has to match a checkout.
COPY pyproject.toml uv.lock ./
COPY app/server/src ./app/server/src
RUN uv sync --locked --no-dev
ENV PATH="/app/.venv/bin:${PATH}"

COPY --from=web /src/app/web/dist ./app/web/dist
COPY fixtures ./fixtures
COPY site ./site

# The demo default: the complete capture the organisers re-uploaded. Override
# both to serve the capture named in the brief.
ENV PLANTPILOT_SCENE=data/equipment \
    PLANTPILOT_SPLAT=data/viewer/equipment.ply

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin plantpilot
USER plantpilot

EXPOSE 8000

# Readiness is the process answering for the built room view, not an API route:
# the API answers 404 for artifacts that are not mounted, and the mount is
# optional at startup. Compose files that want a stricter probe override this.
HEALTHCHECK --interval=30s --timeout=5s --start-period=40s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/demo/', timeout=4).status == 200 else 1)"

CMD ["uvicorn", "plantpilot.main:app", \
     "--host", "0.0.0.0", "--port", "8000", \
     "--app-dir", "app/server/src", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]
