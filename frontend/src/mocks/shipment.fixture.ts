/**
 * B/L Copilot — 목 픽스처 (선적 1건)
 *
 * 백엔드 없이 S2·S3·S4·S5·S6을 개발하기 위한 고정 데이터.
 * 신뢰도 4등급·충돌 필드·판정 3심각도·교정 제안·현실 대조 이벤트를 모두 포함합니다.
 *
 * 규약: FE 개발규약 v0.2 §6.1
 */

import type {
  Shipment,
  ShipmentStatus,
  DocumentMeta,
  FieldValue,
  Suggestion,
  Verdict,
  DefectPrediction,
  ImpactItem,
  ImpactResult,
  RealityEvent,
  Alert,
  AdapterStatus,
  VesselMatch,
  RealityRuleStatus,
  Explanation,
} from '../types/domain';

// ─────────────────────────────────────────────
// 선적
// ─────────────────────────────────────────────

export const mockShipment: Shipment = {
  shipment_id: 'SHP-2026-0812-001',
  status: 'REVIEWING',
  bl_no: 'HLCUBUS2608001',
  cargo_control_no: '26KRPUS0001234',
  lc_no: 'LC26081200123',
  created_at: '2026-08-10T02:14:00Z',
  updated_at: '2026-08-12T01:30:00Z',
  lc_expiry_date: '2026-09-05',
};

// S1 대시보드에서 여러 건이 동시에 보일 때 StatusBadge 색이 섞여 보이도록
// 상태를 다르게 준 선적 3건.
//
// 이 3건의 판정·필드·하자확률은 shipmentData.ts에서 선적별로 따로 묶습니다.
// S4·S7은 URL의 :id로 그 묶음을 찾아 쓰므로, 카드마다 다른 결과가 나옵니다.
// (S3 초안 편집기·S5 타임라인은 아직 mockShipment 것을 그대로 씁니다)
export const mockShipmentDraft: Shipment = {
  shipment_id: 'SHP-2026-0813-002',
  status: 'DRAFT',
  bl_no: null,
  cargo_control_no: null,
  lc_no: 'LC26081300456',
  created_at: '2026-08-13T06:20:00Z',
  updated_at: '2026-08-13T06:20:00Z',
  lc_expiry_date: '2026-09-20',
};

export const mockShipmentVerified: Shipment = {
  shipment_id: 'SHP-2026-0809-003',
  status: 'VERIFIED',
  bl_no: 'MSCUBUS2608077',
  cargo_control_no: '26KRPUS0009981',
  lc_no: 'LC26080900789',
  created_at: '2026-08-05T01:10:00Z',
  updated_at: '2026-08-09T09:45:00Z',
  lc_expiry_date: '2026-08-30',
};

export const mockShipmentSubmitted: Shipment = {
  shipment_id: 'SHP-2026-0801-004',
  status: 'SUBMITTED',
  bl_no: 'ONEYBUS2607512',
  cargo_control_no: '26KRPUS0007765',
  lc_no: 'LC26072800321',
  created_at: '2026-07-28T03:40:00Z',
  updated_at: '2026-08-01T07:15:00Z',
  lc_expiry_date: '2026-08-15',
};

// ─────────────────────────────────────────────
// 업로드 서류
// ─────────────────────────────────────────────

export const mockDocuments: DocumentMeta[] = [
  {
    document_id: 'DOC-001',
    kind: 'SI',
    file_name: 'SI_20260810.pdf',
    file_hash: 'a3f1c9e2b7',
    page_count: 2,
    version: 1,
    uploaded_at: '2026-08-10T02:14:00Z',
  },
  {
    document_id: 'DOC-002',
    kind: 'LC',
    file_name: 'MT700_LC26081200123.txt',
    file_hash: 'd8b4a1f60c',
    page_count: 1,
    version: 1,
    uploaded_at: '2026-08-10T02:15:00Z',
  },
  {
    document_id: 'DOC-003',
    kind: 'INVOICE',
    file_name: 'CommercialInvoice_scan.pdf',
    file_hash: '5e7c2d9a83',
    page_count: 1,
    version: 1,
    uploaded_at: '2026-08-10T02:15:30Z',
  },
  {
    document_id: 'DOC-004',
    kind: 'PACKING',
    file_name: 'PackingList_scan.pdf',
    file_hash: '9c1b6f4e27',
    page_count: 3,
    version: 1,
    uploaded_at: '2026-08-10T02:16:00Z',
  },
];

// ─────────────────────────────────────────────
// 추출 필드 26건
// 확정 15 · 확인 권고 7 · 필수 확인 2(충돌 1 포함) · 미검출 2
// ─────────────────────────────────────────────

const f = (
  field_name: string,
  value: string | null,
  confidence: number,
  source_doc_id: string | null,
  page: number | null,
  bbox: [number, number, number, number] | null,
  extra: Partial<FieldValue> = {},
): FieldValue => ({
  field_name,
  value,
  normalized_value: value,
  confidence,
  source_doc_id,
  page,
  bbox,
  extractor: 'ocr+llm',
  conflict_flag: false,
  ...extra,
});

