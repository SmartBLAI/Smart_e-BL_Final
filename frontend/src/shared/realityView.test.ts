import { describe, expect, it } from 'vitest';
import {
  evidenceEventsOf,
  filterBySeverity,
  isNeverRun,
  runRealityCheckSoftly,
  replaceAlert,
  sortAlerts,
  sortEventsByTime,
} from './realityView';
import type { AdapterStatus, Alert, RealityEvent } from '../types/domain';

const alert = (id: string, severity: Alert['severity'], over: Partial<Alert> = {}): Alert => ({
  alert_id: id,
  shipment_id: 's1',
  severity,
  message: id,
  bl_no: 'BL1',
  document_event_ids: [],
  reality_event_ids: [],
  acknowledged: false,
  created_at: '2026-10-01T00:00:00Z',
  status: 'OPEN',
  ...over,
});

const event = (id: string, occurred_at: string): RealityEvent => ({
  event_id: id,
  shipment_id: 's1',
  source: 'ULSAN_VTS',
  source_event_code: '3',
  event_type: 'ARRIVAL',
  occurred_at,
  recorded_at: occurred_at,
  location: 'KRUSN',
  quantity: null,
  container_no: null,
  trust_grade: 'A',
  precision: 'DATETIME',
  voyage_no: null,
  facility: null,
  raw_code: null,
});

describe('S5', () => {
  it('이벤트를 occurred_at 오름차순으로 정렬 (원본 불변)', () => {
    const input = [event('c', '2026-10-03T00:00:00Z'), event('a', '2026-10-01T00:00:00Z'), event('b', '2026-10-02T00:00:00Z')];
    expect(sortEventsByTime(input).map((e) => e.event_id)).toEqual(['a', 'b', 'c']);
    expect(input[0].event_id).toBe('c');
  });

  it('C-ROUTE-01 처럼 reality_event_ids 가 [] 인 경보도 근거 조회가 빈 배열로 끝남', () => {
    const route = alert('r', 'Critical', { rule_id: 'C-ROUTE-01' });
    expect(evidenceEventsOf(route, [event('a', '2026-10-01T00:00:00Z')])).toEqual([]);
  });

  it('동기화·실패 기록이 없으면 "대조 안 돌림"', () => {
    const s: AdapterStatus = { name: 'ULSAN_VTS', connected: false, last_synced_at: null, consecutive_failures: 0, coverage_note: '' };
    expect(isNeverRun(s)).toBe(true);
    expect(isNeverRun({ ...s, consecutive_failures: 2 })).toBe(false);
    expect(isNeverRun({ ...s, last_synced_at: '2026-10-01T00:00:00Z' })).toBe(false);
    expect(isNeverRun(null)).toBe(false);
  });
});

describe('S6', () => {
  const list = [alert('i', 'Info'), alert('c', 'Critical'), alert('w', 'Warning')];

  it('심각도 필터', () => {
    expect(filterBySeverity(list, 'Warning').map((a) => a.alert_id)).toEqual(['w']);
    expect(filterBySeverity(list, null)).toHaveLength(3);
  });

  it('확인 처리 응답으로 교체하면 status/acknowledged 가 바뀌고 미확인 먼저 정렬이 뒤로 보냄', () => {
    const updated = alert('c', 'Critical', { status: 'ACKNOWLEDGED', acknowledged: true });
    const next = replaceAlert(list, updated);
    expect(next.find((a) => a.alert_id === 'c')?.status).toBe('ACKNOWLEDGED');
    expect(sortAlerts(next).map((a) => a.alert_id)).toEqual(['w', 'i', 'c']);
  });
});

describe('검증 후 현실 대조', () => {
  it('성공하면 true, 실패는 던지지 않고 false', async () => {
    expect(await runRealityCheckSoftly(async () => 1)).toBe(true);
    expect(await runRealityCheckSoftly(async () => { throw new Error('x'); })).toBe(false);
  });
});
