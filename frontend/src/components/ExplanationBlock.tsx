/**
 * F7 — AI 판정 설명. "무엇을 위반했는가"(F3 판정) 옆에 "왜 그런가"를 붙입니다.
 *
 * 근거 없는 값은 표시하지 않는다(CLAUDE.md §4)는 규칙이 여기서는 인용
 * 단위로 적용됩니다 — 출력 검증기가 실재를 확인 못 한 인용(`verified:
 * false`)은 없는 조문·필드를 인용한 것이므로 절대 렌더하지 않고,
 * 대신 몇 건을 걸렀는지(`dropped_citations`)만 밝힙니다.
 *
 * 두 화면(S4 판정 결과 · S6 경보 센터) 이상이 같은 부품을 쓸 예정이라
 * `src/components/`에 둡니다(CLAUDE.md 폴더 구조 규칙).
 */
import { ShieldAlert, ShieldCheck, Sparkles, FileCode2 } from 'lucide-react';
import type { Citation, Explanation, RealityEvent } from '../types/domain';
import { CITATION_INTEGRITY_LABEL, EXPLANATION_SOURCE_LABEL } from '../constants/domain';
import { InfoTip } from './InfoTip';
import { CitationChip } from './CitationChip';

interface ExplanationBlockProps {
  explanation: Explanation | null;
  /** kind: 'EVENT' 인용을 사람이 읽을 이벤트로 바꿀 때 씁니다. 없으면 ref만 보여줍니다 */
  realityEvents?: RealityEvent[];
}

/**
 * 실제로 화면에 그릴 인용만 골라냅니다. `verified: false`는 검증기가 실재를
 * 확인하지 못한 인용이라 여기서 걸러집니다 — 이 절 하나가 "허위 인용을
 * 렌더하지 않는다"는 규칙을 강제합니다. 컴포넌트 밖으로 뺀 순수 함수라
 * React 렌더러 없이도(vitest) 이 규칙을 테스트할 수 있습니다.
 */
export function visibleCitations(explanation: Explanation): Citation[] {
  return explanation.citations.filter((c) => c.verified);
}

export function ExplanationBlock({ explanation, realityEvents = [] }: ExplanationBlockProps) {
  // 설명 자체가 없는 판정도 있습니다(§F7 축소 구현 대상 밖). "설명 없음" 상자를
  // 그리면 화면만 시끄러워지므로 아무것도 렌더하지 않습니다.
  if (explanation === null) return null;

  const isTemplate = explanation.generated_by === 'TEMPLATE';
  const citations = visibleCitations(explanation);
  const integrityNeedsAttention = explanation.integrity !== 'PASS';

  return (
    <details style={{ marginTop: 4 }}>
      <summary style={{ cursor: 'pointer', fontSize: 13.5, fontWeight: 600, color: 'var(--brand-primary)' }}>
        이 판정의 근거 보기
      </summary>

      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 'var(--space-2)',
          marginTop: 'var(--space-2)',
          paddingTop: 'var(--space-2)',
          borderTop: '1px solid var(--border-default)',
        }}
      >
        <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
          {/* 생성 출처 배지 — TEMPLATE(폴백)을 'AI 생성'처럼 보이게 하면 안 됩니다(F4와 같은 규약) */}
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              padding: '2px 8px',
              borderRadius: 999,
              fontSize: 12,
              fontWeight: 600,
              color: isTemplate ? 'var(--text-secondary)' : 'var(--brand-primary)',
              border: `1px solid ${isTemplate ? 'var(--border-default)' : 'var(--brand-primary)'}`,
              backgroundColor: isTemplate ? 'transparent' : 'var(--brand-primary-light)',
            }}
          >
            {isTemplate ? <FileCode2 size={12} aria-hidden="true" /> : <Sparkles size={12} aria-hidden="true" />}
            {EXPLANATION_SOURCE_LABEL[explanation.generated_by]}
          </span>
          {isTemplate && <InfoTip text="LLM 생성에 실패해 정해진 문장으로 대체했습니다." />}

          {/* 인용 무결성 배지 — PASS는 조용하게, REPAIRED/FALLBACK은 경고 톤으로 */}
          <span
            style={{
              display: 'inline-flex',
              alignItems: 'center',
              gap: 4,
              fontSize: integrityNeedsAttention ? 12 : 11.5,
              fontWeight: integrityNeedsAttention ? 600 : 400,
              padding: integrityNeedsAttention ? '2px 8px' : 0,
              borderRadius: 999,
              color: integrityNeedsAttention ? 'var(--severity-warning)' : 'var(--text-muted)',
              backgroundColor: integrityNeedsAttention ? 'var(--severity-warning-bg)' : 'transparent',
            }}
          >
            {integrityNeedsAttention ? (
              <ShieldAlert size={12} aria-hidden="true" />
            ) : (
              <ShieldCheck size={11} aria-hidden="true" />
            )}
            {CITATION_INTEGRITY_LABEL[explanation.integrity]}
          </span>
        </div>

        {integrityNeedsAttention && explanation.dropped_citations > 0 && (
          <p style={{ margin: 0, fontSize: 13, color: 'var(--severity-warning)' }}>
            실재하지 않는 인용 {explanation.dropped_citations}건을 제거했습니다.
          </p>
        )}

        <p style={{ margin: 0, fontSize: 14, lineHeight: 1.6 }}>{explanation.narrative}</p>

        {citations.length === 0 ? (
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
            인용 근거 없음 — 서술만 제공됩니다.
          </p>
        ) : (
          <ul style={{ margin: 0, padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: 8 }}>
            {citations.map((c) => (
              <CitationChip key={c.citation_id} citation={c} realityEvents={realityEvents} />
            ))}
          </ul>
        )}
      </div>
    </details>
  );
}