export const mockFields: FieldValue[] = [
  // ── 당사자 ──
  f('shipper', 'HANKOOK PRECISION CO.,LTD', 0.96, 'DOC-002', 1, [72, 118, 340, 136]),
  f('consignee', 'NORDWIND HANDELS GMBH', 0.94, 'DOC-002', 1, [72, 140, 352, 158]),
  f('notify_party', 'SAME AS CONSIGNEE', 0.91, 'DOC-001', 1, [72, 162, 268, 180]),
  f('carrier', 'HAPAG-LLOYD', 0.88, 'DOC-001', 1, [72, 184, 220, 202]),

  // ── 식별번호 ──
  f('bl_no', 'HLCUBUS2608001', 0.97, 'DOC-001', 1, [420, 96, 596, 114]),
  f('booking_no', 'BKG26080455', 0.95, 'DOC-001', 1, [420, 118, 580, 136]),
  f('lc_no', 'LC26081200123', 0.98, 'DOC-002', 1, [72, 60, 268, 78], { extractor: 'rule' }),
  f('cargo_control_no', '26KRPUS0001234', 0.93, 'DOC-001', 1, [420, 140, 612, 158]),

  // ── 운송구간 ──
  f('place_of_receipt', 'BUSAN CY', 0.92, 'DOC-001', 1, [72, 228, 232, 246]),
  // ⚠ 충돌: L/C는 KRPUS, SI는 KRINC → conflict_flag
  f('port_of_loading', 'BUSAN', 0.64, 'DOC-002', 1, [72, 250, 232, 268], {
    normalized_value: 'KRPUS',
    conflict_flag: true,
    candidates: [
      f('port_of_loading', 'BUSAN', 0.9, 'DOC-002', 1, [72, 250, 232, 268], {
        normalized_value: 'KRPUS',
      }),
      f('port_of_loading', 'INCHEON', 0.71, 'DOC-001', 1, [72, 250, 240, 268], {
        normalized_value: 'KRINC',
      }),
    ],
  }),
  f('port_of_discharge', 'HAMBURG', 0.95, 'DOC-002', 1, [72, 272, 240, 290], {
    normalized_value: 'DEHAM',
  }),
  f('place_of_delivery', 'HAMBURG CY', 0.89, 'DOC-001', 1, [72, 294, 248, 312]),
  f('vessel_voyage', 'HMM ALGECIRAS / 2608E', 0.86, 'DOC-001', 1, [300, 228, 540, 246]),

  // ── 화물 ──
  f('marks_and_numbers', 'NWH-2608\\nHAMBURG\\nC/NO. 1-480', 0.82, 'DOC-004', 1, [64, 180, 300, 240]),
  f('no_of_packages', '480 CARTONS', 0.94, 'DOC-004', 1, [64, 250, 220, 268]),
  f('description_of_goods', 'PRECISION MACHINE PARTS', 0.9, 'DOC-003', 1, [64, 208, 340, 226]),
  f('hs_code', '8471.30', 0.87, 'DOC-003', 1, [400, 208, 520, 226]),
  f('gross_weight', '12,480 KGS', 0.93, 'DOC-004', 2, [64, 320, 200, 338], {
    normalized_value: '12480 KGM',
  }),
  // ⚠ 필수 확인: 저해상도 스캔
  f('measurement', '38.5 CBM', 0.58, 'DOC-004', 2, [220, 320, 340, 338], {
    normalized_value: '38.5 MTQ',
  }),

  // ── 컨테이너 ──
  f('container_no', 'MSKU 123456 5', 0.79, 'DOC-001', 2, [64, 400, 224, 418], {
    normalized_value: 'MSKU1234565',
  }),
  // ⚠ 미검출
  f('seal_no', null, 0, null, null, null, { extractor: 'ocr+llm' }),

  // ── 조건 · 발행 ──
  f('freight_terms', 'FREIGHT PREPAID', 0.96, 'DOC-002', 1, [400, 320, 580, 338]),
  f('incoterms', 'FOB BUSAN', 0.84, 'DOC-003', 1, [400, 250, 540, 268]),
  f('no_of_original_bl', 'THREE (3)', 0.91, 'DOC-002', 1, [400, 294, 540, 312]),
  f('shipped_on_board_date', '2026-07-14', 0.95, 'DOC-001', 1, [400, 430, 540, 448], {
    extractor: 'rule',
  }),
  // ⚠ 미검출
  f('place_and_date_of_issue', null, 0, null, null, null),
];

// ─────────────────────────────────────────────
// 교정 제안 3건 (§5.2)
// ─────────────────────────────────────────────

export const mockSuggestions: Suggestion[] = [
  {
    suggestion_id: 'SGT-001',
    field: 'port_of_discharge',
    as_is: 'HAMBURG',
    to_be: 'DEHAM (Hamburg)',
    authority: 'UN/LOCODE',
    glossary_term_id: 'LOC-DEHAM',
    confidence: 0.97,
    scope: [
      { doc_id: 'DOC-001', field: 'port_of_discharge' },
      { doc_id: 'DOC-002', field: 'port_of_discharge' },
      { doc_id: 'DOC-003', field: 'destination' },
    ],
  },
  {
    suggestion_id: 'SGT-002',
    field: 'gross_weight',
    as_is: 'KGS',
    to_be: 'KGM',
    authority: 'UN/ECE Rec 20',
    glossary_term_id: 'UOM-KGM',
    confidence: 0.99,
    scope: [
      { doc_id: 'DOC-001', field: 'gross_weight' },
      { doc_id: 'DOC-004', field: 'gross_weight' },
    ],
  },
  {
    suggestion_id: 'SGT-003',
    field: 'container_no',
    as_is: 'MSKU 123456 5',
    to_be: 'MSKU1234565',
    authority: 'ISO 6346',
    glossary_term_id: 'CTR-FORMAT',
    confidence: 1.0,
    scope: [{ doc_id: 'DOC-001', field: 'container_no' }],
  },
];

