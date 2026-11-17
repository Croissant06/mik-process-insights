FROM python:3.12-slim
WORKDIR /srv
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
COPY pyproject.toml ./
RUN pip install --no-cache-dir "fastapi>=0.115" "uvicorn[standard]>=0.30" "sqlalchemy>=2.0" \
    "alembic>=1.13" "psycopg[binary]>=3.2" "jinja2>=3.1" "pyyaml>=6.0" "tzdata>=2024.1"
COPY alembic.ini ./
COPY app ./app
COPY migrations ./migrations
COPY questionnaire ./questionnaire
COPY scripts ./scripts
EXPOSE 8000
CMD ["sh", "-c", "alembic upgrade head && uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000"]
