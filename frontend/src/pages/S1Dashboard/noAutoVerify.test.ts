import { describe, expect, it } from 'vitest';

// 대시보드는 카드마다 /verify 를 부르지 않는다 — 감사 로그가 선적 수만큼 쌓인다.
// 저장된 스냅샷만 보여주고, 검증은 S3·S4의 명시적 동작으로만 실행한다.
const sources = import.meta.glob('./*.tsx', { query: '?raw', import: 'default', eager: true }) as Record<
  string,
  string
>;

describe('S1 대시보드', () => {
  it('어떤 파일도 검증/리포트 API 훅을 쓰지 않음', () => {
    expect(Object.keys(sources).length).toBeGreaterThan(0);
    for (const [file, src] of Object.entries(sources)) {
      expect(src, file).not.toMatch(/useVerify|verifyShipment|useReport|generateReport/);
    }
  });
});
