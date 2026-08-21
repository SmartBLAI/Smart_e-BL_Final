"""수용 기준 실측 (19번).

기획안 v2 가 5.1·5.3·5.4 에 붙인 **완료 기준**을 실제로 잰다. 1차 기획안에는
없던 숫자들이라 지금까지 한 번도 측정한 적이 없다.

실행:
    python -m acceptance
    python -m acceptance --count 200 --json acceptance.json

## 최댓값으로 판정한다

명세는 "선적 1건 검증 10초"라고 쓴다. **평균 10초는 절반이 넘긴다는 뜻이다.**
평균으로 보고하면 통과인데 사용자 절반이 기준 밖인 상태가 만들어지므로,
판정은 최댓값으로 하고 분포(p50·p95)를 함께 싣는다.

## 냉시작을 분리한다

첫 1회에는 모델 적재·폰트 등록·룰 카탈로그 파싱이 들어간다. 이건 요청당
비용이 아니라 프로세스당 비용이라, 섞으면 최댓값이 냉시작으로 정해져
정작 요청 비용을 못 본다. 따로 재서 따로 보고한다.

## 잴 수 없는 것을 결과에서 빼지 않는다

룰엔진이 평가불가를 1급 상태로 두는 것과 같은 이유다. 측정하지 못한 항목을
침묵으로 넘기면 "쟀고 통과했다"로 읽힌다. 미측정은 미측정으로 싣고, **왜**
못 쟀는지를 함께 남긴다.

## LLM 서사는 기본으로 끈다

`apply_narrative` 는 GEMINI_API_KEY 가 있으면 외부 API 를 호출한다. 그 경로의
시간은 우리 코드가 아니라 네트워크가 정하므로 기본 측정에서 제외하고, 어느
경로로 쟀는지를 결과에 표기한다. `--llm` 으로 켤 수 있다. F2(`terms.evaluate`
와 짝을 이루는 T16)도 같은 규율을 진다 — `default_selector()` 가 설정 없이는
`None` 을 돌려주므로 `--llm` 을 줘도 설정이 없으면 자동으로 결정론 경로만
잰다(`terms/llm_select.py:default_selector` docstring과 같은 전제).
"""

from __future__ import annotations

import argparse
import json
import statistics
import tempfile
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from time import perf_counter
from typing import Callable, List, Optional, Sequence, Tuple

from mlModel.synth import EVAL, SyntheticGenerator
from ocr.pipeline import IntakePipeline
from report import apply_narrative, build_report, render_pdf
from ruleEngine import RuleEngine
from terms.cascade import DocumentInput, Normalizer
from terms.glossary import GlossaryStack, load_glossary
from terms.llm_select import default_selector
from terms.similarity import NGramRanker

# ── 수용 기준 (기획안 v2) ────────────────────────────────────────
#
# 숫자는 v2 5.1·5.3·5.4 에서 그대로 옮겼다. 10.5 가 "명세 수치는 초기
# 목표치이며 조정 시 기획안을 함께 갱신하라"고 못박았으므로, 여기서 임의로
# 완화하지 않는다. 못 맞추면 완화가 아니라 보고 대상이다.

TARGET_VERIFY_SECONDS = 10.0        # 5.3 선적 1건 검증
TARGET_REPORT_SECONDS = 15.0        # 5.4 리포트
TARGET_REPORT_PDF_SECONDS = 30.0    # 5.4 PDF 포함
TARGET_INTAKE_10P_SECONDS = 60.0    # 5.1 10페이지 추출
TARGET_RATIO = 1.0                  # 근거 표시율·수치 일치율 100%
TARGET_NORMALIZE_FIELD_SECONDS = 2.0       # F2 기획안 — 필드 1건
TARGET_NORMALIZE_SHIPMENT_SECONDS = 10.0   # F2 기획안 — 선적 1건 일괄 (⑤ 포함)



@dataclass
class Timing:
    """반복 측정 결과. 냉시작은 표본에 넣지 않는다."""

    cold_ms: float
    warm_ms: List[float] = field(default_factory=list)

    @property
    def p50_ms(self) -> float:
        return statistics.median(self.warm_ms) if self.warm_ms else 0.0

    @property
    def p95_ms(self) -> float:
        if not self.warm_ms:
            return 0.0
        ordered = sorted(self.warm_ms)
        # 표본이 적을 때 index 가 끝을 넘지 않게 자른다.
        index = min(len(ordered) - 1, int(round(0.95 * (len(ordered) - 1))))
        return ordered[index]

    @property
    def max_ms(self) -> float:
        return max(self.warm_ms) if self.warm_ms else 0.0

    def to_dict(self) -> dict:
        return {
            "cold_ms": round(self.cold_ms, 1),
            "p50_ms": round(self.p50_ms, 1),
            "p95_ms": round(self.p95_ms, 1),
            "max_ms": round(self.max_ms, 1),
            "count": len(self.warm_ms),
        }


