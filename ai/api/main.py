"""
AI 서비스 API (기획안 6.2 "FastAPI(AI 모듈군)").

Express 게이트웨이(:4000)가 이 서비스(:5000)를 호출하고, 결과는 이 API 의
동기 HTTP 응답으로 그대로 돌아간다(콜백 URL 로 되돌리는 별도 경로는 없다).
저장은 하지 않는다 — 저장 책임은 게이트웨이에 있고, 여기서 DB 를 잡으면
AI 모듈이 스키마 변경에 묶인다.
"""

from __future__ import annotations

import hmac
import os
import threading
import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from contextlib import asynccontextmanager

from fastapi import Depends, FastAPI, File, Header, HTTPException, Request, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from dotenv import load_dotenv

from f4_report import TemplateNarrator, apply_narrative, build_report, render_pdf
from f4_report.share import (
    DEFAULT_TTL_SECONDS,
    ExpiredShareToken,
    ShareTokenError,
    ShareTokenTooLarge,
)
from f4_report import share as share_tokens
from f3_rules import UNDECLARED_VERSION, CrossDocumentEngine, DocumentSet, LCTerms, RuleEngine
from f6_reality import EventSourceError, RealityEngine, resolve_call_sign
from f2_terms import (
    Candidate,
    DocumentInput,
    Evidence,
    FieldRef,
    Glossary,
    GlossaryCatalogError,
    GlossaryStack,
    Normalizer,
    Suggestion,
    apply_suggestions,
    build_override,
    default_selector,
    glossary_version_override,
    llm_select_enabled,
    load_all_glossaries,
    reject_suggestions,
    verify_suggestion_id,
)

# `.env` 를 읽는다. 이 호출이 없으면 `.env.example` 이 설명하는 설정이 하나도
# 적용되지 않으며, **그 실패는 조용하다.** GEMINI_API_KEY 가 없으면 리포트가
# 템플릿으로 떨어지고, REPORT_SHARE_SECRET 가 없으면 프로세스마다 임시 키를
# 만들어 재시작 시 발급한 공유 링크가 전부 죽는다. 둘 다 에러 없이 "동작하는
# 것처럼" 보이므로 기동 시점에 확실히 읽어 둔다.
#
# 이미 설정된 환경변수는 덮지 않는다(python-dotenv 기본값). 컨테이너·CI 가
# 주입한 값이 파일보다 우선해야 하기 때문이다.
load_dotenv()

# 룰 카탈로그는 프로세스 기동 시 1회만 읽는다. 요청마다 읽으면 YAML 파싱이
# 응답 시간에 그대로 들어가고, 카탈로그 오류를 기동이 아니라 첫 요청에서
# 발견하게 된다.
_engine: Optional[RuleEngine] = None


def engine() -> RuleEngine:
    global _engine
    if _engine is None:
        _engine = RuleEngine()
    return _engine


# F5 서류 간 정합성(cross_doc.py) 도 같은 자리 — cross_rules.yaml 파싱을
# 요청마다 반복하지 않는다.
_cross_engine: Optional[CrossDocumentEngine] = None


def cross_engine() -> CrossDocumentEngine:
    global _cross_engine
    if _cross_engine is None:
        _cross_engine = CrossDocumentEngine()
    return _cross_engine


# F6 현실 대조 엔진도 같은 자리 — 카탈로그 파싱과 이벤트 소스 구성을
# 요청마다 반복하지 않는다.
_reality_engine: Optional[RealityEngine] = None


def reality_engine() -> RealityEngine:
    global _reality_engine
    if _reality_engine is None:
        _reality_engine = RealityEngine()
    return _reality_engine


_call_sign_cache: dict[str, str] = {}


def _resolve_call_sign_cached(vessel_name: str) -> Optional[str]:
    # 선명 → 콜사인은 거의 안 바뀐다. 매 /reality/check 요청마다 외부
    # API(선박제원정보)를 다시 부르지 않는다 — 그 API 가 느리거나 잠깐
    # 죽어도 이미 알아낸 배는 계속 조회할 수 있어야 한다.
    #
    # lru_cache가 아니라 직접 dict를 쓰는 이유: lru_cache는 실패(None)도
    # 그대로 캐시한다 — 외부 API가 한 번 순간 장애를 내면 그 배는 프로세스
    # 재시작 전까지 영원히 매칭 불가였다(P1-4). 성공한 결과만 저장한다.
    #
    # 여기 말고 `resolve_call_sign` 자체엔 캐시를 안 건다 — 테스트가
    # 같은 인자를 다른 monkeypatch 로 여러 번 호출하는데, 캐시가 있으면
    # 첫 호출 결과가 프로세스 전체에 눌러앉아 뒤 테스트가 깨진다.
    # ponytail: TTL 없는 무한 캐시 — 실제로 콜사인이 바뀌는 경우가
    # 생기면(개명 등) 프로세스 재시작 전까진 안 반영된다. 문제되면
    # TTL 캐시로 바꿀 것.
    if vessel_name in _call_sign_cache:
        return _call_sign_cache[vessel_name]
    call_sign = resolve_call_sign(vessel_name)
    if call_sign is not None:
        _call_sign_cache[vessel_name] = call_sign
    return call_sign


# 하자 확률 예측기도 1회만 만든다. 모델 파일 로드가 요청 시간에 들어가면
# 첫 요청만 느려지고, 그 편차가 성능 측정을 흐린다.
#
# 모델이 없으면 룰 가중치 합산으로 대체되며 산출 출처가 `rules-v1` 로
# 남는다 — 예외가 아니라 값이 달라지는 실패라서, 그 사실이 응답에 드러나야
# 한다.
_predictor: Optional["DefectPredictor"] = None


def predictor() -> "DefectPredictor":
    global _predictor
    if _predictor is None:
        from f3_model.predictor import DefectPredictor

        _predictor = DefectPredictor(model_path=os.getenv("XGBOOST_MODEL_PATH") or None)
    return _predictor


# /extract* 핸들러마다 IntakePipeline()을 새로 만들면 PaddleOCR 모델을
# 업로드마다 재로드한다(요청당 수 초 고정 비용). engine()/predictor()와
# 같은 이유로 1회만 만들어 재사용한다.
_intake_pipeline: Optional["IntakePipeline"] = None


_intake_lock = threading.Lock()


def intake_pipeline() -> "IntakePipeline":
    global _intake_pipeline
    with _intake_lock:
        if _intake_pipeline is None:
            from f1_intake import IntakePipeline

            _intake_pipeline = IntakePipeline(
                lang=os.getenv("OCR_LANG", "en"),
                use_gpu=(os.getenv("OCR_USE_GPU", "").strip().lower() in {"1", "true", "yes", "on"}),
            )
    return _intake_pipeline


def warm_up_ocr() -> None:
    """OCR 엔진을 XGBoost(libgomp)보다 먼저 올린다. 실패는 로그만 — 첫 요청이 재시도한다."""
    try:
        intake_pipeline().extractor.warm_up()
        print("[ai-service] OCR 워밍업 완료")
    except Exception as exc:  # ImportError 포함: OCR 미설치 환경(테스트)도 통과
        print(f"[ai-service] 경고: OCR 워밍업 건너뜀 — {exc!r}")


# ── F2 표준 용어 교정 — 지연 싱글턴 ─────────────────────────────
#
# `engine()`/`predictor()` 와 같은 자리다: 카탈로그·인덱스가 무거워서
# 기동 시(정확히는 첫 접근 시) 1회만 만들고, 이후 요청은 같은 인스턴스를
# 재사용한다. `Normalizer` 자신은 요청별 가변 상태를 갖지 않는다 —
# `f2_terms/cascade.py:_Run` 이 그 이유를 설명한다: "`Normalizer` 인스턴스에
# 담지 않는 이유: 같은 `Normalizer` 를 여러 요청이 재사용한다(사전·인덱스가
# 무거워 요청마다 만들 수 없다). 인스턴스에 쌓으면 두 번째 요청이 첫 번째
# 요청의 제안을 물려받는다." 즉 요청 1건의 상태는 전부 `normalize()` 호출
# 안에서 만들어지는 지역 `_Run` 에 있고, `Normalizer.stack`/`.selector`/
# `.glossary_version`/`.rules_catalog_version`/`._phrase_cache`(읽기 전용
# 정규식 캐시) 는 전부 배포 설정이지 요청 상태가 아니다 — 동시 요청이 이
# 싱글턴을 공유해도 서로의 결과가 섞이지 않는다(아래 "검증" 절에서 실제로
# 동시 재사용을 확인했다).
_all_glossaries: Optional[Dict[str, Glossary]] = None
_glossary: Optional[Glossary] = None
_selector_resolved = False
_selector = None  # Optional[LLMSelector] — 타입만을 위해 terms.LLMSelector 를 끌어올 이유가 없다
_normalizer: Optional[Normalizer] = None


