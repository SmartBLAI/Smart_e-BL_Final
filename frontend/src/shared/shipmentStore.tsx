import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react';
import type { ReactNode } from 'react';
import {
  buildDraftDataFromFields,
  mockDataByShipment,
  type ShipmentMockData,
} from '../mocks/shipmentData';
import {
  confirmField as confirmFieldApi,
  createDraftWithFields,
  deleteShipment,
  getShipmentsOverview,
  saveFields as saveFieldsApi,
} from '../api/shipment';
import {
  acknowledgeAlert as acknowledgeAlertApi,
  addWhitelist,
  listAlerts,
  runRealityCheck as runRealityCheckApi,
} from '../api/reality';
import type { RealityView } from '../api/adaptersReality';
import { replaceAlert } from './realityView';
import { replaceField, withEditedValue } from './fieldEdit';
import type { ConfirmedFields } from './shipmentStats';
import type { Alert, DefectPrediction, FieldValue, Shipment, Verdict } from '../types/domain';

/**
 * 화면이 선적을 읽는 유일한 통로.
 *
 * 게이트웨이(src/smart_e_bl)에 실제로 저장된 선적만 돌려줍니다. 픽스처
 * 4건(mockShipments)은 2026-08-19부로 대시보드에서 완전히 뺐습니다 —
 * 게이트웨이가 붙은 뒤로는 실제로 업로드한 게 없으면 빈 화면(EmptyState)이
 * 맞는 동작입니다. 픽스처 데이터 자체는 S7·S8처럼 아직 축소 구현이라
 * 백엔드 계산이 없는 화면에서는 여전히 씁니다.
 *
 * 판정·하자확률(verdicts·prediction)은 지난 "검증 실행"에서 게이트웨이가
 * 저장해 둔 스냅샷입니다 — 한 번도 안 돌린 선적이면 빈 값입니다.
 *
 * ⚠ 경보·현실 대조·영향분석(S5·S6·S8)은 아직 백엔드가 계산해주지 않습니다.
 *   그 부분은 buildDraftDataFromFields가 여전히 빈 값으로 채웁니다.
 */

/**
 * 게이트웨이 목록 조회의 진행 상태. 'loading' 동안은 아직 아무 선적도
 * 못 찾은 게 정상이라 "선적을 찾을 수 없습니다"를 보여주면 안 된다 —
 * 새로고침·딥링크 직후 잠깐이라도 잘못된 안내가 뜨는 걸 막는다.
 */
export type ShipmentStoreStatus = 'loading' | 'ok' | 'error';

interface ShipmentStoreValue {
  /** 게이트웨이에 실제로 저장된 선적만. 새것이 위로 옵니다 (S1이 "최근 수정순"이라고 밝힘) */
  list: ShipmentMockData[];
  status: ShipmentStoreStatus;
  find: (shipmentId: string | undefined) => ShipmentMockData | null;
  /**
   * 선적을 만들고, 업로드한 파일과 추출된 필드값을 게이트웨이에 저장한 뒤
   * 그 shipment_id를 돌려줍니다. 저장이 끝날 때까지 기다려야 해서 비동기입니다.
   */
  createDraft: (file: File, fields: FieldValue[], lcFile?: File | null) => Promise<string>;
  /**
   * 검증 실행이 게이트웨이에 저장되고 나면, 화면 목록의 상태·판정도 같이 갱신합니다.
   *
   * 판정까지 같이 넣는 이유: 상태만 VERIFIED로 바꾸면 목록의 verdicts는 빈 채로
   * 남아, 검증 직후 뒤로 돌아왔을 때 "검증 완료" 배지 옆에 "아직 검증을
   * 실행하지 않았습니다"가 같이 뜹니다. 새로고침하면 게이트웨이가 같은 값을
   * 다시 주므로(상세 조회의 verdicts), 여기서 미리 맞춰두는 것뿐입니다.
   */
  recordVerification: (
    shipmentId: string,
    status: Shipment['status'],
    verdicts: Verdict[],
    prediction: DefectPrediction | null,
  ) => void;
  /**
   * 필드 1건의 값을 고칩니다 — 화면 목록을 먼저 바꾸고(S1·S4·S5·S7 즉시 반영)
   * 게이트웨이에 저장합니다. 실패하면 원래 필드로 되돌리고 던집니다. 데모(픽스처)
   * 모드는 로컬만 바꿉니다. 고친다고 확정되지는 않습니다(확정은 confirmField).
   */
  editField: (
    shipmentId: string,
    documentId: string | null,
    fieldName: string,
    value: string | null,
  ) => Promise<void>;
  /**
   * 선적을 게이트웨이에서 지우고 목록에서도 뺍니다 — 시연 리허설 중 쌓인
   * 테스트 데이터를 치울 방법이 UI에 없었습니다(P2-16).
   */
  remove: (shipmentId: string) => Promise<void>;
  /** 선적별 "값 확인함" 표시 — 화면 이동으로 사라지지 않게 스토어가 들고 있습니다 */
  confirmed: Record<string, ConfirmedFields>;
  /** 낙관적으로 표시하고 서버에 저장 — 실패하면 표시를 되돌리고 던집니다. 데모 모드는 로컬만 */
  confirmField: (shipmentId: string, fieldName: string) => Promise<void>;
  /** /alerts 목록을 못 불러왔는지 — 빈 목록을 "경보 없음"으로 읽지 않게 S6이 밝힙니다 */
  alertsError: boolean;
  /** 현실 대조 실행(POST check) 후 그 선적의 S5·S6 데이터를 갱신. 실패하면 던집니다 */
  runRealityCheck: (shipmentId: string) => Promise<void>;
  acknowledgeAlert: (alert: Alert) => Promise<void>;
  /** 정상 관행 등록 — 같은 룰의 다른 경보도 서버에서 바뀌므로 /alerts 를 다시 받습니다 */
  whitelistAlert: (alert: Alert, reason: string, callSign: string | null) => Promise<void>;
}

