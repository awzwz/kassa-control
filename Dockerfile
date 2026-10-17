# Один образ для api и worker; отличается только команда запуска (см. docker-compose.yml).
# Шаг 1: только CPU. Для GPU базовый образ меняется через ARG BASE на nvidia/cuda (шаг 3).
ARG BASE=python:3.12-slim
FROM ${BASE}

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 \
    HF_HUB_OFFLINE=1 OMP_NUM_THREADS=2 DET_THREADS=2 MODELS_DIR=/srv/models

RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg tini \
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m -u 10001 app

WORKDIR /srv
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY app ./app
COPY tools ./tools
# веса детектора скачиваются при сборке образа; дальше сеть не нужна
RUN python tools/prepare_models.py && ls -la models
RUN mkdir -p /data && chown -R app:app /data /srv
USER app
VOLUME ["/data"]
EXPOSE 8000
ENTRYPOINT ["/usr/bin/tini", "--"]
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
