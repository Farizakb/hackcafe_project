# Use official python slim image
FROM python:3.11-slim

# Prevent python from buffering stdout/stderr
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1

# Set workspace
WORKDIR /app

# Install system dependencies if required
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

# Copy dependencies first for caching
COPY requirements.txt .

# Install requirements
RUN pip install --no-cache-dir -r requirements.txt

# Copy application files
COPY . .

# Expose ports: 
# - 8080: Central SRE Dashboard
# - 8000: Target Application
# - 8001: Chaos Saboteur
EXPOSE 8080 8000 8001

# Run the unified orchestrator as default entry point
CMD ["python", "main.py"]
