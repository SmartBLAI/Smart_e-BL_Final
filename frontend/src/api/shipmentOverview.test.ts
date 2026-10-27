import { describe, expect, it, vi } from 'vitest';

const getJson = vi.fn().mockResolvedValue({
  total: 1,
  next: null,
  shipments: [
    {
      shipment_id: 'shp-1',
      status: 'DRAFT',
      bl_no: null,
      cargo_control_no: null,
      lc_no: null,
      lc_expiry_date: null,
      created_at: '2026-08-21T00:00:00Z',
      updated_at: '2026-08-21T00:00:00Z',
      fields: [],
      documents: [],
      verdicts: [],
      prediction: null,
      reality: {
        realityEvents: [],
        alerts: [],
        adapterStatus: null,
        vesselMatch: null,
        skipped: [],
      },
    },
  ],
});

vi.mock('./client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./client')>();
  return { ...actual, getJson: (...args: unknown[]) => getJson(...args) };
});

describe('getShipmentsOverview', () => {
  it('요청 한 번으로 선적 상세와 현실 대조 뷰를 함께 돌려준다', async () => {
    const { getShipmentsOverview } = await import('./shipment');
    const out = await getShipmentsOverview();
    expect(getJson).toHaveBeenCalledTimes(1);
    expect(getJson.mock.calls[0][0]).toBe('/api/v1/shipments/overview');
    expect(out).toHaveLength(1);
    expect(out[0].shipment.shipment_id).toBe('shp-1');
    expect(out[0].reality).toBeDefined();
  });
});
