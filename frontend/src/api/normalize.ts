/**
 * F2 용어 교정 — `/normalize`, `/normalize/apply`, `/normalize/reject` 호출 + 번역.
 *
 * 화면은 이 함수들만 부르면 됩니다.
 */

import { postJson } from './client';
import { toBLPayload } from './adapters';
import { toDocumentIn, toNormalizeView, toWireRejectReason, type NormalizeView } from './adaptersNormalize';
import type {
  WireApplyResponse,
  WireCorrection,
  WireNormalizeResponse,
  WireSuggestion,
} from './wireNormalize';
import type { FieldValue, RejectReason } from '../types/domain';

/**
 * 승인자 식별자. 로그인 시스템이 없어 지금은 고정값입니다 — 인증이 붙으면
 * 실제 사용자 식별자로 바꿉니다.
 */
const DECIDED_BY = 'bl-copilot-web';

export async function normalizeShipment(fields: FieldValue[], signal?: AbortSignal): Promise<NormalizeView> {
  const res = await postJson<WireNormalizeResponse>('/normalize', { bl: toBLPayload(fields) }, signal);
  return toNormalizeView(res.suggestions);
}

/**
 * 승인된 제안 하나를 서버에 적용합니다. 서버가 실제로 값을 어떻게 고쳤는지
 * (`documents[0].fields[field_name]`)를 돌려주므로, 화면은 `suggestion.to_be`를
 * 직접 쓰지 않고 이 응답값을 씁니다 — 서버는 span 단위 치환을 하기도 해서
 * 항상 `to_be` 그대로는 아닙니다.
 */
export async function applySuggestion(
  fields: FieldValue[],
  original: WireSuggestion,
  applyToAllInScope: boolean,
  signal?: AbortSignal,
): Promise<WireApplyResponse> {
  return postJson<WireApplyResponse>(
    '/normalize/apply',
    {
      documents: [toDocumentIn(fields)],
      suggestions: [original],
      // 'field'는 제안이 가리키는 자리 하나만, 'all'은 scope에 실린 다른
      // 자리까지 서버가 같이 고칩니다 (backend/aiService/api/main.py의 ApplyRequest).
      scope: applyToAllInScope ? 'all' : 'field',
      decided_by: DECIDED_BY,
      decided_at: new Date().toISOString(),
    },
    signal,
  );
}

export async function rejectSuggestion(
  original: WireSuggestion,
  reason: RejectReason,
  signal?: AbortSignal,
): Promise<WireCorrection> {
  const res = await postJson<{ corrections: WireCorrection[] }>(
    '/normalize/reject',
    {
      suggestions: [original],
      reason: toWireRejectReason(reason),
      decided_by: DECIDED_BY,
      decided_at: new Date().toISOString(),
    },
    signal,
  );
  return res.corrections[0];
}
