import { Link } from 'react-router-dom';
import type { Alert, RealityEvent } from '../../types/domain';
import { EVENT_SOURCE_SHORT, REALITY_EVENT_LABEL, TRUST_GRADE_LABEL } from '../../constants/domain';
import { InfoTip } from '../../components/InfoTip';
import { SeverityBadge } from '../../components/SeverityBadge';

/** RealityEvent.precision을 지킴 — DATE면 시각을 표시하지 않음 (§5.6) */
function formatEventTime(event: RealityEvent): string {
  const date = new Date(event.occurred_at);
  return event.precision === 'DATE' ? date.toLocaleDateString('ko-KR') : date.toLocaleString('ko-KR');
}

/**
 * 타임라인 한 줄의 내용물 — 강조·스크롤을 위한 바깥 div(ref)는 index.tsx가
 * 감쌉니다. 이 컴포넌트는 이벤트 정보를 어떻게 읽어야 하는지 밝히는 부분만
 * 맡습니다.
 */
export function TimelineEvent({ event, alerts }: { event: RealityEvent; alerts: Alert[] }) {
  const isUnknown = event.event_type === 'UNKNOWN';

  return (
    <>
      <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', gap: 8 }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
          <strong>{REALITY_EVENT_LABEL[event.event_type]}</strong>
          {isUnknown && (
            <InfoTip
              text={`원본 코드 ${event.raw_code ?? '?'} — 모르는 관제 코드라 판정에서 제외되었습니다.`}
            />
          )}
        </span>
        <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>{formatEventTime(event)}</span>
      </div>

      {(event.facility !== null || event.voyage_no !== null) && (
        <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', display: 'flex', alignItems: 'center', gap: 4 }}>
          {event.facility !== null && event.facility}
          {event.facility !== null && event.voyage_no !== null && ' · '}
          {event.voyage_no !== null && (
            <>
              항차 {event.voyage_no}
              <InfoTip text="울산항 연번입니다 — 선사 항차번호가 아닙니다." />
            </>
          )}
        </span>
      )}

      <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
        출처 {EVENT_SOURCE_SHORT[event.source]} · {TRUST_GRADE_LABEL[event.trust_grade]}({event.trust_grade})
      </span>

      {alerts.length > 0 && (
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            flexWrap: 'wrap',
            paddingTop: 6,
            borderTop: '1px solid var(--border-default)',
          }}
        >
          {alerts.map((alert) => (
            <SeverityBadge key={alert.alert_id} severity={alert.severity} />
          ))}
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>경보 {alerts.length}건의 근거</span>
          <Link to="/alerts" style={{ fontSize: 12.5 }}>
            경보 센터에서 보기
          </Link>
        </div>
      )}
    </>
  );
}
