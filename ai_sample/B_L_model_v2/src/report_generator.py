"""
하자 리포트 생성 모듈
- JSON 형식 리포트
- 텍스트(콘솔) 리포트
- PDF 리포트 (reportlab + AppleGothic/NotoSansGothic 한글 폰트)
- 정확도 리포트 (이미지 OCR vs 라벨링 JSON 비교 결과)
"""

import json
import os
from datetime import datetime
from typing import Optional

from .field_parser import BLFields
from .validator import LCConditions, ValidationResult


# ── 한글 폰트 경로 후보 (macOS / Linux) ─────────────────────────
_KOREAN_FONT_CANDIDATES = [
    "/System/Library/Fonts/Supplemental/AppleGothic.ttf",          # macOS
    "/System/Library/Fonts/Supplemental/NotoSansGothic-Regular.ttf",
    "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",             # Ubuntu
    "/usr/share/fonts/truetype/noto/NotoSansCJK-Regular.ttc",
]


def _find_korean_font() -> Optional[str]:
    for path in _KOREAN_FONT_CANDIDATES:
        if os.path.exists(path):
            return path
    return None


class ReportGenerator:
    """B/L 하자 검증 리포트 생성기"""

    # ── 공개 메서드 ──────────────────────────────────────────────

    def to_json(
        self,
        bl: BLFields,
        lc: LCConditions,
        result: ValidationResult,
        output_path: Optional[str] = None,
        llm_data: Optional[dict] = None,
    ) -> dict:
        """JSON 리포트 생성 및 선택적 파일 저장"""
        report = {
            "generated_at": datetime.now().isoformat(),
            "lc_no": lc.lc_no,
            "is_valid": result.is_valid,
            "pipeline": "Rule-based + Llama 3.2 sLLM" if llm_data else "Rule-based",
            "summary": {
                "defect_count": result.defect_count,
                "warning_count": result.warning_count,
                "verdict": "이상 없음" if result.is_valid else f"하자 {result.defect_count}건 발견",
            },
            "bl_fields": bl.to_dict(),
            "lc_conditions": {
                "lc_no": lc.lc_no,
                "expiry_date": lc.expiry_date,
                "latest_shipment_date": lc.latest_shipment_date,
                "port_of_loading": lc.port_of_loading,
                "port_of_discharge": lc.port_of_discharge,
                "consignee": lc.consignee,
                "description_of_goods": lc.description_of_goods,
                "max_gross_weight_kg": lc.max_gross_weight_kg,
                "max_measurement_cbm": lc.max_measurement_cbm,
            },
            "validation": result.to_dict(),
        }
        if llm_data:
            report["llm_analysis"] = llm_data.get("llm_judgment", {})
            report["llm_merge_stats"] = {
                "demoted_to_warning": llm_data.get("demoted_count", 0),
                "llm_added_issues": llm_data.get("llm_added_count", 0),
            }
        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(report, f, ensure_ascii=False, indent=2)
        return report

    def to_text(
        self,
        bl: BLFields,
        lc: LCConditions,
        result: ValidationResult,
        llm_data: Optional[dict] = None,
    ) -> str:
        """콘솔 출력용 텍스트 리포트 생성"""
        sep = "=" * 60
        pipeline_label = "Rule-based + Llama 3.2 sLLM" if llm_data else "Rule-based"
        lines = [
            sep,
            "  B/L 하자 검증 리포트",
            f"  생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  파이프라인: {pipeline_label}",
            sep,
            "",
            f"[검증 결과] {'✅ 이상 없음' if result.is_valid else '❌ 하자 발견'}",
            f"  하자(ERROR): {result.defect_count}건  |  경고(WARNING): {result.warning_count}건",
            "",
            "─" * 60,
            "▶ B/L 추출 필드",
            "─" * 60,
        ]

        fields = bl.to_dict()
        label_map = {
            "bl_no": "B/L No.",
            "shipper": "Shipper",
            "consignee": "Consignee",
            "notify_party": "Notify Party",
            "vessel": "Vessel",
            "voyage_no": "Voyage No.",
            "port_of_loading": "Port of Loading",
            "port_of_discharge": "Port of Discharge",
            "description_of_goods": "Description of Goods",
            "gross_weight": "Gross Weight",
            "measurement": "Measurement",
            "date_of_issue": "Date of Issue",
            "on_board_date": "On Board Date",
            "place_of_issue": "Place of Issue",
            "total_freight": "Total Freight",
        }
        for key, label in label_map.items():
            val = fields.get(key)
            display = (val[:70] + "...") if val and len(val) > 70 else (val or "─ 미추출")
            lines.append(f"  {label:<25}: {display}")

        if result.defects or result.warnings:
            lines += ["", "─" * 60, "▶ 하자·경고 목록", "─" * 60]
            for d in result.defects:
                lines.append(f"  ❌ [{d.code}] {d.field}")
                lines.append(f"      {d.description}")
                if d.bl_value:
                    lines.append(f"      B/L 값 : {d.bl_value[:80]}")
                if d.lc_value:
                    lines.append(f"      L/C 조건: {d.lc_value[:80]}")
                lines.append("")
            for w in result.warnings:
                lines.append(f"  ⚠️  [{w.code}] {w.field}")
                lines.append(f"      {w.description}")
                lines.append("")

        # LLM 판단 섹션
        if llm_data:
            llm = llm_data.get("llm_judgment", {})
            verdict = llm.get("overall_verdict", "UNCERTAIN")
            conf = llm.get("confidence", 0.0)
            summary = llm.get("contextual_summary", "")

            verdict_icon = {"COMPLIANT": "✅", "DISCREPANT": "❌", "UNCERTAIN": "❓"}.get(verdict, "❓")
            lines += [
                "",
                "─" * 60,
                "▶ Llama 3.2 문맥 판단",
                "─" * 60,
                f"  종합 판정 : {verdict_icon} {verdict}  (신뢰도 {conf:.0%})",
                f"  종합 의견 : {summary[:120] if summary else '─'}",
            ]

            reviews = llm.get("rule_reviews", [])
            if reviews:
                lines.append("")
                lines.append("  [Rule 재검토]")
                for r in reviews:
                    icon = "✅ 확인" if r.get("confirmed") else "↩️  오감지"
                    lines.append(f"    {r['code']} → {icon}  {r.get('reasoning', '')[:80]}")

            extra = llm.get("additional_findings", [])
            if extra:
                lines.append("")
                lines.append("  [LLM 추가 발견]")
                for f in extra:
                    sev = "❌" if f.get("severity") == "ERROR" else "⚠️ "
                    lines.append(f"    {sev} [{f['code']}] {f['field']}: {f['description'][:80]}")

            stats = llm_data.get("demoted_count", 0), llm_data.get("llm_added_count", 0)
            lines.append(f"\n  오감지 격하: {stats[0]}건  |  LLM 신규 추가: {stats[1]}건")

        lines.append(sep)
        return "\n".join(lines)

    def to_pdf(
        self,
        bl: BLFields,
        lc: LCConditions,
        result: ValidationResult,
        output_path: str,
        llm_data: Optional[dict] = None,
    ) -> None:
        """
        PDF 리포트 생성 (reportlab + 한글 폰트 지원)
        한글 폰트(AppleGothic/NanumGothic)가 없으면 영문 레이블로 폴백.
        """
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import (
                HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table,
                TableStyle,
            )
        except ImportError:
            raise ImportError("PDF 생성에는 reportlab이 필요합니다: pip install reportlab")

        # ── 한글 폰트 등록 ──────────────────────────────────────
        korean_font = "Helvetica"   # 폴백
        font_path = _find_korean_font()
        if font_path:
            try:
                pdfmetrics.registerFont(TTFont("KoreanFont", font_path))
                korean_font = "KoreanFont"
            except Exception:
                pass

        # ── 스타일 정의 ──────────────────────────────────────────
        base_styles = getSampleStyleSheet()
        normal_style = ParagraphStyle(
            "KNormal", fontName=korean_font, fontSize=9, leading=13,
        )
        heading1_style = ParagraphStyle(
            "KH1", fontName=korean_font, fontSize=14, leading=18,
            spaceAfter=4, textColor=colors.HexColor("#1A252F"),
        )
        heading2_style = ParagraphStyle(
            "KH2", fontName=korean_font, fontSize=11, leading=14,
            spaceBefore=6, spaceAfter=3, textColor=colors.HexColor("#2C3E50"),
        )

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        doc = SimpleDocTemplate(
            output_path, pagesize=A4,
            leftMargin=18 * mm, rightMargin=18 * mm,
            topMargin=20 * mm, bottomMargin=20 * mm,
        )
        story = []

        pipeline_label = "Rule-based + Llama 3.2 sLLM" if llm_data else "Rule-based"

        # ── 제목 영역 ────────────────────────────────────────────
        story.append(Paragraph("B/L Discrepancy Verification Report", heading1_style))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; "
            f"L/C No: {lc.lc_no or 'N/A'} &nbsp;|&nbsp; Pipeline: {pipeline_label}",
            normal_style,
        ))
        story.append(Spacer(1, 4 * mm))
        story.append(HRFlowable(width="100%", thickness=1.5,
                                color=colors.HexColor("#2C3E50")))
        story.append(Spacer(1, 4 * mm))

        # ── 결과 요약 배너 ───────────────────────────────────────
        is_ok = result.is_valid
        banner_color = colors.HexColor("#27AE60") if is_ok else colors.HexColor("#C0392B")
        verdict_text = "COMPLIANT  — No Discrepancy Found" if is_ok \
            else f"DISCREPANT  — {result.defect_count} Defect(s) Found"
        summary_data = [
            [Paragraph(f"<b>{verdict_text}</b>",
                       ParagraphStyle("banner", fontName=korean_font, fontSize=11,
                                      textColor=colors.white))],
            [Paragraph(
                f"ERROR: {result.defect_count}건 &nbsp;&nbsp; WARNING: {result.warning_count}건",
                ParagraphStyle("sub", fontName=korean_font, fontSize=9,
                               textColor=colors.white))],
        ]
        banner_table = Table(summary_data, colWidths=[174 * mm])
        banner_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), banner_color),
            ("PADDING", (0, 0), (-1, -1), 7),
            ("TOPPADDING", (0, 0), (-1, 0), 10),
            ("BOTTOMPADDING", (0, -1), (-1, -1), 10),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 6 * mm))

        # ── B/L 추출 필드 테이블 ─────────────────────────────────
        story.append(Paragraph("Extracted B/L Fields", heading2_style))
        field_labels = [
            ("bl_no", "B/L No."),
            ("shipper", "Shipper"),
            ("consignee", "Consignee"),
            ("notify_party", "Notify Party"),
            ("vessel", "Vessel"),
            ("voyage_no", "Voyage No."),
            ("port_of_loading", "Port of Loading"),
            ("port_of_discharge", "Port of Discharge"),
            ("description_of_goods", "Description of Goods"),
            ("gross_weight", "Gross Weight"),
            ("measurement", "Measurement (CBM)"),
            ("date_of_issue", "Date of Issue"),
            ("place_of_issue", "Place of Issue"),
            ("on_board_date", "On Board Date"),
            ("total_freight", "Total Freight"),
        ]
        bl_dict = bl.to_dict()
        bl_data = [[
            Paragraph("<b>Field</b>", ParagraphStyle("th", fontName=korean_font,
                      fontSize=9, textColor=colors.white)),
            Paragraph("<b>Extracted Value</b>", ParagraphStyle("th", fontName=korean_font,
                      fontSize=9, textColor=colors.white)),
        ]]
        for key, label in field_labels:
            val = bl_dict.get(key) or "—"
            if len(str(val)) > 90:
                val = val[:90] + "..."
            bl_data.append([
                Paragraph(label, normal_style),
                Paragraph(str(val), normal_style),
            ])
        bl_table = Table(bl_data, colWidths=[55 * mm, 119 * mm])
        bl_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#F2F3F4")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDC3C7")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(bl_table)
        story.append(Spacer(1, 6 * mm))

        # ── L/C 조건 요약 ────────────────────────────────────────
        story.append(Paragraph("L/C Conditions", heading2_style))
        lc_items = [
            ("L/C No.", lc.lc_no or "—"),
            ("Expiry Date", lc.expiry_date or "—"),
            ("Latest Shipment Date", lc.latest_shipment_date or "—"),
            ("Port of Loading", lc.port_of_loading or "Any"),
            ("Port of Discharge", lc.port_of_discharge or "Any"),
            ("Consignee", lc.consignee or "—"),
            ("Description of Goods", (lc.description_of_goods or "—")[:80]),
            ("Max Gross Weight", f"{lc.max_gross_weight_kg} KG" if lc.max_gross_weight_kg else "—"),
        ]
        lc_data = [[Paragraph("<b>Condition</b>",
                    ParagraphStyle("th", fontName=korean_font, fontSize=9,
                                   textColor=colors.white)),
                    Paragraph("<b>Value</b>",
                    ParagraphStyle("th", fontName=korean_font, fontSize=9,
                                   textColor=colors.white))]]
        for label, val in lc_items:
            lc_data.append([Paragraph(label, normal_style),
                             Paragraph(str(val), normal_style)])
        lc_table = Table(lc_data, colWidths=[55 * mm, 119 * mm])
        lc_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A5276")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#EAF2FF")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDC3C7")),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(lc_table)
        story.append(Spacer(1, 6 * mm))

        # ── 하자·경고 목록 ───────────────────────────────────────
        all_issues = result.defects + result.warnings
        if all_issues:
            story.append(Paragraph("Discrepancy & Warning List", heading2_style))
            issue_data = [[
                Paragraph("<b>Code</b>",
                    ParagraphStyle("th", fontName=korean_font, fontSize=9,
                                   textColor=colors.white)),
                Paragraph("<b>Severity</b>",
                    ParagraphStyle("th", fontName=korean_font, fontSize=9,
                                   textColor=colors.white)),
                Paragraph("<b>Field</b>",
                    ParagraphStyle("th", fontName=korean_font, fontSize=9,
                                   textColor=colors.white)),
                Paragraph("<b>Description</b>",
                    ParagraphStyle("th", fontName=korean_font, fontSize=9,
                                   textColor=colors.white)),
            ]]
            for d in all_issues:
                sev_color = colors.HexColor("#E74C3C") if d.severity == "ERROR" \
                    else colors.HexColor("#E67E22")
                desc = d.description[:100]
                if d.bl_value:
                    desc += f"\n  B/L: {d.bl_value[:60]}"
                if d.lc_value:
                    desc += f"\n  L/C: {d.lc_value[:60]}"
                issue_data.append([
                    Paragraph(d.code, ParagraphStyle("cell", fontName=korean_font,
                              fontSize=8, textColor=sev_color)),
                    Paragraph(d.severity, ParagraphStyle("cell", fontName=korean_font,
                              fontSize=8, textColor=sev_color)),
                    Paragraph(d.field, normal_style),
                    Paragraph(desc, ParagraphStyle("desc", fontName=korean_font,
                              fontSize=8, leading=11)),
                ])
            issue_table = Table(
                issue_data,
                colWidths=[14 * mm, 18 * mm, 32 * mm, 110 * mm],
            )
            issue_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#922B21")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.HexColor("#FDEDEC"), colors.white]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#E5B8B7")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
            ]))
            story.append(issue_table)
            story.append(Spacer(1, 4 * mm))
        else:
            story.append(Paragraph(
                "No discrepancies or warnings found.",
                ParagraphStyle("ok", fontName=korean_font, fontSize=9,
                               textColor=colors.HexColor("#27AE60")),
            ))
            story.append(Spacer(1, 4 * mm))

        # ── LLM 판단 섹션 ────────────────────────────────────────
        if llm_data:
            story.append(Paragraph("Llama 3.2 Contextual Analysis", heading2_style))
            llm = llm_data.get("llm_judgment", {})
            verdict = llm.get("overall_verdict", "UNCERTAIN")
            conf = llm.get("confidence", 0.0)
            summary = llm.get("contextual_summary", "—")
            llm_info = [
                ["Overall Verdict", f"{verdict}  (confidence {conf:.0%})"],
                ["Summary", summary[:150]],
                ["False Positive (demoted)", str(llm_data.get("demoted_count", 0))],
                ["LLM New Findings", str(llm_data.get("llm_added_count", 0))],
            ]
            llm_data_rows = [[
                Paragraph("<b>Item</b>", ParagraphStyle("th", fontName=korean_font,
                          fontSize=9, textColor=colors.white)),
                Paragraph("<b>Value</b>", ParagraphStyle("th", fontName=korean_font,
                          fontSize=9, textColor=colors.white)),
            ]]
            for label, val in llm_info:
                llm_data_rows.append([
                    Paragraph(label, normal_style),
                    Paragraph(str(val), normal_style),
                ])
            llm_table = Table(llm_data_rows, colWidths=[55 * mm, 119 * mm])
            llm_table.setStyle(TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#6C3483")),
                ("ROWBACKGROUNDS", (0, 1), (-1, -1),
                 [colors.white, colors.HexColor("#F5EEF8")]),
                ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#D7BDE2")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ]))
            story.append(llm_table)

        # ── 푸터 ─────────────────────────────────────────────────
        story.append(Spacer(1, 6 * mm))
        story.append(HRFlowable(width="100%", thickness=0.5,
                                color=colors.HexColor("#BDC3C7")))
        story.append(Paragraph(
            "B/L AI Verification System — UCP 600 Rule-based Engine",
            ParagraphStyle("footer", fontName=korean_font, fontSize=7,
                           textColor=colors.grey),
        ))

        doc.build(story)

    # ══════════════════════════════════════════════════════════════
    # 이미지 OCR vs 라벨링 JSON 정확도 리포트
    # ══════════════════════════════════════════════════════════════

    def eval_to_text(self, report) -> str:
        """
        정확도 평가 결과 → 콘솔 텍스트.

        Parameters
        ----------
        report : AccuracyReport  (src.evaluator)
        """
        from .evaluator import AccuracyReport  # 순환 임포트 방지

        EVAL_FIELDS = ["bl_no", "shipper", "consignee",
                       "port_of_loading", "port_of_discharge",
                       "date_of_issue", "gross_weight"]

        sep = "=" * 65
        lines = [
            sep,
            "  B/L OCR 정확도 리포트  (이미지 OCR vs 라벨링 JSON)",
            f"  생성일시: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"  평가 샘플 수: {len(report.samples)}건",
            sep,
            "",
            "─" * 65,
            "▶ 필드별 정확도",
            "─" * 65,
            f"  {'필드':<25} {'정확도':>8}  {'게이지'}",
        ]
        for fn in EVAL_FIELDS:
            acc = report.field_accuracy(fn)
            bar = "█" * int(acc * 20) + "░" * (20 - int(acc * 20))
            lines.append(f"  {fn:<25} {acc:>7.1%}  {bar}")
        lines.append("─" * 65)
        lines.append(f"  {'필드 전체 평균':<25} {report.overall_accuracy:>7.1%}")

        f1 = report.overall_text_f1
        if f1 is not None:
            lines.append(f"  {'텍스트 F1 평균':<25} {f1:>7.1%}  (단어 집합 기반)")

        lines += ["", "─" * 65, "▶ 샘플별 상세", "─" * 65]
        for s in report.samples:
            icon = "✅" if s.accuracy == 1.0 else ("⚠️" if s.accuracy >= 0.7 else "❌")
            tm = s.text_metrics
            tm_str = f"  | 텍스트F1={tm.f1:.1%}  precision={tm.precision:.1%}  recall={tm.recall:.1%}" if tm else ""
            lines.append(f"  {icon} {s.lc_id}  필드={s.matched}/{s.total} ({s.accuracy:.1%}){tm_str}")
            for fr in s.fields:
                if not fr.matched and fr.match_type != "skip":
                    exp_str = (fr.expected or "─")[:50]
                    got_str = (fr.extracted or "─ 미추출")[:50]
                    lines.append(f"       ✗ {fr.field_name}")
                    lines.append(f"           라벨: {exp_str}")
                    lines.append(f"           OCR : {got_str}")

        lines.append(sep)
        return "\n".join(lines)

    def eval_to_json(self, report, output_path: Optional[str] = None) -> dict:
        """정확도 평가 결과 → JSON (선택적 파일 저장)"""
        EVAL_FIELDS = ["bl_no", "shipper", "consignee",
                       "port_of_loading", "port_of_discharge",
                       "date_of_issue", "gross_weight"]

        data = {
            "generated_at": datetime.now().isoformat(),
            "report_type": "image_vs_label_accuracy",
            "sample_count": len(report.samples),
            "overall": {
                "field_accuracy": report.overall_accuracy,
                "text_f1": report.overall_text_f1,
                "field_accuracy_by_field": {
                    fn: report.field_accuracy(fn) for fn in EVAL_FIELDS
                },
            },
            "samples": [],
        }

        for s in report.samples:
            tm = s.text_metrics
            sample_dict = {
                "image_id": s.lc_id,
                "label_file": s.bl_file,
                "field_accuracy": s.accuracy,
                "field_matched": s.matched,
                "field_total": s.total,
                "text_metrics": {
                    "label_word_count": tm.label_word_count,
                    "ocr_word_count": tm.ocr_word_count,
                    "matched_word_count": tm.matched_word_count,
                    "precision": round(tm.precision, 4),
                    "recall": round(tm.recall, 4),
                    "f1": round(tm.f1, 4),
                } if tm else None,
                "fields": [
                    {
                        "field": fr.field_name,
                        "expected": fr.expected,
                        "extracted": fr.extracted,
                        "matched": fr.matched,
                        "match_type": fr.match_type,
                    }
                    for fr in s.fields
                    if fr.match_type != "skip"
                ],
            }
            data["samples"].append(sample_dict)

        if output_path:
            os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
            with open(output_path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
        return data

    def eval_to_pdf(self, report, output_path: str) -> None:
        """정확도 평가 결과 → PDF 리포트"""
        try:
            from reportlab.lib import colors
            from reportlab.lib.pagesizes import A4
            from reportlab.lib.styles import ParagraphStyle
            from reportlab.lib.units import mm
            from reportlab.pdfbase import pdfmetrics
            from reportlab.pdfbase.ttfonts import TTFont
            from reportlab.platypus import (
                HRFlowable, Paragraph, SimpleDocTemplate, Spacer, Table,
                TableStyle,
            )
        except ImportError:
            raise ImportError("PDF 생성에는 reportlab이 필요합니다: pip install reportlab")

        # 한글 폰트 등록
        korean_font = "Helvetica"
        font_path = _find_korean_font()
        if font_path:
            try:
                pdfmetrics.registerFont(TTFont("KoreanFont", font_path))
                korean_font = "KoreanFont"
            except Exception:
                pass

        normal_style = ParagraphStyle("KNormal", fontName=korean_font, fontSize=9, leading=13)
        h1_style = ParagraphStyle("KH1", fontName=korean_font, fontSize=14, leading=18,
                                  spaceAfter=4, textColor=colors.HexColor("#1A252F"))
        h2_style = ParagraphStyle("KH2", fontName=korean_font, fontSize=11, leading=14,
                                  spaceBefore=6, spaceAfter=3, textColor=colors.HexColor("#2C3E50"))

        os.makedirs(os.path.dirname(output_path) or ".", exist_ok=True)
        doc = SimpleDocTemplate(output_path, pagesize=A4,
                                leftMargin=18*mm, rightMargin=18*mm,
                                topMargin=20*mm, bottomMargin=20*mm)
        story = []

        # ── 제목 ─────────────────────────────────────────────────
        story.append(Paragraph("B/L OCR Accuracy Report", h1_style))
        story.append(Paragraph(
            f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')} &nbsp;|&nbsp; "
            f"Samples: {len(report.samples)}",
            normal_style,
        ))
        story.append(Spacer(1, 4*mm))
        story.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor("#2C3E50")))
        story.append(Spacer(1, 4*mm))

        # ── 전체 요약 배너 ───────────────────────────────────────
        overall_acc = report.overall_accuracy
        banner_color = (colors.HexColor("#27AE60") if overall_acc >= 0.8
                        else colors.HexColor("#E67E22") if overall_acc >= 0.6
                        else colors.HexColor("#C0392B"))
        banner_data = [[
            Paragraph(f"<b>필드 추출 정확도: {overall_acc:.1%}</b>",
                      ParagraphStyle("bn", fontName=korean_font, fontSize=11,
                                     textColor=colors.white)),
        ]]
        banner_table = Table(banner_data, colWidths=[174*mm])
        banner_table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, -1), banner_color),
            ("PADDING", (0, 0), (-1, -1), 10),
        ]))
        story.append(banner_table)
        story.append(Spacer(1, 6*mm))

        # ── 필드별 정확도 테이블 ─────────────────────────────────
        EVAL_FIELDS = ["bl_no", "shipper", "consignee",
                       "port_of_loading", "port_of_discharge",
                       "date_of_issue", "gross_weight"]

        story.append(Paragraph("Field-level Accuracy", h2_style))
        field_data = [[
            Paragraph("<b>Field</b>", ParagraphStyle("th", fontName=korean_font,
                      fontSize=9, textColor=colors.white)),
            Paragraph("<b>Accuracy</b>", ParagraphStyle("th", fontName=korean_font,
                      fontSize=9, textColor=colors.white)),
            Paragraph("<b>Gauge</b>", ParagraphStyle("th", fontName=korean_font,
                      fontSize=9, textColor=colors.white)),
        ]]
        for fn in EVAL_FIELDS:
            acc = report.field_accuracy(fn)
            gauge = "█" * int(acc * 15) + "░" * (15 - int(acc * 15))
            acc_color = (colors.HexColor("#27AE60") if acc >= 0.8
                         else colors.HexColor("#E67E22") if acc >= 0.5
                         else colors.HexColor("#C0392B"))
            field_data.append([
                Paragraph(fn, normal_style),
                Paragraph(f"<b>{acc:.1%}</b>",
                          ParagraphStyle("acc", fontName=korean_font, fontSize=9,
                                         textColor=acc_color)),
                Paragraph(gauge, ParagraphStyle("gauge", fontName="Courier", fontSize=8)),
            ])
        # 전체 평균 행
        oa = report.overall_accuracy
        field_data.append([
            Paragraph("<b>Overall Average</b>", ParagraphStyle("tot", fontName=korean_font,
                      fontSize=9)),
            Paragraph(f"<b>{oa:.1%}</b>", ParagraphStyle("tot2", fontName=korean_font,
                      fontSize=9, textColor=colors.HexColor("#2C3E50"))),
            Paragraph("", normal_style),
        ])

        ft = Table(field_data, colWidths=[60*mm, 30*mm, 84*mm])
        ft.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
            ("BACKGROUND", (0, -1), (-1, -1), colors.HexColor("#D5D8DC")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -2), [colors.white, colors.HexColor("#F2F3F4")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDC3C7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 5),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(ft)
        story.append(Spacer(1, 6*mm))

        # ── 샘플별 상세 테이블 ───────────────────────────────────
        story.append(Paragraph("Sample Details", h2_style))
        sample_data = [[
            Paragraph("<b>Image ID</b>", ParagraphStyle("th", fontName=korean_font,
                      fontSize=8, textColor=colors.white)),
            Paragraph("<b>Field Acc.</b>", ParagraphStyle("th", fontName=korean_font,
                      fontSize=8, textColor=colors.white)),
        ]]
        for s in report.samples:
            acc_color = (colors.HexColor("#27AE60") if s.accuracy >= 0.8
                         else colors.HexColor("#E67E22") if s.accuracy >= 0.5
                         else colors.HexColor("#C0392B"))
            sample_data.append([
                Paragraph(s.lc_id[:30], normal_style),
                Paragraph(f"{s.matched}/{s.total} ({s.accuracy:.0%})",
                          ParagraphStyle("c", fontName=korean_font, fontSize=8,
                                         textColor=acc_color)),
            ])

        st = Table(sample_data, colWidths=[120*mm, 54*mm])
        st.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#1A5276")),
            ("ROWBACKGROUNDS", (0, 1), (-1, -1),
             [colors.white, colors.HexColor("#EAF2FF")]),
            ("GRID", (0, 0), (-1, -1), 0.4, colors.HexColor("#BDC3C7")),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 4),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
            ("LEFTPADDING", (0, 0), (-1, -1), 5),
        ]))
        story.append(st)

        # ── 푸터 ─────────────────────────────────────────────────
        story.append(Spacer(1, 6*mm))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.HexColor("#BDC3C7")))
        story.append(Paragraph(
            "B/L AI Verification System — OCR Accuracy Evaluation",
            ParagraphStyle("footer", fontName=korean_font, fontSize=7,
                           textColor=colors.grey),
        ))

        doc.build(story)