def all_glossaries() -> Dict[str, Glossary]:
    """카탈로그 디렉터리의 **모든** 버전을 읽어 검증한다.

    기본 버전만 읽으면 과거 버전이 조용히 썩다가, 그 버전을 실제로 요청한
    재현 요청이 들어온 날에야 깨진 사실이 드러난다(`HANDOFF.md` §4.6
    "기동 시 모든 버전을 검증한다"). 깨진 카탈로그는 `GlossaryCatalogError`
    (`ValueError` 하위)를 던지고, `lifespan` 이 이 함수를 부르는 시점에
    잡지 않으므로 예외가 그대로 올라가 **서버가 뜨지 않는다** — 룰
    카탈로그(`engine()`)와 같은 규약이다.

    `GET /glossary` 의 `available_versions`, `/normalize` 의
    `glossary_version` 요청 처리, `glossary()` 의 기본값 선택이 전부 이
    캐시 하나를 공유한다 — 버전마다 YAML 을 다시 읽지 않기 위해서다.
    """
    global _all_glossaries
    if _all_glossaries is None:
        _all_glossaries = load_all_glossaries()
    return _all_glossaries


def glossary() -> Glossary:
    """이 프로세스가 기본으로 쓸 표준 사전 한 버전.

    용어사전도 기동 시 1회만 읽는다. 요청마다 읽으면 YAML 파싱과 n-gram
    인덱스 빌드가 응답 시간에 그대로 들어간다.

    `TERMS_GLOSSARY_VERSION` 이 설정되어 있으면 그 버전을, 없으면
    `effective_date` 가 가장 최신인 버전을 고른다(`glossary.py:
    _pick_latest_version` 과 같은 규칙 — 그 함수는 `__all__` 에 없는
    내부 헬퍼라 여기서 다시 부르지 않고 이미 검증까지 끝난
    `all_glossaries()` 캐시에서 같은 규칙으로 고른다. 두 번 읽지 않기
    위해서다).
    """
    global _glossary
    if _glossary is None:
        catalogs = all_glossaries()
        version = glossary_version_override()
        if version:
            if version not in catalogs:
                # 배포 설정 오류다(TERMS_GLOSSARY_VERSION 이 없는 버전을
                # 가리킴) — 요청 오류가 아니므로 여기서 그냥 던져 기동을
                # 막는다. 조용히 다른 버전으로 대체하면 "설정한 버전으로
                # 판정한다"는 기대가 조용히 깨진다.
                raise GlossaryCatalogError(
                    f"TERMS_GLOSSARY_VERSION='{version}' 인 사전 버전이 "
                    f"카탈로그에 없습니다 (가용: {', '.join(sorted(catalogs)) or '없음'})"
                )
            _glossary = catalogs[version]
        else:
            _glossary = max(
                catalogs.values(), key=lambda g: (g.effective_date, g.catalog_version)
            )
    return _glossary


def selector():
    """⑤단계 선정기. 미설정이면 `None` 이며 그 자체가 정상 경로다.

    `default_selector()` 는 `TERMS_LLM_SELECT` 가 꺼져 있거나(기본값),
    켜져 있어도 LLM 키가 없으면 `None` 을 돌려준다 — 두 경우를 호출부가
    구분해야 `lifespan` 경고("켰는데 키가 없다")를 정확한 경우에만 찍을
    수 있으므로, 여기서는 `llm_select_enabled()` 와 별도로 판단한다.
    한 번만 시도하고 캐시한다 — `LLMSelector._get_completion` 이 이미
    "한 번만 시도"를 규약으로 삼고 있는 것과 같은 이유로, 매 요청마다
    `default_selector()` 를 다시 부르면 매번 프로바이더 생성을 다시
    시도하게 된다.
    """
    global _selector, _selector_resolved
    if not _selector_resolved:
        _selector = default_selector()
        _selector_resolved = True
    return _selector


def normalizer() -> Normalizer:
    """기본 표준 사전 한 계층만 쓰는 캐스케이드. 대다수 요청이 이걸 쓴다."""
    global _normalizer
    if _normalizer is None:
        _normalizer = Normalizer(
            stack=GlossaryStack([glossary()]),
            selector=selector(),
            # F3 룰 카탈로그와 같은 시점의 판정이었음을 사후 대조하기
            # 위한 값이다(`Versions.rules_catalog_version` docstring).
            # 이 서비스는 F3 카탈로그를 항상 갖고 있으므로(engine()) L/C
            # 를 안 태운 요청에도 이 값을 싣는다 — "이 배포가 참조하는
            # F3 카탈로그 버전"이지 "이 요청이 F3 를 호출했다"는 뜻이
            # 아니다.
            rules_catalog_version=engine().fingerprint.version,
        )
    return _normalizer


def normalizer_for(
    glossary_version_req: Optional[str], overrides: Optional[Dict[str, Any]]
) -> Normalizer:
    """요청이 표준 사전 버전을 지정했거나 조직/선적 오버라이드를 실었을 때만
    그 요청 전용 `Normalizer` 를 만든다. 둘 다 없으면 싱글턴 `normalizer()`
    를 그대로 쓴다.

    새로 만든 `Normalizer` 는 이 함수를 부른 요청이 끝나면 버려진다 —
    저장하지 않는다(무상태). `GlossaryStack`/`Normalizer` 생성 자체는
    가볍다(사전 항목을 다시 읽지 않고 이미 로드된 `Glossary` 객체를
    계층으로 쌓기만 한다) — 무거운 건 YAML 파싱과 인덱스 빌드이고, 그건
    `all_glossaries()`/`build_override` 가 이미 끝낸 뒤다.
    """
    if not glossary_version_req and not overrides:
        return normalizer()

    if glossary_version_req:
        catalogs = all_glossaries()
        if glossary_version_req not in catalogs:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"알 수 없는 용어사전 버전입니다: '{glossary_version_req}' "
                    f"(가용: {', '.join(sorted(catalogs)) or '없음'})"
                ),
            )
        base = catalogs[glossary_version_req]
    else:
        base = glossary()

    layers = [base]
    if overrides:
        # {"organization": {...}, "shipment": {...}} — 계층 이름을 키로
        # 받는다. `GlossaryStack` 은 일반→구체 순서를 요구하므로
        # organization 을 shipment 보다 먼저 넣는다.
        for tier in ("organization", "shipment"):
            payload = overrides.get(tier)
            if not payload:
                continue
            try:
                layers.append(build_override(payload, tier=tier))
            except GlossaryCatalogError as exc:
                # 서버를 죽이지 않는다 — 요청 오류다(HANDOFF.md §5).
                raise HTTPException(status_code=400, detail=str(exc)) from exc

    return Normalizer(
        stack=GlossaryStack(layers),
        selector=selector(),
        rules_catalog_version=engine().fingerprint.version,
    )


