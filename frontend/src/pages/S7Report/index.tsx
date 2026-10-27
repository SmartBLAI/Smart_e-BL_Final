import { useState } from 'react';
import { ClipboardCheck, FileQuestion, Loader2, PauseCircle } from 'lucide-react';
import { useParams } from 'react-router-dom';
import { DataSourceNotice } from '../../components/DataSourceNotice';
import { EmptyState } from '../../components/EmptyState';
import { PageContainer } from '../../components/PageContainer';
import { ShipmentHeader } from '../../components/ShipmentHeader';
import { SkippedList } from '../../components/SkippedList';
import { VerdictCard } from '../S4Verdicts/VerdictCard';
import { useShipmentData, useShipmentStoreStatus } from '../../shared/shipmentStore';
import { bySeverity } from '../../constants/domain';
import { summarizeVerdicts } from '../../shared/shipmentStats';
import { useReport } from '../../api/useReport';
import { downloadReportPdf } from '../../api/report';
import { ApiError } from '../../api/client';
import { OutcomeForm } from './OutcomeForm';

/**
 * S7 선제 대응 리포트 — 축소 구현 (화면전이_정의.md §1 "이번 기간: 축소").
 *
 * 원래 리포트는 [리포트 생성] 시점의 "스냅샷 불변"이라, 이후 서류가 바뀌면
 * 열람 시 "이후 N건 변경됨" 배너를 보여줘야 합니다 (§S4→S7). 이번 기간은
 * 그 불변 스냅샷·변경 감지 로직 없이, `/report`를 매번 새로 불러 그대로
 * 렌더링만 합니다. 백엔드가 안 뜨면 mock 데이터로 물러납니다(DataSourceNotice가
 * 항상 어느 쪽인지 밝힙니다).
 *
 * `/report`가 주는 체크리스트·수정권고·예상 심사결과·제시기한(risks 외 4개
 * 구성)는 이번 증분에서는 화면에 옮기지 않았습니다 — S4와 같은 판정
 * 카드(VerdictCard)·검사못한목록(SkippedList) 재사용만으로 최소 동작을
 * 만들고, 나머지는 다음 증분에서 필요해지면 추가합니다.
 *
 * 공유 버튼은 만들지 않습니다 (규약 §10.1 — 이번 기간 제외).
 */
