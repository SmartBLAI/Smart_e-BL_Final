/**
 * F7 선적 게이트웨이 — src/smart_e_bl/api/main.py 응답·요청 모양.
 *
 * F1(wireExtract.ts)과 같은 백엔드가 아닙니다 — 이건 추출 결과를 DB에 저장하는
 * 별도 서비스(게이트웨이)입니다. `client.ts`의 GATEWAY_API_BASE_URL로 붙습니다.
 */

import type { DefectPrediction, Verdict } from '../types/domain';

import type { WireRealityView } from './wireReality';

export interface WireShipmentListItem {
  shipment_id: string;
  status: 'DRAFT' | 'REVIEWING' | 'VERIFIED' | 'SUBMITTED' | 'MONITORING' | 'CLOSED';
  bl_no: string | null;
  cargo_control_no: string | null;
  lc_no: string | null;
  lc_expiry_date: string | null;
  created_at: string;
  updated_at: string;
}

export interface WireShipmentListResponse {
  shipments: WireShipmentListItem[];
  total?: number;
  next?: number | null;
}

export interface WireFieldValueOut {
  field_name: string;
  value: string | null;
  normalized_value: string | null;
  confidence: number | null;
  source_doc_id: string | null;
  page: number | null;
  bbox: [number, number, number, number] | null;
  extractor: 'rule' | 'ocr+llm' | 'json';
  conflict_flag: boolean;
  grade?: 'CONFIRMED' | 'ADVISORY' | 'REQUIRED' | 'NOT_FOUND';
}

export interface WireDocumentOut {
  document_id: string;
  doc_type:
    | 'BL_DRAFT'
    | 'BL_COPY'
    | 'SI'
    | 'COMMERCIAL_INVOICE'
    | 'PACKING_LIST'
    | 'LC_MT700'
    | 'INSURANCE_POLICY'
    | 'CERTIFICATE_OF_ORIGIN'
    | 'EXPORT_DECLARATION'
    | 'OTHER';
  file_name: string | null;
  file_hash: string;
  page_count: number;
  version: number;
  created_at: string;
}

export interface WireShipmentDetailResponse extends WireShipmentListItem {
  fields: WireFieldValueOut[];
  documents: WireDocumentOut[];
  /**
   * 마지막 "검증 실행"의 판정·하자확률. 한 번도 안 돌린 선적이면 `[]` / `null`.
   *
   * 게이트웨이는 이걸 해석하지 않고 `POST /verification` 으로 받은 걸 그대로
   * 감사 로그에 넣었다가 그대로 돌려줍니다 — 그래서 화면 도메인 타입
   * (`Verdict`·`DefectPrediction`)이 곧 wire 타입입니다. 번역기가 없는 유일한
   * 자리라 여기에 적어둡니다.
   */
  verdicts: Verdict[];
  prediction: DefectPrediction | null;
}

export interface WireCreateShipmentResponse {
  shipment_id: string;
}

export interface WireDocumentUploadResponse {
  document_id: string;
}

/** PUT /shipments/{id}/fields 요청 바디의 필드 한 개 */
export interface WireFieldValueIn {
  field_name: string;
  value: string | null;
  normalized_value?: string | null;
  confidence?: number | null;
  grade: 'CONFIRMED' | 'ADVISORY' | 'REQUIRED' | 'NOT_FOUND';
  extractor: 'rule' | 'ocr+llm' | 'json';
  bbox?: [number, number, number, number] | null;
  conflict_flag?: boolean;
}

export interface WireSaveFieldsRequest {
  document_id: string;
  page: number;
  fields: WireFieldValueIn[];
}

export interface WireSaveFieldsResponse {
  saved: number;
  /** field_definition 카탈로그에 없어 저장되지 않고 버려진 field_name들 */
  skipped: string[];
}

/** POST /shipments/{id}/verification 요청 바디 — 검증 결과를 그대로 감사 로그에 남긴다 */
export interface WireSaveVerificationRequest {
  verdict: Record<string, unknown>;
  prediction: Record<string, unknown> | null;
  override_reason: string | null;
}

export interface WireSaveVerificationResponse {
  status: WireShipmentListItem['status'];
}

/** GET /shipments/overview — 선적별 상세 + 현실 대조 뷰(= /reality 응답)를 한 번에 */
export interface WireShipmentOverviewItem extends WireShipmentDetailResponse {
  reality: WireRealityView;
}

export interface WireShipmentOverviewResponse {
  shipments: WireShipmentOverviewItem[];
  total: number;
  next: number | null;
}
