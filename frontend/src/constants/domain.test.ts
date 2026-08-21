import { describe, expect, it } from 'vitest';
import { canTransitionToVerified } from './domain';

describe('canTransitionToVerified (M-1)', () => {
  it('필수 확인 필드도 미해결 Critical도 없으면 통과', () => {
    const result = canTransitionToVerified({ requiredFieldCount: 0, unresolvedCriticalCount: 0 });
    expect(result.allowed).toBe(true);
    expect(result.blockers).toEqual([]);
  });

  it('필수 확인 필드가 남아 있으면 막고, 사유 기록으로 우회 가능', () => {
    const result = canTransitionToVerified({ requiredFieldCount: 2, unresolvedCriticalCount: 0 });
    expect(result.allowed).toBe(false);
    expect(result.overridable).toBe(true);
    expect(result.blockers).toHaveLength(1);
  });

  it('미해결 Critical 위반이 있으면 막음', () => {
    const result = canTransitionToVerified({ requiredFieldCount: 0, unresolvedCriticalCount: 1 });
    expect(result.allowed).toBe(false);
    expect(result.blockers).toHaveLength(1);
  });

  it('두 조건 모두 걸리면 blocker가 2건', () => {
    const result = canTransitionToVerified({ requiredFieldCount: 1, unresolvedCriticalCount: 1 });
    expect(result.blockers).toHaveLength(2);
  });
});
