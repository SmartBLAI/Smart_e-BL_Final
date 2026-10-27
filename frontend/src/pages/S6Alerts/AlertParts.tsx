import type { ReactNode } from 'react';
import { Info } from 'lucide-react';
import type { AlertStatus, FieldValue, RealityEvent, Suggestion } from '../../types/domain';
import { InfoTip } from '../../components/InfoTip';
import { GradeBadge } from '../../components/GradeBadge';
import { UNSETTLED_LABEL, labelOfField } from '../../constants/domain';
import { effectiveGradeOf } from '../../shared/shipmentStats';

/**
 * 경보·판정 보류 카드가 같이 쓰는 조각들.
 *
 * 근거를 좌우 두 칸으로 보여주는 틀과, 룰 코드·문서 ID·이벤트 코드를 접어두는
 * ⓘ 툴팁입니다. 화면에는 사람이 읽을 값만 남기고, 식별자는 툴팁으로 넘깁니다.
 * CauseField·AckBadge는 원래 AlertCard.tsx에 있었으나 200줄 제한 때문에
 * 옮겨왔습니다(AlertCard.tsx 상단 주석 참고).
 */

/** 근거 두 칸 배치. 좁은 화면에서는 자동으로 위아래로 쌓입니다 */
export function EvidenceColumns({ children }: { children: ReactNode }) {
  return (
    // 두 칸 배치와 세로 구분선은 index.css의 .evidence-columns가 맡습니다 —
    // 인라인 style로는 "두 번째 칸에만 왼쪽 선"이나 미디어쿼리를 못 씁니다
    <div
      className="evidence-columns"
      style={{
        padding: '16px 20px',
        borderTop: '1px solid var(--border-default)',
        backgroundColor: 'var(--bg-card)',
      }}
    >
      {children}
    </div>
  );
}

export function EvidencePanel({
  title,
  tip,
  children,
}: {
  title: string;
  /** 식별자처럼 화면에 안 보여도 되는 정보 — ⓘ에 접어둡니다 */
  tip?: string;
  children: ReactNode;
}) {
  return (
    <section style={{ display: 'flex', flexDirection: 'column', gap: 7, minWidth: 0 }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        <span
          style={{
            fontSize: 11.5,
            fontWeight: 700,
            letterSpacing: '0.02em',
            color: 'var(--text-secondary)',
          }}
        >
          {title}
        </span>
        {tip !== undefined && tip !== '' && <InfoTip text={tip} />}
      </div>
      {children}
    </section>
  );
}


/** RealityEvent.precision을 지킴 — DATE면 시각을 표시하지 않음 (§5.6) */
export function formatEventTime(event: RealityEvent): string {
  const date = new Date(event.occurred_at);
  return event.precision === 'DATE'
    ? date.toLocaleDateString('ko-KR')
    : date.toLocaleString('ko-KR');
}

// InfoTip은 S6·S8이 함께 쓰므로 src/components로 옮겼습니다.
// 이 폴더 안에서 쓰던 이름을 그대로 유지하기 위해 재수출합니다.
export { InfoTip };

/** 원인 필드의 지금 상태 — 등급 뱃지 + 값(충돌 중이면 "미확정") */
export function CauseField({
  field,
  suggestions,
}: {
  field: FieldValue;
  suggestions: Suggestion[];
}) {
  const grade = effectiveGradeOf(field, {});
  const pending = suggestions.filter((suggestion) => suggestion.field === field.field_name).length;
  const candidateCount = field.candidates?.length ?? 0;

  return (
    <>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
        <span style={{ fontSize: 13.5, fontWeight: 700, color: 'var(--text-primary)' }}>
          {labelOfField(field.field_name)}
        </span>
        <GradeBadge grade={grade} size="sm" />
      </div>

      {field.conflict_flag ? (
        // 충돌이 안 풀린 필드는 value에 후보 하나가 들어 있어도 확정값이 아닙니다.
        // S3 FieldRow와 같은 방식으로 "미확정"이라고 씁니다 (두 화면이 어긋나지 않게).
        <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', wordBreak: 'keep-all' }}>
          {UNSETTLED_LABEL} — 후보 {candidateCount}건 중 아직 고르지 않았습니다
        </span>
      ) : (
        <div style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}>
          <span style={{ fontSize: 11.5, fontWeight: 600, color: 'var(--text-muted)' }}>현재값</span>
          <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
            {field.value ?? '-'}
          </span>
        </div>
      )}

      {pending > 0 && (
        <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>교정 제안 {pending}건 대기</span>
      )}
    </>
  );
}

/** 미확인(OPEN) / 확인됨 / 화이트리스트 — status 가 없는 목데이터는 acknowledged 로 판단 */
export function AckBadge({ acknowledged, status }: { acknowledged: boolean; status?: AlertStatus }) {
  const label = status === 'WHITELISTED' ? '화이트리스트' : acknowledged ? '확인됨' : '미확인';
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 4,
        padding: '3px 9px',
        borderRadius: 999,
        fontSize: 12,
        fontWeight: 600,
        color: acknowledged ? 'var(--text-secondary)' : 'var(--brand-primary)',
        border: `1px solid ${acknowledged ? 'var(--border-default)' : 'var(--brand-primary)'}`,
        backgroundColor: acknowledged ? 'transparent' : 'var(--brand-primary-light)',
      }}
    >
      {!acknowledged && <Info size={12} aria-hidden="true" />}
      {label}
    </span>
  );
}
