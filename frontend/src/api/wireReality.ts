/**
 * F6 현실 대조 게이트웨이 응답(src/smart_e_bl/api/reality.py)의 wire 모양.
 * 이벤트·어댑터 상태·선박 매칭은 화면 도메인 타입과 같은 모양으로 내려오고,
 * 경보만 severity 문자열·status가 달라서 번역(adaptersReality.ts)이 필요합니다.
 */
import type { AdapterStatus, AlertStatus, RealityEvent, VesselMatch } from '../types/domain';

export interface WireAlert {
  alert_id: string;
  shipment_id: string;
  /** "Critical" | "Warning" | "Info" (게이트웨이가 capitalize) */
  severity: string;
  message: string;
  bl_no: string;
  document_event_ids: string[];
  reality_event_ids: string[];
  acknowledged: boolean;
  created_at: string;
  rule_id: string;
  title: string;
  status: AlertStatus;
  last_seen_at: string;
}

export interface WireRealitySkipped {
  rule_id: string | null;
  title: string;
  reason: string;
}

export interface WireRealityView {
  realityEvents: RealityEvent[];
  alerts: WireAlert[];
  adapterStatus: AdapterStatus | null;
  vesselMatch: VesselMatch | null;
  skipped: WireRealitySkipped[];
}

export interface WireAlertListResponse {
  alerts: WireAlert[];
}

export interface WireWhitelistEntry {
  id: string;
  rule_id: string;
  call_sign: string | null;
  reason: string;
  created_by: string;
  created_at: string;
  alerts_flipped?: number;
}