// ─────────────────────────────────────────────
// 판정 5건 — Critical 3 · Warning 1 · Info 1
// 룰 ID는 기획안 §5.3 카탈로그 기준
// ─────────────────────────────────────────────

export const mockVerdicts: Verdict[] = [
  {
    verdict_id: 'VD-001',
    rule_id: 'R-UCP-14C',
    target_fields: ['shipped_on_board_date'],
    result: 'VIOLATION',
    severity: 'Critical',
    message: '본선적재일로부터 21일을 초과하여 제출될 예정입니다 (적재 2026-07-14, 경과 29일).',
    action_hint: '제출 기한이 이미 지났습니다. 개설은행에 조건 변경(amendment)을 요청하거나 추심 방식 전환을 검토하세요.',
    evidence: {
      clause_text: 'UCP600 14(c) — 서류는 선적일 후 21일보다 늦게 제시되어서는 안 된다.',
    },
    judged_at: '2026-08-12T01:30:00Z',
    rule_version: 'RC-2026.08.1',
    model_version: null,
  },
  {
    verdict_id: 'VD-002',
    rule_id: 'R-LC-44EF',
    target_fields: ['port_of_loading'],
    result: 'VIOLATION',
    severity: 'Critical',
    message: 'L/C가 지정한 선적항(KRPUS)과 서류상 값이 일치하지 않는 후보가 존재합니다.',
    action_hint: 'SI의 INCHEON 표기와 L/C의 BUSAN 중 실제 선적항을 확인하고 필드를 확정하세요.',
    evidence: {
      clause_text: 'MT700 :44E: Port of Loading — KRPUS BUSAN',
    },
    judged_at: '2026-08-12T01:30:00Z',
    rule_version: 'RC-2026.08.1',
    model_version: null,
  },
  {
    verdict_id: 'VD-003',
    rule_id: 'R-XREF-QTY',
    target_fields: ['no_of_packages'],
    result: 'DEFERRED',
    severity: 'Critical',
    // ⚠ 판정 메시지에는 영문 필드명 대신 한글 표시명(FIELD_LABEL)을 씁니다.
    //   화면은 한글 라벨로 통일했는데 메시지만 measurement처럼 영문이 섞이면
    //   같은 필드가 두 이름으로 보입니다.
    //   실제 API가 붙으면 이 문자열은 백엔드가 만들어 내려주므로 같은 문제가
    //   다시 생깁니다 — BE_판정메시지_필드표기.md 참고.
    message: '포장 수량 교차 검사가 보류되었습니다. 용적 필드가 필수 확인 상태입니다.',
    action_hint: '용적 값을 확인하면 검사가 재개됩니다.',
    evidence: {
      clause_text: '서류 간 정합성 — B/L·포장명세서·송장의 포장 수량 합계 일치',
    },
    judged_at: '2026-08-12T01:30:00Z',
    rule_version: 'RC-2026.08.1',
    model_version: null,
  },
  {
    verdict_id: 'VD-004',
    rule_id: 'R-FMT-CTR',
    target_fields: ['container_no'],
    result: 'VIOLATION',
    severity: 'Warning',
    message: '컨테이너 번호 표기가 ISO 6346 형식과 다릅니다 (공백 포함).',
    action_hint: '교정 제안을 승인하면 MSKU1234565로 정규화됩니다.',
    evidence: {
      clause_text: 'ISO 6346 — 소유자 코드 4자리 + 일련번호 6자리 + 체크디지트 1자리, 구분자 없음',
    },
    judged_at: '2026-08-12T01:30:00Z',
    rule_version: 'RC-2026.08.1',
    model_version: null,
  },
  {
    verdict_id: 'VD-005',
    rule_id: 'R-UCP-30A',
    target_fields: ['incoterms'],
    result: 'VIOLATION',
    severity: 'Info',
    message: 'Incoterms 표기에 장소가 병기되어 신용장의 조건 코드(FOB)와 글자 그대로 일치하지 않습니다.',
    action_hint: '거래조건은 조건 코드(FOB)만 기재하는 것을 권장합니다.',
    evidence: {
      clause_text: '인보이스·신용장 거래조건은 동등 비교한다(X010) — 신용장에는 조건 코드만 담긴다.',
    },
    judged_at: '2026-08-12T01:30:00Z',
    rule_version: 'RC-2026.08.1',
    model_version: null,
  },
];

// ─────────────────────────────────────────────
// 하자 확률 예측 (§5.3 계층 B)
// ─────────────────────────────────────────────

