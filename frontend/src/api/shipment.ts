/**
 * F7 선적 게이트웨이 호출 — 화면(shipmentStore)이 이 함수들만 부르면 됩니다.
 *
 * 흐름: 선적 생성 → 서류 업로드 → 필드값 저장. 세 요청이 순서대로 이어져야
 * 해서(뒤 요청이 앞 요청의 id를 필요로 함) createDraftWithFields 하나로 묶었습니다.
 */

import { deleteRequest, getJson, postForm, postJson, putJson, GATEWAY_API_BASE_URL } from './client';
import { toRealityView, type RealityView } from './adaptersReality';
import { toShipmentAndFields, toShipment, toWireFieldValueIn } from './adaptersShipment';
import type {
  WireCreateShipmentResponse,
  WireDocumentUploadResponse,
  WireSaveFieldsResponse,
  WireSaveVerificationResponse,
  WireShipmentDetailResponse,
  WireShipmentListResponse,
  WireShipmentOverviewResponse,
} from './wireShipment';
import type {
  DefectPrediction,
  DocumentMeta,
  FieldValue,
  Shipment,
  Verdict,
} from '../types/domain';

export async function listShipments(signal?: AbortSignal): Promise<Shipment[]> {
  const wire = await getJson<WireShipmentListResponse>(
    '/api/v1/shipments',
    GATEWAY_API_BASE_URL,
    signal,
  );
  return wire.shipments.map(toShipment);
}

/**
 * 대시보드용: 선적 목록 + 선적별 상세 + 현실 대조 뷰를 요청 한 번에 받습니다.
 * 선적마다 getShipment/getReality 를 부르던 1+2N 요청을 대체합니다 — 내용은 같습니다.
 */
export async function getShipmentsOverview(signal?: AbortSignal): Promise<
  Array<Awaited<ReturnType<typeof getShipment>> & { reality: RealityView }>
> {
  const wire = await getJson<WireShipmentOverviewResponse>(
    '/api/v1/shipments/overview',
    GATEWAY_API_BASE_URL,
    signal,
  );
  return wire.shipments.map((s) => ({ ...toShipmentAndFields(s), reality: toRealityView(s.reality) }));
}

export async function getShipment(
  shipmentId: string,
  signal?: AbortSignal,
): Promise<{
  shipment: Shipment;
  fields: FieldValue[];
  documents: DocumentMeta[];
  /** 지난 "검증 실행"의 판정. 한 번도 안 돌렸으면 빈 배열 */
  verdicts: Verdict[];
  /** 지난 "검증 실행"의 하자 확률. 한 번도 안 돌렸으면 null */
  prediction: DefectPrediction | null;
}> {
  const wire = await getJson<WireShipmentDetailResponse>(
    `/api/v1/shipments/${shipmentId}`,
    GATEWAY_API_BASE_URL,
    signal,
  );
  return toShipmentAndFields(wire);
}

/**
 * 서류 파일 하나를 선적에 붙입니다.
 *
 * `docType` 은 게이트웨이가 서류 종류를 구분하는 값입니다. 안 넘기면
 * B/L 초안(`BL_DRAFT`)으로 저장됩니다 — 신용장을 올릴 때만 `LC_MT700` 을
 * 넘기세요. 종류를 안 붙이면 나중에 어느 파일이 신용장인지 알 수 없어
 * L/C 조건을 다시 읽어올 방법이 없어집니다.
 */
export async function uploadDocument(
  shipmentId: string,
  file: File,
  docType?: 'BL_DRAFT' | 'LC_MT700',
  signal?: AbortSignal,
): Promise<WireDocumentUploadResponse> {
  const form = new FormData();
  form.append('file', file);
  if (docType) form.append('doc_type', docType);
  return postForm<WireDocumentUploadResponse>(
    `/api/v1/shipments/${shipmentId}/documents`,
    form,
    undefined,
    signal,
    GATEWAY_API_BASE_URL,
  );
}

/**
 * 필드값 저장만 합니다 — `PUT /fields`. createDraftWithFields(업로드 직후)와
 * 스토어의 editField(필드 1건 즉시 저장)가 같이 씁니다.
 */
export async function saveFields(
  shipmentId: string,
  documentId: string,
  page: number,
  fields: FieldValue[],
  signal?: AbortSignal,
): Promise<WireSaveFieldsResponse> {
  return putJson<WireSaveFieldsResponse>(
    `/api/v1/shipments/${shipmentId}/fields`,
    {
      document_id: documentId,
      page,
      fields: fields.map(toWireFieldValueIn),
    },
    GATEWAY_API_BASE_URL,
    signal,
  );
}

/** "값 확인함" — 게이트웨이의 대표 field_value 등급을 CONFIRMED로 올립니다 */
export async function confirmField(shipmentId: string, fieldName: string): Promise<void> {
  await postJson<unknown>(
    `/api/v1/shipments/${shipmentId}/fields/${encodeURIComponent(fieldName)}/confirm`,
    {},
    undefined,
    GATEWAY_API_BASE_URL,
  );
}