function withReality(data: ShipmentMockData, view: RealityView): ShipmentMockData {
  return {
    ...data,
    realityEvents: view.realityEvents,
    alerts: view.alerts,
    adapterStatus: view.adapterStatus,
    vesselMatch: view.vesselMatch,
    realitySkipped: view.skipped,
  };
}

/** 선적별로 /alerts 목록을 나눠 담습니다 */
function withAlerts(list: ShipmentMockData[], alerts: Alert[]): ShipmentMockData[] {
  return list.map((d) => ({
    ...d,
    alerts: alerts.filter((a) => a.shipment_id === d.shipment.shipment_id),
  }));
}

/**
 * 목업 시연 모드 — 주소 뒤에 `?demo=1`을 붙이면 게이트웨이 대신 픽스처를 씁니다.
 *
 * 2026-08-19에 "픽스처를 대시보드에서 뺀다"고 정한 결정은 그대로입니다 —
 * 기본값은 여전히 게이트웨이이고, 이 플래그를 켜야만 픽스처가 나옵니다.
 *
 * 플래그를 만든 이유: F5(정정 영향분석)·F6(현실 대조)·F7(판정 설명)은 아직
 * 게이트웨이가 계산해주지 않아서(buildDraftDataFromFields가 빈 값으로 채웁니다)
 * 픽스처 말고는 보여줄 데이터가 없습니다. 그래서 이 세 기능의 화면을 사람이
 * 열어볼 방법 자체가 없었습니다. 이건 그 리뷰용 통로입니다.
 *
 * sessionStorage에 남기는 이유: `?demo=1`은 화면을 옮기면(Link) 주소에서
 * 사라지는데, 그러면 대시보드에서 경보 센터로 넘어가는 순간 데이터가 없어집니다.
 * `?demo=0`으로 들어오면 끕니다. 탭을 닫으면 같이 사라집니다.
 */
const DEMO_KEY = 'blcopilot.demoFixtures';

function readDemoFlag(): boolean {
  const param = new URLSearchParams(window.location.search).get('demo');
  if (param === '1') sessionStorage.setItem(DEMO_KEY, '1');
  if (param === '0') sessionStorage.removeItem(DEMO_KEY);
  return sessionStorage.getItem(DEMO_KEY) === '1';
}

/** 지금 픽스처 모드인지 — 화면이 "목데이터입니다"를 밝히는 데 씁니다 */
export function isDemoFixtures(): boolean {
  return sessionStorage.getItem(DEMO_KEY) === '1';
}

const ShipmentStoreContext = createContext<ShipmentStoreValue | null>(null);

