FROM python:3.11-slim

# Create non-root user
RUN groupadd -g 1000 runner && \
    useradd -u 1000 -g runner -m -s /bin/bash runner

# Install policy_manager (if available from private repo, skip gracefully)
# In production, this would be pre-installed. For now, make it optional.
RUN pip install --no-cache-dir pip --upgrade 2>/dev/null || true

# Copy container runner
COPY __init__.py __main__.py server.py session.py policy.py /opt/container_runner/

# Copy entrypoint
COPY entrypoint.sh /opt/container_runner/entrypoint.sh
RUN chmod +x /opt/container_runner/entrypoint.sh

# Create writable directories
RUN mkdir -p /app/endpoint /app/.cache /app/.store /tmp && \
    chown -R runner:runner /app /tmp /opt/container_runner

# Set PYTHONPATH so container_runner is importable
ENV PYTHONPATH=/opt
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

USER runner
WORKDIR /app/endpoint

EXPOSE 8080

ENTRYPOINT ["/opt/container_runner/entrypoint.sh"]
