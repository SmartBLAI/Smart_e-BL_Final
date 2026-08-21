"""
sLLM 문맥 판단 모듈 (Llama 3 via ollama)

역할: Rule-based 검증이 잡지 못하는 비정형 하자를 Llama 3로 보완
  - 동일 항구 다른 표기 (BUSAN ↔ PUSAN)
  - 화물 명세 의미적 유사성 판단
  - 다중 필드 논리적 일관성 검사
  - UCP 600 미묘한 해석 규칙

실행 환경: 오프라인 (ollama 로컬 서버)
설치 방법:
  1. https://ollama.com 에서 ollama 설치
  2. ollama pull llama3.2       (경량, 추천)
     또는 ollama pull llama3   (고정밀)
  3. ollama serve               (서버 시작, 별도 터미널)
"""

import json
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import List, Optional

from .field_parser import BLFields
from .validator import Defect, LCConditions, ValidationResult


# ── 응답 데이터 클래스 ────────────────────────────────────────────

@dataclass
class RuleReview:
    """Rule-based 하자에 대한 LLM 재검토 결과"""
    code: str
    confirmed: bool       # True: 하자 확인 / False: 오감지로 판단
    reasoning: str


@dataclass
class LLMFinding:
    """LLM이 새로 발견한 하자"""
    field: str
    code: str             # LLM-XXX 형식
    description: str
    severity: str         # "ERROR" | "WARNING"
    reasoning: str


@dataclass
class LLMJudgment:
    """Llama 3 전체 판단 결과"""
    overall_verdict: str          # "DISCREPANT" | "COMPLIANT" | "UNCERTAIN"
    confidence: float             # 0.0 ~ 1.0
    rule_reviews: List[RuleReview] = field(default_factory=list)
    additional_findings: List[LLMFinding] = field(default_factory=list)
    contextual_summary: str = ""
    raw_response: str = ""        # 디버그용 원본 응답

    @property
    def confirmed_defects(self) -> List[RuleReview]:
        return [r for r in self.rule_reviews if r.confirmed]

    @property
    def rejected_defects(self) -> List[RuleReview]:
        return [r for r in self.rule_reviews if not r.confirmed]

    def to_dict(self) -> dict:
        return {
            "overall_verdict": self.overall_verdict,
            "confidence": self.confidence,
            "rule_reviews": [
                {
                    "code": r.code,
                    "confirmed": r.confirmed,
                    "reasoning": r.reasoning,
                }
                for r in self.rule_reviews
            ],
            "additional_findings": [
                {
                    "field": f.field,
                    "code": f.code,
                    "description": f.description,
                    "severity": f.severity,
                    "reasoning": f.reasoning,
                }
                for f in self.additional_findings
            ],
            "contextual_summary": self.contextual_summary,
        }


# ── Llama 3 판단기 ───────────────────────────────────────────────

