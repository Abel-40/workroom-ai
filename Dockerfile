FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /workroom-ai

COPY requirements.txt .

RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Create a non-root user
RUN groupadd --gid 1000 workroom-ai \
    && useradd --uid 1000 --gid 1000 --create-home --shell /bin/bash workroom-ai

COPY . .

RUN chown -R workroom-ai:workroom-ai /workroom-ai

USER workroom-ai

EXPOSE 8001

# Standalone-deployment default; docker-compose.yml overrides with
# `uvicorn --reload` for local hot-reload dev. Fewer workers than the
# Django service: each LLM call is long-lived (up to REQUEST_TIMEOUT_SECONDS),
# so this is sized to avoid piling up concurrent outbound calls, not to
# maximize throughput.
CMD ["gunicorn", "apps.main:app", "-k", "uvicorn_worker.UvicornWorker", \
     "--bind", "0.0.0.0:8001", "--workers", "2", "--timeout", "90"]