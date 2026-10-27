/**
 * 화면에서 `/report`를 부르기 쉽게 감싼 훅. useVerify.ts와 같은 모양입니다.
 */

import { useEffect, useState } from 'react';
import { generateReport } from './report';
import { loadLcParse, type LcParse } from './lc';
import type { ReportView } from './adaptersReport';
import type { DocumentMeta, FieldValue } from '../types/domain';

export type ReportState =
  | { status: 'loading' }
  | { status: 'ok'; view: ReportView; lc: LcParse | null }
  | { status: 'error'; error: Error };

// 같은 fields·documents(스토어가 들고 있는 참조)로 이미 만든 리포트는 다시 만들지 않는다.
// 화면을 다시 열 때마다 AI_REPORT 감사 행이 쌓이는 것을 막는다. 필드가 저장되면 스토어가
// 새 배열을 만들어 참조가 바뀌므로 그때 자동으로 다시 생성된다.
// ponytail: 모듈 전역 Map(새로고침 시 초기화) — 영속 재사용이 필요하면 스토어로 옮긴다.
const reported = new Map<
  string,
  { fields: FieldValue[]; documents?: DocumentMeta[]; state: Extract<ReportState, { status: 'ok' }> }
>();

/**
 * @param shipmentId, documents — useVerify.ts와 같은 이유로 L/C 조건을 같이
 *   싣습니다. 안 실으면 S4는 L/C 대조 위반을 보여주는데 S7은 그 룰들이
 *   "검사 못함"으로 빠져서 같은 선적인데 숫자가 어긋납니다.
 */
export function useReport(
  fields: FieldValue[] | null,
  options: { shipmentId?: string; documents?: DocumentMeta[] } = {},
): ReportState {
  const [state, setState] = useState<ReportState>({ status: 'loading' });
  const { shipmentId, documents } = options;

  useEffect(() => {
    if (fields === null) return;

    const hit = shipmentId ? reported.get(shipmentId) : undefined;
    if (hit && hit.fields === fields && hit.documents === documents) {
      setState(hit.state);
      return;
    }

    const controller = new AbortController();
    setState({ status: 'loading' });

    // L/C 를 못 읽어도 리포트는 진행합니다 — useVerify와 같은 규칙입니다.
    const lcPromise =
      shipmentId && documents
        ? loadLcParse(shipmentId, documents).catch(() => null)
        : Promise.resolve(null);

    lcPromise
      .then(async (parsed) => {
        const view = await generateReport(fields, parsed?.lc, controller.signal, shipmentId);
        const ok = { status: 'ok', view, lc: parsed } as const;
        if (shipmentId) reported.set(shipmentId, { fields, documents, state: ok });
        setState(ok);
      })
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: 'error',
          error: err instanceof Error ? err : new Error(String(err)),
        });
      });

    return () => controller.abort();
  }, [fields, shipmentId, documents]);

  return state;
}
