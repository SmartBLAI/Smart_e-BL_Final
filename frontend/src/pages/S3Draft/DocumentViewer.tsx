import type { CSSProperties } from 'react';
import type { DocumentMeta, FieldValue } from '../../types/domain';
import { DOCUMENT_KIND_LABEL, labelOfField, toConfidenceGrade } from '../../constants/domain';
import { GradeBadge } from '../../components/GradeBadge';
import { GATEWAY_API_BASE_URL } from '../../api/client';
import {
  MOCK_DOCUMENT_ORIGINAL_SIZE,
  bboxToScreenRect,
  type DocumentDisplaySize,
} from './documentGeometry';

// 게이트웨이 서류는 진짜 uuid를 씁니다. 픽스처 서류는 'DOC-001'처럼 사람이
// 지은 id라 이 모양이 절대 아닙니다 — 그 차이로 "실제 파일이 있는 서류"인지
// 판단합니다(별도 플래그를 DocumentMeta에 추가하지 않고 재사용).
const UUID_RE = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

// 문서를 화면에 얼마나 크게 그릴지. 612:792 비율을 유지한 채 폭만 480px로 고정.
// 나중에 실제 PDF 뷰어로 바꿀 때도 이 크기를 그대로 두고, 안쪽 내용만 바꾸면 됩니다.
// export하는 이유: S3Draft가 영향 패널을 여는 동안 뷰어 대신 보여주는 "숨김
// 안내" 박스 높이를 여기 맞춰서, 뷰어가 있던 자리 크기가 느껴지게 합니다.
export const DISPLAY_SIZE: DocumentDisplaySize = {
  width: 480,
  height: Math.round(
    480 * (MOCK_DOCUMENT_ORIGINAL_SIZE.height / MOCK_DOCUMENT_ORIGINAL_SIZE.width),
  ),
};

interface DocumentViewerProps {
  /** 지금 사용자가 보고 있는 필드. bbox가 있으면 문서 위에 노란 박스로 표시합니다 */
  focusedField?: FieldValue;
  /**
   * 이 선적에 붙어 있는 서류. 탭으로 그립니다.
   *
   * 시안은 4개(신용장·선적요청서·상업송장·포장명세서)를 고정으로 그렸지만,
   * 여기서는 넘어온 목록 그대로만 그립니다 — 서류가 2건뿐인 선적은 탭도
   * 2개가 뜨는 게 맞습니다.
   */
  documents: DocumentMeta[];
  /** 실제 서류 파일을 게이트웨이에서 받아올 때 URL을 만드는 데 씁니다 */
  shipmentId: string;
}

/**
 * S3 초안 편집기의 문서 뷰어.
 *
 * 픽스처 서류(목데이터 4건)는 실제 파일이 없어서 회색 사각형(목업)을 그대로
 * 보여줍니다. 게이트웨이에 실제로 업로드된 서류(document_id가 uuid)는
 * `<iframe>`으로 브라우저 내장 PDF 뷰어를 띄웁니다 — pdf.js 등 새 라이브러리
 * 없이 브라우저가 이미 하는 일을 그대로 씁니다.
 *
 * focusedField로 필드가 넘어오고 그 필드에 bbox(원본 좌표)가 있으면, 문서의
 * 어느 위치에서 그 값을 읽었는지 반투명한 노란 박스로 겹쳐서 표시합니다 —
 * 단, 목업(회색 사각형) 위에서만입니다. 실제 PDF는 iframe 내부 페이지
 * 렌더링 크기·스크롤 위치를 밖에서 알 수 없어 좌표를 겹칠 수 없습니다.
 * ponytail: 실제 PDF 위 하이라이트가 필요해지면 pdf.js로 직접 캔버스에
 * 그리는 방식으로 바꿔야 합니다.
 */
