FROM python:3.12-slim

LABEL maintainer="CodeSentinel"
LABEL org.opencontainers.image.source="https://github.com/tzone85/code-sentinal-h"

# Avoid .pyc files and enable unbuffered output for real-time logs
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Install the codesentinel package
COPY .. /app/
RUN pip install --no-cache-dir /app

# Copy the entrypoint script
COPY entrypoint.py /app/entrypoint.py

ENTRYPOINT ["python", "/app/entrypoint.py"]
