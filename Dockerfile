FROM python:3.11-slim

# Install system dependencies
RUN apt-get update && apt-get install -y \
    wget \
    gnupg \
    curl \
    git \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Install Node.js (required for Nitter)
RUN curl -fsSL https://deb.nodesource.com/setup_18.x | bash - \
    && apt-get install -y nodejs

# Install Playwright and dependencies
RUN pip install playwright
RUN playwright install chromium
RUN playwright install-deps chromium

# Set working directory
WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .
RUN pip install -r requirements.txt

# Copy application code
COPY . .

# Expose ports
EXPOSE 8080 3000

# Default command (will be overridden by docker-compose)
CMD ["python", "bot.py"]
