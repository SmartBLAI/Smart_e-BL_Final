import type { RealityRuleStatus } from '../../types/domain';
import { RULE_COVERAGE_LABEL } from '../../constants/domain';
import { mockRealityRules } from '../../mocks/shipment.fixture';
import { SeverityBadge } from '../../components/SeverityBadge';

/**
 * 판정 범위 공개 구역 — F6의 핵심 정직성 장치.
 *
 * 기획 원안(v2)의 모순 규칙 11건 중 지금 API(울산항 VTS + 해수부 선박제원)로
 * 실제 판정 가능한 건 6건뿐입니다. 나머지 5건을 화면에서 빼버리면 "검사했고
 * 문제없다"로 읽히므로(SkippedList와 같은 이유), 왜 못 하는지 reason을 그대로
 * 보여줍니다. 기존 "판정 보류" 구역과 나란히 두되, 대상이 다릅니다 — 판정
 * 보류는 판정 결과(Verdict) 얘기고, 이 구역은 룰 자체를 실행할 수 있는지의
 * 얘기입니다.
 *
 * 숫자는 mockRealityRules 배열 길이에서 매번 계산합니다. 하드코딩하면 룰이
 * 늘어나는 순간 문구가 거짓말이 됩니다.
 *
 * 접어도(<summary>) 건수 문장은 항상 보이고, 안쪽 목록만 접힙니다.
 */
export function RuleCoverageSection() {
  const total = mockRealityRules.length;
  const implemented = mockRealityRules.filter((rule) => rule.coverage === 'IMPLEMENTED');
  const partial = mockRealityRules.filter((rule) => rule.coverage === 'PARTIAL');
  const notEvaluable = mockRealityRules.filter((rule) => rule.coverage === 'NOT_EVALUABLE');
  const evaluable = implemented.length + partial.length;

  return (
    <section style={{ marginTop: 'var(--space-6)', textAlign: 'left' }}>
      <details
        style={{
          border: '1px solid var(--border-default)',
          borderRadius: 'var(--radius-card)',
          backgroundColor: 'var(--bg-card)',
          padding: 'var(--space-3)',
        }}
      >
        <summary style={{ cursor: 'pointer', fontWeight: 600, fontSize: 14, wordBreak: 'keep-all' }}>
          모순 규칙 {total}건 중 {evaluable}건을 판정합니다 (완전 {implemented.length} · 부분{' '}
          {partial.length}). 나머지 {notEvaluable.length}건은 아래 사유로 판정하지 않습니다.
        </summary>

        <div
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 'var(--space-4)',
            marginTop: 'var(--space-3)',
          }}
        >
          <RuleGroup title="부분 판정 — 어디까지만 보는지" rules={partial} />
          <RuleGroup title="판정 불가 — 이 데이터로는 볼 수 없음" rules={notEvaluable} />
        </div>
      </details>
    </section>
  );
}

function RuleGroup({ title, rules }: { title: string; rules: RealityRuleStatus[] }) {
  if (rules.length === 0) return null;

  return (
    <div>
      <h3
        style={{
          margin: '0 0 8px',
          fontSize: 12.5,
          fontWeight: 700,
          color: 'var(--text-secondary)',
        }}
      >
        {title} ({rules.length}건)
      </h3>
      <ul style={{ margin: 0, paddingLeft: '1.2em', display: 'flex', flexDirection: 'column', gap: 8 }}>
        {rules.map((rule) => (
          <li key={rule.rule_id} style={{ fontSize: 13, lineHeight: 1.5, wordBreak: 'keep-all' }}>
            <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              <strong style={{ color: 'var(--text-primary)' }}>{rule.intent}</strong>
              {rule.severity !== null && <SeverityBadge severity={rule.severity} />}
              <span style={{ fontSize: 11, color: 'var(--text-muted)' }}>
                {rule.rule_id} · {RULE_COVERAGE_LABEL[rule.coverage]}
              </span>
            </div>
            <p style={{ margin: '2px 0 0', color: 'var(--text-secondary)' }}>{rule.reason}</p>
          </li>
        ))}
      </ul>
    </div>
  );
}
