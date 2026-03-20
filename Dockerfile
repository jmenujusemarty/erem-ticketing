FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN mkdir -p /app/data

ENV DATABASE=/app/data/complaints.db

CMD ["gunicorn", "app:app", "--workers", "1", "--bind", "0.0.0.0:5000", "--timeout", "120", "--access-logfile", "-", "--keep-alive", "5"]