class LlamaJudge:
    """
    ollama HTTP API를 통한 Llama 3 로컬 추론기

    기본 엔드포인트: http://localhost:11434
    모델: llama3.2 (3B, 기본) 또는 llama3 (8B, 고정밀)
    """

    SYSTEM_PROMPT = """You are an expert trade finance specialist with deep knowledge of:
- ICC UCP 600 (Uniform Customs and Practice for Documentary Credits)
- Bill of Lading (B/L) discrepancy analysis
- Letter of Credit (L/C) compliance verification

Your task is to analyze B/L documents against L/C conditions and identify discrepancies.
You must respond ONLY with valid JSON matching the exact schema provided.
Do not add any text outside the JSON object."""

    def __init__(
        self,
        model: str = "llama3.2",
        host: str = "http://localhost:11434",
        timeout: int = 120,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    # ── 공개 메서드 ──────────────────────────────────────────────

    def judge(self, bl: BLFields, lc: LCConditions, rule_result: ValidationResult) -> LLMJudgment:
        """Llama 3로 B/L 하자 문맥 판단 실행 (Rule 결과가 없으면 즉시 COMPLIANT 반환)"""
        # Rule 하자·경고가 없으면 LLM 호출 불필요
        if not rule_result.defects and not rule_result.warnings:
            return LLMJudgment(
                overall_verdict="COMPLIANT",
                confidence=1.0,
                contextual_summary="Rule-based engine found no issues. LLM review skipped.",
            )

        self._check_server()
        prompt = self._build_prompt(bl, lc, rule_result)
        raw = self._call_ollama(prompt)
        return self._parse_response(raw, rule_result)

    def is_available(self) -> bool:
        """ollama 서버 및 모델 사용 가능 여부 확인"""
        try:
            self._check_server()
            return True
        except RuntimeError:
            return False

    def list_models(self) -> list:
        """설치된 ollama 모델 목록 반환"""
        url = f"{self.host}/api/tags"
        try:
            with urllib.request.urlopen(url, timeout=5) as resp:
                data = json.loads(resp.read())
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    # ── 프롬프트 구성 ────────────────────────────────────────────

    def _build_prompt(
        self, bl: BLFields, lc: LCConditions, rule_result: ValidationResult
    ) -> str:
        bl_dict = bl.to_dict()
        rule_issues = [
            {"code": d.code, "field": d.field, "description": d.description,
             "bl_value": d.bl_value, "lc_value": d.lc_value, "severity": d.severity}
            for d in rule_result.defects + rule_result.warnings
        ]

        # Rule 결과가 없으면 LLM 검토 불필요
        if not rule_issues:
            response_schema = {
                "overall_verdict": "COMPLIANT",
                "confidence": 1.0,
                "rule_based_review": [],
                "contextual_summary": "No rule-based findings to review."
            }
            return json.dumps(response_schema)

        response_schema = {
            "overall_verdict": "<DISCREPANT|COMPLIANT|UNCERTAIN>",
            "confidence": "<0.0 to 1.0>",
            "rule_based_review": [
                {
                    "code": "<same code from Rule-Based Findings>",
                    "confirmed": "<true if it is a real discrepancy | false if it is a false positive>",
                    "reasoning": "<concise explanation in 1-2 sentences>"
                }
            ],
            "contextual_summary": "<overall assessment based solely on rule findings above>"
        }

        prompt = f"""You are a trade finance expert reviewing rule-based discrepancy findings on a Bill of Lading (B/L).

## Your ONLY Task
Review each rule-based finding below and determine whether it is a REAL discrepancy or a FALSE POSITIVE.
- Do NOT add any new findings.
- Do NOT check fields that are not listed in Rule-Based Findings.
- Base your verdict ONLY on the confirmed findings.

## B/L Extracted Fields
{json.dumps(bl_dict, ensure_ascii=False, indent=2)}

## L/C Conditions
- L/C No: {lc.lc_no}
- Expiry Date: {lc.expiry_date or 'Not specified'}
- Latest Shipment Date: {lc.latest_shipment_date or 'Not specified'}
- Port of Loading: {lc.port_of_loading or 'Not specified'}
- Port of Discharge: {lc.port_of_discharge or 'Not specified'}
- Consignee: {lc.consignee or 'Not specified'}
- Description of Goods: {lc.description_of_goods or 'Not specified'}
- Max Gross Weight: {f"{lc.max_gross_weight_kg} KG" if lc.max_gross_weight_kg else 'Not specified'}
- Max Measurement: {f"{lc.max_measurement_cbm} CBM" if lc.max_measurement_cbm else 'Not specified'}

## Rule-Based Findings to Review (ONLY these — do not add others)
{json.dumps(rule_issues, ensure_ascii=False, indent=2)}

## Required JSON Response Schema
{json.dumps(response_schema, indent=2)}

Respond with ONLY the JSON object, no other text."""

        return prompt

    # ── ollama 통신 ──────────────────────────────────────────────

    def _call_ollama(self, prompt: str) -> str:
        """ollama /api/chat 엔드포인트 호출"""
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",            # JSON 출력 강제 (ollama 네이티브 지원)
            "options": {
                "temperature": 0.1,      # 낮은 온도 → 일관된 구조화 응답
                "num_predict": 2048,
            },
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read())
                return result["message"]["content"]
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"ollama 서버 연결 실패: {e}\n"
                f"서버 실행 확인: ollama serve"
            ) from e

    def _check_server(self) -> None:
        """서버 및 모델 가용성 확인"""
        try:
            with urllib.request.urlopen(f"{self.host}/api/tags", timeout=5) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
        except urllib.error.URLError as e:
            raise RuntimeError(
                f"ollama 서버에 접속할 수 없습니다: {e}\n\n"
                f"[해결 방법]\n"
                f"  1. ollama 설치: https://ollama.com\n"
                f"  2. 모델 다운로드: ollama pull {self.model}\n"
                f"  3. 서버 시작:    ollama serve"
            ) from e

        # 모델명 매칭 (태그 포함 or 미포함)
        base = self.model.split(":")[0]
        if not any(m.startswith(base) for m in models):
            raise RuntimeError(
                f"모델 '{self.model}'이 설치되어 있지 않습니다.\n"
                f"설치된 모델: {models}\n"
                f"설치 명령: ollama pull {self.model}"
            )

    # ── 응답 파싱 ────────────────────────────────────────────────

    def _parse_response(self, raw: str, rule_result: ValidationResult) -> LLMJudgment:
        """LLM 응답 JSON 파싱 및 LLMJudgment 변환"""
        try:
            # JSON 블록 추출 (응답에 앞뒤 텍스트가 있을 경우 대비)
            json_match = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_match:
                raise ValueError("JSON 객체를 찾을 수 없습니다")
            data = json.loads(json_match.group())
        except (json.JSONDecodeError, ValueError) as e:
            return LLMJudgment(
                overall_verdict="UNCERTAIN",
                confidence=0.0,
                contextual_summary=f"[LLM 응답 파싱 실패: {e}]",
                raw_response=raw,
            )

        # rule_based_review 파싱
        rule_reviews = []
        for item in data.get("rule_based_review", []):
            rule_reviews.append(RuleReview(
                code=item.get("code", "UNKNOWN"),
                confirmed=bool(item.get("confirmed", True)),
                reasoning=item.get("reasoning", ""),
            ))

        # additional_findings: Rule 1순위 정책에 따라 사용하지 않음
        return LLMJudgment(
            overall_verdict=data.get("overall_verdict", "UNCERTAIN").upper(),
            confidence=float(data.get("confidence", 0.5)),
            rule_reviews=rule_reviews,
            additional_findings=[],
            contextual_summary=data.get("contextual_summary", ""),
            raw_response=raw,
        )


