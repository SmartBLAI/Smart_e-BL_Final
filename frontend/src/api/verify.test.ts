import { describe, expect, it, vi } from 'vitest';
import type { WireVerifyResponse } from './wire';

/**
 * 대시보드는 카드마다 verifyShipment를 부릅니다. 동시에 몇 개까지 나가는지를
 * verify.ts가 스스로 제한하는데, 그 계산이 어긋나면 상한을 넘겨 백엔드가
 * 순간적으로 400을 뱉습니다(P1-2). 눈으로는 안 보이는 계산이라 여기서 셉니다.
 */

const emptyResponse: WireVerifyResponse = {
  shipment_id: null,
  verdict: {
    violations: [],
    skipped: [],
    skipped_count: 0,
    catalog: { label: 'v1' },
    model: null,
  },
  prediction: { probability: 0, model: 'rules-v1', is_defect: false, threshold: 0.5 },
} as unknown as WireVerifyResponse;

/** 지금 몇 개가 동시에 진행 중인지와, 그 최고 기록 */
let running = 0;
let peak = 0;
/** 각 요청을 우리가 원할 때 끝내려고 붙잡아 두는 손잡이들 */
const finishers: Array<() => void> = [];

const postJson = vi.fn(() => {
  running += 1;
  peak = Math.max(peak, running);
  return new Promise((resolve) => {
    finishers.push(() => {
      running -= 1;
      resolve(emptyResponse);
    });
  });
});

vi.mock('./client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./client')>();
  return { ...actual, postJson: () => postJson() };
});

const { verifyShipment } = await import('./verify');

describe('verifyShipment 동시 실행 제한', () => {
  /** 밀린 마이크로태스크가 전부 끝날 때까지 기다립니다 */
  const flush = () => new Promise((resolve) => setTimeout(resolve, 0));

  it('요청이 끝나는 틈에 새 요청이 끼어들어도 동시에 3개를 넘지 않는다', async () => {
    // 카드 5장이 한 번에 뜬 상황
    const calls = Array.from({ length: 5 }, () => verifyShipment([]));
    await flush();

    // 하나가 끝나는 **바로 그 순간** 새 카드가 하나 더 뜹니다. 이 틈이
    // 예전에 자리를 이중으로 세던 지점입니다 — 끝난 쪽이 자리를 비우고,
    // 그 빈자리를 새 요청이 가져가고, 뒤늦게 깨어난 대기자도 자리를 하나
    // 더 세어서 상한을 넘겼습니다.
    for (let i = 0; i < 5; i += 1) {
      const done = finishers.shift();
      if (!done) break;
      done();
      // 자리를 반납한 직후, 대기자가 깨어나기 **전**에 새 요청이 들어오는
      // 순간을 정확히 맞춥니다 — 이 한 틱이 예전 구현이 자리를 이중으로
      // 세던 창이었습니다(여기서 마이크로태스크를 더 기다리면 대기자가
      // 이미 깨어나 버려서 그 버그를 못 잡습니다).
      await Promise.resolve();
      calls.push(verifyShipment([]));
      await flush();
    }

    // 남은 것들을 마저 끝냅니다
    while (finishers.length > 0) {
      finishers.shift()!();
      await flush();
    }

    await Promise.all(calls);
    expect(peak).toBeLessThanOrEqual(3);
  });
});
