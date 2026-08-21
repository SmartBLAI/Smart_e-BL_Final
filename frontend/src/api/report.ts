/**
 * F4 리포트 — `POST /report`(미리보기)·`POST /report/pdf`(다운로드) 호출 + 번역.
 *
 * `/report/share`는 이번 범위 밖입니다 (S7Report 주석 참고).
 */

import { postJson, postJsonForBlob } from './client';
import { toBLPayload } from './adapters';
import { toReportView, type ReportView } from './adaptersReport';
import type { WireReportRequest, WireReportResponse } from './wireReport';
import type { FieldValue } from '../types/domain';

// L/C 조건을 같이 보내야 S4(/verify)와 같은 룰들이 검사됩니다 — 안 보내면
// 이 룰들이 "검사 못함"으로 빠져서 S4·S7 숫자가 어긋납니다 (useVerify.ts 참고).
function toRequestBody(fields: FieldValue[], lc?: Record<string, unknown>): WireReportRequest {
  return { bl: toBLPayload(fields), ...(lc ? { lc } : {}) };
}

export async function generateReport(
  fields: FieldValue[],
  lc?: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<ReportView> {
  const res = await postJson<WireReportResponse>('/report', toRequestBody(fields, lc), signal);
  return toReportView(res, new Date().toISOString());
}

/**
 * 리포트 PDF를 받아 바로 다운로드시킵니다. 표준 브라우저 API만 씁니다 —
 * 임시 `<a download>`를 만들어 클릭한 뒤 바로 지웁니다.
 */
export async function downloadReportPdf(
  fields: FieldValue[],
  lc?: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<void> {
  const { blob, filename } = await postJsonForBlob('/report/pdf', toRequestBody(fields, lc), signal);
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename ?? 'report.pdf';
  a.click();
  // click() 직후 바로 revoke하면 브라우저가 다운로드를 시작하기 전에 URL이
  // 무효화되어 간헐적으로 다운로드가 비어버린다(P2-15) — 다음 이벤트
  // 루프까지 미룬다.
  setTimeout(() => URL.revokeObjectURL(url), 0);
}
