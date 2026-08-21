#!/usr/bin/env python3
"""하자 0건으로 통과하는 시연용 B/L·L/C 쌍을 만듭니다.

두 가지를 만듭니다:

    python docs/frontend/시연_녹화/make-clean-sample.py           # 통과 쌍
    python docs/frontend/시연_녹화/make-clean-sample.py --full     # 전조건 쌍

**통과 쌍**은 원본 L/C 의 조건을 거의 그대로 두고 날짜만 맞춘 것이라, L/C 가
말하지 않는 조건(통지처·중량 한도·용적 한도)은 검사되지 않은 채 남습니다.

**전조건 쌍**은 그 조건들을 L/C 에 실제로 적어 넣어 검사 대상으로 끌어올린
것입니다. 거래조건도 FOB 에서 CFR 로 바꿉니다 — 운임 지급 조건 검사(D026)는
매도인이 주운송비를 부담하는 조건일 때만 켜지기 때문입니다. 수하인도 지시식
으로 갑니다.

전조건 쌍이라도 **미검사가 0 이 되지는 않습니다.** 구조적으로 세 건이 남습니다:

* 수하인 대조(D005B)와 지시식 검사(D027)는 서로 배타적입니다 — 지시식이면
  대조할 상호가 없습니다.
* 운임 금액(D017)은 MT700 에 적는 태그가 사실상 없습니다.
* 본선적재 부기(D030)는 수취식 B/L 일 때만 걸리는 검사인데, 통과하는 쌍은
  본선적재 선하증권이어야 합니다.

기존 샘플(샘플_B_L_SHP-2026-0812-001.pdf)은 발행일·발행지가 비어 있고 선적일이
한참 전이라 구조적으로 통과가 안 됩니다. 이 스크립트는 그 서식을 그대로 쓰되
**날짜만 실행일 기준으로 다시 잡아서** 전 항목 통과본을 만듭니다.

날짜를 박아 두지 않고 매번 만들어 쓰는 이유:
제시기간(D018)은 "선적일로부터 21일"이라 고정 날짜로 저장해 두면 3주 뒤에
같은 파일이 하자로 바뀝니다. 통과 사례는 촬영 당일에 다시 만드세요.

    pip install pymupdf
    python docs/frontend/시연_녹화/make-clean-sample.py

원본을 복사해서 바뀌는 값만 지우고 다시 씁니다. 서식을 새로 그리지 않는 건
파서가 이 서식의 좌표에 맞춰져 있기 때문입니다 — 새로 그리면 값이 밀립니다.
"""

from __future__ import annotations

import datetime as dt
import re
import sys
from pathlib import Path

import pymupdf

FULL = "--full" in sys.argv

DOCS = Path(__file__).resolve().parent.parent
SRC_PDF = DOCS / "샘플_B_L_SHP-2026-0812-001.pdf"
SRC_LC = DOCS / "샘플_L_C_MT700_SHP-2026-0812-001.txt"
OUT_PDF = DOCS / ("샘플_전조건_B_L.pdf" if FULL else "샘플_통과_B_L.pdf")
OUT_LC = DOCS / ("샘플_전조건_L_C_MT700.txt" if FULL else "샘플_통과_L_C_MT700.txt")

# 기존 샘플과 번호가 겹치면 안 됩니다. B/L 번호는 테넌트당 하나뿐이라,
# 겹치면 나중에 올린 쪽 대시보드 B/L 칸이 빈칸으로 찍힙니다.
BL_NO = "HLCUBUS2608888" if FULL else "HLCUBUS2608777"
LC_NO = "LC26082000888" if FULL else "LC26082000777"
PLACE_OF_ISSUE = "BUSAN, KOREA"
CONSIGNEE = "NORDWIND HANDELS GMBH"   # 서식에 인쇄된 수하인. 아래 :46A: 를 여기 맞춥니다
NOTIFY = "SCHENKER AG HAMBURG"        # 전조건 쌍에서만 씁니다
# 한도는 서식에 인쇄된 실제 값(12,480 KGS · 38.5 CBM)보다 조금 위로 잡습니다.
# 통과하는 쌍이어야 하므로 아슬아슬하게 걸치지 않게 여유를 둡니다.
MAX_WEIGHT_KGS = 13000
MAX_CBM = 40

