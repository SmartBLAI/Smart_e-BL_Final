import { describe, expect, it } from 'vitest';
import { toShipmentAndFields, toWireFieldValueIn } from './adaptersShipment';
import type { WireShipmentDetailResponse } from './wireShipment';
import type { FieldValue } from '../types/domain';

function field(overrides: Partial<FieldValue> = {}): FieldValue {
  return {
    field_name: 'place_of_issue',
    value: 'BUSAN',
    normalized_value: null,
    confidence: 0.9,
    source_doc_id: 'doc-1',
    page: 1,
    bbox: [0.1, 0.1, 0.2, 0.2],
    extractor: 'rule',
    conflict_flag: false,
    ...overrides,
  };
}

describe('toWireFieldValueIn', () => {
  it('FieldValue.grade가 있으면 그대로, 없으면 toConfidenceGrade 계산', () => {
    expect(toWireFieldValueIn(field({ grade: 'REQUIRED', confidence: 0.99 })).grade).toBe('REQUIRED');
    expect(toWireFieldValueIn(field({ value: 'BUSAN', bbox: null, confidence: 0 })).grade).toBe('NOT_FOUND');
  });
});

describe('toShipmentAndFields grade', () => {
  const wireField = {
    field_name: 'shipper', value: 'A', normalized_value: null, confidence: 0.5, source_doc_id: null,
    page: 1, bbox: [0.1, 0.1, 0.2, 0.2], extractor: 'rule', conflict_flag: false,
  };
  const detail = (f: object) =>
    ({ shipment_id: 's1', status: 'DRAFT', fields: [f], documents: [], verdicts: [], prediction: null }) as unknown as WireShipmentDetailResponse;

  it('서버 grade를 FieldValue로 옮기고, 없으면 undefined', () => {
    expect(toShipmentAndFields(detail({ ...wireField, grade: 'CONFIRMED' })).fields[0].grade).toBe('CONFIRMED');
    expect(toShipmentAndFields(detail(wireField)).fields[0].grade).toBeUndefined();
  });
});

describe('toShipmentAndFields 검증 스냅샷', () => {
  const base = {
    shipment_id: 's1', bl_no: null, status: 'DRAFT', updated_at: '2026-01-01T00:00:00Z',
    fields: [], documents: [],
  } as unknown as WireShipmentDetailResponse;

  it('저장된 판정·하자확률을 번역 없이 그대로 내려줌', () => {
    const verdicts = [{ rule_id: 'D001' }];
    const prediction = { defect_probability: 0.4 };
    const out = toShipmentAndFields({ ...base, verdicts, prediction } as unknown as WireShipmentDetailResponse);
    expect(out.verdicts).toBe(verdicts);
    expect(out.prediction).toBe(prediction);
  });

  it('한 번도 검증 안 했으면 빈 배열 / null (대시보드가 "검증 전"으로 표시)', () => {
    const out = toShipmentAndFields({ ...base, verdicts: [], prediction: null } as WireShipmentDetailResponse);
    expect(out.verdicts).toEqual([]);
    expect(out.prediction).toBeNull();
  });
});