@asynccontextmanager
async def lifespan(_: FastAPI):
    """기동 시 카탈로그를 검증한다. 룰이 깨졌으면 여기서 죽는 편이 낫다."""
    print(
        f"[ai-service] 룰 카탈로그 로드 완료: {len(engine())}건 "
        f"({engine().fingerprint.label})"
    )
    if engine().fingerprint.version == UNDECLARED_VERSION:
        # rules.yaml 이 version 을 잃어버린 상태다. 다이제스트만으로도
        # 카탈로그는 구분되지만, 사람이 읽는 버전 표기가 사라진다.
        print("[ai-service] 경고: 룰 카탈로그가 version 을 선언하지 않았습니다")
    unverified = engine().unverified_rules()
    if unverified:
        # 기획안 9절 "멘토 기업 실무 검증"의 남은 작업량이다. 발표에서
        # 조문이 틀리면 시스템 전체의 신뢰가 무너지므로 조용히 두지 않는다.
        print(
            f"[ai-service] 경고: 조문 인용 미검증 {len(unverified)}건 "
            f"/ {len(engine())}건 — 실무 검증 필요"
        )
    if os.getenv("OCR_WARMUP", "").strip().lower() in {"1", "true", "yes", "on"}:
        warm_up_ocr()
    # 모델 적재 여부를 기동 시 확정한다. 첫 요청에서 알게 되면, 그때는
    # 이미 rules-v1 로 산출된 응답이 나간 뒤다.
    probe = predictor().predict({}, None, RuleEngine(rules=[
        {"id": "_probe", "title": "probe", "severity": "info",
         "check": "required", "source": "-", "message": "-", "fields": ["bl_no"]}
    ]).verify({}))
    if probe.model == "rules-v1":
        print(
            "[ai-service] 경고: 학습된 하자 예측 모델이 없습니다 — "
            "위험 점수를 룰 가중치로 대체합니다. "
            "학습: python -m f3_model.evaluate --save-model"
        )
    else:
        print(f"[ai-service] 하자 예측 모델 적재: {probe.model}")

    if share_tokens.secret_is_ephemeral():
        # 죽이지는 않는다 — 개발·시연에서는 임시 키로 충분하다. 다만 배포에서
        # 이 줄이 보이면 재시작마다 공유 링크가 끊긴다는 뜻이다.
        print(
            f"[ai-service] 경고: {share_tokens.SECRET_ENV} 미설정 — "
            "공유 링크가 서버 재시작 시 무효가 됩니다."
        )

    # ── F2 표준 용어사전 ─────────────────────────────────────────
    #
    # 모든 버전을 검증한다 — 기본 버전만 확인하면 옛 버전이 조용히
    # 썩다가, 과거 판정을 재현하라는 요청이 들어온 날에야 깨진 사실이
    # 드러난다(`HANDOFF.md` §4.6). 카탈로그가 깨지면 `all_glossaries()`
    # 가 예외를 던지고, 여기서 잡지 않으므로 **서버가 뜨지 않는다** —
    # 룰 카탈로그와 같은 규약이다("조용한 실패는 틀린 답보다 나쁘다").
    all_glossaries()
    g = glossary()
    print(
        f"[ai-service] 용어사전 로드 완료: {g.term_count}건 / "
        f"별칭 {g.alias_count}건 (버전 {g.catalog_version})"
    )
    unverified_terms = g.unverified_count
    if unverified_terms:
        # 표준 표기·별칭을 실무자가 아직 확인하지 않은 항목이다.
        # 기획안 9절 "멘토 기업 실무 검증"의 남은 작업량과 같은 성격이라
        # 룰 카탈로그의 미검증 경고와 같은 문구를 쓴다.
        print(
            f"[ai-service] 경고: 출처 미검증 용어 {unverified_terms}건 "
            f"/ {g.term_count}건 — 실무 검증 필요"
        )

    # ── F6 현실 대조 ────────────────────────────────────────────
    print(
        f"[ai-service] 현실 대조 카탈로그 로드 완료: {len(reality_engine())}건 "
        f"({reality_engine().fingerprint.label}, 소스={reality_engine().source.name})"
    )
    if reality_engine().source.name != "fixture":
        # fixture 는 항상 성공한다. 실 API 로 설정했는데 키가 비어 있으면
        # 첫 요청에서야 503 을 만나는 대신 기동 로그에서 미리 알린다.
        try:
            reality_engine().fetch_records()
        except EventSourceError as exc:
            print(f"[ai-service] 경고: 울산항 VTS 이벤트 소스 확인 실패 — {exc}")
    elif os.getenv("ENV") == "production":
        # 운영인데 REALITY_EVENT_SOURCE 가 fixture 로 남아있으면, 그건
        # env 가 배포 컨테이너에 안 들어갔다는 신호다(설정 실수를 조용히
        # "정상"으로 위장하지 않는다 — 룰/용어사전 검증과 같은 원칙).
        raise RuntimeError(
            "ENV=production 인데 REALITY_EVENT_SOURCE 가 fixture 입니다 — "
            "환경변수가 컨테이너에 전달되지 않았을 가능성이 높습니다"
        )

    if llm_select_enabled() and selector() is None:
        # `TERMS_LLM_SELECT=true` 인데 `default_selector()` 가 `None` 을
        # 냈다 — 키가 없거나(`GEMINI_API_KEY` 미설정) `changeme` 그대로다.
        # 죽이지 않는다: ⑤가 없어도 캐스케이드는 `requires_choice` 로
        # 정상 동작한다(제안이 사라지는 게 아니라 자동 선정만 사라진다).
        # 다만 "켰다고 생각했는데 실제로는 안 켜졌다"는 조용한 실패이므로
        # 기동 로그에서 시끄럽게 알린다.
        print(
            "[ai-service] 경고: TERMS_LLM_SELECT=true 이지만 LLM 이 설정되지 "
            "않았습니다 — F2 ⑤단계는 후보 나열로 떨어집니다."
        )

    yield


# ── 임시 접근 통제 (공유 시크릿 헤더) ──────────────────────────────
#
# 이 서비스는 원래 게이트웨이가 서버끼리 호출하도록 설계됐다(파일 맨
# 위 docstring). 그런데 CORS 절에서 설명한 개발용 임시 상태 — 프론트가
# 브라우저에서 직접 이 서비스를 호출하는 것 — 이 그대로 운영
# docker-compose 에 올라가면서, 인증이 전혀 없는 서비스가 인터넷에
# 노출된다(선하증권·신용장 내용을 그대로 받는 엔드포인트들이다).
#
# 이건 **로그인 인증이 아니다** — 토큰이 프론트 빌드 결과물(JS 번들)에
# 그대로 박혀서 누구나 브라우저 개발자도구로 읽을 수 있다. 그래도 인증
# 없이 무작위로 두드리는 봇·스캐너는 막는다. 진짜 인증은 게이트웨이가
# F1·F3·F4 경로를 중계하게 되는 날 그쪽 책임으로 넘어간다.
AI_INTERNAL_TOKEN = os.getenv("AI_INTERNAL_TOKEN", "")


def _require_internal_token(
    request: Request,
    x_internal_token: Optional[str] = Header(None, alias="X-Internal-Token"),
) -> None:
    if not AI_INTERNAL_TOKEN:
        # 로컬 개발 기본값 — 매번 .env 에 토큰을 채워야 서버가 뜨게 만들
        # 이유가 없다. 운영에서 이 값이 비어 있으면 사실상 무인증이지만,
        # 그건 docker-compose.yml 의 `:?required` 가 막는다.
        return
    if request.url.path == "/health":
        # 컨테이너 헬스체크(docker-compose.yml)가 토큰 없이 스스로를 찌른다.
        return
    if request.url.path.startswith("/report/shared/"):
        # 공유 링크는 "클릭하면 바로 열린다"는 설계다(아래 build_share_link
        # docstring) — 서명된 token 자체가 이미 인증 역할을 하므로
        # X-Internal-Token(프론트 번들에 박힌 값, 외부인은 모름)까지
        # 추가로 요구하면 공유 기능이 아예 동작하지 않는다.
        return
    # 길이 등 타이밍 차이로 정답 토큰을 한 글자씩 추측당하지 않도록 상수 시간 비교(P2-2).
    if not x_internal_token or not hmac.compare_digest(x_internal_token, AI_INTERNAL_TOKEN):
        raise HTTPException(status_code=401, detail="X-Internal-Token 이 유효하지 않습니다.")


app = FastAPI(
    title="B/L Copilot AI Service",
    version="0.1.0",
    description="F1 인테이크 · F3 하자 예측 · F4 리포트",
    lifespan=lifespan,
    dependencies=[Depends(_require_internal_token)],
)


# ── CORS ────────────────────────────────────────────────────────
#
# 브라우저는 이제 게이트웨이만 부른다(ai-service 는 127.0.0.1 바인딩) — 아래 설정은
# 로컬 디버깅용으로만 남겨 둔 것이고 운영 경로에서는 쓰이지 않는다.
# 정상 경로는 게이트웨이(:4000)가 이 서비스를 서버끼리 호출하는 것이고, 거기엔
# CORS 가 필요 없다 — 브라우저가 끼지 않기 때문이다. 그럼에도 여는 이유는
# **개발 중 프론트가 브라우저에서 직접 부르기 때문이다.** 게이트웨이가 F1·F3·F4
# 경로를 아직 중계하지 않는 동안 S3·S4·S7 을 붙여보려면 이 길밖에 없다.
#
# `*` 를 쓰지 않는다. 저장은 안 하지만 이 서비스는 요청 본문으로 선하증권·
# 신용장 내용을 받는다. 아무 출처에서나 부를 수 있게 두면, 사용자가 다른 탭에서
# 연 페이지가 사내망의 이 서비스를 대신 호출하고 응답까지 읽어갈 수 있다.
#
# 허용 목록은 환경변수로 받는다. 배포마다 프론트 주소가 다르고, 그때 코드를
# 고쳐야 한다면 결국 누군가 `*` 로 열어두게 된다.
_DEFAULT_CORS_ORIGINS = "http://localhost:5173,http://127.0.0.1:5173"

_cors_origins = [
    origin.strip()
    for origin in os.getenv("CORS_ALLOW_ORIGINS", _DEFAULT_CORS_ORIGINS).split(",")
    if origin.strip()
]

if _cors_origins:
    from fastapi.middleware.cors import CORSMiddleware

    app.add_middleware(
        CORSMiddleware,
        allow_origins=_cors_origins,
        # 이 서비스는 쿠키·세션을 쓰지 않는다(저장하지 않으므로 로그인도 없다).
        # 켜면 브라우저가 자격증명을 실어 보내는 것을 허용하게 되는데, 얻는 것
        # 없이 공격면만 늘어난다.
        allow_credentials=False,
        # 실제로 여는 것만 적는다. 이 서비스에 DELETE·PUT 은 없다.
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Internal-Token"],
        # `/report/pdf` 의 파일명이 이 헤더에 실린다. 노출하지 않으면 브라우저
        # 스크립트가 읽지 못해 프론트가 파일명을 지어내게 된다.
        expose_headers=["Content-Disposition"],
    )


# ── 요청/응답 모델 ───────────────────────────────────────────────

