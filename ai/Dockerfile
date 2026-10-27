FROM python:3.12-slim

# opencv/paddleocr가 필요로 하는 시스템 라이브러리 (libGL 등) + F4 PDF 리포트 한글 폰트(임베드용)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 libglib2.0-0 fonts-nanum \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
# OCR 모델을 빌드 시 받아 이미지에 넣는다(~/.paddlex). 오프라인 빌드면 건너뛰고 첫 기동에서 받는다.
RUN python -c "from f1_intake.extractor import OCRExtractor; OCRExtractor().warm_up()" || true
# 기동 시 OCR 엔진을 XGBoost 보다 먼저 올린다(api/main.py lifespan).
ENV OCR_WARMUP=1
EXPOSE 5000
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "5000"]
