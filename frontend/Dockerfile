# 1단계: node로 빌드만 하고 버립니다 (결과물인 dist/ 만 다음 단계로 넘어감)
FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
RUN npm run build

# 2단계: 빌드된 정적 파일을 nginx로 서빙합니다 (Vercel이 하던 역할)
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 80
