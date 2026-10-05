# Build from the repo root: docker build -f backend/Dockerfile .
FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY agent agent
COPY backend backend
COPY contracts contracts
COPY data data
COPY evidence evidence
COPY simulation simulation

RUN useradd --system --no-create-home app
USER app

EXPOSE 8000
# One worker: investigations live in this process's memory.
CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
