/**
 * F4 리포트 — 백엔드 `POST /report`·`POST /report/pdf` 가 실제로 주고받는 JSON 모양.
 *
 * 근거: `ai/f4_report/model.py`의 `Report.to_dict()` (필드명 1:1 확인),
 *       `ai/f3_rules/deadline.py`의 `PresentationDeadline.to_dict()`,
 *       `ai/api/main.py`의 `ReportRequest`(`VerifyRequest` + `submitted_documents`).
 *       실제 `curl -X POST localhost:5050/report ...` 응답으로도 확인했습니다.
 */

import type { WireSeverity } from './wire';

/** `POST /report`·`POST /report/pdf` 공통 요청 본문 */
export interface WireReportRequest {
  bl: Record<string, string>;
  // wire.ts의 WireVerifyRequest.lc와 같은 자리(LcParse.lc)라 타입도 맞춥니다.
  lc?: Record<string, unknown>;
  as_of?: string;
  /** 실제 제출한 서류명. 신용장 46A와 대조해 누락 서류를 찾는 데 씁니다 */
  submitted_documents?: string[];
}

/** ② 항목별 리스크 1건. `/verify`의 WireViolation과 거의 같지만 remedy가 없습니다 */
export interface WireRiskItem {
  rule_id: string;
  severity: WireSeverity;
  severity_label: string;
  title: string;
  message: string;
  source: string;
  fields: string[];
  observed: Record<string, string | null>;
}

/** ③ 체크리스트 1행 */
export interface WireChecklistItem {
  label: string;
  done: boolean;
  detail: string;
}

/** ③ 제시기한. 신용장/선적일 정보가 부족하면 null */
export interface WireDeadline {
  presentation_due: string | null;
  expiry: string | null;
  effective_due: string;
  days_left: number;
  is_overdue: boolean;
  basis: string;
  shipped_from: string | null;
}

/** ④ 수정 권고 1건. `risks`와 순서 기준이 달라 index로 안전하게 짝지을 수 없습니다 */
export interface WireRecommendation {
  order: number;
  severity_label: string;
  action: string;
  target_fields: string[];
  source: string;
}

/** 검사하지 못한 항목. `/verify`의 WireSkippedRule과 같은 모양입니다 */
export interface WireUncheckedItem {
  rule_id: string;
  title: string;
  reason: string;
}

export interface WireReportSummary {
  defect_probability: number;
  risk_level: string;
  counts: Record<WireSeverity, number>;
  /** "rules-v1" 이면 학습 모델이 아니라 룰 가중치 합입니다 (WirePrediction.model과 같은 뜻) */
  model: string;
  headline: string;
  narrative: string;
  narrative_source: string;
  rule_catalog: { version: string; digest: string; label: string } | null;
}

export interface WireReportResponse {
  bl_no: string | null;
  lc_no: string | null;
  generated_at: string | null;
  summary: WireReportSummary;
  risks: WireRiskItem[];
  checklist: WireChecklistItem[];
  deadline: WireDeadline | null;
  recommendations: WireRecommendation[];
  outlook: { verdict: string; detail: string };
  unchecked: WireUncheckedItem[];
}
