# One container: FastAPI serves /api/* and the built React app (SPA fallback).
FROM node:22-bookworm-slim AS web
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PORT=8000
WORKDIR /app
# B7: local OCR for photos and scanned PDFs (R13 grounding text). English data only.
RUN apt-get update \
    && apt-get install -y --no-install-recommends tesseract-ocr tesseract-ocr-eng \
    && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt
COPY vendorflow/ vendorflow/
COPY backend/ backend/
COPY --from=web /app/frontend/dist frontend/dist
RUN useradd --create-home --uid 10001 app
USER app
EXPOSE 8000
# Secrets (GEMINI_API_KEY, SUPABASE_URL, SUPABASE_SECRET_KEY, ADMIN_PASSWORD, SESSION_SECRET)
# are injected by the host at runtime — never baked into the image.
CMD ["sh", "-c", "uvicorn backend.main:app --host 0.0.0.0 --port ${PORT} --proxy-headers --forwarded-allow-ips='*'"]
