"""
B/L 필드 파서 모듈 v2 - 교정된 좌표 기반 + 키워드 앵커 보완
- 실측 데이터 기반 Y-ratio 교정 (이미지 크기 1654×2340 기준)
- bbox 단위 구역 할당 (라인 단위 할당의 좌/우 누출 문제 해결)
- 키워드 앵커 fallback (구역 기반 실패 시)
- 필드별 전용 post-processor
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .ocr_extractor import BBox, OCRResult


# ── B/L 서식 헤더 노이즈 패턴 (Shipper 구역에서 제거 대상) ────────────
# 실제 화주 이름이 아닌 서식 제목·필드 라벨 등
_BL_HEADER_NOISE = (
    "BILL OF LADING", "MULTIMODAL", "NEGOTIABLE", "NON-NEGOTIABLE",
    "FIATA", "WIFFA", "WAYBILL", "COMBINED TRANSPORT", "THROUGH BILL",
    "STRAIGHT BILL", "OCEAN CARRIER", "SEA WAYBILL", "SURRENDER",
    "ORIGINAL", "COPY", "SEAWAY", "FREIGHT FORWARDER",
    "CONSIGNOR/SHIPPER", "CONSIGNOR", "SHIPPER",
)


def _is_header_noise(line: str) -> bool:
    """선하증권 서식 헤더·필드 라벨 라인 여부 판정"""
    upper = line.upper()
    return any(kw in upper for kw in _BL_HEADER_NOISE)


def _is_valid_date_str(date_str: str) -> bool:
    """추출된 날짜 문자열이 현실적인 범위인지 검사.

    'dd-mm-yyyy' 또는 'mm-dd-yyyy' 패턴에서 OCR 노이즈(60-55-2708 등)를
    사전에 걸러냅니다. 월·일 이름(MON) 포함 형식은 항상 통과.
    """
    s = date_str.strip().upper()

    # YYYY-MM-DD
    m = re.match(r"^(\d{4})-(\d{2})-(\d{2})$", s)
    if m:
        y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
        return 1900 <= y <= 2099 and 1 <= mo <= 12 and 1 <= d <= 31

    # DD-MM-YYYY 또는 MM-DD-YYYY  (\d{2}-\d{2}-\d{4})
    m = re.match(r"^(\d{2})[-/](\d{2})[-/](\d{4})$", s)
    if m:
        a, b, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
        if not (1900 <= y <= 2099):
            return False
        if a > 31 or b > 31:          # 31 초과는 일/월 모두 불가
            return False
        if a > 12 and b > 12:          # 둘 다 12 초과 → 월 역할 불가
            return False
        return True

    # 월 이름 포함 형식은 패턴 자체가 유효성 보장
    return True


@dataclass
class BLFields:
    """추출된 B/L 필드 집합"""
    bl_no: Optional[str] = None
    shipper: Optional[str] = None
    consignee: Optional[str] = None
    notify_party: Optional[str] = None
    vessel: Optional[str] = None
    voyage_no: Optional[str] = None
    port_of_loading: Optional[str] = None
    port_of_discharge: Optional[str] = None
    description_of_goods: Optional[str] = None
    gross_weight: Optional[str] = None
    measurement: Optional[str] = None
    date_of_issue: Optional[str] = None
    place_of_issue: Optional[str] = None
    on_board_date: Optional[str] = None
    total_freight: Optional[str] = None
    # 원시 구역 텍스트 (디버그용)
    raw_regions: Dict[str, str] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "bl_no": self.bl_no,
            "shipper": self.shipper,
            "consignee": self.consignee,
            "notify_party": self.notify_party,
            "vessel": self.vessel,
            "voyage_no": self.voyage_no,
            "port_of_loading": self.port_of_loading,
            "port_of_discharge": self.port_of_discharge,
            "description_of_goods": self.description_of_goods,
            "gross_weight": self.gross_weight,
            "measurement": self.measurement,
            "date_of_issue": self.date_of_issue,
            "place_of_issue": self.place_of_issue,
            "on_board_date": self.on_board_date,
            "total_freight": self.total_freight,
        }

    def missing_critical_fields(self) -> List[str]:
        """추출 실패한 핵심 필드 목록 반환 (LLM fallback 트리거용)"""
        critical = [
            "bl_no", "consignee",
            "port_of_loading", "port_of_discharge",
            "date_of_issue",
        ]
        return [f for f in critical if not getattr(self, f)]


class FieldParser:
    """OCRResult → BLFields 변환기 (교정 좌표 + 키워드 앵커)"""

    # ── 구역 정의: 실측 데이터 기반 교정 (이미지 1654×2340 기준) ──────
    # 기존 port 영역(yr=0.52-0.64)이 실제 카고 구역을 가리키던 오류 수정.
    # 실측: port는 y=968~1020px = yr≈0.41~0.44 에 위치.
    REGIONS = {
        # 상단 전체: 서류 제목·헤더
        "header":       {"xr": (0.0,  1.0),  "yr": (0.0,  0.13)},
        # B/L No.: 우측 상단 (실측 x=0.62~0.71, y=0.14~0.18, 일부 폼 y≈0.22)
        "bl_no":        {"xr": (0.50, 0.85), "yr": (0.13, 0.26)},
        # Shipper: 좌측 상단 (실측 y=0.04~0.17)
        "shipper":      {"xr": (0.0,  0.50), "yr": (0.04, 0.17)},
        # Consignee: 좌측 (실측 y=0.17~0.26)
        "consignee":    {"xr": (0.0,  0.50), "yr": (0.16, 0.26)},
        # Notify Party: 좌측 중상단 (실측 y=0.26~0.38)
        "notify":       {"xr": (0.0,  0.50), "yr": (0.25, 0.38)},
        # 선박·항로: 좌측+중앙 (실측 y=0.37~0.43, CFS/CY 토큰 위 0.37 시작)
        "vessel_info":  {"xr": (0.0,  0.60), "yr": (0.37, 0.44)},
        # 선적항: 좌측 첫 번째 컬럼 (실측 x=0.0~0.28)  ← 핵심 수정
        "port_left":    {"xr": (0.0,  0.28), "yr": (0.40, 0.47)},
        # 양하항: 두 번째 컬럼 (실측 x=0.28~0.55)  ← 핵심 수정
        "port_right":   {"xr": (0.28, 0.55), "yr": (0.40, 0.47)},
        # 화물 명세: 중앙 (실측 y=0.52~0.69)
        "cargo":        {"xr": (0.05, 0.68), "yr": (0.50, 0.70)},
        # 총 중량: 화물 우측~하단 (인라인 KG 및 TOTAL 라인 모두 포함)
        "weight":       {"xr": (0.60, 0.82), "yr": (0.50, 0.75)},
        # 총 용적: 화물 우측~하단 (CBM 값 포함)
        "measurement":  {"xr": (0.80, 0.97), "yr": (0.50, 0.75)},
        # 운임·Incoterms: 좌측 하단 (실측 y=0.73~0.86)
        "freight":      {"xr": (0.0,  0.55), "yr": (0.73, 0.87)},
        # 발행지·발행일: 좌측 최하단 (실측 y=0.84~0.96)
        "footer":       {"xr": (0.0,  0.55), "yr": (0.83, 0.97)},
    }

    # ── 키워드 앵커: 구역 기반 실패 시 fallback ──────────────────────
    FIELD_ANCHORS = {
        "bl_no": [
            "B/L NO", "BL NO", "B.L.NO", "BILL OF LADING NO",
            "BILL OF LADING NUMBER", "B/L NUMBER",
        ],
        "shipper": [
            "CONSIGNOR/SHIPPER", "SHIPPER/EXPORTER", "CONSIGNOR",
            "SHIPPER", "EXPORTER", "FROM",
        ],
        "port_of_loading": [
            "PORT OF LOADING", "PORT OF LOAD", "LOADING PORT",
            "POL", "PORT OF SHIPMENT", "PORT OF RECEIPT",
        ],
        "port_of_discharge": [
            "PORT OF DISCHARGE", "PORT OF DISCHARGING", "DISCHARGE PORT",
            "POD", "PLACE OF DELIVERY", "FINAL DESTINATION",
        ],
        "vessel": [
            "VESSEL", "VESSEL NAME", "OCEAN VESSEL", "SHIP",
            "OCEAN VESSEL / VOY", "VESSEL/VOYAGE",
        ],
        "date_of_issue": [
            "DATE OF ISSUE", "DATE ISSUED", "PLACE AND DATE OF ISSUE",
            "DATED", "SIGNED ON",
        ],
        "on_board_date": [
            "ON BOARD", "SHIPPED ON BOARD", "LADEN ON BOARD",
            "DATE LADEN ON BOARD", "ON BOARD DATE",
        ],
    }

    # ── 정규식 패턴 ──────────────────────────────────────────────
    # 날짜: ISO / US / "MM-DD-YYYY" / "DD MON YYYY" / "MON DD, YYYY"
    RE_DATE = re.compile(
        r"\b("
        r"\d{4}-\d{2}-\d{2}"                                # 2014-09-15
        r"|\d{2}-\d{2}-\d{4}"                               # 09-11-2015
        r"|\d{2}/\d{2}/\d{4}"                               # 09/11/2015
        r"|\d{1,2}\s+(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{4}"  # 6 SEP 2006
        r"|(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)\s+\d{1,2}[,.]?\s+\d{4}"  # SEP 06, 2006 / APR 05. 2009
        r"|\d{2}-(?:JAN|FEB|MAR|APR|MAY|JUN|JUL|AUG|SEP|OCT|NOV|DEC)-\d{4}"  # 05-AUG-2016
        r")\b",
        re.IGNORECASE,
    )
    RE_BL_NO = re.compile(r"\b([A-Z]{2,6}\d{4,12})\b")
    RE_WEIGHT = re.compile(
        r"([\d,]+\.?\d*)\s*(KGS?|KG|MT|M\.T\.|METRIC\s*TONS?)", re.IGNORECASE
    )
    RE_CBM = re.compile(r"([\d,]+\.?\d*)\s*(CBM|M3|CU\.?\s*M)", re.IGNORECASE)
    RE_AMOUNT = re.compile(r"\$\s*([\d,]+\.?\d*)")
    # 항구명 오염 토큰: 운송 유형 코드 (제거 대상)
    RE_PORT_NOISE = re.compile(
        r"\b(?:CY|CFS|FCL|LCL|VIA|TRANSIT|THRU)(?:[/\-]\w+)?\b",
        re.IGNORECASE,
    )
    # 선박명 오염 토큰 (제거 대상)
    RE_VESSEL_NOISE = re.compile(
        r"\b(?:CFS|CY|FCL|LCL)(?:[/\-]\w+)?\b",
        re.IGNORECASE,
    )
    # 전화·팩스 라인
    RE_CONTACT = re.compile(r"(?:TEL|FAX|T\)|F\)|PHONE|MOBILE)[^\n]*", re.IGNORECASE)

    def parse(self, ocr: OCRResult, debug: bool = False) -> BLFields:
        """OCR 결과에서 B/L 필드 추출"""
        lines = self._build_lines(ocr.bboxes)
        regions = self._extract_regions(ocr)
        fields_obj = self._map_fields(regions, ocr, lines)

        if debug:
            self._print_debug(fields_obj, regions)
        return fields_obj

    # ─── 1단계: bbox → 라인 재조합 ──────────────────────────────

    def _build_lines(
        self, bboxes: List[BBox], y_tolerance: int = 15
    ) -> List[List[BBox]]:
        """Y 좌표가 가까운 bbox를 같은 라인으로 묶고 X 순 정렬"""
        if not bboxes:
            return []
        sorted_bboxes = sorted(bboxes, key=lambda b: b.center_y)
        lines: List[List[BBox]] = []
        current_line: List[BBox] = [sorted_bboxes[0]]

        for bbox in sorted_bboxes[1:]:
            if abs(bbox.center_y - current_line[-1].center_y) <= y_tolerance:
                current_line.append(bbox)
            else:
                lines.append(sorted(current_line, key=lambda b: b.x_min))
                current_line = [bbox]
        lines.append(sorted(current_line, key=lambda b: b.x_min))
        return lines

    # ─── 2단계: bbox 단위 구역 할당 (라인 단위 누출 문제 해결) ────

    def _extract_regions(self, ocr: OCRResult) -> Dict[str, str]:
        """각 bbox를 해당 구역에 단독 할당 → 좌/우 경계 누출 방지"""
        w, h = ocr.image_width, ocr.image_height
        region_bboxes: Dict[str, List[BBox]] = {k: [] for k in self.REGIONS}

        for bbox in ocr.bboxes:
            for region_name, bounds in self.REGIONS.items():
                x1 = bounds["xr"][0] * w
                x2 = bounds["xr"][1] * w
                y1 = bounds["yr"][0] * h
                y2 = bounds["yr"][1] * h
                if x1 <= bbox.center_x <= x2 and y1 <= bbox.center_y <= y2:
                    region_bboxes[region_name].append(bbox)

        result: Dict[str, str] = {}
        for region_name, rbboxes in region_bboxes.items():
            # 읽기 순서(위→아래, 좌→우)로 정렬 후 라인 단위 텍스트 생성
            rbboxes_sorted = sorted(rbboxes, key=lambda b: (b.center_y, b.x_min))
            sub_lines = self._build_lines(rbboxes_sorted)
            result[region_name] = "\n".join(
                " ".join(b.text for b in ln) for ln in sub_lines
            )
        return result

    # ─── 3단계: 필드 매핑 ───────────────────────────────────────

    def _map_fields(
        self,
        regions: Dict[str, str],
        ocr: OCRResult,
        lines: List[List[BBox]],
    ) -> BLFields:
        f = BLFields(raw_regions=regions)

        # ── B/L No. ──────────────────────────────────────────────
        bl_no_text = regions.get("bl_no", "") + " " + regions.get("header", "")
        bl_matches = self.RE_BL_NO.findall(bl_no_text)
        # "DLSU...", "K...", "T...", "P...", "W...", "G...", "S..." 같은
        # 화물 식별 코드와 구분: 앞글자 2자 이상 알파벳 + 6자리 이상 숫자 제외
        for m in bl_matches:
            if len(m) <= 12 and not m.startswith("DLSU"):
                f.bl_no = m
                break
        # anchor fallback: B/L NO 라벨 근처에서 탐색
        if not f.bl_no:
            anchor_text = self._find_by_anchor(
                "bl_no", ocr.bboxes, ocr.image_width, ocr.image_height
            )
            if anchor_text:
                m_list = self.RE_BL_NO.findall(anchor_text)
                for m in m_list:
                    if len(m) <= 12 and not m.startswith("DLSU"):
                        f.bl_no = m
                        break

        # ── Shipper ──────────────────────────────────────────────
        f.shipper = self._clean_party_name(regions.get("shipper", ""))
        if not f.shipper:
            anchor_text = self._find_by_anchor(
                "shipper", ocr.bboxes, ocr.image_width, ocr.image_height
            )
            if anchor_text:
                f.shipper = self._clean_party_name(anchor_text) or anchor_text.strip()[:150]

        # ── Consignee ────────────────────────────────────────────
        f.consignee = self._clean_party_name(regions.get("consignee", ""))

        # ── Notify Party ─────────────────────────────────────────
        f.notify_party = self._clean_party_name(regions.get("notify", ""))

        # ── Vessel / Voyage ──────────────────────────────────────
        vessel_text = regions.get("vessel_info", "")
        f.vessel, f.voyage_no = self._extract_vessel_voyage(vessel_text)

        # ── Port of Loading ──────────────────────────────────────
        pol_raw = regions.get("port_left", "")
        f.port_of_loading = self._clean_port_name(pol_raw) if pol_raw.strip() else None
        if not f.port_of_loading:
            f.port_of_loading = self._find_by_anchor(
                "port_of_loading", ocr.bboxes, ocr.image_width, ocr.image_height
            )

        # ── Port of Discharge ────────────────────────────────────
        pod_raw = regions.get("port_right", "")
        f.port_of_discharge = self._clean_port_name(pod_raw) if pod_raw.strip() else None
        if not f.port_of_discharge:
            f.port_of_discharge = self._find_by_anchor(
                "port_of_discharge", ocr.bboxes, ocr.image_width, ocr.image_height
            )

        # ── Description of Goods ─────────────────────────────────
        f.description_of_goods = self._extract_description(
            regions.get("cargo", "")
        )

        # ── Gross Weight (TOTAL 라인에서 추출) ───────────────────
        weight_text = regions.get("weight", "")
        # TOTAL 라인 우선, 없으면 weight 구역 전체
        f.gross_weight = self._extract_total_weight(
            regions.get("cargo", "") + "\n" + weight_text
        )

        # ── Measurement (TOTAL 라인에서 추출) ────────────────────
        cbm_text = regions.get("measurement", "")
        f.measurement = self._extract_total_cbm(
            regions.get("cargo", "") + "\n" + cbm_text
        )

        # ── Dates ────────────────────────────────────────────────
        footer_text = regions.get("footer", "")
        freight_text = regions.get("freight", "")
        all_dates_footer = [d for d in self.RE_DATE.findall(footer_text) if _is_valid_date_str(d)]
        all_dates_freight = [d for d in self.RE_DATE.findall(freight_text) if _is_valid_date_str(d)]

        # 발행일: footer 구역의 가장 마지막(하단) 날짜
        if all_dates_footer:
            f.date_of_issue = all_dates_footer[-1]
        # 선적일(On Board): freight/footer 영역의 첫 날짜 또는 두 번째 날짜
        all_dates = all_dates_freight + all_dates_footer
        if len(all_dates) >= 2 and not f.on_board_date:
            f.on_board_date = all_dates[0]
        elif all_dates and not f.date_of_issue:
            f.date_of_issue = all_dates[0]

        # 키워드 앵커로 날짜 재시도 (구역 추출 실패 시)
        if not f.date_of_issue:
            f.date_of_issue = self._find_date_by_anchor(
                "date_of_issue", ocr.bboxes, ocr.image_width, ocr.image_height
            )
        if not f.on_board_date:
            f.on_board_date = self._find_date_by_anchor(
                "on_board_date", ocr.bboxes, ocr.image_width, ocr.image_height
            )

        # ── Place of Issue ───────────────────────────────────────
        f.place_of_issue = self._extract_place_of_issue(footer_text)

        # ── Total Freight ────────────────────────────────────────
        amt_match = self.RE_AMOUNT.search(freight_text)
        if amt_match:
            f.total_freight = f"${amt_match.group(1)}"

        return f

    # ─── 키워드 앵커 fallback ────────────────────────────────────

    def _find_by_anchor(
        self,
        field_name: str,
        bboxes: List[BBox],
        img_w: float,
        img_h: float,
    ) -> Optional[str]:
        """
        필드 라벨 키워드를 찾아 그 오른쪽/아래 텍스트를 수집.
        구역 기반 추출 실패 시 fallback으로 사용.
        """
        candidates = self.FIELD_ANCHORS.get(field_name, [])
        anchor = None
        anchor_y = None

        # 같은 y 레벨의 bbox들을 라인 단위로 구성
        for bbox in bboxes:
            normalized = re.sub(r"[^A-Z0-9/ ]", "", bbox.text.upper()).strip()
            for cand in candidates:
                cand_norm = re.sub(r"[^A-Z0-9/ ]", "", cand.upper()).strip()
                if cand_norm == normalized or cand_norm in normalized:
                    anchor = bbox
                    anchor_y = bbox.center_y
                    break
            if anchor:
                break

        if not anchor:
            return None

        # 앵커 오른쪽 또는 바로 아래 bbox 텍스트 수집
        line_height = max(anchor.y_max - anchor.y_min, 20)
        value_bboxes = [
            b for b in bboxes
            if (
                # 같은 라인, 오른쪽
                (abs(b.center_y - anchor_y) <= line_height * 0.7
                 and b.x_min > anchor.x_max)
                or
                # 바로 아래 한 줄
                (anchor_y + line_height * 0.3 < b.center_y < anchor_y + line_height * 2.5
                 and anchor.x_min - line_height <= b.x_min <= anchor.x_max + line_height * 4)
            )
        ]
        if not value_bboxes:
            return None

        value_bboxes.sort(key=lambda b: (b.center_y, b.x_min))
        text = " ".join(b.text for b in value_bboxes[:10])

        if field_name in ("port_of_loading", "port_of_discharge"):
            return self._clean_port_name(text)
        return text.strip() or None

    def _find_date_by_anchor(
        self,
        field_name: str,
        bboxes: List[BBox],
        img_w: float,
        img_h: float,
    ) -> Optional[str]:
        """날짜 관련 앵커 키워드 근처에서 날짜 패턴 탐색"""
        candidates = self.FIELD_ANCHORS.get(field_name, [])
        anchor_y = None

        for bbox in bboxes:
            norm = re.sub(r"[^A-Z ]", "", bbox.text.upper()).strip()
            for cand in candidates:
                if cand.upper() in norm:
                    anchor_y = bbox.center_y
                    break
            if anchor_y:
                break

        # 앵커 근처 bbox에서 날짜 패턴 탐색
        search_bboxes = bboxes if anchor_y is None else [
            b for b in bboxes if abs(b.center_y - anchor_y) < 60
        ]
        text = " ".join(b.text for b in sorted(search_bboxes, key=lambda b: b.center_y))
        dates = [d for d in self.RE_DATE.findall(text) if _is_valid_date_str(d)]
        return dates[-1] if dates else None

    # ─── 필드별 post-processor ──────────────────────────────────

    def _clean_party_name(self, text: str) -> Optional[str]:
        """
        Shipper / Consignee / Notify Party 정제:
        - 전화·팩스 라인 제거
        - 주소 라인 이후 제거
        - 회사명(CO.,LTD.,INC.,CORP.) 포함 첫 줄 반환
        """
        if not text or not text.strip():
            return None

        # 연락처 라인 제거
        text = self.RE_CONTACT.sub("", text)
        lines = [ln.strip() for ln in re.split(r"\n|(?<=\.)\s{2,}", text) if ln.strip()]

        # 회사명이 포함된 첫 줄 찾기 (헤더 노이즈 라인 제외)
        for line in lines:
            if _is_header_noise(line):
                continue
            if re.search(r"CO\.|LTD\.|INC\.|CORP\.|LLC|GMBH|PTE\.|PVT\.", line, re.I):
                # 앞의 ID 코드 제거 (예: "HG290309 DHHJ FRANCHISING CO., LTD.")
                line = re.sub(r"^[A-Z]{2}\d{6,}\s+", "", line)
                cleaned = line.strip()
                if cleaned:
                    return cleaned[:150]

        # 회사명 패턴 없으면 헤더 노이즈를 제외한 첫 비공백 줄 반환
        for line in lines:
            if _is_header_noise(line):
                continue
            cleaned = re.sub(r"^[A-Z]{2}\d{6,}\s+", "", line).strip()
            if cleaned and len(cleaned) > 3:
                return cleaned[:150]
        return None

    def _clean_port_name(self, text: str) -> Optional[str]:
        """
        항구명 정제:
        - 라인별 처리: 콤마 있는 줄(CITY, COUNTRY) 우선 반환
        - 운송 유형 코드(CY/CFS/FCL/LCL) 제거
        - 서수 카운트 라인(ONE (1), TWO (2)) 제거
        - TOTAL/중량 라인 제거
        """
        if not text or not text.strip():
            return None

        candidates_with_comma: List[str] = []
        candidates_no_comma: List[str] = []

        for ln in text.split("\n"):
            stripped = ln.strip()
            if not stripped:
                continue
            # TOTAL/수량/중량 라인 스킵
            if re.match(r"^\s*(TOTAL|SAY|\d+\s*PKG|\d+\s*KG)", stripped, re.I):
                continue
            # 서수 카운트 라인 스킵 (ONE (1), TWO (2) → 원본 매수)
            if re.match(r"^(?:ONE|TWO|THREE|FOUR|FIVE|SIX)\s*\(\d+\)", stripped, re.I):
                continue

            # 운송 유형 코드 제거
            cleaned = self.RE_PORT_NOISE.sub("", stripped)
            # 중량/용적 숫자 제거
            cleaned = re.sub(r"\d[\d,\.]*\s*(?:KGS?|KG|CBM|M3)\b", "", cleaned, flags=re.I)
            # 연속 공백·콤마 정리
            cleaned = re.sub(r"\s+", " ", cleaned).strip().strip(",").strip()

            if not cleaned or len(cleaned) <= 2:
                continue

            if "," in cleaned:
                candidates_with_comma.append(cleaned)
            else:
                candidates_no_comma.append(cleaned)

        # 콤마 있는 후보(CITY, COUNTRY) 우선 → 없으면 첫 후보
        result = (candidates_with_comma or candidates_no_comma)
        return result[0][:80] if result else None

    def _extract_description(self, cargo_text: str) -> Optional[str]:
        """
        화물 명세 추출:
        - 화물 추적 코드(DLSU..., K536...) 제거
        - "TOTAL" 라인 이전까지
        - 수량/중량 라인에서 품목명만 추출
        """
        if not cargo_text.strip():
            return None

        goods_lines = []
        for ln in cargo_text.split("\n"):
            stripped = ln.strip()
            if not stripped:
                continue
            # TOTAL 라인 정지
            if re.match(r"^TOTAL\b", stripped, re.I):
                break
            # 화물 추적 코드 라인 제거 (예: "DLSU8179031", "K536400", "R577189")
            if re.match(r"^[A-Z]{1,4}\d{5,}\s*$", stripped, re.I):
                continue
            # 화물 추적 코드 접두어 제거 (예: "DLSU8179031 27 PKG CELL ASSEMBLY")
            stripped = re.sub(r"^[A-Z]{1,4}\d{5,}\s+", "", stripped)

            # 수량 라인에서 품목명 추출 (예: "27 PKG CELL ASSEMBLY, 259KG")
            if re.match(r"^\d+\s*(PKG|PCS|CTNS?|ROLLS?|SETS?|BAGS?|BUNDLES?)\b", stripped, re.I):
                item = re.sub(
                    r"^\d+\s*(?:PKG|PCS|CTNS?|ROLLS?|SETS?|BAGS?|BUNDLES?)\s+",
                    "", stripped, flags=re.I
                )
                # 끝에 붙은 중량/CBM 제거
                item = re.sub(r",?\s*\d[\d,.]*\s*(?:KGS?|KG|CBM|M3)\b.*$", "", item, flags=re.I)
                item = item.strip().rstrip(",")
                if item and len(item) > 2:
                    goods_lines.append(item)
            else:
                goods_lines.append(stripped)

        if not goods_lines:
            return None

        # 중복 제거하며 합치기
        seen: set = set()
        unique = []
        for g in goods_lines:
            key = g.upper()[:30]
            if key not in seen:
                seen.add(key)
                unique.append(g)

        result = " / ".join(unique)
        return result[:200] if result else None

    def _extract_total_weight(self, text: str) -> Optional[str]:
        """TOTAL 키워드 근처의 중량 우선 추출"""
        # TOTAL 라인에서 찾기
        for ln in text.split("\n"):
            if re.match(r"^TOTAL\b", ln.strip(), re.I):
                m = self.RE_WEIGHT.search(ln)
                if m:
                    return f"{m.group(1)} {m.group(2).upper()}"
        # TOTAL 없으면 마지막 중량 패턴
        matches = list(self.RE_WEIGHT.finditer(text))
        if matches:
            m = matches[-1]
            return f"{m.group(1)} {m.group(2).upper()}"
        return None

    def _extract_total_cbm(self, text: str) -> Optional[str]:
        """TOTAL 키워드 근처의 CBM 우선 추출"""
        for ln in text.split("\n"):
            if re.match(r"^TOTAL\b", ln.strip(), re.I):
                m = self.RE_CBM.search(ln)
                if m:
                    return f"{m.group(1)} CBM"
        matches = list(self.RE_CBM.finditer(text))
        if matches:
            m = matches[-1]
            return f"{m.group(1)} CBM"
        return None

    def _extract_vessel_voyage(self, text: str) -> Tuple[Optional[str], Optional[str]]:
        """선박명과 항차 번호를 분리 추출"""
        if not text.strip():
            return None, None

        # 운송 유형 코드 제거 (CFS/CY, CY/CY 등)
        text = self.RE_VESSEL_NOISE.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()

        # M/V, MV, VESSEL 등 접두어 이후
        m = re.search(
            r"(?:M/?V|S/?S|VESSEL|OCEAN\s+VESSEL)\s+([A-Z][A-Z\s\-\.]+?)(?:\s+V\.?\s*(\w+))?$",
            text.strip(), re.IGNORECASE | re.MULTILINE,
        )
        if m:
            vessel = m.group(1).strip()
            voyage = m.group(2)
            return vessel, voyage

        # 접두어 없는 경우: 첫 줄에서 "WORD WORD V.NNN" 패턴
        lines = [ln.strip() for ln in text.split("\n") if ln.strip()]
        if not lines:
            return None, None
        first_line = lines[0]
        voyage_m = re.search(r"\bV\.?(\w+)\b", first_line)
        voyage = voyage_m.group(0) if voyage_m else None
        vessel_words = first_line
        if voyage_m:
            vessel_words = first_line[:voyage_m.start()].strip()
        vessel = " ".join(vessel_words.split()[:4]) if vessel_words else None
        return vessel, voyage

    def _extract_place_of_issue(self, footer_text: str) -> Optional[str]:
        """발행지 추출: 날짜를 제외한 지명(대문자 단어)"""
        text = self.RE_DATE.sub("", footer_text)
        text = self.RE_CONTACT.sub("", text)
        text = re.sub(r"\s+", " ", text).strip()
        # 대문자 단어 시퀀스 추출
        place_m = re.search(r"([A-Z][A-Z\s,\.]+)", text)
        if place_m:
            place = place_m.group(1).strip().strip(",")
            if len(place) > 2:
                return place[:80]
        return None

    # ─── 디버그 ──────────────────────────────────────────────────

    def _print_debug(self, f: BLFields, regions: Dict[str, str]) -> None:
        print("\n[FieldParser DEBUG]")
        for key in f.to_dict():
            val = getattr(f, key)
            print(f"  {key:<25}: {str(val)[:70] if val else '─ 미추출'}")
        print()