def measure(fn: Callable[[int], object], count: int) -> Timing:
    """fn 을 count 회 돌려 시간을 잰다. 첫 회는 냉시작으로 뗀다."""
    start = perf_counter()
    fn(0)
    cold_ms = (perf_counter() - start) * 1000

    warm: List[float] = []
    for index in range(1, count):
        start = perf_counter()
        fn(index)
        warm.append((perf_counter() - start) * 1000)
    return Timing(cold_ms=cold_ms, warm_ms=warm)


# ── 결과 ─────────────────────────────────────────────────────────

PASSED = "통과"
FAILED = "미달"
UNMEASURED = "미측정"


@dataclass
class Result:
    """수용 기준 1건의 실측 결과."""

    feature: str        # F1 | F3 | F4
    name: str
    spec: str           # 기획안 근거 절
    target: str         # 사람이 읽는 목표
    status: str         # 통과 | 미달 | 미측정
    measured: str = ""
    note: str = ""
    timing: Optional[Timing] = None

    def to_dict(self) -> dict:
        out = {
            "feature": self.feature,
            "name": self.name,
            "spec": self.spec,
            "target": self.target,
            "status": self.status,
            "measured": self.measured,
            "note": self.note,
        }
        if self.timing is not None:
            out["timing"] = self.timing.to_dict()
        return out


def _fmt_ms(value: float) -> str:
    """읽는 사람 기준으로 단위를 고른다.

    전부 초로 찍으면 `0.000초` 가 나오는데, 그 숫자는 통과 판정을 주면서
    아무것도 말하지 않는다 — 빠른 건지 측정이 안 된 건지 구분되지 않는다.
    """
    if value >= 1000:
        return f"{value / 1000:.2f}초"
    if value >= 1:
        return f"{value:.1f}ms"
    return f"{value * 1000:.0f}µs"


def _seconds_result(
    feature: str, name: str, spec: str, target_seconds: float, timing: Timing
) -> Result:
    """시간 기준 결과. 판정은 최댓값으로 한다."""
    return Result(
        feature=feature,
        name=name,
        spec=spec,
        target=f"{target_seconds:g}초 이하",
        status=PASSED if timing.max_ms <= target_seconds * 1000 else FAILED,
        measured=f"최대 {_fmt_ms(timing.max_ms)} (p95 {_fmt_ms(timing.p95_ms)})",
        timing=timing,
    )


def _ratio_result(
    feature: str, name: str, spec: str, hit: int, total: int, note: str = ""
) -> Result:
    """비율 기준 결과. 명세가 100% 를 요구하는 항목들이다."""
    ratio = hit / total if total else 0.0
    return Result(
        feature=feature,
        name=name,
        spec=spec,
        target="100%",
        status=PASSED if total and ratio >= TARGET_RATIO else FAILED,
        measured=f"{ratio:.2%} ({hit}/{total})",
        note=note,
    )


# ── F3 · F4 측정 ─────────────────────────────────────────────────

