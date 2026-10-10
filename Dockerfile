# Python 3.11 slim production image
FROM python:3.11-slim

# Avoid buffering stdout and stderr
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PORT=5000

# Set working directory
WORKDIR /app

# Install system dependencies (needed for psycopg2, libpq, and image processing)
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt gunicorn

# Copy only deployment-necessary application source code
COPY app/ app/
COPY policies/ policies/
COPY static/ static/
COPY templates/ templates/
COPY run.py .

# Ensure upload directory exists
RUN mkdir -p static/uploads

# Expose target port
EXPOSE 5000

# Run with gunicorn
CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-5000} --workers 4 --threads 2 --timeout 120 run:app"]
