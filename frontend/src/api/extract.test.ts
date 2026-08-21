import { describe, expect, it, vi } from 'vitest';
import type { WireBLDraft } from './wireExtract';

const emptyDraft: WireBLDraft = {
  image_id: 'img-1',
  form_type: 'BL',
  source: 'test',
  ocr_mean_confidence: 0.9,
  processing_time_ms: 100,
  completeness: 1,
  is_ready_for_verification: true,
  review_required_count: 0,
  fields: [],
};

const postForm = vi.fn().mockResolvedValue(emptyDraft);

vi.mock('./client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./client')>();
  return { ...actual, postForm: (...args: Parameters<typeof actual.postForm>) => postForm(...args) };
});

const { extractDraft } = await import('./extract');

function fileNamed(name: string): File {
  return new File(['x'], name);
}

describe('extractDraft 확장자 라우팅', () => {
  it('.pdf는 /extract/pdf로, page는 0부터 받아 1부터로 맞춰 보냄', async () => {
    postForm.mockClear();
    await extractDraft(fileNamed('bl.pdf'), { page: 0 });
    expect(postForm).toHaveBeenCalledWith('/extract/pdf', expect.any(FormData), { page: 0 }, undefined);
  });

  it('.jpg/.png 등 이미지는 /extract로, page 파라미터 없이 보냄', async () => {
    postForm.mockClear();
    await extractDraft(fileNamed('scan.png'));
    expect(postForm).toHaveBeenCalledWith('/extract', expect.any(FormData), undefined, undefined);
  });

  it('.txt처럼 지원 목록에 있어도 추출 엔드포인트가 없는 확장자는 거절', async () => {
    postForm.mockClear();
    await expect(extractDraft(fileNamed('note.txt'))).rejects.toThrow(
      '이 형식은 아직 자동 추출을 지원하지 않습니다.',
    );
    expect(postForm).not.toHaveBeenCalled();
  });

  it('대문자 확장자도 소문자로 취급 (.PDF)', async () => {
    postForm.mockClear();
    await extractDraft(fileNamed('bl.PDF'));
    expect(postForm).toHaveBeenCalledWith('/extract/pdf', expect.any(FormData), { page: 0 }, undefined);
  });
});
