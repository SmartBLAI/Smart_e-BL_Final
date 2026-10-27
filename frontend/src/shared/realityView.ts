/** F6 화면용 순수 함수 — S5·S6·store 가 같이 쓰고, 테스트가 직접 부릅니다 */
import { bySeverity } from '../constants/domain';
import type { AdapterStatus, Alert, RealityEvent, Severity } from '../types/domain';

/** 타임라인은 발생 시각 오름차순 */
export function sortEventsByTime(events: RealityEvent[]): RealityEvent[] {
  return [...events].sort(
    (a, b) => new Date(a.occurred_at).getTime() - new Date(b.occurred_at).getTime(),
  );
}

/** 미확인 먼저, 그 안에서 심각도 순 */
export function sortAlerts(alerts: Alert[]): Alert[] {
  return [...alerts].sort((a, b) =>
    a.acknowledged !== b.acknowledged ? (a.acknowledged ? 1 : -1) : bySeverity(a, b),
  );
}

export function filterBySeverity(alerts: Alert[], severity: Severity | null): Alert[] {
  return severity === null ? alerts : alerts.filter((a) => a.severity === severity);
}

/** 경보 한 건을 교체(확인 처리 응답 등). 없으면 그대로 */
export function replaceAlert(alerts: Alert[], updated: Alert): Alert[] {
  return alerts.map((a) => (a.alert_id === updated.alert_id ? updated : a));
}

/** 경보의 근거 이벤트. C-ROUTE-01 처럼 reality_event_ids 가 [] 여도 빈 배열을 돌려줄 뿐 */
export function evidenceEventsOf(alert: Alert, events: RealityEvent[]): RealityEvent[] {
  return alert.reality_event_ids
    .map((id) => events.find((e) => e.event_id === id))
    .filter((e): e is RealityEvent => e !== undefined);
}

/** 한 번도 대조를 안 돌린 선적 — 동기화 기록도 실패 기록도 없음 (§5.6: "이상 없음"이 아님) */
export function isNeverRun(status: AdapterStatus | null): boolean {
  return status !== null && status.last_synced_at === null && status.consecutive_failures === 0;
}

/**
 * 검증 성공 직후의 현실 대조 — 실패해도 던지지 않고 false 만 돌려줍니다.
 * 검증 결과를 실패로 뒤집지 않기 위해서입니다(S5가 어댑터 실패 상태를 따로 보여줌).
 */
export async function runRealityCheckSoftly(run: () => Promise<unknown>): Promise<boolean> {
  try {
    await run();
    return true;
  } catch {
    return false;
  }
}
