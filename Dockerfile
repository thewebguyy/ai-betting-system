FROM python:3.11-slim

# System deps needed for weasyprint and playwright
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    libpango-1.0-0 \
    libpangocairo-1.0-0 \
    libcairo2 \
    libgdk-pixbuf2.0-0 \
    libffi-dev \
    shared-mime-info \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python deps
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Install Playwright chromium for scraping
RUN playwright install chromium --with-deps

# Copy source
COPY . .

# Create required directories
RUN mkdir -p db logs reports models/cache

# Expose FastAPI port
EXPOSE 8000

# Entry point — run migrations then start the server
CMD ["sh", "-c", "python -m backend.db_init && uvicorn backend.app:app --host 0.0.0.0 --port 8000"]
