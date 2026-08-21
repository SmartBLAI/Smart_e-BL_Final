/**
 * F2 용어 교정 — aiService `/normalize`, `/normalize/apply`, `/normalize/reject` 모양.
 *
 * 백엔드 `terms/types.py`(dataclass `to_dict()`) + `api/main.py`의 Pydantic
 * 요청 모델과 1:1로 맞췄습니다.
 *
 * ⚠ `WireSuggestion`은 `/normalize` 응답에서 받은 걸 **그대로** apply/reject에
 *   되돌려 보내야 합니다 — 서버가 전체 내용으로 `suggestion_id`를 다시
 *   계산해 변조 여부를 검사합니다(필드 하나라도 바뀌면 다른 제안으로 읽힘).
 */

export interface WireFieldRef {
  doc: string;
  field: string;
  doc_id: string | null;
  span: [number, number] | null;
}

export interface WireEvidence {
  authority: string;
  term_id: string | null;
  glossary_version: string;
  tier: string;
  stage: string;
  verified: boolean;
  diverges_from_standard: string | null;
}

export interface WireCandidate {
  to_be: string;
  term_id: string | null;
  authority: string;
  score: number;
  reason: string;
}

export interface WireSuggestion {
  suggestion_id: string;
  field: WireFieldRef;
  as_is: string;
  to_be: string | null;
  term_class: string;
  evidence: WireEvidence;
  confidence: number;
  impact: WireFieldRef[];
  candidates: WireCandidate[];
  requires_choice: boolean;
  message: string;
}

export interface WireNotice {
  kind: 'lc_wording' | 'injection' | 'deterministic_error' | 'not_covered';
  severity: 'critical' | 'warning' | 'info';
  field: WireFieldRef;
  message: string;
}

export interface WireUnevaluated {
  field: WireFieldRef;
  reason: string;
  score: number | null;
  as_is: string | null;
}

export interface WireNormalizeResponse {
  suggestions: WireSuggestion[];
  notices: WireNotice[];
  unevaluated: WireUnevaluated[];
  versions: {
    glossary_version: string;
    cascade_version: string;
    rules_catalog_version: string | null;
    llm_model: string | null;
    ranker: string;
  };
  stats: {
    by_stage: Record<string, number>;
    llm_path: string;
    llm_calls: number;
    elapsed_ms: number | null;
  };
}

/** `/normalize`·`/normalize/apply`가 공유하는 서류 1건 형태 */
export interface WireDocumentIn {
  doc: string;
  doc_id?: string | null;
  fields: Record<string, string | null>;
}

/** 적용하지 못한 제안 1건 — apply.py의 unapplied.append({...}) 모양 그대로 */
export interface WireUnapplied {
  suggestion_id: string;
  reason: string;
  field: WireFieldRef;
}

export interface WireApplyResponse {
  documents: { doc: string; doc_id: string | null; fields: Record<string, string | null> }[];
  corrections: WireCorrection[];
  /** suggestion_id가 변조됐거나 사전 버전이 달라 적용 못 한 제안 목록 (문자열 배열이 아닙니다) */
  unapplied: WireUnapplied[];
}

export interface WireCorrection {
  suggestion_id: string;
  field: WireFieldRef;
  as_is: string;
  to_be: string | null;
  term_class: string;
  decision: 'accepted' | 'rejected';
  decided_by: string;
  decided_at: string;
  impact: WireFieldRef[];
  reason: string | null;
  note: string | null;
}

export interface WireRejectResponse {
  corrections: WireCorrection[];
}
