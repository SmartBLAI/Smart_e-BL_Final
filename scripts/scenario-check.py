#!/usr/bin/env python3
"""시나리오 점검. 실무 하자 사유를 하나씩 넣어 보고 엔진이 무엇을 놓치는지 본다.

expect  : 이 규칙들이 위반으로 나와야 한다
forbid  : 이 규칙들이 나오면 오탐이다
gap     : UCP 600 상 은행이 거절하는 사유인데 대응 규칙이 있는지 확인하려는 것.
          아무것도 안 나오면 '기능 없음'으로 보고한다.

사용법:
    ./scripts/demo-check.sh 로 서비스가 떠 있는지 먼저 확인하고
    python scripts/scenario-check.py

종료 코드는 보지 않는다 -- 구멍 목록을 사람이 읽고 판단하는 도구다.
"""
import json, os, urllib.request, datetime as dt

URL = os.environ.get("AI", "http://127.0.0.1:5050") + "/verify"
TOK = "changeme-internal-token"
today = dt.date.today()
D = lambda n: (today + dt.timedelta(days=n)).isoformat()

# 전 항목 통과하는 기준 서류. 시나리오는 여기서 한 군데씩만 비튼다.
BL = dict(
    bl_no="HLCUBUS2608777", shipper="HANKOOK PRECISION CO., LTD.",
    consignee="NORDWIND HANDELS GMBH", notify_party="SAME AS CONSIGNEE",
    vessel="HMM ALGECIRAS", voyage_no="0125E",
    port_of_loading="BUSAN, KOREA", port_of_discharge="HAMBURG, GERMANY",
    description_of_goods="PRECISION MACHINE PARTS (HS 8471.30)",
    gross_weight="12,480 KGS", measurement="38.5 CBM",
    date_of_issue=D(-3), place_of_issue="BUSAN, KOREA",
    on_board_date=D(-3), total_freight="USD 3,200.00",
    no_of_original_bl="THREE (3)",
)
LC = dict(
    lc_no="LC26082000777", currency_amount="USD125000,00",
    expiry_date=D(60), latest_shipment_date=D(10),
    port_of_loading="BUSAN, KOREA", port_of_discharge="HAMBURG, GERMANY",
    description_of_goods="PRECISION MACHINE PARTS", applicant="NORDWIND HANDELS GMBH",
    beneficiary="HANKOOK PRECISION CO.,LTD", consignee="NORDWIND HANDELS GMBH",
    partial_shipment="PROHIBITED", transhipment="PROHIBITED",
    documents_required=[
        "SIGNED COMMERCIAL INVOICE IN TRIPLICATE",
        "FULL SET OF CLEAN ON BOARD OCEAN BILL OF LADING CONSIGNED TO NORDWIND HANDELS GMBH",
        "PACKING LIST IN TRIPLICATE",
    ],
    presentation_days=21,
)

def S(name, ucp, bl=None, lc=None, expect=(), forbid=(), gap=False):
    return dict(name=name, ucp=ucp, bl={**BL, **(bl or {})},
                lc={**LC, **(lc or {})}, expect=set(expect), forbid=set(forbid), gap=gap)

