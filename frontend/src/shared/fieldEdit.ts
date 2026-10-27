import { toConfidenceGrade } from '../constants/domain';
import type { ShipmentMockData } from '../mocks/shipmentData';
import type { FieldValue } from '../types/domain';

/**
 * 사용자가 값을 직접 고친 뒤의 필드.
 *
 * 고친다고 확정되지는 않습니다 — 등급은 원래 신뢰도에서 다시 계산하고, "값 확인함"만
 * 확정으로 올립니다. 다만 값이 있는데 미검출(NOT_FOUND)로 남으면 게이트웨이가 값을
 * 버리므로(field_value_not_found_ck) 그때는 REQUIRED로 둡니다. 정규화값은 옛 값의
 * 것이라 비웁니다(게이트웨이도 같은 규칙).
 */
export function withEditedValue(field: FieldValue, value: string | null): FieldValue {
  const derived = toConfidenceGrade({ ...field, value, grade: undefined });
  const grade = value !== null && derived === 'NOT_FOUND' ? 'REQUIRED' : derived;
  return { ...field, value, normalized_value: null, grade };
}

/** 선적 하나의 필드 하나를 바꿔 끼운 새 목록 (낙관적 갱신·롤백 공용) */
export function replaceField(
  list: ShipmentMockData[],
  shipmentId: string,
  field: FieldValue,
): ShipmentMockData[] {
  return list.map((data) =>
    data.shipment.shipment_id === shipmentId
      ? { ...data, fields: data.fields.map((f) => (f.field_name === field.field_name ? field : f)) }
      : data,
  );
}
