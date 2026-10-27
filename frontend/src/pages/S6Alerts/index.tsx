import { PauseCircle } from 'lucide-react';
import { useSearchParams } from 'react-router-dom';
import { EmptyState } from '../../components/EmptyState';
import { PageContainer } from '../../components/PageContainer';
import { isDemoFixtures, useRealityActions, useShipmentList } from '../../shared/shipmentStore';
import { filterBySeverity, sortAlerts } from '../../shared/realityView';
import type { Severity } from '../../types/domain';
import { AlertCard } from './AlertCard';
import { DeferredCard } from './DeferredCard';
import { RuleCoverageSection } from './RuleCoverageSection';
import { SeverityFilterBar } from './SeverityFilterBar';
import { ShipmentGroupHeader } from './ShipmentGroupHeader';

/** URL의 ?severity= 값이 유효한 Severity인지 확인. 이상한 값이면 무시(=전체) */
function parseSeverityParam(value: string | null): Severity | null {
  return value === 'Critical' || value === 'Warning' || value === 'Info' ? value : null;
}

/**
 * S6 경보 센터 — 서류와 실제 운송 기록이 어긋난 건을 전 선적에서 모아 봅니다.
 *
 * 전역 화면이라 상단에 선적 하나를 고정하지 않습니다. 대신 선적별 그룹 헤더를
 * 반복해서, 어느 선적의 경보인지 카드 위에서 바로 읽히게 합니다. 탭도 두지
 * 않습니다 — 탭은 "하나를 고르면 나머지는 안 보인다"는 뜻인데, 경보 센터는
 * 여러 선적을 한눈에 훑는 자리입니다.
 */