def measure_f3_f4(count: int, seed: int, use_llm: bool) -> List[Result]:
    """검증·리포트·PDF 를 같은 표본으로 잰다.

    평가셋 네임스페이스를 쓴다(16번). 개발 중 열람하지 않은 서류로 재는 것이
    시간 측정에서도 맞다 — 룰을 고치며 본 서류만 빠르게 도는 경우를 배제한다.
    """
    generator = SyntheticGenerator(seed=seed, split=EVAL)
    samples = generator.generate(count, 0.5)
    engine = RuleEngine()

    verdicts = []

    def verify(index: int) -> None:
        s = samples[index]
        verdicts.append(engine.verify(s.bl, s.lc, as_of=s.as_of))

    verify_timing = measure(verify, count)

    # **검증부터 잰다.** `/report` 는 verify → build_report → 서사를 한 번에
    # 하므로(`api.main._make_report`), 조립만 재면 사용자가 기다리는 시간이
    # 아니다. 이미 계산해 둔 verdict 를 재사용하면 0.000초가 나오는데, 그
    # 숫자는 통과 판정을 주면서 아무것도 말하지 않는다.
    def report(index: int) -> None:
        s = samples[index]
        verdict = engine.verify(s.bl, s.lc, as_of=s.as_of)
        built = build_report(verdict, s.bl.to_dict(), s.lc, as_of=s.as_of)
        if use_llm:
            apply_narrative(built)

    report_timing = measure(report, count)

    def report_pdf(index: int) -> None:
        s = samples[index]
        verdict = engine.verify(s.bl, s.lc, as_of=s.as_of)
        built = build_report(verdict, s.bl.to_dict(), s.lc, as_of=s.as_of)
        if use_llm:
            built = apply_narrative(built)
        render_pdf(built)

    # PDF 는 한 건이 무거워 전량을 돌리면 측정 자체가 오래 걸린다. 상한을 둔다.
    pdf_count = min(count, 30)
    pdf_timing = measure(report_pdf, pdf_count)

    results = [
        _seconds_result("F3", "선적 1건 검증", "v2 5.3", TARGET_VERIFY_SECONDS, verify_timing),
        _seconds_result("F4", "리포트 생성", "v2 5.4", TARGET_REPORT_SECONDS, report_timing),
        _seconds_result(
            "F4", "리포트 + PDF", "v2 5.4", TARGET_REPORT_PDF_SECONDS, pdf_timing
        ),
    ]
    if pdf_count < count:
        results[-1].note = f"표본 {pdf_count}건 (전량 렌더는 측정 자체가 길어진다)"
    results[1].note = "LLM 서사 포함" if use_llm else "템플릿 서사 (LLM 미포함)"

    results.extend(_measure_evidence_ratios(samples, verdicts, use_llm))
    return results


def _measure_evidence_ratios(samples, verdicts, use_llm: bool) -> List[Result]:
    """근거 표시율·수치 일치율. 시간과 달리 전건이 100% 여야 한다."""
    violations = [v for verdict in verdicts for v in verdict.violations]

    with_source = sum(1 for v in violations if v.source)
    with_remedy = sum(1 for v in violations if v.source and v.remedy)

    # 리포트의 수치가 판정 데이터와 일치하는가. 리포트가 스스로 다시 세는
    # 곳이 있으면 여기서 어긋난다.
    matched = 0
    for sample, verdict in zip(samples, verdicts):
        report = build_report(
            verdict, sample.bl.to_dict(), sample.lc, as_of=sample.as_of
        )
        if (
            report.counts == verdict.counts
            and report.defect_probability == verdict.defect_probability
            and len(report.risks) == len(verdict.violations)
            and len(report.unchecked) == len(verdict.skipped)
        ):
            matched += 1

    return [
        _ratio_result(
            "F3", "조문 근거 표시율", "v2 5.3", with_source, len(violations),
            note="룰 카탈로그가 source 를 필수로 요구하므로 구조로 보장된다",
        ),
        _ratio_result(
            "F4", "조문 인용 + 조치 문장 보유율", "v2 5.4",
            with_remedy, len(violations),
        ),
        _ratio_result(
            "F4", "리포트 수치와 판정 데이터 일치율", "v2 5.4",
            matched, len(samples),
        ),
    ]


# ── F2 측정 (16번) ───────────────────────────────────────────────
#
# 필드 1건(2초)·선적 1건 일괄(10초) 두 기준을 잰다. `terms.evaluate`(15번)가
# **정확성**(정밀도·재현율)을 재는 것과 이 절이 **응답 시간**을 재는 것은
# 서로 다른 축이다 — 정밀도가 아무리 높아도 10초를 넘기면 F2 는 배포할 수
# 없고, 그 반대도 마찬가지다. 이 절이 F2 정확성을 다시 재지 않는 이유다.

