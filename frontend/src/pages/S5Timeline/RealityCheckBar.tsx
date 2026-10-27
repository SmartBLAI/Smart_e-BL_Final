import { useState } from 'react';
import { Loader2, Play } from 'lucide-react';
import { ApiError } from '../../api/client';

/**
 * "현실 대조 실행" — 울산항 VTS 관제 기록과 B/L을 대조하도록 게이트웨이에 요청합니다.
 * 실패하면 사유를 그 자리에 밝힙니다 (조용히 빈 타임라인으로 두지 않음).
 */
export function RealityCheckBar({ onRun }: { onRun: () => Promise<void> }) {
  const [running, setRunning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleClick() {
    setRunning(true);
    setError(null);
    try {
      await onRun();
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : '현실 대조에 실패했습니다. 잠시 후 다시 시도하세요.');
    } finally {
      setRunning(false);
    }
  }

  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
      <button
        type="button"
        className="btn btn-primary"
        onClick={handleClick}
        disabled={running}
        style={{ gap: 6, padding: '8px 16px', fontSize: 13, fontWeight: 600 }}
      >
        {running ? <Loader2 size={14} className="spin" aria-hidden="true" /> : <Play size={14} aria-hidden="true" />}
        {running ? '대조 중…' : '현실 대조 실행'}
      </button>
      {error !== null && (
        <span role="alert" style={{ fontSize: 12.5, color: 'var(--severity-critical)' }}>
          {error}
        </span>
      )}
    </div>
  );
}
