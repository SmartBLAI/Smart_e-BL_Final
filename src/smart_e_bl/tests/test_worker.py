"""워커 process(): AI HTTP 호출을 모킹해 잡 상태와 field_value 근거 좌표를 확인한다.
실제 Postgres 필요(conftest 와 동일). 만든 행은 선적 삭제로 CASCADE 정리.
"""

import hashlib
import uuid
from unittest.mock import MagicMock

import pytest
from sqlalchemy import delete, select

from smart_e_bl import storage
from smart_e_bl.config import BOOTSTRAP_TENANT_ID, BOOTSTRAP_USER_ID, settings
from smart_e_bl.db import sync_session
from smart_e_bl.models import Document, FieldValue, IngestJob, Shipment
from smart_e_bl.models.enums import DocumentType, JobStatus
from smart_e_bl.worker import main as worker

PDF = b"%PDF-1.4 worker test " + uuid.uuid4().bytes


@pytest.fixture
def queued(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "storage_backend", "local")
    monkeypatch.setattr(settings, "ai_service_url", "http://ai")
    _, uri = storage.save(str(tmp_path), PDF, ".pdf")
    with sync_session() as s:
        ship = Shipment(tenant_id=BOOTSTRAP_TENANT_ID, created_by=BOOTSTRAP_USER_ID)
        s.add(ship)
        s.flush()
        job = IngestJob(tenant_id=BOOTSTRAP_TENANT_ID, shipment_id=ship.id)
        s.add(job)
        s.flush()
        s.add(Document(
            tenant_id=BOOTSTRAP_TENANT_ID, shipment_id=ship.id, ingest_job_id=job.id,
            doc_type=DocumentType.BL_DRAFT, original_filename="t.pdf", mime_type="application/pdf",
            byte_size=len(PDF), file_hash=hashlib.sha256(PDF).hexdigest(), storage_uri=uri,
            uploaded_by=BOOTSTRAP_USER_ID,
        ))
        s.commit()
        ids = ship.id, job.id
    # 다른 테스트의 QUEUED 잡이 먼저 집히지 않게 이 잡만 남긴다.
    yield ids
    with sync_session() as s:
        s.execute(delete(Shipment).where(Shipment.id == ids[0]))
        s.commit()


def _ai(monkeypatch, *, fail=False):
    import httpx

    resp = MagicMock()
    if fail:
        resp.raise_for_status.side_effect = httpx.HTTPError("ai down")
    else:
        code = "bl_no"
        resp.json.return_value = {"source": "pdf-text", "fields": [
            {"name": code, "value": "BUSAN", "confidence": 0.95, "bbox": [0.1, 0.1, 0.4, 0.2]},
            {"name": code, "value": "NOBOX", "confidence": 0.9, "bbox": None},
        ]}
    post = MagicMock(return_value=resp)
    monkeypatch.setattr(httpx.Client, "post", lambda self, *a, **kw: post(*a, **kw))
    return post


def _run_job(job_id):
    # run_once 는 가장 오래된 QUEUED 잡을 집으므로, 테스트 잡 외 대기 잡은 건드리지 않게 직접 호출.
    with sync_session() as s:
        job = s.get(IngestJob, job_id)
        job.status = JobStatus.EXTRACTING
        try:
            worker.process(s, job)
        except Exception as exc:  # noqa: BLE001  run_once 와 같은 분기
            s.rollback()
            job = s.get(IngestJob, job_id)
            job.status, job.error_code, job.error_message = JobStatus.FAILED, "EXTRACTION_ERROR", str(exc)
        else:
            job.status = JobStatus.DONE
        s.commit()


def test_성공하면_근거있는_field_value_저장(queued, monkeypatch):
    ship_id, job_id = queued
    post = _ai(monkeypatch)
    monkeypatch.setattr(settings, "ai_internal_token", "tok")

    _run_job(job_id)

    assert post.call_args.kwargs["headers"] == {"X-Internal-Token": "tok"}
    with sync_session() as s:
        assert s.get(IngestJob, job_id).status == JobStatus.DONE
        rows = s.scalars(select(FieldValue).where(FieldValue.shipment_id == ship_id)).all()
    grounded = [r for r in rows if r.value == "BUSAN"]
    assert len(grounded) == 1 and grounded[0].bbox_x1 is not None and grounded[0].page == 1
    assert [r for r in rows if r.value is None]  # bbox 없는 값은 NOT_FOUND 로 남음


def test_AI_실패하면_FAILED와_오류기록(queued, monkeypatch):
    ship_id, job_id = queued
    _ai(monkeypatch, fail=True)

    _run_job(job_id)

    with sync_session() as s:
        job = s.get(IngestJob, job_id)
        assert job.status == JobStatus.FAILED and "ai down" in job.error_message
        assert not s.scalars(select(FieldValue).where(FieldValue.shipment_id == ship_id)).all()