export function ShipmentStoreProvider({ children }: { children: ReactNode }) {
  const [createdData, setCreatedData] = useState<ShipmentMockData[]>([]);
  const [status, setLoadStatus] = useState<ShipmentStoreStatus>('loading');
  const [alertsError, setAlertsError] = useState(false);
  const [confirmed, setConfirmed] = useState<Record<string, ConfirmedFields>>({});

  const confirmField = useCallback(async (shipmentId: string, fieldName: string) => {
    setConfirmed((prev) => ({
      ...prev,
      [shipmentId]: { ...prev[shipmentId], [fieldName]: true },
    }));
    if (isDemoFixtures()) return;
    try {
      await confirmFieldApi(shipmentId, fieldName);
    } catch (err) {
      setConfirmed((prev) => {
        const { [fieldName]: _undone, ...rest } = prev[shipmentId] ?? {};
        return { ...prev, [shipmentId]: rest };
      });
      throw err;
    }
  }, []);

  useEffect(() => {
    let cancelled = false;

    // 픽스처 모드면 게이트웨이를 아예 부르지 않습니다 — 502가 나든 말든
    // 보여줄 데이터는 픽스처이므로, 실패를 기다릴 이유가 없습니다.
    if (readDemoFlag()) {
      setCreatedData(Object.values(mockDataByShipment));
      setLoadStatus('ok');
      return;
    }

    (async () => {
      try {
        // 선적 목록·상세·현실 대조는 개요 API 한 번으로, 경보는 따로 — 요청 수는 선적 수와 무관합니다.
        const [overview, globalAlerts] = await Promise.all([
          getShipmentsOverview(),
          listAlerts().catch((err) => {
            console.error('경보 목록을 불러오지 못했습니다', err);
            return null;
          }),
        ]);
        if (cancelled) return;
        // 최신순(list는 이미 created_at 내림차순으로 옴)
        const built = overview.map(({ shipment, fields, documents, verdicts, prediction, reality }) =>
          withReality(
            buildDraftDataFromFields(shipment, fields, documents, verdicts, prediction),
            reality,
          ),
        );
        setCreatedData(globalAlerts ? withAlerts(built, globalAlerts) : built);
        setAlertsError(globalAlerts === null);
        setLoadStatus('ok');
      } catch (err) {
        // 픽스처는 대시보드에서 뺐으므로 여기서 물러날 곳이 없습니다 — 목록은
        // 빈 채로 두고 status='error'로 화면이 "못 불러왔다"고 밝히게 합니다.
        console.error('선적 목록을 불러오지 못했습니다', err);
        if (!cancelled) setLoadStatus('error');
      }
    })();

    return () => {
      cancelled = true;
    };
  }, []);

  const createDraft = useCallback(
    async (file: File, fields: FieldValue[], lcFile?: File | null): Promise<string> => {
    // 근거 좌표(bbox)가 있는 필드들은 다 같은 페이지에서 나왔습니다 — 그중 하나에서 가져옵니다.
    const page = fields.find((f) => f.page !== null)?.page ?? 1;
    const { shipment, fields: saved, documents } = await createDraftWithFields(
      file,
      fields,
      page,
      lcFile,
    );
    setCreatedData((prev) => [buildDraftDataFromFields(shipment, saved, documents), ...prev]);
    return shipment.shipment_id;
    },
    [],
  );

  const recordVerification = useCallback(
    (
      shipmentId: string,
      status: Shipment['status'],
      verdicts: Verdict[],
      prediction: DefectPrediction | null,
    ) => {
      setCreatedData((prev) =>
        prev.map((data) =>
          data.shipment.shipment_id === shipmentId
            ? { ...data, shipment: { ...data.shipment, status }, verdicts, prediction }
            : data,
        ),
      );
    },
    [],
  );

  // 롤백 때 "고치기 전 필드"를 찾으려고 최신 목록을 ref로도 들고 있습니다
  const createdDataRef = useRef(createdData);
  createdDataRef.current = createdData;

  const editField = useCallback(
    async (
      shipmentId: string,
      documentId: string | null,
      fieldName: string,
      value: string | null,
    ): Promise<void> => {
      const before = createdDataRef.current
        .find((d) => d.shipment.shipment_id === shipmentId)
        ?.fields.find((f) => f.field_name === fieldName);
      if (before === undefined) return;
      const after = withEditedValue(before, value);
      setCreatedData((prev) => replaceField(prev, shipmentId, after));
      if (isDemoFixtures()) return;
      try {
        if (documentId === null) throw new Error('저장할 B/L 서류가 없습니다');
        await saveFieldsApi(shipmentId, documentId, before.page ?? 1, [after]);
      } catch (err) {
        setCreatedData((prev) => replaceField(prev, shipmentId, before));
        throw err;
      }
    },
    [],
  );

  const remove = useCallback(async (shipmentId: string): Promise<void> => {
    await deleteShipment(shipmentId);
    setCreatedData((prev) => prev.filter((data) => data.shipment.shipment_id !== shipmentId));
  }, []);

  const runRealityCheck = useCallback(async (shipmentId: string): Promise<void> => {
    const view = await runRealityCheckApi(shipmentId);
    setCreatedData((prev) =>
      prev.map((d) => (d.shipment.shipment_id === shipmentId ? withReality(d, view) : d)),
    );
  }, []);

  const acknowledgeAlert = useCallback(async (alert: Alert): Promise<void> => {
    const updated = await acknowledgeAlertApi(alert.alert_id);
    setCreatedData((prev) =>
      prev.map((d) =>
        d.shipment.shipment_id === updated.shipment_id
          ? { ...d, alerts: replaceAlert(d.alerts, updated) }
          : d,
      ),
    );
  }, []);

  const whitelistAlert = useCallback(
    async (alert: Alert, reason: string, callSign: string | null): Promise<void> => {
      if (!alert.rule_id) throw new Error('룰 정보가 없는 경보입니다');
      await addWhitelist({ rule_id: alert.rule_id, call_sign: callSign, reason });
      const all = await listAlerts();
      setCreatedData((prev) => withAlerts(prev, all));
    },
    [],
  );

  const value = useMemo<ShipmentStoreValue>(() => {
    const list = createdData;

    return {
      list,
      status,
      find: (shipmentId) =>
        shipmentId === undefined
          ? null
          : list.find((data) => data.shipment.shipment_id === shipmentId) ?? null,
      createDraft,
      recordVerification,
      editField,
      remove,
      confirmed,
      confirmField,
      alertsError,
      runRealityCheck,
      acknowledgeAlert,
      whitelistAlert,
    };
  }, [
    createdData, status, createDraft, recordVerification, editField, remove,
    confirmed, confirmField, alertsError, runRealityCheck, acknowledgeAlert, whitelistAlert,
  ]);

  return <ShipmentStoreContext.Provider value={value}>{children}</ShipmentStoreContext.Provider>;
}

