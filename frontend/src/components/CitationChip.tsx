/**
 * F7 인용 한 줄 — `ExplanationBlock`의 부품.
 *
 * `ExplanationBlock.tsx`가 150줄을 넘어서 CLAUDE.md §9(200줄 넘으면 부품
 * 쪼개기, 여기서는 스스로 정한 150줄 기준)에 따라 분리했습니다. 이 파일이
 * 렌더하는 인용은 이미 `visibleCitations`로 걸러진(= `verified: true`) 것만
 * 들어온다고 가정합니다 — 필터링 자체는 `ExplanationBlock.tsx`가 맡습니다.
 */
import { BookText, FileText, Ship } from 'lucide-react';
import type { Citation, CitationKind, RealityEvent } from '../types/domain';
import { CITATION_KIND_LABEL, REALITY_EVENT_LABEL, labelOfField } from '../constants/domain';

const KIND_ICON: Record<CitationKind, typeof BookText> = {
  CLAUSE: BookText,
  EVENT: Ship,
  FIELD: FileText,
};

/** kind별로 ref를 사람이 읽을 말로 바꿉니다. FIELD는 한글 필드명, EVENT는 이벤트 라벨+시각 */
function describeCitation(citation: Citation, realityEvents: RealityEvent[]): string {
  if (citation.kind === 'FIELD') return labelOfField(citation.ref);
  if (citation.kind === 'EVENT') {
    const event = realityEvents.find((e) => e.event_id === citation.ref);
    if (event === undefined) return `${citation.ref} — 이 화면에서는 확인할 수 없는 이벤트`;
    const date = new Date(event.occurred_at);
    const time = event.precision === 'DATE' ? date.toLocaleDateString('ko-KR') : date.toLocaleString('ko-KR');
    return `${REALITY_EVENT_LABEL[event.event_type]} — ${time}`;
  }
  return citation.ref; // CLAUSE — 조문 코드 자체가 이미 사람이 읽는 값
}

export function CitationChip({ citation, realityEvents }: { citation: Citation; realityEvents: RealityEvent[] }) {
  const Icon = KIND_ICON[citation.kind];

  return (
    <li style={{ display: 'flex', flexDirection: 'column', gap: 2, fontSize: 13.5 }}>
      <span style={{ display: 'inline-flex', alignItems: 'center', gap: 5, fontWeight: 600 }}>
        <Icon size={13} aria-hidden="true" style={{ color: 'var(--text-muted)' }} />
        {CITATION_KIND_LABEL[citation.kind]}
        <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}>
          {describeCitation(citation, realityEvents)}
        </span>
      </span>
      <span
        style={{
          marginLeft: 18,
          padding: '2px 8px',
          borderRadius: 4,
          fontSize: 12.5,
          color: 'var(--text-muted)',
          backgroundColor: 'var(--code-bg)',
        }}
      >
        “{citation.snippet}”
      </span>
    </li>
  );
}
