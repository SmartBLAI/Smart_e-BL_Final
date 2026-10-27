import { afterEach, describe, expect, it, vi } from 'vitest';
import { postJson } from './client';

afterEach(() => vi.unstubAllGlobals());

describe('postJson', () => {
  it('204 No Content 는 본문 없이 성공으로 처리한다 (값 확인함 회귀)', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => new Response(null, { status: 204 })));
    await expect(postJson('/x', {})).resolves.toBeUndefined();
  });
});