export const mockPrediction: DefectPrediction = {
  probability: 0.78,
  top_factors: [
    { factor: '제출 기한 초과 (UCP600 14c)', contribution: 0.31 },
    { factor: '선적항 값 충돌', contribution: 0.19 },
    { factor: '필수 확인 필드 잔여', contribution: 0.11 },
    { factor: 'L/C 유효기일까지 24일', contribution: 0.09 },
    { factor: '컨테이너 번호 형식 오류', contribution: 0.05 },
  ],
  deferred_count: 1,
};

// ─────────────────────────────────────────────
// F5 정정 영향분석 — S8 ImpactPanel용 (§5.5)
//
// 축소 구현이라 실제 제약 그래프 탐색은 없고, "port_of_loading을 고치면
// 이 항목들을 다시 봐야 한다"는 결과값만 고정 mock으로 둡니다. mockVerdicts의
// VD-002(port_of_loading L/C 충돌)·VD-003(no_of_packages 교차검사 보류)과
// 같은 필드를 가리키게 해서, S4에서 본 판정과 S8의 영향 목록이 서로
// 이어지는 것처럼 보이게 했습니다.
//
// 이번 기간 렌더 대상은 제약 3종(EQ·SUM·REF)뿐이라 그 세 개만 만들었습니다.
// 깊이 2 원칙: 직접 영향(indirect: false) 2건 + 깊이 초과라 접어서 건수만
// 보여줄 간접 영향(indirect: true) 1건.
// ─────────────────────────────────────────────

export const mockImpactItems: ImpactItem[] = [
  {
    affected_doc: 'DOC-001',
    affected_field: 'port_of_loading',
    action: 'SI(선적지시서)의 선적항 표기를 확정값과 같게 다시 맞춰야 합니다.',
    party: '포워더',
    urgency: 'Critical',
    requires_recheck: true,
    rule_id: 'R-LC-44EF',
    constraint_type: 'REF',
    indirect: false,
  },
  {
    affected_doc: 'DOC-002',
    affected_field: 'port_of_loading',
    action: 'L/C 44E 지정 선적항(KRPUS)과 값이 같은지 재대사가 필요합니다.',
    party: '은행',
    urgency: 'Critical',
    requires_recheck: true,
    rule_id: 'R-LC-44EF',
    constraint_type: 'EQ',
    indirect: false,
  },
  {
    affected_doc: 'DOC-004',
    affected_field: 'no_of_packages',
    action: '포장 수량 교차 검사(DEFERRED)가 선적항 확정 이후 재개됩니다.',
    party: '화주',
    urgency: 'Warning',
    requires_recheck: true,
    rule_id: 'R-XREF-QTY',
    constraint_type: 'SUM',
    indirect: true,
  },
];

export const mockImpactResult: ImpactResult = {
  items: mockImpactItems,
  indirect_count: mockImpactItems.filter((item) => item.indirect).length,
  // 아직 REVIEWING 단계(제출 전)라 재발행이 아니라 초안 수정으로 충분함
  reissue_path: 'DRAFT_EDIT',
  requires_amendment: false,
};

// ─────────────────────────────────────────────
// F6 현실 대조 이벤트 6건 — S5 타임라인 · S6 경보 센터용 (§5.6)
//
// 2026-08-24 갱신: 세관(UNIPASS)·선사(DCSA) 이벤트를 전부 걷어내고,
// 실제로 붙은 어댑터인 울산항만공사 "항만 내 선박 운항정보"(VTS) 기록으로
// 교체했습니다. 근거 문서(f6-customs-reality-check.md)가 "하지 않은 검증을
// 했다고 말하는 것"이라며 금지한 표기(세관 이벤트)였습니다.
//
// 항차 2026-087, 콜사인 DSOZ8(선명 M/V OSUNG HO V.112, mockVesselMatch 참고)
// 기준 6건. 투묘 → 양묘 → 입항 → 접안 → 출항 → 미상 코드 순서입니다.
//
// ⚠ 모순 사례(EVT-005): 접안(EVT-004) 이후 이안(UNBERTH) 기록 없이
//   출항(DEPARTURE)이 찍혀 있습니다. C-STAT-01(관제 시퀀스 이상)이 잡아내는
//   사례입니다 — mockAlerts의 ALT-002.
// ⚠ EVT-006은 모르는 관제 코드('12')입니다. 조용히 버리지 않고
//   event_type: 'UNKNOWN' + raw_code로 원본을 남깁니다.
// ─────────────────────────────────────────────

