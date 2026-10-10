FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BUDGET_DB_PATH=/data/budget.db
WORKDIR /srv

# Install dependencies declared in pyproject.toml (the project is not an installable package, only its deps are needed).
COPY pyproject.toml ./
RUN pip install --no-cache-dir $(python -c "import tomllib;print(' '.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))")

COPY app ./app

RUN useradd --system --uid 10001 --no-create-home app && mkdir -p /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
