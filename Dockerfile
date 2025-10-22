# Use a lightweight, stable Python image.
# We will use the same image for the final stage for simplicity, 
# as multi-stage often doesn't save much for Python without heavy build steps.
FROM python:3.11-slim

# Set environment variable for unbuffered output - CRITICAL for logging in Cloud Run
ENV PYTHONUNBUFFERED 1
# Set the Cloud Run expected port to the default 8080.
ENV PORT 8080

# Set working directory inside container
WORKDIR /app

# 1. Copy and install dependencies first (for caching)
# This layer is only rebuilt if requirements.txt changes.
COPY requirements.txt .

# Use --no-cache-dir to keep the image small
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# 2. Copy application source code (replace `app:app` with your actual module path)
# Assuming your main FastAPI application object is named 'app' inside 'app/main.py'
COPY . /app

# 3. Expose port (Optional but good practice)
# Cloud Run automatically handles port 8080, which we set in ENV PORT.
EXPOSE 8080

# 4. Production-Ready Command (CRITICAL CHANGE)
# Use Gunicorn as the process manager with Uvicorn workers for concurrency and stability.
# Cloud Run injects the listening port via the $PORT environment variable (defaulting to 8080).
# The '$PORT' variable in your CMD should NOT be quoted or the value might be misinterpreted.
CMD ["gunicorn", "app.main:app", \
     "--workers", "4", \
     "--worker-class", "uvicorn.workers.UvicornWorker", \
     "--bind", "0.0.0.0:8080", \
     "--timeout", "120"]
