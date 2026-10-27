import { ArrowRight } from 'lucide-react';
import { Link } from 'react-router-dom';
import type { Alert, Explanation, FieldValue, RealityEvent, Suggestion } from '../../types/domain';
import { SeverityBadge } from '../../components/SeverityBadge';
import { EVENT_SOURCE_SHORT, REALITY_EVENT_LABEL, SEVERITY, labelOfField } from '../../constants/domain';
import { ExplanationBlock } from '../../components/ExplanationBlock';
import { evidenceEventsOf } from '../../shared/realityView';
import { AlertActions } from './AlertActions';
import { AckBadge, CauseField, EvidenceColumns, EvidencePanel, formatEventTime } from './AlertParts';

interface AlertCardProps {
  alert: Alert;
  /** 이 선적의 필드 — 서류측 근거(원인 필드)의 현재 상태를 읽습니다 */
  fields: FieldValue[];
  /** 이 선적의 현실 대조 이벤트 — 현실측 근거를 찾습니다 */
  realityEvents: RealityEvent[];
  /** 이 선적의 교정 제안 — 원인 필드에 대기 중인 제안이 있는지 표시 */
  suggestions: Suggestion[];
  /**
   * F7 판정 설명 — 이 경보가 왜 떴는지. 설명이 없는 경보도 있어서 null을 받습니다
   * (ExplanationBlock이 null이면 아무것도 그리지 않습니다).
   */
  explanation?: Explanation | null;
  /** 둘 다 주어졌을 때만(=실제 선적) 처리 버튼이 나옵니다. 데모 픽스처는 안 넘김 */
  onAcknowledge?: () => Promise<void>;
  onWhitelist?: (reason: string) => Promise<void>;
  /** 이 선적의 콜사인 — 화이트리스트 적용 범위 안내에 씁니다 (없으면 테넌트 전체) */
  callSign?: string | null;
}

/**
 * 경보 카드 하나 — 서류와 실제 운송 기록이 어긋난 건.
 *
 * 근거를 서류측·현실측 두 칸으로 나눠 보여줍니다. 어긋남을 판단하려면 양쪽을
 * 나란히 봐야 하는데, 한 줄로 이어 쓰면 무엇과 무엇이 다른지 읽어내기 어렵습니다.
 *
 * ⚠ "확인 처리" 버튼은 넣지 않았습니다. acknowledged를 바꿀 수단이 없어서
 *   눌러도 새로고침하면 원복됩니다. 상태는 확인됨/미확인 표시로만 둡니다.
 *
 * 카드 전체를 링크로 감싸지 않습니다 — 이동 경로가 둘(원인 필드 고치기 /
 * 타임라인 근거 보기)이라 카드를 누르면 어디로 갈지 알 수 없습니다.
 */
