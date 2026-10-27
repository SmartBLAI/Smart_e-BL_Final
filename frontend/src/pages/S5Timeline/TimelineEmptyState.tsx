import { AlertTriangle, SatelliteDish } from 'lucide-react';
import type { AdapterStatus } from '../../types/domain';
import { EmptyState } from '../../components/EmptyState';

/**
 * 이벤트 0건일 때의 두 갈래 (§5.6 "데이터 없음 ≠ 이상 없음").
 *
 * - 어댑터는 붙었는데 이 선적의 기록이 없음 → "볼 수 없음"으로 읽히게
 * - 어댑터 연결 자체가 실패 → 데이터 부족을 경고 톤으로 밝힘
 * 두 문장을 절대 같은 자리에서 같은 톤으로 쓰지 않습니다.
 */
export function TimelineEmptyState({ status }: { status: AdapterStatus | null }) {
  if (status === null) {
    // 어댑터 상태 정보 자체가 없는 선적 — 목데이터엔 없지만 타입상 가능
    return <EmptyState icon={AlertTriangle} message="F6 어댑터 연동 정보가 없습니다." />;
  }

  const syncText =
    status.last_synced_at === null
      ? '동기화 기록 없음'
      : new Date(status.last_synced_at).toLocaleString('ko-KR');

  const isFailed = !status.connected || status.consecutive_failures > 0;

  if (isFailed) {
    return (
      <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-2)' }}>
        <AlertTriangle size={32} color="var(--severity-warning)" aria-hidden="true" />
        <p style={{ margin: 0, color: 'var(--severity-warning)', fontWeight: 600 }}>
          데이터 부족 — 조회에 실패했습니다.
        </p>
        <p style={{ margin: 0, fontSize: 12.5, color: 'var(--text-muted)', textAlign: 'center' }}>
          {status.coverage_note}
          {status.consecutive_failures > 0 && ` · 연속 실패 ${status.consecutive_failures}회`}
        </p>
      </div>
    );
  }

  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 'var(--space-2)' }}>
      <EmptyState icon={SatelliteDish} message="울산항 관제 기록이 없습니다." />
      <p style={{ margin: 0, fontSize: 12.5, color: 'var(--text-muted)', textAlign: 'center' }}>
        {status.coverage_note} · 최종 동기화 {syncText}
      </p>
    </div>
  );
}
