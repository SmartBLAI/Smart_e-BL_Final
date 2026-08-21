FROM python:3.12-slim

# opencv/paddleocr가 필요로 하는 시스템 라이브러리 (libGL 등)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
EXPOSE 5000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "5000"]
