import { useEffect, useRef, useState } from 'react';
import { FileQuestion, Loader2 } from 'lucide-react';
import { useParams, useSearchParams } from 'react-router-dom';
import { FieldForm } from './FieldForm';
import { DocumentViewer } from './DocumentViewer';
import { VerifyBar } from './VerifyBar';
import { ImpactPanel } from './ImpactPanel';
import { EmptyState } from '../../components/EmptyState';
import { PageContainer } from '../../components/PageContainer';
import { DataSourceNotice } from '../../components/DataSourceNotice';
import {
  useConfirmedFields,
  useEditField,
  useShipmentData,
  useShipmentStoreStatus,
} from '../../shared/shipmentStore';
import { toScreenFieldName } from '../../api/adapters';
import { ShipmentHeader } from '../../components/ShipmentHeader';
import {
  resolveConflicts,
  type ResolvedConflicts,
} from '../../shared/shipmentStats';
import { useNormalize } from '../../api/useNormalize';
import { applySuggestion, rejectSuggestion } from '../../api/normalize';
import { ApiError } from '../../api/client';
import type { FieldValue, RejectReason, Suggestion } from '../../types/domain';

export function S3Draft() {
  // S4·S7과 같은 방식 — URL(/shipments/:id/draft)의 :id로 이 선적의 묶음을 찾습니다
  const { id } = useParams();
  const data = useShipmentData(id);
  const storeStatus = useShipmentStoreStatus();

  // 백엔드 aiService의 /normalize를 부릅니다. data가 없으면(선적 못 찾음)
  // null을 넘겨 "요청하지 말라"고 알려줍니다 — S4의 useVerify와 같은 패턴.
  const normalize = useNormalize(data?.fields ?? null);

  // S8 영향분석 패널의 열림/닫힘은 ImpactPanel 스스로 이 값을 읽어서 결정합니다
  // (화면전이_정의.md §1: "?impact=1" URL 상태). 여기서는 토글 버튼만 둡니다.
  const [searchParams, setSearchParams] = useSearchParams();
  const isImpactOpen = searchParams.get('impact') === '1';

  function toggleImpactPanel() {
    const next = new URLSearchParams(searchParams);
    if (isImpactOpen) {
      next.delete('impact');
    } else {
      next.set('impact', '1');
    }
    setSearchParams(next);
  }

  // 지금 문서 뷰어에서 하이라이트할 필드. FieldRow를 클릭하면 여기로 들어옴.
  //
  // ?focus=<field_name>은 화면전이_정의.md §6에 정의된 규칙으로, S4 판정과 S6
  // 경보가 "이 필드 고치러 가기"로 넘어올 때 어느 필드를 볼지 지정합니다.
  // 새로고침·딥링크 직후에는 data가 아직 없어서(useState 초기값 시점) 못 찾으므로,
  // 데이터가 생긴 뒤에 한 번만 적용합니다. 룰 어휘(on_board_date 등)도 받아줍니다.
  const focusParam = searchParams.get('focus');
  const [focusedField, setFocusedField] = useState<FieldValue | null>(null);
  const appliedFocus = useRef<string | null>(null);

  useEffect(() => {
    if (focusParam === null || data === null || appliedFocus.current === focusParam) return;
    const target = data.fields.find((field) => field.field_name === toScreenFieldName(focusParam));
    if (target === undefined) return;
    appliedFocus.current = focusParam;
    setFocusedField(target);
    // 접힌 그룹이 펼쳐진 뒤(FieldGroup effect → 재렌더)에 행이 생기므로 두 프레임 뒤에 찾습니다
    requestAnimationFrame(() =>
      requestAnimationFrame(() =>
        document
          .querySelector(`[data-field-name="${target.field_name}"]`)
          ?.scrollIntoView({ block: 'center', behavior: 'smooth' }),
      ),
    );
  }, [focusParam, data]);

  // 값 수정은 즉시 스토어·게이트웨이에 저장됩니다(useEditField) — 그래서 필드 값
  // 자체는 data.fields가 항상 최신입니다. editedValues는 "이번에 고친 필드" 표식
  // (영향분석 패널이 이 키들을 봅니다)으로만 남겼고, 저장에 실패하면 키를 뺍니다.
  // 직접 타이핑과 교정 제안 승인은 같은 applyEdit를 거칩니다.
  const [editedValues, setEditedValues] = useState<Record<string, string | null>>({});
  const editField = useEditField();
  const blDocumentId = data?.documents.find((doc) => doc.kind === 'BL')?.document_id ?? null;
  const [savedField, setSavedField] = useState<string | null>(null);
  const [editError, setEditError] = useState<string | null>(null);

  function applyEdit(fieldName: string, value: string | null) {
    setEditError(null);
    setSavedField(null);
    setEditedValues((prev) => ({ ...prev, [fieldName]: value }));
    editField(id ?? '', blDocumentId, fieldName, value).then(
      () => {
        setSavedField(fieldName);
        setTimeout(() => setSavedField((cur) => (cur === fieldName ? null : cur)), 2000);
      },
      () => {
        setEditedValues((prev) => {
          const { [fieldName]: _undone, ...rest } = prev;
          return rest;
        });
        setEditError(`"${fieldName}" 값을 저장하지 못했습니다. 원래 값으로 되돌렸습니다.`);
      },
    );
  }

  // 값 충돌 필드에서 사용자가 고른 후보. editedValues와 따로 두는 이유는
  // "직접 새 값을 입력한 것"과 "이미 읽어낸 후보 중 고른 것"이 다른 행동이기
  // 때문입니다 — 후자는 원문의 인식 품질을 바꾸지 않으므로 등급도 그 후보의
  // 신뢰도를 그대로 따릅니다 (M1_M2_팀확정요청.md 참고).
  const [resolvedConflicts, setResolvedConflicts] = useState<ResolvedConflicts>({});

  function handleConflictResolve(fieldName: string, chosenValue: string) {
    setResolvedConflicts((prev) => ({ ...prev, [fieldName]: chosenValue }));
  }

  function handleConflictClear(fieldName: string) {
    // 키를 지워서 원래 충돌 상태(필수 확인)로 되돌립니다. 값을 되돌리는 게
    // 아니라 "아직 안 골랐다"로 되돌리는 것이라 원본 필드가 그대로 살아납니다.
    setResolvedConflicts((prev) => {
      const next = { ...prev };
      delete next[fieldName];
      return next;
    });
  }

  const handleFieldEdit = applyEdit;

  // 값은 안 고치고 "다시 보니 이 값이 맞다"고 확인만 표시한 필드. editedValues와
  // 따로 두는 이유는 위 handleFieldEdit과 같습니다 — "새 값을 쓴 것"과 "원래
  // 값을 확인만 한 것"은 다른 행동입니다.
  // 이 화면을 떠났다 돌아와도 남도록 스토어(선적 id별)에 둡니다.
  const [confirmedFields, confirmField] = useConfirmedFields(id);
  const [confirmError, setConfirmError] = useState<string | null>(null);
  function handleFieldConfirm(fieldName: string) {
    setConfirmError(null);
    confirmField(fieldName).catch(() => setConfirmError('값 확인을 저장하지 못했습니다. 다시 시도해 주세요.'));
  }

  // /normalize/apply·reject 호출이 실패했을 때만 채웁니다 — 성공하면 조용히 넘어갑니다.
  const [suggestionError, setSuggestionError] = useState<string | null>(null);

  // 목데이터로 물러난 상태(normalize.status !== 'ok')에서는 서버에 되돌려 보낼
  // 원본 WireSuggestion이 없습니다 — 그때는 예전처럼 화면 값만 바꿉니다.
  const suggestionsById = normalize.status === 'ok' ? normalize.view.bySuggestionId : {};

  async function handleSuggestionAccept(suggestion: Suggestion, applyToAllInScope: boolean) {
    if (data === null) return;
    const original = suggestionsById[suggestion.suggestion_id];

    if (original === undefined) {
      applyEdit(suggestion.field, suggestion.to_be);
      if (applyToAllInScope) {
        for (const { field } of suggestion.scope) applyEdit(field, suggestion.to_be);
      }
      return;
    }

    try {
      const result = await applySuggestion(data.fields, original, applyToAllInScope);
      if (result.unapplied.some((u) => u.suggestion_id === suggestion.suggestion_id)) {
        setSuggestionError(
          `"${suggestion.field}" 제안을 적용하지 못했습니다 — 그 사이 값이 바뀌었을 수 있습니다.`,
        );
        return;
      }
      // 서버가 실제로 고친 값을 그대로 씁니다 — suggestion.to_be를 바로 쓰지
      // 않는 이유는 서버가 값 전체가 아니라 구간(span) 단위로 치환하기도
      // 해서입니다.
      const patched = result.documents[0]?.fields ?? {};
      setSuggestionError(null);
      applyEdit(suggestion.field, patched[suggestion.field] ?? null);
      if (applyToAllInScope) {
        for (const { field } of suggestion.scope) applyEdit(field, patched[field] ?? null);
      }
    } catch (err) {
      setSuggestionError(err instanceof ApiError ? err.detail : '제안 적용에 실패했습니다.');
    }
  }

  async function handleSuggestionReject(suggestion: Suggestion, reason: string) {
    // 거절은 필드 값을 바꾸지 않습니다 — 사유만 서버에 기록합니다.
    const original = suggestionsById[suggestion.suggestion_id];
    if (original === undefined) return; // 목데이터 폴백 — 기록할 서버가 없습니다

    try {
      await rejectSuggestion(original, reason as RejectReason);
      setSuggestionError(null);
    } catch (err) {
      setSuggestionError(err instanceof ApiError ? err.detail : '거절 기록에 실패했습니다.');
    }
  }

  // ⚠ 이 자리보다 위에서 return하면 안 됩니다. useState·useSearchParams 같은
  // 훅은 화면을 다시 그릴 때마다 "항상 같은 순서로, 같은 개수만큼" 불려야 하는데,
  // 훅 호출 위에서 먼저 빠져나가면 그 규칙이 깨져서 React가 에러를 냅니다.
  // 그래서 훅을 전부 부른 다음에 "선적 없음" 처리를 합니다.
  if (data === null) {
    // 게이트웨이 목록 조회가 아직 안 끝났으면 못 찾은 게 아니라 로딩 중인
    // 것이다 — 구분 안 하면 새로고침·딥링크 직후 잠깐 "찾을 수 없습니다"가
    // 잘못 뜬다.
    if (storeStatus === 'loading') {
      return (
        <PageContainer>
          <EmptyState icon={Loader2} message="선적 정보를 불러오는 중입니다…" spin />
        </PageContainer>
      );
    }
    return (
      <PageContainer>
        <EmptyState icon={FileQuestion} message={`선적 ${id ?? ''}을(를) 찾을 수 없습니다.`} />
      </PageContainer>
    );
  }

  // 충돌이 해소된 필드는 고른 후보의 값·신뢰도로 갈아끼운 뒤 아래로 내려보냅니다.
  // 그래야 등급 계산·필수 확인 건수·검증 게이트가 전부 같은 필드를 보고 움직입니다.
  const fields = resolveConflicts(data.fields, resolvedConflicts);

  // 백엔드가 성공하면 그 제안을, 실패하면 목데이터를 씁니다 — S4와 같은 원칙.
  // 로딩 중(normalize.status === 'loading')에는 둘 다 아닙니다 — 목데이터를
  // 출처 배너 없이 보여주면 아직 서버 응답을 못 받았는데도 실제 제안처럼
  // 보이고, 그 사이 승인을 누르면 서버 호출 없이 목 값이 조용히 반영됩니다.
  // 그래서 로딩 중에는 빈 배열로 둡니다.
  const isNormalizeLive = normalize.status === 'ok';
  const isNormalizeLoading = normalize.status === 'loading';
  const suggestions = isNormalizeLive
    ? normalize.view.suggestions
    : isNormalizeLoading
      ? []
      : data.suggestions;

  return (
    <PageContainer>
      {/* 영향 패널(fixed, 폭 354px + 오른쪽 여백)이 열린 동안엔 .s3-impact-open이 본문 오른쪽을
          비우고 뷰어·필드폼을 세로로 쌓습니다 — 가로로 두면 필드폼이 ~330px로 눌려
          라벨·값·뱃지가 겹칩니다. 규칙은 index.css에 있습니다. */}
      <div className={isImpactOpen ? 's3-impact-open' : undefined}>
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'space-between',
          }}
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4, textAlign: 'left' }}>
            <h1 className="page-title">초안 편집기</h1>
            {/* 어느 선적을 보고 있는지 — 세 화면(S3·S5·S7)이 같은 부품을 씁니다 */}
            <ShipmentHeader shipment={data.shipment} />
          </div>
          <button type="button" className="btn-secondary" onClick={toggleImpactPanel}>
            {isImpactOpen ? '영향 패널 닫기' : '영향 확인'}
          </button>
        </div>

        <div style={{ margin: 'var(--space-2) 0' }}>
          {isNormalizeLive ? (
            <DataSourceNotice source="live" />
          ) : normalize.status === 'error' ? (
            <DataSourceNotice source="mock" reason={normalize.error.message} />
          ) : isNormalizeLoading ? (
            <EmptyState icon={Loader2} message="용어 교정 제안을 불러오는 중입니다…" spin />
          ) : null}
          {(confirmError ?? editError) !== null && (
            <p style={{ color: 'var(--severity-critical)', fontSize: 13, margin: '8px 0 0' }}>
              {confirmError ?? editError}
            </p>
          )}
          {suggestionError !== null && (
            <p style={{ color: 'var(--severity-critical)', fontSize: 13, margin: '8px 0 0' }}>
              {suggestionError}
            </p>
          )}
        </div>

        {/* 가로 배치(뷰어+필드폼)는 index.css의 .s3-content-row가 맡습니다 —
            1024px 이하에서는 미디어쿼리로 세로 쌓기로 바뀝니다. 인라인
            style로는 미디어쿼리를 못 써서 이 div만 className을 씁니다. */}
        <div className="s3-content-row">
          <DocumentViewer
            focusedField={focusedField ?? undefined}
            documents={data.documents}
            shipmentId={id ?? ''}
          />
          <div style={{ flex: 1, minWidth: 0 }}>
            {/* fields는 원본(data.fields)을 넘깁니다 — FieldForm이 그룹 배치를
                원본 등급으로 정해야 후보를 고른 카드가 다른 그룹으로 튀어나가지
                않습니다. 아래 VerifyBar에는 해소된 fields를 넘겨서 "남은 필수
                확인 건수"와 검증 버튼 조건이 즉시 반영되게 합니다. */}
            <FieldForm
              fields={data.fields}
              suggestions={suggestions}
              verdicts={data.verdicts}
              focusedFieldName={focusedField?.field_name ?? null}
              onFieldFocus={setFocusedField}
              editedValues={editedValues}
              onFieldEdit={handleFieldEdit}
              savedFieldName={savedField}
              confirmedFields={confirmedFields}
              onFieldConfirm={handleFieldConfirm}
              onSuggestionAccept={handleSuggestionAccept}
              onSuggestionReject={handleSuggestionReject}
              resolvedConflicts={resolvedConflicts}
              onConflictResolve={handleConflictResolve}
              onConflictClear={handleConflictClear}
            />
          </div>
        </div>

        {/* 이 화면의 핵심 동작이라 스크롤과 무관하게 항상 보이도록 하단에
            고정합니다. sticky는 부모에 overflow가 없어야 동작하므로 여기서만
            감싸고, 겹치는 내용이 비쳐 보이지 않게 배경색을 채웁니다 */}
        <div
          style={{
            position: 'sticky',
            bottom: 0,
            zIndex: 10,
            marginTop: 'var(--space-4)',
            paddingBottom: 'var(--space-3)',
            backgroundColor: 'var(--bg)',
          }}
        >
          <VerifyBar
            shipmentId={id ?? ''}
            fields={fields}
            documents={data.documents}
            verdicts={data.verdicts}
            prediction={data.prediction}
            confirmedFields={confirmedFields}
          />
        </div>
      </div>

      <ImpactPanel
        impact={data.impact}
        shipment={data.shipment}
        editedValues={editedValues}
        resolvedConflicts={resolvedConflicts}
      />
    </PageContainer>
  );
}
