/**
 * 화면에서 `/normalize`를 부르기 쉽게 감싼 훅. useVerify.ts와 같은 모양입니다.
 */

import { useEffect, useState } from 'react';
import { normalizeShipment } from './normalize';
import type { NormalizeView } from './adaptersNormalize';
import type { FieldValue } from '../types/domain';

export type NormalizeState =
  | { status: 'loading' }
  | { status: 'ok'; view: NormalizeView }
  | { status: 'error'; error: Error };

export function useNormalize(fields: FieldValue[] | null): NormalizeState {
  const [state, setState] = useState<NormalizeState>({ status: 'loading' });

  useEffect(() => {
    if (fields === null) return;

    const controller = new AbortController();
    setState({ status: 'loading' });

    normalizeShipment(fields, controller.signal)
      .then((view) => setState({ status: 'ok', view }))
      .catch((err: unknown) => {
        if (controller.signal.aborted) return;
        setState({
          status: 'error',
          error: err instanceof Error ? err : new Error(String(err)),
        });
      });

    return () => controller.abort();
  }, [fields]);

  return state;
}
