import { ArrowRight, ChevronRight, Clock, Trash2 } from 'lucide-react';
import { useState } from 'react';
import { Link } from 'react-router-dom';
import { StatusBadge } from '../../components/StatusBadge';
import { SHIPMENT_STATUS } from '../../constants/domain';
import type { Verdict } from '../../types/domain';
import type { ShipmentMockData } from '../../mocks/shipmentData';
import { useConfirmedFields, useDeleteShipment } from '../../shared/shipmentStore';
import { CardFieldGrid } from './CardFieldGrid';
import { CardRouteBand } from './CardRouteBand';
import { CardVerdictBand } from './CardVerdictBand';
import { NO_SOURCE_LABEL, formatShortDate, formatShortDateTime, valueOf } from './cardFields';
import { countRequiredFields } from '../../shared/shipmentStats';

interface ShipmentCardProps {
  /** 선적 1건의 목데이터 묶음 — Shipment만으로는 판정·필드를 그릴 수 없어서 통째로 받습니다 */
  data: ShipmentMockData;
  /** L/C 유효기일 D-day 계산 기준 시각. 목록이 카드마다 다른 "지금"을 쓰지 않도록 위에서 내려줍니다 */
  now: Date;
}

/**
 * S1 대시보드의 선적 카드 — 카드 하나로 그 선적의 상태를 다 읽을 수 있게
 * 가로 띠를 쌓은 구조입니다 (디자인 시안 4a "카드 하나로 완결되는 목록").
 *
 *   머리(식별)  → 당사자 → 항로 → 필드 격자 → 판정 요약 → 바닥(이동 버튼)
 *
 * 띠마다 파일을 나눈 이유: 한 파일에 다 넣으면 300줄이 넘어가고, 항로·격자·
 * 판정은 각각 따로 손볼 일이 많아서입니다.
 *
 * 값은 전부 기존 타입/상수에서 옵니다 — 색은 SHIPMENT_STATUS·SEVERITY의
 * colorVar를, 없는 값은 CONFIDENCE.NOT_FOUND의 문구를 씁니다. 카드가 자기만의
 * 색이나 문구를 새로 정하지 않습니다 (CLAUDE.md 1·2번).
 */
