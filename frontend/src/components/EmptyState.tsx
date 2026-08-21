import { Inbox } from 'lucide-react';
import type { LucideIcon } from 'lucide-react';

interface EmptyStateProps {
  /** 기본은 Inbox. 화면 성격에 맞는 아이콘이 있으면 넘겨서 바꿀 수 있음 */
  icon?: LucideIcon;
  message: string;
  /** true면 아이콘을 회전시켜 로딩 중임을 보여줌 (index.css의 .spin) */
  spin?: boolean;
}

/** 목록에 아직 아무것도 없을 때(또는 로딩 중일 때) 보여주는 안내 */
export function EmptyState({ icon: Icon = Inbox, message, spin = false }: EmptyStateProps) {
  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        gap: 'var(--space-3)',
        padding: 'var(--space-6) 0',
        color: 'var(--text-muted)',
      }}
    >
      <Icon size={32} aria-hidden="true" className={spin ? 'spin' : undefined} />
      <p style={{ margin: 0 }}>{message}</p>
    </div>
  );
}
