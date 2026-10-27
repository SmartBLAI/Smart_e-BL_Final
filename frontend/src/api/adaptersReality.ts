/** F6 번역기 — wireReality.ts → 화면 도메인 타입. 없는 값을 지어내지 않습니다. */
import type { Alert, AdapterStatus, RealityEvent, Severity, VesselMatch } from '../types/domain';
import type { SkippedRuleView } from './adapters';
import type { WireAlert, WireRealityView } from './wireReality';

const SEVERITY_BY_LOWER: Record<string, Severity> = {
  critical: 'Critical',
  warning: 'Warning',
  info: 'Info',
};

/** 알 수 없는 심각도는 가장 약한 Info 로 — 경보를 버리지는 않습니다 */
export function toSeverity(raw: string): Severity {
  return SEVERITY_BY_LOWER[raw.toLowerCase()] ?? 'Info';
}

export function toAlert(wire: WireAlert): Alert {
  return {
    ...wire,
    severity: toSeverity(wire.severity),
    // 게이트웨이 규칙: acknowledged = status !== 'OPEN'
    acknowledged: wire.status !== 'OPEN',
  };
}

export interface RealityView {
  realityEvents: RealityEvent[];
  alerts: Alert[];
  adapterStatus: AdapterStatus | null;
  vesselMatch: VesselMatch | null;
  skipped: SkippedRuleView[];
}

export function toRealityView(wire: WireRealityView): RealityView {
  return {
    realityEvents: wire.realityEvents,
    alerts: wire.alerts.filter((a) => a.status !== 'RESOLVED').map(toAlert),
    adapterStatus: wire.adapterStatus,
    vesselMatch: wire.vesselMatch,
    skipped: wire.skipped.map((s) => ({ rule_id: s.rule_id ?? '-', title: s.title, reason: s.reason })),
  };
}