export function S7Report() {
  // S4와 마찬가지로 URL의 :id로 선적을 찾습니다 (/shipments/:id/report)
  const { id } = useParams();
  const data = useShipmentData(id);
  const storeStatus = useShipmentStoreStatus();

  // 백엔드 aiService 의 /report 를 부릅니다. data가 없어도(선적 못 찾음)
  // 훅은 항상 불러야 하므로(early return보다 먼저), fields 대신 null을 넘겨
  // "요청하지 말라"고 알려줍니다 — useVerify와 같은 규칙입니다.
  const report = useReport(data?.fields ?? null, {
    shipmentId: id,
    documents: data?.documents,
  });

  // "PDF로 내보내기" 버튼의 진행 상태만 로컬로 둡니다.
  const [pdfStatus, setPdfStatus] = useState<'idle' | 'pending' | 'error'>('idle');
  const [pdfError, setPdfError] = useState<string | null>(null);

  if (data === null) {
    if (storeStatus === 'loading') {
      return (
        <PageContainer narrow>
          <EmptyState icon={Loader2} message="선적 정보를 불러오는 중입니다…" spin />
        </PageContainer>
      );
    }
    return (
      <PageContainer narrow>
        <EmptyState icon={FileQuestion} message={`선적 ${id ?? ''}을(를) 찾을 수 없습니다.`} />
      </PageContainer>
    );
  }

  if (report.status === 'loading') {
    return (
      <PageContainer narrow>
        <EmptyState icon={ClipboardCheck} message="리포트를 생성하는 중입니다…" />
      </PageContainer>
    );
  }

  // handleExportPdf(아래) 는 중첩 함수라 TS가 data의 null 체크를 넘겨받지
  // 못합니다. fields로 미리 꺼내 그 문제를 피합니다.
  const { shipment, fields } = data;
  const isLive = report.status === 'ok';
  const verdicts = isLive ? report.view.verdicts : data.verdicts;
  const prediction = isLive ? report.view.prediction : data.prediction;
  const unchecked = isLive ? report.view.unchecked : [];

  const notice = isLive ? (
    <DataSourceNotice source="live" predictionModel={report.view.predictionModel} />
  ) : (
    <DataSourceNotice source="mock" reason={report.error.message} />
  );

  // 백엔드가 안 떠서 mock으로 물러났고, mock에도 검증 전이라 담을 판정이
  // 없으면 빈 리포트를 껍데기만 그리는 대신 안내로 대체합니다. 백엔드가
  // 응답했다면(isLive) /report 자체가 검증을 새로 실행하므로 이 안내는
  // 필요 없습니다 — 위반 0건도 "검증했는데 문제 없음"이라는 유효한 결과입니다.
  if (!isLive && (verdicts.length === 0 || prediction === null)) {
    return (
      <PageContainer narrow>
        {notice}
        <EmptyState
          icon={ClipboardCheck}
          message="검증을 실행한 뒤에 리포트를 만들 수 있습니다."
        />
      </PageContainer>
    );
  }

  // isLive일 때 /report는 항상 하자 확률을 주므로 실제로는 오지 않는
  // 분기입니다. prediction의 타입(mock 쪽 null 가능성)만 좁히기 위해 둡니다.
  if (prediction === null) {
    return (
      <PageContainer narrow>
        {notice}
        <EmptyState
          icon={ClipboardCheck}
          message="검증을 실행한 뒤에 리포트를 만들 수 있습니다."
        />
      </PageContainer>
    );
  }

  async function handleExportPdf() {
    setPdfStatus('pending');
    setPdfError(null);
    try {
      // 화면에 보이는 리포트와 같은 L/C 조건으로 PDF를 만듭니다 — 검증 때
      // 이미 받아둔 값(report.lc)을 재사용하고, 다시 파싱하지 않습니다.
      await downloadReportPdf(fields, isLive ? report.lc?.lc : undefined, undefined, shipment.shipment_id);
      setPdfStatus('idle');
    } catch (err) {
      setPdfStatus('error');
      setPdfError(err instanceof ApiError ? err.detail : 'PDF 생성에 실패했습니다.');
    }
  }

  const sortedVerdicts = [...verdicts].sort(bySeverity);
  // 보류 건수는 shared/shipmentStats가 셉니다 — S1·S4·S6과 같은 규칙을 타야
  // 화면마다 숫자가 어긋나지 않습니다. (라이브 risks는 DEFERRED가 없어 0건입니다 —
  // 검사 못한 항목은 위 prediction.deferred_count·아래 SkippedList가 대신 밝힙니다)
  const { deferred: deferredCount } = summarizeVerdicts(verdicts);

  return (
    <PageContainer narrow>
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 16,
        }}
      >
        <h1 className="page-title">선제 대응 리포트</h1>
        <button type="button" className="btn-secondary" onClick={handleExportPdf} disabled={pdfStatus === 'pending'}>
          {pdfStatus === 'pending' ? 'PDF 생성 중…' : 'PDF로 내보내기'}
        </button>
      </div>

      {pdfStatus === 'error' && pdfError !== null && (
        <p style={{ margin: '-8px 0 16px', fontSize: 13, color: 'var(--severity-critical)' }}>
          {pdfError}
        </p>
      )}

      <div style={{ marginBottom: 16 }}>{notice}</div>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        {/* 선적 기본 정보 — 식별 줄은 S3·S5와 같은 부품 */}
        <ShipmentHeader shipment={shipment} boxed>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
            화물관리번호 {shipment.cargo_control_no ?? '-'}
          </span>
          <span style={{ fontSize: 12, color: 'var(--text-muted)' }}>
            조회 시각: {new Date().toLocaleString('ko-KR')} — 스냅샷이 아닌 현재 데이터 기준입니다
          </span>
        </ShipmentHeader>

        {/* 하자 확률 요약 */}
        <section
          style={{
            display: 'flex',
            flexDirection: 'column',
            gap: 6,
            padding: 'var(--space-3)',
            border: '1px solid var(--border-default)',
            borderRadius: 'var(--radius-card)',
            boxShadow: 'var(--shadow-card)',
            backgroundColor: 'var(--brand-primary-light)',
            textAlign: 'left',
          }}
        >
          <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>하자 확률 요약</p>
          <p style={{ margin: 0, fontSize: 20, fontWeight: 700 }}>
            예상 하자 확률 {Math.round(prediction.probability * 100)}%
            {prediction.deferred_count > 0 && (
              <span style={{ fontSize: 13, fontWeight: 400, color: 'var(--text-muted)' }}>
                {' '}
                (판정 보류 {prediction.deferred_count}건 제외)
              </span>
            )}
          </p>
          {prediction.top_factors.length > 0 && (
            <ul style={{ margin: '4px 0 0', paddingLeft: 18, fontSize: 13, color: 'var(--text-muted)' }}>
              {prediction.top_factors.map((factor) => (
                <li key={factor.factor}>
                  {factor.factor} ({Math.round(factor.contribution * 100)}%)
                </li>
              ))}
            </ul>
          )}
        </section>

        {/* 판정 보류 안내 */}
        {deferredCount > 0 && (
          <div
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              gap: 8,
              padding: 'var(--space-3)',
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-card)',
              backgroundColor: 'var(--bg-card)',
              textAlign: 'left',
            }}
          >
            <PauseCircle
              size={16}
              color="var(--text-muted)"
              aria-hidden="true"
              style={{ flexShrink: 0, marginTop: 2 }}
            />
            <p style={{ margin: 0, fontSize: 13, color: 'var(--text-muted)' }}>
              판정 보류 {deferredCount}건 — 위 하자 확률에는 반영되지 않았습니다. 관련 필드가
              확인되면 판정이 재개됩니다.
            </p>
          </div>
        )}

        {/* 판정 목록 */}
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
          <h2 className="section-title" style={{ marginBottom: 0 }}>판정 목록</h2>
          {sortedVerdicts.map((verdict) => (
            <VerdictCard
              key={verdict.verdict_id}
              verdict={verdict}
              shipmentId={shipment.shipment_id}
            />
          ))}
        </div>

        <SkippedList skipped={unchecked} />

        <OutcomeForm shipmentId={shipment.shipment_id} />
      </div>
    </PageContainer>
  );
}
