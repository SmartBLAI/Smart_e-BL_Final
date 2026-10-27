import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // .env 파일을 읽습니다. 세 번째 인자 ''는 "VITE_ 로 시작하지 않는 것도 읽어라"는 뜻입니다.
  const env = loadEnv(mode, process.cwd(), '')

  // 게이트웨이(src/smart_e_bl, FastAPI)가 떠 있는 곳. 로컬 개발 시 기본 포트는
  // uvicorn 기본값 8000 (docker-compose에서는 8001로 노출되지만, 그건 컨테이너 밖
  // 포트라 로컬 uv run 실행과 다릅니다).
  const gatewayTarget = env.GATEWAY_ORIGIN ?? 'http://127.0.0.1:8000'

  return {
    plugins: [react()],
    server: {
      proxy: {
        // Vite 가 대신 요청을 전달합니다. 브라우저 입장에서는 같은 출처(5173)로
        // 보내는 것이므로 CORS 가 아예 생기지 않습니다. AI 호출도 게이트웨이가 중계합니다.
        //
        // 게이트웨이용 프록시
        '/gw-api': {
          target: gatewayTarget,
          changeOrigin: true,
          rewrite: (path) => path.replace(/^\/gw-api/, ''),
        },
      },
    },
  }
})
