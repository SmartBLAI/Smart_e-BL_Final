/**
 * B/L Copilot — 공유 도메인 타입
 *
 * 근거: 기획안 v2 §5.1 / §5.2 / §5.5 / §5.6 / §5.8
 * 규약: FE 개발규약 v0.2 §3
 *
 * ⚠ 이 파일은 FE 2인의 공유 정의입니다.
 *   수정 시 반드시 상호 리뷰를 거칩니다. (규약 §6.3)
 */

// ─────────────────────────────────────────────
// 공통 열거형
// ─────────────────────────────────────────────

/** 심각도 3단계 — F3·F6이 공유. 화면 색상·정렬 순서 동일 적용 (§5.8) */
export type Severity = 'Critical' | 'Warning' | 'Info';

/** 선적 상태 6종 — 임의 추가 금지 (§5.8) */
export type ShipmentStatus =
  | 'DRAFT'        // 초안 생성
  | 'REVIEWING'    // 필수 확인 필드 처리 중
  | 'VERIFIED'     // 검증 완료 · Critical 미해결 없음
  | 'SUBMITTED'    // 제출
  | 'MONITORING'   // 현실 대조 중
  | 'CLOSED';      // 결과 기록 완료

/** 필드 신뢰도 등급 (§5.1) */
export type ConfidenceGrade =
  | 'CONFIRMED'   // 확정      — 0.90 이상
  | 'ADVISORY'    // 확인 권고  — 0.70 이상 0.90 미만
  | 'REQUIRED'    // 필수 확인  — 0.70 미만 · 스키마 위반 · 값 충돌
  | 'NOT_FOUND';  // 미검출    — 근거 위치 없음

/** 정정 영향의 담당 당사자 (§5.5) */
export type Party = '화주' | '포워더' | '선사' | '은행' | '관세사';

/** ISO8601 UTC 문자열. 표시 시에만 현지 시간대로 변환 (§5.6) */
export type UtcTimestamp = string;

// ─────────────────────────────────────────────
// F1 — 서류 인테이크 · 초안
// ─────────────────────────────────────────────

/** 원문 근거 좌표 [x0, y0, x1, y1] */
export type BBox = [number, number, number, number];

/**
 * 추출 필드값 (§5.1)
 *
 * ⚠ bbox가 null인 값은 저장·표시하지 않습니다.
 *   추정 생성 금지 원칙 (규약 §2.4)
 */
export interface FieldValue {
  field_name: string;
  value: string | null;
  normalized_value: string | null;
  confidence: number;
  source_doc_id: string | null;
  page: number | null;
  bbox: BBox | null;
  extractor: 'rule' | 'ocr+llm' | 'json';
  conflict_flag: boolean;
  /** 게이트웨이가 저장해 둔 등급(새로고침 후에도 "값 확인함" 유지). 목데이터엔 없어 optional */
  grade?: ConfidenceGrade;
  /** 다중 출처 충돌 시 후보를 폐기하지 않고 모두 보존 (§5.1) */
  candidates?: FieldValue[];
}

export type DocumentKind =
  | 'BL'          // 선하증권
  | 'INVOICE'     // 상업송장
  | 'PACKING'     // 포장명세서
  | 'LC'          // 신용장 (MT700)
  | 'SI'          // 선적요청서
  | 'UNKNOWN';

export interface DocumentMeta {
  document_id: string;
  kind: DocumentKind;
  file_name: string;
  file_hash: string;
  page_count: number;
  version: number;
  uploaded_at: UtcTimestamp;
}

/** 비동기 추출 작업 상태 (§5.1) */
export type JobStatus = 'PENDING' | 'EXTRACTING' | 'DONE' | 'FAILED';

export interface Job {
  job_id: string;
  status: JobStatus;
  progress: number | null;
  failure_reason: string | null;
}

// ─────────────────────────────────────────────
// F2 — 표준 용어 교정
// ─────────────────────────────────────────────

/** 교정 근거 출처 (§5.2) */
export type Authority =
  | 'UN/LOCODE'
  | 'UN/ECE Rec 20'
  | 'ISO 6346'
  | 'Incoterms 2020'
  | 'ISBP 745'
  | 'DCSA'
  | '조직사전';

