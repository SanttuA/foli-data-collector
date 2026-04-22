FROM python:3.14-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY foli_harvester ./foli_harvester

VOLUME ["/app/data"]

HEALTHCHECK --interval=60s --timeout=20s --start-period=90s --retries=3 \
  CMD python -m foli_harvester healthcheck

CMD ["python", "-m", "foli_harvester", "collect"]
