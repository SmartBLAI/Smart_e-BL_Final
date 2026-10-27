import { describe, expect, it, vi } from 'vitest';

const getJson = vi.fn();
const putJson = vi.fn();

vi.mock('./client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./client')>();
  return { ...actual, getJson: (...a: unknown[]) => getJson(...a), putJson: (...a: unknown[]) => putJson(...a) };
});

const { getOutcome, saveOutcome } = await import('./outcome');
const { ApiError } = await import('./client');

describe('outcome api', () => {
  it('204(본문 없음)는 기록 없음(null), 오류는 그대로 던진다', async () => {
    getJson.mockResolvedValueOnce(undefined);
    expect(await getOutcome('s1')).toBeNull();
    getJson.mockRejectedValueOnce(new ApiError(500, 'boom'));
    await expect(getOutcome('s1')).rejects.toThrow();
  });

  it('PUT 은 선적별 outcome 경로로 보낸다', async () => {
    putJson.mockResolvedValueOnce({});
    const input = { decision: 'APPROVED', reason: 'UNKNOWN', memo: '', decided_on: '2026-10-01' } as const;
    await saveOutcome('s1', input);
    expect(putJson.mock.calls[0][0]).toBe('/api/v1/shipments/s1/outcome');
    expect(putJson.mock.calls[0][1]).toEqual(input);
  });
});
