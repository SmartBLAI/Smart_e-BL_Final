import { describe, expect, it } from 'vitest';
import { toAlert, toRealityView, toSeverity } from './adaptersReality';
import type { WireAlert } from './wireReality';

function wireAlert(overrides: Partial<WireAlert> = {}): WireAlert {
  return {
    alert_id: 'a1',
    shipment_id: 's1',
    severity: 'Critical',
    message: '선박이 울산 기록에 없음',
    bl_no: 'BL1',
    document_event_ids: ['vessel_voyage'],
    reality_event_ids: [],
    acknowledged: false,
    created_at: '2026-10-01T00:00:00Z',
    rule_id: 'C-ROUTE-01',
    title: '선박 미발견',
    status: 'OPEN',
    last_seen_at: '2026-10-02T00:00:00Z',
    ...overrides,
  };
}

describe('toSeverity', () => {
  it('Critical/Warning/Info 를 그대로, 소문자도 받아주고, 모르는 값은 Info', () => {
    expect(toSeverity('Critical')).toBe('Critical');
    expect(toSeverity('warning')).toBe('Warning');
    expect(toSeverity('whatever')).toBe('Info');
  });
});

describe('toAlert', () => {
  it('acknowledged 는 status !== OPEN, 추가 필드와 빈 reality_event_ids 를 보존', () => {
    const open = toAlert(wireAlert());
    expect(open.acknowledged).toBe(false);
    expect(open.reality_event_ids).toEqual([]);
    expect(open.rule_id).toBe('C-ROUTE-01');
    expect(toAlert(wireAlert({ status: 'ACKNOWLEDGED', acknowledged: false })).acknowledged).toBe(true);
    expect(toAlert(wireAlert({ status: 'WHITELISTED' })).acknowledged).toBe(true);
  });
});

describe('toRealityView', () => {
  it('skipped 의 null rule_id 는 "-" 로, 나머지는 그대로', () => {
    const view = toRealityView({
      realityEvents: [],
      alerts: [wireAlert({ severity: 'warning' })],
      adapterStatus: null,
      vesselMatch: null,
      skipped: [{ rule_id: null, title: '현실 대조', reason: '선명 없음' }],
    });
    expect(view.skipped).toEqual([{ rule_id: '-', title: '현실 대조', reason: '선명 없음' }]);
    expect(view.alerts[0].severity).toBe('Warning');
  });
});