today = dt.date.today()
on_board = today - dt.timedelta(days=3)      # 제시기간 21일 안 (D018)
date_of_issue = on_board                     # 미래 발행일 아님 (D019)
latest_shipment = today + dt.timedelta(days=10)   # 선적기한 여유 (D002)
lc_issue = today - dt.timedelta(days=20)
expiry = today + dt.timedelta(days=60)       # 유효기간 여유 (D008)


def swift(d: dt.date) -> str:
    return d.strftime("%y%m%d")


# ── B/L PDF ───────────────────────────────────────────────────
doc = pymupdf.open(SRC_PDF)
page = doc[0]

# 지우고 다시 쓸 값들. 좌표를 손으로 적지 않고 원문을 찾아 그 자리에 씁니다.
replacements = {
    "HLCUBUS2608001": BL_NO,
    "LC26081200123": LC_NO,
    "2026-07-14": on_board.isoformat(),
}
if FULL:
    # 지시식 수하인 + L/C 가 지정한 통지처 + CFR. 셋 다 L/C 쪽과 짝을 맞춥니다.
    replacements.update({
        CONSIGNEE: "TO ORDER OF SHIPPER",
        "SAME AS CONSIGNEE": NOTIFY,
        "FOB BUSAN": "CFR HAMBURG",
    })
def baseline_of(rect: pymupdf.Rect) -> float:
    """원문 글자의 기준선(baseline)을 읽습니다.

    `insert_text` 가 받는 y 는 글자 상자의 아래가 아니라 기준선입니다.
    `rect.y1 - 1.6` 처럼 어림잡으면 1pt 남짓 밀리는데, **그 정도만 밀려도
    파서가 깨집니다** — `field_parser._build_lines` 가 세로 간격으로 줄을
    묶어서, 밀린 값이 서식의 아랫줄과 한 줄로 합쳐지고 수하인이 통째로
    사라집니다. 지우기 전에 원문 기준선을 그대로 받아 씁니다.
    """
    # 겹치는 span 중 **겹침이 가장 큰** 것을 고릅니다. 서식의 항목명 칸과
    # 값 칸은 1pt 남짓 겹쳐 있어서, 먼저 만난 span 을 그냥 쓰면 값 자리에
    # 항목명의 기준선이 들어가 값이 한 줄 위로 올라앉습니다.
    best, best_area = None, 0.0
    for blk in page.get_text("dict")["blocks"]:
        for line in blk.get("lines", []):
            for span in line["spans"]:
                overlap = pymupdf.Rect(span["bbox"]) & rect
                area = overlap.get_area() if not overlap.is_empty else 0.0
                if area > best_area:
                    best, best_area = span, area
    if best is None:
        sys.exit(f"{rect} 자리의 원문 기준선을 못 읽었습니다.")
    return best["origin"][1]


targets = []
for old, new in replacements.items():
    hits = page.search_for(old)
    if not hits:
        sys.exit(f"원본에서 {old} 를 못 찾았습니다. 샘플 서식이 바뀌었습니다.")
    for rect in hits:
        targets.append((rect, new, baseline_of(rect)))
        page.add_redact_annot(rect)

# 안내 문구도 손댑니다 — 원본은 다른 픽스처를 가리킵니다.
for rect in page.search_for("SHP-2026-0812-001)"):
    targets.append((rect, "clean-pass sample)", baseline_of(rect)))
    page.add_redact_annot(rect)

# 글자만 지웁니다. 기본값으로 지우면 서식의 괘선까지 같이 날아갑니다.
page.apply_redactions(graphics=pymupdf.PDF_REDACT_LINE_ART_NONE)

for rect, text, base_y in targets:
    size = 7.5 if text.endswith("sample)") else 9.5
    font = "helv" if text.endswith("sample)") else "hebo"
    page.insert_text((rect.x0, base_y), text, fontsize=size, fontname=font)

# 원본에서 비어 있던 "Place and Date of Issue" 칸을 채웁니다.
# 이 칸이 비어 있는 게 D021(발행지 누락)·D022(발행일 누락)의 원인이었습니다.
label = page.search_for("Place and Date of Issue")
if not label:
    sys.exit("발행지·발행일 칸을 못 찾았습니다.")
