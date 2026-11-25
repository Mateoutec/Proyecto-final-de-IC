# Imagen de producción: compila el frontend y sirve todo con FastAPI (InsightFace en CPU).
FROM node:22-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.11-slim
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy
RUN apt-get update && apt-get install -y --no-install-recommends libglib2.0-0 libgomp1 \
    && rm -rf /var/lib/apt/lists/* && pip install --no-cache-dir uv
WORKDIR /app/backend
COPY backend/pyproject.toml backend/uv.lock ./
RUN uv sync --frozen --no-dev
COPY backend/ ./
COPY --from=web /app/frontend/dist /app/frontend/dist
# Modelos ONNX dentro de la imagen: el primer arranque es inmediato
RUN .venv/bin/python -m app.cli download-models
EXPOSE 8000
# En el contenedor escucha en 0.0.0.0; solo Caddy (HTTPS) lo expone a internet
CMD [".venv/bin/uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips", "*"]
