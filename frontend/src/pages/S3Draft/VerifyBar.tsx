import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ChevronDown, ChevronRight } from 'lucide-react';
import { SEVERITY, VERDICT_RESULT_LABEL, canTransitionToVerified } from '../../constants/domain';
import type { DefectPrediction, DocumentMeta, FieldValue, Verdict } from '../../types/domain';
import {
  SEVERITIES_IN_ORDER,
  countRequiredFields,
  isEditedField,
  summarizeVerdicts,
  worstSeverity,
  type ConfirmedFields,
} from '../../shared/shipmentStats';
import { verifyShipment } from '../../api/verify';
import { loadLcParse } from '../../api/lc';
import { saveVerification } from '../../api/shipment';
import { ApiError } from '../../api/client';
import { useRecordVerification, useSaveFields } from '../../shared/shipmentStore';

interface VerifyBarProps {
  /** 이 선적 id — 검증 성공 후 이동할 S4 경로에 씁니다 */
  shipmentId: string;
  /** 이 선적의 필드 — 필수 확인 건수를 셀 대상 */
  fields: FieldValue[];
  /**
   * 이 선적의 서류 — 신용장이 있으면 L/C 조건까지 대조해서 검증합니다.
   * 없으면 서류 내부 정합성만 봅니다(룰 상당수가 평가불가로 빠짐).
   */
  documents: DocumentMeta[];
  /** 이 선적의 판정 — 미해결 Critical 건수를 셀 대상. 검증 전이면 빈 배열 */
  verdicts: Verdict[];
  /** 이 선적의 하자 확률. 아직 검증 전이면 null이라 요약을 못 그립니다 */
  prediction: DefectPrediction | null;
  /** FieldForm·SuggestionCard와 공유하는 "필드별 수정값" */
  editedValues: Record<string, string | null>;
  /** 값은 안 고치고 "확인"만 표시한 필드 — 필수 확인 건수 집계에 씀 */
  confirmedFields: ConfirmedFields;
}

/**
 * S3 초안 편집기 하단의 검증 바 — 리스크 요약 + "검증 실행".
 *
 * 이 화면의 핵심 동작이라 S3Draft가 화면 아래에 sticky로 붙입니다. 그래서
 * 세로로 쌓지 않고 가로 한 줄로 눕혔습니다 — 세로 카드는 본문을 너무 많이
 * 가립니다. 하자 확률 기여 요인은 확률 숫자를 눌러 접었다 펼 수 있습니다 —
 * 78%의 근거라 빼지 않되, 항상 펼쳐두지도 않습니다.
 *
 * M-1 확정(2026-08-19): "검증 실행" 버튼은 canTransitionToVerified 게이트를
 *   그대로 따릅니다. 막혔을 때는 "사유 기록 후 강제 실행"으로 우회할 수
 *   있고, 사유를 기록하는 즉시 검증을 진행합니다 — 사유는 게이트웨이의
 *   shipment_status_history(force_reason)에 저장됩니다 (M1_M2_팀확정요청.md 참고).
 */
