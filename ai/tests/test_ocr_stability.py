"""OCR 락·워밍업 배선 — PaddleOCR 없이 엔진 팩토리를 가짜로 바꿔 검증한다."""
import sys
import threading
import time
import types

from api import main
from f1_intake.extractor import OCRExtractor


def _fake_paddle(monkeypatch, built):
    class FakeOCR:
        def __init__(self, **_):
            built.append(1)
            time.sleep(0.05)

        def predict(self, _):
            return []

    monkeypatch.setitem(sys.modules, "paddleocr", types.SimpleNamespace(PaddleOCR=FakeOCR))


def test_engine_built_once_under_concurrent_calls(monkeypatch):
    built = []
    _fake_paddle(monkeypatch, built)
    ext = OCRExtractor()
    ts = [threading.Thread(target=ext._get_ocr) for _ in range(8)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(built) == 1


def test_warm_up_builds_and_predicts(monkeypatch):
    built = []
    _fake_paddle(monkeypatch, built)
    OCRExtractor().warm_up()
    assert built == [1]


def test_warm_up_failure_is_not_fatal(monkeypatch):
    def boom():
        raise ImportError("no paddle")

    monkeypatch.setattr(main, "intake_pipeline", boom)
    main.warm_up_ocr()  # 예외 없이 반환
