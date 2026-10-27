import { useState } from 'react';
import { ApiError } from '../../api/client';
import type { AlertStatus } from '../../types/domain';

interface AlertActionsProps {
  /** OPEN 은 두 버튼, ACKNOWLEDGED 는 정상 관행 등록만, 그 밖은 모두 숨깁니다 */
  status: AlertStatus;
  /** 이 선적의 콜사인 — 있으면 선박 단위, 없으면 테넌트 전체에 적용됩니다 */
  callSign?: string | null;
  onAcknowledge: () => Promise<void>;
  onWhitelist: (reason: string) => Promise<void>;
}

/**
 * 경보 처리 버튼 — "확인"(이 경보만) / "정상 관행 등록"(같은 룰의 이후 경보도 화이트리스트).
 * 사유는 window.prompt 대신 카드 안 인라인 입력으로 받습니다.
 */
export function AlertActions({ status, callSign, onAcknowledge, onWhitelist }: AlertActionsProps) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [reasonOpen, setReasonOpen] = useState(false);
  const [reason, setReason] = useState('');

  async function run(fn: () => Promise<void>) {
    setBusy(true);
    setError(null);
    try {
      await fn();
      setReasonOpen(false);
      setReason('');
    } catch (err) {
      setError(err instanceof ApiError ? err.detail : '처리에 실패했습니다. 잠시 후 다시 시도하세요.');
    } finally {
      setBusy(false);
    }
  }

  if (status !== 'OPEN' && status !== 'ACKNOWLEDGED') return null;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 8, padding: '0 20px 13px' }}>
      <div style={{ display: 'flex', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
        {status === 'OPEN' && (
          <button
            type="button"
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => run(onAcknowledge)}
            style={{ padding: '8px 14px', fontSize: 13 }}
          >
            확인
          </button>
        )}
        <button
          type="button"
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => setReasonOpen((v) => !v)}
          style={{ padding: '8px 14px', fontSize: 13 }}
        >
          정상 관행 등록
        </button>
      </div>

      {reasonOpen && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
          <label style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
            정상 관행으로 보는 사유 (
            {callSign ? (
              `이 선박(콜사인 ${callSign})의 같은 룰 경보`
            ) : (
              <strong>이 테넌트의 모든 선적에서 같은 룰 경보</strong>
            )}
            가 앞으로 자동으로 화이트리스트 처리됩니다)
            <textarea
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              maxLength={500}
              rows={2}
              style={{ display: 'block', width: '100%', marginTop: 4, boxSizing: 'border-box', font: 'inherit' }}
            />
          </label>
          <div>
            <button
              type="button"
              className="btn btn-primary"
              disabled={busy || reason.trim() === ''}
              onClick={() => run(() => onWhitelist(reason.trim()))}
              style={{ padding: '8px 14px', fontSize: 13 }}
            >
              등록
            </button>
          </div>
        </div>
      )}

      {error !== null && (
        <span role="alert" style={{ fontSize: 12.5, color: 'var(--severity-critical)' }}>
          {error}
        </span>
      )}
    </div>
  );
}
