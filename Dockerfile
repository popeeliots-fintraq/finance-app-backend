# Use official Python image
FROM python:3.11-slim

# Set working directory inside container
WORKDIR /app

# Copy and install dependencies first (for caching)
COPY requirements.txt .

RUN pip install --upgrade pip
RUN pip install -r requirements.txt

# Copy application source code
COPY . .

# Expose port 8000 to the outside world
EXPOSE 8000

# Command to run the app with uvicorn
CMD ["uvicorn", "app:app", "--host", "0.0.0.0", "--port", "$PORT"]
