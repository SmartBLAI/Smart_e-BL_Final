import type { CSSProperties } from 'react';
import { AlertTriangle } from 'lucide-react';
import { labelOfField } from '../../constants/domain';

const warningBoxStyle: CSSProperties = {
  display: 'flex',
  alignItems: 'flex-start',
  gap: 6,
  padding: 'var(--space-2)',
  borderRadius: 6,
  backgroundColor: 'var(--severity-warning-bg)',
  border: '1px solid var(--severity-warning)',
};

interface OverlapWarningProps {
  field: string;
  count: number;
}

/** span(글자 범위) 겹치는 교정 제안 경고 한 줄 (요구사항 7) */
export function OverlapWarning({ field, count }: OverlapWarningProps) {
  return (
    <div style={warningBoxStyle}>
      <AlertTriangle size={14} color="var(--severity-warning)" aria-hidden="true" />
      <span style={{ fontSize: 12, color: 'var(--severity-warning)' }}>
        {labelOfField(field)} 교정 제안 {count}건의 수정 범위가 겹칩니다 — 동시에 승인하면 나중
        것이 앞 것을 덮어씁니다.
      </span>
    </div>
  );
}
