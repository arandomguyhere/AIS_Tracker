# Arsenal Ship Tracker
# Multi-stage build for minimal image size

FROM python:3.11-slim as builder

WORKDIR /app

# Install build dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir --user -r requirements.txt

# Production image
FROM python:3.11-slim

WORKDIR /app

# Copy installed packages from builder
COPY --from=builder /root/.local /root/.local
ENV PATH=/root/.local/bin:$PATH

# Copy application code
COPY *.py ./
COPY schema.sql ./
COPY static/ ./static/
COPY ais_sources/ ./ais_sources/
COPY osint/ ./osint/
COPY tests/ ./tests/
COPY data/ ./data/

# Create directories for runtime data
RUN mkdir -p /app/static/photos

# Expose port
EXPOSE 8080

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/api/stats')" || exit 1

# Initialize database and start server
CMD ["sh", "-c", "python server.py init && python server.py"]
