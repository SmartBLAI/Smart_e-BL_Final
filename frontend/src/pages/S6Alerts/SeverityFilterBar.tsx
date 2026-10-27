import type { Severity } from '../../types/domain';
import { SEVERITY } from '../../constants/domain';

const SEVERITIES: Severity[] = ['Critical', 'Warning', 'Info'];

interface SeverityFilterBarProps {
  /** 심각도별 경보 건수 — 필터와 무관하게 항상 전체 기준 */
  counts: Record<Severity, number>;
  total: number;
  /** 지금 선택된 심각도. null이면 "전체" */
  active: Severity | null;
  onChange: (severity: Severity | null) => void;
}

/**
 * 심각도 필터 버튼 — 전체 / 위반 / 주의 / 참고.
 *
 * 화면전이_정의.md §6의 `?severity=Critical` 규칙을 따릅니다. 각 버튼에
 * 건수를 같이 적어서, 눌러보기 전에 걸러질 게 있는지 없는지 미리 알 수
 * 있게 합니다. 라벨·색은 constants/domain.ts의 SEVERITY가 유일한 정의처입니다.
 */
export function SeverityFilterBar({ counts, total, active, onChange }: SeverityFilterBarProps) {
  return (
    <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
      <FilterButton
        label="전체"
        count={total}
        isActive={active === null}
        onClick={() => onChange(null)}
      />
      {SEVERITIES.map((severity) => (
        <FilterButton
          key={severity}
          label={SEVERITY[severity].label}
          count={counts[severity]}
          colorVar={SEVERITY[severity].colorVar}
          bgVar={SEVERITY[severity].bgVar}
          isActive={active === severity}
          onClick={() => onChange(severity)}
        />
      ))}
    </div>
  );
}

function FilterButton({
  label,
  count,
  colorVar = '--brand-primary',
  bgVar = '--brand-primary-light',
  isActive,
  onClick,
}: {
  label: string;
  count: number;
  colorVar?: string;
  bgVar?: string;
  isActive: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      onClick={onClick}
      aria-pressed={isActive}
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 5,
        padding: '5px 12px',
        borderRadius: 999,
        cursor: 'pointer',
        fontSize: 12.5,
        fontWeight: 600,
        fontFamily: 'inherit',
        border: `1px solid ${isActive ? `var(${colorVar})` : 'var(--border-default)'}`,
        backgroundColor: isActive ? `var(${bgVar})` : 'var(--bg)',
        color: isActive ? `var(${colorVar})` : 'var(--text-secondary)',
      }}
    >
      {label}
      <span style={{ opacity: 0.85 }}>{count}건</span>
    </button>
  );
}