/**
 * 선적 하나를 만들고, 업로드한 서류·추출된 필드값까지 한 번에 저장합니다.
 *
 * page는 1부터 시작합니다(extract.ts가 이미 1-idx로 맞춰서 넘겨줍니다).
 * bbox가 있는 필드만 그 서류를 근거로 삼습니다 — bbox 없는 필드(예: json 추출)는
 * document_id 없이 저장됩니다(게이트웨이가 field_value_evidence_required_ck에
 * 맞춰 판단).
 *
 * `lcFile` 은 같이 첨부한 신용장(MT700) 전문입니다. 있으면 같은 선적에
 * `LC_MT700` 으로 올라가고, 이후 검증이 그걸 대조 기준으로 씁니다.
 *
 * 중간에 실패하면 **방금 만든 선적을 지우고** 오류를 올려보냅니다. 요청이
 * 네 번으로 나뉘어 있어서, 선적만 만들어지고 서류가 안 올라간 상태로 끝날 수
 * 있습니다. 화면은 "실패"라고 알리는데 대시보드에는 빈 선적이 하나 남고,
 * 사용자가 다시 시도할 때마다 그게 계속 쌓입니다.
 */
export async function createDraftWithFields(
  file: File,
  fields: FieldValue[],
  page: number,
  lcFile?: File | null,
  signal?: AbortSignal,
): Promise<{ shipment: Shipment; fields: FieldValue[]; documents: DocumentMeta[] }> {
  const created = await postJson<WireCreateShipmentResponse>(
    '/api/v1/shipments',
    {},
    signal,
    GATEWAY_API_BASE_URL,
  );
  const shipmentId = created.shipment_id;

  try {
    const uploaded = await uploadDocument(shipmentId, file, 'BL_DRAFT', signal);

    // 업로드 직후 최초 저장 — 아직 사용자가 고친 필드가 없으므로 editedFieldNames 없음
    await saveFields(shipmentId, uploaded.document_id, page, fields, signal);

    // 신용장은 마지막 조회 **전에** 올려야 documents 에 같이 담겨 옵니다 —
    // 나중에 올리면 화면 스토어에 B/L 만 든 서류 목록이 남아, S3·S4 가
    // "신용장 없음"으로 검증하게 됩니다.
    if (lcFile) await uploadDocument(shipmentId, lcFile, 'LC_MT700', signal);

    // created_at 등은 DB가 채운 실제 값을 써야 해서(지어내지 않음) 한 번 더 조회합니다.
    // 필드값은 방금 우리가 보낸 것과 같으므로 다시 안 받아도 되지만, documents는
    // 방금 올린 서류의 진짜 document_id·file_name을 담고 있어 다시 받아야 합니다.
    const { shipment, documents } = await getShipment(shipmentId, signal);
    return { shipment, fields, documents };
  } catch (err) {
    // 되돌리기가 실패해도(게이트웨이가 아예 꺼진 경우 등) 원래 오류를 그대로
    // 올려보냅니다 — 사용자에게 알려야 할 건 "저장에 실패했다"이지 "정리에
    // 실패했다"가 아닙니다.
    await deleteShipment(shipmentId).catch(() => undefined);
    throw err;
  }
}

/**
 * 선적을 지웁니다 — 시연 리허설 중 쌓인 테스트 데이터를 치울 방법이 UI에
 * 없었습니다(P2-16). 서류·필드값·판정 등은 게이트웨이 DB의 CASCADE 제약이
 * 같이 지웁니다.
 */
export async function deleteShipment(shipmentId: string, signal?: AbortSignal): Promise<void> {
  await deleteRequest(`/api/v1/shipments/${shipmentId}`, GATEWAY_API_BASE_URL, signal);
}

/**
 * "검증 실행" 결과를 게이트웨이에 저장합니다. aiService(/verify)가 이미 계산한
 * verdict·prediction을 그대로 실어 보내면, 게이트웨이는 감사 로그(audit_log)에
 * 스냅샷으로 남기고 선적 상태를 DRAFT/REVIEWING → VERIFIED로 바꿉니다. 이걸
 * 안 부르면 새로고침했을 때 판정 결과가 사라지고 상태도 영원히 DRAFT입니다.
 */
export async function saveVerification(
  shipmentId: string,
  verdict: unknown,
  prediction: unknown,
  overrideReason: string | null,
  signal?: AbortSignal,
): Promise<Shipment['status']> {
  const res = await postJson<WireSaveVerificationResponse>(
    `/api/v1/shipments/${shipmentId}/verification`,
    { verdict, prediction, override_reason: overrideReason },
    signal,
    GATEWAY_API_BASE_URL,
  );
  return res.status;
}
