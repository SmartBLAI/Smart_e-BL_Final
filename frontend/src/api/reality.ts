/** F6 게이트웨이 호출 — 현실 대조·경보·화이트리스트 */
import { deleteRequest, getJson, postJson, GATEWAY_API_BASE_URL } from './client';
import { toAlert, toRealityView, type RealityView } from './adaptersReality';
import type {
  WireAlert,
  WireAlertListResponse,
  WireRealityView,
  WireWhitelistEntry,
} from './wireReality';
import type { Alert, Severity } from '../types/domain';

export async function getReality(shipmentId: string, signal?: AbortSignal): Promise<RealityView> {
  const wire = await getJson<WireRealityView>(
    `/api/v1/shipments/${shipmentId}/reality`,
    GATEWAY_API_BASE_URL,
    signal,
  );
  return toRealityView(wire);
}

/** 현실 대조 실행 — 결과 뷰를 바로 돌려줍니다 */
export async function runRealityCheck(shipmentId: string, signal?: AbortSignal): Promise<RealityView> {
  const wire = await postJson<WireRealityView>(
    `/api/v1/shipments/${shipmentId}/reality/check`,
    {},
    signal,
    GATEWAY_API_BASE_URL,
  );
  return toRealityView(wire);
}

export async function listAlerts(
  filter: { severity?: Severity; status?: string } = {},
  signal?: AbortSignal,
): Promise<Alert[]> {
  const q = new URLSearchParams();
  if (filter.severity) q.set('severity', filter.severity);
  if (filter.status) q.set('status', filter.status);
  const qs = q.size > 0 ? `?${q}` : '';
  const wire = await getJson<WireAlertListResponse>(`/api/v1/alerts${qs}`, GATEWAY_API_BASE_URL, signal);
  return wire.alerts.filter((a) => filter.status === 'RESOLVED' || a.status !== 'RESOLVED').map(toAlert);
}

export async function acknowledgeAlert(alertId: string, signal?: AbortSignal): Promise<Alert> {
  const wire = await postJson<WireAlert>(
    `/api/v1/alerts/${alertId}/acknowledge`,
    {},
    signal,
    GATEWAY_API_BASE_URL,
  );
  return toAlert(wire);
}

export function addWhitelist(
  body: { rule_id: string; call_sign?: string | null; reason: string },
  signal?: AbortSignal,
): Promise<WireWhitelistEntry> {
  return postJson<WireWhitelistEntry>('/api/v1/reality/whitelist', body, signal, GATEWAY_API_BASE_URL);
}

export function listWhitelist(signal?: AbortSignal): Promise<{ whitelist: WireWhitelistEntry[] }> {
  return getJson('/api/v1/reality/whitelist', GATEWAY_API_BASE_URL, signal);
}

export function deleteWhitelist(id: string, signal?: AbortSignal): Promise<void> {
  return deleteRequest(`/api/v1/reality/whitelist/${id}`, GATEWAY_API_BASE_URL, signal);
}