export const mockRealityEvents: RealityEvent[] = [
  {
    event_id: 'EVT-001',
    shipment_id: mockShipment.shipment_id,
    source: 'ULSAN_VTS',
    source_event_code: '7',
    event_type: 'ANCHOR',
    occurred_at: '2026-07-12T04:10:00Z',
    recorded_at: '2026-07-12T04:12:00Z',
    location: 'KRUSN',
    quantity: null,
    container_no: null,
    trust_grade: 'A',
    precision: 'DATETIME',
    voyage_no: '2026-087',
    facility: '정박지',
    raw_code: null,
  },
  {
    event_id: 'EVT-002',
    shipment_id: mockShipment.shipment_id,
    source: 'ULSAN_VTS',
    source_event_code: '8',
    event_type: 'WEIGH_ANCHOR',
    occurred_at: '2026-07-12T22:30:00Z',
    recorded_at: '2026-07-12T22:32:00Z',
    location: 'KRUSN',
    quantity: null,
    container_no: null,
    trust_grade: 'A',
    precision: 'DATETIME',
    voyage_no: '2026-087',
    facility: '정박지',
    raw_code: null,
  },
  {
    event_id: 'EVT-003',
    shipment_id: mockShipment.shipment_id,
    source: 'ULSAN_VTS',
    source_event_code: '3',
    event_type: 'ARRIVAL',
    occurred_at: '2026-07-13T01:05:00Z',
    recorded_at: '2026-07-13T01:07:00Z',
    location: 'KRUSN',
    quantity: null,
    container_no: null,
    trust_grade: 'A',
    precision: 'DATETIME',
    voyage_no: '2026-087',
    facility: null,
    raw_code: null,
  },
  {
    event_id: 'EVT-004',
    shipment_id: mockShipment.shipment_id,
    source: 'ULSAN_VTS',
    source_event_code: '4',
    event_type: 'BERTH',
    occurred_at: '2026-07-13T06:40:00Z',
    recorded_at: '2026-07-13T06:42:00Z',
    location: 'KRUSN',
    quantity: null,
    container_no: null,
    trust_grade: 'A',
    precision: 'DATETIME',
    voyage_no: '2026-087',
    facility: '계류시설',
    raw_code: null,
  },
  // ⚠ 이안(UNBERTH) 없이 출항 — C-STAT-01 관제 시퀀스 이상 (ALT-002 근거)
  {
    event_id: 'EVT-005',
    shipment_id: mockShipment.shipment_id,
    source: 'ULSAN_VTS',
    source_event_code: '9',
    event_type: 'DEPARTURE',
    occurred_at: '2026-07-13T14:00:00Z',
    recorded_at: '2026-07-13T14:02:00Z',
    location: 'KRUSN',
    quantity: null,
    container_no: null,
    trust_grade: 'A',
    precision: 'DATETIME',
    voyage_no: '2026-087',
    facility: null,
    raw_code: null,
  },
  // ⚠ 모르는 관제 코드 — 버리지 않고 UNKNOWN + raw_code로 원본 보존
  {
    event_id: 'EVT-006',
    shipment_id: mockShipment.shipment_id,
    source: 'ULSAN_VTS',
    source_event_code: '12',
    event_type: 'UNKNOWN',
    occurred_at: '2026-07-13T14:05:00Z',
    recorded_at: '2026-07-13T14:07:00Z',
    location: 'KRUSN',
    quantity: null,
    container_no: null,
    trust_grade: 'A',
    precision: 'DATETIME',
    voyage_no: '2026-087',
    facility: null,
    raw_code: '12',
  },
];

// ─────────────────────────────────────────────
// F6 모순 경보 3건 — S6 경보 센터용. mockRealityEvents와 연결됨 (§5.6)
//
// 2026-08-24 갱신: 기존 수량 불일치 경보(컨테이너 대수)는 삭제했습니다.
// VTS 관제 기록에는 수량 필드가 없어 근거가 없습니다(C-QTY-01은
// mockRealityRules에서 NOT_EVALUABLE로 분류됨). 대신 이 데이터로 실제
// 성립하는 경보 3건(C-TIME-02·C-STAT-01·C-ROUTE-01)으로 교체했습니다.
//
// ⚠ document_event_ids는 spec 원안의 'on_board_date'·'vessel' 대신 실제
//   mockFields.field_name인 'shipped_on_board_date'·'vessel_voyage'를
//   씁니다 — 원안 그대로 두면 AlertCard가 "필드를 찾지 못했습니다"로
//   빠져 서류측 근거가 안 붙습니다.
// ─────────────────────────────────────────────

export const mockAlerts: Alert[] = [
  // C-TIME-02 — 서류상 본선적재일이 실제 출항보다 늦음
  {
    alert_id: 'ALT-001',
    shipment_id: mockShipment.shipment_id,
    severity: 'Critical',
    message:
      '서류의 본선적재일(2026-07-14)이 울산항 실제 출항 시각(2026-07-13 23:00 KST)보다 늦습니다. 배가 떠난 뒤에 실은 것으로 기재되어 있습니다.',
    bl_no: mockShipment.bl_no ?? '',
    document_event_ids: ['shipped_on_board_date'],
    reality_event_ids: ['EVT-005'],
    acknowledged: false,
    created_at: '2026-07-13T14:10:00Z',
  },
  // C-STAT-01 — 관제 시퀀스 이상 (접안 후 이안 없이 출항)
  {
    alert_id: 'ALT-002',
    shipment_id: mockShipment.shipment_id,
    severity: 'Info',
    message:
      '접안(07-13 15:40) 이후 이안 기록 없이 출항(07-13 23:00)이 기록되었습니다. 관제 기록 누락일 수 있습니다.',
    bl_no: mockShipment.bl_no ?? '',
    document_event_ids: ['vessel_voyage'],
    reality_event_ids: ['EVT-004', 'EVT-005'],
    acknowledged: false,
    created_at: '2026-07-13T14:10:00Z',
  },
  // C-ROUTE-01 — 선적항 불일치
  {
    alert_id: 'ALT-003',
    shipment_id: mockShipment.shipment_id,
    severity: 'Warning',
    message: 'B/L 선적항 기재(INCHEON)가 실제 관제 기록이 있는 울산항(KRUSN)과 다릅니다.',
    bl_no: mockShipment.bl_no ?? '',
    document_event_ids: ['port_of_loading'],
    reality_event_ids: ['EVT-003'],
    // 이미 mockFields에서 conflict_flag로 알려진 충돌이라, 담당자가 인지는 하고 있는 상태로 설정
    acknowledged: true,
    created_at: '2026-07-13T01:10:00Z',
  },
];