# 필드 1건 측정에 돌려 쓸 대표 입력 8종. 클래스 하나만 반복해서 재면 그
# 클래스가 유독 가볍거나(사전 exact 히트) 무거워(자유서식 정규식 스캔) 보일
# 수 있다 — 사전 조회·정규식 검증·유사도 판별까지 골고루 태우도록 서로 다른
# 클래스를 섞는다. 값은 실제로 표기 불일치를 담아 캐스케이드가 놀지 않게
# 고른다(이미 표준인 값만 돌리면 ⓪format 조기 종결만 재게 된다).
_F2_FIELD_CASES: Tuple[Tuple[str, str, str], ...] = (
    ("선하증권", "port_of_loading", "부산"),
    ("선하증권", "port_of_discharge", "PORTLAND, USA"),  # 동음이의 판별 경로까지 포함
    ("포장명세서", "gross_weight", "1,234.50 KGS"),
    ("포장명세서", "measurement", "25 CBM"),
    ("상업송장", "incoterms", "FOB BUSAN"),
    ("선하증권", "shipper", "HANJIN SHIPPING CO.,LTD"),
    ("상업송장", "description_of_goods", "HS 8471.30 1000 LAPTOP COMPUTERS"),
    ("포장명세서", "marks", "MSKU 123456 5 said to contain 500 cartons"),
)


def _f2_shipment_documents() -> List[DocumentInput]:
    """선적 1건 = 서류 3장(선하증권·상업송장·포장명세서) × 필드 10~15개.

    필드 이름은 `ocr/types.py:BLFields`·`ocr/doc_types.py` 의 **실제** 명세를
    그대로 옮긴다(15/9/10 필드) — 지어낸 필드로 재면 이 측정이 상한값이 된다
    (교정된 서식에서 잰 추출 정확도가 상한인 것과 같은 이유,
    `_extraction_accuracy` docstring 참고). 값도 상당수를 일부러 표기
    불일치로 채운다 — 전부 이미 표준인 값이면 캐스케이드가 ⓪ 에서 조기
    종결해 실제 요청이 태우는 사전 조회·정규식·유사도 비용을 재지 못한다.
    """
    bl = DocumentInput(
        doc="선하증권",
        fields={
            "bl_no": "HG290309",
            "shipper": "HANJIN SHIPPING CO.,LTD",
            "consignee": "GLOBAL TRADING CO LTD",
            "notify_party": "SAME AS CONSIGNEE",
            "vessel": "MSC BIANCA",
            "voyage_no": "V.112",
            "port_of_loading": "부산",
            # 국가를 붙이지 않은 동음이의 항구다(USPDX/AUPTJ). 값·인접 필드·L/C
            # 어디서도 국가를 좁힐 수 없어 ⑤단계까지 내려간다 — `--llm` 측정이
            # 실제로 Gemini 왕복을 재려면 선적 표본에 이런 필드가 하나는 있어야
            # 한다. "LOS ANGELES" 였을 때는 ⑤가 한 번도 안 돌아 25초 기준을
            # 1.1ms 로 "통과"했고, 그 수치는 아무것도 말하지 않았다.
            "port_of_discharge": "PORTLAND",
            "description_of_goods": (
                "HS 8471.30 1000 LAPTOP COMPUTERS, shipped on board vessel"
            ),
            "gross_weight": "1,234.50 KGS",
            "measurement": "25 CBM",
            "date_of_issue": "2026-01-01",
            "place_of_issue": "SEOUL, KOREA",
            "on_board_date": "2026-01-02",
            "total_freight": "$1,741.56",
        },
    )
    invoice = DocumentInput(
        doc="상업송장",
        fields={
            "invoice_no": "INV-2026-0417",
            "invoice_date": "2026-01-01",
            "seller": "SAMSUNG ELECTRONICS CO., LTD",
            "buyer": "ABC TRADING CORP",
            "description_of_goods": "HS 8471.30 1000 LAPTOP COMPUTERS",
            "quantity": "20 CTN",
            "total_amount": "USD 50,000",
            "incoterms": "FOB BUSAN",
            "lc_no": "LC-2026-0417",
        },
    )
    packing = DocumentInput(
        doc="포장명세서",
        fields={
            "invoice_no": "INV-2026-0417",
            "packing_date": "2026-01-01",
            "seller": "SAMSUNG ELECTRONICS CO., LTD",
            "buyer": "ABC TRADING CORP",
            "description_of_goods": "LAPTOP COMPUTERS 100 PCS",
            "package_count": "100 PCS",
            "gross_weight": "1,234.50 KGS",
            "net_weight": "10,000 KG",
            "measurement": "25 CBM",
            "marks": "MSKU 123456 5 said to contain 500 cartons",
        },
    )
    return [bl, invoice, packing]


def _prime_lazy_caches(normalizer: Normalizer, use_llm: bool) -> None:
    """스캔 대상 클래스를 전부 한 번씩 건드려 `cascade.py` 의 지연 캐시를
    미리 빌드한다. 결과는 버린다 — 목적은 부수효과(캐시 적재)뿐이다."""
    normalizer.normalize(_f2_shipment_documents(), llm=use_llm)


