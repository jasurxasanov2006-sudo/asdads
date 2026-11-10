FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt /tmp/requirements.txt
RUN sed '/^pytest$/d' /tmp/requirements.txt > /tmp/requirements-prod.txt \
    && pip install --no-cache-dir -r /tmp/requirements-prod.txt \
    && rm /tmp/requirements.txt /tmp/requirements-prod.txt
COPY backend/*.py /app/backend/
COPY frontend/ /app/frontend/
RUN groupadd --system --gid 10001 dataflow \
    && useradd --system --uid 10001 --gid 10001 --home-dir /data --shell /usr/sbin/nologin dataflow \
    && mkdir -p /data \
    && chown dataflow:dataflow /data
ENV DATAFLOW_DATA_DIR=/data
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "main:app", "--app-dir", "/app/backend", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers", "--forwarded-allow-ips=172.30.0.0/24", "--workers", "1"]
