import { describe, expect, it, vi } from 'vitest';
import type { DocumentMeta } from '../types/domain';

/**
 * loadLcParse는 파싱 결과를 서류 id로 캐시해 여러 화면이 나눠 씁니다.
 * 그 "나눠 쓰는 약속"에 한 화면의 취소 신호가 섞이면, 그 화면이 사라질 때
 * 다음 화면의 결과까지 같이 취소됩니다 — S4가 신용장을 못 읽고 "첨부되지
 * 않았습니다"라고 사실과 다르게 안내하게 되는 경로라 여기서 막습니다.
 */

const getText = vi.fn().mockResolvedValue('{1:F01...}');
const postJson = vi.fn().mockResolvedValue({ lc: {}, tags: {}, unmapped: {}, notes: [] });

vi.mock('./client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./client')>();
  return {
    ...actual,
    getText: (...args: unknown[]) => getText(...args),
    postJson: (...args: unknown[]) => postJson(...args),
  };
});

const { loadLcParse } = await import('./lc');

function docs(documentId: string): DocumentMeta[] {
  return [
    {
      document_id: 'doc-bl',
      kind: 'BL',
      file_name: 'bl.pdf',
      file_hash: 'h1',
      page_count: 1,
      version: 1,
      uploaded_at: '2026-08-20T00:00:00Z',
    },
    {
      document_id: documentId,
      kind: 'LC',
      file_name: 'lc.txt',
      file_hash: 'h2',
      page_count: 1,
      version: 1,
      uploaded_at: '2026-08-20T00:00:00Z',
    },
  ];
}

describe('loadLcParse', () => {
  it('신용장이 없으면 백엔드를 부르지 않고 null을 돌려준다', async () => {
    getText.mockClear();
    const onlyBl = docs('doc-lc-unused').filter((d) => d.kind === 'BL');

    expect(await loadLcParse('shp-1', onlyBl)).toBeNull();
    expect(getText).not.toHaveBeenCalled();
  });

  it('취소 신호를 넘기지 않는다 — 넘기면 한 화면의 이탈이 다른 화면 결과까지 취소시킨다', async () => {
    getText.mockClear();
    postJson.mockClear();

    await loadLcParse('shp-2', docs('doc-lc-2'));

    const [, , ...rest] = getText.mock.calls[0];
    expect(rest.filter((arg) => arg !== undefined)).toEqual([]);
    const [, , ...parseRest] = postJson.mock.calls[0];
    expect(parseRest.filter((arg) => arg !== undefined)).toEqual([]);
  });

  it('같은 서류는 화면이 몇 개든 한 번만 읽는다', async () => {
    getText.mockClear();

    const [a, b] = await Promise.all([
      loadLcParse('shp-3', docs('doc-lc-3')),
      loadLcParse('shp-3', docs('doc-lc-3')),
    ]);

    expect(getText).toHaveBeenCalledTimes(1);
    expect(a).toBe(b);
  });

  it('실패한 약속은 캐시에 남기지 않는다 — 다음 화면이 영원히 같은 실패를 받지 않도록', async () => {
    getText.mockClear();
    getText.mockRejectedValueOnce(new Error('일시적 오류'));

    await expect(loadLcParse('shp-4', docs('doc-lc-4'))).rejects.toThrow('일시적 오류');
    await expect(loadLcParse('shp-4', docs('doc-lc-4'))).resolves.not.toBeNull();
    expect(getText).toHaveBeenCalledTimes(2);
  });
});