def measure_f2(count: int, use_llm: bool) -> List[Result]:
    """F2(`terms.normalize`) 응답 시간. 필드 1건·선적 1건 일괄을 같은
    `Normalizer` 인스턴스로 잰다.

    **냉시작을 분리한다.** 사전 카탈로그 YAML 파싱과 n-gram 인덱스 빌드
    (`GlossaryStack([load_glossary()])`)는 요청마다 드는 비용이 아니라
    `api/main.py:normalizer()` 싱글턴이 기동 시 1회만 문다(`glossary.py`
    docstring "카탈로그를 기동 시 1회만 읽는다"와 같은 배치). 섞어서 재면
    첫 요청이 그 비용을 통째로 떠안은 것처럼 보여 최댓값 판정이 냉시작으로
    정해지고, 정작 재야 할 요청 비용을 못 보게 된다(모듈 docstring "냉시작을
    분리한다").
    """
    cold_start_started = perf_counter()
    stack = GlossaryStack([load_glossary()])
    selector = default_selector() if use_llm else None
    normalizer = Normalizer(
        stack=stack,
        ranker=NGramRanker(),
        selector=selector,
    )
    # 사전 로드만으로는 냉시작이 끝나지 않는다. `cascade.Normalizer` 는 자유
    # 서식 문구 스캔(practice_phrase·transport_doc·delivery·goods)의 정규식
    # 인덱스를 생성 시점이 아니라 **그 클래스를 처음 스캔할 때** 지연
    # 빌드해 `_phrase_cache` 에 얹는다(`terms/cascade.py:Normalizer.__init__`
    # 주석 — 사전 항목 수백 건 × 별칭을 요청마다 컴파일하지 않으려는
    # 캐시다). 실측으로 확인했다: description_of_goods 를 처음 스캔하면
    # 약 100ms, 그 뒤로는 0.1ms 미만이다. 여기서 미리 한 번 태우지 않으면
    # 이 일회성 비용이 "따뜻한" 표본 하나에 숨어 최댓값을 밀어 올린다 —
    # 판정은 최댓값으로 하므로(모듈 docstring) 숨은 한 표본이 판정을
    # 좌우할 수 있다. `terms/` 소스는 고치지 않는다는 제약이 있으므로
    # (`cascade.py` 를 생성 시점에 즉시 빌드하도록 바꾸지 않는다) 이 파일이
    # 냉시작 구간 안에서 한 번 헛돌려 흡수한다.
    _prime_lazy_caches(normalizer, use_llm)
    cold_start_ms = (perf_counter() - cold_start_started) * 1000

    def normalize_field(index: int) -> None:
        doc, field_name, value = _F2_FIELD_CASES[index % len(_F2_FIELD_CASES)]
        normalizer.normalize(
            [DocumentInput(doc=doc, fields={field_name: value})], llm=use_llm
        )

    field_timing = measure(normalize_field, count)

    shipment_documents = _f2_shipment_documents()

    def normalize_shipment(_: int) -> None:
        normalizer.normalize(shipment_documents, llm=use_llm)

    shipment_timing = measure(normalize_shipment, count)

    # `use_llm=True` 라도 키가 없으면 `default_selector()` 가 None 이다.
    # 기준을 가르는 것은 **의도**가 아니라 **실제로 붙었는가**여야 한다 —
    # 안 붙은 실행에 재협상 기준(25초)을 대면 기획안 기준으로 잰 척하게 된다.
    llm_note = (
        "⑤LLM 포함" if selector is not None
        else ("⑤LLM 미포함(TERMS_LLM_SELECT/키 미설정으로 붙지 않음)" if use_llm
              else "⑤LLM 미포함(결정론 경로만)")
    )
    cold_note = f"냉시작(사전 로드+인덱스 빌드+지연 캐시 예열) {_fmt_ms(cold_start_ms)} — 별도 보고, 요청 비용에서 뺐다"

    field_result = _seconds_result(
        "F2", "표준 용어 교정 — 필드 1건", "F2 기획안",
        TARGET_NORMALIZE_FIELD_SECONDS, field_timing,
    )
    field_result.note = f"{llm_note} · {cold_note}"

    field_count = sum(len(d.fields) for d in shipment_documents)
    # ⑤를 켜도 기준은 기획안의 10초 하나다. 한때 25초로 올렸다가 되돌렸다 —
    # `gemini-3.7-flash`(2.5~15.9초, 하루 20건 무료 한도)를 쓸 때는 10초를
    # 넘겼지만, ⑤가 하는 일은 후보 5개 중 번호 하나 고르기라 lite 모델이면
    # 충분하고 `gemini-3.5-flash-lite` 는 선적 1건을 1.1초에 끝낸다.
    # 기준을 올리는 것보다 모델을 바꾸는 것이 옳은 답이었다.
    shipment_result = _seconds_result(
        "F2", "표준 용어 교정 — 선적 1건 일괄", "F2 기획안",
        TARGET_NORMALIZE_SHIPMENT_SECONDS, shipment_timing,
    )
    shipment_result.note = (
        f"서류 3장(선하증권·상업송장·포장명세서) × 필드 {field_count}건 · {llm_note}"
    )

    # 냉시작은 통과/미달을 가릴 기준이 없다 — 기획안이 냉시작 예산을 못박지
    # 않았다. `_extraction_accuracy` 가 "측정은 됐지만 수용 기준의 답은
    # 아니다"를 UNMEASURED 로 표시하는 것과 같은 자리다: 실측값은
    # `measured` 에 그대로 싣고, 기준이 없다는 사실을 감추지 않는다(모듈
    # docstring "잴 수 없는 것을 결과에서 빼지 않는다"와 같은 논거를 "기준이
    # 없는 것"에도 적용한다).
    cold_start_result = Result(
        feature="F2",
        name="표준 용어 교정 — 냉시작(사전 로드+인덱스 빌드+지연 캐시 예열)",
        spec="F2 기획안",
        target="기준 없음(참고값)",
        status=UNMEASURED,
        measured=_fmt_ms(cold_start_ms),
        note=(
            "YAML 파싱 + n-gram 인덱스 빌드 + 자유서식 문구 스캔 정규식 캐시 예열"
            "(`_prime_lazy_caches`). 셋 다 요청당 비용이 아니라 프로세스당 1회 비용이다"
        ),
    )

    return [field_result, shipment_result, cold_start_result]


