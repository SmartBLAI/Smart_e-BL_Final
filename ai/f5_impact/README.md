# f5_impact — F5 정정 영향분석 (전용 백엔드 모듈 없음)

이 폴더는 비어 있다. 잊어서가 아니라, **현재 F5 의 백엔드 몫이 F2 안에서
나오기 때문**이다. 지금 상태를 여기 적어 둔다 — `ls ai/` 했을 때 F5 만 없어서
"빠뜨렸나" 를 다시 조사하지 않게 하려는 것이다.

## 지금 F5 를 만드는 코드는 어디 있나

| 조각 | 위치 |
|---|---|
| 영향 자리 산출 (`Suggestion.impact` — 같은 값이 쓰인 다른 필드) | `ai/f2_terms/cascade.py` |
| 승인 시 영향 자리까지 함께 치환 (`scope="all"`) · `Correction.impact` 기록 | `ai/f2_terms/apply.py` |
| 타입 정의 (`FieldRef`, `Suggestion.impact`, `Correction.impact`) | `ai/f2_terms/types.py` |
| 응답 전달 | `ai/api/main.py` — `/normalize`, `/normalize/apply` |
| 화면 (S3 초안 편집기 인라인 패널) | `frontend/src/pages/S3Draft/ImpactPanel.tsx`, `impactMerge.ts` |

`f2_terms/types.py` 의 `Suggestion.impact` 주석이 "`impact` 는 F5(정정
영향분석)의 입력이다" 라고 밝히는 그 경계다.

## 아직 없는 것

기획안이 말하는 **캐스케이드 역산**(필드 변경 → 영향 문서·필드·담당 당사자·
재확인 필요 여부를 제약 그래프로 되짚기)은 백엔드에 없다. 프론트 `ImpactPanel`
은 축소 구현이라 `shipment.fixture.ts` 의 `mockImpactItems` /
`mockImpactResult` 로 깊이 2 · 제약 3종(EQ·SUM·REF)만 그린다.

## 코드가 생기면

제약 그래프 역산을 실제로 구현할 때 이 폴더가 그 자리다. F2 캐스케이드가
이미 갖고 있는 제약 관계를 읽어 역방향으로 훑는 모듈이므로, `f2_terms` 를
임포트하는 쪽이 되지 그 반대가 아니다.
