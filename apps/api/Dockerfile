FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends poppler-utils && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY cyberhunter_api ./cyberhunter_api
COPY static ./static
RUN useradd -r -u 10001 app
USER app
EXPOSE 8000
CMD ["uvicorn", "cyberhunter_api.server:app", "--host", "0.0.0.0", "--port", "8000"]