# ── F1 측정 ──────────────────────────────────────────────────────

# 라벨 데이터셋 해상도. 좌표를 비율로 옮기는 기준이라 값 자체는 중요하지 않다.
_LABEL_WIDTH = 1654
_LABEL_HEIGHT = 2340
_PDF_WIDTH = 595.0
_PDF_HEIGHT = 842.0

# 교정된 서식의 정상 B/L 한 장. (필드명, 지면 비율 x, y, 텍스트)
# `field_parser.REGIONS` 가 교정된 그 레이아웃이다 — 이 사실이 아래
# '추출 정확도'를 상한값으로 만든다.
_BL_LINES = [
    ("header", 0.36, 0.03, "BILL OF LADING"),
    ("bl_no", 0.62, 0.08, "B/L NO HG290309"),
    ("shipper", 0.06, 0.14, "GAE WOON CO., LTD."),
    ("consignee", 0.06, 0.21, "DHHJ FRANCHISING CO., LTD."),
    ("notify", 0.06, 0.28, "TRY ENERGY CO., LTD."),
    ("vessel_info", 0.06, 0.40, "MSC BIANCA V.112"),
    ("port_left", 0.06, 0.45, "OMA, JAPAN"),
    ("port_right", 0.55, 0.45, "SHINJIMA, JAPAN"),
    ("cargo", 0.06, 0.55, "27 PKG CELL ASSEMBLY"),
    ("weight", 0.62, 0.62, "TOTAL 884 KG"),
    ("measurement", 0.62, 0.66, "TOTAL 349.64 CBM"),
    ("freight", 0.06, 0.78, "FREIGHT PREPAID $1,741.56"),
    ("issue_place", 0.27, 0.90, "SEOUL, KOREA"),
    ("issue_date", 0.27, 0.93, "SEP 06, 2006"),
]

# 위 서식이 담고 있는 정답. 추출 정확도의 대조군이다.
_BL_TRUTH = {
    "bl_no": "HG290309",
    "shipper": "GAE WOON CO., LTD.",
    "consignee": "DHHJ FRANCHISING CO., LTD.",
    "notify_party": "TRY ENERGY CO., LTD.",
    "port_of_loading": "OMA, JAPAN",
    "port_of_discharge": "SHINJIMA, JAPAN",
}


