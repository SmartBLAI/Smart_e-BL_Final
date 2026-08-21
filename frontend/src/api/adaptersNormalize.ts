/**
 * F2 번역기 — 백엔드 교정 제안 응답(wireNormalize.ts)을 화면이 쓰는 타입으로.
 *
 * 원칙은 F3 번역기(adapters.ts)와 같습니다: 없는 값을 지어내지 않습니다.
 */

import { toBLPayload } from './adapters';
import type { WireDocumentIn, WireSuggestion } from './wireNormalize';
import type { Authority, FieldValue, RejectReason, Suggestion } from '../types/domain';

/**
 * 화면 필드를 `/normalize`·`/normalize/apply`가 쓰는 서류 1건으로 묶습니다.
 *
 * 지금 화면은 서류를 나누지 않고 "선하증권" 한 장으로 취급합니다(F3의
 * `toBLPayload`와 같은 전제) — 여러 서류(상업송장·포장명세서 등)를 따로
 * 다루는 건 이번 F2 범위 밖입니다.
 */
export function toDocumentIn(fields: FieldValue[]): WireDocumentIn {
  return { doc: '선하증권', fields: toBLPayload(fields) };
}

/**
 * 백엔드 제안 하나를 화면용 Suggestion으로 바꿉니다. `null`이면 이 제안은
 * 화면에 대응 개념이 없어 걸러야 한다는 뜻입니다(호출부가 filter).
 *
 * - `requires_choice=true`(즉 `to_be===null`)인 제안은 후보 중 하나를
 *   골라야 값이 정해지는데, 도메인 Suggestion에는 후보 선택 UI가 없어
 *   값을 지어낼 수 없습니다 — 걸러냅니다.
 * - `evidence.authority`는 백엔드가 도메인의 닫힌 7종보다 더 다양한
 *   문자열(예: "ISBP 821", "HS 2022")을 냅니다. 화면은 이 값을 그대로
 *   문자열로 보여주기만 하고(SuggestionCard) 분기하지 않으므로, 타입만
 *   넓혀 씁니다(as Authority) — 실제 표시에는 영향 없는 안전한 단순화.
 * - `evidence.term_id`가 없으면(패턴/포맷 단계 제안은 사전 항목을 안 씀)
 *   "해당 없음"을 빈 문자열로 표시합니다 — 값을 지어낸 게 아니라 없다는
 *   사실 그대로입니다.
 */
export function toSuggestion(wire: WireSuggestion): Suggestion | null {
  if (wire.requires_choice || wire.to_be === null) return null;

  return {
    suggestion_id: wire.suggestion_id,
    field: wire.field.field,
    as_is: wire.as_is,
    to_be: wire.to_be,
    authority: wire.evidence.authority as Authority,
    glossary_term_id: wire.evidence.term_id ?? '',
    confidence: wire.confidence,
    scope: wire.impact.map((ref) => ({ doc_id: ref.doc_id ?? '', field: ref.field })),
  };
}

export interface NormalizeView {
  suggestions: Suggestion[];
  /** suggestion_id → 원본 WireSuggestion. apply/reject 호출 시 그대로 되돌려 보내야 합니다 */
  bySuggestionId: Record<string, WireSuggestion>;
  /** requires_choice라 화면에 못 띄우고 걸러낸 제안 수 */
  skippedChoiceCount: number;
}

export function toNormalizeView(wireSuggestions: WireSuggestion[]): NormalizeView {
  const suggestions: Suggestion[] = [];
  const bySuggestionId: Record<string, WireSuggestion> = {};
  let skippedChoiceCount = 0;

  for (const wire of wireSuggestions) {
    bySuggestionId[wire.suggestion_id] = wire;
    const suggestion = toSuggestion(wire);
    if (suggestion === null) {
      skippedChoiceCount += 1;
      continue;
    }
    suggestions.push(suggestion);
  }

  return { suggestions, bySuggestionId, skippedChoiceCount };
}

/**
 * 도메인 3종 거절 사유 → 백엔드 4종 문자열. 백엔드의 `other`는 화면에 고를
 * 방법이 없는 값이라(도메인 RejectReason에 없음) 여기서 다루지 않습니다.
 */
const REJECT_REASON_TO_WIRE: Record<RejectReason, string> = {
  INTERNAL_PRACTICE: 'in_house',
  COUNTERPARTY: 'counterparty',
  WRONG_SUGGESTION: 'false_positive',
};

export function toWireRejectReason(reason: RejectReason): string {
  return REJECT_REASON_TO_WIRE[reason];
}
