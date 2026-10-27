import { useState, type CSSProperties } from 'react';
import { useSearchParams } from 'react-router-dom';
import { REISSUE_PATH_LABEL, SHIPMENT_STATUS, labelOfField } from '../../constants/domain';
import type { ResolvedConflicts } from '../../shared/shipmentStats';
import type { ImpactResult, Shipment } from '../../types/domain';
import {
  mockImpactByField,
  mockOverlappingSuggestions,
  mockReissueByStatus,
} from '../../mocks/shipment.fixture';
import { impactItemKey, mergeImpactItems } from './impactMerge';
import { ImpactItemCard } from './ImpactItemCard';
import { OverlapWarning } from './OverlapWarning';
import { hasOverlappingSpans } from './spanOverlap';

interface ImpactPanelProps {
  /** 이 선적의 영향분석 결과 — 재발행 경로 폴백(mockReissueByStatus에 없는 상태용)으로만 씁니다 */
  impact: ImpactResult;
  /** 재발행 경로를 선적 상태에서 뽑기 위해 필요합니다(요구사항 6). S3Draft가 :id로 찾아 넘겨줍니다 */
  shipment: Shipment;
  /**
   * S3Draft가 들고 있는 "필드별 수정값" 상태 — 이 패널이 구독하는 입력 중 하나.
   * 편집기 내부 상태에는 직접 접근하지 않습니다 (화면전이_정의.md §S3↔S8).
   */
  editedValues: Record<string, string | null>;
  /**
   * 값 충돌을 해소한 필드. editedValues와 별도입니다 — 후보 선택은 "값 수정"이
   * 아니라 "충돌 해소"로 따로 다루기 때문입니다(M-2). 둘 다 안 보면 후보를
   * 골라도 패널이 반응하지 않습니다.
   */
  resolvedConflicts: ResolvedConflicts;
}

// 뷰어+필드폼+패널을 한 줄에 다 넣으면 필드폼이 심하게 눌려서, 패널은 화면
// 오른쪽에 뜨는 고정(fixed) 패널로 뺐습니다. bottom 대신 maxHeight를 써서
// 내용이 짧을 때 빈 공간이 남지 않게 하고, 길어지면 스크롤(overflowY)만 생깁니다.
const panelBaseStyle: CSSProperties = {
  position: 'fixed',
  top: 'var(--space-5)',
  right: 'var(--space-3)',
  width: 320,
  maxHeight: 'calc(100vh - var(--space-5) - var(--space-4))',
  overflowY: 'auto',
  zIndex: 20,
  display: 'flex',
  flexDirection: 'column',
  gap: 12,
  padding: 'var(--space-3)',
  border: '1px solid var(--border-default)',
  borderRadius: 'var(--radius-card)',
  boxShadow: 'var(--shadow-card)',
  backgroundColor: 'var(--bg-card)',
  textAlign: 'left',
};

/**
 * S8 정정 영향분석 패널 — 축소 구현 (깊이 2, 제약 3종 EQ·SUM·REF만).
 *
 * 별도 화면이 아니라 S3 안의 사이드 패널입니다. 화면전이_정의.md §1에 따라
 * `?impact=1` URL 상태로 열림/닫힘을 관리하고(별도 라우트 없음), 이 컴포넌트가
 * 그 쿼리 파라미터를 직접 읽습니다 — 부모(S3Draft)가 열림 상태를 따로
 * 내려줄 필요가 없습니다.
 *
 * 예전에는 WATCHED_FIELD = 'port_of_loading' 하나만 하드코딩해서 반응했는데,
 * 지금은 mockImpactByField를 써서 사용자가 실제로 고친 모든 필드를 봅니다.
 */
