FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app

COPY requirements.txt requirements-embed.txt ./
RUN pip install -r requirements.txt -r requirements-embed.txt

COPY app ./app
COPY scripts ./scripts
COPY data ./data
COPY tests ./tests
COPY pyproject.toml ./
RUN mkdir -p artifacts && useradd --create-home trialmatch && chown -R trialmatch /app
USER trialmatch

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--timeout-keep-alive", "75"]
