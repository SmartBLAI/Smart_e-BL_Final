# f7_explain — F7 AI 판정 설명 (백엔드 미구현)

이 폴더는 비어 있다. **F7 은 지금 프론트엔드에만 있고, 데이터는 목데이터다.**
`ls ai/` 했을 때 F7 만 없어서 "빠뜨렸나" 를 다시 조사하지 않도록 상태를 적어
둔다.

## 지금 F7 처럼 보이는 것은 어디 있나

| 조각 | 위치 |
|---|---|
| 설명 블록 렌더 (미검증 인용 `verified:false` 는 렌더하지 않음) | `frontend/src/components/ExplanationBlock.tsx` |
| 인용 한 줄 (CLAUSE · EVENT · FIELD) | `frontend/src/components/CitationChip.tsx` |
| `Explanation` · `Citation` 타입 | `frontend/src/types/domain.ts` |
| 실제 데이터 | `frontend/src/mocks/shipmentData.ts` — **목데이터** |

리포트 산문은 F7 이 아니라 **F4** 다 — `ai/f4_report/narrative.py`. 이쪽은
"LLM 은 수치를 만들지 않는다(템플릿이 채운다)" 규약을 이미 지키지만, 인용 ID
의 실재를 대조하는 **출력 검증기는 없다**.

## 아직 없는 것

기획안이 F7 에 요구하는 두 가지가 백엔드에 없다.

1. **인용 무결성 검증기** — 생성된 설명이 인용한 조문 ID·이벤트 ID·필드명이
   실제 룰 카탈로그(`f3_rules/rules.yaml`)·현실 이벤트·추출 필드에 있는지
   대조하고, 없으면 재생성하거나 템플릿 문장으로 대체.
2. **판정별 설명 생성 엔드포인트** — 지금 `/verify`·`/reality/check` 는 위반
   목록만 돌려주고 설명은 붙이지 않는다.

## 코드가 생기면

이 폴더가 그 자리다. 검증기는 `f3_rules`(조문)·`f6_reality`(이벤트)·
`f1_intake`(필드)를 읽어 대조하므로 세 모듈을 임포트하는 쪽이 되고,
`f4_report/narrative.py` 의 LLM 폴백 규약(`Summary.source` 로 실제 출처를
정직하게 표기)을 그대로 따르면 된다.
