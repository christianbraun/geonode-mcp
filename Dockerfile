# ABOUTTHIS: Builds the geonode-mcp sidecar image consumed by oceb-geonode's
# ABOUTTHIS: docker-compose.yml (build context: ./mcp submodule).
FROM python:3.11-slim

WORKDIR /app
COPY pyproject.toml LICENSE .
COPY src/ src/
RUN pip install --no-cache-dir .

EXPOSE 8000
CMD ["python", "-m", "geonode_mcp.server"]
