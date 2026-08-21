import { describe, expect, it } from 'vitest';
import { toDraftFields } from './adaptersExtract';
import { toConfidenceGrade } from '../constants/domain';
import type { WireBLDraft, WireDraftField } from './wireExtract';

function wireField(overrides: Partial<WireDraftField> = {}): WireDraftField {
  return {
    name: 'shipper',
    label: '송하인',
    value: 'ACME',
    confidence: 0.9,
    source: 'region',
    bbox: [0.1, 0.1, 0.2, 0.2],
    is_critical: false,
    needs_review: false,
    review_reason: null,
    review_message: null,
    ...overrides,
  };
}

function draft(fields: WireDraftField[]): WireBLDraft {
  return {
    image_id: 'img-1',
    form_type: 'BL',
    source: 'test',
    ocr_mean_confidence: 0.9,
    processing_time_ms: 100,
    completeness: 1,
    is_ready_for_verification: true,
    review_required_count: 0,
    fields,
  };
}

describe('toDraftFields', () => {
  it('total_freight는 화면에 대응 자리가 없어 버림', () => {
    const result = toDraftFields(draft([wireField({ name: 'total_freight' })]));
    expect(result).toHaveLength(0);
  });

  it('on_board_date는 shipped_on_board_date로 이름만 바뀜(값은 그대로)', () => {
    const result = toDraftFields(draft([wireField({ name: 'on_board_date', value: '2026-01-01' })]));
    expect(result[0].field_name).toBe('shipped_on_board_date');
    expect(result[0].value).toBe('2026-01-01');
  });

  it('vessel + voyage_no는 vessel_voyage 하나로 합쳐지고 bbox는 합집합', () => {
    const result = toDraftFields(
      draft([
        wireField({ name: 'vessel', value: 'EVER GIVEN', confidence: 0.9, bbox: [0.1, 0.1, 0.3, 0.2] }),
        wireField({ name: 'voyage_no', value: '123E', confidence: 0.8, bbox: [0.4, 0.1, 0.5, 0.2] }),
      ]),
    );
    const merged = result.find((f) => f.field_name === 'vessel_voyage');
    expect(merged?.value).toBe('EVER GIVEN / 123E');
    expect(merged?.bbox).toEqual([0.1, 0.1, 0.5, 0.2]);
    // 합친 필드의 신뢰도는 두 값 중 더 낮은 쪽을 따름 (근거 없이 부풀리지 않음)
    expect(merged?.confidence).toBe(0.8);
    expect(result.some((f) => f.field_name === 'vessel' || f.field_name === 'voyage_no')).toBe(false);
  });

  it('bbox가 없는 필드는 근거 없음이라 page도 null', () => {
    const result = toDraftFields(draft([wireField({ bbox: null })]), 1);
    expect(result[0].bbox).toBeNull();
    expect(result[0].page).toBeNull();
  });

  it('source가 llm이면 extractor는 ocr+llm, 그 외(region/anchor)는 rule로 뭉뚱그림', () => {
    const result = toDraftFields(draft([wireField({ source: 'llm' }), wireField({ name: 'consignee', source: 'anchor' })]));
    expect(result[0].extractor).toBe('ocr+llm');
    expect(result[1].extractor).toBe('rule');
  });

  // 텍스트 레이어 PDF는 전 필드가 confidence 1.0으로 온다. 그 값이 올바른
  // 필드에 꽂혔는지는 needs_review가 따로 알려주므로, 그걸 버리면 틀린 값이
  // "확정"으로 표시돼 아무도 확인하지 않는다.
  it('needs_review면 confidence 1.0이어도 필수 확인 등급으로 내려감', () => {
    const result = toDraftFields(
      draft([
        wireField({
          value: 'Consignee NORDWIND HANDELS GMBH',
          confidence: 1.0,
          needs_review: true,
          review_reason: 'label_echoed',
        }),
      ]),
    );
    expect(toConfidenceGrade(result[0])).toBe('REQUIRED');
  });

  it('needs_review가 아니면 confidence를 그대로 둠', () => {
    const result = toDraftFields(draft([wireField({ confidence: 1.0, needs_review: false })]));
    expect(result[0].confidence).toBe(1.0);
    expect(toConfidenceGrade(result[0])).toBe('CONFIRMED');
  });

  it('좌표 없이 확인 대상이어도 출처 없음이 아니라 필수 확인으로 남음', () => {
    const result = toDraftFields(
      draft([wireField({ value: 'Measurement', bbox: null, confidence: 1.0, needs_review: true })]),
    );
    expect(toConfidenceGrade(result[0])).toBe('REQUIRED');
  });

  it('vessel/voyage 중 하나만 확인 대상이어도 합친 필드가 확인 대상', () => {
    const result = toDraftFields(
      draft([
        wireField({ name: 'vessel', value: 'EVER GIVEN', confidence: 1.0, needs_review: true }),
        wireField({ name: 'voyage_no', value: '123E', confidence: 1.0, needs_review: false }),
      ]),
    );
    const merged = result.find((f) => f.field_name === 'vessel_voyage');
    expect(toConfidenceGrade(merged!)).toBe('REQUIRED');
  });
});
