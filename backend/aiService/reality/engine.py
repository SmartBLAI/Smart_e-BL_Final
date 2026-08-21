"""
F6 현실 대조 엔진.

`ruleEngine.cross_doc.CrossDocumentEngine` 과 같은 모양이다 — 카탈로그를
자체 YAML 로 따로 읽고(다른 카탈로그를 고쳐도 지문이 안 섞이게), 신원은
`ruleEngine.engine.fingerprint_of` 를 그대로 쓴다.

I/O(이벤트 소스 호출)와 순수 계산(정규화·매칭·판정)을 나눈다 —
`fetch_records()` 만 네트워크/파일을 만지고, `check()` 은 레코드 목록을
받아 결정론적으로 계산한다. 테스트가 `check()` 만 부르면 고정된 입력으로
재현 가능하다(design doc §7).
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from ruleEngine.engine import UNDECLARED_VERSION, RuleCatalogError, fingerprint_of
from ruleEngine.checks import CheckOutcome, not_evaluated
from ruleEngine.types import Severity, SkippedRule, Verdict, Violation

from .adapter import EventSource, EventSourceError, source_from_env
from .checks import REGISTRY
from .matcher import match_vessel
from .normalize import NormalizeError, group_voyages
from .types import RealityContext, VesselMatch

DEFAULT_REALITY_RULES_PATH = Path(__file__).with_name("reality_rules.yaml")

_REQUIRED_KEYS = ("id", "title", "severity", "check", "source", "message")


class RealityEngine:
    """울산항 관제 기록과 B/L 을 대조한다."""

    def __init__(
        self,
        rules: Optional[List[dict]] = None,
        version: Optional[str] = None,
        path: Optional[Path] = None,
        source: Optional[EventSource] = None,
    ) -> None:
        if rules is None:
            rules, declared = read_reality_catalog(path)
            version = version if version is not None else declared
        self.rules = rules
        _validate_reality_catalog(self.rules)
        self.fingerprint = fingerprint_of(self.rules, version)
        self.source = source or source_from_env()

    def __len__(self) -> int:
        return len(self.rules)

    def fetch_records(
        self,
        bl: Optional[Any] = None,
        *,
        call_sign: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> List[Dict[str, Any]]:
        """이벤트 소스에서 원시 레코드를 가져온다. 실패하면 `EventSourceError`.

        fixture 소스는 무시하지만, 실 API 소스는 callsgn 없이 호출할 수
        없다(어댑터가 확인해 준 제약) — 그래서 `check()`가 나중에 매칭에
        쓸 call_sign/연도를 fetch 시점에 미리 넘긴다.
        """
        year = None
        if as_of is not None:
            year = str(as_of.year)
        elif bl is not None:
            target_date = _bl_date(bl, "on_board_date")
            if target_date is not None:
                year = str(target_date.year)
        return self.source.fetch(call_sign=call_sign, year=year)

    def check(
        self,
        bl,
        records: List[Dict[str, Any]],
        *,
        call_sign: Optional[str] = None,
        as_of: Optional[datetime] = None,
    ) -> tuple[VesselMatch, Verdict]:
        """B/L 을 원시 레코드와 대조한다. I/O 없이 결정론적으로 계산한다."""
        # VTS 레코드의 occurred_at은 항상 naive다(_parse_timestamp 참고).
        # as_of가 tz-aware로 들어오면(예: "Z" 접미) matcher._pick_voyage의
        # aware-naive 비교가 TypeError를 던진다 — ruleEngine.engine.verify와
        # 같은 이유로 여기서도 진입 시점에 naive로 맞춘다.
        if as_of is not None and as_of.tzinfo is not None:
            as_of = as_of.replace(tzinfo=None)
        try:
            by_call_sign = group_voyages(records)
        except NormalizeError as exc:
            raise RuleCatalogError(f"이벤트 레코드를 정규화할 수 없습니다: {exc}") from exc

        vessel_name = _bl_field(bl, "vessel")
        target_date = as_of or _bl_date(bl, "on_board_date")
        match = match_vessel(
            by_call_sign,
            call_sign=call_sign,
            vessel_name=vessel_name,
            target_date=target_date,
        )
        population = by_call_sign.get(match.call_sign, []) if match.call_sign else []
        ctx = RealityContext(match=match, population=population, as_of=as_of)

        verdict = Verdict(model="reality-v1", catalog=self.fingerprint.to_dict())
        for rule in self.rules:
            outcome = self._run_check(rule, bl, ctx)
            if not outcome.evaluated:
                verdict.skipped.append(
                    SkippedRule(rule_id=rule["id"], title=rule["title"], reason=outcome.reason)
                )
                continue
            verdict.evaluated_count += 1
            if outcome.violated:
                verdict.violations.append(_to_violation(rule, outcome))

        return match, verdict

    @staticmethod
    def _run_check(rule: dict, bl, ctx: RealityContext) -> CheckOutcome:
        fn = REGISTRY.get(rule["check"])
        if fn is None:
            return not_evaluated(f"알 수 없는 검사: {rule['check']}")
        try:
            return fn(bl, ctx, rule)
        except Exception as exc:  # noqa: BLE001 - 룰 하나가 전체를 멈추면 안 된다
            return not_evaluated(f"검사 실패: {exc}")

    def unverified_rules(self) -> List[dict]:
        return [r for r in self.rules if r.get("verified") is not True]


def _bl_field(bl, name: str) -> Optional[str]:
    from ruleEngine.checks import field_value

    return field_value(bl, name)


def _bl_date(bl, name: str) -> Optional[datetime]:
    from ruleEngine.checks import parse_date

    raw = _bl_field(bl, name)
    return parse_date(raw) if raw else None


def _to_violation(rule: dict, outcome: CheckOutcome) -> Violation:
    return Violation(
        rule_id=rule["id"],
        severity=Severity(rule["severity"]),
        title=rule["title"],
        message=_render(rule.get("message", ""), outcome),
        fields=rule.get("fields", []),
        source=rule.get("source", ""),
        remedy=rule.get("remedy", ""),
        weight=float(rule.get("weight", 0.0)),
        observed=dict(outcome.observed or {}),
    )


def _render(template: str, outcome: CheckOutcome) -> str:
    try:
        return template.format(detail=outcome.detail, **(outcome.observed or {}))
    except KeyError:
        return template


def read_reality_catalog(path: Optional[Path] = None) -> tuple:
    try:
        import yaml
    except ImportError as exc:
        raise ImportError("PyYAML 이 필요합니다: pip install PyYAML") from exc

    with open(path or DEFAULT_REALITY_RULES_PATH, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)

    rules = (data or {}).get("rules")
    if not rules:
        raise RuleCatalogError("현실 대조 룰이 하나도 없습니다")

    declared = (data or {}).get("version")
    return rules, (str(declared) if declared is not None else UNDECLARED_VERSION)


def load_reality_rules(path: Optional[Path] = None) -> List[dict]:
    return read_reality_catalog(path)[0]


def _validate_reality_catalog(rules: List[dict]) -> None:
    """기동 시 전수 검사한다. 카탈로그 오류를 첫 요청에서 만나면 늦다."""
    problems: List[str] = []
    seen: Dict[str, int] = {}

    for index, rule in enumerate(rules):
        where = rule.get("id") or f"#{index}"

        for key in _REQUIRED_KEYS:
            if not rule.get(key):
                problems.append(f"{where}: '{key}' 가 없습니다")

        if rule.get("id"):
            if rule["id"] in seen:
                problems.append(f"{where}: id 가 중복입니다")
            seen[rule["id"]] = index

        if rule.get("check") and rule["check"] not in REGISTRY:
            problems.append(
                f"{where}: 알 수 없는 check '{rule['check']}' "
                f"(가능: {', '.join(sorted(REGISTRY))})"
            )

        if rule.get("severity"):
            try:
                Severity(rule["severity"])
            except ValueError:
                problems.append(f"{where}: 알 수 없는 severity '{rule['severity']}'")

        weight = rule.get("weight")
        if weight is not None and not (0.0 <= float(weight) <= 1.0):
            problems.append(f"{where}: weight 는 0~1 이어야 합니다")

    if problems:
        raise RuleCatalogError("현실 대조 카탈로그 오류:\n  - " + "\n  - ".join(problems))


__all__ = [
    "DEFAULT_REALITY_RULES_PATH",
    "EventSourceError",
    "RealityEngine",
    "load_reality_rules",
    "read_reality_catalog",
]
