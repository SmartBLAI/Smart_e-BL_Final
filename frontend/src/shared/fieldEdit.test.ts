import { describe, expect, it } from 'vitest';
import { replaceField, withEditedValue } from './fieldEdit';
import type { ShipmentMockData } from '../mocks/shipmentData';
import type { FieldValue } from '../types/domain';

const base: FieldValue = {
  field_name: 'shipper', value: 'A', normalized_value: 'a', confidence: 0.5, source_doc_id: 'd',
  page: 1, bbox: [0.1, 0.1, 0.2, 0.2], extractor: 'rule', conflict_flag: false,
};
const store = (f: FieldValue) =>
  [{ shipment: { shipment_id: 's1' }, fields: [f] }] as unknown as ShipmentMockData[];

describe('withEditedValue', () => {
  it('값을 바꾸고 정규화값을 비우며, 고쳐도 확정으로 올리지 않음', () => {
    const e = withEditedValue(base, 'B');
    expect([e.value, e.normalized_value, e.grade]).toEqual(['B', null, 'REQUIRED']);
  });
  it('미검출이던 필드에 값을 넣으면 REQUIRED, 비우면 NOT_FOUND', () => {
    const nf = { ...base, value: null, bbox: null, confidence: 0 };
    expect(withEditedValue(nf, 'X').grade).toBe('REQUIRED');
    expect(withEditedValue(base, null).grade).toBe('NOT_FOUND');
  });
});

describe('replaceField (낙관적 갱신 → 롤백)', () => {
  it('바꿨다가 원래 필드로 되돌리면 원상복구', () => {
    const s0 = store(base);
    const s1 = replaceField(s0, 's1', withEditedValue(base, 'B'));
    expect(s1[0].fields[0].value).toBe('B');
    expect(replaceField(s1, 's1', base)[0].fields[0]).toEqual(base);
    expect(replaceField(s0, 'other', base)).toEqual(s0);
  });
});
