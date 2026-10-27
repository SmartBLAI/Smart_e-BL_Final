#!/usr/bin/env python3
"""F6 fixture 대 실 API(울산항 VTS) 대조 점검. 읽기 전용 공개 데이터만 건드린다.

같은 B/L 을 fixture 레코드와 실 레코드로 각각 RealityEngine 에 넣어 매칭 결과와
발화 룰 id 를 콜사인별로 비교한다. 키는 출력하지 않는다.

사용법:
    python scripts/reality_live_check.py [--count 3]

종료 코드: 0 = 실행 완료, 1 = 키 없음/인증 실패/쿼터 초과 등 실 API 실패.
"""
import argparse
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "ai"))

from dotenv import load_dotenv  # noqa: E402

# ai/.env 가 우선, 루트 .env 는 비어 있는 값만 채운다(override=False).
load_dotenv(ROOT / "ai" / ".env")
load_dotenv(ROOT / ".env")

from f6_reality import (  # noqa: E402
    EventSourceError,
    FixtureSource,
    RealityEngine,
    UlsanVtsSource,
    group_voyages,
)


def fail(reason: str) -> None:
    print(f"실패: {reason}", file=sys.stderr)
    sys.exit(1)


def run(engine, bl, records, call_sign, as_of):
    match, verdict = engine.check(bl, records, call_sign=call_sign, as_of=as_of)
    return (
        (match.matched, match.voyage.voyage_no if match.voyage else None),
        sorted(v.rule_id for v in verdict.violations),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--count", type=int, default=3, help="점검할 콜사인 수")
    args = parser.parse_args()

    live = UlsanVtsSource()
    if not live.base_url or not live.service_key or live.service_key == "changeme":
        fail("ULSAN_VTS_BASE_URL / ULSAN_VTS_SERVICE_KEY 가 ai/.env 또는 루트 .env 에 없습니다")

    fixture = FixtureSource().fetch()
    engine = RealityEngine(source=FixtureSource())
    diffs = 0
    # 콜사인별로 fixture 의 첫 완결 항차를 골라 그 날짜·연도로 실 API 를 조회한다.
    for call_sign, voyages in list(group_voyages(fixture).items())[: args.count]:
        v = next((v for v in voyages if v.arrival and v.departure), None)
        if v is None:
            continue
        as_of = v.arrival.occurred_at
        bl = {"vessel": v.vessel_name_en, "on_board_date": as_of.date().isoformat()}
        try:
            live_records = live.fetch(call_sign=call_sign, year=v.year)
        except EventSourceError as exc:
            msg = str(exc)
            kind = "쿼터 초과" if ("22" in msg or "LIMIT" in msg.upper()) else "인증/호출 실패"
            fail(f"{kind} — {msg}")
        fx = run(engine, bl, fixture, call_sign, as_of)
        lv = run(engine, bl, live_records, call_sign, as_of)
        same = fx == lv
        diffs += not same
        print(f"[{call_sign}] {v.vessel_name_en} {v.year} 실 레코드 {len(live_records)}건 "
              f"{'동일' if same else '차이'}")
        print(f"    fixture: 매칭(matched, 항차)={fx[0]} 룰={fx[1]}")
        print(f"    live   : 매칭(matched, 항차)={lv[0]} 룰={lv[1]}")
    print(f"완료: 차이 {diffs}건")


if __name__ == "__main__":
    main()
