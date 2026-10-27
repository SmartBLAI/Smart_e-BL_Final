"""인증 모드 스위치. 클라이언트가 보낸 테넌트·사용자 ID는 절대 신뢰하지 않는다.

oidc: IdP 가 app_user_id(UUID) 클레임을 담아 서명한 RS256 토큰을 검증하고,
역할·테넌트는 항상 DB 에서 읽는다. IdP 미구성이면 보호 엔드포인트는 fail-closed.
bootstrap: 토큰을 보지 않고 부트스트랩 ADMIN 으로 동작(로컬·시연 전용).
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt import InvalidTokenError, PyJWKClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.concurrency import run_in_threadpool

from smart_e_bl.config import BOOTSTRAP_TENANT_ID, BOOTSTRAP_USER_ID, settings
from smart_e_bl.db import get_session
from smart_e_bl.models import AppUser, AuditLog, Shipment

bearer = HTTPBearer(auto_error=False)


@dataclass(frozen=True)
class Actor:
    user_id: uuid.UUID
    tenant_id: uuid.UUID
    role: str


@lru_cache(maxsize=1)
def _jwk_client() -> PyJWKClient:
    if not (settings.oidc_jwks_url and settings.oidc_issuer and settings.oidc_audience):
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OIDC 인증이 구성되지 않았습니다.",
        )
    return PyJWKClient(settings.oidc_jwks_url, cache_jwk_set=True, lifespan=3600)


async def get_actor(
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer),
    session: AsyncSession = Depends(get_session),
) -> Actor:
    if settings.auth_mode == "bootstrap":
        # 10_bootstrap_tenant.sql 의 app_user.role 과 같은 값(ADMIN)
        return Actor(user_id=BOOTSTRAP_USER_ID, tenant_id=BOOTSTRAP_TENANT_ID, role="ADMIN")
    if not (settings.oidc_jwks_url and settings.oidc_issuer and settings.oidc_audience):
        raise HTTPException(status_code=503, detail="OIDC 인증이 구성되지 않았습니다.")
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="인증이 필요합니다.",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = credentials.credentials
    try:
        # JWKS 조회는 동기 HTTP — 캐시 미스 시 이벤트 루프를 막지 않게 스레드로 뺀다.
        signing_key = await run_in_threadpool(_jwk_client().get_signing_key_from_jwt, token)
        payload = jwt.decode(
            token,
            signing_key.key,
            algorithms=["RS256"],
            issuer=settings.oidc_issuer,
            audience=settings.oidc_audience,
            options={"require": ["exp", "iat", "iss", "aud", "sub"]},
            leeway=30,
        )
        user_id = uuid.UUID(str(payload["app_user_id"]))
    except (InvalidTokenError, KeyError, TypeError, ValueError, jwt.PyJWKClientError) as exc:
        raise HTTPException(
            status_code=401, detail="유효하지 않은 인증 토큰입니다.",
            headers={"WWW-Authenticate": "Bearer"},
        ) from exc
    user = await session.scalar(
        select(AppUser).where(AppUser.id == user_id, AppUser.is_active.is_(True))
    )
    if user is None:
        raise HTTPException(status_code=403, detail="등록되었거나 활성화된 사용자가 아닙니다.")
    return Actor(user_id=user.id, tenant_id=user.tenant_id, role=user.role)


def require_editor(actor: Actor) -> None:
    # 역할은 토큰 클레임이 아니라 DB 의 AppUser 행 기준으로 읽기 전용을 막는다.
    if actor.role.upper() in {"VIEWER", "AUDITOR", "READ_ONLY"}:
        raise HTTPException(status_code=403, detail="이 사용자에게 변경 권한이 없습니다.")


async def owned_shipment(
    session: AsyncSession, actor: Actor, shipment_id: uuid.UUID,
) -> Shipment:
    shipment = await session.scalar(select(Shipment).where(
        Shipment.id == shipment_id, Shipment.tenant_id == actor.tenant_id,
    ))
    if shipment is None:
        # 타 테넌트 접근도 404 — 객체 존재 여부를 알려주지 않는다.
        raise HTTPException(status_code=404, detail="선적을 찾을 수 없습니다.")
    return shipment


def audit(
    actor: Actor, action: str, entity: str, entity_id: uuid.UUID,
    shipment_id: uuid.UUID | None = None, before: dict | None = None, after: dict | None = None,
) -> AuditLog:
    """감사 로그 행 생성(세션 추가는 호출자가). tenant·actor 는 항상 인증된 Actor 기준."""
    return AuditLog(
        tenant_id=actor.tenant_id, actor_id=actor.user_id, action=action,
        entity_type=entity, entity_id=entity_id, shipment_id=shipment_id,
        before_state=before, after_state=after,
    )
