import { StatusBadge } from '../../components/StatusBadge';
import type { ShipmentMockData } from '../../mocks/shipmentData';

/**
 * 선적별 그룹 헤더 — B/L 번호 · 상태 뱃지 · L/C 번호.
 * 원래 index.tsx에 있었으나 200줄 제한 때문에 옮겨왔습니다.
 */
export function ShipmentGroupHeader({ data, count }: { data: ShipmentMockData; count: string }) {
  const { shipment } = data;

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-2)',
        flexWrap: 'wrap',
        padding: '12px 18px',
        border: '1px solid var(--border-default)',
        // 모서리는 .alert-group이 정합니다 — 여기서 인라인으로 주면 첫/마지막
        // 카드만 깎는 규칙을 덮어버립니다
        backgroundColor: 'var(--bg-card)',
      }}
    >
      {shipment.bl_no !== null ? (
        <strong style={{ fontSize: 15.5, letterSpacing: '-0.2px' }}>{shipment.bl_no}</strong>
      ) : (
        <span style={{ fontSize: 15, color: 'var(--text-muted)', fontStyle: 'italic' }}>
          B/L 번호 미발급
        </span>
      )}
      <StatusBadge status={shipment.status} />
      <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
        L/C {shipment.lc_no ?? '-'}
      </span>
      <div style={{ flex: 1, minWidth: 'var(--space-2)' }} />
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{count}</span>
    </div>
  );
}
