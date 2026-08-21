"""
Rule-based 하자 검증 모듈 (ICC UCP 600 기반)
- B/L 필드와 L/C 조건을 1:1 교차 비교
- 하자 코드 및 설명 생성
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, List, Optional

from .field_parser import BLFields


# ── L/C 조건 데이터 클래스 ───────────────────────────────────────

@dataclass
class LCConditions:
    """신용장(L/C) 조건 - ICC UCP 600 전체 필드"""

    # ── 기본 정보 ───────────────────────────────────────────────
    lc_no: str = ""
    lc_type: str = "IRREVOCABLE"              # IRREVOCABLE | REVOCABLE

    # ── 당사자 ──────────────────────────────────────────────────
    applicant: Optional[str] = None           # 개설의뢰인 (Applicant)
    beneficiary: Optional[str] = None         # 수익자 (Beneficiary)
    issuing_bank: Optional[str] = None        # 개설은행
    advising_bank: Optional[str] = None       # 통지은행

    # ── 금액 ────────────────────────────────────────────────────
    currency: str = "USD"
    amount: Optional[float] = None            # L/C 금액
    tolerance_pct: float = 10.0              # 허용 오차 % (UCP 600 Art.30)

    # ── 기간 ────────────────────────────────────────────────────
    expiry_date: Optional[str] = None         # L/C 유효기간
    expiry_place: Optional[str] = None        # 유효기간 만료 장소
    latest_shipment_date: Optional[str] = None  # 최종 선적일
    period_for_presentation: int = 21         # 서류 제출 기간(일) UCP 600 Art.14

    # ── 운송 조건 ───────────────────────────────────────────────
    port_of_loading: Optional[str] = None     # 지정 선적항
    port_of_discharge: Optional[str] = None   # 지정 양하항
    incoterms: Optional[str] = None           # FOB / CIF / CFR 등
    partial_shipment: str = "PROHIBITED"      # ALLOWED | PROHIBITED
    transhipment: str = "PROHIBITED"          # ALLOWED | PROHIBITED

    # ── 화물 ────────────────────────────────────────────────────
    consignee: Optional[str] = None           # 지정 수화인
    description_of_goods: Optional[str] = None  # 화물 명세 키워드
    max_gross_weight_kg: Optional[float] = None  # 최대 허용 중량 (KG)
    max_measurement_cbm: Optional[float] = None  # 최대 허용 용적 (CBM)

    # ── 결제 조건 ───────────────────────────────────────────────
    payment_terms: str = "SIGHT"              # SIGHT | USANCE
    usance_days: Optional[int] = None         # Usance 일수
    freight_amount: Optional[float] = None    # 지정 운임 금액 (D017 검증용, None이면 검증 생략)

    # ── 요구 서류 ───────────────────────────────────────────────
    required_documents: List[str] = field(default_factory=list)
    # 예: ["COMMERCIAL INVOICE", "PACKING LIST", "CERTIFICATE OF ORIGIN", "BILL OF LADING"]

    # ── 특별 조건 ───────────────────────────────────────────────
    special_conditions: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict) -> "LCConditions":
        known = set(cls.__dataclass_fields__)
        return cls(**{k: v for k, v in d.items() if k in known})


# ── 하자 결과 데이터 클래스 ──────────────────────────────────────

@dataclass
class Defect:
    code: str
    field: str
    description: str
    bl_value: Optional[str]
    lc_value: Optional[str]
    severity: str  # "ERROR" | "WARNING"


@dataclass
class ValidationResult:
    is_valid: bool
    defects: List[Defect] = field(default_factory=list)
    warnings: List[Defect] = field(default_factory=list)

    @property
    def defect_count(self) -> int:
        return len(self.defects)

    @property
    def warning_count(self) -> int:
        return len(self.warnings)

    def to_dict(self) -> dict:
        return {
            "is_valid": self.is_valid,
            "defect_count": self.defect_count,
            "warning_count": self.warning_count,
            "defects": [
                {
                    "code": d.code,
                    "field": d.field,
                    "description": d.description,
                    "bl_value": d.bl_value,
                    "lc_value": d.lc_value,
                    "severity": d.severity,
                }
                for d in self.defects + self.warnings
            ],
        }


# ── 검증기 ───────────────────────────────────────────────────────

class BLValidator:
    """B/L 하자 검증기 (UCP 600 룰셋)"""

    DATE_FORMATS = [
        "%m-%d-%Y", "%Y-%m-%d", "%d-%m-%Y",
        "%m/%d/%Y", "%Y/%m/%d", "%d/%m/%Y",
        "%d %b %Y", "%d %B %Y",
    ]

    # 항구명 동의어 테이블 (도시명 단위 매칭)
    PORT_SYNONYMS: List[frozenset] = [
        frozenset(["BUSAN", "PUSAN"]),
        frozenset(["GUANGZHOU", "CANTON"]),
        frozenset(["MUMBAI", "BOMBAY"]),
        frozenset(["CHENNAI", "MADRAS"]),
        frozenset(["KOLKATA", "CALCUTTA"]),
        frozenset(["BEIJING", "PEKING"]),
        frozenset(["TROMSOE", "TROMSO"]),
        frozenset(["JEDDAH", "JEDDA"]),
        frozenset(["INCHEON", "INCHON"]),
    ]

    def validate(self, bl: BLFields, lc: LCConditions) -> ValidationResult:
        defects: List[Defect] = []
        warnings: List[Defect] = []

        checks = [
            self._check_bl_no(bl),
            self._check_shipper(bl),
            self._check_consignee(bl, lc),
            self._check_notify_party(bl),
            self._check_vessel(bl),
            self._check_port_of_loading(bl, lc),
            self._check_port_of_discharge(bl, lc),
            self._check_shipment_date(bl, lc),
            self._check_expiry_date(bl, lc),
            self._check_description(bl, lc),
            self._check_gross_weight(bl, lc),
            self._check_measurement(bl, lc),
            # 신규: UCP 600 확장 룰
            self._check_partial_shipment(bl, lc),
            self._check_transhipment(bl, lc),
            self._check_incoterms(bl, lc),
            self._check_required_documents(bl, lc),
            self._check_freight_amount(bl, lc),
        ]

        for result in checks:
            if result is None:
                continue
            if result.severity == "ERROR":
                defects.append(result)
            else:
                warnings.append(result)

        return ValidationResult(
            is_valid=len(defects) == 0,
            defects=defects,
            warnings=warnings,
        )

    # ─── 개별 룰 ─────────────────────────────────────────────────

    def _check_bl_no(self, bl: BLFields) -> Optional[Defect]:
        if not bl.bl_no:
            return Defect(
                code="D001", field="bl_no",
                description="B/L 번호가 누락되었습니다",
                bl_value=None, lc_value=None, severity="ERROR",
            )
        return None

    def _check_shipper(self, bl: BLFields) -> Optional[Defect]:
        if not bl.shipper:
            return Defect(
                code="D009", field="shipper",
                description="Shipper 정보가 누락되었습니다",
                bl_value=None, lc_value=None, severity="WARNING",
            )
        return None

    def _check_consignee(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        if not bl.consignee:
            return Defect(
                code="D005", field="consignee",
                description="Consignee 정보가 누락되었습니다",
                bl_value=None, lc_value=lc.consignee, severity="ERROR",
            )
        if lc.consignee and not self._partial_match(bl.consignee, lc.consignee):
            return Defect(
                code="D005", field="consignee",
                description="Consignee가 L/C 지정과 불일치합니다",
                bl_value=bl.consignee, lc_value=lc.consignee, severity="ERROR",
            )
        return None

    def _check_notify_party(self, bl: BLFields) -> Optional[Defect]:
        if not bl.notify_party:
            return Defect(
                code="D010", field="notify_party",
                description="Notify Party 정보가 누락되었습니다",
                bl_value=None, lc_value=None, severity="WARNING",
            )
        return None

    def _check_vessel(self, bl: BLFields) -> Optional[Defect]:
        if not bl.vessel:
            return Defect(
                code="D011", field="vessel",
                description="선박명이 누락되었습니다",
                bl_value=None, lc_value=None, severity="WARNING",
            )
        return None

    def _check_port_of_loading(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        if not bl.port_of_loading:
            return Defect(
                code="D012", field="port_of_loading",
                description="선적항 정보가 누락되었습니다",
                bl_value=None, lc_value=lc.port_of_loading, severity="ERROR",
            )
        if lc.port_of_loading and not self._partial_match(bl.port_of_loading, lc.port_of_loading):
            return Defect(
                code="D003", field="port_of_loading",
                description="선적항이 L/C 지정 항구와 불일치합니다",
                bl_value=bl.port_of_loading, lc_value=lc.port_of_loading, severity="ERROR",
            )
        return None

    def _check_port_of_discharge(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        if not bl.port_of_discharge:
            return Defect(
                code="D012", field="port_of_discharge",
                description="양하항 정보가 누락되었습니다",
                bl_value=None, lc_value=lc.port_of_discharge, severity="ERROR",
            )
        if lc.port_of_discharge and not self._partial_match(bl.port_of_discharge, lc.port_of_discharge):
            return Defect(
                code="D004", field="port_of_discharge",
                description="양하항이 L/C 지정 항구와 불일치합니다",
                bl_value=bl.port_of_discharge, lc_value=lc.port_of_discharge, severity="ERROR",
            )
        return None

    def _check_shipment_date(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        if not lc.latest_shipment_date:
            return None
        date_str = bl.on_board_date or bl.date_of_issue
        if not date_str:
            return Defect(
                code="D002", field="on_board_date",
                description="선적일 정보가 누락되었습니다",
                bl_value=None, lc_value=lc.latest_shipment_date, severity="ERROR",
            )
        bl_date = self._parse_date(date_str)
        lc_date = self._parse_date(lc.latest_shipment_date)
        if bl_date and lc_date and bl_date > lc_date:
            return Defect(
                code="D002", field="on_board_date",
                description=f"선적일({date_str})이 L/C 최종 선적기한({lc.latest_shipment_date})을 초과합니다",
                bl_value=date_str, lc_value=lc.latest_shipment_date, severity="ERROR",
            )
        return None

    def _check_expiry_date(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        if not lc.expiry_date or not bl.date_of_issue:
            return None
        bl_date = self._parse_date(bl.date_of_issue)
        exp_date = self._parse_date(lc.expiry_date)
        if bl_date and exp_date and bl_date > exp_date:
            return Defect(
                code="D008", field="date_of_issue",
                description=f"발행일({bl.date_of_issue})이 L/C 유효기간({lc.expiry_date}) 이후입니다",
                bl_value=bl.date_of_issue, lc_value=lc.expiry_date, severity="ERROR",
            )
        return None

    def _check_description(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        if not lc.description_of_goods or not bl.description_of_goods:
            return None
        keywords = [k.strip().upper() for k in lc.description_of_goods.split(",")]
        bl_desc = bl.description_of_goods.upper()
        missing = [kw for kw in keywords if kw not in bl_desc]
        if missing:
            return Defect(
                code="D006", field="description_of_goods",
                description=f"화물 명세에 다음 키워드가 없습니다: {', '.join(missing)}",
                bl_value=bl.description_of_goods[:100], lc_value=lc.description_of_goods, severity="ERROR",
            )
        return None

    def _check_gross_weight(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        if not lc.max_gross_weight_kg or not bl.gross_weight:
            return None
        bl_kg = self._parse_weight_kg(bl.gross_weight)
        if bl_kg is not None and bl_kg > lc.max_gross_weight_kg:
            return Defect(
                code="D007", field="gross_weight",
                description=f"총 중량({bl_kg:.2f} KG)이 L/C 허용 한도({lc.max_gross_weight_kg} KG)를 초과합니다",
                bl_value=bl.gross_weight, lc_value=f"{lc.max_gross_weight_kg} KG", severity="ERROR",
            )
        return None

    def _check_measurement(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        if not lc.max_measurement_cbm or not bl.measurement:
            return None
        bl_cbm = self._parse_cbm(bl.measurement)
        if bl_cbm is not None and bl_cbm > lc.max_measurement_cbm:
            return Defect(
                code="D007", field="measurement",
                description=f"용적({bl_cbm:.3f} CBM)이 L/C 허용 한도({lc.max_measurement_cbm} CBM)를 초과합니다",
                bl_value=bl.measurement, lc_value=f"{lc.max_measurement_cbm} CBM", severity="WARNING",
            )
        return None

    def _check_partial_shipment(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        """UCP 600 Art.31 - 분할선적 금지 여부 확인"""
        if lc.partial_shipment != "PROHIBITED":
            return None
        desc = (bl.description_of_goods or "").upper()
        keywords = ["PARTIAL", "PART SHIPMENT", "PARTIAL SHIPMENT", "1ST SHIPMENT", "2ND SHIPMENT",
                    "FIRST SHIPMENT", "SECOND SHIPMENT"]
        for kw in keywords:
            if kw in desc:
                return Defect(
                    code="D013", field="description_of_goods",
                    description=f"분할선적 금지(PROHIBITED) 조건에서 분할선적 표시가 발견되었습니다: '{kw}'",
                    bl_value=bl.description_of_goods[:100] if bl.description_of_goods else None,
                    lc_value="PARTIAL SHIPMENT: PROHIBITED",
                    severity="ERROR",
                )
        return None

    def _check_transhipment(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        """UCP 600 Art.20c - 환적 금지 여부 확인"""
        if lc.transhipment != "PROHIBITED":
            return None
        text = " ".join(filter(None, [
            bl.description_of_goods,
            bl.port_of_loading,
            bl.port_of_discharge,
        ])).upper()
        keywords = ["TRANSHIPMENT", "TRANSSHIPMENT", "VIA", "TRANSIT"]
        for kw in keywords:
            if kw in text:
                return Defect(
                    code="D014", field="description_of_goods",
                    description=f"환적 금지(PROHIBITED) 조건에서 환적 표시가 발견되었습니다: '{kw}'",
                    bl_value=text[:100],
                    lc_value="TRANSHIPMENT: PROHIBITED",
                    severity="ERROR",
                )
        return None

    def _check_incoterms(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        """Incoterms 일치 여부 확인"""
        if not lc.incoterms:
            return None
        desc = (bl.description_of_goods or "").upper()
        lc_term = lc.incoterms.upper()
        # 주요 Incoterms 용어 목록
        known_terms = ["FOB", "CIF", "CFR", "CIP", "CPT", "DAP", "DPU", "DDP", "EXW", "FCA", "FAS"]
        lc_base = next((t for t in known_terms if lc_term.startswith(t)), lc_term)
        if lc_base not in desc:
            return Defect(
                code="D015", field="description_of_goods",
                description=f"L/C 지정 Incoterms({lc.incoterms})가 화물 명세에 없습니다",
                bl_value=bl.description_of_goods[:100] if bl.description_of_goods else None,
                lc_value=lc.incoterms,
                severity="WARNING",
            )
        return None

    def _check_required_documents(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        """요구 서류 목록 확인 (B/L 자체 존재 여부)"""
        if not lc.required_documents:
            return None
        if "BILL OF LADING" not in [d.upper() for d in lc.required_documents]:
            return Defect(
                code="D016", field="required_documents",
                description="L/C 요구 서류 목록에 BILL OF LADING이 명시되지 않았습니다",
                bl_value=None,
                lc_value=", ".join(lc.required_documents),
                severity="WARNING",
            )
        return None

    # ─── 유틸 ───────────────────────────────────────────────────

    def _parse_date(self, text: str) -> Optional[datetime]:
        for fmt in self.DATE_FORMATS:
            try:
                return datetime.strptime(text.strip(), fmt)
            except ValueError:
                continue
        return None

    def _partial_match(self, bl_val: str, lc_val: str, threshold: float = 0.6) -> bool:
        """단어 단위 부분 매칭 (대소문자 무관) + 항구 동의어 처리
        콤마/특수문자 구분 없이 알파벳 토큰 단위로 비교."""
        bl_words = set(re.findall(r"[A-Z]+", bl_val.upper()))
        lc_words = set(re.findall(r"[A-Z]+", lc_val.upper()))
        if not lc_words:
            return True
        # 동의어 확장: 동의어 set 내의 다른 표기도 매칭으로 처리
        expanded_bl = set(bl_words)
        for word in list(bl_words):
            for syn_set in self.PORT_SYNONYMS:
                if word in syn_set:
                    expanded_bl |= syn_set
        overlap = expanded_bl & lc_words
        return len(overlap) / len(lc_words) >= threshold

    def _check_freight_amount(self, bl: BLFields, lc: LCConditions) -> Optional[Defect]:
        """D017: 운임 금액이 L/C 지정 운임 허용 오차 범위를 벗어나는지 확인 (UCP 600 Art.30)
        lc.freight_amount가 설정된 경우에만 검증 (total L/C amount과 혼동 방지)"""
        if not lc.freight_amount or not bl.total_freight:
            return None
        m = re.search(r"\$?\s*([\d,]+\.?\d*)", bl.total_freight)
        if not m:
            return None
        bl_amount = float(m.group(1).replace(",", ""))
        tol = lc.tolerance_pct / 100.0
        lower = lc.freight_amount * (1 - tol)
        upper = lc.freight_amount * (1 + tol)
        if not (lower <= bl_amount <= upper):
            return Defect(
                code="D017", field="total_freight",
                description=(
                    f"운임 금액({bl_amount:,.2f} {lc.currency})이 "
                    f"L/C 허용 범위 ±{lc.tolerance_pct}% "
                    f"({lower:,.2f}~{upper:,.2f} {lc.currency})를 벗어납니다 "
                    f"(UCP 600 Art.30)"
                ),
                bl_value=bl.total_freight,
                lc_value=f"{lc.freight_amount} {lc.currency} ±{lc.tolerance_pct}%",
                severity="ERROR",
            )
        return None

    def _parse_weight_kg(self, text: str) -> Optional[float]:
        match = re.search(r"([\d,]+\.?\d*)\s*(KGS?|KG)", text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
        match = re.search(r"([\d,]+\.?\d*)\s*(MT|M\.T\.)", text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", "")) * 1000
        return None

    def _parse_cbm(self, text: str) -> Optional[float]:
        match = re.search(r"([\d,]+\.?\d*)\s*(CBM|M3)", text, re.IGNORECASE)
        if match:
            return float(match.group(1).replace(",", ""))
        return None
