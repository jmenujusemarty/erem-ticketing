FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Bezpečnost: spouštěj jako non-root uživatel
RUN useradd -m -u 1000 appuser && \
    mkdir -p /app/data && \
    chown -R appuser:appuser /app

USER appuser

ENV DATABASE=/app/data/complaints.db

CMD ["gunicorn", "app:app", "--workers", "1", "--bind", "0.0.0.0:5000", "--timeout", "120", "--access-logfile", "-", "--keep-alive", "5"]
