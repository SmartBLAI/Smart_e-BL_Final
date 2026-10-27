/**
 * S10 결과 기록 — 사용자가 직접 입력한 은행 매입 결과를 게이트웨이에 저장/조회합니다.
 * 은행과 연동된 값이 아니며, AI 예측으로 채우지도 않습니다.
 */

import { getJson, putJson, GATEWAY_API_BASE_URL } from './client';

export const OUTCOME_DECISIONS = {
  PENDING: '심사 대기',
  APPROVED: '매입 승인',
  AMENDMENT: '정정 요청',
  REJECTED: '매입 거절',
} as const;

export const OUTCOME_REASONS = {
  UNKNOWN: '알 수 없음',
  DOCUMENT_MISMATCH: '서류 간 불일치',
  LC_DISCREPANCY: '신용장 조건 불일치',
  LATE_PRESENTATION: '제시기간 초과',
  OTHER: '기타',
} as const;

export interface OutcomeInput {
  decision: keyof typeof OUTCOME_DECISIONS;
  reason: keyof typeof OUTCOME_REASONS;
  memo: string;
  /** YYYY-MM-DD */
  decided_on: string;
}

export interface Outcome extends OutcomeInput {
  shipment_id: string;
  source: 'USER_INPUT';
  recorded_at: string;
  updated_at: string;
}

const path = (shipmentId: string) => `/api/v1/shipments/${shipmentId}/outcome`;

/** 아직 기록이 없으면(204) null */
export async function getOutcome(shipmentId: string, signal?: AbortSignal): Promise<Outcome | null> {
  return (await getJson<Outcome | undefined>(path(shipmentId), GATEWAY_API_BASE_URL, signal)) ?? null;
}

export function saveOutcome(shipmentId: string, input: OutcomeInput, signal?: AbortSignal): Promise<Outcome> {
  return putJson<Outcome>(path(shipmentId), input, GATEWAY_API_BASE_URL, signal);
}