class VerifyRequest(BaseModel):
    """하자 검증 요청.

    bl 은 F1 이 뽑은 값이든 S3 편집기에서 사람이 고친 값이든 같은 형태로
    받는다. 두 경로를 가르면 '편집 후 재검증'이 다른 코드 경로를 타게 된다.
    """

    bl: Dict[str, Optional[str]] = Field(
        ..., description="B/L 필드. BLFields.to_dict() 와 같은 형태."
    )
    lc: Optional[Dict[str, Any]] = Field(
        None, description="신용장 조건(MT700). 없으면 서류 내부 정합성만 검사."
    )
    as_of: Optional[datetime] = Field(
        None, description="제시기간 계산 기준 시각. 생략하면 현재 시각."
    )


class VerifyResponse(BaseModel):
    shipment_id: Optional[str] = None
    verdict: Dict[str, Any]
    prediction: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "하자 확률(위험도 순위용). 판정 자체는 verdict 가 한다 — "
            "이진 판정은 룰이, 순위는 모델이 낫다는 측정 결과에 따른다."
        ),
    )


# ── 엔드포인트 ───────────────────────────────────────────────────

@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "rules_loaded": len(engine()),
        # 배포된 인스턴스가 어느 카탈로그를 물고 있는지. 같은 입력에 다른
        # 판정이 나올 때 제일 먼저 봐야 하는 값이다.
        "rule_catalog": engine().fingerprint.to_dict(),
        "env": os.getenv("ENV", "development"),
        # F2 — 이 배포가 기본으로 판정에 쓰는 표준 사전. 같은 입력에
        # 다른 제안이 나올 때 `rule_catalog` 와 함께 제일 먼저 봐야 하는
        # 값이다.
        "glossary_version": glossary().catalog_version,
        "glossary_terms": glossary().term_count,
        # F6 — 어느 현실 대조 카탈로그·이벤트 소스를 물고 있는지.
        "reality_catalog": reality_engine().fingerprint.to_dict(),
        "reality_source": reality_engine().source.name,
    }


@app.get("/rules")
def list_rules() -> dict:
    """적재된 룰 목록. S11 설정 화면과 발표 시연에서 쓴다."""
    return {
        "count": len(engine()),
        "catalog": engine().fingerprint.to_dict(),
        # 조문 인용이 실무 검증을 거치지 않은 룰 수. 화면이 이 값을 숨기면
        # 미검증 조문이 검증된 것처럼 인용된다 — 기획안 9절의 리스크다.
        "unverified_source_count": len(engine().unverified_rules()),
        "rules": [
            {
                "id": r["id"],
                "title": r["title"],
                "severity": r["severity"],
                "source": r.get("source", ""),
                "source_verified": r.get("verified") is True,
                "check": r["check"],
            }
            for r in engine().rules
        ],
    }


@app.get("/reality/rules")
def list_reality_rules() -> dict:
    """F6 — 적재된 현실 대조 룰 목록. `/rules` 와 같은 모양이다."""
    return {
        "count": len(reality_engine()),
        "catalog": reality_engine().fingerprint.to_dict(),
        "source": reality_engine().source.name,
        "unverified_source_count": len(reality_engine().unverified_rules()),
        "rules": [
            {
                "id": r["id"],
                "title": r["title"],
                "severity": r["severity"],
                "source": r.get("source", ""),
                "source_verified": r.get("verified") is True,
                "check": r["check"],
            }
            for r in reality_engine().rules
        ],
    }


# ── F1 인테이크 ──────────────────────────────────────────────────

class LabelExtractRequest(BaseModel):
    """라벨 JSON 으로 추출.

    OCR 엔진 없이 파서만 태우는 경로다. PaddleOCR·PaddlePaddle 은 설치가
    무겁고 플랫폼을 타는데, 파서 동작 확인과 시연에는 그게 필요 없다.
    """

    Images: Dict[str, Any] = Field(default_factory=dict, description="이미지 메타")
    bbox: List[Dict[str, Any]] = Field(default_factory=list, description="OCR bbox 목록")


def _draft_response(draft) -> dict:
    return draft.to_dict()


MAX_UPLOAD_BYTES = int(os.getenv("MAX_UPLOAD_BYTES", str(20 * 1024 * 1024)))


async def _read_upload_capped(file: UploadFile, max_bytes: Optional[int] = None) -> bytes:
    """업로드를 max_bytes까지만 읽는다.

    `UploadFile.read()`를 크기 없이 부르면 파일 전체를 메모리에 올린다 — 큰
    파일을 계속 올리는 것만으로 서버 메모리를 고갈시킬 수 있다. `read(n)`으로
    상한+1바이트만 읽어, 실제로 그 이상 읽지 않고 바로 거절한다.

    `max_bytes`는 기본 인자가 아니라 호출 시점에 모듈 전역값을 읽는다 —
    기본 인자로 두면 정의 시점 값에 고정되어, 테스트가 `MAX_UPLOAD_BYTES`를
    바꿔도 반영되지 않는다.
    """
    if max_bytes is None:
        max_bytes = MAX_UPLOAD_BYTES
    payload = await file.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다 (최대 {max_bytes // (1024 * 1024)}MB).",
        )
    return payload


def _read_upload_capped_sync(file: UploadFile, max_bytes: Optional[int] = None) -> bytes:
    """`_read_upload_capped`의 동기 버전.

    OCR을 태우는 핸들러(`/extract*`)는 `def`(동기)라야 FastAPI 스레드풀에서
    돌아 이벤트 루프를 막지 않는다 — 그 안에서는 `await`를 쓸 수 없으므로
    `UploadFile.file`(내부 SpooledTemporaryFile)을 직접 동기로 읽는다.
    """
    if max_bytes is None:
        max_bytes = MAX_UPLOAD_BYTES
    payload = file.file.read(max_bytes + 1)
    if len(payload) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=f"파일이 너무 큽니다 (최대 {max_bytes // (1024 * 1024)}MB).",
        )
    return payload


@app.post("/extract/label")
def extract_from_label(req: LabelExtractRequest) -> dict:
    """F1 — 라벨 JSON → B/L 초안. 기획안 S3(초안 편집기)가 이 응답을 그린다."""
    import json
    import tempfile
    from pathlib import Path

    if not req.bbox:
        raise HTTPException(status_code=400, detail="bbox 가 비어 있습니다.")

    # 추출기가 경로를 받는 구조라 임시 파일을 거친다. 요청 본문을 그대로
    # 파서에 넣는 오버로드를 두면 두 입력 경로가 갈려 유지보수가 늘어난다.
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "label.json"
        path.write_text(
            json.dumps({"Images": req.Images, "bbox": req.bbox}, ensure_ascii=False),
            encoding="utf-8",
        )
        draft = intake_pipeline().run_from_json(str(path))

    return _draft_response(draft)


@app.post("/extract")
def extract_from_image(file: UploadFile = File(...)) -> dict:
    """F1 — 이미지 → B/L 초안. PaddleOCR 이 필요하다."""
    import tempfile
    from pathlib import Path

    suffix = Path(file.filename or "upload.png").suffix or ".png"
    payload = _read_upload_capped_sync(file)
    if not payload:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / f"upload{suffix}"
        path.write_bytes(payload)
        try:
            draft = intake_pipeline().run_from_image(str(path))
        except ImportError as exc:
            # OCR 엔진 미설치는 서버 구성 문제지 요청 오류가 아니다.
            # 500 으로 흘리면 게이트웨이가 무의미하게 재시도한다.
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _draft_response(draft)


@app.post("/extract/pdf")
def extract_from_pdf(
    file: UploadFile = File(...),
    page: int = 0,
) -> dict:
    """F1 — PDF → B/L 초안.

    텍스트 레이어가 있는 PDF(전자 발행 서류 대부분)는 **OCR 을 타지 않는다.**
    스캔본만 이미지로 구워 OCR 에 넘기므로, 그때만 PaddleOCR 이 필요하다.
    어느 경로였는지는 응답의 `source` 에 `pdf-text` / `pdf-ocr` 로 남는다.
    """
    import tempfile
    from pathlib import Path

    payload = _read_upload_capped_sync(file)
    if not payload:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if not payload.startswith(b"%PDF"):
        # 확장자가 아니라 내용으로 판정한다. 이미지 파일을 .pdf 로 바꿔
        # 올리는 일이 흔하고, 그때 PyMuPDF 오류를 그대로 흘리면 원인을
        # 알 수 없는 500 이 된다.
        raise HTTPException(
            status_code=400,
            detail="PDF 파일이 아닙니다. 이미지는 /extract 를 쓰세요.",
        )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.pdf"
        path.write_bytes(payload)
        try:
            draft = intake_pipeline().run_from_pdf(str(path), page_number=page)
        except ValueError as exc:
            # 페이지 번호 범위 초과·빈 PDF — 요청이 잘못된 경우다.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ImportError as exc:
            # PyMuPDF 미설치, 또는 스캔본인데 PaddleOCR 미설치.
            # 서버 구성 문제지 요청 오류가 아니다.
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _draft_response(draft)


