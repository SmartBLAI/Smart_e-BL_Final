/**
 * aiService 로 요청을 보내는 아주 얇은 도구.
 *
 * 지금은 aiService(FastAPI)에 **직접** 붙습니다. 나중에 게이트웨이가 앞에
 * 서면 base URL 하나만 바꾸면 되도록 여기 한 곳에 모아둡니다.
 */

/**
 * 백엔드 주소.
 *
 * 기본값 `/ai-api` 는 **Vite 개발 프록시**를 가리킵니다 (vite.config.ts 참고).
 *
 * aiService 에 CORS 가 열려 있어서 `http://localhost:5000` 을 직접 적어도
 * 동작합니다. 그래도 프록시를 기본으로 두는 이유는, 직접 붙이면 백엔드의
 * 허용 목록(`CORS_ALLOW_ORIGINS`)과 프론트 주소가 **양쪽 다** 맞아야 하기
 * 때문입니다. 프록시를 거치면 브라우저에게는 같은 출처(5173)라 그 조건이
 * 아예 사라집니다.
 *
 * `import.meta.env` 는 Vite 가 `.env` 파일의 값을 넣어주는 자리입니다.
 * `VITE_` 로 시작하는 이름만 들어옵니다 (그래야 실수로 비밀값이 화면에
 * 딸려나가지 않습니다).
 */
export const AI_API_BASE_URL: string =
  import.meta.env.VITE_AI_API_BASE_URL ?? '/ai-api';

/**
 * 게이트웨이(`src/smart_e_bl`) 주소 — 선적·서류·필드값을 DB에 저장하는 쪽입니다.
 * aiService(추출 전용)와는 별개 서비스라 base URL도 따로 둡니다. 개발 프록시는
 * `/gw-api` (vite.config.ts 참고).
 */
export const GATEWAY_API_BASE_URL: string =
  import.meta.env.VITE_GATEWAY_API_BASE_URL ?? '/gw-api';

/**
 * aiService 를 브라우저가 직접 부를 때(위 설명대로, 게이트웨이가 아직
 * 안 서 있는 임시 상태) 같이 보내는 공유 토큰입니다.
 *
 * 이 값은 빌드된 JS 번들에 그대로 들어가므로 "누구나 볼 수 있는 값"입니다
 * — 진짜 로그인 인증이 아니라, 인증 없는 스캐너·봇이 API 를 마구 두드리는
 * 것만 막는 최소한의 문턱입니다. 미설정이면 헤더를 아예 안 보냅니다
 * (백엔드도 AI_INTERNAL_TOKEN 이 없으면 검사를 안 합니다 — 로컬 개발용).
 */
const AI_INTERNAL_TOKEN: string = import.meta.env.VITE_AI_INTERNAL_TOKEN ?? '';

function aiServiceAuthHeaders(baseUrl: string): Record<string, string> {
  return baseUrl === AI_API_BASE_URL && AI_INTERNAL_TOKEN
    ? { 'X-Internal-Token': AI_INTERNAL_TOKEN }
    : {};
}

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
 * JSON 을 POST 하고 JSON 을 받습니다.
 *
 * `<TRes>` 는 "받아올 응답의 타입을 부르는 쪽이 정한다"는 뜻입니다 (제네릭).
 * 예: `postJson<WireVerifyResponse>('/verify', body)`
 */
export async function postJson<TRes>(
  path: string,
  body: unknown,
  signal?: AbortSignal,
  baseUrl: string = AI_API_BASE_URL,
): Promise<TRes> {
  const res = await fetch(`${baseUrl}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...aiServiceAuthHeaders(baseUrl) },
    body: JSON.stringify(body),
    signal: withTimeout(signal),
  });

  if (!res.ok) {
    // FastAPI 는 에러를 { "detail": "..." } 로 내려줍니다.
    // 에러 본문이 JSON 이 아닐 수도 있으니(502 등) 실패해도 넘어갑니다.
    const detail = await res
      .json()
      .then((j: { detail?: string }) => j.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as TRes;
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
    headers: { 'Content-Type': 'application/json', ...aiServiceAuthHeaders(baseUrl) },
    body: JSON.stringify(body),
    signal: withTimeout(signal),
  });

  if (!res.ok) {
    const detail = await res
      .json()
      .then((j: { detail?: string }) => j.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as TRes;
}

/** GET 으로 JSON 을 받습니다 (예: 선적 목록·상세 조회). */
export async function getJson<TRes>(
  path: string,
  baseUrl: string,
  signal?: AbortSignal,
): Promise<TRes> {
  const res = await fetch(`${baseUrl}${path}`, {
    headers: aiServiceAuthHeaders(baseUrl),
    signal: withTimeout(signal),
  });

  if (!res.ok) {
    const detail = await res
      .json()
      .then((j: { detail?: string }) => j.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as TRes;
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
    headers: aiServiceAuthHeaders(baseUrl),
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
    headers: aiServiceAuthHeaders(baseUrl),
    signal: withTimeout(signal),
  });

  if (!res.ok) {
    const detail = await res
      .json()
      .then((j: { detail?: string }) => j.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }
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
  baseUrl: string = AI_API_BASE_URL,
): Promise<TRes> {
  const query = params ? `?${new URLSearchParams(params as Record<string, string>)}` : '';
  const res = await fetch(`${baseUrl}${path}${query}`, {
    method: 'POST',
    headers: aiServiceAuthHeaders(baseUrl),
    body: formData,
    signal: withTimeout(signal),
  });

  if (!res.ok) {
    const detail = await res
      .json()
      .then((j: { detail?: string }) => j.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }

  return (await res.json()) as TRes;
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
): Promise<{ blob: Blob; filename: string | null }> {
  const res = await fetch(`${AI_API_BASE_URL}${path}`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json', ...aiServiceAuthHeaders(AI_API_BASE_URL) },
    body: JSON.stringify(body),
    signal: withTimeout(signal),
  });

  if (!res.ok) {
    const detail = await res
      .json()
      .then((j: { detail?: string }) => j.detail ?? res.statusText)
      .catch(() => res.statusText);
    throw new ApiError(res.status, detail);
  }

  const disposition = res.headers.get('Content-Disposition') ?? '';
  const filenameMatch = /filename="?([^";]+)"?/.exec(disposition);
  return { blob: await res.blob(), filename: filenameMatch?.[1] ?? null };
}
