# ==============================================================================
# Omnididact Multi-stage Dockerfile
# Stage 1: Build the React 18 / Vite / TypeScript Frontend
# Stage 2: Minimal Python 3.11 Runtime for FastAPI & Document Processing
# ==============================================================================

# --- Stage 1: Frontend Build ---
FROM node:20-alpine AS frontend-builder
WORKDIR /app/frontend

# Install dependencies with caching
COPY frontend/package*.json ./
RUN npm ci

# Copy frontend source and build static artifacts
COPY frontend/ ./
RUN npm run build

# --- Stage 2: Python Backend Runtime ---
FROM python:3.11-slim AS runtime

WORKDIR /app

# Set production environment flags
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HOST=0.0.0.0 \
    PORT=8000

# Install lightweight system dependencies for PyMuPDF & networking
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy backend application source code
COPY config_store.py config_app.py doc_converter.py proxy.py study_router.py study_service.py ./
COPY providers/ ./providers/
COPY plugins/ ./plugins/
COPY study/ ./study/
COPY templates/ ./templates/
COPY static/ ./static/

# Copy default config template
COPY config.example.json ./config.example.json

# Copy compiled frontend from Stage 1
COPY --from=frontend-builder /app/frontend/dist ./frontend/dist

# Create runtime directories
RUN mkdir -p /app/data/documents /app/data/uploads

# Expose default HTTP service port
EXPOSE 8000

# Mountable persistent storage
VOLUME ["/app/data"]

# Healthcheck
HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD curl -f http://localhost:8000/study || exit 1

# Start the Omnididact service
CMD ["python", "proxy.py"]
