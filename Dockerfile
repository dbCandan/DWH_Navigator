# syntax=docker/dockerfile:1
# DWH Navigator (VSA) — üretim imajı.
#   docker build -t dwh-navigator:0.2.0 .
# Ayrıntı: docs/KURULUM.md. İmaja yalnız uygulama kodu, terim sözlüğü ve durak kelimeler
# girer (bkz. .dockerignore); sözlük, ayarlar ve kayıtlar /app/data birimindedir.

# Taban imaj özetiyle sabitlenir (aynı girdi, aynı imaj); güncellemek için: docs/KURULUM.md
ARG PYTHON_IMAGE=python:3.12-alpine@sha256:1b668429b3511ab407d8e00648891631b0b1a4d7e15e3ca70f38ab5b91ad4ab4

# ---------------------------------------------------------------- bağımlılıklar
FROM ${PYTHON_IMAGE} AS build
ENV PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.lock /tmp/requirements.lock
# Sürümü ve hash'i sabitlenmiş paketler (tedarik zinciri); kurulumdan sonra pip çıkarılır.
RUN python -m venv /opt/venv \
 && /opt/venv/bin/pip install --require-hashes --no-deps --only-binary=:all: \
        -r /tmp/requirements.lock \
 && /opt/venv/bin/pip uninstall -y pip

# ---------------------------------------------------------------- çalışma imajı
FROM ${PYTHON_IMAGE}
LABEL org.opencontainers.image.title="DWH Navigator" \
      org.opencontainers.image.description="Veri Sözlüğü Asistanı" \
      org.opencontainers.image.version="0.2.0"

# İşletim sistemi yamaları; imajın kendi pip'i çalışma anında gerekmez (zafiyet yüzeyi).
RUN set -eux; \
    apk upgrade --no-cache; \
    python -m pip uninstall -y pip setuptools wheel || true; \
    addgroup -S -g 10001 vsa; \
    adduser -S -D -H -u 10001 -G vsa -h /app -s /sbin/nologin vsa

COPY --from=build /opt/venv /opt/venv
WORKDIR /app
COPY src/vsa /app/src/vsa
# data/ is a volume: a missing term dictionary / stopword file starts from these (ADR-052).
COPY data/terms.jsonl data/stopwords.jsonl /app/src/vsa/defaults/
# `vsa …` inside the container, as on a developer machine.
RUN printf '#!/bin/sh\nexec python -m vsa.cli "$@"\n' > /usr/local/bin/vsa \
 && chmod 755 /usr/local/bin/vsa

ENV PATH=/opt/venv/bin:$PATH \
    PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONIOENCODING=utf-8

RUN mkdir -p /app/data && chown vsa:vsa /app/data
USER 10001:10001
VOLUME ["/app/data"]
EXPOSE 8765

HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
  CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/healthz', timeout=4)"]

# serve builds a missing / stale index before it opens (sözlük yoksa boş açılır).
ENTRYPOINT ["vsa"]
CMD ["serve", "--host", "0.0.0.0", "--port", "8765"]
