import { describe, expect, it } from 'vitest';
import { visibleCitations } from './ExplanationBlock';
import type { Explanation } from '../types/domain';

function explanation(overrides: Partial<Explanation> = {}): Explanation {
  return {
    target_id: 'VD-002',
    narrative: 'test',
    citations: [],
    generated_by: 'LLM',
    integrity: 'REPAIRED',
    dropped_citations: 1,
    generated_at: '2026-08-12T01:32:00Z',
    ...overrides,
  };
}

describe('visibleCitations', () => {
  it('verified: false인 인용(허위 인용으로 검증기가 걸러낸 것)은 화면에 내보내지 않는다', () => {
    const e = explanation({
      citations: [
        { citation_id: 'CIT-005', kind: 'FIELD', ref: 'port_of_loading', snippet: 'BUSAN', verified: true },
        {
          citation_id: 'CIT-006',
          kind: 'FIELD',
          ref: 'customs_declaration_no',
          snippet: '실재하지 않는 근거',
          verified: false,
        },
      ],
    });

    const result = visibleCitations(e);

    expect(result).toHaveLength(1);
    expect(result.map((c) => c.citation_id)).toEqual(['CIT-005']);
    expect(result.every((c) => c.verified)).toBe(true);
  });

  it('전부 verified: true면 그대로 전부 남는다', () => {
    const e = explanation({
      citations: [
        { citation_id: 'CIT-001', kind: 'CLAUSE', ref: 'R-UCP-14C', snippet: '조문', verified: true },
        { citation_id: 'CIT-002', kind: 'FIELD', ref: 'bl_no', snippet: 'HLCUBUS2608001', verified: true },
      ],
    });

    expect(visibleCitations(e)).toHaveLength(2);
  });
});
