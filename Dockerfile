FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends curl ca-certificates && rm -rf /var/lib/apt/lists/*
RUN useradd --uid 10001 --create-home watcher && mkdir -p /app /data && chown watcher:watcher /app /data
WORKDIR /app
COPY --chown=watcher:watcher scan.py telegram_client.py run_forever.py ./
USER watcher
ENV BREADFAST_STATE_DIR=/data PYTHONUNBUFFERED=1
VOLUME /data
CMD ["python", "run_forever.py"]
