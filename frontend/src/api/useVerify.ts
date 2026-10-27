/**
 * 화면에서 `/verify` 를 부르기 쉽게 감싼 훅(hook).
 *
 * 용어: "훅"은 React 컴포넌트가 상태(state)나 바깥 세계(네트워크 등)를
 * 쓰게 해주는 함수입니다. 이름이 `use` 로 시작해야 React 가 알아봅니다.
 */

import { useEffect, useState } from 'react';
import { verifyShipment } from './verify';
import { loadLcParse, type LcParse } from './lc';
import type { VerifyView } from './adapters';
import type { DocumentMeta, FieldValue } from '../types/domain';

/**
 * 지금 어떤 상태인지.
 *
 * · `loading` — 백엔드에 물어보는 중
 * · `ok`      — 받아왔음. `view` 에 결과가 들어 있음
 * · `error`   — 실패. `error` 에 이유가 들어 있음 (화면은 목데이터로 물러남)
 */
export type VerifyState =
  | { status: 'loading' }
  | { status: 'ok'; view: VerifyView; lc: LcParse | null }
  | { status: 'error'; error: Error };

/**
 * @param documents 그 선적의 서류 목록. 신용장(`kind: 'LC'`)이 들어 있으면
 *   L/C 조건까지 같이 실어 보냅니다 — 안 실으면 룰 29개 중 17개가 조용히
 *   빠지고 결과는 "위반 0건"으로 보입니다. 서류 목록이 없거나 신용장이
 *   없으면 지금까지처럼 서류 내부 정합성만 검사합니다.
 */
export function useVerify(
  fields: FieldValue[] | null,
  options: { asOf?: string; shipmentId?: string; documents?: DocumentMeta[] } = {},
): VerifyState {
  const [state, setState] = useState<VerifyState>({ status: 'loading' });
  const { asOf, shipmentId, documents } = options;

  useEffect(() => {
    if (fields === null) return;

    // 화면을 떠나면 요청을 취소합니다. 취소하지 않으면 이미 사라진
    // 컴포넌트에 결과를 넣으려다 경고가 납니다.
    const controller = new AbortController();

    setState({ status: 'loading' });

    // L/C 를 못 읽어도 검증은 진행합니다 — 대조 기준 없이 돌린 결과라도
    // 아예 없는 것보다 낫고, 화면은 lc 가 null 인 걸로 그 사실을 압니다.
    const lcPromise =
      shipmentId && documents
        ? loadLcParse(shipmentId, documents).catch(() => null)
        : Promise.resolve(null);

    lcPromise
      .then(async (parsed) => {
        const view = await verifyShipment(fields, {
          asOf,
          lc: parsed?.lc,
          shipmentId,
          signal: controller.signal,
        });
        setState({ status: 'ok', view, lc: parsed });
      })
      .catch((err: unknown) => {
        // 취소는 실패가 아닙니다 — 그냥 조용히 끝냅니다.
        if (controller.signal.aborted) return;
        setState({
          status: 'error',
          error: err instanceof Error ? err : new Error(String(err)),
        });
      });

    return () => controller.abort();
    // fields 는 목데이터라 매 렌더마다 같은 객체입니다. 선적이 바뀌면
    // 새 배열이 오므로 그때만 다시 부릅니다. documents 도 같은 출처(스토어)라
    // 같은 규칙을 따릅니다.
  }, [fields, asOf, shipmentId, documents]);

  return state;
}
