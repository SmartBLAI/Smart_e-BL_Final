import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // .env 파일을 읽습니다. 세 번째 인자 ''는 "VITE_ 로 시작하지 않는 것도 읽어라"는 뜻입니다.
  const env = loadEnv(mode, process.cwd(), '')

  // aiService(FastAPI)가 떠 있는 곳. .env 에서 바꿀 수 있습니다.
  // 포트 5000 은 백엔드 문서가 정한 값입니다 (docs/ai-service/api-spec.md "Base URL").
  const aiTarget = env.AI_SERVICE_ORIGIN ?? 'http://127.0.0.1:5000'

  // 게이트웨이(src/smart_e_bl, FastAPI)가 떠 있는 곳. 로컬 개발 시 기본 포트는
  // uvicorn 기본값 8000 (docker-compose에서는 8001로 노출되지만, 그건 컨테이너 밖
  // 포트라 로컬 uv run 실행과 다릅니다).
  const gatewayTarget = env.GATEWAY_ORIGIN ?? 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      proxy: {
        // Vite 가 대신 요청을 전달합니다. 브라우저 입장에서는 같은 출처(5173)로
        // 보내는 것이므로 CORS 가 아예 생기지 않습니다.
        //
        // aiService 쪽에도 CORS 를 열어뒀으니 직접 붙어도 되지만, 그러면 백엔드
        // 허용 목록(CORS_ALLOW_ORIGINS)과 프론트 주소가 양쪽 다 맞아야 합니다.
        // 프록시가 그 조건을 없애줍니다.
        //
        // 운영에서는 게이트웨이가 앞에 서므로 이 프록시는 개발 전용입니다.
        '/ai-api': {
          target: aiTarget,
          changeOrigin: true,
          // '/ai-api/verify' → '/verify' 로 접두어를 떼고 보냅니다.
          rewrite: (path) => path.replace(/^\/ai-api/, ''),
        },
        // 게이트웨이용 프록시 — 위와 같은 이유(CORS 회피)
        '/gw-api': {
          target: gatewayTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/gw-api/, ''),
        },
      },
    },
  }
})
