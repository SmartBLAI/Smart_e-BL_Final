"""
B/L AI 하자 검증 시스템 - 전역 설정
"""

import os

# 데이터 경로
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
SAMPLE_DATA_DIR = os.path.join(BASE_DIR, "Sample Data", "025.OCR 데이터(금융 및 물류)", "01-1.정식개방데이터")

TRAINING_LABEL_DIR = os.path.join(SAMPLE_DATA_DIR, "Training", "02.라벨링데이터", "TL_물류_3.선하증권_BL01")
TRAINING_IMAGE_DIR = os.path.join(SAMPLE_DATA_DIR, "Training", "01.원천데이터", "TS_물류_3.선하증권_BL01")
VALIDATION_IMAGE_DIR = os.path.join(SAMPLE_DATA_DIR, "Validation", "01.원천데이터", "VS_물류_3.선하증권_BL01")

# OCR 설정
OCR_LANGUAGE = ["en"]          # PaddleOCR 언어 (영어 기본)
OCR_USE_GPU = False            # GPU 사용 여부

# 필드 추출 설정 (정규화된 좌표 비율 기준, 이미지 너비/높이 대비)
FIELD_REGIONS = {
    "bl_no": {"x_ratio": (0.45, 1.0), "y_ratio": (0.05, 0.18)},       # 우측 상단
    "shipper": {"x_ratio": (0.0, 0.5), "y_ratio": (0.10, 0.30)},      # 좌측 상단
    "consignee": {"x_ratio": (0.5, 1.0), "y_ratio": (0.18, 0.35)},    # 우측 중상
    "notify_party": {"x_ratio": (0.0, 0.5), "y_ratio": (0.30, 0.50)}, # 좌측 중간
    "vessel": {"x_ratio": (0.0, 0.5), "y_ratio": (0.50, 0.60)},       # 좌측 중하
    "port_of_loading": {"x_ratio": (0.0, 0.5), "y_ratio": (0.55, 0.65)},
    "port_of_discharge": {"x_ratio": (0.5, 1.0), "y_ratio": (0.55, 0.65)},
    "description": {"x_ratio": (0.3, 0.8), "y_ratio": (0.60, 0.85)},
    "gross_weight": {"x_ratio": (0.6, 0.9), "y_ratio": (0.70, 0.90)},
    "measurement": {"x_ratio": (0.8, 1.0), "y_ratio": (0.70, 0.90)},
    "date_of_issue": {"x_ratio": (0.0, 0.5), "y_ratio": (0.85, 1.0)},
    "place_of_issue": {"x_ratio": (0.0, 0.5), "y_ratio": (0.82, 0.95)},
}

# 하자 검증 룰 (ICC UCP 600 기반)
DEFECT_CODES = {
    "D001": "B/L 번호 누락",
    "D002": "선적일이 L/C 기한 초과",
    "D003": "선적항 불일치",
    "D004": "양하항 불일치",
    "D005": "수화인(Consignee) 불일치",
    "D006": "화물 명세 불일치",
    "D007": "중량·수량 초과",
    "D008": "발행일이 L/C 유효기간 초과",
    "D009": "Shipper 정보 누락",
    "D010": "Notify Party 정보 누락",
    "D011": "선박명 누락",
    "D012": "항구 정보 누락",
}

# 정규식 패턴
REGEX_PATTERNS = {
    "date": r"\b(\d{1,2}[-/]\d{1,2}[-/]\d{2,4}|\d{4}[-/]\d{1,2}[-/]\d{1,2}|\d{2}\s+\w+\s+\d{4})\b",
    "bl_no": r"\b([A-Z]{2,6}\d{6,12})\b",
    "weight_kg": r"(\d+[\.,]?\d*)\s*(?:KGS?|KG|KILOGRAMS?)",
    "weight_mt": r"(\d+[\.,]?\d*)\s*(?:MT|M\.T\.|METRIC\s+TONS?)",
    "measurement_cbm": r"(\d+[\.,]?\d*)\s*(?:CBM|M3|CU\.?\s*M)",
    "port_code": r"\b([A-Z]{2}[A-Z]{3})\b",   # IATA/UN 항구 코드
    "amount": r"\$[\d,]+\.?\d*",
}
