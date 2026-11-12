FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    SECURITY_CHECK_REQUIRE_TOKEN=1 \
    SECURITY_CHECK_HTTPS=1

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
    && python -m playwright install --with-deps chromium

COPY . .

ENV PORT=8080
EXPOSE 8080

CMD ["sh", "-c", "gunicorn --bind 0.0.0.0:${PORT:-8080} --workers 1 --threads 4 --timeout 180 app:app"]
