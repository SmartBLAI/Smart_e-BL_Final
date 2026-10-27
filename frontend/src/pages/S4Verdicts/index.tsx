import { ClipboardCheck, FileQuestion, Loader2 } from 'lucide-react';
import { Link, useParams } from 'react-router-dom';
import { VerdictCard } from './VerdictCard';
import { VerdictSummary } from './VerdictSummary';
import { DataSourceNotice } from '../../components/DataSourceNotice';
import { SkippedList } from '../../components/SkippedList';
import { EmptyState } from '../../components/EmptyState';
import { PageContainer } from '../../components/PageContainer';
import { useShipmentData, useShipmentStoreStatus } from '../../shared/shipmentStore';
import { bySeverity } from '../../constants/domain';
import { useVerify } from '../../api/useVerify';

export function S4Verdicts() {
  // URL이 /shipments/:id/verdicts 라서, useParams()로 그 :id 자리의 값을 꺼냅니다.
  // (App.tsx의 <Route path="/shipments/:id/verdicts"> 와 이름이 같아야 합니다)
  const { id } = useParams();
  const data = useShipmentData(id);
  const storeStatus = useShipmentStoreStatus();

  // 백엔드 aiService 의 /verify 를 부릅니다.
  //
  // 훅(use~)은 컴포넌트 맨 위에서, 조건문보다 먼저 불러야 합니다. 아래 early
  // return 뒤에 두면 "어떤 렌더에서는 부르고 어떤 렌더에서는 안 부르는" 상태가
  // 되어 React 가 오류를 냅니다. 그래서 data 가 없을 때는 null 을 넘겨
  // "요청하지 말라"고 알려줍니다.
  const verify = useVerify(data?.fields ?? null, { shipmentId: id, documents: data?.documents });

  // 주소창에 없는 선적 id를 직접 쳐서 들어온 경우. 단, 게이트웨이 목록
  // 조회가 아직 안 끝났으면 못 찾은 게 아니라 로딩 중인 것이다.
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

  const { shipment } = data;

  if (verify.status === 'loading') {
    return (
      <PageContainer narrow>
        <EmptyState icon={ClipboardCheck} message="검증 결과를 불러오는 중입니다…" />
      </PageContainer>
    );
  }

  // 백엔드가 성공하면 그 결과를, 실패하면 목데이터를 씁니다.
  // 어느 쪽인지는 화면 위 DataSourceNotice 가 항상 밝힙니다 — 목데이터를
  // 실제 판정처럼 보여주지 않기 위해서입니다 (규약 §2.4).
  const isLive = verify.status === 'ok';
  const verdicts = isLive ? verify.view.verdicts : data.verdicts;
  const skipped = isLive ? verify.view.skipped : [];

  const notice = isLive ? (
    <DataSourceNotice source="live" predictionModel={verify.view.predictionModel} />
  ) : (
    <DataSourceNotice source="mock" reason={verify.error.message} />
  );

  // 아직 검증 전(DRAFT)인 선적. 판정이 0건인 것과 "검증했는데 문제 없음"은
  // 전혀 다른 뜻이라, 0건 요약(위반 0 · 주의 0 · 참고 0)을 보여주면 후자로
  // 오해됩니다. 그래서 요약 대신 안내 문구를 띄웁니다.
  //
  // ⚠ 단, 백엔드가 응답한 경우(isLive)에는 "검증했는데 위반이 없다"가 맞습니다.
  //   검사하지 못한 항목이 있으면 그건 아래 SkippedList 가 따로 밝힙니다.
  if (verdicts.length === 0 && !isLive) {
    return (
      <PageContainer narrow>
        {notice}
        <EmptyState icon={ClipboardCheck} message="아직 검증을 실행하지 않았습니다." />
        <div style={{ display: 'flex', justifyContent: 'center' }}>
          <Link to={`/shipments/${shipment.shipment_id}/draft`} className="btn btn-primary">
            초안 편집기에서 검증 실행
          </Link>
        </div>
      </PageContainer>
    );
  }

  return (
    <PageContainer narrow>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
        {/* 다른 화면(S3·S5·S6·S7)처럼 제목 줄을 두고, 이동 버튼은 제목 오른쪽에 둡니다 */}
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            gap: 'var(--space-2)',
            flexWrap: 'wrap',
          }}
        >
          <h1 className="page-title">검증 결과</h1>
          <div style={{ display: 'flex', gap: 'var(--space-2)' }}>
            <Link to={`/shipments/${shipment.shipment_id}`} className="btn btn-secondary">
              운항 타임라인
            </Link>
            <Link to={`/shipments/${shipment.shipment_id}/report`} className="btn btn-primary">
              리포트 생성
            </Link>
          </div>
        </div>

        {notice}

        <VerdictSummary verdicts={verdicts} />
        {[...verdicts].sort(bySeverity).map((verdict) => (
          <VerdictCard
            key={verdict.verdict_id}
            verdict={verdict}
            shipmentId={shipment.shipment_id}
            // F7 — 백엔드 응답(verdict_id가 목데이터와 다를 수 있음)이든 목데이터든
            // data.explanations에 없는 판정은 undefined → null로 정리해 넘깁니다.
            explanation={data.explanations[verdict.verdict_id] ?? null}
            realityEvents={data.realityEvents}
          />
        ))}

        {/* 신용장이 없으면 대조 룰이 통째로 빠지는데 화면에는 "위반 0건"으로
            보입니다. 못 검사한 이유를 여기서 밝힙니다. */}
        <SkippedList
          skipped={skipped}
          hint={
            isLive && verify.lc === null
              ? '이 선적에는 신용장(MT700)이 첨부되지 않았습니다. L/C 조건과 대조하는 룰은 기준이 없어 판단할 수 없습니다 — 업로드 화면에서 신용장을 함께 올리면 검사합니다.'
              : undefined
          }
        />
      </div>
    </PageContainer>
  );
}
