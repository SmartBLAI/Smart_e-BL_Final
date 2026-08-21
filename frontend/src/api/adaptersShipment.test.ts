import { describe, expect, it } from 'vitest';
import { toWireFieldValueIn } from './adaptersShipment';
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
  it('원래 NOT_FOUND(값 없음)이던 필드에 값을 넣고 편집됨으로 저장하면 CONFIRMED로 보내고 value도 살아있음', () => {
    // 원래 미검출: 값 없음 · bbox 없음 · confidence 0
    const edited = field({ value: 'BUSAN', bbox: null, confidence: 0 });
    const wire = toWireFieldValueIn(edited, true);
    expect(wire.grade).toBe('CONFIRMED');
    expect(wire.value).toBe('BUSAN');
  });

  it('편집하지 않은 필드는 toConfidenceGrade 계산을 그대로 씀(NOT_FOUND면 NOT_FOUND)', () => {
    const untouched = field({ value: 'BUSAN', bbox: null, confidence: 0 });
    const wire = toWireFieldValueIn(untouched, false);
    expect(wire.grade).toBe('NOT_FOUND');
  });
});
