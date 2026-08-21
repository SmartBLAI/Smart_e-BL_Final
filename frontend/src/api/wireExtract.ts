/**
 * F1 서류 인테이크 — aiService `/extract`, `/extract/pdf` 응답 모양.
 *
 * 백엔드 `ocr/draft.py`의 `DraftField.to_dict()` / `BLDraft.to_dict()`와
 * 1:1로 맞춘 타입입니다. F3(`wire.ts`)와 같은 백엔드지만, 기능이 다르고
 * 한 파일에 다 몰아두면 너무 길어져서(규약: 파일 200줄 넘으면 먼저 물어보기)
 * 기능별로 나눴습니다.
 *
 * ⚠ 이 응답에는 source_doc_id가 없습니다. `source`는 "이 값을 어떤 방법으로
 *   뽑았는지"(region/anchor/llm)이지, 어떤 서류에서 왔는지가 아닙니다 —
 *   도메인 FieldValue의 source_doc_id와 다른 개념이니 착각하지 마세요.
 *   adaptersExtract.ts에서 번역할 때 이 차이를 그대로 반영합니다.
 *
 * bbox는 [x1, y1, x2, y2] 순서의 0~1 비율 좌표이거나(근거 있음), null(근거
 * 없음 — 값 자체가 null이거나 좌표를 합칠 수 없었던 경우)입니다.
 */

export interface WireDraftField {
  name: string;
  label: string;
  value: string | null;
  confidence: number | null;
  source: 'region' | 'anchor' | 'llm' | null;
  bbox: [number, number, number, number] | null;
  is_critical: boolean;
  needs_review: boolean;
  review_reason:
    | 'missing_critical'
    | 'missing'
    | 'low_confidence'
    | 'anchor_derived'
    | 'label_echoed'
    | 'uncalibrated_layout'
    | null;
  review_message: string | null;
}

export interface WireBLDraft {
  image_id: string;
  form_type: string;
  source: string;
  ocr_mean_confidence: number;
  processing_time_ms: number | null;
  completeness: number;
  is_ready_for_verification: boolean;
  review_required_count: number;
  fields: WireDraftField[];
}