@app.post("/extract/excel")
def extract_from_excel(
    file: UploadFile = File(...),
    sheet: Optional[str] = None,
) -> dict:
    """F1 — 엑셀 → B/L 초안. OCR 을 타지 않는다.

    sheet 를 주지 않으면 값이 가장 많은 시트를 고른다. 첫 시트를 쓰면
    표지·안내 시트가 앞에 있는 파일에서 빈 결과가 나온다.
    """
    import tempfile
    from pathlib import Path

    payload = _read_upload_capped_sync(file)
    if not payload:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")
    if not payload.startswith(b"PK"):
        # xlsx 는 zip 컨테이너다. 확장자가 아니라 내용으로 판정한다.
        # 구형 .xls(OLE2)나 CSV 를 올리면 여기서 걸리는데, openpyxl 오류를
        # 그대로 흘리는 것보다 무엇이 잘못됐는지 알려주는 편이 낫다.
        raise HTTPException(
            status_code=400,
            detail="xlsx 파일이 아닙니다. 구형 .xls 는 xlsx 로 변환해 주세요.",
        )

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.xlsx"
        path.write_bytes(payload)
        try:
            draft = intake_pipeline().run_from_excel(str(path), sheet=sheet)
        except ValueError as exc:
            # 값이 없는 시트·없는 시트명 — 요청이 잘못된 경우다.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ImportError as exc:
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _draft_response(draft)


@app.post("/extract/email")
def extract_from_email(file: UploadFile = File(...)) -> dict:
    """F1 — 이메일(.eml) → B/L 초안.

    **첨부를 먼저 본다.** 본문은 대개 안내문이고 첨부가 서류이므로, 본문부터
    읽으면 선하증권 대신 인사말을 파싱한다. 지원 첨부가 없을 때만 본문을 읽는다.

    응답의 `source` 가 어느 경로였는지 알린다 — `email-pdf` / `email-excel` /
    `email-image` / `email-body`. 본문에서 뽑은 값과 첨부 원본에서 뽑은 값은
    신뢰 수준이 다르다.
    """
    import tempfile
    from pathlib import Path

    payload = _read_upload_capped_sync(file)
    if not payload:
        raise HTTPException(status_code=400, detail="빈 파일입니다.")

    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "upload.eml"
        path.write_bytes(payload)
        try:
            draft = intake_pipeline().run_from_email(str(path))
        except ValueError as exc:
            # 본문도 비었고 읽을 첨부도 없는 경우.
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except ImportError as exc:
            # 첨부가 스캔 이미지인데 PaddleOCR 이 없는 경우 등.
            raise HTTPException(status_code=503, detail=str(exc)) from exc

    return _draft_response(draft)


# ── L/C 인테이크 ─────────────────────────────────────────────────

class MT700Request(BaseModel):
    """MT700 전문 원문.

    파일 업로드가 아니라 텍스트로 받는다. SWIFT 전문은 텍스트이고, 파일로
    받으면 인코딩 추측이 한 겹 더 붙는다 — 그 추측이 틀리면 태그는 읽히는데
    상호·품명만 깨지고, 그 상태로도 검증이 돌아 버린다.
    """

    text: str = Field(..., description="MT700 전문 원문. 블록 구조({4:...-})가 있어도 된다.")


@app.post("/lc/mt700")
def parse_lc_mt700(req: MT700Request) -> dict:
    """MT700 원문 → L/C 조건(기획안 v2 5.1 입력 사양).

    `/verify` 의 `lc` 에 그대로 실을 수 있는 형태로 돌려준다. 이 경로를
    `/extract/*` 에 두지 않은 이유는 응답이 다르기 때문이다 — 추출 경로는
    전부 B/L 초안을 내는데 이건 L/C 조건을 낸다. 같은 접두어에 다른 응답을
    섞으면 S3 편집기가 경로마다 분기해야 한다.

    응답의 `notes` 와 `unmapped` 를 화면이 버리지 말 것. L/C 조건이 비면
    그 조건을 쓰는 룰은 평가불가로 빠지고, **위반 0건은 '하자 없음'으로
    읽힌다.** 무엇을 못 읽었는지가 결과만큼 중요하다.
    """
    from f3_rules import MT700ParseError, parse_mt700

    try:
        parsed = parse_mt700(req.text)
    except MT700ParseError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return parsed.to_dict()


@app.post("/verify", response_model=VerifyResponse)
def verify(req: VerifyRequest) -> VerifyResponse:
    """F3 하자 예측. 기획안 S4(검증 결과) 화면이 이 응답을 그대로 그린다."""
    if not req.bl:
        raise HTTPException(status_code=400, detail="bl 필드가 비어 있습니다.")

    lc = LCTerms.from_dict(req.lc) if req.lc else None

    try:
        verdict = engine().verify(req.bl, lc, as_of=req.as_of)
    except TypeError as exc:
        # 입력 형 오류는 400 이다. 500 으로 흘리면 게이트웨이가 재시도한다.
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    return VerifyResponse(
        shipment_id=req.bl.get("bl_no"),
        verdict=verdict.to_dict(),
        prediction=_predict(req.bl, lc, verdict, req.as_of).to_dict(),
    )


def _predict(bl, lc, verdict, as_of):
    """하자 확률. 예측이 실패해도 검증 결과는 돌려준다.

    모델은 부가 축이다. 여기서 터져 500 을 내면, 룰엔진이 정상적으로 낸
    하자 목록까지 함께 잃는다.
    """
    try:
        return predictor().predict(bl, lc, verdict, as_of)
    except Exception as exc:  # noqa: BLE001
        print(f"[ai-service] 경고: 하자 확률 예측 실패 — {exc}")
        from f3_model.predictor import Prediction

        return Prediction(
            probability=verdict.defect_probability,
            model="rules-v1",
            is_defect=verdict.has_critical,
            threshold=0.5,
        )


# ── F6 통관·운송 현실 대조 ───────────────────────────────────────

class RealityCheckRequest(BaseModel):
    """F6 현실 대조 요청.

    `call_sign` 을 주면 그것만 쓴다(가장 신뢰할 수 있는 키). 없으면
    `bl.vessel` 선명으로 매칭한다 — 매칭 실패는 오류가 아니라 정상
    응답(`match.matched=false`)이다(design doc §6).
    """

    bl: Dict[str, Optional[str]] = Field(
        ..., description="B/L 필드. vessel/port_of_loading/port_of_discharge/on_board_date 를 본다."
    )
    call_sign: Optional[str] = Field(None, description="선박 콜사인. 있으면 선명 매칭보다 우선한다.")
    as_of: Optional[datetime] = Field(None, description="매칭 기준 시각. 생략하면 bl.on_board_date.")
    events: Optional[List[Dict[str, Any]]] = Field(
        None,
        description=(
            "재현·폐쇄망 환경에서 실시간 소스 대신 쓸 원시 관제 레코드. "
            "생략하면 설정된 이벤트 소스(REALITY_EVENT_SOURCE)에서 가져온다."
        ),
    )


class RealityCheckResponse(BaseModel):
    shipment_id: Optional[str] = None
    source: Dict[str, Any]
    match: Dict[str, Any]
    verdict: Dict[str, Any]
    # 타임라인용 항차 이벤트와, 게이트웨이가 항차를 중복 제거할 때 쓰는 그룹 키.
    events: List[Dict[str, Any]] = []
    voyage: Optional[Dict[str, str]] = None  # {call_sign, year, voyage_no}


@app.post("/reality/check", response_model=RealityCheckResponse)
def reality_check(req: RealityCheckRequest) -> RealityCheckResponse:
    """F6 — 서류를 울산항 관제 기록과 대조한다.

    매칭 실패(`match.matched=false`)도 200 이다 — 이 데이터로 판정할 수
    없다는 것 자체가 유효한 결과이고, `verdict.skipped` 에 전부 남는다.
    """
    if not req.bl:
        raise HTTPException(status_code=400, detail="bl 필드가 비어 있습니다.")

    call_sign = req.call_sign

    if req.events is not None:
        records = req.events
        adapter_name = "request"
    else:
        if not call_sign and reality_engine().source.name != "fixture":
            # 콜사인이 없으면 실 API 는 애초에 호출할 수 없다(EventSourceError
            # 사유). 그래서 fetch 전에 선명 → 콜사인 역방향 조회를 먼저
            # 시도한다. 이것도 실패하면 네트워크를 타지 않고 그냥 0건으로
            # 떨어뜨린다 — 매칭 불가는 오류가 아니라 정상 결과다(design
            # doc §6).
            from f3_rules.checks import field_value

            vessel_name = field_value(req.bl, "vessel")
            if vessel_name:
                call_sign = _resolve_call_sign_cached(vessel_name)

        if not call_sign and reality_engine().source.name != "fixture":
            records = []
        else:
            try:
                records = reality_engine().fetch_records(
                    req.bl, call_sign=call_sign, as_of=req.as_of
                )
            except EventSourceError as exc:
                # 소스 설정·호출 실패는 서버 구성 문제다. 빈 목록으로 조용히
                # 떨어지면 '경보 없음'으로 읽힌다(design doc §1) — 그래서 503.
                raise HTTPException(status_code=503, detail=str(exc)) from exc
        adapter_name = reality_engine().source.name

    from f3_rules import RuleCatalogError

    try:
        match, verdict = reality_engine().check(
            req.bl, records, call_sign=call_sign, as_of=req.as_of
        )
    except RuleCatalogError as exc:
        # 레코드 정규화 실패 — 소스 데이터 형식 문제지 요청 오류가 아니다.
        raise HTTPException(status_code=503, detail=str(exc)) from exc

    return RealityCheckResponse(
        shipment_id=req.bl.get("bl_no"),
        source={
            "adapter": adapter_name,
            "port": "울산",
            "records": len(records),
            "fetched_at": datetime.now().isoformat(),
        },
        match=match.to_dict(),
        verdict=verdict.to_dict(),
        events=[e.to_dict() for e in match.voyage.events] if match.voyage else [],
        voyage=(
            {
                "call_sign": match.voyage.call_sign,
                "year": match.voyage.year,
                "voyage_no": match.voyage.voyage_no,
            }
            if match.voyage
            else None
        ),
    )


