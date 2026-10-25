FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home --uid 10001 sonic
COPY sonic ./sonic
COPY web ./web
USER sonic
EXPOSE 8080
CMD ["sh", "-c", "uvicorn sonic.api:app --host 0.0.0.0 --port ${PORT:-8080}"]