# ── LLM 필드 추출기 (규칙 기반 실패 시 fallback) ─────────────────

class LlamaExtractor:
    """
    OCR 텍스트에서 누락 필드를 Llama 3.2로 추출.
    FieldParser 추출 실패 시 fallback으로 호출됨.

    사용법::
        extractor = LlamaExtractor()
        filled = extractor.extract_missing_fields(ocr_text, ["port_of_loading"])
        # → {"port_of_loading": "BUSAN, KOREA"}
    """

    SYSTEM_PROMPT = (
        "You are a trade document parser. Extract specific fields from "
        "Bill of Lading (B/L) OCR text. "
        "Respond ONLY with valid JSON. No explanation. No extra text."
    )

    # 필드별 설명 (프롬프트 힌트)
    FIELD_HINTS = {
        "bl_no": "B/L number (e.g. HG290309, format: 2-6 letters + 4-12 digits)",
        "consignee": "Consignee company name (e.g. ABC TRADING CO., LTD.)",
        "port_of_loading": "Port of Loading city and country (e.g. BUSAN, KOREA)",
        "port_of_discharge": "Port of Discharge city and country (e.g. OSAKA, JAPAN)",
        "date_of_issue": "Date of Issue (e.g. 15 SEP 2022, 2022-09-15)",
        "vessel": "Vessel/ship name (e.g. MSC BIANCA)",
        "gross_weight": "Total gross weight with unit (e.g. 884 KG)",
    }

    def __init__(
        self,
        model: str = "llama3.2",
        host: str = "http://localhost:11434",
        timeout: int = 60,
    ):
        self.model = model
        self.host = host.rstrip("/")
        self.timeout = timeout

    def extract_missing_fields(
        self, ocr_text: str, missing_fields: List[str]
    ) -> dict:
        """
        OCR 텍스트에서 누락 필드 추출.

        :param ocr_text: bbox 전체를 줄바꿈으로 합친 원시 텍스트
        :param missing_fields: 추출할 필드 이름 목록
        :returns: {field_name: extracted_value, ...}  (실패 시 빈 dict)
        """
        if not missing_fields:
            return {}

        hints = "\n".join(
            f"  - {f}: {self.FIELD_HINTS.get(f, f)}"
            for f in missing_fields
        )
        # 텍스트 길이 제한 (토큰 과다 방지)
        text_excerpt = ocr_text[:4000]

        schema_example = {f: "<extracted value or null>" for f in missing_fields}

        prompt = (
            f"From the following Bill of Lading OCR text, extract these fields:\n"
            f"{hints}\n\n"
            f"OCR TEXT:\n{text_excerpt}\n\n"
            f"Respond with ONLY this JSON (null if not found):\n"
            f"{json.dumps(schema_example, indent=2)}"
        )

        try:
            raw = self._call_ollama(prompt)
        except RuntimeError:
            return {}

        return self._parse_extraction(raw, missing_fields)

    def is_available(self) -> bool:
        """ollama 서버 사용 가능 여부"""
        try:
            with urllib.request.urlopen(
                f"{self.host}/api/tags", timeout=3
            ) as resp:
                data = json.loads(resp.read())
                models = [m["name"] for m in data.get("models", [])]
                base = self.model.split(":")[0]
                return any(m.startswith(base) for m in models)
        except Exception:
            return False

    def _call_ollama(self, prompt: str) -> str:
        payload = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self.SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
            "format": "json",
            "options": {"temperature": 0.05, "num_predict": 512},
        }
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{self.host}/api/chat",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                result = json.loads(resp.read())
                return result["message"]["content"]
        except urllib.error.URLError as e:
            raise RuntimeError(f"ollama 연결 실패: {e}") from e

    def _parse_extraction(self, raw: str, fields: List[str]) -> dict:
        try:
            json_m = re.search(r"\{.*\}", raw, re.DOTALL)
            if not json_m:
                return {}
            data = json.loads(json_m.group())
        except (json.JSONDecodeError, ValueError):
            return {}

        result = {}
        for f in fields:
            val = data.get(f)
            if val and str(val).strip().lower() not in ("null", "none", "", "n/a"):
                result[f] = str(val).strip()
        return result