/** 교정 거절 사유 — 사전 개선 입력이므로 수집 생략 불가 (§5.2) */
export type RejectReason = 'INTERNAL_PRACTICE' | 'COUNTERPARTY' | 'WRONG_SUGGESTION';

/** 자유서식 필드 치환 범위 (§5.5). 문자 인덱스 [start, end) */
export interface TextSpan {
  start: number;
  end: number;
}

export interface Suggestion {
  suggestion_id: string;
  field: string;
  as_is: string;
  to_be: string;
  authority: Authority;
  glossary_term_id: string;
  confidence: number;
  /** 동일 값이 쓰인 다른 서류·필드 — "전체 적용" 일괄 승인 범위 */
  scope: { doc_id: string; field: string }[];
  /**
   * 자유서식 필드(상품명세 등)에서 이 제안이 바꿀 글자 범위.
   * 정형 필드는 값 전체를 바꾸므로 없음(undefined).
   */
  span?: TextSpan;
}

// ─────────────────────────────────────────────
// F3 · F6 — 판정
// ─────────────────────────────────────────────

export type VerdictResult =
  | 'VIOLATION'
  | 'PASS'
  | 'DEFERRED';   // 판정 보류 — 필수 확인 필드 미처리 (§5.3)

export interface VerdictEvidence {
  /** 조문 원문 스니펫 — F7 설명의 인용 근거 */
  clause_text: string;
  /** F6 모순 경보의 근거 이벤트 (서류측·현실측 각 1건 이상) */
  event_ids?: string[];
}

export interface Verdict {
  verdict_id: string;
  rule_id: string;
  target_fields: string[];
  result: VerdictResult;
  severity: Severity;
  message: string;
  /** 수정 가이드 — 모든 위반은 최소 1개의 구체적 조치 문장 보유 (§5.4) */
  action_hint: string | null;
  evidence: VerdictEvidence;
  judged_at: UtcTimestamp;
  /** 판정 재현성 — 당시 버전으로 과거 판정 재현 (§5.8) */
  rule_version: string;
  model_version: string | null;
}

/** 하자 확률 예측 결과 (§5.3 계층 B) */
export interface DefectPrediction {
  /** 보정(캘리브레이션) 후 확률. 보정 전 원점수는 표시하지 않음 */
  probability: number;
  /** SHAP 기여도 상위 5개 */
  top_factors: { factor: string; contribution: number }[];
  /** 판정 보류 건수 — 20% 초과 시 신뢰도 제한 경고 (§5.4) */
  deferred_count: number;
}

// ─────────────────────────────────────────────
// F5 — 정정 영향분석
// ─────────────────────────────────────────────

/** 제약 유형 — 타입은 6종 유지, 이번 기간 렌더는 EQ·SUM·REF 3종 (§10.1) */
export type ConstraintType = 'EQ' | 'SUM' | 'DERIVE' | 'REF' | 'COND' | 'EXT';

export interface ImpactItem {
  affected_doc: string;
  affected_field: string;
  action: string;
  party: Party;
  urgency: Severity;
  requires_recheck: boolean;
  rule_id: string | null;
  constraint_type: ConstraintType;
  /** 탐색 깊이 초과분 — 접어서 건수만 노출 (§5.5) */
  indirect: boolean;
}

/** B/L 발행 후 변경 시 재발행 경로 (§5.5) */
export type ReissuePath = 'DRAFT_EDIT' | 'ENDORSEMENT' | 'REISSUE' | 'SWITCH_BL';

export interface ImpactResult {
  items: ImpactItem[];
  indirect_count: number;
  reissue_path: ReissuePath;
  /** 이미 은행 제출 건이면 조건 변경(amendment) 필요 표시 */
  requires_amendment: boolean;
}

// ─────────────────────────────────────────────
// F6 — 현실 대조
// ─────────────────────────────────────────────

