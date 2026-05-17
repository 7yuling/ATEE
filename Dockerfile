FROM python:3.12-slim

WORKDIR /app

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1
ENV ATEE_HOST=0.0.0.0
ENV ATEE_PORT=8787

COPY services ./services
COPY apps/admin-console ./apps/admin-console
COPY adapters ./adapters
COPY config/config.example.json ./config/config.example.json
COPY README.md ./README.md

RUN mkdir -p /app/config /app/data

EXPOSE 8787

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8787/health', timeout=3).read()"

CMD ["sh", "-c", "python services/core-service/check_config.py && python services/core-service/run_server.py"]
