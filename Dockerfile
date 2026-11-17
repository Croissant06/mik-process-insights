# Reproducible build: dependencies come from the hash-pinned lock file (requirements.txt).
FROM python:3.12-slim AS base
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/srv \
    PIP_NO_CACHE_DIR=1 PIP_DISABLE_PIP_VERSION_CHECK=1
COPY requirements.txt ./
RUN pip install --require-hashes -r requirements.txt
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY questionnaire ./questionnaire
COPY scripts ./scripts

# Test image: used only by docker-compose.test.yml
FROM base AS test
COPY requirements-dev.txt ./
RUN pip install --require-hashes -r requirements-dev.txt
COPY tests ./tests
COPY docs ./docs
# Files that regression tests read (never the real .env; .dockerignore keeps it out of the build context)
COPY Dockerfile .env.example ./
CMD ["python", "-m", "pytest", "-q"]

# Runtime image (last stage = default target)
FROM base AS runtime
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