/**
 * 이벤트 출처.
 *
 * 이번 구현이 실제로 붙은 것은 ULSAN_VTS 하나이고, 해양수산부 선박제원정보
 * (MOF_VSSL)는 이벤트가 아니라 "선명 → 콜사인" 해소에만 쓴다.
 * UNIPASS·DCSA는 원안에만 있고 채택하지 않았다 — 타입에는 남겨두되
 * 목데이터에서는 쓰지 않는다.
 */
export type EventSource = 'ULSAN_VTS' | 'MOF_VSSL' | 'UNIPASS' | 'DCSA' | 'USER' | 'INTERNAL';

/** 소스 신뢰등급 (§5.6) */
export type TrustGrade = 'A' | 'B' | 'C' | 'INTERNAL';

/** 울산항 VTS 관제 이벤트 7종 (ioprtVtsType 3~9) + 미상 */
export type RealityEventType =
  | 'ARRIVAL' | 'BERTH' | 'UNBERTH' | 'SHIFT_BERTH'
  | 'ANCHOR' | 'WEIGH_ANCHOR' | 'DEPARTURE' | 'UNKNOWN';

export interface RealityEvent {
  event_id: string;
  shipment_id: string;
  source: EventSource;
  source_event_code: string;
  event_type: RealityEventType;
  occurred_at: UtcTimestamp;
  recorded_at: UtcTimestamp;
  location: string | null;      // UN/LOCODE
  quantity: number | null;
  container_no: string | null;
  trust_grade: TrustGrade;
  /** 날짜만 제공된 이벤트는 시각을 표시하지 않음 (§5.6) */
  precision: 'DATE' | 'DATETIME';
  /** 항차 그룹 키 — (콜사인, 연도, 울산항 연번) */
  voyage_no: string | null;
  /** 정박지(WAM)인지 계류시설인지 — C-STAT-01이 이 구분을 씀 */
  facility: '정박지' | '계류시설' | null;
  /** 모르는 관제 코드는 버리지 않고 원본을 남긴다 (event_type = 'UNKNOWN') */
  raw_code: string | null;
}

/** 어댑터 연결 상태 — S5에 표시. 데이터 없음을 정상으로 판단하지 않음 (§5.6) */
export interface AdapterStatus {
  name: EventSource;
  connected: boolean;
  last_synced_at: UtcTimestamp | null;
  consecutive_failures: number;
  /** 어댑터가 볼 수 있는 범위. 화면이 "커버리지 밖"을 설명할 때 씀 */
  coverage_note: string;
}

/**
 * F6 모순 경보 — S6 경보 센터(전역, 여러 선적을 한 화면에 모아 보여줌)에서 사용 (§5.6)
 *
 * ⚠ 서류측·현실측 근거 이벤트를 각각 1건 이상 가져야 합니다.
 *   document_event_ids·reality_event_ids 둘 다 비어 있는 경보는 만들지 않습니다.
 *   단 예외: C-ROUTE-01(B/L은 울산항이라는데 울산 관제 기록에 그 선박이 없음)은
 *   reality_event_ids가 []입니다 — "기록이 없다"는 사실 자체가 현실측 근거라서
 *   가리킬 이벤트가 없습니다. 화면은 빈 배열을 정상으로 다뤄야 합니다.
 */
export interface Alert {
  alert_id: string;
  shipment_id: string;
  severity: Severity;
  message: string;
  /** 목록에서 선적을 바로 식별할 수 있도록. S6은 여러 선적의 경보를 한 화면에서 다룸 */
  bl_no: string;
  /** 서류측 근거 — 관련 FieldValue.field_name 참조. 최소 1건 */
  document_event_ids: string[];
  /** 현실측 근거 — RealityEvent.event_id 참조. 최소 1건 */
  reality_event_ids: string[];
  acknowledged: boolean;
  created_at: UtcTimestamp;
  /** 게이트웨이(reality.py)가 실제 경보에 추가로 내려주는 값 — 목데이터엔 없어서 optional */
  rule_id?: string;
  title?: string;
  /** acknowledged는 status !== 'OPEN' 과 같은 뜻입니다 */
  status?: AlertStatus;
  last_seen_at?: UtcTimestamp;
}

export type AlertStatus = 'OPEN' | 'ACKNOWLEDGED' | 'WHITELISTED' | 'RESOLVED';

