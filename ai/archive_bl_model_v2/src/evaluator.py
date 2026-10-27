"""
B/L 필드 추출 정확도 평가 모듈
- ground_truth.json 기반 필드별 정확도 측정 (Evaluator)
- 이미지 OCR vs 라벨링 JSON 정확도 측정 (ImageVsLabelEvaluator)
- 날짜 정규화, 항구명 동의어, 회사명 토큰 겹침 등 퍼지 매칭 지원
"""

from __future__ import annotations

import json
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .ocr_extractor import OCRExtractor
from .field_parser import BLFields, FieldParser


# ── 항구명 동의어 테이블 ───────────────────────────────────────────
PORT_SYNONYMS: List[frozenset] = [
    frozenset(["BUSAN", "PUSAN"]),
    frozenset(["GUANGZHOU", "CANTON"]),
    frozenset(["MUMBAI", "BOMBAY"]),
    frozenset(["CHENNAI", "MADRAS"]),
    frozenset(["KOLKATA", "CALCUTTA"]),
    frozenset(["BEIJING", "PEKING"]),
    frozenset(["TROMSOE", "TROMSO"]),
]

# 날짜 파싱: 여러 형식 → (year, month, day) 정규화
_MONTHS = {
    "JAN": 1, "FEB": 2, "MAR": 3, "APR": 4, "MAY": 5, "JUN": 6,
    "JUL": 7, "AUG": 8, "SEP": 9, "OCT": 10, "NOV": 11, "DEC": 12,
}


def _parse_date(s: str) -> Optional[Tuple[int, int, int]]:
    """날짜 문자열 → (year, month, day). 파싱 실패 시 None."""
    s = s.strip().upper()

    # ISO: 2014-09-15
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        return int(m.group(1)), int(m.group(2)), int(m.group(3))

    # US MM-DD-YYYY or MM/DD/YYYY: 09-11-2015 / 12-15-2010
    m = re.match(r"^(\d{2})[-/](\d{2})[-/](\d{4})$", s)
    if m:
        return int(m.group(3)), int(m.group(1)), int(m.group(2))

    # DD MON YYYY: 16 AUG 2009  /  01-06-2018 handled above
    m = re.match(r"^(\d{1,2})\s+([A-Z]{3})\s+(\d{4})$", s)
    if m:
        mon = _MONTHS.get(m.group(2))
        if mon:
            return int(m.group(3)), mon, int(m.group(1))

    # MON DD, YYYY or MON DD. YYYY: SEP 06, 2006 / APR 05. 2009
    m = re.match(r"^([A-Z]{3})\s+(\d{1,2})[,.]?\s+(\d{4})$", s)
    if m:
        mon = _MONTHS.get(m.group(1))
        if mon:
            return int(m.group(3)), mon, int(m.group(2))

    # DD-MON-YYYY: 16-AUG-2009 / 05-AUG-2016
    m = re.match(r"^(\d{1,2})-([A-Z]{3})-(\d{4})$", s)
    if m:
        mon = _MONTHS.get(m.group(2))
        if mon:
            return int(m.group(3)), mon, int(m.group(1))

    # MON-DD-YYYY: JAN-30-2003
    m = re.match(r"^([A-Z]{3})-(\d{1,2})-(\d{4})$", s)
    if m:
        mon = _MONTHS.get(m.group(1))
        if mon:
            return int(m.group(3)), mon, int(m.group(2))

    return None


def _normalize_port(name: str) -> str:
    """항구명 정규화: 알파벳 단어 토큰만 추출 후 공백으로 결합.

    콤마 뒤 공백 유무에 따른 차이를 흡수합니다.
    예) 'BOWDEN, JAMAICA' → 'BOWDEN JAMAICA'
        'BOWDEN,JAMAICA'  → 'BOWDEN JAMAICA'  (기존에는 'BOWDENJAM AICA'로 연결되던 버그 수정)
    """
    tokens = re.findall(r"[A-Z]+", name.upper())
    return " ".join(tokens)


