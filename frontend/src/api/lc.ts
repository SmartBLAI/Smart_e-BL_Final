/**
 * 신용장(MT700) — 원문을 L/C 조건으로 바꾸고, 그걸 `/verify` 에 실어 보냅니다.
 *
 * 왜 필요한가: L/C 조건 없이 `/verify` 를 부르면 룰엔진이 29개 룰 중 17개를
 * "평가불가"로 건너뜁니다. 그런데 화면에는 **위반 0건**으로 보입니다 —
 * 서류에 하자가 없어서가 아니라 대조할 기준이 없어서인데, 결과만 보면
 * 구분이 안 됩니다. 그래서 `notes`·`unmapped` 를 버리지 않고 같이 들고
 * 다닙니다 (백엔드 `ruleEngine/mt700.py` 가 명시적으로 요구하는 것).
 *
 * 저장 방식: MT700 전문 원문을 서류(`LC_MT700`)로 게이트웨이에 올려두고,
 * 필요할 때 다시 읽어서 파싱합니다. 파싱 결과를 저장할 자리(jsonb 컬럼)를
 * DB에 새로 만들면 마이그레이션이 필요한데, 이 배포는 마이그레이션을
 * 자동으로 적용하지 않습니다.
 */

// 파일 읽기는 게이트웨이, MT700 파싱은 aiService — postJson 의 기본 base URL 이
// aiService 라서 parseMt700 은 base URL 을 따로 안 넘깁니다.
import { getText, postJson, GATEWAY_API_BASE_URL } from './client';
import type { DocumentMeta } from '../types/domain';

/**
 * `POST /lc/mt700` 응답.
 *
 * `lc` 값의 타입이 제각각이라(문자열·숫자·문자열 배열) `unknown` 으로 둡니다.
 * 화면은 이 안을 뒤지지 않고 `/verify` 에 그대로 넘기기만 합니다.
 */
export interface LcParse {
  /** `/verify` 의 `lc` 에 그대로 실을 수 있는 L/C 조건 */
  lc: Record<string, unknown>;
  /** 원문에서 잘라낸 SWIFT 태그 (정규화 전) */
  tags: Record<string, string>;
  /** 태그로는 읽었지만 L/C 조건에 자리가 없는 것 (47A 등) */
  unmapped: Record<string, string>;
  /** 해석하지 못하고 버린 것 — 화면이 반드시 보여줘야 합니다 */
  notes: string[];
}

/** MT700 전문 원문 → L/C 조건. 태그를 하나도 못 찾으면 400 이 옵니다. */
export function parseMt700(text: string, signal?: AbortSignal): Promise<LcParse> {
  return postJson<LcParse>('/lc/mt700', { text }, signal);
}

/**
 * 이미 파싱한 결과를 서류 id 로 기억해 둡니다.
 *
 * S1 대시보드는 카드마다, S3·S4 는 화면마다 같은 선적의 L/C 를 찾습니다.
 * 캐시가 없으면 같은 전문을 화면 수만큼 내려받아 다시 파싱합니다. 서류는
 * 한 번 올리면 바뀌지 않으므로(버전이 오르면 id 가 달라짐) 만료가 없습니다.
 */
const cache = new Map<string, Promise<LcParse>>();

/**
 * 선적의 서류 목록에서 신용장을 찾아 L/C 조건을 돌려줍니다.
 * 신용장을 안 올린 선적이면 `null` — 그건 오류가 아니라 정상입니다.
 *
 * **취소 신호(AbortSignal)를 일부러 받지 않습니다.**
 *
 * 캐시에 담기는 건 "요청"이 아니라 "약속(Promise)" 하나이고, 그 약속은 여러
 * 화면이 나눠 씁니다. 여기에 맨 처음 부른 화면의 신호를 물려두면, 그 화면이
 * 사라질 때(예: 대시보드 카드에서 S4로 이동) 아직 그 약속을 기다리던 **다음
 * 화면까지** 같이 취소됩니다. 그러면 S4는 신용장을 못 읽은 채 "이 선적에는
 * 신용장이 첨부되지 않았습니다"라고 사실과 다르게 안내하고, 룰 17개가 조용히
 * 빠진 결과를 위반 0건처럼 보여줍니다 — 이 파일이 막으려던 바로 그 상황입니다.
 *
 * 취소를 못 해서 낭비되는 건 파일 한 번 읽기와 파싱 한 번뿐이고, 그마저도
 * 캐시에 남아 다음 화면이 그대로 씁니다. 부르는 쪽은 화면이 사라졌으면
 * 결과를 그냥 버리면 됩니다(useVerify·useReport가 그렇게 합니다).
 */
export function loadLcParse(
  shipmentId: string,
  documents: DocumentMeta[],
): Promise<LcParse | null> {
  const doc = documents.find((d) => d.kind === 'LC');
  if (!doc) return Promise.resolve(null);

  const hit = cache.get(doc.document_id);
  if (hit) return hit;

  const pending = getText(
    `/api/v1/shipments/${shipmentId}/documents/${doc.document_id}/file`,
    GATEWAY_API_BASE_URL,
  ).then((text) => parseMt700(text));

  // 실패한 약속을 캐시에 남기면 다음 화면도 영원히 같은 실패를 받습니다.
  pending.catch(() => cache.delete(doc.document_id));
  cache.set(doc.document_id, pending);
  return pending;
}