export function S6Alerts() {
  // 화면전이_정의.md §6 — S4·S6 공통 규칙인 ?severity= 필터. S6은 이 화면
  // 안에서만 구현합니다(S4는 T4 담당 범위 밖).
  const [searchParams, setSearchParams] = useSearchParams();
  const severityFilter = parseSeverityParam(searchParams.get('severity'));
  const { acknowledgeAlert, whitelistAlert, alertsError } = useRealityActions();
  const canAct = !isDemoFixtures();

  function handleSeverityChange(severity: Severity | null) {
    const next = new URLSearchParams(searchParams);
    if (severity === null) {
      next.delete('severity');
    } else {
      next.set('severity', severity);
    }
    setSearchParams(next);
  }

  // 목록 순서는 S1과 같은 useShipmentList를 따릅니다 — 두 화면의 선적 순서가
  // 다르면 같은 데이터인데 다른 목록처럼 보입니다.
  // 여기 담기는 alerts는 필터 없이 전부입니다 — 버튼 건수·"필터 해제 시 N건"
  // 문구가 필터된 값이 아니라 전체 값을 봐야 하기 때문입니다.
  const groups = useShipmentList().map((data) => ({
      data,
      alerts: sortAlerts(data.alerts),
      // 판정 보류는 아래 별도 구역에서 다룹니다 (심각도 필터의 영향을 받지 않음)
      deferred: data.verdicts.filter((verdict) => verdict.result === 'DEFERRED'),
  }));

  const allAlerts = groups.flatMap((group) => group.alerts);
  const totalAlertCount = allAlerts.length;
  const severityCounts: Record<Severity, number> = { Critical: 0, Warning: 0, Info: 0 };
  allAlerts.forEach((alert) => {
    severityCounts[alert.severity] += 1;
  });

  // 화면에 실제로 뿌릴 목록 — 필터가 있으면 여기서만 걸러냅니다
  const filteredGroups =
    severityFilter === null
      ? groups
      : groups.map((group) => ({
          ...group,
          alerts: filterBySeverity(group.alerts, severityFilter),
        }));

  const withAlerts = filteredGroups.filter((group) => group.alerts.length > 0);
  const withDeferred = groups.filter((group) => group.deferred.length > 0);
  const unacknowledged = withAlerts
    .flatMap((group) => group.alerts)
    .filter((alert) => !alert.acknowledged).length;

  return (
    <PageContainer narrow>
      <header
        style={{
          display: 'flex',
          alignItems: 'baseline',
          gap: 'var(--space-2)',
          flexWrap: 'wrap',
          marginBottom: 'var(--space-3)',
          textAlign: 'left',
        }}
      >
        <h1 className="page-title">경보 센터</h1>
        <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', wordBreak: 'keep-all' }}>
          서류 기재와 울산항 선박 운항 관제 기록이 어긋난 건 — 미확인 먼저, 그 안에서 심각도 순
        </span>
        <div style={{ flex: 1, minWidth: 'var(--space-2)' }} />
        <span style={{ fontSize: 12.5, fontWeight: 600, color: 'var(--text-secondary)' }}>
          미확인 {unacknowledged}건
        </span>
      </header>

      <div style={{ marginBottom: 'var(--space-4)' }}>
        <SeverityFilterBar
          counts={severityCounts}
          total={totalAlertCount}
          active={severityFilter}
          onChange={handleSeverityChange}
        />
      </div>

      {alertsError && (
        <p role="alert" style={{ color: 'var(--severity-warning)', fontSize: 13, textAlign: 'left' }}>
          경보 목록을 불러오지 못했습니다 — 아래 "경보 없음"은 이상 없음이 아니라 데이터 부족입니다.
        </p>
      )}

      {withAlerts.length === 0 ? (
        // 필터로 가려진 0건과 진짜 0건은 다른 문장입니다 — 전자는 필터를
        // 해제하면 몇 건이 있는지까지 알려줍니다.
        <EmptyState
          message={
            totalAlertCount === 0
              ? '지금 올라온 경보가 없습니다.'
              : `이 심각도의 경보가 없습니다 — 필터를 해제하면 ${totalAlertCount}건이 있습니다.`
          }
        />
      ) : (
        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          {withAlerts.map(({ data, alerts }) => (
            // 헤더와 카드들을 한 덩어리로 붙입니다 (index.css의 .alert-group)
            <section key={data.shipment.shipment_id} className="alert-group">
              <ShipmentGroupHeader data={data} count={`경보 ${alerts.length}건`} />
              {alerts.map((alert) => (
                <AlertCard
                  key={alert.alert_id}
                  alert={alert}
                  fields={data.fields}
                  realityEvents={data.realityEvents}
                  suggestions={data.suggestions}
                  explanation={data.explanations[alert.alert_id] ?? null}
                  callSign={data.vesselMatch?.call_sign ?? null}
                  onAcknowledge={canAct ? () => acknowledgeAlert(alert) : undefined}
                  onWhitelist={
                    canAct
                      ? (reason) => whitelistAlert(alert, reason, data.vesselMatch?.call_sign ?? null)
                      : undefined
                  }
                />
              ))}
            </section>
          ))}
        </div>
      )}

      {withDeferred.length > 0 && (
        <section style={{ marginTop: 'var(--space-6)', textAlign: 'left' }}>
          <div
            style={{
              display: 'flex',
              alignItems: 'center',
              gap: 'var(--space-2)',
              flexWrap: 'wrap',
              marginBottom: 'var(--space-2)',
            }}
          >
            <PauseCircle size={16} color="var(--text-muted)" aria-hidden="true" />
            <h2 className="section-title" style={{ margin: 0 }}>
              판정 보류 {withDeferred.reduce((sum, group) => sum + group.deferred.length, 0)}건
            </h2>
            <span style={{ fontSize: 12.5, color: 'var(--text-secondary)', wordBreak: 'keep-all' }}>
              — 아직 판단이 끝나지 않았습니다
            </span>
          </div>

          {/* 위 경보 목록과 달리 선적별 그룹 헤더를 반복하지 않습니다. 선적이
              한 건뿐일 때 같은 줄("HLCUBUS2608001 · 검토 중 · L/C …")이 두 번
              나왔습니다. 어느 선적인지는 카드가 B/L 번호로 밝힙니다.
              선적이 여러 건이 되면 묶는 방식을 다시 봅니다. */}
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-2)' }}>
            {withDeferred.flatMap(({ data, deferred }) =>
              deferred.map((verdict) => (
                <DeferredCard
                  key={verdict.verdict_id}
                  verdict={verdict}
                  fields={data.fields}
                  shipment={data.shipment}
                />
              )),
            )}
          </div>
        </section>
      )}

      {/* 판정 범위 공개 구역 — 판정 보류 구역과 나란히, 그 아래 둡니다.
          판정 보류(위)는 "이 판정이 왜 아직 안 끝났나"고, 이 구역은
          "이 룰을 애초에 실행할 수 있나"라 성격이 다릅니다. */}
      <RuleCoverageSection />
    </PageContainer>
  );
}
