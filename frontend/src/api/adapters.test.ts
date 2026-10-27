import { describe, expect, it } from 'vitest';
import { toBLPayload, toScreenFieldName } from './adapters';
import type { FieldValue } from '../types/domain';

function field(overrides: Partial<FieldValue> = {}): FieldValue {
  return {
    field_name: 'shipper',
    value: 'ACME',
    normalized_value: 'ACME',
    confidence: 0.9,
    source_doc_id: null,
    page: null,
    bbox: null,
    extractor: 'rule',
    conflict_flag: false,
    ...overrides,
  };
}

describe('toBLPayload', () => {
  it('vessel_voyage는 " / "로 나눠 vessel·voyage_no 두 키로 보냄', () => {
    const bl = toBLPayload([field({ field_name: 'vessel_voyage', value: 'HMM ALGECIRAS / 2608E' })]);
    expect(bl.vessel).toBe('HMM ALGECIRAS');
    expect(bl.voyage_no).toBe('2608E');
  });

  it('vessel_voyage에 구분자가 없으면 전체를 vessel로 보냄', () => {
    const bl = toBLPayload([field({ field_name: 'vessel_voyage', value: 'HMM ALGECIRAS' })]);
    expect(bl.vessel).toBe('HMM ALGECIRAS');
    expect(bl.voyage_no).toBeUndefined();
  });

  it('vessel_voyage에 구분자가 두 번 있으면 첫 구분자에서만 나눠 세 번째 조각을 잃지 않음', () => {
    const bl = toBLPayload([field({ field_name: 'vessel_voyage', value: 'HMM ALGECIRAS / 2608E / A' })]);
    expect(bl.vessel).toBe('HMM ALGECIRAS');
    expect(bl.voyage_no).toBe('2608E / A');
  });

  it('shipped_on_board_date는 on_board_date로 이름만 바뀜', () => {
    const bl = toBLPayload([field({ field_name: 'shipped_on_board_date', value: '2026-01-01' })]);
    expect(bl.on_board_date).toBe('2026-01-01');
    expect(bl.shipped_on_board_date).toBeUndefined();
  });
});

describe('toScreenFieldName', () => {
  it('룰 어휘를 화면 필드 이름으로, 모르는 이름은 그대로', () => {
    expect(toScreenFieldName('on_board_date')).toBe('shipped_on_board_date');
    expect(toScreenFieldName('vessel')).toBe('vessel_voyage');
    expect(toScreenFieldName('port_of_loading')).toBe('port_of_loading');
  });
});
