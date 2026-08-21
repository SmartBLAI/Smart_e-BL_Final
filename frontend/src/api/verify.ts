/**
 * F3 하자 검증 — `POST /verify` 한 번 호출하고 화면용으로 번역까지.
 *
 * 화면은 이 함수만 부르면 됩니다. 백엔드 응답 모양(`wire.ts`)이나 번역
 * 규칙(`adapters.ts`)을 화면이 알 필요는 없습니다.
 */

import { postJson } from './client';
import { toBLPayload, toVerifyView, type VerifyView } from './adapters';
import type { WireVerifyRequest, WireVerifyResponse } from './wire';
import type { FieldValue } from '../types/domain';

// 대시보드는 카드마다 이 함수를 부릅니다 — 선적이 N건이면 N개의 POST /verify가
// 동시에 나가 백엔드가 순간적으로 400을 뱉는 문제가 있었습니다(P1-2). 모든
// 호출이 이 함수 하나를 거치므로, 여기 한 곳에서만 동시 실행 수를 제한하면
// 호출부(S1 카드, S4 등)를 손대지 않고 고쳐집니다.
const MAX_CONCURRENT_VERIFY = 3;
let inFlight = 0;
const waiters: Array<() => void> = [];

async function acquireVerifySlot(): Promise<void> {
  if (inFlight < MAX_CONCURRENT_VERIFY) {
    inFlight += 1;
    return;
  }
  // 줄을 서서 기다립니다. 깨어났다는 건 앞사람이 자기 자리를 **넘겨줬다는**
  // 뜻이라 여기서 inFlight를 다시 올리지 않습니다 — 올리면 이중 계산입니다.
  await new Promise<void>((resolve) => waiters.push(resolve));
}

function releaseVerifySlot(): void {
  const next = waiters.shift();
  if (next) {
    // 자리를 비우지 않고 그대로 다음 사람에게 넘깁니다.
    //
    // 전에는 `inFlight -= 1` 을 먼저 하고 다음 사람을 깨웠는데, 깨우는 건
    // 즉시가 아니라 "다음 차례"에 일어납니다. 그 틈에 새 호출이 끼어들면
    // 비어 보이는 자리를 가져가고, 뒤늦게 깨어난 사람도 자리를 하나 더
    // 세어서 상한 3을 넘겼습니다. 카드가 여러 장 한꺼번에 뜨는 대시보드에서
    // 정확히 그 상황이 납니다.
    next();
    return;
  }
  inFlight -= 1;
}

export interface VerifyOptions {
  /** 신용장 조건(MT700). 없으면 백엔드가 서류 내부 정합성만 검사합니다 */
  lc?: Record<string, unknown>;
  /**
   * 제시기간 계산 기준 시각.
   * 시연·테스트에서 이걸 넣어야 매번 같은 결과가 나옵니다.
   */
  asOf?: string;
  /** 화면을 떠날 때 요청을 취소하기 위한 신호 */
  signal?: AbortSignal;
}

/**
 * 필드 목록을 백엔드에 보내 하자 검증 결과를 받아옵니다.
 *
 * 용어: `async` 함수는 결과를 바로 주지 않고 "곧 줄게"라는 약속(Promise)을
 * 줍니다. 부르는 쪽에서 `await` 로 기다립니다.
 */
export async function verifyShipment(
  fields: FieldValue[],
  options: VerifyOptions = {},
): Promise<VerifyView> {
  const body: WireVerifyRequest = {
    bl: toBLPayload(fields),
    ...(options.lc ? { lc: options.lc } : {}),
    ...(options.asOf ? { as_of: options.asOf } : {}),
  };

  await acquireVerifySlot();
  try {
    const res = await postJson<WireVerifyResponse>('/verify', body, options.signal);

    // 백엔드가 판정 시각을 안 주므로 응답을 받은 시각으로 대신합니다.
    // 동기 호출이라 실제 판정 시각과 밀리초 단위 차이입니다.
    return toVerifyView(res, new Date().toISOString());
  } finally {
    releaseVerifySlot();
  }
}
