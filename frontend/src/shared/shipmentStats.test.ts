import { describe, expect, it } from 'vitest';
import { countRequiredFields, effectiveGradeOf, resolveConflicts, summarizeVerdicts } from './shipmentStats';
import type { FieldValue, Verdict } from '../types/domain';

function field(overrides: Partial<FieldValue> = {}): FieldValue {
  return {
    field_name: 'shipper',
    value: 'ACME',
    normalized_value: 'ACME',
    confidence: 0.9,
    source_doc_id: 'doc-1',
    page: 1,
    bbox: [0.1, 0.1, 0.2, 0.2],
    extractor: 'rule',
    conflict_flag: false,
    ...overrides,
  };
}

function verdict(overrides: Partial<Verdict> = {}): Verdict {
  return {
    verdict_id: 'v1',
    rule_id: 'R1',
    target_fields: [],
    result: 'VIOLATION',
    severity: 'Warning',
    message: 'test',
    action_hint: null,
    evidence: { clause_text: '' },
    judged_at: '2026-01-01T00:00:00Z',
    rule_version: '1',
    model_version: null,
    ...overrides,
  };
}

describe('effectiveGradeOf', () => {
  it('직접 고친 값은 원래 신뢰도와 무관하게 CONFIRMED (M-2)', () => {
    const f = field({ field_name: 'shipper', confidence: 0.1, bbox: null });
    expect(effectiveGradeOf(f, { shipper: 'NEW VALUE' })).toBe('CONFIRMED');
  });

  it('안 고친 필드는 confidence 기반 등급을 그대로 씀', () => {
    const f = field({ confidence: 0.95 });
    expect(effectiveGradeOf(f, {})).toBe('CONFIRMED');
  });

  it('값은 안 고쳐도 confirmedFields에 있으면 CONFIRMED', () => {
    const f = field({ field_name: 'shipper', confidence: 0.5 });
    expect(effectiveGradeOf(f, {}, { shipper: true })).toBe('CONFIRMED');
  });

  it('confirmedFields에 없는 필드는 영향 없음', () => {
    const f = field({ field_name: 'shipper', confidence: 0.5 });
    expect(effectiveGradeOf(f, {}, { other_field: true })).toBe('REQUIRED');
  });
});

describe('countRequiredFields', () => {
  it('필수 확인 등급(확인 권고 임계값 미만)인 필드 수만 셈', () => {
    const fields = [field({ field_name: 'a', confidence: 0.5 }), field({ field_name: 'b', confidence: 0.95 })];
    expect(countRequiredFields(fields)).toBe(1);
  });

  it('값 충돌(conflict_flag)이 있으면 신뢰도가 높아도 필수 확인으로 셈', () => {
    const fields = [field({ field_name: 'a', confidence: 0.95, conflict_flag: true })];
    expect(countRequiredFields(fields)).toBe(1);
  });

  it('"값 확인함"으로 확인한 필드는 건수에서 빠짐 (대시보드 카드·S3 공통)', () => {
    const fields = [field({ field_name: 'a', confidence: 0.5 }), field({ field_name: 'b', confidence: 0.5 })];
    expect(countRequiredFields(fields, {}, { a: true })).toBe(1);
    expect(countRequiredFields(fields, {}, { a: true, b: true })).toBe(0);
  });
});

describe('countRequiredFields 서버 grade', () => {
  it('서버 CONFIRMED는 신뢰도가 낮아도 확인된 것으로 셈', () => {
    const fields = [field({ field_name: 'a', confidence: 0.5, grade: 'CONFIRMED' }), field({ field_name: 'b', confidence: 0.5 })];
    expect(countRequiredFields(fields)).toBe(1);
  });
});

describe('summarizeVerdicts', () => {
  it('DEFERRED는 심각도 집계에서 빠지고 deferred로만 잡힘', () => {
    const verdicts: Verdict[] = [
      verdict({ verdict_id: 'v1', severity: 'Critical', result: 'DEFERRED' }),
      verdict({ verdict_id: 'v2', severity: 'Warning', result: 'VIOLATION' }),
    ];
    const counts = summarizeVerdicts(verdicts);
    expect(counts.bySeverity.Critical).toBe(0);
    expect(counts.bySeverity.Warning).toBe(1);
    expect(counts.deferred).toBe(1);
    expect(counts.total).toBe(2);
  });
});

describe('resolveConflicts', () => {
  it('고른 후보의 confidence를 그대로 승계 (직접 입력과 다르게 CONFIRMED로 안 올림)', () => {
    const f = field({
      field_name: 'port_of_loading',
      value: 'BUSAN',
      confidence: 0.9,
      conflict_flag: true,
      candidates: [
        field({ field_name: 'port_of_loading', value: 'BUSAN', confidence: 0.9, source_doc_id: 'doc-1' }),
        field({ field_name: 'port_of_loading', value: 'INCHEON', confidence: 0.71, source_doc_id: 'doc-2' }),
      ],
    });
    const resolved = resolveConflicts([f], { port_of_loading: 'INCHEON' });
    expect(resolved[0].value).toBe('INCHEON');
    expect(resolved[0].confidence).toBe(0.71);
    expect(resolved[0].conflict_flag).toBe(false);
  });

  it('resolved에 없는 필드는 그대로 통과', () => {
    const f = field({ field_name: 'shipper' });
    const resolved = resolveConflicts([f], {});
    expect(resolved[0]).toEqual(f);
  });
});
