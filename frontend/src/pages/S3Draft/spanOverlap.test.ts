import { describe, expect, it } from 'vitest';
import { spansOverlap } from './spanOverlap';

describe('spansOverlap', () => {
  it('겹치는 두 구간은 true, 맞닿기만 하고 겹치지 않는 구간은 false', () => {
    // mockOverlappingSuggestions와 같은 값 — {0,14}와 {8,22}는 8~14 구간이 겹칩니다
    expect(spansOverlap({ start: 0, end: 14 }, { start: 8, end: 22 })).toBe(true);
    // 끝과 시작이 맞닿기만 하면(5 === 5) 겹치는 게 아닙니다
    expect(spansOverlap({ start: 0, end: 5 }, { start: 5, end: 10 })).toBe(false);
  });
});
