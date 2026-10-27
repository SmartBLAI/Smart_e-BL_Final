import { bySeverity } from '../../constants/domain';
import type { ConstraintType, ImpactItem } from '../../types/domain';

/**
 * 이번 기간 렌더 대상 제약 3종 (§10.1). 타입 자체는 6종 유지하되 나머지는 숨김.
 * (기존 ImpactPanel.tsx에 있던 상수를 그대로 옮겨왔습니다)
 */
export const RENDERED_CONSTRAINT_TYPES: ConstraintType[] = ['EQ', 'SUM', 'REF'];

/** 여러 필드가 같은 영향 항목을 부를 수 있어서, 어느 필드들 때문인지 같이 들고 다닙니다 */
export interface MergedImpactItem {
  item: ImpactItem;
  /** 이 항목을 불러온 필드 이름들 (사용자가 고친 필드 기준) */
  sourceFields: string[];
}

/** 같은 항목인지 구분하는 키 — (영향받는 문서, 필드, 제약유형)이 같으면 같은 항목 */
export function impactItemKey(item: ImpactItem): string {
  return `${item.affected_doc}|${item.affected_field}|${item.constraint_type}`;
}

/**
 * 사용자가 고친 모든 필드(changedFields)에 대해 mockImpactByField에서 영향
 * 항목을 모으고, 같은 항목이 여러 필드에서 나오면 한 줄로 합칩니다.
 *
 * 합칠 때 urgency(심각도)는 더 심한 쪽을 남깁니다 — 필드마다 갖고 있는
 * ImpactItem이 서로 다른 urgency로 기록돼 있을 수 있어서(예: 목데이터 설계상
 * 항상 같지만), 안전하게 더 심한 쪽 기준으로 보여줍니다.
 */
export function mergeImpactItems(
  changedFields: string[],
  impactByField: Record<string, ImpactItem[]>,
): MergedImpactItem[] {
  const merged = new Map<string, MergedImpactItem>();

  for (const field of changedFields) {
    const items = (impactByField[field] ?? []).filter((item) =>
      RENDERED_CONSTRAINT_TYPES.includes(item.constraint_type),
    );

    for (const item of items) {
      const key = impactItemKey(item);
      const existing = merged.get(key);

      if (existing === undefined) {
        merged.set(key, { item, sourceFields: [field] });
        continue;
      }

      if (!existing.sourceFields.includes(field)) {
        existing.sourceFields.push(field);
      }
      // bySeverity(a, b) < 0 이면 a가 b보다 더 심각합니다 (order가 작을수록 심각).
      // ImpactItem은 severity가 아니라 urgency 필드라 { severity: ... } 형태로 감싸서 넘깁니다.
      if (bySeverity({ severity: item.urgency }, { severity: existing.item.urgency }) < 0) {
        existing.item = { ...existing.item, urgency: item.urgency };
      }
    }
  }

  return [...merged.values()];
}
