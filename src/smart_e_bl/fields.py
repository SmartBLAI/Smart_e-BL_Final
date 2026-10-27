"""프론트 field_name <-> field_definition.code(BL.*) 변환 규칙. 게이트웨이·워커 공용."""

# frontend/src/constants/domain.ts 의 field_name과 field_definition.code(BL.*) 접미사가
# 거의 다 기계적으로 맞아떨어지지만(대문자 변환), 안 맞는 것만 예외로 둔다.
#
# ai-service 원본 추출 이름(vessel, voyage_no, on_board_date)도 별칭으로 추가했다
# (P1-5) — 프론트 어댑터(adaptersExtract.ts)를 거치지 않고 게이트웨이를 직접
# 부르는 통합·테스트가 이 이름을 그대로 보내면, 카탈로그에 없는 접미사로
# 대문자 변환되어 조용히 버려졌었다.
#
# ponytail: vessel과 voyage_no는 둘 다 같은 필드(BL.VESSEL_VOYAGE)로 인코딩된다 —
# 프론트는 값을 합쳐서 보내지만, 이 별칭을 통해 둘을 따로 보내면 나중 것이
# 앞의 것을 덮어쓴다(병합 아님). 완전한 병합이 필요해지면 프론트 어댑터의
# 병합 로직을 게이트웨이 쪽에도 옮길 것.
_FIELD_NAME_OVERRIDES = {
    "shipped_on_board_date": "ONBOARD_DATE",
    "on_board_date": "ONBOARD_DATE",
    "vessel": "VESSEL_VOYAGE",
    "voyage_no": "VESSEL_VOYAGE",
}

# 디코딩(코드→이름)은 항상 프론트가 쓰는 정식 이름 하나로만 돌아가야 한다 —
# 위 별칭처럼 여러 이름이 같은 코드로 인코딩되더라도, 게이트웨이가 프론트에
# 돌려주는 field_name은 애매해지면 안 된다.
_FIELD_CODE_TO_CANONICAL_NAME = {
    "ONBOARD_DATE": "shipped_on_board_date",
    "VESSEL_VOYAGE": "vessel_voyage",
}


def field_code(field_name: str) -> str:
    suffix = _FIELD_NAME_OVERRIDES.get(field_name, field_name.upper())
    return f"BL.{suffix}"


def field_name(field_code: str) -> str:
    suffix = field_code.removeprefix("BL.")
    return _FIELD_CODE_TO_CANONICAL_NAME.get(suffix, suffix.lower())

