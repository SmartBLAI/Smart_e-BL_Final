/**
 * 게이트웨이로 요청을 보내는 아주 얇은 도구.
 *
 * 브라우저는 게이트웨이하고만 통신합니다. aiService(추출·검증·리포트)는 게이트웨이가
 * 인증·감사를 거쳐 중계하므로 브라우저가 직접 부르지 않고, 내부 토큰도 받지 않습니다.
 */

/**
 * 게이트웨이(`src/smart_e_bl`) 주소 — 선적·서류·필드값을 DB에 저장하고 AI 호출을 중계하는 쪽입니다.
 * 개발 프록시·운영 nginx 모두 `/gw-api` (vite.config.ts, nginx.conf 참고).
 */
export const GATEWAY_API_BASE_URL: string =
  import.meta.env.VITE_GATEWAY_API_BASE_URL ?? '/gw-api';

/**
 * 저장된 선적의 AI 호출 경로 — 게이트웨이가 인증·감사를 거쳐 ai-service 로 중계합니다.
 * `postJson(gatewayAiPath(id, 'verify'), body, signal, GATEWAY_API_BASE_URL)` 처럼 씁니다.
 * 선적 id 가 없는 호출은 아래 `gatewayTenantAiPath` 를 씁니다.
 */
export const gatewayAiPath = (shipmentId: string, operation: string): string =>
  `/api/v1/shipments/${shipmentId}/ai/${operation}`;

/** 선적 id 없이 테넌트 단위로 중계되는 AI 호출 경로 (추출·L/C 파싱·용어 교정 등) */
export const gatewayTenantAiPath = (operation: string): string => `/api/v1/ai/${operation}`;

/**
 * 30초 타임아웃을 기본으로 건다. 호출부가 signal 을 준 경우에도 타임아웃은
 * 그대로 살아있어야 한다 — `signal ?? AbortSignal.timeout(30_000)` 이면
 * 호출부가 signal 을 주는 순간(useVerify·useReport·useExtract·useNormalize
 * 전부 그렇다) 타임아웃이 통째로 사라진다. `AbortSignal.any`로 둘 중
 * 먼저 신호가 오는 쪽을 따르게 한다.
 *
 * 이게 없으면 백엔드가 무응답일 때 "검증 중…" 같은 로딩 상태가 fetch가
 * 끝나기를 영원히 기다린다 — 브라우저는 스스로 타임아웃을 걸지 않는다.
 */
function withTimeout(signal?: AbortSignal): AbortSignal {
  return signal ? AbortSignal.any([signal, AbortSignal.timeout(30_000)]) : AbortSignal.timeout(30_000);
}

/**
 * 백엔드가 에러를 돌려줬을 때 던지는 오류.
 *
 * 용어: `extends Error` 는 "기본 오류에 정보를 더 붙인 오류를 만든다"는 뜻입니다.
 * 화면에서 `err instanceof ApiError` 로 "백엔드가 거절한 것"과 "네트워크가
 * 끊긴 것"을 구분할 수 있습니다.
 */
export class ApiError extends Error {
  // 생성자 인자에 바로 readonly 를 붙이는 축약형(파라미터 프로퍼티)은 이
  // 프로젝트의 tsconfig(`erasableSyntaxOnly`)가 막습니다 — 타입만 지우면
  // 그대로 JS 가 되는 문법만 쓰겠다는 설정이라, 필드를 따로 선언합니다.
  readonly status: number;
  readonly detail: string;

  constructor(status: number, detail: string) {
    super(`aiService ${status}: ${detail}`);
    this.name = 'ApiError';
    this.status = status;
    this.detail = detail;
  }
}

/**
 * 실패한 응답을 ApiError 로 던집니다.
 * FastAPI 는 에러를 { "detail": "..." } 로 내려줍니다.
 * 에러 본문이 JSON 이 아닐 수도 있으니(502 등) 실패해도 넘어갑니다.
 */
async function throwApiError(res: Response): Promise<never> {
  const detail = await res
    .json()
    .then((j: { detail?: string }) => j.detail ?? res.statusText)
    .catch(() => res.statusText);
  throw new ApiError(res.status, detail);
}

/** 실패면 던지고, 성공이면 JSON 을 꺼냅니다. 204(No Content)는 본문이 없어 res.json()이 던지므로 건너뜁니다. */
async function readJson<TRes>(res: Response): Promise<TRes> {
  if (!res.ok) await throwApiError(res);
  return (res.status === 204 ? undefined : await res.json()) as TRes;
}

