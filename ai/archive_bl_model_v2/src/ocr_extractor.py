"""
OCR 텍스트 추출 모듈
- 기존 JSON 라벨 파일 로드 (샘플 데이터)
- PaddleOCR 직접 추출 (실제 이미지 입력 시)
"""

import json
import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional, Tuple


@dataclass
class BBox:
    """단일 OCR 바운딩 박스"""
    text: str
    x_min: int
    y_min: int
    x_max: int
    y_max: int
    center_x: float = field(init=False)
    center_y: float = field(init=False)

    def __post_init__(self):
        self.center_x = (self.x_min + self.x_max) / 2
        self.center_y = (self.y_min + self.y_max) / 2

    @property
    def width(self) -> int:
        return self.x_max - self.x_min

    @property
    def height(self) -> int:
        return self.y_max - self.y_min


@dataclass
class OCRResult:
    """OCR 추출 결과 (전체 문서)"""
    image_id: str
    image_width: int
    image_height: int
    form_type: str
    bboxes: List[BBox]
    source: str  # "json" | "paddleocr"


class OCRExtractor:
    """OCR 추출기 - JSON 로드 또는 PaddleOCR 실행"""

    def __init__(self, use_gpu: bool = False):
        self._ocr = None  # PaddleOCR lazy 초기화
        self._use_gpu = use_gpu

    # ─── 공개 메서드 ──────────────────────────────────────────

    def from_json(self, json_path: str) -> OCRResult:
        """샘플 데이터 JSON 파일에서 OCR 결과 로드"""
        with open(json_path, "r", encoding="utf-8") as f:
            data = json.load(f)

        images_meta = data.get("Images", {})
        bboxes = self._parse_bbox_list(data.get("bbox", []))

        return OCRResult(
            image_id=images_meta.get("identifier", Path(json_path).stem),
            image_width=images_meta.get("width", 1654),
            image_height=images_meta.get("height", 2340),
            form_type=images_meta.get("form_type", "선하증권"),
            bboxes=bboxes,
            source="json",
        )

    def from_image(self, image_path: str) -> OCRResult:
        """이미지 파일에서 PaddleOCR로 직접 추출"""
        ocr = self._get_ocr()
        result = ocr.ocr(str(image_path))

        bboxes: List[BBox] = []
        if result and result[0]:
            item = result[0]
            # PaddleOCR 3.x: dict-like OCRResult with rec_texts / dt_polys
            if hasattr(item, "get"):
                rec_texts = item.get("rec_texts", [])
                dt_polys = item.get("dt_polys", [])
                for text, poly in zip(rec_texts, dt_polys):
                    pts = list(poly)
                    xs = [int(p[0]) for p in pts]
                    ys = [int(p[1]) for p in pts]
                    if text and text.strip():
                        bboxes.append(BBox(
                            text=text.strip(),
                            x_min=min(xs), y_min=min(ys),
                            x_max=max(xs), y_max=max(ys),
                        ))
            else:
                # PaddleOCR 2.x 호환: [(coords, (text, conf)), ...]
                for line in item:
                    coords, (text, _conf) = line
                    xs = [int(p[0]) for p in coords]
                    ys = [int(p[1]) for p in coords]
                    bboxes.append(BBox(
                        text=text,
                        x_min=min(xs), y_min=min(ys),
                        x_max=max(xs), y_max=max(ys),
                    ))

        import cv2
        img = cv2.imread(str(image_path))
        h, w = img.shape[:2] if img is not None else (2340, 1654)

        return OCRResult(
            image_id=Path(image_path).stem,
            image_width=w,
            image_height=h,
            form_type="선하증권",
            bboxes=bboxes,
            source="paddleocr",
        )

    def load_dataset(self, label_dir: str) -> List[OCRResult]:
        """라벨 디렉토리 전체 JSON 파일 일괄 로드"""
        results = []
        for json_file in sorted(Path(label_dir).glob("*.json")):
            try:
                results.append(self.from_json(str(json_file)))
            except Exception as e:
                print(f"[경고] {json_file.name} 로드 실패: {e}")
        return results

    # ─── 내부 메서드 ──────────────────────────────────────────

    def _parse_bbox_list(self, raw: list) -> List[BBox]:
        bboxes = []
        for item in raw:
            text = item.get("data", "").strip()
            xs = item.get("x", [])
            ys = item.get("y", [])
            if not text or len(xs) < 2 or len(ys) < 2:
                continue
            bboxes.append(BBox(
                text=text,
                x_min=min(xs), y_min=min(ys),
                x_max=max(xs), y_max=max(ys),
            ))
        return bboxes

    def _get_ocr(self):
        if self._ocr is None:
            try:
                from paddleocr import PaddleOCR
                self._ocr = PaddleOCR(
                    lang="en",
                    use_doc_orientation_classify=False,
                    use_doc_unwarping=False,
                )
            except ImportError:
                raise ImportError(
                    "PaddleOCR가 설치되어 있지 않습니다.\n"
                    "설치: pip install paddlepaddle paddleocr"
                )
        return self._ocr
