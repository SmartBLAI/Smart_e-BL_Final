import type { TextSpan } from '../../types/domain';

/**
 * 두 글자 범위가 겹치는지 판정 (§5.5).
 * 자유서식 필드(상품명세 등)에서 교정 제안 두 개가 같은 부분을 고치려 하면
 * 동시에 승인했을 때 나중 것이 앞 것을 덮어씁니다 — 그걸 미리 알려주기 위한 판정입니다.
 */
export function spansOverlap(a: TextSpan, b: TextSpan): boolean {
  return a.start < b.end && b.start < a.end;
}

/** span 목록 안에 서로 겹치는 쌍이 하나라도 있으면 true */
export function hasOverlappingSpans(spans: TextSpan[]): boolean {
  for (let i = 0; i < spans.length; i++) {
    for (let j = i + 1; j < spans.length; j++) {
      if (spansOverlap(spans[i], spans[j])) return true;
    }
  }
  return false;
}