SCEN = [
  # ── A. 기준선 ──────────────────────────────────────────────
  S("정상 서류 (오탐 없어야 함)", "—", forbid=["*"]),

  # ── B. 잡혀야 하는 것 ──────────────────────────────────────
  S("선적항 불일치", "UCP 600 Art.20(a)(iii)", bl={"port_of_loading":"INCHEON, KOREA"}, expect=["D003"]),
  S("양하항 불일치", "UCP 600 Art.20(a)(iii)", bl={"port_of_discharge":"ROTTERDAM"}, expect=["D004"]),
  S("수하인 불일치", "UCP 600 Art.14(d)", bl={"consignee":"ACME TRADING LLC"}, expect=["D005B"]),
  S("선적기한 초과", "UCP 600 Art.6(d)", bl={"on_board_date":D(20)}, lc={"latest_shipment_date":D(5)}, expect=["D002"]),
  S("유효기간 경과 (발행일도 기간 밖)", "UCP 600 Art.6(d)",
    bl={"date_of_issue":D(-3)}, lc={"expiry_date":D(-5)}, expect=["D008"]),
  S("제시기간 21일 경과", "UCP 600 Art.14(c)", bl={"on_board_date":D(-40),"date_of_issue":D(-40)}, expect=["D018"]),
  S("발행일이 미래", "ISBP 821", bl={"date_of_issue":D(5)}, expect=["D019"]),
  S("발행지 누락", "UCP 600 Art.20", bl={"place_of_issue":None}, expect=["D021"]),
  S("발행일 누락", "UCP 600 Art.20(a)(ii)", bl={"date_of_issue":None}, expect=["D022"]),
  S("고장 문언", "UCP 600 Art.27", bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - 3 CARTONS DAMAGED, TORN"}, expect=["D023"]),
  S("예정 선박", "UCP 600 Art.20(a)(ii)", bl={"vessel":"INTENDED VESSEL HMM ALGECIRAS"}, expect=["D024"]),
  S("항구 미특정", "UCP 600 Art.20(a)(iii)", bl={"port_of_discharge":"EUROPEAN MAIN PORT"}, expect=["D025"]),
  S("분할선적 금지 위반", "UCP 600 Art.31(a)", bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - PARTIAL SHIPMENT 1 OF 2"}, expect=["D013"]),
  S("환적 금지 위반", "UCP 600 Art.20(c)", bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - TRANSHIPMENT AT SINGAPORE"}, expect=["D014"]),
  S("선박명 누락", "UCP 600 Art.20(a)(ii)", bl={"vessel":None}, expect=["D011"]),
  S("통지처 불일치", "UCP 600 Art.14(d)", lc={"notify_party":"SCHENKER AG HAMBURG"}, expect=["D020"]),
  S("화물 명세 불일치", "UCP 600 Art.14(e)", bl={"description_of_goods":"FROZEN SEAFOOD"}, expect=["D006"]),
  S("중량 한도 초과", "L/C 조건", lc={"max_gross_weight_kg":10000}, expect=["D007"]),

  S("B/L 번호 누락", "UCP 600 Art.20", bl={"bl_no":None}, expect=["D001"]),
  S("수하인 누락", "UCP 600 Art.20", bl={"consignee":None}, expect=["D005"]),
  S("선적항 누락", "UCP 600 Art.20(a)(iii)", bl={"port_of_loading":None}, expect=["D012"]),
  S("양하항 누락", "UCP 600 Art.20(a)(iii)", bl={"port_of_discharge":None}, expect=["D012B"]),
  S("송하인 누락", "ISBP 821", bl={"shipper":None}, expect=["D009"]),
  S("통지처 누락 (L/C 지정 있음)", "UCP 600 Art.14(d)",
    bl={"notify_party":None}, lc={"notify_party":"SCHENKER AG HAMBURG"}, expect=["D010"]),
  S("용적 한도 초과", "L/C 조건", lc={"max_measurement_cbm":30.0}, expect=["D007B"]),
  S("운임 허용범위 이탈", "L/C 조건",
    bl={"total_freight":"USD 9,900.00"}, lc={"freight_amount":3200.0}, expect=["D017"]),
  S("Incoterms 미표시", "ISBP 821 A.19", lc={"incoterms":"CFR"}, expect=["D015"]),
  S("46A 요구서류에 B/L 없음", "UCP 600 Art.14",
    lc={"documents_required":["SIGNED COMMERCIAL INVOICE IN TRIPLICATE","PACKING LIST"]}, expect=["D016"]),
  S("운임 지급 조건 저촉 (CFR인데 운임 후불)", "ISBP 821 E",
    bl={"total_freight":"FREIGHT COLLECT"}, lc={"incoterms":"CFR"}, expect=["D026"]),

  # ── C. 구멍 탐지: 은행이 실제로 거절하는데 규칙이 있나? ──────
  S("용선계약 선하증권", "UCP 600 Art.20(a)(vi) — 용선계약 종속 표시는 수리 거절",
    bl={"bl_clauses":"SUBJECT TO CHARTER PARTY DATED 2026-07-01"}, expect=["D028"]),
  S("갑판적재", "UCP 600 Art.26(b) — 갑판적재 표시 선하증권은 수리 불가",
    bl={"bl_clauses":"GOODS SHIPPED ON DECK"}, expect=["D029"]),
  S("원본 통수 미표시", "UCP 600 Art.20(a)(iv)",
    bl={"no_of_original_bl":None}, expect=["D032"]),
  S("지시식 요구인데 기명식 수하인", "UCP 600 Art.20 / 유통성 결여",
    lc={"bl_consignment":"TO_ORDER", "consignee":None}, expect=["D027"]),
  S("[함정] 지시식 요구 + 지시식 B/L", "UCP 600 Art.20",
    bl={"consignee":"TO ORDER OF SHIPPER"},
    lc={"bl_consignment":"TO_ORDER", "consignee":None}, forbid=["D027"]),
  S("[함정] 지시식 요구인데 수하인 공란", "값 없음은 D005 소관 — 같은 사실로 두 번 잡으면 안 된다",
    bl={"consignee":None}, lc={"bl_consignment":"TO_ORDER", "consignee":None},
    expect=["D005"], forbid=["D027"]),
  S("운송인 명칭·서명 자격 미표시", "UCP 600 Art.20(a)(i) (의도적 미구현)",
    bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - SIGNED WITHOUT STATED CAPACITY"}, gap=True),
  S("수취선하증권에 본선적재 부기 없음", "UCP 600 Art.20(a)(ii)",
    bl={"bl_clauses":"RECEIVED FOR SHIPMENT IN APPARENT GOOD ORDER AND CONDITION", "on_board_date":None}, expect=["D030"]),
  S("정정 미인증", "UCP 600 Art.20 / ISBP 821 A",
    bl={"bl_clauses":"QUANTITY ALTERED FROM 100 TO 120 CARTONS"}, expect=["D031"]),
  S("포장 수량 불일치 (L/C 480 CARTONS)", "UCP 600 Art.14(d)",
    bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - 300 CARTONS"},
    lc={"description_of_goods":"PRECISION MACHINE PARTS, 480 CARTONS"}, gap=True),
  S("유효기간 지난 뒤 제시 (발행일은 기간 안)", "UCP 600 Art.6(d)·14(a) — 유효기일 판단 기준은 제시일이다",
    bl={"date_of_issue":D(-10)}, lc={"expiry_date":D(-1)}, expect=["D008"]),
  S("Incoterms FOB 인데 운임 선불", "ISBP 821 E",
    bl={"total_freight":"FREIGHT PREPAID USD 3,200.00"}, lc={"incoterms":"FOB"}, gap=True),

  # ── D. 오탐 함정: UCP 상 수리 가능한데 하자로 잡으면 안 되는 것 ──
  S("[함정] SAID TO CONTAIN", "UCP 600 Art.26(a) — 수리 가능",
    bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - SAID BY SHIPPER TO CONTAIN"}, forbid=["*"]),
  S("[함정] 약식 선하증권", "UCP 600 Art.20(a)(v) — 수리 가능",
    bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - SHORT FORM / BLANK BACK"}, forbid=["*"]),
  S("[함정] 갑판적재 가능성 문언", "UCP 600 Art.26(b) — 'MAY BE CARRIED ON DECK' 는 수리 가능",
    bl={"bl_clauses":"GOODS MAY BE CARRIED ON DECK"}, forbid=["*"]),
  S("[함정] 환적 허용인데 환적 표기", "UCP 600 Art.20(c)",
    bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - TRANSHIPMENT AT SINGAPORE"},
    lc={"transhipment":"ALLOWED"}, forbid=["D014"]),
  S("[함정] L/C 침묵 시 분할선적", "UCP 600 Art.31(a) — 침묵이면 허용",
    bl={"description_of_goods":"PRECISION MACHINE PARTS (HS 8471.30) - PARTIAL SHIPMENT 1 OF 2"},
    lc={"partial_shipment":"ALLOWED"}, forbid=["D013"]),
]

def call(bl, lc):
    body = json.dumps({"bl":bl, "lc":lc}).encode()
    req = urllib.request.Request(URL, body, {"Content-Type":"application/json","X-Internal-Token":TOK})
    return json.load(urllib.request.urlopen(req, timeout=60))["verdict"]

rows, gaps, fails = [], [], []
for s in SCEN:
    v = call(s["bl"], s["lc"])
    got = {x["rule_id"] for x in v["violations"]}
    miss = s["expect"] - got
    extra = (got if "*" in s["forbid"] else got & s["forbid"]) - s["expect"]
    if s["gap"]:
        status = "잡음" if got else "기능없음"
        (gaps if not got else rows).append((s, got, status))
    else:
        status = "OK" if not miss and not extra else "실패"
        if status == "실패": fails.append((s, got, miss, extra))
    print(f"{status:6} {s['name']:38} 위반={sorted(got) or '없음'}  "
          f"평가{v['evaluated_count']}/미검사{v['skipped_count']}")

covered = set()
for sc in SCEN: covered |= sc["expect"]
import urllib.request as _u
_r = _u.Request(os.environ.get("AI","http://127.0.0.1:5050")+"/rules", headers={"X-Internal-Token":TOK})
allids = {r["id"] for r in json.load(_u.urlopen(_r))["rules"]}
print("\n" + "="*70)
print(f"규칙 커버리지 {len(covered)}/{len(allids)}  미커버={sorted(allids-covered) or '없음'}")
print(f"기능 없음 {len(gaps)}건 / 규칙 실패 {len(fails)}건")
for s,_,_ in gaps: print(f"  [구멍] {s['name']}  ← {s['ucp']}")
for s,got,miss,extra in fails:
    print(f"  [실패] {s['name']}  누락={sorted(miss)} 오탐={sorted(extra)}")
