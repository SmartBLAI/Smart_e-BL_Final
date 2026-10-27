"""
병렬 평가 청크 결과 병합 스크립트

사용법:
  python3.13 merge_eval_chunks.py

4개 청크(chunk_0~chunk_3)의 eval_report.json을 읽어
하나의 통합 PDF + JSON 리포트를 reports_eval_2000/ 에 생성합니다.
"""

import json
import os
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

from src.evaluator import AccuracyReport, SampleResult, FieldResult, TextMatchResult
from src.report_generator import ReportGenerator


CHUNK_DIR = os.path.join(BASE_DIR, "reports_eval_2000")
OUTPUT_DIR = CHUNK_DIR
CHUNK_NAMES = ["chunk_0", "chunk_1", "chunk_2", "chunk_3"]


def load_chunk_json(chunk_name: str) -> dict:
    path = os.path.join(CHUNK_DIR, chunk_name, "eval_report.json")
    if not os.path.exists(path):
        print(f"  [경고] {path} 없음 — 아직 완료되지 않았거나 실패한 청크입니다")
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def rebuild_report(data: dict) -> AccuracyReport:
    """eval_to_json JSON dict → AccuracyReport 재구성"""
    report = AccuracyReport()
    for s in data.get("samples", []):
        sample = SampleResult(
            lc_id=s["image_id"],
            bl_file=s.get("label_file", ""),
        )
        # 필드별 결과 복원 (fields는 리스트, 각 항목의 키는 "field")
        for fd in s.get("fields", []):
            fr = FieldResult(
                field_name=fd["field"],
                expected=fd.get("expected"),
                extracted=fd.get("extracted"),
                matched=fd.get("matched", False),
                match_type=fd.get("match_type", "none"),
            )
            sample.fields.append(fr)
        # 텍스트 지표 복원
        tm = s.get("text_metrics")
        if tm:
            sample.text_metrics = TextMatchResult(
                label_word_count=tm.get("label_word_count", 0),
                ocr_word_count=tm.get("ocr_word_count", 0),
                matched_word_count=tm.get("matched_word_count", 0),
                precision=tm.get("precision", 0.0),
                recall=tm.get("recall", 0.0),
                f1=tm.get("f1", 0.0),
            )
        report.samples.append(sample)
    return report


def main():
    print("=" * 60)
    print("  병렬 평가 청크 병합")
    print("=" * 60)

    merged = AccuracyReport()
    loaded = 0

    for chunk_name in CHUNK_NAMES:
        data = load_chunk_json(chunk_name)
        if data is None:
            continue
        partial = rebuild_report(data)
        merged.samples.extend(partial.samples)
        print(f"  {chunk_name}: {len(partial.samples)}건 로드")
        loaded += 1

    if not merged.samples:
        print("\n  오류: 로드할 수 있는 청크 결과가 없습니다.")
        sys.exit(1)

    print(f"\n  총 샘플: {len(merged.samples)}건 ({loaded}/{len(CHUNK_NAMES)} 청크 병합)")
    print(f"  필드 전체 정확도: {merged.overall_accuracy:.1%}")
    f1 = merged.overall_text_f1
    if f1 is not None:
        print(f"  텍스트 F1 평균 : {f1:.1%}")

    reporter = ReportGenerator()

    # JSON 저장
    json_out = os.path.join(OUTPUT_DIR, "eval_report_merged.json")
    reporter.eval_to_json(merged, json_out)
    print(f"\n  JSON 저장 완료: {json_out}")

    # PDF 저장
    pdf_out = os.path.join(OUTPUT_DIR, "eval_report_merged.pdf")
    try:
        reporter.eval_to_pdf(merged, pdf_out)
        print(f"  PDF 저장 완료 : {pdf_out}")
    except Exception as e:
        print(f"  PDF 생성 실패 : {e}")

    print("\n" + "=" * 60)
    print(f"  병합 완료! 총 {len(merged.samples)}건 평가 결과")
    print("=" * 60)


if __name__ == "__main__":
    main()