// ─────────────────────────────────────────────
// F6 신규 mock — 어댑터 상태 · 선명 해소 · 룰 커버리지 (§2 / §3.2 / §5.6)
// ─────────────────────────────────────────────

/** 울산항 VTS 어댑터 연결 상태 — S5 타임라인 상단 배너용 */
export const mockAdapterStatus: AdapterStatus = {
  name: 'ULSAN_VTS',
  connected: true,
  last_synced_at: '2026-07-14T04:00:00Z',
  consecutive_failures: 0,
  coverage_note:
    '울산항 안에서의 선박 이동만 관제됩니다. 양륙항이 울산이 아니면 그 항의 기록은 존재하지 않습니다.',
};

/** 선명 → 콜사인 해소 결과 — mockShipment의 vessel_voyage에 대응 */
export const mockVesselMatch: VesselMatch = {
  bl_vessel: 'M/V OSUNG HO V.112',
  normalized: 'OSUNG',
  call_sign: 'DSOZ8',
  method: 'NAME_FALLBACK',
  candidates: [],
};

/**
 * 모순 룰 11건의 실행 가능성 — S6 "판정 범위 공개" 구역용.
 *
 * 원안(기획 v2)에는 11건이 있었지만, 실제로 이 API(울산항 VTS + 해수부
 * 선박제원)로 판정 가능한 건 6건(완전 3 · 부분 3)뿐입니다. 나머지 5건은
 * 왜 못 하는지를 reason에 숨기지 않고 그대로 적습니다.
 * 근거: docs/backend/ai-service/f6-customs-reality-check.md §2
 */
export const mockRealityRules: RealityRuleStatus[] = [
  {
    rule_id: 'C-TIME-01',
    intent: '서류 이벤트가 물리 이벤트보다 이름 (본선적재일 < 실제 입항)',
    coverage: 'IMPLEMENTED',
    severity: 'Critical',
    reason: '입항 실측 시각으로 판정합니다.',
  },
  {
    rule_id: 'C-TIME-02',
    intent: '서류 이벤트가 물리 이벤트보다 늦음 (본선적재일 > 실제 출항)',
    coverage: 'IMPLEMENTED',
    severity: 'Critical',
    reason: '출항 실측 시각으로 판정합니다.',
  },
  {
    rule_id: 'C-TIME-03',
    intent: '세관 신고 순서 역전',
    coverage: 'NOT_EVALUABLE',
    severity: null,
    reason: '세관 신고 이벤트를 받는 경로가 없습니다.',
  },
  {
    rule_id: 'C-TIME-04',
    intent: '예정 대비 실제 지연 이상',
    coverage: 'PARTIAL',
    severity: 'Warning',
    reason: "이 API에는 '예정 vs 실제' 축이 없어 체류시간 분포 이탈만 봅니다.",
  },
  {
    rule_id: 'C-QTY-01',
    intent: '세관 신고 수량 ↔ 서류 수량',
    coverage: 'NOT_EVALUABLE',
    severity: null,
    reason: '관제 기록에 수량 필드가 없습니다.',
  },
  {
    rule_id: 'C-QTY-02',
    intent: '분할 반출 누계 ↔ 서류 수량',
    coverage: 'NOT_EVALUABLE',
    severity: null,
    reason: '동상 — 수량 필드가 없습니다.',
  },
  {
    rule_id: 'C-REL-01',
    intent: '원본회수·L/G ↔ 세관 반출',
    coverage: 'NOT_EVALUABLE',
    severity: null,
    reason: '인도 이벤트도 세관 이벤트도 없습니다.',
  },
  {
    rule_id: 'C-ROUTE-01',
    intent: '양륙항·선적항 불일치',
    coverage: 'PARTIAL',
    severity: 'Critical',
    reason: '울산이 선적항 또는 양륙항인 건만 판정합니다. 그 외는 판정하지 않음으로 남깁니다.',
  },
  {
    rule_id: 'C-VSL-01',
    intent: '선명·항차 불일치',
    coverage: 'PARTIAL',
    severity: 'Warning',
    reason: '선명은 대조하지만 항차번호는 대조하지 못합니다 — 관제 연번은 선사 항차번호가 아닙니다.',
  },
  {
    rule_id: 'C-STAT-01',
    intent: '이벤트 상태 진행 순서 이상',
    coverage: 'IMPLEMENTED',
    severity: 'Info',
    reason: '관제 시퀀스 문법으로 판정합니다.',
  },
  {
    rule_id: 'C-ANOM-01',
    intent: '이상탐지 모델',
    coverage: 'NOT_EVALUABLE',
    severity: null,
    reason: '표본이 부족해 적용하지 않았습니다.',
  },
];