def _write_bl_pdf(path: Path, pages: int) -> bool:
    """텍스트 레이어를 가진 B/L PDF 를 만든다. PyMuPDF 가 없으면 False."""
    try:
        import pymupdf
    except ImportError:
        return False

    doc = pymupdf.open()
    for _ in range(pages):
        page = doc.new_page(width=_PDF_WIDTH, height=_PDF_HEIGHT)
        for _name, xr, yr, text in _BL_LINES:
            page.insert_text(
                (xr * _PDF_WIDTH, yr * _PDF_HEIGHT), text, fontsize=9, fontname="helv"
            )
    doc.save(str(path))
    doc.close()
    return True


def measure_f1(pages: int = 10) -> List[Result]:
    """텍스트 레이어 PDF 추출 시간과 정확도.

    스캔 경로(PaddleOCR)는 여기서 재지 않는다 — 실물 스캔이 없으면 정확도가
    측정되지 않고, 합성 이미지 1장으로는 여섯 모델 구성이 전부 만점이 나와
    아무것도 구분되지 않는다는 것을 이미 확인했다(2.1절).
    """
    unmeasurable = _f1_unmeasurable()

    with tempfile.TemporaryDirectory() as tmp:
        pdf_path = Path(tmp) / "bl_10p.pdf"
        if not _write_bl_pdf(pdf_path, pages):
            return [
                Result(
                    feature="F1", name=f"{pages}페이지 추출", spec="v2 5.1",
                    target=f"{TARGET_INTAKE_10P_SECONDS:g}초 이하", status=UNMEASURED,
                    note="PyMuPDF 미설치 — pip install pymupdf",
                )
            ] + unmeasurable

        pipeline = IntakePipeline()
        drafts = []

        def extract(index: int) -> None:
            drafts.append(pipeline.run_from_pdf(str(pdf_path), page_number=index))

        timing = measure(extract, pages)

        # 명세는 "10페이지 60초"다. 페이지당이 아니라 문서 전체 시간이므로
        # 냉시작을 포함한 총합으로 판정한다.
        total_ms = timing.cold_ms + sum(timing.warm_ms)
        results = [
            Result(
                feature="F1",
                name=f"{pages}페이지 추출 (텍스트 레이어)",
                spec="v2 5.1",
                target=f"{TARGET_INTAKE_10P_SECONDS:g}초 이하",
                status=(
                    PASSED if total_ms <= TARGET_INTAKE_10P_SECONDS * 1000 else FAILED
                ),
                measured=f"총 {_fmt_ms(total_ms)} (페이지당 p50 {_fmt_ms(timing.p50_ms)})",
                timing=timing,
            ),
            _extraction_accuracy(drafts[0]),
        ]

    return results + unmeasurable


def _extraction_accuracy(draft) -> Result:
    """교정된 서식에서의 추출 정확도.

    **수용 기준의 답이 아니다.** 이 레이아웃은 `field_parser.REGIONS` 가
    교정된 바로 그 서식이라, 여기서 나오는 값은 상한이지 실물 성적이 아니다.
    임의 레이아웃에서는 값이 밀린다는 것이 이미 관측돼 있다(선적항 자리에
    "DATE OF ISSUE" 가 들어갔다). 그래서 참고값으로만 싣는다.
    """
    hit = sum(
        1 for name, truth in _BL_TRUTH.items()
        if (draft.get(name).value if draft.get(name) else None) == truth
    )
    return Result(
        feature="F1",
        name="추출 정확도 (텍스트 PDF)",
        spec="v2 5.1",
        target="95%",
        status=UNMEASURED,
        measured=f"참고값 {hit / len(_BL_TRUTH):.2%} ({hit}/{len(_BL_TRUTH)})",
        note=(
            "교정 서식 기준이라 상한값이다. REGIONS 가 이 레이아웃에서 "
            "교정됐으므로 수용 기준의 답으로 쓸 수 없다 — 실물 서식이 필요하다"
        ),
    )


