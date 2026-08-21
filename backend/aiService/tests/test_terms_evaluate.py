"""F2 정밀도 평가 임계값 테스트 (15번).

여기서 잠그는 것은 두 가지다.

1. **측정 도구가 정직한가** — `test_acceptance.py` 와 같은 규약이다.
   `requires_choice` 를 제안으로 세면 애매한 케이스를 전부 choice 로 밀어
   정밀도를 1.0 으로 만들 수 있다(`docs/ai-service/f2-standard-terms.md`
   §정밀도를 재현율보다 우선한다). 그 구멍이 나중에 조용히 다시 열리지
   않는지를 `_aggregate` 단위 테스트로 고정한다 — 실제 코퍼스나 사전을
   건드리지 않으므로 카탈로그가 바뀌어도 깨지지 않는다.

2. **커밋된 코퍼스에서 기획안 기준(0.90)을 넘는가** — LLM 을 끄면 판정이
   전부 결정론(사전 조회·정규식·체크디지트)이라 어느 기계에서도 같은
   수치가 나온다. **지금 실측이 0.90 보다 높다고 그 실측값을 임계값으로
   박지 않는다** — 그러면 사소한 리팩터링만으로도 회귀로 잡힌다. 기획안이
   못박은 0.90 을 그대로 쓴다. 시간은 여기서 재지 않는다 — 기계마다
   달라지므로 `acceptance.py` 의 몫이다(`HANDOFF.md` §9).
"""

from __future__ import annotations

from terms.evaluate import CaseEval, _aggregate, evaluate_corpus


class Test정밀도_기준:
    """LLM 을 끄면 판정이 결정론이라 어느 기계에서도 같은 수치가 나온다.
    시간은 여기서 재지 않는다 — 기계에 따라 달라지므로 acceptance 의 몫이다."""

    def test_커밋된_코퍼스에서_정밀도가_0_90_이상이다(self):
        m = evaluate_corpus(llm=False)
        assert m.precision >= 0.90, f"정밀도 {m.precision:.4f} — 회귀"

    def test_커밋된_코퍼스에서_재현율이_0_90_이상이다(self):
        # 재현율도 함께 고정한다 — 정밀도만 지키면 "제안을 거의 안 해서
        # 정밀도가 높다"는 역설이 통과된다(§정밀도 "requires_choice 로
        # 밀어 정밀도를 1.0 으로 만들 수 있다"와 같은 종류의 구멍).
        m = evaluate_corpus(llm=False)
        assert m.recall >= 0.90, f"재현율 {m.recall:.4f} — 회귀"

    def test_결정론_경로는_LLM_옵션과_무관하게_같은_수치를_낸다(self):
        # TERMS_LLM_SELECT/GEMINI_API_KEY 가 설정돼 있지 않은 한
        # `--llm` 을 줘도 `default_selector()` 가 None 이라 결과가 같아야
        # 한다 — 이 저장소의 테스트 환경이 그 전제다.
        off = evaluate_corpus(llm=False)
        on = evaluate_corpus(llm=True)
        assert off.precision == on.precision
        assert off.recall == on.recall


class Test측정도구_정직성:
    """`test_acceptance.py` 머리말과 같은 규약 — 검사 대상은 측정 도구가
    정직한가이지 사전·캐스케이드의 성능이 아니다. 실제 코퍼스·사전을
    타지 않고 `_aggregate` 만 검증하므로 카탈로그가 바뀌어도 깨지지 않는다.
    """

    def test_requires_choice_케이스는_정밀도_분모에_들어가지_않는다(self):
        # PORTLAND 처럼 판별 불가라 choice 로 넘긴 케이스는 "판정"이
        # 아니므로 confirmed_total(정밀도 분모)에 잡히면 안 된다.
        cases = [
            CaseEval("A", "선하증권", "port_of_discharge", "port", "PORTLAND",
                     expected="choice", actual="choice"),
            CaseEval("B", "선하증권", "port_of_loading", "port", "부산",
                     expected="value:KRPUS", actual="value:KRPUS"),
        ]
        m = _aggregate(cases)

        assert m.confirmed_total == 1
        assert m.precision == 1.0
        assert m.choice_actual == 1
        assert m.choice_rate == 0.5

    def test_임의_선택_금지를_어기고_확정_제안을_내면_정밀도가_떨어진다(self):
        # 판별 불가(§동음이의)인데 캐스케이드가 임의로 하나를 확정해
        # 버리면, 그 확정은 "제안"으로 세어져 정밀도를 깎아야 한다 —
        # choice 로 카운트해 조용히 넘어가면 임의 선택 금지 위반이
        # 정밀도 수치에서 사라진다.
        cases = [
            CaseEval("C", "선하증권", "port_of_loading", "port", "PORTLAND",
                     expected="choice", actual="value:USPDX"),
        ]
        m = _aggregate(cases)

        assert m.confirmed_total == 1
        assert m.confirmed_correct == 0
        assert m.precision == 0.0

    def test_확정_제안이_없으면_재현율_분모만_깎이고_분자는_늘지_않는다(self):
        # 정답이 있는데 침묵한 케이스(Unevaluated 로 빠졌거나 신뢰도 미달)는
        # 재현율을 깎아야 한다 — confirmed_total 에 안 잡히므로 정밀도에는
        # 영향이 없다(분모가 다르다는 것이 이 지표 설계의 핵심).
        cases = [
            CaseEval("D", "선하증권", "port_of_loading", "port", "제다",
                     expected="value:SAJED", actual="none"),
        ]
        m = _aggregate(cases)

        assert m.confirmed_total == 0
        assert m.expect_total == 1
        assert m.recall == 0.0
        assert m.precision == 0.0  # 확정 제안이 0건이라 분모가 0 → 0.0