export function AlertCard({
  alert,
  fields,
  realityEvents,
  suggestions,
  explanation = null,
  onAcknowledge,
  callSign,
  onWhitelist,
}: AlertCardProps) {
  const meta = SEVERITY[alert.severity];
  // 서류측 근거는 FieldValue.field_name을 가리킵니다 (types/domain.ts §F6)
  const causeFieldName: string | undefined = alert.document_event_ids[0];
  const causeField =
    causeFieldName === undefined
      ? undefined
      : fields.find((field) => field.field_name === causeFieldName);
  // C-ROUTE-01 은 reality_event_ids 가 [] — 이벤트가 아니라 "기록 부재"가 근거입니다
  const events = evidenceEventsOf(alert, realityEvents);
  const firstEventId: string | undefined = alert.reality_event_ids[0];

  return (
    <article
      style={{
        display: 'flex',
        border: '1px solid var(--border-default)',
        borderLeft: `5px solid var(${meta.colorVar})`,
        // 모서리는 .alert-group이 정합니다 (그룹 안에서만 쓰이는 카드입니다)
        boxShadow: 'var(--shadow-card)',
        backgroundColor: 'var(--bg)',
        overflow: 'hidden',
        textAlign: 'left',
      }}
    >
      <div style={{ flex: '1 1 auto', minWidth: 0, display: 'flex', flexDirection: 'column' }}>
        <div style={{ display: 'flex', flexDirection: 'column', gap: 10, padding: '18px 20px' }}>
          <div style={{ display: 'flex', alignItems: 'center', gap: 'var(--space-2)', flexWrap: 'wrap' }}>
            <SeverityBadge severity={alert.severity} />
            <AckBadge acknowledged={alert.acknowledged} status={alert.status} />
            <div style={{ flex: 1, minWidth: 'var(--space-2)' }} />
            <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
              {new Date(alert.created_at).toLocaleString('ko-KR')} 발생
            </span>
          </div>

          <p
            style={{
              margin: 0,
              fontSize: 15,
              fontWeight: 600,
              lineHeight: 1.55,
              color: 'var(--text-primary)',
              wordBreak: 'keep-all',
            }}
          >
            {alert.message}
          </p>
        </div>

        <EvidenceColumns>
          <EvidencePanel title="서류측 근거">
            {causeField === undefined ? (
              <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
                {causeFieldName === undefined
                  ? '연결된 서류 필드가 없습니다'
                  : `이 선적에서 ${causeFieldName} 필드를 찾지 못했습니다`}
              </span>
            ) : (
              <CauseField field={causeField} suggestions={suggestions} />
            )}
          </EvidencePanel>

          <EvidencePanel
            title={`현실측 근거 ${events.length}건`}
            tip={events
              .map(
                (event) =>
                  `${event.event_id} (${EVENT_SOURCE_SHORT[event.source]} · ${event.source_event_code})`,
              )
              .join(' · ')}
          >
            <div style={{ display: 'flex', flexDirection: 'column', gap: 5 }}>
              {events.length === 0 && (
                <span style={{ fontSize: 12.5, color: 'var(--text-muted)' }}>
                  울산항 VTS 관제 기록에 해당 선박의 기록이 없습니다 — 기록이 없다는 사실이 근거입니다
                </span>
              )}
              {events.map((event) => (
                <div
                  key={event.event_id}
                  style={{ display: 'flex', alignItems: 'baseline', gap: 8, flexWrap: 'wrap' }}
                >
                  {/* 세관 표기가 아니라 울산항 관제 기록임이 드러나야 합니다 —
                      영문 코드를 그대로 뿌리지 않고 REALITY_EVENT_LABEL로 한글화합니다 */}
                  <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-primary)' }}>
                    {REALITY_EVENT_LABEL[event.event_type]}
                  </span>
                  <span style={{ fontSize: 11.5, color: 'var(--text-muted)' }}>
                    {formatEventTime(event)}
                    {event.quantity !== null && ` · ${event.quantity}대`}
                    {event.location !== null && ` · ${event.location}`}
                  </span>
                </div>
              ))}
            </div>
          </EvidencePanel>
        </EvidenceColumns>

        {/* F7 — 근거를 두 칸으로 보여준 다음, 그 둘이 왜 모순인지를 설명합니다.
            근거 위에 두면 설명을 먼저 읽고 근거를 나중에 보게 되어 순서가 뒤집힙니다. */}
        <div style={{ padding: '0 20px' }}>
          <ExplanationBlock explanation={explanation} realityEvents={realityEvents} />
        </div>

        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 'var(--space-2)',
            flexWrap: 'wrap',
            padding: '13px 20px',
            borderTop: '1px solid var(--border-default)',
          }}
        >
          {/* 화면전이_정의.md §6의 ?focus= 규칙 — S3 진입 시 이 필드를 포커스합니다 */}
          {causeField !== undefined && (
            <Link
              to={`/shipments/${alert.shipment_id}/draft?focus=${causeField.field_name}`}
              className="btn btn-primary"
              style={{ gap: 5, padding: '8px 16px', fontSize: 13, fontWeight: 600 }}
            >
              {labelOfField(causeField.field_name)} 고치러 가기
              <ArrowRight size={13} aria-hidden="true" />
            </Link>
          )}
          <Link
            to={`/shipments/${alert.shipment_id}${firstEventId === undefined ? '' : `?event=${firstEventId}`}`}
            className="btn btn-secondary"
            style={{ padding: '8px 14px', fontSize: 13 }}
          >
            {firstEventId === undefined ? '타임라인 보기' : '타임라인 근거 보기'}
          </Link>
        </div>

        {onAcknowledge !== undefined && onWhitelist !== undefined && (
          <AlertActions
            status={alert.status ?? (alert.acknowledged ? 'ACKNOWLEDGED' : 'OPEN')}
            callSign={callSign}
            onAcknowledge={onAcknowledge}
            onWhitelist={onWhitelist}
          />
        )}
      </div>
    </article>
  );
}

// CauseField·AckBadge는 AlertParts.tsx로 옮겼습니다 — 파일 200줄 제한 때문이며,
// DeferredCard도 CauseField와 거의 같은 모양(등급 뱃지+현재값)을 그릴 일이
// 있어 공용 조각 파일에 두는 편이 자연스럽습니다.

