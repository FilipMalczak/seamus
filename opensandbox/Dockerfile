FROM python:3.12-slim

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SANDBOX_CONFIG_PATH=/etc/opensandbox/config.toml \
    SEAMUS_OPENSANDBOX_KEY_FILE=/var/run/seamus-opensandbox/api_key

RUN uv pip install --system --no-cache opensandbox-server

COPY sandbox.toml /etc/opensandbox/config.toml
COPY entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh && mkdir -p /data /var/run/seamus-opensandbox

EXPOSE 8080

HEALTHCHECK --interval=5s --timeout=3s --retries=10 --start-period=5s \
    CMD python3 -c "import urllib.request; urllib.request.urlopen('http://localhost:8080/health')" || exit 1

ENTRYPOINT ["/entrypoint.sh"]