class ReportRequest(VerifyRequest):
    """F4 리포트 요청. 검증 입력에 제출 서류 목록만 더한다."""

    submitted_documents: Optional[List[str]] = Field(
        None, description="실제 제출한 서류명. 신용장 46A 와 대조해 누락을 찾는다."
    )


def _make_report(req: "ReportRequest", narrator=None):
    """검증 → 리포트 조립 → 요약. /report 와 /report/pdf 가 공유한다."""
    if not req.bl:
        raise HTTPException(status_code=400, detail="bl 필드가 비어 있습니다.")

    lc = LCTerms.from_dict(req.lc) if req.lc else None
    try:
        verdict = engine().verify(req.bl, lc, as_of=req.as_of)
    except TypeError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    report = build_report(
        verdict, req.bl, lc,
        submitted_documents=req.submitted_documents,
        as_of=req.as_of,
        prediction=_predict(req.bl, lc, verdict, req.as_of),
    )
    return apply_narrative(report, narrator)


@app.post("/report")
def report_json(req: ReportRequest) -> dict:
    """리포트 JSON. 기획안 S7(선제 대응 리포트) 미리보기가 이걸 그린다."""
    return _make_report(req).to_dict()


@app.post("/report/pdf")
def report_pdf(req: ReportRequest) -> Response:
    """리포트 PDF. 기획안 5.2 'PDF 로 저장·공유'."""
    return _pdf_response(_make_report(req), inline=False)


def _pdf_response(report, inline: bool) -> Response:
    """PDF 응답. 공유 링크는 브라우저에서 바로 열려야 하므로 inline 이다."""
    disposition = "inline" if inline else "attachment"
    # bl_no는 사용자 입력이라 헤더 인젝션/경로 조작을 막기 위해 안전한 문자만 남긴다(P2-3).
    safe_bl_no = re.sub(r"[^A-Za-z0-9._-]", "_", report.bl_no or "draft") or "draft"
    filename = f"BL_Copilot_Report_{safe_bl_no}.pdf"
    return Response(
        content=render_pdf(report),
        media_type="application/pdf",
        headers={"Content-Disposition": f'{disposition}; filename="{filename}"'},
    )


# ── F4 공유 ──────────────────────────────────────────────────────

class ShareRequest(ReportRequest):
    """공유 링크 발급 요청. 리포트 요청에 만료만 더한다."""

    ttl_seconds: Optional[int] = Field(
        None,
        ge=60,
        le=90 * 24 * 60 * 60,
        description="링크 유효기간(초). 생략하면 7일.",
    )


class ShareResponse(BaseModel):
    token: str
    path: str
    pdf_path: str
    expires_at: datetime
    ephemeral_secret: bool = Field(
        ...,
        description=(
            "True 면 서버 재시작 시 링크가 무효가 된다. "
            "REPORT_SHARE_SECRET 를 설정하면 False."
        ),
    )
    warning: Optional[str] = None


@app.post("/report/share", response_model=ShareResponse)
def create_share_link(req: ShareRequest) -> ShareResponse:
    """F4 — 리포트 공유 링크 발급. 기획안 5절 "PDF 출력·공유 가능".

    저장하지 않는다. 링크가 입력을 싣고 다니며, 열릴 때마다 같은 리포트를
    다시 조립한다. 설계 근거와 한계는 `f4_report/share.py` 를 볼 것.
    """
    # 발급 시점에 한 번 조립해 본다. 열어 봐야 400 이 나는 링크를 쥐여주면
    # 공유받은 쪽에서 터지고, 그때는 원인을 알 방법이 없다.
    _make_report(req)

    payload = {
        "bl": req.bl,
        "lc": req.lc,
        "as_of": req.as_of.isoformat() if req.as_of else None,
        "submitted_documents": req.submitted_documents,
    }
    try:
        token = share_tokens.encode(
            payload, ttl_seconds=req.ttl_seconds or DEFAULT_TTL_SECONDS
        )
    except ShareTokenTooLarge as exc:
        raise HTTPException(status_code=413, detail=str(exc)) from exc

    ephemeral = share_tokens.secret_is_ephemeral()
    return ShareResponse(
        token=token,
        path=f"/report/shared/{token}",
        pdf_path=f"/report/shared/{token}/pdf",
        expires_at=datetime.fromtimestamp(share_tokens.expires_at(token)),
        ephemeral_secret=ephemeral,
        warning=(
            f"{share_tokens.SECRET_ENV} 가 설정되지 않아 서버 재시작 시 "
            "링크가 무효가 됩니다."
            if ephemeral else None
        ),
    )


def _report_from_token(token: str):
    """토큰 → 리포트. 공유 경로 두 개가 공유한다."""
    try:
        payload = share_tokens.decode(token)
    except ExpiredShareToken as exc:
        # 410 이다. 404 로 내면 받은 쪽이 '주소가 틀렸나'를 의심하게 된다.
        raise HTTPException(status_code=410, detail=str(exc)) from exc
    except ShareTokenError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

    as_of = payload.get("as_of")
    # 공유 링크는 열 때마다 리포트를 새로 조립한다 — LLM 요약까지 매번 동기로
    # 부르면 열람 한 번에 최대 20초 침묵이 생긴다(P1-9). 발급 시점(create_share_link)
    # 에는 이미 LLM 요약을 한 번 만들어 봤으니, 열람 경로는 항상 템플릿 요약을 쓴다.
    return _make_report(
        ReportRequest(
            bl=payload["bl"],
            lc=payload.get("lc"),
            as_of=datetime.fromisoformat(as_of) if as_of else None,
            submitted_documents=payload.get("submitted_documents"),
        ),
        narrator=TemplateNarrator(),
    )


@app.get("/report/shared/{token}")
def read_shared_report(token: str) -> dict:
    """공유된 리포트 JSON."""
    return _report_from_token(token).to_dict()


@app.get("/report/shared/{token}/pdf")
def read_shared_report_pdf(token: str) -> Response:
    """공유된 리포트 PDF. 링크를 클릭하면 브라우저에서 바로 열린다."""
    return _pdf_response(_report_from_token(token), inline=True)


# ── F2 표준 용어 교정 ────────────────────────────────────────────
#
# `docs/f2/HANDOFF.md` §5(API 표면)·§6.3(배선), `docs/ai-service/
# f2-standard-terms.md` §무상태의 한계의 구현이다. 평면 라우트를
# 유지한다 — 기존 라우트가 전부 평면(`/verify`·`/report`·`/rules`·
# `/lc/mt700`)이고 `/api/v1` 프리픽스와 이미 어긋나 있으므로, F2 만
# 프리픽스를 붙이면 같은 서비스에 두 규약이 생긴다. 프리픽스는
# 게이트웨이가 정한다.


class DocumentIn(BaseModel):
    """서류 1건. `/normalize`·`/normalize/apply` 가 공유하는 형태다."""

    doc: str = Field("선하증권", description="서류 종류(예: 선하증권·상업송장·포장명세서).")
    doc_id: Optional[str] = Field(
        None,
        description=(
            "게이트웨이가 붙인 서류 식별자. 같은 종류 서류가 한 요청에 "
            "둘 이상 실릴 수 있어(예: 선하증권 2장) 구분에 쓴다."
        ),
    )
    fields: Dict[str, Optional[str]] = Field(
        default_factory=dict,
        description="필드명 → 값. 값이 null 이면 '추출 실패'로 보고 판정 대상에서 뺀다.",
    )


