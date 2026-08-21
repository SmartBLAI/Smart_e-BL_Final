/**
 * F7 번역기 — 게이트웨이 응답·요청(wireShipment.ts)과 화면 도메인 타입 사이.
 *
 * 원칙은 F1 번역기(adaptersExtract.ts)와 같습니다: 없는 값을 지어내지 않습니다.
 */

import { toConfidenceGrade } from '../constants/domain';
import type {
  DefectPrediction,
  DocumentKind,
  DocumentMeta,
  FieldValue,
  Shipment,
  Verdict,
} from '../types/domain';
import type {
  WireDocumentOut,
  WireFieldValueIn,
  WireFieldValueOut,
  WireShipmentDetailResponse,
  WireShipmentListItem,
} from './wireShipment';

const DOCUMENT_KIND_FROM_WIRE: Record<WireDocumentOut['doc_type'], DocumentKind> = {
  BL_DRAFT: 'BL',
  BL_COPY: 'BL',
  SI: 'SI',
  COMMERCIAL_INVOICE: 'INVOICE',
  PACKING_LIST: 'PACKING',
  LC_MT700: 'LC',
  INSURANCE_POLICY: 'UNKNOWN',
  CERTIFICATE_OF_ORIGIN: 'UNKNOWN',
  EXPORT_DECLARATION: 'UNKNOWN',
  OTHER: 'UNKNOWN',
};

export function toDocumentMetaFromWire(wire: WireDocumentOut): DocumentMeta {
  return {
    document_id: wire.document_id,
    kind: DOCUMENT_KIND_FROM_WIRE[wire.doc_type],
    file_name: wire.file_name ?? '(파일명 없음)',
    file_hash: wire.file_hash,
    page_count: wire.page_count,
    version: wire.version,
    uploaded_at: wire.created_at,
  };
}

export function toShipment(wire: WireShipmentListItem): Shipment {
  return {
    shipment_id: wire.shipment_id,
    status: wire.status,
    bl_no: wire.bl_no,
    cargo_control_no: wire.cargo_control_no,
    lc_no: wire.lc_no,
    lc_expiry_date: wire.lc_expiry_date,
    created_at: wire.created_at,
    updated_at: wire.updated_at,
  };
}

export function toFieldValueFromWire(wire: WireFieldValueOut): FieldValue {
  return {
    field_name: wire.field_name,
    value: wire.value,
    normalized_value: wire.normalized_value,
    confidence: wire.confidence ?? 0,
    source_doc_id: wire.source_doc_id,
    page: wire.page,
    bbox: wire.bbox,
    extractor: wire.extractor,
    conflict_flag: wire.conflict_flag,
  };
}

export function toShipmentAndFields(wire: WireShipmentDetailResponse): {
  shipment: Shipment;
  fields: FieldValue[];
  documents: DocumentMeta[];
  verdicts: Verdict[];
  prediction: DefectPrediction | null;
} {
  return {
    shipment: toShipment(wire),
    fields: wire.fields.map(toFieldValueFromWire),
    documents: wire.documents.map(toDocumentMetaFromWire),
    // 판정은 게이트웨이가 화면 도메인 타입 그대로 저장·반환합니다 — 번역 없음
    // (wireShipment.ts의 verdicts 주석 참고).
    verdicts: wire.verdicts,
    prediction: wire.prediction,
  };
}

/**
 * 화면 FieldValue를 저장 요청 모양으로 바꿉니다.
 *
 * grade는 화면 FieldValue에 아예 없는 값입니다(파생값 — toConfidenceGrade 참고).
 * 게이트웨이가 grade로 DB confidence 등급(ConfidenceGrade)을 결정하므로, 여기서
 * 같은 규칙으로 미리 계산해서 보냅니다. 지어내는 게 아니라 화면에 이미 있는
 * 계산을 그대로 재사용하는 것입니다.
 *
 * isEdited: 사용자가 직접 타이핑해서 고친 필드인지(shared/shipmentStats.ts의
 *   isEditedField로 판정된 값을 그대로 받습니다). 원래 미검출(NOT_FOUND)이던
 *   필드는 값만 채워져도 bbox·confidence가 그대로라 toConfidenceGrade가 여전히
 *   NOT_FOUND를 계산하고, 게이트웨이는 NOT_FOUND 필드의 value를 null로 버립니다
 *   (field_value_not_found_ck) — 사용자가 타이핑한 값이 저장 직후 사라지는
 *   버그였습니다. 사용자가 직접 고친 값은 사용자 본인이 근거이므로 CONFIRMED로
 *   보냅니다(M-2 확정의 저장 경로 반영 — effectiveGradeOf와 같은 결론).
 */
export function toWireFieldValueIn(field: FieldValue, isEdited = false): WireFieldValueIn {
  return {
    field_name: field.field_name,
    value: field.value,
    normalized_value: field.normalized_value,
    confidence: field.confidence,
    grade: isEdited ? 'CONFIRMED' : toConfidenceGrade(field),
    extractor: field.extractor,
    bbox: field.bbox,
    conflict_flag: field.conflict_flag,
  };
}