export function ImpactPanel({ impact, shipment, editedValues, resolvedConflicts }: ImpactPanelProps) {
  const [searchParams] = useSearchParams();
  const isOpen = searchParams.get('impact') === '1';

  // 재확인 체크박스 상태 — 이 컴포넌트만의 로컬 state입니다. F5는 백엔드가
  // 없어서 저장할 곳이 없고, 화면을 벗어나거나 새로고침하면 그대로 사라집니다.
  // (규약 §5 자동 반영 금지와는 무관 — 체크는 필드 값을 바꾸지 않습니다)
  const [checkedKeys, setCheckedKeys] = useState<Record<string, boolean>>({});

  if (!isOpen) return null;

  function toggleCheck(key: string) {
    setCheckedKeys((prev) => ({ ...prev, [key]: !prev[key] }));
  }

  // 직접 입력이든 후보 선택이든 "이 필드 값이 정해졌다"는 점은 같습니다
  const changedFields = [
    ...new Set([...Object.keys(editedValues), ...Object.keys(resolvedConflicts)]),
  ];

  if (changedFields.length === 0) {
    return (
      <div style={panelBaseStyle}>
        <h2 className="section-title" style={{ margin: 0 }}>정정 영향분석</h2>
        <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
          아직 고친 필드가 없습니다. 값을 고치면 여기에 영향 범위가 표시됩니다.
        </p>
      </div>
    );
  }

  const merged = mergeImpactItems(changedFields, mockImpactByField);
  const directItems = merged.filter((m) => !m.item.indirect);
  const indirectItems = merged.filter((m) => m.item.indirect);
  const recheckItems = merged.filter((m) => m.item.requires_recheck);
  const checkedCount = recheckItems.filter((m) => checkedKeys[impactItemKey(m.item)]).length;

  // 재발행 경로는 impact.reissue_path 고정값이 아니라 선적 상태로 다시 뽑습니다.
  // mockReissueByStatus에 없는 상태(CLOSED)면 impact.reissue_path로 물러납니다.
  const reissuePath = mockReissueByStatus[shipment.status] ?? impact.reissue_path;
  const requiresAmendment = SHIPMENT_STATUS[shipment.status].order >= SHIPMENT_STATUS.SUBMITTED.order;

  // span 겹침 경고 — 사용자가 고친 필드 중 자유서식 필드에서, 승인 대기 중인
  // 교정 제안끼리 글자 범위가 겹치는 게 있는지 봅니다.
  const overlapWarnings = changedFields
    .map((field) => {
      const spans = mockOverlappingSuggestions
        .filter((s) => s.field === field && s.span !== undefined)
        .map((s) => s.span!);
      return { field, count: spans.length, overlapping: hasOverlappingSpans(spans) };
    })
    .filter((w) => w.overlapping);

  return (
    <div style={panelBaseStyle}>
      <h2 className="section-title" style={{ margin: 0 }}>정정 영향분석</h2>
      <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
        고친 필드 {changedFields.length}개({changedFields.map((f) => labelOfField(f)).join(', ')})에
        따라 아래 항목을 다시 확인해야 합니다.
      </p>

      {recheckItems.length > 0 && (
        <p style={{ margin: 0, fontSize: 12, color: 'var(--text-muted)' }}>
          재확인 {recheckItems.length}건 중 {checkedCount}건 확인
          {/* 저장되지 않는다는 사실을 화면에도 밝힙니다 (F5 백엔드 없음) */}
          <br />
          체크 상태는 저장되지 않습니다 — 화면을 벗어나면 초기화됩니다.
        </p>
      )}

      {overlapWarnings.map((w) => (
        <OverlapWarning key={w.field} field={w.field} count={w.count} />
      ))}

      {directItems.map((m) => (
        <ImpactItemCard
          key={impactItemKey(m.item)}
          merged={m}
          checked={!!checkedKeys[impactItemKey(m.item)]}
          onToggleCheck={toggleCheck}
        />
      ))}

      {indirectItems.length > 0 && (
        // 새 라이브러리·커스텀 아코디언 없이 네이티브 details/summary로 펼칩니다
        <details>
          <summary style={{ fontSize: 12, color: 'var(--text-muted)', cursor: 'pointer' }}>
            간접 영향 {indirectItems.length}건 더 있음 (펼쳐서 보기)
          </summary>
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginTop: 8 }}>
            {indirectItems.map((m) => (
              <ImpactItemCard
                key={impactItemKey(m.item)}
                merged={m}
                checked={!!checkedKeys[impactItemKey(m.item)]}
                onToggleCheck={toggleCheck}
              />
            ))}
          </div>
        </details>
      )}

      <div
        style={{
          fontSize: 12,
          color: 'var(--text-muted)',
          borderTop: '1px solid var(--border-default)',
          paddingTop: 8,
        }}
      >
        재발행 경로: {REISSUE_PATH_LABEL[reissuePath]}
        {requiresAmendment && (
          <span style={{ color: 'var(--severity-warning)', fontWeight: 700 }}>
            {' '}
            · 은행 조건 변경(amendment) 필요
          </span>
        )}
      </div>
    </div>
  );
}
