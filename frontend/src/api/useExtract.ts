/**
 * F1 서류 인테이크 훅 — S2Upload가 파일 선택 시 직접 호출(run)하는 1회성 액션.
 *
 * useVerify처럼 마운트되자마자 자동 실행하는 게 아니라, 사용자가 파일을 골라야
 * 시작되므로 상태를 밖에서 트리거하는 형태로 만들었습니다.
 */

import { useCallback, useRef, useState } from 'react';
import { extractDraft } from './extract';
import { ApiError } from './client';
import type { FieldValue } from '../types/domain';

export type ExtractStatus = 'idle' | 'loading' | 'error';

export function useExtract() {
  const [status, setStatus] = useState<ExtractStatus>('idle');
  const [error, setError] = useState<string | null>(null);
  const abortRef = useRef<AbortController | null>(null);

  const run = useCallback(
    async (file: File): Promise<{ ok: true; fields: FieldValue[] } | { ok: false; message: string }> => {
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      setStatus('loading');
      setError(null);
      try {
        const fields = await extractDraft(file, { signal: controller.signal });
        setStatus('idle');
        return { ok: true, fields };
      } catch (err) {
        const message = err instanceof ApiError ? err.detail : '문서 인식에 실패했습니다.';
        setStatus('error');
        setError(message);
        return { ok: false, message };
      }
    },
    [],
  );

  const reset = useCallback(() => {
    setStatus('idle');
    setError(null);
  }, []);

  return { status, error, run, reset };
}
