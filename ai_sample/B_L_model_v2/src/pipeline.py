"""
B/L AI 하자 검증 통합 파이프라인
이미지 또는 JSON → OCR → 필드 추출 → Rule 검증 → [sLLM 보완] → 리포트
"""

import os
from pathlib import Path
from typing import Optional

from .field_parser import BLFields, FieldParser
from .ocr_extractor import OCRExtractor, OCRResult
from .report_generator import ReportGenerator
from .validator import BLValidator, LCConditions, ValidationResult


class BLVerificationPipeline:
    """B/L 하자 검증 전체 파이프라인"""

    def __init__(
        self,
        use_gpu: bool = False,
        use_llm: bool = False,
        llm_model: str = "llama3.2",
        llm_host: str = "http://localhost:11434",
        llm_timeout: int = 120,
    ):
        self.extractor = OCRExtractor(use_gpu=use_gpu)
        self.parser = FieldParser()
        self.validator = BLValidator()
        self.reporter = ReportGenerator()
        self.use_llm = use_llm
        self._judge = None

        if use_llm:
            from .sllm_judge import LlamaJudge
            self._judge = LlamaJudge(
                model=llm_model,
                host=llm_host,
                timeout=llm_timeout,
            )

    # ── 기본 실행 ────────────────────────────────────────────────

    def run_from_json(
        self,
        json_path: str,
        lc: Optional[LCConditions] = None,
        output_dir: Optional[str] = None,
    ) -> dict:
        """JSON 라벨 파일로 파이프라인 실행"""
        ocr = self.extractor.from_json(json_path)
        return self._run(ocr, lc, output_dir)

    def run_from_image(
        self,
        image_path: str,
        lc: Optional[LCConditions] = None,
        output_dir: Optional[str] = None,
        preprocess: bool = True,
    ) -> dict:
        """B/L 이미지 파일로 파이프라인 실행"""
        if preprocess:
            image_path = self._preprocess_image(image_path)
        ocr = self.extractor.from_image(image_path)
        return self._run(ocr, lc, output_dir)

    # ── 배치 처리 ────────────────────────────────────────────────

    def run_batch(
        self,
        label_dir: str,
        lc: Optional[LCConditions] = None,
        output_dir: Optional[str] = None,
        max_files: int = 0,
    ) -> list:
        """디렉토리 내 전체 JSON 파일 일괄 처리"""
        json_files = sorted(Path(label_dir).glob("*.json"))
        if max_files > 0:
            json_files = json_files[:max_files]

        results = []
        for i, json_file in enumerate(json_files, 1):
            llm_tag = " [+LLM]" if self.use_llm else ""
            print(f"[{i}/{len(json_files)}]{llm_tag} {json_file.name} 처리 중...")
            try:
                result = self.run_from_json(str(json_file), lc, output_dir)
                results.append(result)
            except Exception as e:
                print(f"  ⚠️  실패: {e}")
                results.append({"file": str(json_file), "error": str(e)})

        return results

    # ── 내부 ─────────────────────────────────────────────────────

    def _run(
        self,
        ocr: OCRResult,
        lc: Optional[LCConditions],
        output_dir: Optional[str],
    ) -> dict:
        if lc is None:
            lc = LCConditions()

        # 1. 필드 추출
        bl: BLFields = self.parser.parse(ocr)

        # 1-b. LLM fallback: 핵심 필드 누락 시 Llama로 보완
        if self.use_llm:
            missing = bl.missing_critical_fields()
            if missing:
                try:
                    from .sllm_judge import LlamaExtractor
                    _lx = LlamaExtractor(host=self._judge.host if self._judge else "http://localhost:11434")
                    if _lx.is_available():
                        ocr_text = "\n".join(b.text for b in ocr.bboxes)
                        filled = _lx.extract_missing_fields(ocr_text, missing)
                        for fn, val in filled.items():
                            if val and not getattr(bl, fn, None):
                                setattr(bl, fn, val)
                        if filled:
                            print(f"  → LLM 필드 보완: {list(filled.keys())}")
                except Exception:
                    pass

        # 2. Rule-based 검증
        rule_result: ValidationResult = self.validator.validate(bl, lc)

        # 3. sLLM 문맥 보완 (옵션)
        llm_data: Optional[dict] = None
        if self.use_llm and self._judge is not None:
            print("  → Llama 3 문맥 판단 중...", end=" ", flush=True)
            try:
                from .sllm_judge import merge_results
                judgment = self._judge.judge(bl, lc, rule_result)
                llm_data = merge_results(rule_result, judgment)

                # 병합 결과로 rule_result 교체 (리포트에 반영)
                from .validator import ValidationResult as VR
                merged = llm_data["merged_validation"]
                defects = []
                for d in merged["defects"]:
                    from .validator import Defect
                    defects.append(Defect(
                        code=d["code"], field=d["field"],
                        description=d["description"],
                        bl_value=d.get("bl_value"),
                        lc_value=d.get("lc_value"),
                        severity=d["severity"],
                    ))
                rule_result = VR(
                    is_valid=merged["is_valid"],
                    defects=[d for d in defects if d.severity == "ERROR"],
                    warnings=[d for d in defects if d.severity == "WARNING"],
                )
                print("완료")
            except RuntimeError as e:
                print(f"\n  ⚠️  LLM 판단 건너뜀: {e}")

        # 4. 리포트 생성
        report = self.reporter.to_json(bl, lc, rule_result, llm_data=llm_data)
        report["image_id"] = ocr.image_id

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            json_out = os.path.join(output_dir, f"{ocr.image_id}_report.json")
            self.reporter.to_json(bl, lc, rule_result, llm_data=llm_data, output_path=json_out)
            # PDF 리포트 자동 생성
            pdf_out = os.path.join(output_dir, f"{ocr.image_id}_report.pdf")
            try:
                self.reporter.to_pdf(bl, lc, rule_result, pdf_out, llm_data=llm_data)
                report["pdf_path"] = pdf_out
            except Exception as e:
                print(f"  [경고] PDF 생성 실패: {e}")

        return report

    # ── 이미지 OCR vs 라벨링 JSON 정확도 평가 ──────────────────

    def run_eval_single(
        self,
        image_path: str,
        label_path: str,
        output_dir: Optional[str] = None,
    ) -> dict:
        """
        단일 이미지-라벨 쌍 정확도 평가.

        이미지에서 PaddleOCR로 텍스트를 추출하고,
        라벨링 JSON과 비교하여 필드 추출 정확도 및
        텍스트 수준 일치율을 반환합니다.
        """
        from .evaluator import ImageVsLabelEvaluator

        ev = ImageVsLabelEvaluator(use_gpu=self.extractor._use_gpu)
        sample = ev.evaluate_single(image_path, label_path)

        result = {
            "image_id": sample.lc_id,
            "label_file": sample.bl_file,
            "field_accuracy": sample.accuracy,
            "field_matched": sample.matched,
            "field_total": sample.total,
            "text_metrics": None,
        }
        if sample.text_metrics:
            tm = sample.text_metrics
            result["text_metrics"] = {
                "precision": round(tm.precision, 4),
                "recall": round(tm.recall, 4),
                "f1": round(tm.f1, 4),
            }

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)
            from .evaluator import AccuracyReport
            single_report = AccuracyReport(samples=[sample])
            json_out = os.path.join(output_dir, f"{sample.lc_id}_eval.json")
            self.reporter.eval_to_json(single_report, json_out)
            result["json_path"] = json_out

            try:
                pdf_out = os.path.join(output_dir, f"{sample.lc_id}_eval.pdf")
                self.reporter.eval_to_pdf(single_report, pdf_out)
                result["pdf_path"] = pdf_out
            except Exception as e:
                print(f"  [경고] PDF 생성 실패: {e}")

        return result

    def run_eval_batch(
        self,
        image_dir: str,
        label_dir: str,
        output_dir: Optional[str] = None,
        max_files: int = 0,
        file_offset: int = 0,
    ) -> dict:
        """
        디렉토리 단위 배치 정확도 평가.

        label_dir의 JSON 파일마다 image_dir에서 동일 stem의 이미지를 찾아
        OCR vs 라벨링 비교를 수행합니다.
        """
        from .evaluator import ImageVsLabelEvaluator

        ev = ImageVsLabelEvaluator(use_gpu=self.extractor._use_gpu)
        report = ev.evaluate_batch(image_dir, label_dir, max_files=max_files, file_offset=file_offset)

        # 콘솔 출력
        print(self.reporter.eval_to_text(report))

        result = {
            "sample_count": len(report.samples),
            "overall_field_accuracy": report.overall_accuracy,
            "overall_text_f1": report.overall_text_f1,
        }

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

            json_out = os.path.join(output_dir, "eval_report.json")
            self.reporter.eval_to_json(report, json_out)
            result["json_path"] = json_out

            try:
                pdf_out = os.path.join(output_dir, "eval_report.pdf")
                self.reporter.eval_to_pdf(report, pdf_out)
                result["pdf_path"] = pdf_out
            except Exception as e:
                print(f"  [경고] PDF 생성 실패: {e}")

        return result

    def _preprocess_image(self, image_path: str) -> str:
        try:
            from .preprocessor import ImagePreprocessor
            pp = ImagePreprocessor()
            img = pp.process(image_path)
            out_path = image_path.replace(".png", "_preprocessed.png").replace(
                ".jpg", "_preprocessed.jpg"
            )
            pp.save(img, out_path)
            return out_path
        except ImportError:
            print("[경고] OpenCV 미설치 → 전처리 생략")
            return image_path