function useStore(): ShipmentStoreValue {
  const store = useContext(ShipmentStoreContext);
  if (store === null) {
    throw new Error('ShipmentStoreProvider 안에서만 쓸 수 있습니다');
  }
  return store;
}

/** 선적 목록 — S1·S6처럼 여러 건을 한 화면에 놓는 곳에서 씁니다 */
export function useShipmentList(): ShipmentMockData[] {
  return useStore().list;
}

/**
 * 게이트웨이 목록 조회가 아직 끝나지 않았는지. S3·S4·S5·S7이 `useShipmentData`가
 * null을 돌려줄 때 "찾을 수 없습니다"와 "불러오는 중입니다"를 구분하는 데 씁니다
 * — status를 안 보면 새로고침·딥링크 순간 항상 전자로 잘못 보입니다.
 */
export function useShipmentStoreStatus(): ShipmentStoreStatus {
  return useStore().status;
}

/** URL의 :id로 선적 1건 찾기. 없으면 null */
export function useShipmentData(shipmentId: string | undefined): ShipmentMockData | null {
  return useStore().find(shipmentId);
}

/** 새 초안 만들기 — S2 업로드가 끝났을 때 씁니다 */
export function useCreateDraft(): (
  file: File,
  fields: FieldValue[],
  lcFile?: File | null,
) => Promise<string> {
  return useStore().createDraft;
}

/** 검증 결과(상태·판정·하자확률)를 화면 목록에 바로 반영합니다 — VerifyBar가 검증 저장 후에 씁니다 */
export function useRecordVerification(): (
  shipmentId: string,
  status: Shipment['status'],
  verdicts: Verdict[],
  prediction: DefectPrediction | null,
) => void {
  return useStore().recordVerification;
}

/** 필드 1건 즉시 저장(낙관적 갱신 + 실패 시 롤백) — S3 인라인 편집·교정 승인이 씁니다 */
export function useEditField(): ShipmentStoreValue['editField'] {
  return useStore().editField;
}

/** F6 — S5 "현실 대조 실행"·S6 경보 처리. 데모(픽스처) 모드에선 화면이 버튼을 숨깁니다 */
export function useRealityActions() {
  const { runRealityCheck, acknowledgeAlert, whitelistAlert, alertsError } = useStore();
  return { runRealityCheck, acknowledgeAlert, whitelistAlert, alertsError };
}

/** 선적 삭제 — S1 대시보드 카드의 "삭제" 버튼이 씁니다 */
export function useDeleteShipment(): (shipmentId: string) => Promise<void> {
  return useStore().remove;
}

const NO_CONFIRMED: ConfirmedFields = {};

/**
 * 선적의 "값 확인함" 표시와 확인 핸들러 — S3(편집)와 S1(필수 확인 건수)이 같은
 * 출처를 봐서 두 화면 숫자가 어긋나지 않게 합니다.
 */
export function useConfirmedFields(
  shipmentId: string | undefined,
): [ConfirmedFields, (fieldName: string) => Promise<void>] {
  const { confirmed, confirmField } = useStore();
  const mine = (shipmentId !== undefined && confirmed[shipmentId]) || NO_CONFIRMED;
  return [mine, async (fieldName) => { if (shipmentId !== undefined) await confirmField(shipmentId, fieldName); }];
}
