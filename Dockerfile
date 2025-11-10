# Use a lightweight, stable Python image.
FROM python:3.11-slim

# Set environment variable for unbuffered output - CRITICAL for logging in Cloud Run
ENV PYTHONUNBUFFERED 1
# Set the Cloud Run expected port to the default 8080.
ENV PORT 8080

# Set working directory inside container
WORKDIR /app

# 1. Copy and install dependencies first (for caching)
COPY requirements.txt .

# Use --no-cache-dir to keep the image small
RUN pip install --no-cache-dir --upgrade pip
# CRITICAL FIX: Ensure gunicorn, uvicorn, and all other dependencies are in requirements.txt
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy application source code (Fin-Traq V2 files: app.py, models, api, etc.)
COPY . /app

# 3. Expose port (Optional but good practice)
EXPOSE 8080

# 4. Production-Ready Command (Using Gunicorn with Uvicorn workers)
# CRITICAL FIX 1: Change 'main:app' to 'app:app' to match your application file name.
# CRITICAL FIX 2: Use the JSON array form for better signal handling and use the env var $PORT.
CMD ["gunicorn", "app:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "120"] 
# NOTE: Cloud Run will automatically map the Gunicorn port (8080) to the exposed port ($PORT).
