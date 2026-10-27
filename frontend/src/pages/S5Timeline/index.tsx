import { useEffect, useRef } from 'react';
import { FileQuestion, Loader2, SatelliteDish } from 'lucide-react';
import { useParams, useSearchParams } from 'react-router-dom';
import {
  isDemoFixtures,
  useRealityActions,
  useShipmentData,
  useShipmentStoreStatus,
} from '../../shared/shipmentStore';
import { isNeverRun, sortEventsByTime } from '../../shared/realityView';
import { SkippedList } from '../../components/SkippedList';
import { ShipmentHeader } from '../../components/ShipmentHeader';
import { EmptyState } from '../../components/EmptyState';
import { PageContainer } from '../../components/PageContainer';
import type { Alert } from '../../types/domain';
import { AdapterBanner } from './AdapterBanner';
import { TimelineEvent } from './TimelineEvent';
import { TimelineEmptyState } from './TimelineEmptyState';
import { RealityCheckBar } from './RealityCheckBar';

export function S5Timeline() {
  const { id } = useParams();
  const data = useShipmentData(id);
  const storeStatus = useShipmentStoreStatus();
  const { runRealityCheck } = useRealityActions();

  // 화면전이_정의.md: "경보 카드 클릭 → /shipments/:id?event=<event_id> →
  // 타임라인에서 해당 마커로 스크롤". 이 페이지가 그 "스크롤"을 담당함
  const [searchParams] = useSearchParams();
  const highlightedEventId = searchParams.get('event');
  const highlightedRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (highlightedEventId !== null) {
      highlightedRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [highlightedEventId]);

  // 훅(useSearchParams·useRef·useEffect)을 전부 부른 다음에 "선적 없음"을
  // 처리합니다 — 훅 위에서 return하면 호출 순서가 깨져 React가 에러를 냅니다
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

  const { shipment, realityEvents, alerts, adapterStatus, vesselMatch } = data;

  // 이 이벤트를 근거로 삼는 경보 찾기 — 타임라인 위에 "경보 근거" 표식을 답니다.
  // 경보 내용 자체(근거 대조·이동)는 S6가 맡습니다. 두 화면이 같은 경보를
  // 나란히 보여주면 어느 쪽이 본체인지 알 수 없어서, 여기서는 표식만 둡니다.
  const alertsOfEvent = (eventId: string): Alert[] =>
    alerts.filter((alert) => alert.reality_event_ids.includes(eventId));

  // ?event=<id>로 들어오면 그 이벤트만이 아니라, 그 이벤트를 근거로 쓰는
  // 경보의 근거 이벤트를 전부 강조합니다.
  //
  // 화면전이_정의.md §S6→S5: "경보는 서류측·현실측 근거 이벤트를 각각 1건 이상
  // 보유하므로, 타임라인에서 두 지점을 연결해 보여준다". 하나만 강조하면 무엇과
  // 무엇이 어긋났는지가 안 보입니다. ?event= 규칙은 그대로 두고(문서 수정 불필요)
  // S5가 나머지 근거를 스스로 찾습니다.
  const highlightedEventIds = new Set<string>();
  if (highlightedEventId !== null) {
    highlightedEventIds.add(highlightedEventId);
    for (const alert of alertsOfEvent(highlightedEventId)) {
      for (const eventId of alert.reality_event_ids) highlightedEventIds.add(eventId);
    }
  }
  const sortedEvents = sortEventsByTime(realityEvents);
  const isDemo = isDemoFixtures();
  const neverRun = !isDemo && isNeverRun(adapterStatus);
  // C-ROUTE-01 같은 "기록 부재" 경보는 가리킬 이벤트가 없어 타임라인 표식으로 못 보입니다
  const absenceAlerts = alerts.filter((alert) => alert.reality_event_ids.length === 0);

  return (
    <PageContainer narrow>
      <div style={{ textAlign: 'left' }}>
        <h1 className="page-title" style={{ marginBottom: 'var(--space-4)' }}>선적 상세</h1>

        <ShipmentHeader shipment={shipment} boxed>
          <span style={{ fontSize: 12.5, color: 'var(--text-secondary)' }}>
            화물관리번호 {shipment.cargo_control_no ?? '-'}
            {shipment.lc_expiry_date !== null && ` · L/C 유효기일 ${shipment.lc_expiry_date}`}
          </span>
        </ShipmentHeader>

        <div style={{ height: 16 }} />

        {adapterStatus !== null && vesselMatch !== null && (
          <AdapterBanner status={adapterStatus} vesselMatch={vesselMatch} />
        )}

        <div style={{ height: 16 }} />

        {!isDemo && (
          <div style={{ margin: 'var(--space-1) 0 var(--space-2)' }}>
            <RealityCheckBar onRun={() => runRealityCheck(shipment.shipment_id)} />
          </div>
        )}

        {absenceAlerts.length > 0 && (
          <ul style={{ margin: '12px 0 0', paddingLeft: 18, fontSize: 13, color: 'var(--text-secondary)' }}>
            {absenceAlerts.map((alert) => (
              <li key={alert.alert_id}>
                {alert.message} <span style={{ color: 'var(--text-muted)' }}>(울산항 VTS 관제 기록에 해당 선박이 없음 — 기록 부재가 근거)</span>
              </li>
            ))}
          </ul>
        )}

        <h2 className="section-title">타임라인</h2>
        {neverRun ? (
          <EmptyState
            icon={SatelliteDish}
            message="아직 현실 대조를 실행하지 않았습니다. 위 버튼으로 울산항 VTS 관제 기록과 대조하세요."
          />
        ) : sortedEvents.length === 0 ? (
          // §5.6 "데이터 없음을 정상으로 판단하지 않는다" — 어댑터가 붙었는데
          // 이 선적 기록이 없는 경우와, 어댑터 연결 자체가 실패한 경우를
          // 같은 문장으로 뭉개지 않고 나눕니다 (TimelineEmptyState 참고).
          <TimelineEmptyState status={adapterStatus} />
        ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
          {sortedEvents.map((event) => {
            const isHighlighted = highlightedEventIds.has(event.event_id);
            // 스크롤은 URL이 직접 가리킨 이벤트로만 갑니다
            const isScrollTarget = event.event_id === highlightedEventId;
            const eventAlerts = alertsOfEvent(event.event_id);
            return (
              <div
                key={event.event_id}
                ref={isScrollTarget ? highlightedRef : undefined}
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: 4,
                  padding: 12,
                  border: isHighlighted
                    ? '1.5px solid var(--brand-primary)'
                    : '1px solid var(--border-default)',
                  borderRadius: 'var(--radius-card)',
                  boxShadow: 'var(--shadow-card)',
                  backgroundColor: isHighlighted ? 'var(--brand-primary-light)' : 'var(--bg-card)',
                }}
              >
                <TimelineEvent event={event} alerts={eventAlerts} />
              </div>
            );
          })}
        </div>
        )}

        <div style={{ marginTop: 16 }}>
          <SkippedList
            skipped={data.realitySkipped ?? []}
            hint="울산항 VTS 관제 기록 기준으로 평가하지 못한 항목입니다 (평가 못 함은 이상 없음이 아닙니다)."
          />
        </div>
      </div>
    </PageContainer>
  );
}