export function VerifyBar({
  shipmentId,
  fields,
  documents,
  verdicts,
  prediction,
  editedValues,
  confirmedFields,
}: VerifyBarProps) {
  const navigate = useNavigate();
  const recordVerification = useRecordVerification();
  const saveFields = useSaveFields();
  const [showOverrideForm, setShowOverrideForm] = useState(false);
  const [overrideReason, setOverrideReason] = useState('');
  const [overrideRecorded, setOverrideRecorded] = useState<string | null>(null);
  // 하자 확률 기여 요인은 접어둡니다 — 78%라는 숫자의 근거라 꼭 볼 수 있어야
  // 하지만, 하단 고정 바에 항상 펼쳐두면 본문을 너무 많이 가립니다.
  const [showFactors, setShowFactors] = useState(false);
  // "검증 실행" 클릭 진행 상태 — idle(안 누름) / loading(요청 중) / error(실패)
  const [verifyStatus, setVerifyStatus] = useState<'idle' | 'loading' | 'error'>('idle');
  const [verifyError, setVerifyError] = useState<string | null>(null);

  /** 성공하면 true, 실패하면 false — 강제 실행 흐름이 실패를 구분해 되돌릴 수 있게 알려줍니다 */
  async function handleVerifyClick(overrideReasonToSave: string | null = null): Promise<boolean> {
    setVerifyStatus('loading');
    setVerifyError(null);
    // 화면에 보이는 값(직접 수정·제안 승인 반영)을 그대로 검증에 보냅니다 —
    // 아직 화면에 안 반영된 원본 값을 검증하면 사용자가 방금 고친 값과
    // 다른 결과를 보게 됩니다.
    const effectiveFields = fields.map((field) =>
      isEditedField(field, editedValues)
        ? { ...field, value: editedValues[field.field_name] }
        : field,
    );
    try {
      // F2 교정 승인·직접 수정값은 지금까지 컴포넌트 state(editedValues)에만
      // 있었습니다 — 검증 실행 직전에 게이트웨이로 한 번 저장해서, S4·S7이
      // 다시 읽는 data.fields에도 이 값이 반영되게 합니다. B/L 서류를 못
      // 찾으면(업로드 전 등) 근거 문서 없이 저장할 수 없어 건너뜁니다.
      // ponytail: 승인 후 검증 없이 다른 화면으로 갔다 오면 편집값이 소실됩니다
      // — 입력마다 디바운스 자동저장을 붙이면 해결되지만 지금은 범위 밖입니다.
      const blDocument = documents.find((doc) => doc.kind === 'BL');
      if (blDocument) {
        const page = effectiveFields.find((f) => f.page !== null)?.page ?? 1;
        // 원본 fields(값 병합 전)로 판정해야 isEditedField가 맞게 동작합니다 —
        // effectiveFields는 이미 값이 병합돼 있어 "달라졌는지"를 못 봅니다.
        const editedFieldNames = new Set(
          fields.filter((field) => isEditedField(field, editedValues)).map((field) => field.field_name),
        );
        await saveFields(shipmentId, blDocument.document_id, page, effectiveFields, editedFieldNames);
      }
      // L/C 를 못 읽어도 검증은 진행합니다 — 여기서 멈추면 신용장 파싱
      // 실패 하나로 검증 자체를 못 하게 됩니다.
      const parsed = await loadLcParse(shipmentId, documents).catch(() => null);
      const result = await verifyShipment(effectiveFields, { lc: parsed?.lc });
      // aiService가 방금 계산한 결과를 게이트웨이에 저장 — 이게 없으면
      // 새로고침했을 때 판정이 사라지고 선적 상태도 계속 DRAFT로 남습니다.
      const status = await saveVerification(
        shipmentId,
        result.verdicts,
        result.prediction,
        overrideReasonToSave,
      );
      recordVerification(shipmentId, status, result.verdicts, result.prediction);
      navigate(`/shipments/${shipmentId}/verdicts`);
      return true;
    } catch (err) {
      setVerifyStatus('error');
      setVerifyError(err instanceof ApiError ? err.detail : '검증 요청에 실패했습니다.');
      return false;
    }
  }

  const requiredCount = countRequiredFields(fields, editedValues, confirmedFields);
  const verdictCounts = summarizeVerdicts(verdicts);

  // 미해결 Critical만 셉니다. 판정 보류는 필수 확인 필드 쪽에서 이미 세고 있는
  // 문제라 여기서 또 세면 같은 문제를 두 번 반영하게 됩니다.
  const unresolvedCriticalCount = verdicts.filter(
    (verdict) => verdict.severity === 'Critical' && verdict.result === 'VIOLATION',
  ).length;

  const gate = canTransitionToVerified({
    requiredFieldCount: requiredCount,
    unresolvedCriticalCount,
  });

  async function handleOverrideSubmit() {
    const trimmed = overrideReason.trim();
    if (trimmed === '') return;
    setOverrideRecorded(trimmed);
    setShowOverrideForm(false);
    // 실패하면(네트워크 오류 등) 사유 기록을 되돌립니다 — 안 그러면 "사유 기록 후
    // 강제 실행" 버튼이 다시 안 보여서 새로고침 전까지 재시도할 방법이 없습니다.
    const ok = await handleVerifyClick(trimmed);
    if (!ok) setOverrideRecorded(null);
  }

  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        gap: 'var(--space-4)',
        flexWrap: 'wrap',
        padding: 'var(--space-3)',
        border: '1px solid var(--border-default)',
        borderRadius: 'var(--radius-card)',
        boxShadow: 'var(--shadow-card)',
        backgroundColor: 'var(--bg-card)',
        textAlign: 'left',
      }}
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, minWidth: 0 }}>
        {prediction === null ? (
          // 검증 전에는 0%로 채우지 않습니다 — 0%는 "안전하다"는 근거 없는 주장 (§2.4)
          <span style={{ fontSize: 13, color: 'var(--text-muted)' }}>
            아직 검증을 실행하지 않아 하자 확률이 없습니다.
          </span>
        ) : (
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-3)',
              flexWrap: 'wrap',
            }}
          >
            <span style={{ display: 'inline-flex', alignItems: 'baseline', gap: 7 }}>
              <span style={{ fontSize: 12, fontWeight: 600, color: 'var(--text-secondary)' }}>
                하자 확률
              </span>
              <button
                type="button"
                onClick={() => setShowFactors((open) => !open)}
                title="이 확률이 어떻게 나왔는지 보기"
                style={{
                  display: 'inline-flex',
                  alignItems: 'center',
                  gap: 4,
                  padding: 0,
                  border: 'none',
                  background: 'none',
                  fontSize: 26,
                  fontWeight: 700,
                  lineHeight: 1,
                  color: `var(${SEVERITY[worstSeverity(verdicts) ?? 'Info'].colorVar})`,
                }}
              >
                {Math.round(prediction.probability * 100)}%
                {showFactors ? (
                  <ChevronDown size={16} aria-hidden="true" />
                ) : (
                  <ChevronRight size={16} aria-hidden="true" />
                )}
              </button>
              {prediction.deferred_count > 0 && (
                <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                  판정 보류 {prediction.deferred_count}건 제외
                </span>
              )}
            </span>

            {/* 판정 건수 — 집계는 shared/shipmentStats가 맡아 S1·S4와 항상 같습니다 */}
            <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
              {SEVERITIES_IN_ORDER.map((severity) => (
                <Pill
                  key={severity}
                  label={`${SEVERITY[severity].label} ${verdictCounts.bySeverity[severity]}`}
                  colorVar={SEVERITY[severity].colorVar}
                  bgVar={SEVERITY[severity].bgVar}
                />
              ))}
              {verdictCounts.deferred > 0 && (
                <Pill
                  label={`${VERDICT_RESULT_LABEL.DEFERRED} ${verdictCounts.deferred}`}
                  colorVar="--text-secondary"
                  bgVar={null}
                />
              )}
            </span>
          </div>
        )}

        {/* 하자 확률의 근거 — SHAP 기여도 상위 요인. AI 판정을 설명하는
            자리라 빼지 않고, 접었다 펼 수 있게 뒀습니다 (§5.3 계층 B) */}
        {showFactors && prediction !== null && (
          <ul
            style={{
              margin: '4px 0 0',
              paddingLeft: 18,
              fontSize: 12.5,
              lineHeight: 1.6,
              color: 'var(--text-secondary)',
            }}
          >
            {prediction.top_factors.map((factor) => (
              <li key={factor.factor}>
                {factor.factor}{' '}
                <strong style={{ color: 'var(--text-primary)' }}>
                  {Math.round(factor.contribution * 100)}%
                </strong>
              </li>
            ))}
          </ul>
        )}
      </div>

      <div style={{ flex: 1, minWidth: 'var(--space-2)' }} />

      <div style={{ display: 'flex', flexDirection: 'column', gap: 6, alignItems: 'flex-end' }}>
        {/* 차단 사유를 한 줄로 잇습니다 — 세로로 쌓으면 하단 고정 바가
            그만큼 두꺼워져서 본문을 더 가립니다 */}
        {!gate.allowed && (
          <span style={{ fontSize: 12.5, color: 'var(--severity-critical)', textAlign: 'right' }}>
            {gate.blockers.join(' · ')}
          </span>
        )}

        {overrideRecorded !== null && (
          <span style={{ fontSize: 12.5, color: 'var(--brand-primary)' }}>
            사유 기록됨: {overrideRecorded}
          </span>
        )}

        {verifyStatus === 'error' && (
          <span style={{ fontSize: 12.5, color: 'var(--severity-critical)', textAlign: 'right' }}>
            검증 실패: {verifyError}
          </span>
        )}

        {showOverrideForm ? (
          <div style={{ display: 'flex', alignItems: 'center', gap: 6, flexWrap: 'wrap' }}>
            <input
              type="text"
              value={overrideReason}
              onChange={(event) => setOverrideReason(event.target.value)}
              placeholder="강제 실행 사유"
              autoFocus
              style={{
                font: 'inherit',
                fontSize: 13,
                color: 'inherit',
                border: '1px solid var(--border-default)',
                borderRadius: 4,
                padding: '6px 8px',
              }}
            />
            <button
              type="button"
              className="btn-primary"
              // "검증 실행" 버튼과 같은 이유로 진행 중이면 막는다 — 응답이
              // 늦게 오면 그 사이에 다시 눌러 강제 실행이 두 번 나갈 수
              // 있다(P2-15).
              disabled={verifyStatus === 'loading'}
              onClick={handleOverrideSubmit}
            >
              확인
            </button>
            <button
              type="button"
              className="btn-secondary"
              onClick={() => setShowOverrideForm(false)}
            >
              취소
            </button>
          </div>
        ) : (
          <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
            {!gate.allowed && gate.overridable && overrideRecorded === null && (
              <button
                type="button"
                className="btn-secondary"
                onClick={() => setShowOverrideForm(true)}
              >
                사유 기록 후 강제 실행
              </button>
            )}
            <button
              type="button"
              className="btn-primary"
              disabled={!gate.allowed || verifyStatus === 'loading'}
              onClick={() => handleVerifyClick()}
              style={{ padding: '10px 22px', fontSize: 14, fontWeight: 700 }}
            >
              {verifyStatus === 'loading' ? '검증 중…' : '검증 실행'}
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

/** 건수 알약 — 색·글자를 함께 씁니다 (규약 §6.2) */
function Pill({
  label,
  colorVar,
  bgVar,
}: {
  label: string;
  colorVar: string;
  bgVar: string | null;
}) {
  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        padding: '3px 10px',
        borderRadius: 999,
        fontSize: 12.5,
        fontWeight: 700,
        color: `var(${colorVar})`,
        backgroundColor: bgVar !== null ? `var(${bgVar})` : 'transparent',
        border: `1px solid var(${bgVar !== null ? colorVar : '--border-default'})`,
      }}
    >
      {label}
    </span>
  );
}