class NormalizeRequest(BaseModel):
    """`POST /normalize` 요청."""

    bl: Optional[Dict[str, Optional[str]]] = Field(
        None,
        description=(
            "B/L 필드. `/verify`·`/report` 와 같은 입력 형태다 — 서류 1장뿐일 "
            "때는 이걸로 보내면 '선하증권 1장'으로 해석한다. `documents` 가 "
            "함께 오면 `documents` 를 우선한다."
        ),
    )
    documents: Optional[List[DocumentIn]] = Field(
        None, description="서류 여러 장. `bl` 과 `documents` 중 하나는 있어야 한다."
    )
    lc: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "신용장 조건(MT700 파싱 결과). 값이 있는 필드는 사전 기반 교정을 "
            "건너뛰고 L/C 문언 우선 안내로 대체한다(F3 의 match_place 와 같은 "
            "자리에 두 판단이 모순되지 않도록)."
        ),
    )
    lc_raw_tags: Optional[Dict[str, str]] = Field(
        None,
        description=(
            "MT700 태그 원문 dict. `lc` 가 없을 때만 이걸로 L/C 조건을 만든다 "
            "— `/lc/mt700` 과 같은 파서를 탄다."
        ),
    )
    overrides: Optional[Dict[str, Any]] = Field(
        None,
        description=(
            "조직/선적 사전 오버라이드. "
            '`{"organization": {...}, "shipment": {...}}` 형태이고, 각 값은 '
            "`POST /glossary/validate` 가 검증하는 것과 같은 payload 다."
        ),
    )
    glossary_version: Optional[str] = Field(
        None,
        description=(
            "이 요청에만 쓸 표준 사전 버전. 생략하면 기동 시 고른 기본 버전을 "
            "쓴다. 없는 버전을 주면 400 이고, 가용 버전 목록이 detail 에 실린다."
        ),
    )
    llm: Optional[bool] = Field(
        None,
        description=(
            "⑤단계(LLM 후보 선정)를 이 요청에서 태울지. `TERMS_LLM_SELECT` 가 "
            "꺼져 있거나 LLM 이 설정되지 않았으면 true 를 줘도 효과가 없다 "
            "— 결정론 제안은 그대로 나가고 ④ 후보는 사람이 직접 고른다."
        ),
    )


def _documents_from_request(req: NormalizeRequest) -> List[DocumentInput]:
    """`documents` 가 있으면 그것을, 없고 `bl` 만 있으면 '선하증권 1장'으로
    해석한다(`api.md` "입력 형태" 규약 — `/verify`·`/report` 와 같은 판단).
    """
    if req.documents:
        return [
            DocumentInput(doc=d.doc, fields=dict(d.fields), doc_id=d.doc_id)
            for d in req.documents
        ]
    if req.bl:
        return [DocumentInput(doc="선하증권", fields=dict(req.bl))]
    return []


@app.post("/normalize")
def normalize(req: NormalizeRequest) -> dict:
    """F2 — 서류 필드 → 교정 제안. 기획안 S3 초안 편집기가 이 응답을 그린다.

    **LLM 실패도 200 이다.** ⑤ 가 실패해도 결정론 제안(①②③④)은 그대로
    나가고, `stats.llm_path` 가 `"failed"` 로 그 사실을 알린다 —
    선정기가 뭘 잘못했다고 요청 전체를 500 으로 내리면 이미 확정된 제안
    까지 함께 잃는다(`/verify` 의 `prediction` 실패 처리와 같은 논거).
    """
    documents = _documents_from_request(req)
    if not documents:
        raise HTTPException(
            status_code=400, detail="documents 와 bl 이 모두 비어 있습니다. 둘 중 하나는 있어야 합니다."
        )

    lc = LCTerms.from_dict(req.lc) if req.lc else None

    norm = normalizer_for(req.glossary_version, req.overrides)
    result = norm.normalize(documents, lc=lc, lc_raw_tags=req.lc_raw_tags, llm=bool(req.llm))
    return result.to_dict()


class FieldRefIn(BaseModel):
    """`Suggestion.field`/`impact` 1건. `/normalize` 응답을 그대로 되쏜다."""

    doc: str = Field(..., description="서류 종류.")
    field: str = Field(..., description="필드명.")
    doc_id: Optional[str] = Field(None, description="서류 식별자.")
    span: Optional[Tuple[int, int]] = Field(
        None,
        description="값 문자열 안의 조각 오프셋 (start, end). 필드 전체를 가리키면 생략.",
    )


class EvidenceIn(BaseModel):
    """`Suggestion.evidence` 1건."""

    authority: str = Field(..., description="근거 출처(UN/LOCODE·ISBP 745·조직 사전 등).")
    term_id: Optional[str] = Field(None, description="사전 항목 id.")
    glossary_version: str = Field(..., description="이 제안을 만든 사전 버전.")
    tier: str = Field(..., description="표준/조직/선적 중 어느 계층이 답했는지.")
    stage: str = Field(..., description="확정 단계(format|exact|alias|pattern|similarity|llm).")
    verified: bool = Field(False, description="표준 표기·별칭을 실무자가 확인했는지.")
    diverges_from_standard: Optional[str] = Field(
        None, description="하위 계층이 표준과 다른 값으로 덮어썼을 때 표준 쪽 값."
    )


class CandidateIn(BaseModel):
    """`Suggestion.candidates` 1건. `requires_choice=true` 일 때만 있다."""

    to_be: str = Field(..., description="후보 표준 표기.")
    term_id: Optional[str] = Field(None, description="사전 항목 id.")
    authority: str = Field(..., description="근거 출처.")
    score: float = Field(..., description="후보 점수(④유사도·⑤LLM 단계 산출).")
    reason: str = Field("", description="후보 선정 근거 부연.")


class SuggestionIn(BaseModel):
    """`/normalize` 응답의 제안 카드 1건을 그대로 되쏜다.

    `/normalize/apply`·`/normalize/reject` 가 공유한다 — 게이트웨이는
    화면에서 승인/거절된 카드를 그대로 body 에 실어 보내면 된다. 서버는
    `suggestion_id` 를 재료에서 재파생해 변조/사전 버전 불일치를 대조한다
    (`terms.verify_suggestion_id`).
    """

    suggestion_id: str = Field(..., description="제안 id. 서버가 재파생해 대조한다.")
    field: FieldRefIn = Field(..., description="교정 대상 자리.")
    as_is: str = Field(..., description="원래 값(또는 그 자리의 부분 문자열).")
    to_be: Optional[str] = Field(
        None,
        description=(
            "교정될 값. `requires_choice=true` 였던 제안은 사람이 `candidates` "
            "중 하나를 골라 채운 값을 여기 넣어 보낸다."
        ),
    )
    term_class: str = Field(..., description="용어 클래스(port·party_suffix 등).")
    evidence: EvidenceIn = Field(..., description="근거.")
    confidence: float = Field(..., description="신뢰도.")
    impact: List[FieldRefIn] = Field(
        default_factory=list,
        description="같은 값이 쓰인 다른 자리. scope='all' 일 때 함께 적용을 시도한다.",
    )
    candidates: List[CandidateIn] = Field(
        default_factory=list, description="`requires_choice=true` 일 때의 후보 목록."
    )
    requires_choice: bool = Field(
        False, description="사람이 후보 중 하나를 고르지 않으면 적용할 수 없는 제안인지."
    )
    message: str = Field("", description="화면에 보여줄 설명 문구.")


def _field_ref_from_in(f: FieldRefIn) -> FieldRef:
    return FieldRef(doc=f.doc, field=f.field, doc_id=f.doc_id, span=f.span)


def _suggestion_from_in(s: SuggestionIn) -> Suggestion:
    """`SuggestionIn` → 도메인 `Suggestion`.

    `f2_terms/types.py` 에 `Suggestion.from_dict` 가 없어(그 파일은 고치지
    않는다 — 지시사항) 여기서 변환한다. `/normalize` 가 낸 `to_dict()` 의
    반대 방향이며, 필드를 하나라도 빠뜨리면 `suggestion_id` 재파생이
    조용히 다른 값을 내 정상 제안이 변조로 오판된다 — 그래서 `Suggestion`/
    `Evidence`/`Candidate`/`FieldRef` 의 모든 필드를 1:1로 옮긴다.
    """
    return Suggestion(
        suggestion_id=s.suggestion_id,
        field=_field_ref_from_in(s.field),
        as_is=s.as_is,
        to_be=s.to_be,
        term_class=s.term_class,
        evidence=Evidence(
            authority=s.evidence.authority,
            term_id=s.evidence.term_id,
            glossary_version=s.evidence.glossary_version,
            tier=s.evidence.tier,
            stage=s.evidence.stage,
            verified=s.evidence.verified,
            diverges_from_standard=s.evidence.diverges_from_standard,
        ),
        confidence=s.confidence,
        impact=[_field_ref_from_in(f) for f in s.impact],
        candidates=[
            Candidate(
                to_be=c.to_be, term_id=c.term_id, authority=c.authority,
                score=c.score, reason=c.reason,
            )
            for c in s.candidates
        ],
        requires_choice=s.requires_choice,
        message=s.message,
    )


class ApplyRequest(BaseModel):
    """`POST /normalize/apply` 요청."""

    documents: List[DocumentIn] = Field(
        ..., description="적용 대상 서류 목록. `/normalize` 요청과 같은 `documents` 형태."
    )
    suggestions: List[SuggestionIn] = Field(
        ..., description="승인된 제안 목록. `/normalize` 응답의 항목을 그대로 되쏜다."
    )
    scope: str = Field(
        "field",
        pattern="^(field|all)$",
        description=(
            "'field' 는 제안이 가리키는 자리 하나만 적용한다. 'all' 은 그 자리 "
            "+ `impact` 에 실린 자리까지 함께 적용한다(같은 값이 쓰인 다른 곳)."
        ),
    )
    decided_by: str = Field(..., description="승인자 식별자. `Correction.decided_by` 에 실린다.")
    decided_at: datetime = Field(
        ..., description="승인 시각. 서버가 만들지 않고 요청이 싣는다(재현성 — `Correction` docstring)."
    )


