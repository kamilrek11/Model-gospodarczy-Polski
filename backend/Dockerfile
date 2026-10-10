FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 BUDGET_DB_PATH=/data/budget.db
WORKDIR /srv

# Install the pinned RUNTIME dependencies of pyproject.toml (the project is not an installable package);
# the dev group (pytest) is deliberately not installed in the image.
COPY pyproject.toml ./
RUN pip install --no-cache-dir $(python -c "import tomllib;print(' '.join(tomllib.load(open('pyproject.toml','rb'))['project']['dependencies']))")

COPY app ./app

RUN useradd --system --uid 10001 --no-create-home app && mkdir -p /data && chown app /data
USER app
VOLUME /data
EXPOSE 8000
# Run uvicorn with a SINGLE worker: the refresh job state (app/api/refresh.py) lives in the process,
# so several workers would report inconsistent /refresh/status and could run refreshes concurrently.
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
