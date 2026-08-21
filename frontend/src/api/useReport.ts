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

    const controller = new AbortController();
    setState({ status: 'loading' });

    // L/C 를 못 읽어도 리포트는 진행합니다 — useVerify와 같은 규칙입니다.
    const lcPromise =
      shipmentId && documents
        ? loadLcParse(shipmentId, documents).catch(() => null)
        : Promise.resolve(null);

    lcPromise
      .then(async (parsed) => {
        const view = await generateReport(fields, parsed?.lc, controller.signal);
        setState({ status: 'ok', view, lc: parsed });
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
