# 1단계: node로 빌드만 하고 버립니다 (결과물인 dist/ 만 다음 단계로 넘어감)
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
# Vite는 이 값을 빌드 시점에 JS 번들 안에 박아 넣습니다(런타임에 못 바꿈).
# 브라우저가 aiService를 직접 부르는 주소입니다.
#
# 기본값이 5050인 이유: 루트 docker-compose.yml이 aiService를 `5050:5000`으로
# 내보냅니다(호스트 5000은 macOS AirPlay가 씀). 컨테이너 안 포트는 5000이지만
# 브라우저는 호스트 쪽 포트로 붙으므로 5050이 맞습니다. 여기를 5000으로 두면
# 루트 compose를 안 거친 빌드(`docker build ./frontend` 등)가 아무도 안 듣는
# 주소를 번들에 굽습니다 — 배포 환경에서는 AI_SERVICE_PUBLIC_URL(.env)로 덮습니다.
ARG VITE_AI_API_BASE_URL=http://localhost:5050
ENV VITE_AI_API_BASE_URL=$VITE_AI_API_BASE_URL
# aiService 의 공유 시크릿 헤더(X-Internal-Token) 값. 마찬가지로 번들에
# 그대로 박히므로 진짜 비밀은 아니다 — 봇 최소 방어용.
ARG VITE_AI_INTERNAL_TOKEN=""
ENV VITE_AI_INTERNAL_TOKEN=$VITE_AI_INTERNAL_TOKEN
RUN npm run build

# 2단계: 빌드된 정적 파일을 nginx로 서빙합니다 (Vercel이 하던 역할)
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