def _ports_match(a: str, b: str) -> bool:
    """항구명 매칭: 정규화 동일 또는 동의어"""
    a_norm = _normalize_port(a)
    b_norm = _normalize_port(b)
    if a_norm == b_norm:
        return True
    # 첫 번째 단어(도시명)만 비교
    a_tokens = a_norm.split()
    b_tokens = b_norm.split()
    a_city = a_tokens[0] if a_tokens else ""
    b_city = b_tokens[0] if b_tokens else ""
    if a_city and b_city and a_city == b_city:
        return True
    # 동의어 테이블
    for syn_set in PORT_SYNONYMS:
        if a_city in syn_set and b_city in syn_set:
            return True
    return False


def _company_match(a: str, b: str, threshold: float = 0.6) -> bool:
    """회사명 토큰 겹침 비율로 매칭"""
    def tokens(s: str) -> set:
        return {t for t in re.split(r"[\s,\.\-]+", s.upper()) if len(t) > 1}

    t_a, t_b = tokens(a), tokens(b)
    if not t_a or not t_b:
        return False
    overlap = len(t_a & t_b)
    return overlap / min(len(t_a), len(t_b)) >= threshold


def _weight_match(a: str, b: str, tolerance: float = 0.05) -> bool:
    """중량 수치 비교 (5% 허용)"""
    def extract_num(s: str) -> Optional[float]:
        m = re.search(r"[\d,]+\.?\d*", s.replace(",", ""))
        return float(m.group()) if m else None

    va, vb = extract_num(a), extract_num(b)
    if va is None or vb is None:
        return False
    if max(va, vb) == 0:
        return True
    return abs(va - vb) / max(va, vb) <= tolerance


@dataclass
class FieldResult:
    field_name: str
    expected: Optional[str]
    extracted: Optional[str]
    matched: bool
    match_type: str  # "exact" | "fuzzy" | "none" | "skip"


@dataclass
class TextMatchResult:
    """단어 수준 텍스트 일치 지표"""
    label_word_count: int
    ocr_word_count: int
    matched_word_count: int
    precision: float   # OCR 단어 중 라벨에 있는 비율
    recall: float      # 라벨 단어 중 OCR에서 찾은 비율
    f1: float          # F1 스코어


@dataclass
class SampleResult:
    lc_id: str
    bl_file: str
    fields: List[FieldResult] = field(default_factory=list)
    text_metrics: Optional[TextMatchResult] = None  # 이미지-라벨 비교 시 텍스트 지표

    @property
    def total(self) -> int:
        return sum(1 for f in self.fields if f.match_type != "skip")

    @property
    def matched(self) -> int:
        return sum(1 for f in self.fields if f.matched)

    @property
    def accuracy(self) -> float:
        return self.matched / self.total if self.total else 0.0