def _f1_unmeasurable() -> List[Result]:
    """지금 잴 수 없는 F1 기준. 왜 못 재는지가 결과의 일부다."""
    return [
        Result(
            feature="F1", name="추출 정확도 (스캔)", spec="v2 5.1", target="85%",
            status=UNMEASURED,
            note=(
                "실물 스캔 말뭉치가 없다. 합성 이미지 1장으로는 모델 구성 여섯 개가 "
                "전부 만점이라 정확도가 구분되지 않는다(2.1절)"
            ),
        ),
        Result(
            feature="F1", name="근거 좌표 보유율", spec="v2 5.1", target="100%",
            status=UNMEASURED,
            note=(
                "구조적으로 잴 수 없다 — `BLFields` 가 좌표를 들고 나오지 않는다. "
                "confidence·provenance 만 남고 bbox 는 파서 안에서 버려진다. "
                "DB 스키마의 field_value 는 자동 추출 값에 좌표를 CHECK 로 요구하므로 "
                "연동 시 반드시 걸린다"
            ),
        ),
        Result(
            feature="F1", name="오추출 라우팅 재현율", spec="v2 5.1", target="90%",
            status=UNMEASURED,
            note=(
                "수단은 생겼다(18번 · `ocr.degrade`). 다만 실행에 PaddleOCR 과 "
                "원본 서류 이미지가 필요해 이 측정에 포함하지 않는다 — 포함하면 "
                "수용 기준 측정 전체가 OCR 설치와 장당 10초에 묶인다. "
                "따로 돌릴 것: python -m ocr.degrade --image <서류.png>"
            ),
        ),
    ]


# ── 보고 ─────────────────────────────────────────────────────────

def render(results: Sequence[Result]) -> str:
    lines = [
        "",
        "수용 기준 실측 (기획안 v2 5.1 · 5.3 · 5.4)",
        "=" * 78,
        f"{'기능':<4} {'기준':<32} {'목표':<12} {'실측':<24} 판정",
        "-" * 78,
    ]
    for r in results:
        lines.append(
            f"{r.feature:<4} {r.name:<32} {r.target:<12} {r.measured:<24} {r.status}"
        )
    lines.append("-" * 78)

    counts = {s: sum(1 for r in results if r.status == s) for s in (PASSED, FAILED, UNMEASURED)}
    lines.append(
        f"통과 {counts[PASSED]} · 미달 {counts[FAILED]} · 미측정 {counts[UNMEASURED]}"
    )

    notes = [r for r in results if r.note]
    if notes:
        lines.append("")
        lines.append("비고")
        for r in notes:
            lines.append(f"  · {r.name}: {r.note}")

    failed = [r for r in results if r.status == FAILED]
    if failed:
        lines.append("")
        lines.append("미달 항목 — 기획안 10.5 에 따라 임의 완화 대상이 아니다")
        for r in failed:
            lines.append(f"  · [{r.feature}] {r.name}: 목표 {r.target} / 실측 {r.measured}")

    lines.append("")
    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="수용 기준 실측 (19번)")
    parser.add_argument("--count", type=int, default=100, help="F3·F4 표본 수")
    parser.add_argument("--pages", type=int, default=10, help="F1 추출 페이지 수")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument(
        "--llm", action="store_true",
        help="리포트 서사를 LLM 으로 생성해 잰다 (네트워크에 묶인다)",
    )
    parser.add_argument("--json", type=Path, help="결과를 JSON 으로 저장")
    args = parser.parse_args()

    results = (
        measure_f1(args.pages)
        + measure_f2(args.count, args.llm)
        + measure_f3_f4(args.count, args.seed, args.llm)
    )
    # 기능 순으로 모아 보여 준다. 측정 순서는 의존 관계지 읽는 순서가 아니다.
    results.sort(key=lambda r: (r.feature, r.status == UNMEASURED))

    print(render(results))

    if args.json:
        args.json.write_text(
            json.dumps(
                {
                    "measured_at": datetime.now().isoformat(timespec="seconds"),
                    "sample_count": args.count,
                    "llm_narrative": args.llm,
                    "results": [r.to_dict() for r in results],
                },
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
        print(f"JSON 저장: {args.json}")


if __name__ == "__main__":
    # `.env` 는 **CLI 실행에서만** 읽는다. 모듈 임포트 시점에 읽으면
    # 테스트가 실제 GEMINI_API_KEY 를 집어 네트워크를 타기 시작한다 —
    # 실제로 그렇게 깨뜨렸다(전체 스위트 5초 → 18.6초, 실패 1건 추가).
    # `remaining-work.md` 가 "외부 API 기능은 기본 꺼짐"을 규약으로 둔 이유가
    # 이것이다: 테스트가 조용히 네트워크·비용·지연에 묶이면 안 된다.
    from dotenv import load_dotenv

    load_dotenv()

    main()
