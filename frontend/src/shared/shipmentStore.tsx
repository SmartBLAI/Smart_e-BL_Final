import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { buildDraftDataFromFields, type ShipmentMockData } from '../mocks/shipmentData';
import {
  createDraftWithFields,
  deleteShipment,
  getShipment,
  listShipments,
  saveFields as saveFieldsApi,
} from '../api/shipment';
import type { DefectPrediction, FieldValue, Shipment, Verdict } from '../types/domain';

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
   * 필드값을 게이트웨이에 저장하고, 성공하면 화면 목록의 fields도 같이
   * 갱신합니다 — VerifyBar가 검증 실행 직전에 F2 교정 승인값을 영속시키는 데 씁니다.
   */
  saveFields: (
    shipmentId: string,
    documentId: string,
    page: number,
    fields: FieldValue[],
    editedFieldNames?: ReadonlySet<string>,
  ) => Promise<void>;
  /**
   * 선적을 게이트웨이에서 지우고 목록에서도 뺍니다 — 시연 리허설 중 쌓인
   * 테스트 데이터를 치울 방법이 UI에 없었습니다(P2-16).
   */
  remove: (shipmentId: string) => Promise<void>;
}

const ShipmentStoreContext = createContext<ShipmentStoreValue | null>(null);

export function ShipmentStoreProvider({ children }: { children: ReactNode }) {
  const [createdData, setCreatedData] = useState<ShipmentMockData[]>([]);
  const [status, setLoadStatus] = useState<ShipmentStoreStatus>('loading');

  useEffect(() => {
    let cancelled = false;

    (async () => {
      try {
        const shipments = await listShipments();
        // ponytail: 선적마다 상세 조회를 한 번씩 더 합니다(N+1) — 목록 응답에
        // 필드값까지 담겨 있지 않아서입니다. 지금은 부트스트랩 테넌트 하나뿐이라
        // 선적 수가 적어 문제없고, 늘어나면 목록 응답에 필드도 같이 주도록
        // 게이트웨이를 고칠 것.
        const details = await Promise.all(shipments.map((s) => getShipment(s.shipment_id)));
        if (cancelled) return;
        // 최신순(list는 이미 created_at 내림차순으로 옴)
        setCreatedData(
          details.map(({ shipment, fields, documents, verdicts, prediction }) =>
            buildDraftDataFromFields(shipment, fields, documents, verdicts, prediction),
          ),
        );
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

  const saveFields = useCallback(
    async (
      shipmentId: string,
      documentId: string,
      page: number,
      fields: FieldValue[],
      editedFieldNames?: ReadonlySet<string>,
    ): Promise<void> => {
      await saveFieldsApi(shipmentId, documentId, page, fields, editedFieldNames);
      setCreatedData((prev) =>
        prev.map((data) => (data.shipment.shipment_id === shipmentId ? { ...data, fields } : data)),
      );
    },
    [],
  );

  const remove = useCallback(async (shipmentId: string): Promise<void> => {
    await deleteShipment(shipmentId);
    setCreatedData((prev) => prev.filter((data) => data.shipment.shipment_id !== shipmentId));
  }, []);

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
      saveFields,
      remove,
    };
  }, [createdData, status, createDraft, recordVerification, saveFields, remove]);

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

/** 필드값을 게이트웨이에 저장하고 화면 목록에 반영합니다 — VerifyBar가 검증 실행 직전에 씁니다 */
export function useSaveFields(): (
  shipmentId: string,
  documentId: string,
  page: number,
  fields: FieldValue[],
  editedFieldNames?: ReadonlySet<string>,
) => Promise<void> {
  return useStore().saveFields;
}

/** 선적 삭제 — S1 대시보드 카드의 "삭제" 버튼이 씁니다 */
export function useDeleteShipment(): (shipmentId: string) => Promise<void> {
  return useStore().remove;
}
