import { AlertTriangle, RadioTower } from 'lucide-react';
import type { AdapterStatus, VesselMatch } from '../../types/domain';
import { EVENT_SOURCE_LABEL, VESSEL_MATCH_LABEL } from '../../constants/domain';

/**
 * F6 어댑터 상태 배너 — 타임라인 맨 위에 둡니다.
 *
 * 이 화면이 보여주는 건 세관 기록이 아니라 **울산항 안에서의 선박 이동
 * 관제(VTS) 기록**입니다. "세관"·"통관"이라는 말은 절대 쓰지 않습니다
 * (근거: f6-customs-reality-check.md §1). coverage_note는 항상 같이
 * 보여줘야 합니다 — "기록이 없음"과 "이상 없음"을 같은 문장으로 뭉개지
 * 않기 위한 최소 장치입니다.
 */
export function AdapterBanner({
  status,
  vesselMatch,
}: {
  status: AdapterStatus;
  vesselMatch: VesselMatch;
}) {
  const isWarn = !status.connected || status.consecutive_failures > 0;
  const syncText =
    status.last_synced_at === null
      ? '동기화 기록 없음'
      : new Date(status.last_synced_at).toLocaleString('ko-KR');

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        padding: 'var(--space-2) var(--space-3)',
        fontSize: 13,
        lineHeight: 1.6,
        border: '1px solid var(--border-default)',
        borderLeft: isWarn ? '4px solid var(--severity-warning)' : '4px solid var(--border-default)',
        borderRadius: 'var(--radius-card)',
        backgroundColor: isWarn ? 'var(--severity-warning-bg)' : 'var(--bg-card)',
        textAlign: 'left',
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', gap: 6 }}>
        {isWarn ? (
          <AlertTriangle size={14} color="var(--severity-warning)" aria-hidden="true" />
        ) : (
          <RadioTower size={14} color="var(--text-secondary)" aria-hidden="true" />
        )}
        <strong style={{ color: 'var(--text)' }}>출처 {EVENT_SOURCE_LABEL[status.name]}</strong>
      </div>

      <span style={{ color: 'var(--text-secondary)' }}>최종 동기화 {syncText}</span>

      {isWarn && (
        <strong style={{ color: 'var(--severity-warning)' }}>
          조회 실패 — 아래 구간은 데이터 부족입니다
        </strong>
      )}

      <span style={{ color: 'var(--text-muted)' }}>{status.coverage_note}</span>

      <VesselMatchLine match={vesselMatch} />
    </div>
  );
}

/**
 * 선명 → 콜사인 해소 표기 (§3.2).
 * B/L에는 콜사인 칸이 없어 이름으로 조인할 수밖에 없다는 사실을, 어떤
 * 경로로 배를 특정했는지와 함께 밝힙니다.
 */
function VesselMatchLine({ match }: { match: VesselMatch }) {
  const isUnresolved = match.method === 'AMBIGUOUS' || match.method === 'NOT_FOUND';
  return (
    <span style={{ color: isUnresolved ? 'var(--severity-warning)' : 'var(--text-secondary)' }}>
      {match.bl_vessel !== '' && (
        <>
          {match.bl_vessel}
          {match.bl_vessel !== match.normalized && <> → {match.normalized}</>}
          {match.call_sign !== null && <> → 콜사인 {match.call_sign}</>}
          {' '}
        </>
      )}
      ({VESSEL_MATCH_LABEL[match.method]})
      {isUnresolved && ' — 배를 특정하지 못해 이 구간은 판정하지 않습니다'}
    </span>
  );
}