export function DocumentViewer({ focusedField, documents, shipmentId }: DocumentViewerProps) {
  // 어느 탭을 보여줄지는 지금 선택된 필드가 정합니다 — 필드를 누르면 그 값이
  // 나온 서류로 자동으로 넘어갑니다. 아직 아무 필드도 안 눌렀으면 첫 서류.
  // (탭을 직접 누르는 기능은 필드 클릭과 규칙이 충돌할 수 있어 뒤로 미룹니다)
  const activeDocument =
    documents.find((document) => document.document_id === focusedField?.source_doc_id) ??
    documents[0] ??
    null;
  const fileUrl =
    activeDocument !== null && UUID_RE.test(activeDocument.document_id)
      ? `${GATEWAY_API_BASE_URL}/api/v1/shipments/${shipmentId}/documents/${activeDocument.document_id}/file`
      : null;
  const bbox = fileUrl === null ? (focusedField?.bbox ?? null) : null;
  // %로 계산합니다(px 아님) — .s3-viewer-box의 실제 렌더 폭은 480px 고정이
  // 아니라 CSS(width:100%, max-width:480px)로 화면 폭에 따라 줄어듭니다.
  // px로 계산하면 좁은 화면에서 박스는 작아지는데 하이라이트는 480px 기준
  // 그대로라 어긋납니다. %는 부모 크기에 맞춰 같이 줄어들어서 항상 맞습니다.
  const highlightRect =
    bbox !== null ? bboxToScreenRect(bbox, MOCK_DOCUMENT_ORIGINAL_SIZE, { width: 100, height: 100 }) : null;
  const documentAreaStyle: CSSProperties = {
    position: 'relative',
    // 종이 문서를 흉내내는 자리라서 앱 다크/라이트 테마와 무관하게 고정된
    // 종이색을 씁니다. var(--bg-card)를 쓰면 다크 테마에서 거의 검은색이 돼서
    // "미리보기가 고장났다"로 오해받기 쉬웠습니다.
    backgroundColor: '#f4f3ef',
    border: '1px solid #d8d5cd',
    borderRadius: 'var(--radius-card)',
    boxShadow: 'var(--shadow-card)',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'center',
    overflow: 'hidden',
  };

  return (
    <div
      // 오른쪽 필드 목록을 스크롤해도 문서 뷰어는 화면에 계속 보이도록 고정.
      // 좁은 화면(1024px 이하)에서는 위아래로 쌓이기 때문에 고정을 풀어야 합니다 —
      // 그대로 두면 뷰어가 아래 필드 목록 위로 미끄러져 내려와 글자가 겹칩니다.
      // 미디어쿼리는 인라인 스타일로 못 쓰므로 index.css의 클래스로 뺐습니다.
      className="s3-viewer-sticky"
      style={{
        display: 'inline-flex',
        flexDirection: 'column',
        alignItems: 'flex-start',
        gap: 6,
      }}
    >
      {documents.length > 0 && (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 4, width: '100%' }}>
          <div
            style={{
              display: 'flex',
              flexWrap: 'wrap',
              gap: 2,
              borderBottom: '1px solid var(--border-default)',
            }}
          >
            {documents.map((document) => {
              const isActive = document.document_id === activeDocument?.document_id;
              return (
                <span
                  key={document.document_id}
                  style={{
                    padding: '8px 11px',
                    fontSize: 12.5,
                    fontWeight: isActive ? 700 : 500,
                    color: isActive ? 'var(--text-primary)' : 'var(--text-secondary)',
                    borderBottom: `2px solid ${isActive ? 'var(--brand-primary)' : 'transparent'}`,
                    marginBottom: -1,
                  }}
                >
                  {DOCUMENT_KIND_LABEL[document.kind]}
                </span>
              );
            })}
          </div>
          {activeDocument !== null && (
            <div
              style={{
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: 'var(--space-2)',
                fontSize: 11.5,
                color: 'var(--text-muted)',
              }}
            >
              <span style={{ minWidth: 0, overflowWrap: 'anywhere' }}>
                {activeDocument.file_name}
              </span>
              <span style={{ flexShrink: 0 }}>{activeDocument.page_count}p</span>
            </div>
          )}
        </div>
      )}

      {/* 실제 서류가 있으면 iframe으로 진짜 파일을, 없으면(픽스처) 회색 목업을 보여줌 */}
      <div className="s3-viewer-box" style={documentAreaStyle}>
        {fileUrl !== null ? (
          <iframe
            src={fileUrl}
            title={activeDocument?.file_name ?? '문서 미리보기'}
            style={{ width: '100%', height: '100%', border: 'none' }}
          />
        ) : (
          <span style={{ fontSize: 12, color: '#8a8680' }}>문서 미리보기 (목업)</span>
        )}

        {highlightRect !== null && (
          <div
            aria-hidden="true"
            style={{
              position: 'absolute',
              left: `${highlightRect.left}%`,
              top: `${highlightRect.top}%`,
              width: `${highlightRect.width}%`,
              height: `${highlightRect.height}%`,
              backgroundColor: 'rgba(250, 204, 21, 0.35)',
              border: '1.5px solid rgba(217, 160, 12, 0.9)',
              borderRadius: 2,
            }}
          />
        )}
      </div>

      {/* 뷰어 아래 근거 정보 — 실제 PDF가 없어 회색 박스가 비어 보이는 자리를
          "지금 무엇을 보고 있는지"로 채웁니다. 값은 전부 선택된 필드에서 옵니다 */}
      <div
        style={{
          display: 'flex',
          flexDirection: 'column',
          gap: 6,
          width: '100%',
          padding: 'var(--space-2) 0 0',
          textAlign: 'left',
        }}
      >
        {focusedField === undefined ? (
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            오른쪽에서 필드를 누르면 그 값을 어느 서류 어디에서 읽었는지 여기 표시됩니다.
          </span>
        ) : (
          <>
            <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
              <span style={{ fontSize: 12.5, fontWeight: 700, color: 'var(--text-primary)' }}>
                {labelOfField(focusedField.field_name)}
              </span>
              {/* 신뢰도는 숫자(64%)가 아니라 등급으로 보여줍니다 — 판단 기준은
                  CONFIDENCE_THRESHOLD가 갖고 있으므로 사용자가 숫자를 해석할
                  필요가 없습니다 */}
              <GradeBadge grade={toConfidenceGrade(focusedField)} size="sm" />
              <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                {focusedField.bbox === null
                  ? '원문 근거 없음'
                  : `${focusedField.source_doc_id} · ${focusedField.page}p`}
              </span>
            </div>

            {/* 다른 서류에 다른 값이 있으면 그것도 밝힙니다 (시안의 "충돌 후보" 카드) */}
            {(focusedField.candidates ?? [])
              .filter((candidate) => candidate.value !== focusedField.value)
              .map((candidate) => (
                <div
                  key={`${candidate.source_doc_id}-${candidate.value}`}
                  style={{
                    display: 'flex',
                    flexDirection: 'column',
                    gap: 3,
                    padding: '10px 12px',
                    border: '1px solid var(--border-default)',
                    borderLeft: '4px solid var(--severity-critical)',
                    borderRadius: 6,
                    backgroundColor: 'var(--bg-card)',
                  }}
                >
                  <span style={{ fontSize: 11.5, fontWeight: 700, color: 'var(--severity-critical)' }}>
                    다른 서류의 충돌 후보
                  </span>
                  <span style={{ fontSize: 13, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {candidate.value}
                    {candidate.normalized_value !== null && (
                      <span style={{ fontWeight: 400, color: 'var(--text-secondary)' }}>
                        {' '}
                        {candidate.normalized_value}
                      </span>
                    )}
                  </span>
                  <span
                    style={{
                      display: 'inline-flex',
                      alignItems: 'center',
                      gap: 6,
                      flexWrap: 'wrap',
                      fontSize: 11.5,
                      color: 'var(--text-muted)',
                    }}
                  >
                    <GradeBadge grade={toConfidenceGrade(candidate)} size="sm" />
                    {candidate.source_doc_id} · {candidate.page}p
                  </span>
                </div>
              ))}
          </>
        )}
      </div>
    </div>
  );
}
