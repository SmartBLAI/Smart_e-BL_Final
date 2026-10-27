"""워커 프로세스.

ingest_job 테이블 자체를 큐로 씁니다. FOR UPDATE SKIP LOCKED 로 잡을 집으면
워커를 여러 개 띄워도 같은 잡을 두 번 처리하지 않습니다.

Redis·Celery 를 도입하지 않은 이유: 잡 상태(QUEUED/EXTRACTING/DONE/FAILED)와
진행률을 어차피 DB 에 두어야 화면이 폴링할 수 있고(기획안 5.1), 브로커를 따로 두면
폐쇄망 단일 호스트 배포에 컴포넌트가 하나 더 늘어납니다. 처리량이 부족해지면
그때 브로커로 옮기면 됩니다 — 이 파일의 집는 부분만 바뀝니다.
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
import signal
import time
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import FrameType

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.pool import NullPool

from smart_e_bl import storage
from smart_e_bl.config import settings
from smart_e_bl.db import sync_session
from smart_e_bl.fields import field_code as _field_code
from smart_e_bl.api.security import Actor
from smart_e_bl.models import AppUser, AuditLog, Document, FieldDefinition, FieldValue, IngestJob
from smart_e_bl.models.enums import ConfidenceGrade, ExtractorKind, JobStatus

logger = logging.getLogger("smart_e_bl.worker")

_shutdown = False


def _handle_signal(signum: int, frame: FrameType | None) -> None:
    global _shutdown
    _shutdown = True
    logger.info("종료 신호 수신(%s). 진행 중인 잡을 마치고 멈춥니다.", signum)


def claim_job(session) -> IngestJob | None:
    """대기 중인 잡 하나를 배타적으로 집습니다."""
    job = session.scalar(
        select(IngestJob)
        .where(IngestJob.status == JobStatus.QUEUED)
        .order_by(IngestJob.created_at)
        .limit(1)
        .with_for_update(skip_locked=True)
    )
    if job is None:
        return None
    job.status = JobStatus.EXTRACTING
    job.started_at = datetime.now(UTC)
    session.commit()
    return job


def _valid_bbox(raw: object) -> tuple[float, float, float, float] | None:
    """Only persist normalized 0..1 evidence coordinates."""
    if not isinstance(raw, (list, tuple)) or len(raw) != 4:
        return None
    if any(not isinstance(n, (int, float)) for n in raw):
        return None
    x0, y0, x1, y1 = map(float, raw)
    if 0 <= x0 < x1 <= 1 and 0 <= y0 < y1 <= 1:
        return x0, y0, x1, y1
    return None


def process(session, job: IngestJob) -> None:
    """저장된 원본 -> AI 서비스 추출 -> 근거 좌표가 있는 field_value 저장.

    근거(bbox)를 검증할 수 없는 값은 저장하지 않고 NOT_FOUND 로 남긴다 —
    출처 없는 추정값을 확정 데이터처럼 넣지 않기 위함이다.
    """
    import httpx

    doc = session.scalar(
        select(Document).where(
            Document.ingest_job_id == job.id,
            Document.tenant_id == job.tenant_id,
        )
    )
    if doc is None or not doc.storage_uri:
        raise ValueError("업로드된 원본 문서가 작업에 연결되지 않았습니다.")
    payload = storage.read(doc.storage_uri)
    if not payload or len(payload) > settings.max_document_bytes:
        raise ValueError("저장된 원본 파일이 비어 있거나 업로드 크기 제한을 초과했습니다.")
    if hashlib.sha256(payload).hexdigest() != doc.file_hash:
        raise ValueError("원본 파일 해시가 DB 기록과 다릅니다.")

    is_pdf = payload.startswith(b"%PDF-")
    is_image = payload.startswith(
        (b"\x89PNG\r\n\x1a\n", b"\xff\xd8\xff", b"II*\x00", b"MM\x00*")
    )
    if not (is_pdf or is_image):
        raise ValueError("PDF·PNG·JPEG·TIFF 이외 원본 문서는 추출할 수 없습니다.")

    if not settings.ai_service_url:
        raise RuntimeError("AI_SERVICE_URL 이 설정되지 않았습니다.")
    endpoint = "/extract/pdf" if is_pdf else "/extract"
    headers = (
        {"X-Internal-Token": settings.ai_internal_token}
        if settings.ai_internal_token else {}
    )
    with httpx.Client(timeout=settings.extraction_timeout_seconds) as client:
        response = client.post(
            settings.ai_service_url.rstrip("/") + endpoint,
            files={"file": (doc.original_filename or "document", payload, doc.mime_type or "application/octet-stream")},
            headers=headers,
        )
        response.raise_for_status()
        data = response.json()

    if not isinstance(data, dict) or not isinstance(data.get("fields"), list):
        raise ValueError("AI 서비스가 추출 필드 목록을 반환하지 않았습니다.")

    definitions = {
        field.code for field in session.scalars(select(FieldDefinition))
    }
    persisted = 0
    not_grounded = 0
    for item in data["fields"]:
        if not isinstance(item, dict):
            continue
        name = item.get("name")
        if not isinstance(name, str):
            continue
        code = _field_code(name)  # ai-service 이름(bl_no) -> 카탈로그 코드(BL.BL_NO)
        if code not in definitions:
            continue
        value = item.get("value")
        if value is not None and not isinstance(value, str):
            continue
        bbox = _valid_bbox(item.get("bbox"))
        grounded = value is not None and bbox is not None
        if value is not None and not grounded:
            not_grounded += 1
        # F1 DB check prohibits preserving ungrounded auto-generated text.
        kept_value = value if grounded else None
        confidence = item.get("confidence")
        if not isinstance(confidence, (int, float)) or not 0 <= confidence <= 1:
            confidence = None
        if kept_value is None:
            grade = ConfidenceGrade.NOT_FOUND
        elif confidence is not None and confidence >= 0.9:
            grade = ConfidenceGrade.CONFIRMED
        elif confidence is not None and confidence >= 0.7:
            grade = ConfidenceGrade.REVIEW_SUGGESTED
        else:
            grade = ConfidenceGrade.REVIEW_REQUIRED

        # The first source remains representative until a human chooses
        # among conflicts. Never silently overwrite the original evidence.
        original = session.scalar(select(FieldValue).where(
            FieldValue.shipment_id == job.shipment_id,
            FieldValue.field_code == code,
            FieldValue.tenant_id == job.tenant_id,
            FieldValue.is_representative.is_(True),
        ).with_for_update())
        representative = original is None
        conflict = original is not None and original.value != kept_value
        if conflict:
            original.conflict_flag = True
        row = FieldValue(
            tenant_id=job.tenant_id, shipment_id=job.shipment_id,
            document_id=doc.id if grounded else None,
            field_code=code, value=kept_value, normalized_value=None,
            page=1 if grounded else None,
            bbox_x1=Decimal(str(bbox[0])) if grounded else None,
            bbox_y1=Decimal(str(bbox[1])) if grounded else None,
            bbox_x2=Decimal(str(bbox[2])) if grounded else None,
            bbox_y2=Decimal(str(bbox[3])) if grounded else None,
            confidence=Decimal(str(confidence)) if confidence is not None else None,
            grade=grade, extractor=ExtractorKind.RULE,
            is_representative=representative, conflict_flag=conflict,
        )
        session.add(row)
        persisted += 1

    session.add(AuditLog(
        tenant_id=job.tenant_id, actor_id=None,
        action="OCR_EXTRACTION_COMPLETED",
        entity_type="ingest_job", entity_id=job.id,
        shipment_id=job.shipment_id,
        after_state={"document_id": str(doc.id), "field_rows": persisted,
                     "ungrounded_field_count": not_grounded,
                     "engine_source": data.get("source")},
    ))
    job.progress = 100
    session.flush()
    logger.info("추출 저장 job=%s fields=%d ungrounded=%d",
                job.id, persisted, not_grounded)


def run_once() -> bool:
    """잡 하나를 처리합니다. 처리했으면 True."""
    with sync_session() as session:
        job = claim_job(session)
        if job is None:
            return False
        logger.info("잡 시작 job_id=%s", job.id)
        try:
            process(session, job)
        except Exception as exc:  # noqa: BLE001
            session.rollback()
            job = session.get(IngestJob, job.id)
            job.status = JobStatus.FAILED
            job.error_code = "EXTRACTION_ERROR"
            job.error_message = str(exc)[:2000]
            job.finished_at = datetime.now(UTC)
            session.commit()
            logger.exception("잡 실패 job_id=%s", job.id)
        else:
            job.status = JobStatus.DONE
            job.progress = 100
            job.finished_at = datetime.now(UTC)
            session.commit()
            logger.info("잡 완료 job_id=%s", job.id)
        return True


_ULSAN = ("울산", "ULSAN", "KRUSN")  # ai/f6_reality _ULSAN_ALIASES 와 같은 의미 (게이트웨이는 ai/ 를 import 하지 않는다)
_POLL_FIELDS = {"BL.ONBOARD_DATE": "date", "BL.PORT_OF_LOADING": "pol", "BL.PORT_OF_DISCHARGE": "pod"}


def _eligible_shipments(session) -> list[tuple]:
    """(shipment_id, tenant_id): 본선적재일이 lookback 안이고 POL/POD 가 울산인 선적."""
    since = date.today() - timedelta(days=settings.reality_poll_lookback_days)
    by_ship: dict = {}
    rows = session.execute(
        select(FieldValue.shipment_id, FieldValue.tenant_id, FieldValue.field_code,
               FieldValue.value, FieldValue.normalized_value)
        .where(FieldValue.is_representative, FieldValue.field_code.in_(_POLL_FIELDS))
    )
    for sid, tid, code, value, norm in rows:
        by_ship.setdefault((sid, tid), {})[_POLL_FIELDS[code]] = value or norm or ""
    out = []
    for key, f in by_ship.items():
        try:
            on_board = date.fromisoformat(f.get("date", "")[:10])
        except ValueError:
            continue  # 날짜를 못 읽는 선적은 점검 대상이 아니다
        ports = f"{f.get('pol', '')} {f.get('pod', '')}".upper()
        if on_board >= since and any(a in ports for a in _ULSAN):
            out.append(key)
    return out


def poll_reality() -> int:
    """울산 선적을 한 번 훑어 현실 대조를 돌린다. 점검한 건수 반환."""
    from smart_e_bl.api.reality import run_reality_check

    with sync_session() as session:
        targets = _eligible_shipments(session)
        admins = {}
        for _, tid in set(targets):
            admins[tid] = session.scalar(
                select(AppUser.id).where(AppUser.tenant_id == tid, AppUser.role == "ADMIN", AppUser.is_active)
                .order_by(AppUser.created_at).limit(1))

    async def _run() -> int:
        # asyncio.run 마다 이벤트 루프가 새로 생기므로 전역 풀 대신 이번 패스 전용 엔진을 쓴다
        engine = create_async_engine(settings.async_database_url, poolclass=NullPool)
        done = 0
        for sid, tid in targets:
            if admins[tid] is None:
                logger.warning("현실 대조 건너뜀: 테넌트 %s 에 ADMIN 이 없음 shipment=%s", tid, sid)
                continue
            try:  # 실패한 실행은 run_reality_check 가 이미 기록한다
                async with AsyncSession(engine, expire_on_commit=False) as s:
                    await run_reality_check(s, Actor(user_id=admins[tid], tenant_id=tid, role="ADMIN"), sid)
                done += 1
            except Exception:  # noqa: BLE001
                logger.exception("현실 대조 실패 shipment=%s", sid)
        await engine.dispose()
        return done

    return asyncio.run(_run())


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    signal.signal(signal.SIGTERM, _handle_signal)
    signal.signal(signal.SIGINT, _handle_signal)
    logger.info("워커 시작 (프로파일=%s)", settings.deployment_profile)
    next_poll = time.monotonic() + settings.reality_poll_interval_seconds
    while not _shutdown:
        if settings.reality_poll_interval_seconds > 0 and time.monotonic() >= next_poll:
            try:
                logger.info("현실 대조 주기 점검 %d건", poll_reality())
            except Exception:  # noqa: BLE001
                logger.exception("현실 대조 주기 점검 실패")
            next_poll = time.monotonic() + settings.reality_poll_interval_seconds
        if not run_once():
            time.sleep(settings.worker_poll_seconds)
    logger.info("워커 종료")


if __name__ == "__main__":
    main()
