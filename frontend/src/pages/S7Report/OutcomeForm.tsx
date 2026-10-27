import { useEffect, useState } from 'react';
import { ApiError } from '../../api/client';
import {
  OUTCOME_DECISIONS,
  OUTCOME_REASONS,
  getOutcome,
  saveOutcome,
  type OutcomeInput,
} from '../../api/outcome';

const EMPTY: OutcomeInput = { decision: 'PENDING', reason: 'UNKNOWN', memo: '', decided_on: '' };

const labelStyle = { display: 'flex', flexDirection: 'column', gap: 4, fontSize: 13, textAlign: 'left' } as const;

/** S10 결과 기록 — 사용자가 직접 입력한 값을 게이트웨이에 저장합니다. */
export function OutcomeForm({ shipmentId }: { shipmentId: string }) {
  const [form, setForm] = useState<OutcomeInput>(EMPTY);
  const [status, setStatus] = useState<'loading' | 'idle' | 'saving' | 'saved' | 'error'>('loading');
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const controller = new AbortController();
    getOutcome(shipmentId, controller.signal)
      .then((saved) => {
        if (saved) setForm({ decision: saved.decision, reason: saved.reason, memo: saved.memo, decided_on: saved.decided_on });
        setStatus('idle');
      })
      .catch(() => {
        // 게이트웨이를 못 읽어도 입력은 막지 않는다(저장 시 오류로 알린다).
        if (!controller.signal.aborted) setStatus('idle');
      });
    return () => controller.abort();
  }, [shipmentId]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setStatus('saving');
    setError(null);
    try {
      await saveOutcome(shipmentId, form);
      setStatus('saved');
    } catch (err) {
      setStatus('error');
      setError(err instanceof ApiError ? err.detail : '결과 저장에 실패했습니다.');
    }
  }

  const set = <K extends keyof OutcomeInput>(key: K, value: OutcomeInput[K]) => {
    setForm((prev) => ({ ...prev, [key]: value }));
    setStatus('idle');
  };

  return (
    <section
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 'var(--space-2)',
        padding: 'var(--space-3)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-card)',
        backgroundColor: 'var(--bg-card)',
        textAlign: 'left',
      }}
    >
      <h2 className="section-title" style={{ margin: 0 }}>은행 매입 결과 기록</h2>
      <p style={{ margin: 0, fontSize: 12.5, color: 'var(--text-muted)' }}>
        사용자가 직접 입력한 결과이며, 은행 시스템과 연동된 값이 아닙니다.
      </p>
      <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
        <label htmlFor="outcome-decision" style={labelStyle}>
          심사 결과
          <select id="outcome-decision" value={form.decision} onChange={(e) => set('decision', e.target.value as OutcomeInput['decision'])}>
            {Object.entries(OUTCOME_DECISIONS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label htmlFor="outcome-reason" style={labelStyle}>
          사유
          <select id="outcome-reason" value={form.reason} onChange={(e) => set('reason', e.target.value as OutcomeInput['reason'])}>
            {Object.entries(OUTCOME_REASONS).map(([value, label]) => (
              <option key={value} value={value}>{label}</option>
            ))}
          </select>
        </label>
        <label htmlFor="outcome-decided-on" style={labelStyle}>
          결정일
          <input id="outcome-decided-on" type="date" required value={form.decided_on} onChange={(e) => set('decided_on', e.target.value)} />
        </label>
        <label htmlFor="outcome-memo" style={labelStyle}>
          메모
          <textarea id="outcome-memo" rows={3} maxLength={1500} value={form.memo} onChange={(e) => set('memo', e.target.value)} />
        </label>
        <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
          <button type="submit" className="btn-primary" disabled={status === 'saving' || status === 'loading'}>
            {status === 'saving' ? '저장 중…' : '결과 저장'}
          </button>
          {status === 'saved' && <span role="status" style={{ fontSize: 13, color: 'var(--text-muted)' }}>저장되었습니다.</span>}
          {status === 'error' && error !== null && (
            <span style={{ fontSize: 13, color: 'var(--severity-critical)' }}>{error}</span>
          )}
        </div>
      </form>
    </section>
  );
}