@dataclass
class AccuracyReport:
    samples: List[SampleResult] = field(default_factory=list)

    @property
    def overall_accuracy(self) -> float:
        total = sum(s.total for s in self.samples)
        matched = sum(s.matched for s in self.samples)
        return matched / total if total else 0.0

    @property
    def overall_text_f1(self) -> Optional[float]:
        """텍스트 수준 평균 F1 (ImageVsLabelEvaluator 사용 시)"""
        scores = [s.text_metrics.f1 for s in self.samples if s.text_metrics]
        return sum(scores) / len(scores) if scores else None

    def field_accuracy(self, field_name: str) -> float:
        results = [
            fr for s in self.samples
            for fr in s.fields
            if fr.field_name == field_name and fr.match_type != "skip"
        ]
        if not results:
            return 0.0
        return sum(1 for r in results if r.matched) / len(results)

    def print_report(self) -> None:
        fields = ["bl_no", "shipper", "consignee", "port_of_loading",
                  "port_of_discharge", "date_of_issue", "gross_weight"]
        print("=" * 60)
        print(f"B/L 필드 추출 정확도 보고서")
        print("=" * 60)
        print(f"\n{'필드':<25} {'정확도':>8}  {'bar'}")
        print("-" * 60)
        for fn in fields:
            acc = self.field_accuracy(fn)
            bar = "#" * int(acc * 20)
            print(f"  {fn:<23} {acc:>7.1%}  {bar}")
        print("-" * 60)
        print(f"  {'전체 평균':<23} {self.overall_accuracy:>7.1%}")
        f1 = self.overall_text_f1
        if f1 is not None:
            print(f"  {'텍스트 F1 평균':<23} {f1:>7.1%}")
        print()
        print("샘플별 상세:")
        for s in self.samples:
            status = "✅" if s.accuracy == 1.0 else ("⚠️" if s.accuracy >= 0.7 else "❌")
            tm = s.text_metrics
            tm_str = f"  텍스트F1={tm.f1:.1%}" if tm else ""
            print(f"  {status} {s.lc_id}  {s.matched}/{s.total}  ({s.accuracy:.1%}){tm_str}")
            for fr in s.fields:
                if not fr.matched and fr.match_type != "skip":
                    print(f"       ✗ {fr.field_name}: expected={fr.expected!r}  got={fr.extracted!r}")


class Evaluator:
    """
    ground_truth.json 기반 필드 추출 정확도 평가기.

    사용법::
        ev = Evaluator()
        report = ev.evaluate_batch(label_dir, "ground_truth.json")
        report.print_report()
    """

    EVAL_FIELDS = [
        "bl_no", "shipper", "consignee",
        "port_of_loading", "port_of_discharge",
        "date_of_issue", "gross_weight",
    ]

    def __init__(self) -> None:
        self._extractor = OCRExtractor()
        self._parser = FieldParser()

    def evaluate_batch(
        self,
        label_dir: str,
        ground_truth_path: str = "ground_truth.json",
    ) -> AccuracyReport:
        """ground_truth.json의 모든 샘플에 대해 정확도 측정"""
        with open(ground_truth_path, encoding="utf-8") as f:
            gt_data = json.load(f)

        report = AccuracyReport()
        for sample_gt in gt_data["samples"]:
            bl_path = os.path.join(label_dir, sample_gt["bl_file"])
            if not os.path.exists(bl_path):
                print(f"[WARN] {bl_path} 없음, 스킵")
                continue

            ocr = self._extractor.from_json(bl_path)
            bl = self._parser.parse(ocr)

            result = self._evaluate_sample(sample_gt, bl)
            report.samples.append(result)

        return report

    def _evaluate_sample(
        self, gt: dict, bl: BLFields
    ) -> SampleResult:
        sample_result = SampleResult(
            lc_id=gt.get("lc_id", "?"),
            bl_file=gt.get("bl_file", "?"),
        )
        for fn in self.EVAL_FIELDS:
            expected = gt.get(fn)
            extracted = getattr(bl, fn, None)

            if expected is None:
                fr = FieldResult(fn, None, extracted, True, "skip")
            else:
                matched, match_type = self._compare_field(fn, expected, extracted)
                fr = FieldResult(fn, expected, extracted, matched, match_type)

            sample_result.fields.append(fr)

        return sample_result

    def _compare_field(
        self,
        field_name: str,
        expected: str,
        extracted: Optional[str],
    ) -> Tuple[bool, str]:
        if extracted is None:
            return False, "none"

        # B/L No.: 정확 일치
        if field_name == "bl_no":
            ok = expected.strip().upper() == extracted.strip().upper()
            return ok, "exact" if ok else "none"

        # 날짜: datetime 파싱 후 비교
        if field_name == "date_of_issue":
            d_exp = _parse_date(expected)
            d_ext = _parse_date(extracted)
            if d_exp and d_ext:
                ok = d_exp == d_ext
                return ok, "exact" if ok else "none"
            # 파싱 실패 시 문자열 비교
            ok = expected.strip().upper() == extracted.strip().upper()
            return ok, "exact" if ok else "none"

        # 항구명
        if field_name in ("port_of_loading", "port_of_discharge"):
            ok = _ports_match(expected, extracted)
            return ok, "fuzzy" if ok else "none"

        # 중량
        if field_name == "gross_weight":
            ok = _weight_match(expected, extracted)
            return ok, "fuzzy" if ok else "none"

        # 회사명 (shipper, consignee)
        if field_name in ("shipper", "consignee"):
            ok = _company_match(expected, extracted)
            return ok, "fuzzy" if ok else "none"

        # 기타: 대소문자 무시 포함 검사
        exp_norm = expected.strip().upper()
        ext_norm = extracted.strip().upper()
        if exp_norm == ext_norm:
            return True, "exact"
        if exp_norm in ext_norm or ext_norm in exp_norm:
            return True, "fuzzy"
        return False, "none"


