FROM python:3.11-slim

# Set up workspace structure that matches local dev
WORKDIR /workspace

# Copy the backend package into workspace
COPY . /workspace/backend/

# Install curl for healthcheck
RUN apt-get update && apt-get install -y curl && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
WORKDIR /workspace/backend
RUN pip install --no-cache-dir --upgrade pip setuptools wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip install --no-cache-dir jinja2 python-multipart

# Set working directory to workspace (parent of backend)
WORKDIR /workspace

# Run backend as a module from workspace root
CMD ["python", "-m", "backend.app"]
