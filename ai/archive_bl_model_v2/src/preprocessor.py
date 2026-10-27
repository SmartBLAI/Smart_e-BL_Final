"""
이미지 전처리 모듈 (OpenCV 기반)
- 그레이스케일 변환
- 노이즈 제거
- 이진화 (Adaptive Thresholding)
- 기울기 보정 (Deskewing)
- 해상도 정규화
"""

import numpy as np
from pathlib import Path
from typing import Optional

try:
    import cv2
    CV2_AVAILABLE = True
except ImportError:
    CV2_AVAILABLE = False


class ImagePreprocessor:
    """B/L 스캔 이미지 전처리기"""

    def __init__(self, target_dpi: int = 300):
        if not CV2_AVAILABLE:
            raise ImportError("opencv-python 패키지가 필요합니다: pip install opencv-python")
        self.target_dpi = target_dpi

    def process(self, image_path: str) -> np.ndarray:
        """전체 전처리 파이프라인 실행"""
        img = self._load(image_path)
        img = self._to_grayscale(img)
        img = self._remove_noise(img)
        img = self._binarize(img)
        img = self._deskew(img)
        img = self._normalize_resolution(img)
        return img

    # ─── 개별 단계 ──────────────────────────────────────────

    def _load(self, path: str) -> np.ndarray:
        img = cv2.imread(str(path))
        if img is None:
            raise FileNotFoundError(f"이미지를 로드할 수 없습니다: {path}")
        return img

    def _to_grayscale(self, img: np.ndarray) -> np.ndarray:
        if len(img.shape) == 3:
            return cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        return img

    def _remove_noise(self, img: np.ndarray) -> np.ndarray:
        """Gaussian + Median 블러로 노이즈 제거"""
        img = cv2.GaussianBlur(img, (3, 3), 0)
        img = cv2.medianBlur(img, 3)
        return img

    def _binarize(self, img: np.ndarray) -> np.ndarray:
        """Adaptive Thresholding으로 이진화"""
        return cv2.adaptiveThreshold(
            img, 255,
            cv2.ADAPTIVE_THRESH_GAUSSIAN_C,
            cv2.THRESH_BINARY,
            blockSize=11,
            C=2,
        )

    def _deskew(self, img: np.ndarray) -> np.ndarray:
        """Hough 변환 기반 기울기 감지 및 보정"""
        angle = self._detect_skew_angle(img)
        if abs(angle) < 0.5:          # 0.5도 미만이면 보정 불필요
            return img
        h, w = img.shape[:2]
        center = (w // 2, h // 2)
        M = cv2.getRotationMatrix2D(center, angle, 1.0)
        rotated = cv2.warpAffine(
            img, M, (w, h),
            flags=cv2.INTER_CUBIC,
            borderMode=cv2.BORDER_REPLICATE,
        )
        return rotated

    def _detect_skew_angle(self, img: np.ndarray) -> float:
        """이미지에서 텍스트 기울기 각도 추정"""
        edges = cv2.Canny(img, 50, 150, apertureSize=3)
        lines = cv2.HoughLinesP(
            edges, 1, np.pi / 180,
            threshold=100, minLineLength=100, maxLineGap=10,
        )
        if lines is None:
            return 0.0
        angles = []
        for line in lines:
            x1, y1, x2, y2 = line[0]
            if x2 != x1:
                angle = np.degrees(np.arctan2(y2 - y1, x2 - x1))
                if abs(angle) < 45:    # 수평 라인만 고려
                    angles.append(angle)
        return float(np.median(angles)) if angles else 0.0

    def _normalize_resolution(self, img: np.ndarray) -> np.ndarray:
        """이미지 최소 해상도 보정 (너비 기준 1654px 표준)"""
        h, w = img.shape[:2]
        target_w = 1654
        if w < target_w:
            scale = target_w / w
            img = cv2.resize(img, None, fx=scale, fy=scale, interpolation=cv2.INTER_CUBIC)
        return img

    def save(self, img: np.ndarray, output_path: str) -> None:
        """전처리된 이미지 저장"""
        cv2.imwrite(str(output_path), img)