export function ShipmentCard({ data, now }: ShipmentCardProps) {
  const { shipment, fields, documents } = data;
  const statusMeta = SHIPMENT_STATUS[shipment.status];

  // 대시보드는 AI를 부르지 않습니다 — 카드를 열 때마다 /verify 가 돌면 감사 로그가
  // 선적 수만큼 쌓입니다. 게이트웨이가 저장해 둔 마지막 검증 스냅샷(스토어)만 보여주고,
  // 없으면 "검증 전"으로 둡니다. 검증은 S3·S4의 명시적 동작으로만 실행됩니다.
  const { verdicts, prediction } = data;

  // 아직 안 풀린 필수 확인 건수 — 편집값은 S3 안에만 있으므로 비워 두고, S3에서
  // "값 확인함"으로 확인한 필드는 스토어에서 받아 같은 계산식에 넣습니다.
  const [confirmedFields] = useConfirmedFields(shipment.shipment_id);
  const requiredFieldCount = countRequiredFields(fields, {}, confirmedFields);

  // 판정 띠가 "위반 0건"과 "아직 안 돌렸다"를 구분하는 데 쓰는 값입니다.
  // 저장된 스냅샷(하자 확률)이 있어야 검증을 거친 것입니다.
  const isVerified = prediction !== null;

  // P2-16: 시연 리허설 중 쌓인 테스트 선적을 지울 방법이 UI에 없었다.
  // 삭제는 되돌릴 수 없어서 window.confirm으로 한 번 더 확인한다.
  const deleteShipment = useDeleteShipment();
  const [isDeleting, setIsDeleting] = useState(false);

  async function handleDelete() {
    const label = shipment.bl_no ?? shipment.shipment_id;
    if (!window.confirm(`선적 "${label}"을(를) 삭제할까요? 되돌릴 수 없습니다.`)) return;
    setIsDeleting(true);
    try {
      await deleteShipment(shipment.shipment_id);
    } catch (err) {
      console.error('선적 삭제에 실패했습니다', err);
      window.alert('선적 삭제에 실패했습니다. 다시 시도해주세요.');
      setIsDeleting(false);
    }
  }

  return (
    <div
      style={{
        border: '1px solid var(--border-default)',
        // 왼쪽에 상태색 띠를 둡니다 — 목록을 훑을 때 상태 뱃지를 읽기 전에
        // 색만으로 구분이 되고, 뱃지 글자가 함께 있으니 색만으로 뜻을
        // 전달하는 것도 아닙니다 (규약 §6.2)
        borderLeft: `4px solid var(${statusMeta.colorVar})`,
        borderRadius: 'var(--radius-card)',
        boxShadow: 'var(--shadow-card)',
        backgroundColor: 'var(--bg)',
        overflow: 'hidden',
        textAlign: 'left',
      }}
    >
      {/* ── 머리: 무엇인지 식별 ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: '14px 18px 12px',
          flexWrap: 'wrap',
        }}
      >
        {shipment.bl_no !== null ? (
          <strong style={{ fontSize: 17, letterSpacing: '-0.2px', color: 'var(--text-primary)' }}>
            {shipment.bl_no}
          </strong>
        ) : (
          // B/L 번호는 발행 후에 생기는 값이라 초안 단계엔 없는 게 정상입니다.
          // "-"로 두면 오류처럼 보여서 이유를 문구로 밝힙니다.
          <span style={{ fontSize: 16, color: 'var(--text-muted)', fontStyle: 'italic' }}>
            B/L 번호 미발급
          </span>
        )}

        <StatusBadge status={shipment.status} />

        <div style={{ flex: 1, minWidth: 'var(--space-2)' }} />

        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>{shipment.shipment_id}</span>
        <span
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            gap: 4,
            fontSize: 12,
            color: 'var(--text-muted)',
          }}
        >
          <Clock size={12} aria-hidden="true" />
          {formatShortDateTime(shipment.updated_at)}
        </span>

        <button
          type="button"
          onClick={handleDelete}
          disabled={isDeleting}
          title="선적 삭제"
          aria-label="선적 삭제"
          style={{
            display: 'inline-flex',
            alignItems: 'center',
            padding: 4,
            border: 'none',
            background: 'none',
            cursor: isDeleting ? 'default' : 'pointer',
            color: 'var(--text-muted)',
            opacity: isDeleting ? 0.5 : 1,
          }}
        >
          <Trash2 size={14} aria-hidden="true" />
        </button>
      </div>

      {/* ── 당사자·화물 ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-3)',
          padding: '0 18px 14px',
          flexWrap: 'wrap',
        }}
      >
        <Party name={valueOf(fields, 'shipper')} />
        <ArrowRight size={13} color="var(--text-muted)" aria-hidden="true" />
        <Party name={valueOf(fields, 'consignee')} />

        <span
          style={{ width: 1, height: 14, backgroundColor: 'var(--border-default)' }}
          aria-hidden="true"
        />

        <span style={{ fontSize: 12, color: 'var(--text-secondary)' }}>
          {goodsSummary(fields)}
        </span>
      </div>

      <CardRouteBand
        fields={fields}
        loadedOnBoard={loadedOnBoardLabel(fields)}
        prediction={prediction}
        verdicts={verdicts}
      />

      <CardFieldGrid shipment={shipment} fields={fields} documentCount={documents.length} now={now} />

      <CardVerdictBand
        verdicts={verdicts}
        isVerified={isVerified}
        requiredFieldCount={requiredFieldCount}
        shipmentId={shipment.shipment_id}
      />

      {/* ── 바닥: 판정 기준 + 이동 ── */}
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          gap: 'var(--space-2)',
          padding: '11px 18px',
          borderTop: '1px solid var(--border-default)',
          flexWrap: 'wrap',
        }}
      >
        <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
          {ruleBasisLabel(shipment, verdicts)}
        </span>

        <div style={{ flex: 1, minWidth: 'var(--space-2)' }} />

        {/* 제출 이후 상태는 초안을 고칠 수 없습니다 — SHIPMENT_STATUS.editable을
            그대로 따르므로, 상태가 늘어나도 이 카드를 다시 손볼 필요가 없습니다 */}
        {statusMeta.editable && (
          <Link
            to={`/shipments/${shipment.shipment_id}/draft`}
            className="btn btn-secondary"
            style={{ padding: '5px 13px', fontSize: 13 }}
          >
            초안 편집
          </Link>
        )}
        <Link
          to={`/shipments/${shipment.shipment_id}`}
          className="btn btn-secondary"
          style={{ padding: '5px 13px', fontSize: 13 }}
        >
          운항 타임라인
        </Link>
        <Link
          to={`/shipments/${shipment.shipment_id}/verdicts`}
          className="btn btn-primary"
          style={{ gap: 5, padding: '5px 13px', fontSize: 13, fontWeight: 600 }}
        >
          검증 결과 보기
          <ChevronRight size={13} aria-hidden="true" />
        </Link>
      </div>
    </div>
  );
}

function Party({ name }: { name: string | null }) {
  return (
    <span
      style={{
        fontSize: 13,
        lineHeight: 1.4,
        color: name !== null ? 'var(--text-primary)' : 'var(--text-muted)',
      }}
    >
      {name ?? NO_SOURCE_LABEL}
    </span>
  );
}

/** "PRECISION MACHINE PARTS · HS 8471.30" — 둘 다 없으면 출처 없음 */
function goodsSummary(fields: Parameters<typeof valueOf>[0]): string {
  const goods = valueOf(fields, 'description_of_goods');
  const hsCode = valueOf(fields, 'hs_code');
  const parts = [goods, hsCode !== null ? `HS ${hsCode}` : null].filter(
    (part): part is string => part !== null,
  );
  return parts.length === 0 ? NO_SOURCE_LABEL : parts.join(' · ');
}

/** 본선적재일을 "07-14" 형태로. 아직 적재 전이면 null */
function loadedOnBoardLabel(fields: Parameters<typeof valueOf>[0]): string | null {
  const loaded = valueOf(fields, 'shipped_on_board_date');
  if (loaded === null) return null;
  return formatShortDate(loaded);
}

/**
 * "판정 기준 RC-2026.08.1 · 08-12 10:30".
 *
 * 판정이 없으면 기준 버전도 없습니다 — 아직 어떤 룰로도 판정하지 않았으니
 * 버전을 적으면 거짓이 됩니다. 그때는 마지막 수정 시각만 보여줍니다.
 */
function ruleBasisLabel(shipment: ShipmentMockData['shipment'], verdicts: Verdict[]): string {
  const updated = formatShortDateTime(shipment.updated_at);
  const firstVerdict = verdicts[0];
  if (firstVerdict === undefined) return `마지막 수정 ${updated}`;
  return `판정 기준 ${firstVerdict.rule_version} · ${updated}`;
}