box = label[0]
page.insert_text(
    (box.x0, box.y1 + 10.2),
    f"{PLACE_OF_ISSUE}   {date_of_issue.isoformat()}",
    fontsize=9.5,
    fontname="hebo",
)

doc.save(OUT_PDF, incremental=False, deflate=True)
doc.close()

# ── L/C (MT700) ───────────────────────────────────────────────
lc = SRC_LC.read_text()
for tag, value in {
    "20": LC_NO,
    "31C": swift(lc_issue),
    "31D": f"{swift(expiry)} HAMBURG",
    "44C": swift(latest_shipment),
}.items():
    lc, n = re.subn(rf"^:{tag}:.*$", f":{tag}:{value}", lc, count=1, flags=re.MULTILINE)
    if n != 1:
        sys.exit(f"L/C 에서 :{tag}: 를 못 바꿨습니다.")

def sub1(pattern: str, repl: str, text: str, what: str) -> str:
    text, n = re.subn(pattern, repl, text, count=1, flags=re.MULTILINE)
    if n != 1:
        sys.exit(f"L/C 에서 {what} 을(를) 못 바꿨습니다. 원본 서식이 바뀌었습니다.")
    return text


BL_LINE = r"^(\+FULL SET OF CLEAN ON BOARD OCEAN BILL OF LADING) MADE OUT TO ORDER$"

if FULL:
    # 지시식 + 통지처 지정. 통지처를 46A 의 선하증권 항목에 붙이는 것이 실무
    # 표기입니다 — MT700 에는 통지처 전용 태그가 없습니다.
    lc = sub1(BL_LINE,
              rf"\1 MADE OUT TO ORDER AND BLANK ENDORSED NOTIFY {NOTIFY}",
              lc, "선하증권 수하인·통지처 지정 문구")
    # 거래조건을 CFR 로 올리고 중량·용적 한도를 명시합니다. 47A 자유서식이
    # 이 조건들이 실제로 실리는 자리입니다.
    # 47A 는 태그가 첫 줄에 붙어 있습니다(`:47A:+SHIPMENT...`) — 46A 의 이어지는
    # 줄과 달리 접두를 살려 둬야 합니다.
    lc = sub1(r"^(:47A:)\+SHIPMENT OF 480 CARTONS ON FOB BUSAN BASIS, INCOTERMS 2020$",
              r"\1" + "+SHIPMENT OF 480 CARTONS ON CFR HAMBURG BASIS, INCOTERMS 2020\n"
              f"+GROSS WEIGHT NOT TO EXCEED {MAX_WEIGHT_KGS:,} KGS\n"
              f"+MEASUREMENT NOT TO EXCEED {MAX_CBM} CBM",
              lc, "거래조건·중량·용적 한도")
else:
    # 서식의 수하인 칸은 상호가 인쇄된 기명식인데 원본 L/C 는 지시식(MADE OUT
    # TO ORDER)을 요구합니다. 그대로 두면 지시식/기명식 저촉이 치명 하자로
    # 잡혀 통과본이 안 됩니다. 서류를 고치지 않고 L/C 를 서류에 맞추는 이유는
    # 서식의 좌표를 건드리면 파서가 값을 놓치기 때문입니다. 덤으로 수하인
    # 상호 대조가 미검사에서 검사 대상으로 올라옵니다.
    lc = sub1(BL_LINE, rf"\1 CONSIGNED TO {CONSIGNEE}", lc, "선하증권 수하인 지정 문구")

OUT_LC.write_text(lc)

print(f"{OUT_PDF.name}  B/L {BL_NO} · 선적 {on_board} · 발행 {date_of_issue} {PLACE_OF_ISSUE}")
print(f"{OUT_LC.name}  L/C {LC_NO} · 선적기한 {latest_shipment} · 유효기간 {expiry}")
if FULL:
    print(f"  전조건: 지시식 · 통지처 {NOTIFY} · CFR HAMBURG · "
          f"중량 {MAX_WEIGHT_KGS:,} KGS · 용적 {MAX_CBM} CBM")