# ── 텍스트 수준 비교 유틸 ─────────────────────────────────────────

def _text_to_words(ocr_bboxes) -> List[str]:
    """OCRResult.bboxes → 정규화된 단어 리스트"""
    words = []
    for b in ocr_bboxes:
        for w in re.split(r"\s+", b.text.upper()):
            w = re.sub(r"[^A-Z0-9]", "", w)
            if w:
                words.append(w)
    return words


def _text_match_metrics(label_words: List[str], ocr_words: List[str]) -> TextMatchResult:
    """라벨 단어 리스트와 OCR 단어 리스트 사이의 F1 지표 계산"""
    label_set = set(label_words)
    ocr_set = set(ocr_words)
    matched = len(label_set & ocr_set)
    precision = matched / len(ocr_set) if ocr_set else 0.0
    recall = matched / len(label_set) if label_set else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0
    return TextMatchResult(
        label_word_count=len(label_set),
        ocr_word_count=len(ocr_set),
        matched_word_count=matched,
        precision=precision,
        recall=recall,
        f1=f1,
    )


class ImageVsLabelEvaluator:
    """
    이미지 OCR vs 라벨링 JSON 정확도 평가기.

    이미지에서 PaddleOCR로 텍스트를 추출한 후,
    라벨링 JSON(ground truth)과 비교하여 필드 추출 정확도와
    텍스트 수준 일치율(F1)을 측정합니다.

    사용법::
        ev = ImageVsLabelEvaluator(use_gpu=False)
        report = ev.evaluate_batch(image_dir, label_dir, max_files=10)
        report.print_report()
    """

    EVAL_FIELDS = [
        "bl_no", "shipper", "consignee",
        "port_of_loading", "port_of_discharge",
        "date_of_issue", "gross_weight",
    ]

    def __init__(self, use_gpu: bool = False) -> None:
        self._extractor = OCRExtractor(use_gpu=use_gpu)
        self._parser = FieldParser()

    # ── 공개 메서드 ──────────────────────────────────────────────

    def evaluate_single(
        self,
        image_path: str,
        label_path: str,
    ) -> SampleResult:
        """
        단일 이미지-라벨 쌍 평가.

        Parameters
        ----------
        image_path : 이미지 파일 경로 (.png/.jpg)
        label_path : 라벨링 JSON 파일 경로

        Returns
        -------
        SampleResult  (필드별 비교 + text_metrics)
        """
        # Ground truth: 라벨링 JSON → OCRResult → BLFields
        label_ocr = self._extractor.from_json(label_path)
        label_fields = self._parser.parse(label_ocr)

        # Predicted: 이미지 PaddleOCR → OCRResult → BLFields
        image_ocr = self._extractor.from_image(image_path)
        image_fields = self._parser.parse(image_ocr)

        # 텍스트 수준 지표 (단어 집합 F1)
        label_words = _text_to_words(label_ocr.bboxes)
        ocr_words = _text_to_words(image_ocr.bboxes)
        text_metrics = _text_match_metrics(label_words, ocr_words)

        # 필드 수준 비교
        result = SampleResult(
            lc_id=label_ocr.image_id,
            bl_file=os.path.basename(label_path),
            text_metrics=text_metrics,
        )
        for fn in self.EVAL_FIELDS:
            expected = getattr(label_fields, fn, None)
            extracted = getattr(image_fields, fn, None)

            if expected is None:
                fr = FieldResult(fn, None, extracted, True, "skip")
            else:
                matched, match_type = self._compare_field(fn, expected, extracted)
                fr = FieldResult(fn, expected, extracted, matched, match_type)

            result.fields.append(fr)

        return result

    def evaluate_batch(
        self,
        image_dir: str,
        label_dir: str,
        max_files: int = 0,
        file_offset: int = 0,
    ) -> AccuracyReport:
        """
        디렉토리 단위 배치 평가.
        라벨 JSON 파일명과 동일한 stem의 .png 이미지를 찾아 매핑합니다.

        Parameters
        ----------
        file_offset : 시작 파일 인덱스 (병렬 분할 시 사용)
        """
        label_files = sorted(Path(label_dir).glob("*.json"))
        if file_offset > 0:
            label_files = label_files[file_offset:]
        if max_files > 0:
            label_files = label_files[:max_files]

        report = AccuracyReport()
        for i, label_file in enumerate(label_files, 1):
            # 이미지 파일 탐색 (.png 우선, 없으면 .jpg)
            img_path = Path(image_dir) / (label_file.stem + ".png")
            if not img_path.exists():
                img_path = Path(image_dir) / (label_file.stem + ".jpg")
            if not img_path.exists():
                print(f"  [{i}] 이미지 없음, 스킵: {label_file.stem}")
                continue

            print(f"  [{i}/{len(label_files)}] {label_file.name} 평가 중...")
            try:
                sample = self.evaluate_single(str(img_path), str(label_file))
                tm = sample.text_metrics
                tm_str = f"  텍스트F1={tm.f1:.1%}" if tm else ""
                status = "✅" if sample.accuracy == 1.0 else ("⚠️" if sample.accuracy >= 0.7 else "❌")
                print(f"    {status} 필드정확도={sample.accuracy:.1%}{tm_str}")
                report.samples.append(sample)
            except Exception as e:
                print(f"    ❌ 평가 실패: {e}")

        return report

    # ── 내부 ─────────────────────────────────────────────────────

    def _compare_field(
        self,
        field_name: str,
        expected: str,
        extracted: Optional[str],
    ) -> Tuple[bool, str]:
        """Evaluator와 동일한 퍼지 매칭 로직"""
        if extracted is None:
            return False, "none"

        if field_name == "bl_no":
            ok = expected.strip().upper() == extracted.strip().upper()
            return ok, "exact" if ok else "none"

        if field_name == "date_of_issue":
            d_exp = _parse_date(expected)
            d_ext = _parse_date(extracted)
            if d_exp and d_ext:
                ok = d_exp == d_ext
                return ok, "exact" if ok else "none"
            ok = expected.strip().upper() == extracted.strip().upper()
            return ok, "exact" if ok else "none"

        if field_name in ("port_of_loading", "port_of_discharge"):
            ok = _ports_match(expected, extracted)
            return ok, "fuzzy" if ok else "none"

        if field_name == "gross_weight":
            ok = _weight_match(expected, extracted)
            return ok, "fuzzy" if ok else "none"

        if field_name in ("shipper", "consignee"):
            ok = _company_match(expected, extracted)
            return ok, "fuzzy" if ok else "none"

        exp_norm = expected.strip().upper()
        ext_norm = extracted.strip().upper()
        if exp_norm == ext_norm:
            return True, "exact"
        if exp_norm in ext_norm or ext_norm in exp_norm:
            return True, "fuzzy"
        return False, "none"