@app.post("/normalize/apply")
def normalize_apply(req: ApplyRequest) -> dict:
    """F2 — 승인된 제안을 서류에 반영한다. 순수 함수, 아무것도 저장하지 않는다.

    **400 판단 기준 — "하나라도 변조"가 아니라 "전부 변조"일 때만 요청
    전체를 400 으로 내린다.** `apply_suggestions` 는 제안 단위로 변조를
    검사하므로, 요청에 실린 제안 중 일부만 `suggestion_id` 가 어긋나도
    **다른 제안은 정상 적용됐을 수 있다.** 거기서 요청 전체를 400 으로
    내리면 이미 성공한 적용까지 클라이언트가 못 받게 되고, 게이트웨이는
    "아무것도 안 됐다"고 오해한다. 반대로 **요청에 실린 모든 제안이
    변조**라면 이 배치에서 신뢰할 수 있는 것이 하나도 없다는 뜻이고,
    이는 대개 사전 버전이 바뀐 뒤 옛 배치를 그대로 재전송한 경우다
    (`HANDOFF.md` §4.7 "사전을 올리면 id 가 전부 바뀐다") — 이때는
    `unapplied` 목록을 만들 필요도 없이 400 하나로 충분하다. 그래서
    `apply_suggestions` 를 부르기 **전에** `verify_suggestion_id` 로
    전수 검사부터 한다: 하나라도 통과하면 정상 경로(200 + `unapplied`)로
    보내고, 전부 실패해야만 여기서 짧게 끊는다.
    """
    documents = [
        DocumentInput(doc=d.doc, fields=dict(d.fields), doc_id=d.doc_id) for d in req.documents
    ]
    suggestions = [_suggestion_from_in(s) for s in req.suggestions]

    if suggestions and all(not verify_suggestion_id(s) for s in suggestions):
        raise HTTPException(status_code=400, detail="제안이 변조되었거나 사전 버전이 다릅니다")

    outcome = apply_suggestions(
        documents, suggestions, scope=req.scope, decided_by=req.decided_by, decided_at=req.decided_at
    )
    return {
        # `DocumentInput` 은 `f2_terms/types.py` 의 응답 dataclass 가 아니라
        # `cascade.py` 의 입력 dataclass라 `to_dict()` 가 없다 — 손으로 편다.
        "documents": [
            {"doc": d.doc, "doc_id": d.doc_id, "fields": d.fields} for d in outcome.documents
        ],
        "corrections": [c.to_dict() for c in outcome.corrections],
        "unapplied": outcome.unapplied,
    }


class RejectRequest(BaseModel):
    """`POST /normalize/reject` 요청."""

    suggestions: List[SuggestionIn] = Field(
        ..., description="거절할 제안 목록. `/normalize` 응답 항목을 그대로 되쏜다."
    )
    reason: str = Field(
        ...,
        pattern="^(in_house|counterparty|false_positive|other)$",
        description=(
            "거절 사유. in_house=사내 관행이 다르다 · counterparty=거래상대방 "
            "요청 · false_positive=오탐 · other=기타."
        ),
    )
    note: str = Field("", description="자유서식 부연.")
    decided_by: str = Field(..., description="거절 결정자 식별자.")
    decided_at: datetime = Field(
        ..., description="거절 시각. 서버가 만들지 않고 요청이 싣는다."
    )


@app.post("/normalize/reject")
def normalize_reject(req: RejectRequest) -> dict:
    """F2 — 거절 사유를 기록할 `Correction` 목록을 만든다. 서류는 건드리지 않는다.

    거절은 값을 바꾸지 않으므로 `suggestion_id` 변조 대조를 하지 않는다
    (`apply.reject_suggestions` docstring) — 사람이 "이 제안이 틀렸다"고
    판단한 사실만 남기면 된다. 저장은 게이트웨이의 몫이다.
    """
    suggestions = [_suggestion_from_in(s) for s in req.suggestions]
    corrections = reject_suggestions(
        suggestions,
        reason=req.reason,
        note=req.note,
        decided_by=req.decided_by,
        decided_at=req.decided_at,
    )
    return {"corrections": [c.to_dict() for c in corrections]}


# ── F5 서류 간 정합성 ────────────────────────────────────────────


class CrossVerifyRequest(BaseModel):
    """`POST /verify/cross` 요청. `documents` 는 `/normalize` 와 같은 형태다."""

    documents: List[DocumentIn] = Field(
        default_factory=list,
        description="대조할 서류 2건 이상. 하나뿐이면 대조할 상대가 없어 전부 미평가로 남는다.",
    )
    lc: Optional[Dict[str, Any]] = Field(
        None, description="신용장 조건. 룰에서 '신용장'을 서류로 참조할 때만 쓰인다."
    )


@app.post("/verify/cross")
def verify_cross(req: CrossVerifyRequest) -> dict:
    """F5 — 서류 간 정합성 대조(`f3_rules/cross_doc.py`, UCP 600 Art.14(d)).

    `/verify`·`/report` 는 서류 1건을 L/C 에 대조한다. 여기는 **서류끼리**
    대조한다 — 비교할 서류가 세트에 없는 룰은 위반이 아니라 `skipped` 로
    남는다(`cross_doc.py` 모듈 docstring "없는 서류는 저촉이 아니다").
    """
    documents = DocumentSet(lc=LCTerms.from_dict(req.lc) if req.lc else None)
    for d in req.documents:
        documents.add(dict(d.fields), form_type=d.doc)
    return cross_engine().verify(documents).to_dict()


@app.get("/glossary")
def get_glossary() -> dict:
    """F2 — 적재된 표준 사전 요약. 기획안 S11 설정 화면·발표 시연이 쓴다.

    `GET /rules` 의 `unverified_source_count` 와 같은 모양이다. 화면이
    `unverified_term_count` 를 숨기면 미검증 표기가 검증된 것처럼
    인용된다 — 기획안 9절의 리스크와 같은 자리다.
    """
    g = glossary()
    catalogs = all_glossaries()
    return {
        "catalog_version": g.catalog_version,
        "effective_date": g.effective_date,
        "terms": g.term_count,
        "aliases": g.alias_count,
        "unverified_term_count": g.unverified_count,
        "by_class": g.by_class(),
        "available_versions": sorted(catalogs),
    }


class GlossaryValidateRequest(BaseModel):
    """`POST /glossary/validate` 요청. `terms.build_override` 가 받는 payload 그대로."""

    version: str = Field(..., description="이 오버라이드가 자처하는 버전 이름.")
    terms: List[Dict[str, Any]] = Field(
        ...,
        description=(
            "오버라이드 용어 항목 리스트. 표준 카탈로그와 같은 스키마 "
            "(term_id·category·canonical·lang·authority·version·effective_date 등)."
        ),
    )
    effective_date: Optional[str] = Field(None, description="이 오버라이드가 적용되는 날짜(YYYY-MM-DD).")
    tier: str = Field(
        "organization",
        pattern="^(organization|shipment)$",
        description="검증할 계층. 조직 사전 또는 선적 예외.",
    )


@app.post("/glossary/validate")
def validate_glossary(req: GlossaryValidateRequest) -> dict:
    """F2 — 조직/선적 사전 후보를 저장 전에 검증한다. 기획안 S11 이 부른다.

    게이트웨이가 조직 사전을 **저장하기 전에** 호출한다. `build_override`
    를 표준 카탈로그와 같은 검증기로 태우고, 문제를 전부 모아 한 번에
    돌려준다(`glossary.py` "문제를 전부 모아 한 번에" 규약) — 깨진
    사전이 DB 에 들어가는 것을 막는 것이 이 엔드포인트의 유일한 목적이다.
    검증만 하고 **아무것도 저장하지 않는다.**
    """
    payload = {"version": req.version, "terms": req.terms, "effective_date": req.effective_date}
    try:
        override = build_override(payload, tier=req.tier)
    except GlossaryCatalogError as exc:
        # `build_override` 는 문제를 한 문자열에 "\n  - " 로 모아 던진다.
        # 첫 줄은 머리말("오버라이드 사전에 문제가 있습니다:")이라 빼고,
        # 나머지를 배열로 돌려줘야 화면이 항목별로 보여줄 수 있다.
        lines = str(exc).split("\n  - ")
        problems = lines[1:] if len(lines) > 1 else lines
        raise HTTPException(status_code=400, detail=problems) from exc

    return {
        "ok": True,
        "catalog_version": override.catalog_version,
        "terms": override.term_count,
        "aliases": override.alias_count,
        "tier": override.tier,
    }


__all__ = ["app"]
