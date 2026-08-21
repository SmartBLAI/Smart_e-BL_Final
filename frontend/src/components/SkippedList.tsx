/**
 * 검사하지 **못한** 룰 목록.
 *
 * `/verify`·`/report` 응답의 `skipped`·`unchecked`입니다. 입력이 비었거나
 * 파싱에 실패해서 판단 자체를 못 한 룰이며, **통과가 아닙니다.**
 *
 * 이걸 화면에서 빼면 사용자는 "검사했고 문제없다"로 읽습니다. 백엔드
 * `SkippedRule` 주석도 같은 말을 합니다 — "검사하지 못한 항목을 침묵으로
 * 넘기면 사용자는 '검사했고 문제없다'로 읽는다".
 *
 * S4(F3 검증)에서 시작했지만 S7(F4 리포트)도 같은 패턴이 필요해져
 * `components/`로 옮겼습니다 — 두 화면 이상이 쓰는 부품 규칙(CLAUDE.md).
 */

import type { SkippedRuleView } from '../api/adapters';

interface SkippedListProps {
  skipped: SkippedRuleView[];
  /**
   * 왜 이만큼이나 못 검사했는지 한 줄 설명. 목록만으로는 "룰이 원래 그런가"
   * 로 읽히는데, 대부분은 입력이 빠져서입니다(신용장 미첨부 등).
   */
  hint?: string;
}

export function SkippedList({ skipped, hint }: SkippedListProps) {
  if (skipped.length === 0) return null;

  return (
    <details
      style={{
        padding: 'var(--space-3)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-card)',
        backgroundColor: 'var(--bg-card)',
        textAlign: 'left',
      }}
    >
      {/* <details>/<summary> 는 브라우저가 기본 제공하는 접기/펼치기입니다 */}
      <summary style={{ cursor: 'pointer', fontWeight: 600 }}>
        검사하지 못한 항목 {skipped.length}건
      </summary>

      <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--text-muted)' }}>
        아래 항목은 <strong>통과한 것이 아니라 판단하지 못한 것</strong>입니다.
      </p>

      {hint !== undefined && (
        <p style={{ margin: '8px 0 0', fontSize: 13, color: 'var(--text-secondary)' }}>{hint}</p>
      )}

      <ul style={{ margin: '8px 0 0', paddingLeft: '1.2em' }}>
        {skipped.map((s) => (
          <li key={s.rule_id} style={{ marginTop: 6, fontSize: 14 }}>
            {s.title}
            <span style={{ color: 'var(--text-muted)' }}> — {s.reason}</span>
            <span style={{ marginLeft: 6, fontSize: 12, color: 'var(--text-muted)' }}>
              {s.rule_id}
            </span>
          </li>
        ))}
      </ul>
    </details>
  );
}