/**
 * 선명 → 콜사인 해소 결과 (§3.2).
 *
 * B/L에는 콜사인 칸이 없어서 선명으로 조인할 수밖에 없다. 어떤 경로로
 * 배를 특정했는지를 화면이 밝혀야 한다 — 이름 폴백은 동명이선 위험이 있다.
 */
export type VesselMatchMethod = 'CALLSIGN' | 'NAME_FALLBACK' | 'AMBIGUOUS' | 'NOT_FOUND';

export interface VesselMatch {
  /** B/L에 적힌 원문 선명. 예: "M/V OSUNG HO V.112" */
  bl_vessel: string;
  /** 접두(M/V·MV)·접미(HO)·항차(V.112) 제거 후 */
  normalized: string;
  call_sign: string | null;
  method: VesselMatchMethod;
  /** AMBIGUOUS일 때 후보 콜사인들 */
  candidates: string[];
}

/** 모순 룰 실행 가능성 (§2). 원안 11건 중 실제 구현은 6건 */
export type RuleCoverage = 'IMPLEMENTED' | 'PARTIAL' | 'NOT_EVALUABLE';

export interface RealityRuleStatus {
  rule_id: string;          // 'C-TIME-01' 등
  intent: string;           // 원안 취지 한 줄
  coverage: RuleCoverage;
  severity: Severity | null;  // NOT_EVALUABLE이면 null
  /** 왜 못 하는지 / 어디까지만 하는지. 숨기지 않는다 */
  reason: string;
}

// ─────────────────────────────────────────────
// F7 — AI 판정 설명
// ─────────────────────────────────────────────

/** 인용 종류 — 조문 · 현실 이벤트 · 서류 필드 */
export type CitationKind = 'CLAUSE' | 'EVENT' | 'FIELD';

export interface Citation {
  citation_id: string;
  kind: CitationKind;
  /** 가리키는 대상 ID. CLAUSE면 조문 코드, EVENT면 event_id, FIELD면 field_name */
  ref: string;
  /** 화면에 보여줄 원문 조각 */
  snippet: string;
  /**
   * 출력 검증기가 이 인용 ID의 실재를 대조한 결과.
   * false면 화면에 렌더하지 않는다 — 없는 조문을 인용한 것이므로.
   */
  verified: boolean;
}

/** 설명을 누가 썼는가. 폴백을 'AI 생성'으로 표기하지 않기 위해 반드시 구분한다 */
export type ExplanationSource = 'LLM' | 'TEMPLATE';

/** 인용 무결성 검사 결과 */
export type CitationIntegrity =
  | 'PASS'      // 모든 인용이 실재함
  | 'REPAIRED'  // 허위 인용을 걸러내고 재생성함
  | 'FALLBACK'; // 재생성도 실패해 템플릿 문장으로 대체함

export interface Explanation {
  /** 설명 대상 — Verdict.verdict_id 또는 Alert.alert_id */
  target_id: string;
  narrative: string;
  citations: Citation[];
  generated_by: ExplanationSource;
  integrity: CitationIntegrity;
  /** 검증기가 걸러낸 허위 인용 건수. 0이 아니면 화면에 밝힌다 */
  dropped_citations: number;
  generated_at: UtcTimestamp;
}

// ─────────────────────────────────────────────
// 선적 (전 기능 공통 키)
// ─────────────────────────────────────────────

export interface Shipment {
  shipment_id: string;
  status: ShipmentStatus;
  bl_no: string | null;
  cargo_control_no: string | null;
  lc_no: string | null;
  created_at: UtcTimestamp;
  updated_at: UtcTimestamp;
  /** 유효기일 등 기한 */
  lc_expiry_date: string | null;
}

export interface ShipmentDraft {
  shipment: Shipment;
  documents: DocumentMeta[];
  fields: FieldValue[];
  suggestions: Suggestion[];
}

/** 상태 강제 진행 시 기록 — 리포트와 피드백 데이터에 남음 (§5.8) */
export interface StatusOverride {
  from: ShipmentStatus;
  to: ShipmentStatus;
  reason: string;
  actor: string;
  at: UtcTimestamp;
}
