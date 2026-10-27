"""인증된 선적 단위로 내부 stateless ai-service 를 중계한다.

브라우저는 AI_INTERNAL_TOKEN 을 받지 않는다. 입력에 사용자가 고친 값이 섞일 수 있어
감사 해시는 요청 해시일 뿐 은행 수락·독립 검증을 뜻하지 않는다.
"""
from __future__ import annotations

import hashlib
import json
import uuid
from collections.abc import AsyncIterator

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from smart_e_bl.api.security import Actor, audit, get_actor, owned_shipment
from smart_e_bl.config import settings
from smart_e_bl.db import get_session

router = APIRouter(prefix="/api/v1", tags=["ai"])

AI_OPERATIONS = frozenset({
    "verify", "normalize", "normalize/apply", "normalize/reject",
    "impact", "reality/check", "explain", "report", "report/pdf",
})


# 선적 id 가 없는 tenant 단위 호출(추출·L/C 파싱·용어 교정). 프론트가 실제로 쓰는 op 만 연다.
TENANT_AI_POST_OPERATIONS = frozenset({
    "extract", "extract/pdf", "lc/mt700",
    "normalize", "normalize/apply", "normalize/reject",
    "verify", "report", "report/pdf",
})


async def _forward(
    operation: str, body: bytes | AsyncIterator[bytes], content_type: str = "application/json", query: str = "",
) -> httpx.Response:
    """ai-service 호출 + 에러 매핑 (선적/tenant 경로 공용)."""
    if not settings.ai_service_url:
        raise HTTPException(status_code=503, detail="AI 서비스 연결 주소가 설정되지 않았습니다.")
    headers = {"Content-Type": content_type}
    if settings.ai_internal_token:
        headers["X-Internal-Token"] = settings.ai_internal_token
    url = settings.ai_service_url.rstrip("/") + "/" + operation + (f"?{query}" if query else "")
    try:
        async with httpx.AsyncClient(timeout=settings.extraction_timeout_seconds) as client:
            response = await client.post(url, content=body, headers=headers)
    except httpx.RequestError as exc:
        raise HTTPException(status_code=503, detail="내부 AI 서비스에 연결할 수 없습니다.") from exc
    if response.status_code >= 400:
        # 401/403 은 사용자 인증이 아니라 내부 토큰 문제라 502 로 숨긴다
        raise HTTPException(
            status_code=502 if response.status_code >= 500 or response.status_code in (401, 403)
            else response.status_code,
            detail=f"AI 서비스가 요청을 거절했습니다 (status {response.status_code}).",
        )
    if len(response.content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=502, detail="AI 응답 크기 제한을 초과했습니다.")
    return response


async def _audit(
    session: AsyncSession, actor: Actor, operation: str, input_sha256: str, response: httpx.Response,
    shipment_id: uuid.UUID | None = None,
) -> None:
    session.add(audit(
        actor, "AI_" + operation.replace("/", "_").upper(),
        "shipment" if shipment_id else "tenant", shipment_id or actor.tenant_id, shipment_id,
        after={
            "input_sha256": input_sha256,
            "output_sha256": hashlib.sha256(response.content).hexdigest(),
            "operation": operation,
            "source": "internal_ai_service",
        },
    ))
    await session.commit()


async def call_ai(
    session: AsyncSession, actor: Actor, shipment_id: uuid.UUID,
    operation: str, payload: dict,
) -> httpx.Response:
    """소유 선적 검증 → ai-service 호출 → 감사 기록. 실패는 HTTPException."""
    await owned_shipment(session, actor, shipment_id)
    if operation not in AI_OPERATIONS:
        raise HTTPException(status_code=404, detail="지원하지 않는 AI 기능입니다.")
    body = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    if len(body) > 2 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="AI 요청 크기가 제한을 초과합니다.")
    await session.commit()  # 소유 확인용 읽기 트랜잭션을 닫아, AI 호출 동안 DB 커넥션을 붙잡지 않는다
    response = await _forward(operation, body)
    await _audit(session, actor, operation, hashlib.sha256(body).hexdigest(), response, shipment_id)
    return response


@router.get("/me")
async def whoami(actor: Actor = Depends(get_actor)) -> dict:
    return {"user_id": str(actor.user_id), "tenant_id": str(actor.tenant_id), "role": actor.role}


@router.post("/shipments/{shipment_id}/ai/{operation:path}")
async def authorized_ai_operation(
    shipment_id: uuid.UUID, operation: str, request: dict,
    actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> Response:
    response = await call_ai(session, actor, shipment_id, operation, request)
    return Response(
        content=response.content,
        media_type="application/pdf" if operation == "report/pdf" else "application/json",
        headers={"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
    )


@router.post("/ai/{operation:path}")
async def tenant_ai_operation(
    operation: str, request: Request,
    actor: Actor = Depends(get_actor),
    session: AsyncSession = Depends(get_session),
) -> Response:
    """선적 없는 호출 중계. 본문·Content-Type 을 그대로 전달해 multipart 업로드도 통과한다."""
    if operation not in TENANT_AI_POST_OPERATIONS:
        raise HTTPException(status_code=404, detail="지원하지 않는 AI 기능입니다.")
    # multipart 경계·필드 오버헤드 여유 1MiB
    limit = settings.max_document_bytes + 1024 * 1024
    if int(request.headers.get("content-length") or 0) > limit:
        raise HTTPException(status_code=413, detail="AI 요청 크기가 제한을 초과합니다.")
    digest = hashlib.sha256()

    async def capped() -> AsyncIterator[bytes]:
        # content-length 가 없거나 거짓이어도 상한을 넘는 즉시 끊는다. 본문은 메모리에 모으지 않는다.
        total = 0
        async for chunk in request.stream():
            total += len(chunk)
            if total > limit:
                raise HTTPException(status_code=413, detail="AI 요청 크기가 제한을 초과합니다.")
            digest.update(chunk)
            yield chunk

    await session.commit()  # get_actor 의 읽기 트랜잭션을 닫아 AI 호출 중 커넥션을 반납
    response = await _forward(
        operation, capped(), request.headers.get("content-type", "application/json"), request.url.query,
    )
    await _audit(session, actor, operation, digest.hexdigest(), response)
    headers = {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"}
    if "content-disposition" in response.headers:  # report/pdf 파일명
        headers["Content-Disposition"] = response.headers["content-disposition"]
    return Response(
        content=response.content, headers=headers,
        media_type=response.headers.get("content-type", "application/json"),
    )