# ── Rule-based + LLM 결과 병합 ───────────────────────────────────

def merge_results(
    rule_result: ValidationResult,
    llm_judgment: LLMJudgment,
) -> dict:
    """
    Rule-based 검증 결과와 LLM 판단을 병합하여 최종 결과 생성

    병합 전략 (Rule 1순위):
    - Rule이 탐지한 하자만을 최종 결과의 기반으로 사용
    - LLM이 오감지(false positive)로 판단한 rule 하자는 경고(WARNING)로 격하
    - LLM이 확인한 rule 하자는 그대로 ERROR 유지
    - LLM 독자적 추가 발견은 반영하지 않음
    - UNCERTAIN이면 rule 결과를 그대로 사용
    """
    # LLM이 false positive라고 판단한 코드 집합
    rejected_codes = {r.code for r in llm_judgment.rejected_defects}

    final_defects = []
    demoted_to_warning = []

    for d in rule_result.defects:
        if d.code in rejected_codes:
            review = next((r for r in llm_judgment.rule_reviews if r.code == d.code), None)
            reasoning = review.reasoning if review else "LLM 재검토 결과 오감지 판단"
            demoted = Defect(
                code=d.code, field=d.field,
                description=f"[LLM 재검토: 오감지 가능성] {d.description}  ※ {reasoning}",
                bl_value=d.bl_value, lc_value=d.lc_value,
                severity="WARNING",
            )
            demoted_to_warning.append(demoted)
        else:
            final_defects.append(d)

    all_warnings = rule_result.warnings + demoted_to_warning

    # 최종 is_valid: Rule 하자 중 LLM이 확인한 것만 남김
    is_valid = len(final_defects) == 0

    merged = ValidationResult(
        is_valid=is_valid,
        defects=final_defects,
        warnings=all_warnings,
    )
    return {
        "merged_validation": merged.to_dict(),
        "llm_judgment": llm_judgment.to_dict(),
        "demoted_count": len(demoted_to_warning),
        "llm_added_count": 0,   # 추가 발견 비활성화
    }
