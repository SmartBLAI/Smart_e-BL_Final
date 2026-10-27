"""F6 통관·운송 현실 대조 — 울산항 관제 기록 대 B/L 서류.

기획안 5.6절. `ruleEngine` 과 같은 공개 규약(각 하위 모듈이 자기
`__all__` 을 갖고, 여기서는 최상위로 재노출만 한다)을 따른다.
"""

from .adapter import (
    DEFAULT_FIXTURE_PATH,
    EventSource,
    EventSourceError,
    FixtureSource,
    UlsanVtsSource,
    resolve_call_sign,
    source_from_env,
)
from .engine import (
    DEFAULT_REALITY_RULES_PATH,
    RealityEngine,
    load_reality_rules,
    read_reality_catalog,
)
from .matcher import match_vessel, vessel_key
from .normalize import NormalizeError, group_voyages, record_to_event
from .types import (
    EVENT_TYPES,
    PortEvent,
    RealityContext,
    VesselMatch,
    Voyage,
)

__all__ = [
    "DEFAULT_FIXTURE_PATH",
    "EventSource",
    "EventSourceError",
    "FixtureSource",
    "UlsanVtsSource",
    "resolve_call_sign",
    "source_from_env",
    "DEFAULT_REALITY_RULES_PATH",
    "RealityEngine",
    "load_reality_rules",
    "read_reality_catalog",
    "match_vessel",
    "vessel_key",
    "NormalizeError",
    "group_voyages",
    "record_to_event",
    "EVENT_TYPES",
    "PortEvent",
    "RealityContext",
    "VesselMatch",
    "Voyage",
]
