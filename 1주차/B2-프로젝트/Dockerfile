# syntax=docker/dockerfile:1
FROM node:22-bookworm-slim AS frontend
WORKDIR /frontend
COPY b2-service/package.json b2-service/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY b2-service/index.html b2-service/tsconfig.json ./
COPY b2-service/src ./src
RUN npm run build

FROM python:3.12-slim-bookworm AS runtime
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONUTF8=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 HF_HUB_OFFLINE=1 TRANSFORMERS_OFFLINE=1 \
    HF_HUB_DISABLE_TELEMETRY=1 DO_NOT_TRACK=1 \
    B2_DATABASE=/app/b2-service/data/meetings.sqlite3 B2_MANUAL_ONLY=1
COPY requirements-web.txt /tmp/requirements-web.txt
RUN pip install --no-cache-dir -r /tmp/requirements-web.txt \
    && useradd --create-home --uid 10001 b2 \
    && mkdir -p /app/b2-service/data /app/b2-model/results /app/b2-model/models \
    && chown -R b2:b2 /app
WORKDIR /app/b2-service
USER b2
EXPOSE 8766
CMD ["python", "-m", "uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8766"]

FROM runtime AS ai-deps
USER root
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY requirements-ai.txt /tmp/requirements-ai.txt
RUN pip install --no-cache-dir torch==2.9.1 --index-url https://download.pytorch.org/whl/cu128 \
    && pip install --no-cache-dir -c /tmp/requirements-web.txt -r /tmp/requirements-ai.txt
USER b2

FROM runtime AS web
COPY --chown=b2:b2 b2-service/*.py ./
COPY --chown=b2:b2 b2-service/sample ./sample
COPY --chown=b2:b2 --from=frontend /frontend/dist ./dist
COPY --chown=b2:b2 b2-model/runtime.py /app/b2-model/runtime.py

FROM ai-deps AS ai
ENV B2_MANUAL_ONLY=0
COPY --chown=b2:b2 --from=web /app /app
