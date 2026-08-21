import { describe, expect, it, vi } from 'vitest';
import type { FieldValue } from '../types/domain';

/**
 * createDraftWithFields는 요청 네 개(선적 생성 → 서류 업로드 → 필드 저장 →
 * 신용장 업로드)로 이뤄집니다. 중간에 실패하면 선적만 만들어진 채로 끝나서,
 * 화면은 "실패"라고 알리는데 대시보드에는 빈 선적이 남습니다. 사용자가 다시
 * 시도할 때마다 하나씩 쌓이므로 되돌리기가 있어야 합니다.
 */

const postJson = vi.fn().mockResolvedValue({ shipment_id: 'shp-new' });
const postForm = vi.fn().mockResolvedValue({ document_id: 'doc-new' });
const putJson = vi.fn().mockResolvedValue({ saved: 1, skipped: [] });
const getJson = vi.fn().mockResolvedValue({
  shipment_id: 'shp-new',
  status: 'DRAFT',
  bl_no: null,
  cargo_control_no: null,
  lc_no: null,
  lc_expiry_date: null,
  created_at: '2026-08-21T00:00:00Z',
  updated_at: '2026-08-21T00:00:00Z',
  fields: [],
  documents: [],
  verdicts: [],
  prediction: null,
});
const deleteRequest = vi.fn().mockResolvedValue(undefined);

vi.mock('./client', async (importOriginal) => {
  const actual = await importOriginal<typeof import('./client')>();
  return {
    ...actual,
    postJson: (...args: unknown[]) => postJson(...args),
    postForm: (...args: unknown[]) => postForm(...args),
    putJson: (...args: unknown[]) => putJson(...args),
    getJson: (...args: unknown[]) => getJson(...args),
    deleteRequest: (...args: unknown[]) => deleteRequest(...args),
  };
});

const { createDraftWithFields } = await import('./shipment');

const file = new File(['x'], 'bl.pdf');
const fields: FieldValue[] = [];

describe('createDraftWithFields 되돌리기', () => {
  it('전부 성공하면 선적을 지우지 않는다', async () => {
    deleteRequest.mockClear();

    await createDraftWithFields(file, fields, 1);

    expect(deleteRequest).not.toHaveBeenCalled();
  });

  it('서류 업로드가 실패하면 방금 만든 선적을 지우고 원래 오류를 올려보낸다', async () => {
    deleteRequest.mockClear();
    postForm.mockRejectedValueOnce(new Error('업로드 실패'));

    await expect(createDraftWithFields(file, fields, 1)).rejects.toThrow('업로드 실패');
    expect(deleteRequest).toHaveBeenCalledWith('/api/v1/shipments/shp-new', '/gw-api', undefined);
  });

  it('필드 저장이 실패해도 마찬가지로 지운다', async () => {
    deleteRequest.mockClear();
    putJson.mockRejectedValueOnce(new Error('필드 저장 실패'));

    await expect(createDraftWithFields(file, fields, 1)).rejects.toThrow('필드 저장 실패');
    expect(deleteRequest).toHaveBeenCalledWith('/api/v1/shipments/shp-new', '/gw-api', undefined);
  });

  it('되돌리기까지 실패해도 사용자에게는 원래 오류를 보여준다', async () => {
    deleteRequest.mockClear();
    postForm.mockRejectedValueOnce(new Error('업로드 실패'));
    deleteRequest.mockRejectedValueOnce(new Error('삭제도 실패'));

    // "정리에 실패했다"가 아니라 "저장에 실패했다"가 알려져야 합니다
    await expect(createDraftWithFields(file, fields, 1)).rejects.toThrow('업로드 실패');
  });
});
