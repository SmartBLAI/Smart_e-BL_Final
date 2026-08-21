/**
 * F1 번역기 — 백엔드 추출 응답(wireExtract.ts)을 화면이 쓰는 FieldValue로.
 *
 * 원칙은 F3 번역기(adapters.ts)와 같습니다: 없는 값을 지어내지 않습니다.
 *
 * 백엔드(aiService `ocr/types.py`의 BL_FIELD_NAMES, 15개)와 화면 어휘
 * (constants/domain.ts의 FIELD_LABEL, 26개)는 이름이 완전히 같지 않습니다:
 * - vessel + voyage_no → 화면은 vessel_voyage 하나로 합쳐 보여주므로 여기서
 *   "{vessel} / {voyage_no}" 문자열로 합치고, bbox도 두 사각형의 합집합으로.
 * - on_board_date → 화면 이름은 shipped_on_board_date (이름만 다름, 값은 같음).
 * - place_of_issue / date_of_issue → 백엔드가 서로 다른 근거 좌표를 가진 별개
 *   필드로 주고, DB도 별도 컬럼으로 저장하기로 했습니다. 화면 관례상
 *   place_and_date_of_issue로 합쳐 보이던 것과 다르게, 합치지 않고 각각
 *   그대로 둡니다(FIELD_LABEL에 두 이름 모두 라벨이 있음).
 * - total_freight → 화면 26개 필드에도 DB 카탈로그에도 대응 자리가 없어 버립니다.
 */

import type { BBox, FieldValue } from '../types/domain';
import { CONFIDENCE_THRESHOLD } from '../constants/domain';
import type { WireBLDraft, WireDraftField } from './wireExtract';

const FIELD_NAME_OVERRIDES: Record<string, string> = {
  on_board_date: 'shipped_on_board_date',
};

const DROPPED_FIELD_NAMES = new Set(['total_freight']);

/**
 * 확인이 필요하다고 표시된 필드에 줄 화면 신뢰도.
 *
 * 확인 권고 하한(ADVISORY) 미만이라 `toConfidenceGrade`가 "필수 확인"으로
 * 분류합니다. 0을 쓰지 않는 이유는 좌표가 없는 값이 "출처 없음"(NOT_FOUND)으로
 * 잘못 분류되기 때문입니다 — `toConfidenceGrade` 참고.
 */
const REVIEW_CONFIDENCE = CONFIDENCE_THRESHOLD.ADVISORY / 2;

/**
 * 백엔드 신뢰도 → 화면 신뢰도.
 *
 * 이름은 같지만 두 숫자는 서로 다른 질문에 답합니다:
 * - 백엔드 `confidence` = "글자를 제대로 읽었는가" (OCR 인식 신뢰도)
 * - 화면 `confidence` = `toConfidenceGrade`가 "사람이 봐야 하는가"를 정하는 값
 *
 * 텍스트 레이어가 있는 PDF는 글자를 원문 그대로 가져오므로 전 필드가 1.0으로
 * 옵니다. 하지만 그 텍스트가 *올바른 필드에 꽂혔는가* 는 다른 질문이고,
 * 백엔드는 그걸 `needs_review`로 따로 알려줍니다 (구역이 밀려 옆 칸의 항목명이
 * 값에 섞여 들어온 `label_echoed` 등 — aiService `ocr/draft.py` 참고).
 *
 * 이 신호를 버리고 1.0만 쓰면 틀린 값이 "확정" 배지를 달고 확인 대기열에서
 * 빠집니다. 입력이 정확할수록 아무도 검토하지 않는 역설이 생기므로, 여기서
 * 백엔드의 판단을 화면 어휘(= 필수 확인 등급)로 옮겨 줍니다.
 */
function screenConfidence(confidence: number | null, needsReview: boolean): number {
  const raw = confidence ?? 0;
  return needsReview ? Math.min(raw, REVIEW_CONFIDENCE) : raw;
}

function mergeBbox(a: BBox | null, b: BBox | null): BBox | null {
  if (!a) return b;
  if (!b) return a;
  return [Math.min(a[0], b[0]), Math.min(a[1], b[1]), Math.max(a[2], b[2]), Math.max(a[3], b[3])];
}

/**
 * 백엔드 필드 하나를 화면용 FieldValue로 바꿉니다.
 *
 * source_doc_id는 백엔드 응답에 아예 없어 항상 null입니다(지어내지 않음).
 * bbox·page는 실제 값을 그대로 씁니다(page는 호출자가 넘긴 값 — 이 함수는
 * 필드 하나가 어느 페이지에서 왔는지 모릅니다).
 *
 * extractor는 도메인 3종(rule/ocr+llm/json)과 백엔드 3종(region/anchor/llm)이
 * 정확히 안 맞습니다. llm만 구분하고 나머지(region·anchor)는 rule로
 * 뭉뚱그렸습니다 — 지금 화면 어디도 extractor로 분기하는 곳이 없어
 * 안전한 단순화입니다.
 */
function toFieldValue(field: WireDraftField, page: number | null): FieldValue {
  return {
    field_name: FIELD_NAME_OVERRIDES[field.name] ?? field.name,
    value: field.value,
    normalized_value: field.value,
    confidence: screenConfidence(field.confidence, field.needs_review),
    source_doc_id: null,
    page: field.bbox ? page : null,
    bbox: field.bbox,
    extractor: field.source === 'llm' ? 'ocr+llm' : 'rule',
    conflict_flag: false,
  };
}

export function toDraftFields(draft: WireBLDraft, page: number | null = null): FieldValue[] {
  const byName = new Map(draft.fields.map((f) => [f.name, f]));
  const vessel = byName.get('vessel');
  const voyageNo = byName.get('voyage_no');

  const fields = draft.fields
    .filter((f) => !DROPPED_FIELD_NAMES.has(f.name) && f.name !== 'vessel' && f.name !== 'voyage_no')
    .map((f) => toFieldValue(f, page));

  if (vessel || voyageNo) {
    const value = [vessel?.value, voyageNo?.value].filter(Boolean).join(' / ') || null;
    const bbox = mergeBbox(vessel?.bbox ?? null, voyageNo?.bbox ?? null);
    // 둘 중 하나만 확인이 필요해도 합친 필드는 확인 대상입니다 — 합쳐 보여주는
    // 이상 사람이 볼 때도 둘을 같이 보게 됩니다.
    const needsReview = (vessel?.needs_review ?? false) || (voyageNo?.needs_review ?? false);
    const confidence = screenConfidence(
      Math.min(vessel?.confidence ?? 0, voyageNo?.confidence ?? 0),
      needsReview,
    );
    const isLlm = vessel?.source === 'llm' || voyageNo?.source === 'llm';
    fields.push({
      field_name: 'vessel_voyage',
      value,
      normalized_value: value,
      confidence,
      source_doc_id: null,
      page: bbox ? page : null,
      bbox,
      extractor: isLlm ? 'ocr+llm' : 'rule',
      conflict_flag: false,
    });
  }

  return fields;
}
