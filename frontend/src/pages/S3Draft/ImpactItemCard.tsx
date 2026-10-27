import { SeverityBadge } from '../../components/SeverityBadge';
import { InfoTip } from '../../components/InfoTip';
import { CONSTRAINT_TYPE_LABEL, labelOfField } from '../../constants/domain';
import { impactItemKey, type MergedImpactItem } from './impactMerge';

interface ImpactItemCardProps {
  merged: MergedImpactItem;
  /** 재확인 체크 여부 — requires_recheck가 아닌 항목이면 항상 무시됩니다 */
  checked: boolean;
  onToggleCheck: (key: string) => void;
}

/** 정정 영향 항목 카드 한 장. 직접 영향·간접 영향 둘 다 이 카드를 씁니다 */
export function ImpactItemCard({ merged, checked, onToggleCheck }: ImpactItemCardProps) {
  const { item, sourceFields } = merged;
  const key = impactItemKey(item);

  return (
    <div
      style={{
        display: 'flex',
        flexDirection: 'column',
        gap: 4,
        padding: 'var(--space-2)',
        border: '1px solid var(--border-default)',
        borderRadius: 6,
      }}
    >
      <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between' }}>
        {/* 코드(EQ 등) 대신 뜻을 보여줍니다 — 코드는 아래 ⓘ 안에 남겨둡니다 */}
        <span
          style={{
            fontSize: 11,
            fontWeight: 700,
            color: 'var(--text-muted)',
            border: '1px solid var(--border-default)',
            borderRadius: 4,
            padding: '1px 6px',
          }}
        >
          {CONSTRAINT_TYPE_LABEL[item.constraint_type]}
        </span>
        <SeverityBadge severity={item.urgency} />
      </div>

      <p style={{ margin: 0 }}>{item.action}</p>

      {/* 어느 필드를 고쳐서 이 항목이 딸려왔는지 — 여러 필드가 같은 항목을 부르면 전부 나열 */}
      <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
        {sourceFields.map((field) => labelOfField(field)).join(' · ')} 변경 때문
      </span>

      {/* 화면에는 사람이 읽을 값만 — 문서 ID·룰 코드·제약 코드는 ⓘ로 접습니다 (S6과 같은 방식) */}
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          gap: 6,
          flexWrap: 'wrap',
          fontSize: 12,
          color: 'var(--text-muted)',
        }}
      >
        {labelOfField(item.affected_field)} · 담당 {item.party}
        <InfoTip
          text={[item.affected_doc, item.rule_id, `제약 ${item.constraint_type}`]
            .filter((part): part is string => part !== null)
            .join(' · ')}
        />
      </span>

      {item.requires_recheck && (
        <label
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 6,
            fontSize: 12,
            color: 'var(--text-secondary)',
            cursor: 'pointer',
          }}
        >
          <input type="checkbox" checked={checked} onChange={() => onToggleCheck(key)} />
          재확인 완료로 표시
        </label>
      )}
    </div>
  );
}