// ─────────────────────────────────────────────
// F5 신규 mock — 필드별 영향 맵 · 재발행 경로 · 겹치는 교정 제안 (§5.5)
//
// 축소 구현입니다. 실제 F5는 F2 캐스케이드의 제약 그래프를 역산하지만,
// 목업에서는 어떤 필드를 고쳤을 때 무엇이 딸려오는지를 이 표로 흉내 냅니다.
// 키는 사용자가 고친 필드 이름이고, 값은 그때 다시 확인해야 하는 항목들입니다.
//
// ⚠ 필드 키는 spec 원안의 'on_board_date'가 아니라 실제 mockFields.field_name인
//   'shipped_on_board_date'를 씁니다 (아래 T1 보고 참고).
// ─────────────────────────────────────────────

export const mockImpactByField: Record<string, ImpactItem[]> = {
  // 기존 mockImpactItems 3건을 그대로 재사용
  port_of_loading: mockImpactItems,
  shipped_on_board_date: [
    {
      affected_doc: 'DOC-002',
      affected_field: 'shipped_on_board_date',
      action: 'L/C 44C가 지정한 최종선적일과 값이 같은지 확인해야 합니다.',
      party: '은행',
      urgency: 'Critical',
      requires_recheck: true,
      rule_id: null,
      constraint_type: 'EQ',
      indirect: false,
    },
    {
      affected_doc: 'DOC-003',
      affected_field: 'shipped_on_board_date',
      action: '상업송장 발행일이 본선적재일 이후인지 순서를 다시 확인해야 합니다.',
      party: '포워더',
      urgency: 'Warning',
      requires_recheck: true,
      rule_id: null,
      // 원안은 COND(조건부 제약)지만 이번 기간 렌더 대상 3종(EQ·SUM·REF)에
      // 맞춰 REF로 둡니다 (§10.1)
      constraint_type: 'REF',
      indirect: true,
    },
  ],
  no_of_packages: [
    {
      affected_doc: 'DOC-004',
      affected_field: 'no_of_packages',
      action: '포장명세서의 포장 수량 합계가 값과 일치하는지 다시 확인해야 합니다.',
      party: '화주',
      urgency: 'Critical',
      requires_recheck: true,
      rule_id: 'R-XREF-QTY',
      constraint_type: 'SUM',
      indirect: false,
    },
    {
      affected_doc: 'DOC-003',
      affected_field: 'no_of_packages',
      action: '상업송장 금액의 계산 근거(포장 수량)가 달라져 다시 계산해야 합니다.',
      party: '화주',
      urgency: 'Warning',
      requires_recheck: true,
      rule_id: null,
      constraint_type: 'DERIVE',
      indirect: true,
    },
  ],
  description_of_goods: [
    {
      affected_doc: 'DOC-002',
      affected_field: 'description_of_goods',
      action: 'L/C 45A가 지정한 상품명세와 값이 같은지 확인해야 합니다.',
      party: '은행',
      urgency: 'Critical',
      requires_recheck: true,
      rule_id: null,
      constraint_type: 'EQ',
      indirect: false,
    },
  ],
};

/** 선적 상태별 재발행 경로 — 초안이면 다시 쓰면 되지만 제출 후면 무게가 다르다 */
export const mockReissueByStatus: Partial<Record<ShipmentStatus, ImpactResult['reissue_path']>> = {
  DRAFT: 'DRAFT_EDIT',
  REVIEWING: 'DRAFT_EDIT',
  VERIFIED: 'REISSUE',
  SUBMITTED: 'ENDORSEMENT',
  MONITORING: 'SWITCH_BL',
};

/**
 * span이 겹치는 교정 제안 — 동시 승인하면 서로를 덮어씁니다 (§5.5).
 * 상품명세처럼 자유서식인 필드에서만 생깁니다.
 *
 * description_of_goods의 원문 'PRECISION MACHINE PARTS'에서
 * [0,14)="PRECISION MACH"와 [8,22)=" MACHINE PART"가 겹칩니다.
 */
export const mockOverlappingSuggestions: Suggestion[] = [
  {
    suggestion_id: 'SGT-004',
    field: 'description_of_goods',
    as_is: 'PRECISION MACHINE PARTS',
    to_be: 'PRECISION MACHINERY',
    authority: '조직사전',
    glossary_term_id: 'GLS-MACHINERY',
    confidence: 0.81,
    scope: [{ doc_id: 'DOC-003', field: 'description_of_goods' }],
    span: { start: 0, end: 14 },
  },
  {
    suggestion_id: 'SGT-005',
    field: 'description_of_goods',
    as_is: 'PRECISION MACHINE PARTS',
    to_be: 'MACHINE COMPONENTS (HS 8471.30)',
    authority: 'ISBP 745',
    glossary_term_id: 'GLS-COMPONENTS',
    confidence: 0.76,
    scope: [{ doc_id: 'DOC-003', field: 'description_of_goods' }],
    span: { start: 8, end: 22 },
  },
];

// ─────────────────────────────────────────────
// F7 신규 mock — AI 판정 설명 (§F7)
//
// verdict_id / alert_id → 설명. 네 가지 경우를 하나씩 보여줍니다:
// 정상 인용(PASS) · 허위 인용 제거 후 재생성(REPAIRED) · 재생성 실패
// 폴백(FALLBACK) · F6 경보에 붙는 설명. narrative의 수치는 전부
// mockVerdicts·mockAlerts·mockRealityEvents의 값과 일치시켰습니다.
// ─────────────────────────────────────────────

