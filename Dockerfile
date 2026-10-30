# --- 1) compilation de l'interface React ---
FROM node:20-alpine AS front
WORKDIR /front
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2) serveur Python qui sert l'API et l'interface ---
FROM python:3.12-slim
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/app ./app
COPY --from=front /front/dist ./static
ENV STATIC_DIR=/app/static
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-10000}"]