/**
 * JSON 을 POST 하고 JSON 을 받습니다.
 *
 * `<TRes>` 는 "받아올 응답의 타입을 부르는 쪽이 정한다"는 뜻입니다 (제네릭).
 * 예: `postJson<WireVerifyResponse>('/verify', body)`
 */
export async function postJson<TRes>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
  baseUrl: string = GATEWAY_API_BASE_URL,
): Promise<TRes> {
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: withTimeout(signal),
  });

  return readJson<TRes>(res);
}

/** JSON 을 PUT 하고 JSON 을 받습니다 (예: 필드값 upsert). */
export async function putJson<TRes>(
  path: string,
  body: unknown,
  baseUrl: string,
  signal?: AbortSignal,
): Promise<TRes> {
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'PUT',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: withTimeout(signal),
  });

  return readJson<TRes>(res);
}

/** GET 으로 JSON 을 받습니다 (예: 선적 목록·상세 조회). */
export async function getJson<TRes>(
  path: string,
  baseUrl: string,
  signal?: AbortSignal,
): Promise<TRes> {
  const res = await fetch(`${baseUrl}${path}`, {
    signal: withTimeout(signal),
  });

  return readJson<TRes>(res);
}

/**
 * GET 으로 파일 원문을 텍스트로 받습니다 (예: 올려둔 MT700 전문 다시 읽기).
 *
 * `getJson` 과 나눈 이유는 응답이 JSON 이 아니기 때문입니다 — `res.json()` 을
 * 부르면 SWIFT 전문 첫 글자에서 파싱이 터집니다.
 */
export async function getText(
  path: string,
  baseUrl: string,
  signal?: AbortSignal,
): Promise<string> {
  const res = await fetch(`${baseUrl}${path}`, {
    signal: withTimeout(signal),
  });

  if (!res.ok) {
    throw new ApiError(res.status, res.statusText);
  }

  return await res.text();
}

/** DELETE 요청을 보냅니다 (예: 선적 삭제). 응답 본문이 없습니다(204). */
export async function deleteRequest(
  path: string,
  baseUrl: string,
  signal?: AbortSignal,
): Promise<void> {
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'DELETE',
    signal: withTimeout(signal),
  });

  if (!res.ok) await throwApiError(res);
}

/**
 * 파일을 업로드하고 JSON 을 받습니다 (예: 이미지/PDF 추출).
 *
 * `FormData` 를 보낼 때는 `Content-Type` 헤더를 **직접 쓰면 안 됩니다** —
 * 브라우저가 파일 조각을 구분하는 경계값(boundary)까지 자동으로 채워서
 * 넣어주는데, 헤더를 손으로 쓰면 그 경계값이 빠져서 백엔드가 못 읽습니다.
 *
 * `params` 는 URL 뒤에 붙는 `?page=0` 같은 쿼리 파라미터입니다.
 */
export async function postForm<TRes>(
  path: string,
  formData: FormData,
  params?: Record<string, string | number>,
  signal?: AbortSignal,
  baseUrl: string = GATEWAY_API_BASE_URL,
): Promise<TRes> {
  const query = params ? `?${new URLSearchParams(params as Record<string, string>)}` : '';
  const res = await fetch(`${baseUrl}${path}${query}`, {
    method: 'POST',
    body: formData,
    signal: withTimeout(signal),
  });

  return readJson<TRes>(res);
}

/**
 * JSON 을 POST 하고, 파일(PDF 등)을 받습니다 (예: 리포트 PDF 다운로드).
 *
 * 응답이 JSON 이 아니라 파일 원본(binary)이라 `res.blob()` 으로 받습니다.
 * 파일 이름은 백엔드가 `Content-Disposition` 응답 헤더에 실어 보내줍니다.
 */
export async function postJsonForBlob(
  path: string,
  body: unknown,
  signal?: AbortSignal,
  baseUrl: string = GATEWAY_API_BASE_URL,
): Promise<{ blob: Blob; filename: string | null }> {
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
    signal: withTimeout(signal),
  });

  if (!res.ok) await throwApiError(res);

  const disposition = res.headers.get('Content-Disposition') ?? '';
  const filenameMatch = /filename="?([^";]+)"?/.exec(disposition);
  return { blob: await res.blob(), filename: filenameMatch?.[1] ?? null };
}
