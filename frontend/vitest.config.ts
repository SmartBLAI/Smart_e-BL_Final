import { defineConfig } from 'vitest/config';

// P1-12: 순수 로직(집계·게이트·wire 어댑터·확장자 라우팅)만 검증합니다.
// 컴포넌트 렌더링 테스트가 아니라서 jsdom이 필요 없습니다 — 기본 환경(node)을 그대로 씁니다.
export default defineConfig({
  test: {
    include: ['src/**/*.test.ts'],
  },
});
