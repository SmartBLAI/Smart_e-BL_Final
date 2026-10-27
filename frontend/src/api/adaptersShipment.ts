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
    grade: wire.grade,
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
 * grade는 FieldValue.grade(서버 값 또는 shared/fieldEdit.ts의 편집 결과)를 그대로
 * 쓰고, 없으면 toConfidenceGrade로 계산합니다. 편집한다고 CONFIRMED가 되지 않습니다.
 */
export function toWireFieldValueIn(field: FieldValue): WireFieldValueIn {
  return {
    field_name: field.field_name,
    value: field.value,
    normalized_value: field.normalized_value,
    confidence: field.confidence,
    grade: toConfidenceGrade(field),
    extractor: field.extractor,
    bbox: field.bbox,
    conflict_flag: field.conflict_flag,
  };
}
