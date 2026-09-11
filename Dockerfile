# --- stage 1: build the frontend static assets -----------------------------
FROM node:20-slim AS frontend-build
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- stage 2: runtime ---------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

COPY backend/requirements.txt backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

COPY backend/ backend/
COPY scripts/ scripts/
COPY data/ data/
COPY --from=frontend-build /app/frontend/dist frontend/dist

ENV DATA_DIR=/app/data
EXPOSE 8080

CMD ["uvicorn", "app.main:app", "--app-dir", "backend", "--host", "0.0.0.0", "--port", "8080"]
