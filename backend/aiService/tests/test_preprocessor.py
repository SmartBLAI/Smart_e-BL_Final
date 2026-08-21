"""ocr/preprocessor.py — 화이트박스 (분기 커버리지).

설계표는 docs/ai-service/whitebox-test-plan.md 참고.
"""

from __future__ import annotations

import pytest

cv2 = pytest.importorskip("cv2", reason="opencv-python 미설치 시 건너뜀")
import numpy as np  # noqa: E402

from ocr.preprocessor import STANDARD_WIDTH, ImagePreprocessor  # noqa: E402


@pytest.fixture
def pre() -> ImagePreprocessor:
    return ImagePreprocessor()


def _blank_bgr(w: int = 400, h: int = 300) -> np.ndarray:
    return np.full((h, w, 3), 255, dtype=np.uint8)


def _skewed_lines_gray(w: int = 400, h: int = 300) -> np.ndarray:
    """뚜렷한 대각선 여러 개 — Hough 가 유의미한 각도를 잡도록."""
    img = np.zeros((h, w), dtype=np.uint8)
    for y0 in range(40, h - 20, 40):
        cv2.line(img, (20, y0 + 60), (w - 20, y0), 255, 3)
    return img


class TestLoad:
    def test_존재하지_않는_경로는_FileNotFoundError(self, pre, tmp_path):
        with pytest.raises(FileNotFoundError):
            pre._load(str(tmp_path / "no-such.png"))

    def test_존재하는_파일은_ndarray로_읽는다(self, pre, tmp_path):
        path = tmp_path / "a.png"
        cv2.imwrite(str(path), _blank_bgr())
        img = pre._load(str(path))
        assert img is not None
        assert img.shape[2] == 3


class TestGrayscale:
    def test_3채널은_그레이스케일로_변환된다(self, pre):
        img = pre._to_grayscale(_blank_bgr())
        assert img.ndim == 2

    def test_이미_그레이스케일이면_그대로_돌려준다(self, pre):
        gray = np.zeros((50, 50), dtype=np.uint8)
        out = pre._to_grayscale(gray)
        assert out is gray


class TestRemoveNoiseAndBinarize:
    def test_노이즈_제거는_형태를_보존한다(self, pre):
        gray = _skewed_lines_gray()
        out = pre._remove_noise(gray)
        assert out.shape == gray.shape

    def test_이진화_결과는_0과_255뿐이다(self, pre):
        gray = _skewed_lines_gray()
        out = pre._binarize(gray)
        assert set(np.unique(out)).issubset({0, 255})


class TestDeskew:
    def test_직선이_없으면_각도는_0이고_원본을_그대로_돌려준다(self, pre):
        blank = np.zeros((100, 100), dtype=np.uint8)
        angle = pre._detect_skew_angle(blank)
        assert angle == 0.0
        out = pre._deskew(blank)
        assert out is blank

    def test_기운_직선들이_있으면_0이_아닌_각도를_추정한다(self, pre):
        img = _skewed_lines_gray()
        angle = pre._detect_skew_angle(img)
        assert angle != 0.0

    def test_수직선과_45도_이상_급경사선은_걸러지고_완만한_선만_쓴다(self, pre):
        """수직선(x2==x1)은 continue 로, 급경사(|angle|>=45)는 필터로 빠진다."""
        img = np.zeros((200, 300), dtype=np.uint8)
        cv2.line(img, (150, 10), (150, 190), 255, 3)  # x2 == x1 → continue
        cv2.line(img, (140, 10), (170, 190), 255, 3)  # 급경사 → 필터
        cv2.line(img, (20, 150), (278, 58), 255, 3)  # 완만함 → 채택
        angle = pre._detect_skew_angle(img)
        assert -25 < angle < -10

    def test_임계각_미만이면_보정하지_않는다(self, pre, monkeypatch):
        gray = _skewed_lines_gray()
        monkeypatch.setattr(pre, "_detect_skew_angle", lambda img: 0.1)
        out = pre._deskew(gray)
        assert out is gray

    def test_임계각_이상이면_회전_보정한다(self, pre, monkeypatch):
        gray = _skewed_lines_gray()
        monkeypatch.setattr(pre, "_detect_skew_angle", lambda img: 5.0)
        out = pre._deskew(gray)
        assert out.shape == gray.shape
        assert not np.array_equal(out, gray)


class TestNormalizeResolution:
    def test_기준_너비_이상이면_그대로_둔다(self, pre):
        img = np.zeros((100, STANDARD_WIDTH), dtype=np.uint8)
        out = pre._normalize_resolution(img)
        assert out is img

    def test_기준_너비_미만이면_확대한다(self, pre):
        img = np.zeros((100, 200), dtype=np.uint8)
        out = pre._normalize_resolution(img)
        assert out.shape[1] == STANDARD_WIDTH


class TestProcessEndToEnd:
    def test_전체_파이프라인이_기준_해상도로_끝난다(self, pre, tmp_path):
        path = tmp_path / "scan.png"
        cv2.imwrite(str(path), _skewed_lines_gray(w=300, h=200))
        out = pre.process(str(path))
        assert out.shape[1] == STANDARD_WIDTH

    def test_save는_파일을_만든다(self, pre, tmp_path):
        out_path = tmp_path / "out.png"
        pre.save(_blank_bgr(), str(out_path))
        assert out_path.exists()
