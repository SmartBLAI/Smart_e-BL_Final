/**
 * F1 서류 인테이크 — 파일을 aiService로 보내 필드를 추출합니다.
 *
 * 화면(S2Upload)은 이 함수 하나만 부르면 됩니다. 확장자별로 어느 엔드포인트로
 * 보낼지는 여기서 결정합니다.
 */

import { ApiError, postForm } from './client';
import { toDraftFields } from './adaptersExtract';
import type { WireBLDraft } from './wireExtract';
import type { FieldValue } from '../types/domain';

function getExtension(fileName: string): string {
  const dotIndex = fileName.lastIndexOf('.');
  return dotIndex === -1 ? '' : fileName.slice(dotIndex).toLowerCase();
}

const IMAGE_EXT = ['.jpg', '.jpeg', '.png', '.tif'];

export interface ExtractOptions {
  /** PDF 여러 페이지 중 몇 번째를 읽을지 (0부터) */
  page?: number;
  signal?: AbortSignal;
}

/**
 * 파일을 확장자로 보고 알맞은 aiService 엔드포인트로 보냅니다.
 *
 * ⚠ `.txt`는 SUPPORTED_INPUT.ACCEPTED_EXT(constants/domain.ts)에는 있지만,
 *   백엔드에 대응하는 추출 엔드포인트가 없습니다(`/lc/mt700`은 SWIFT MT700
 *   전용이라 다른 용도). 잘못된 엔드포인트로 보내 헷갈리는 에러를 받는 대신
 *   여기서 바로 명확한 메시지로 거절합니다.
 */
export async function extractDraft(file: File, options: ExtractOptions = {}): Promise<FieldValue[]> {
  const ext = getExtension(file.name);
  const form = new FormData();
  form.append('file', file);

  let draft: WireBLDraft;
  // DB의 field_value.page는 1부터 시작(field_value_page_ck) — options.page(0부터)를 여기서 맞춰줍니다.
  let page: number;
  if (ext === '.pdf') {
    page = (options.page ?? 0) + 1;
    draft = await postForm<WireBLDraft>(
      '/extract/pdf',
      form,
      { page: options.page ?? 0 },
      options.signal,
    );
  } else if (IMAGE_EXT.includes(ext)) {
    page = 1;
    draft = await postForm<WireBLDraft>('/extract', form, undefined, options.signal);
  } else {
    throw new ApiError(0, '이 형식은 아직 자동 추출을 지원하지 않습니다.');
  }

  return toDraftFields(draft, page);
}