export const mockExplanations: Record<string, Explanation> = {
  // VD-001 (VIOLATION) — 인용 3건(CLAUSE·FIELD·FIELD) 전부 실재함
  'VD-001': {
    target_id: 'VD-001',
    narrative:
      '본선적재일(2026-07-14)로부터 21일을 초과한 시점에 제출될 예정이라 UCP600 14(c)를 위반합니다. 이 B/L(HLCUBUS2608001)은 조건 변경 협의가 필요합니다.',
    citations: [
      {
        citation_id: 'CIT-001',
        kind: 'CLAUSE',
        ref: 'R-UCP-14C',
        snippet: 'UCP600 14(c) — 서류는 선적일 후 21일보다 늦게 제시되어서는 안 된다.',
        verified: true,
      },
      {
        citation_id: 'CIT-002',
        kind: 'FIELD',
        ref: 'shipped_on_board_date',
        snippet: '2026-07-14',
        verified: true,
      },
      {
        citation_id: 'CIT-003',
        kind: 'FIELD',
        ref: 'bl_no',
        snippet: 'HLCUBUS2608001',
        verified: true,
      },
    ],
    generated_by: 'LLM',
    integrity: 'PASS',
    dropped_citations: 0,
    generated_at: '2026-08-12T01:31:00Z',
  },
  // VD-002 (VIOLATION) — 허위 인용 1건을 걸러내고 재생성. 검증 실패한 인용
  // 1건을 배열에 일부러 남겨둠(화면이 verified:false를 렌더하지 않는지 확인용)
  'VD-002': {
    target_id: 'VD-002',
    narrative:
      '선적항 필드에 두 후보(BUSAN/INCHEON)가 있어 L/C 44E 지정값(KRPUS BUSAN)과 대조가 필요합니다. 확정 전까지는 위반으로 판정합니다.',
    citations: [
      {
        citation_id: 'CIT-004',
        kind: 'CLAUSE',
        ref: 'R-LC-44EF',
        snippet: 'MT700 :44E: Port of Loading — KRPUS BUSAN',
        verified: true,
      },
      {
        citation_id: 'CIT-005',
        kind: 'FIELD',
        ref: 'port_of_loading',
        snippet: 'BUSAN (충돌 — INCHEON 후보 있음)',
        verified: true,
      },
      // ⚠ 검증기가 걸러낸 허위 인용 — 존재하지 않는 필드를 인용함. 화면은
      //   이 항목을 렌더하면 안 됩니다.
      {
        citation_id: 'CIT-006',
        kind: 'FIELD',
        ref: 'customs_declaration_no',
        snippet: '세관 신고번호와 대조함 (실재하지 않는 근거)',
        verified: false,
      },
    ],
    generated_by: 'LLM',
    integrity: 'REPAIRED',
    dropped_citations: 1,
    generated_at: '2026-08-12T01:32:00Z',
  },
  // VD-003 (DEFERRED) — LLM 생성 실패로 템플릿 문장 폴백. 인용 1건(FIELD)
  'VD-003': {
    target_id: 'VD-003',
    narrative:
      '이 판정은 관련 필드가 아직 확인되지 않아 보류되었습니다. 필드가 확인되면 판정이 자동으로 재개됩니다. 지금은 별도 조치가 필요하지 않습니다.',
    citations: [
      {
        citation_id: 'CIT-007',
        kind: 'FIELD',
        ref: 'measurement',
        snippet: '38.5 CBM (필수 확인)',
        verified: true,
      },
    ],
    generated_by: 'TEMPLATE',
    integrity: 'FALLBACK',
    dropped_citations: 0,
    generated_at: '2026-08-12T01:33:00Z',
  },
  // ALT-001 (F6 경보) — 인용 2건: 현실측 이벤트(EVENT) + 서류측 필드(FIELD)
  'ALT-001': {
    target_id: 'ALT-001',
    narrative:
      'B/L의 본선적재일(2026-07-14)이 울산항 실제 출항 시각(2026-07-13 23:00 KST)보다 늦게 기재되어 있습니다. 배가 이미 떠난 뒤에 선적된 것으로 기록된 셈이라 서류를 다시 확인해야 합니다.',
    citations: [
      {
        citation_id: 'CIT-008',
        kind: 'EVENT',
        ref: 'EVT-005',
        snippet: '출항 (DEPARTURE) — 2026-07-13T14:00:00Z',
        verified: true,
      },
      {
        citation_id: 'CIT-009',
        kind: 'FIELD',
        ref: 'shipped_on_board_date',
        // 인용 스니펫은 실제 mockFields의 값과 같아야 합니다 — 다르면 인용
        // 무결성 검사(integrity)를 통과했다고 표시하면서 틀린 값을 보여주게 됩니다
        snippet: '2026-07-14',
        verified: true,
      },
    ],
    generated_by: 'LLM',
    integrity: 'PASS',
    dropped_citations: 0,
    generated_at: '2026-07-13T14:11:00Z',
  },
};
