# Use a lightweight, stable Python image.
FROM python:3.11-slim

# Set environment variable for unbuffered output - CRITICAL for logging in Cloud Run
ENV PYTHONUNBUFFERED 1
# Set the Cloud Run expected port to the default 8080.
# While Cloud Run provides $PORT, setting a default here is safer for local testing.
ENV PORT 8080

# Set working directory inside container
WORKDIR /app

# 1. Copy and install dependencies first (for caching)
# This layer is only rebuilt if requirements.txt changes.
COPY requirements.txt .

# Use --no-cache-dir to keep the image small
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy application source code (Fin-Traq V2 files: main.py, ML logic, etc.)
# Copy everything from the current directory into the container's /app directory.
COPY . /app

# 3. Expose port (Optional but good practice)
EXPOSE 8080

# 4. Production-Ready Command (Using Gunicorn with Uvicorn workers)
# CRITICAL: 'app.main:app' assumes your application object 'app' is in a file at 'app/main.py'.
# Adjust 'app.main:app' if your entry file/object is different (e.g., 'main:app' for main.py).
CMD ["gunicorn", "main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:$PORT", \
     "--timeout", "120"]
