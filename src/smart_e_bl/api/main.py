"""API 프로세스.

여기서는 짧은 요청만 처리합니다. OCR·LLM 추출·추론처럼 오래 걸리는 작업은
ingest_job 에 넣고 워커 프로세스가 가져갑니다 — 기획안 5.1 의
"업로드 즉시 job_id 를 반환하고 진행 상태를 폴링/SSE 로 표시한다" 가 이 구조입니다.
GIL 아래에서 CPU 작업을 이벤트 루프에 올리면 API 전체가 멈춥니다.
"""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import date, datetime
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from fastapi import Depends, FastAPI, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, text
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from smart_e_bl import storage
from smart_e_bl.config import BOOTSTRAP_TENANT_ID, BOOTSTRAP_USER_ID, settings
from smart_e_bl.db import async_engine, get_session
from smart_e_bl.models import (
    AuditLog,
    Document,
    FieldDefinition,
    FieldValue,
    IngestJob,
    Shipment,
    ShipmentStatusHistory,
)
from smart_e_bl.models.enums import (
    ConfidenceGrade,
    DocumentType,
    ExtractorKind,
    JobStatus,
    ShipmentStatus,
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # storage.save()는 업로드 시점에야 mkdir을 시도한다 — 경로에 쓸 권한이
    # 없으면(Docker 밖에서 컨테이너 전용 절대경로 기본값을 못 쓰는 경우 등)
    # 첫 업로드 요청에서야 알 수 없는 500으로 터진다. 기동 시 한 번
    # 만들어 보고, 안 되면 바로 실패해 원인을 로그로 남긴다.
    try:
        Path(settings.document_storage_root).mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise RuntimeError(
            f"DOCUMENT_STORAGE_ROOT({settings.document_storage_root!r})를 만들 수 "
            f"없습니다: {exc}. 쓰기 권한이 있는 경로로 DOCUMENT_STORAGE_ROOT를 지정하세요."
        ) from exc
    yield
    await async_engine.dispose()


app = FastAPI(
    title="B/L Copilot API",
    version="0.1.0",
    lifespan=lifespan,
)


# 프론트가 이 서비스를 브라우저에서 직접 호출한다(backend/aiService/api/main.py 와 같은
# 이유 — 서버끼리 중계하는 게이트웨이가 아직 없다). `*` 대신 허용 목록을 환경변수로 받는다.
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
        allow_credentials=False,
        allow_methods=["GET", "POST", "PUT", "OPTIONS"],
        allow_headers=["Content-Type"],
    )


class HealthResponse(BaseModel):
    status: str
    profile: str
    schema_revision: str | None


class JobResponse(BaseModel):
    """기획안 5.1 진행 상태: 대기·추출중·완료·실패."""

    job_id: UUID
    status: JobStatus
    progress: int
    error_code: str | None = None
    error_message: str | None = None


@app.get("/health", response_model=HealthResponse)
async def health(session: AsyncSession = Depends(get_session)) -> HealthResponse:
    """DB 연결과 적용된 마이그레이션 리비전을 함께 확인합니다."""
    revision = await session.scalar(text("SELECT version_num FROM alembic_version"))
    return HealthResponse(
        status="ok", profile=settings.deployment_profile, schema_revision=revision
    )


# P1-8 (범위 명시): 잡 폴링 API·워커(worker/main.py)는 기획안 5.1의 "업로드 즉시
# job_id 반환" 경로용으로 만들어졌지만, 이번 기간 실제 추출은 프론트가 aiService
# (/extract/*)를 동기 호출하는 경로로 구현됐다 — upload_document는 IngestJob을
# 만들지 않으므로 이 엔드포인트·워커는 이번 기간 시연 범위 밖(미사용)이다.
# 비동기 잡 큐로 전환하려면 upload_document에서 IngestJob을 생성하고,
# worker/main.py의 process()에 aiService 호출을 배선해야 한다.
@app.get("/api/v1/jobs/{job_id}", response_model=JobResponse)
async def get_job(
    job_id: UUID, session: AsyncSession = Depends(get_session)
) -> JobResponse:
    # 목록 조회가 없어 눈에 덜 띄지만 같은 이유로 테넌트로 거른다 (P2-10)
    job = await session.scalar(
        select(IngestJob).where(
            IngestJob.id == job_id, IngestJob.tenant_id == BOOTSTRAP_TENANT_ID
        )
    )
    if job is None:
        raise HTTPException(status_code=404, detail="job not found")
    return JobResponse(
        job_id=job.id,
        status=job.status,
        progress=job.progress,
        error_code=job.error_code,
        error_message=job.error_message,
    )


# ── 선적 · 서류 · 필드값 ─────────────────────────────────────────
#
# 인증이 아직 없어 모든 선적이 BOOTSTRAP_TENANT_ID 하나에 붙습니다.
# migrations/sql/10_bootstrap_tenant.sql 참고.

# frontend/src/constants/domain.ts 의 field_name과 field_definition.code(BL.*) 접미사가
# 거의 다 기계적으로 맞아떨어지지만(대문자 변환), 안 맞는 것만 예외로 둔다.
#
# aiService 원본 추출 이름(vessel, voyage_no, on_board_date)도 별칭으로 추가했다
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


def _field_code(field_name: str) -> str:
    suffix = _FIELD_NAME_OVERRIDES.get(field_name, field_name.upper())
    return f"BL.{suffix}"


def _field_name(field_code: str) -> str:
    suffix = field_code.removeprefix("BL.")
    return _FIELD_CODE_TO_CANONICAL_NAME.get(suffix, suffix.lower())


_GRADE_TO_DB = {
    "CONFIRMED": ConfidenceGrade.CONFIRMED,
    "ADVISORY": ConfidenceGrade.REVIEW_SUGGESTED,
    "REQUIRED": ConfidenceGrade.REVIEW_REQUIRED,
    "NOT_FOUND": ConfidenceGrade.NOT_FOUND,
}
_GRADE_FROM_DB = {v: k for k, v in _GRADE_TO_DB.items()}

# 프론트 타입(frontend/src/types/domain.ts)에는 'manual'이 없다 — 화면 어디도 extractor로
# 분기하지 않아(F1 adaptersExtract.ts와 같은 근거) 'rule'로 뭉뚱그려도 안전하다.
_EXTRACTOR_FROM_DB = {
    ExtractorKind.RULE: "rule",
    ExtractorKind.OCR_LLM: "ocr+llm",
    ExtractorKind.JSON: "json",
    ExtractorKind.MANUAL: "rule",
}


def _extractor_kind(extractor: str, has_bbox: bool) -> ExtractorKind:
    """bbox 유무로 extractor_kind를 정한다.

    field_value_evidence_required_ck가 좌표 없이 저장을 허용하는 건 정확히
    MANUAL·JSON 뿐이다. bbox가 있으면 그 제약을 만족하니 원래 종류(RULE/OCR_LLM)를
    쓰고, 없으면 JSON이 아닌 한 MANUAL로 강제해 제약을 항상 만족시킨다.
    """
    if has_bbox:
        return ExtractorKind.OCR_LLM if extractor == "ocr+llm" else ExtractorKind.RULE
    if extractor == "json":
        return ExtractorKind.JSON
    return ExtractorKind.MANUAL


async def _get_tenant_shipment(session: AsyncSession, shipment_id: UUID) -> Shipment | None:
    """`session.get(Shipment, id)` 는 PK만 보고 테넌트를 안 본다 — 목록
    조회(`list_shipments`)는 이미 tenant_id 로 거르는데 단건 조회만 안
    거르면, 인증이 붙어 다중 테넌트가 실제로 생기는 날 다른 테넌트의
    shipment_id 를 그대로 넣어 조회할 수 있다(P2-10). 단건도 같은 조건으로
    맞춘다.
    """
    return await session.scalar(
        select(Shipment).where(
            Shipment.id == shipment_id, Shipment.tenant_id == BOOTSTRAP_TENANT_ID
        )
    )


async def _get_tenant_document(session: AsyncSession, document_id: UUID) -> Document | None:
    """`_get_tenant_shipment` 과 같은 이유 — Document 단건 조회도 테넌트로 거른다."""
    return await session.scalar(
        select(Document).where(
            Document.id == document_id, Document.tenant_id == BOOTSTRAP_TENANT_ID
        )
    )


_MAX_UPLOAD_BYTES = 30 * 1024 * 1024  # document_byte_size_ck 와 동일한 상한
# frontend/src/api/extract.ts 의 IMAGE_EXT + '.pdf' 와 같은 목록으로 유지한다.
_ALLOWED_UPLOAD_EXT = {".jpg", ".jpeg", ".png", ".tif", ".pdf"}
# 신용장(MT700)은 SWIFT 전문 원문이라 이미지·PDF 가 아니라 텍스트로 올라온다.
# 서류 종류별로 허용 확장자가 다르므로 B/L 목록과 섞지 않는다 — 섞으면
# B/L 자리에 .txt 를 올릴 수 있게 되어 추출 경로가 엉뚱한 입력을 받는다.
_ALLOWED_LC_UPLOAD_EXT = {".txt"}


class CreateShipmentResponse(BaseModel):
    shipment_id: UUID


class CreateShipmentRequest(BaseModel):
    """선적 생성은 아직 입력을 받지 않는다. 본문 파라미터가 없으면 FastAPI가
    아예 검증 없이 몸통을 무시해, 아무 필드나 보내도(예: title: 12345) 조용히
    201을 돌려준다(P2-16) — 빈 스키마를 명시하고 extra 필드는 막는다."""

    model_config = ConfigDict(extra="forbid")


@app.post("/api/v1/shipments", response_model=CreateShipmentResponse, status_code=201)
async def create_shipment(
    _body: CreateShipmentRequest = CreateShipmentRequest(),
    session: AsyncSession = Depends(get_session),
) -> CreateShipmentResponse:
    shipment = Shipment(tenant_id=BOOTSTRAP_TENANT_ID, created_by=BOOTSTRAP_USER_ID)
    session.add(shipment)
    await session.commit()
    await session.refresh(shipment)
    return CreateShipmentResponse(shipment_id=shipment.id)


class ShipmentListItem(BaseModel):
    shipment_id: UUID
    status: ShipmentStatus
    bl_no: str | None
    cargo_control_no: str | None
    lc_no: str | None
    lc_expiry_date: date | None
    created_at: datetime
    updated_at: datetime


class ShipmentListResponse(BaseModel):
    shipments: list[ShipmentListItem]


def _to_list_item(s: Shipment) -> ShipmentListItem:
    return ShipmentListItem(
        shipment_id=s.id,
        status=s.status,
        bl_no=s.bl_no,
        cargo_control_no=s.cargo_control_no,
        lc_no=s.lc_no,
        lc_expiry_date=s.lc_expiry_date,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


@app.get("/api/v1/shipments", response_model=ShipmentListResponse)
async def list_shipments(
    session: AsyncSession = Depends(get_session),
) -> ShipmentListResponse:
    rows = await session.scalars(
        select(Shipment)
        .where(Shipment.tenant_id == BOOTSTRAP_TENANT_ID)
        .order_by(Shipment.created_at.desc())
    )
    return ShipmentListResponse(shipments=[_to_list_item(s) for s in rows])


class FieldValueOut(BaseModel):
    field_name: str
    value: str | None
    normalized_value: str | None
    confidence: float | None
    source_doc_id: UUID | None
    page: int | None
    bbox: tuple[float, float, float, float] | None
    extractor: str
    conflict_flag: bool


class DocumentOut(BaseModel):
    document_id: UUID
    doc_type: DocumentType
    file_name: str | None
    file_hash: str
    page_count: int
    version: int
    created_at: datetime


class ShipmentDetailResponse(ShipmentListItem):
    fields: list[FieldValueOut]
    documents: list[DocumentOut]
    # 마지막 "검증 실행"의 판정·하자확률 스냅샷. 한 번도 안 돌렸으면 [] / None.
    # save_verification이 저장한 것과 같은 모양(화면 도메인 타입)을 그대로 돌려준다.
    verdicts: list[Any] = []
    prediction: Any | None = None


@app.get("/api/v1/shipments/{shipment_id}", response_model=ShipmentDetailResponse)
async def get_shipment(
    shipment_id: UUID, session: AsyncSession = Depends(get_session)
) -> ShipmentDetailResponse:
    shipment = await _get_tenant_shipment(session, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="shipment not found")

    rows = await session.scalars(
        select(FieldValue).where(
            FieldValue.shipment_id == shipment_id, FieldValue.is_representative
        )
    )
    fields = []
    for fv in rows:
        bbox = None
        if fv.bbox_x1 is not None:
            bbox = (
                float(fv.bbox_x1),
                float(fv.bbox_y1),
                float(fv.bbox_x2),
                float(fv.bbox_y2),
            )
        fields.append(
            FieldValueOut(
                field_name=_field_name(fv.field_code),
                value=fv.value,
                normalized_value=fv.normalized_value,
                confidence=float(fv.confidence) if fv.confidence is not None else None,
                source_doc_id=fv.document_id,
                page=fv.page,
                bbox=bbox,
                extractor=_EXTRACTOR_FROM_DB[fv.extractor],
                conflict_flag=fv.conflict_flag,
            )
        )

    doc_rows = await session.scalars(
        select(Document).where(Document.shipment_id == shipment_id)
    )
    documents = [
        DocumentOut(
            document_id=d.id,
            doc_type=d.doc_type,
            file_name=d.original_filename,
            file_hash=d.file_hash,
            # ponytail: PDF 실제 페이지 수를 세려면 PDF 파싱 라이브러리가 필요하다.
            # 지금은 뷰어가 페이지 탭을 안 쓰므로 1로 고정 — 페이지별 탐색이 필요해지면 채운다.
            page_count=d.page_count or 1,
            version=d.version,
            created_at=d.created_at,
        )
        for d in doc_rows
    ]

    # 판정은 verdict·defect_prediction 테이블에 정규화해 넣지 않고 audit_log
    # 스냅샷으로만 남긴다(save_verification 주석의 rule 카탈로그 불일치 참고).
    # 읽을 때도 같은 자리에서 최신 1건을 꺼낸다 — 저장만 하고 안 돌려주면
    # 새로고침 시 판정이 사라져, 화면이 "검증 완료" 배지 옆에 "아직 검증을
    # 실행하지 않았습니다"를 같이 띄우고 S3 검증 게이트의 Critical 조건도
    # 항상 0건으로 읽힌다.
    snapshot = await session.scalar(
        select(AuditLog.after_state)
        .where(AuditLog.shipment_id == shipment_id, AuditLog.action == "VERIFY_RUN")
        .order_by(AuditLog.occurred_at.desc())
        .limit(1)
    )
    snapshot = snapshot or {}

    return ShipmentDetailResponse(
        **_to_list_item(shipment).model_dump(),
        fields=fields,
        documents=documents,
        # 저장할 때 키가 단수(verdict)다 — 화면 도메인 이름(verdicts)으로 맞춰 내보낸다.
        verdicts=snapshot.get("verdict") or [],
        prediction=snapshot.get("prediction"),
    )


@app.delete("/api/v1/shipments/{shipment_id}", status_code=204)
async def delete_shipment(
    shipment_id: UUID, session: AsyncSession = Depends(get_session)
) -> None:
    """선적을 지운다 — 시연 리허설 중 쌓인 테스트 데이터를 치울 방법이 UI에
    없었다(P2-16). 서류·필드값·판정·리포트는 전부 shipment FK가
    ON DELETE CASCADE라 DB가 같이 지운다(migrations/sql/02~07). audit_log만
    ON DELETE SET NULL이라 감사 기록은 선적이 지워져도 남는다(08_audit.sql).
    """
    shipment = await _get_tenant_shipment(session, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="shipment not found")
    await session.delete(shipment)
    await session.commit()


class DocumentUploadResponse(BaseModel):
    document_id: UUID


@app.post(
    "/api/v1/shipments/{shipment_id}/documents",
    response_model=DocumentUploadResponse,
    status_code=201,
)
async def upload_document(
    shipment_id: UUID,
    file: UploadFile = File(...),
    doc_type: DocumentType = Form(DocumentType.BL_DRAFT),
    session: AsyncSession = Depends(get_session),
) -> DocumentUploadResponse:
    """서류를 선적에 붙인다.

    `doc_type` 은 기본값이 `BL_DRAFT` 라 기존 호출부(B/L 업로드)는 그대로
    동작한다. 신용장을 올릴 때만 `LC_MT700` 을 넘긴다 — 종류를 안 받고
    전부 B/L 로 저장하면 나중에 어느 파일이 신용장인지 구분할 수가 없다.
    """
    shipment = await _get_tenant_shipment(session, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="shipment not found")

    allowed = (
        _ALLOWED_LC_UPLOAD_EXT if doc_type is DocumentType.LC_MT700 else _ALLOWED_UPLOAD_EXT
    )
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in allowed:
        raise HTTPException(
            status_code=415, detail=f"지원하지 않는 파일 형식입니다: {ext or '(확장자 없음)'}"
        )

    # file.read() 로 한 번에 다 읽으면, 30MB 제한을 검사하기 *전에* 파일
    # 전체가 이미 메모리에 올라간다 — 컨테이너 메모리 제한(256m)보다 큰
    # 파일을 올리면 크기 검사가 실행되기도 전에 OOM 이 난다. Content-Length
    # 헤더는 클라이언트가 얼마든지 속일 수 있어 그것만으로는 못 막으므로,
    # 청크 단위로 읽으면서 상한을 넘는 순간 바로 끊는다(P2-8).
    chunks: list[bytes] = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)
        if not chunk:
            break
        total += len(chunk)
        if total > _MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="파일이 30MB를 초과합니다")
        chunks.append(chunk)
    content = b"".join(chunks)
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="빈 파일은 업로드할 수 없습니다")

    file_hash, storage_uri = storage.save(settings.document_storage_root, content, ext)

    # 같은 선적에 같은 파일을 다시 올리는 건 에러가 아니라 재업로드다(기존 서류 재사용).
    # ponytail: select 후 insert라 이론상 동시 업로드 경합 창이 있다 — 지금은 단일 사용자
    # 시나리오라 무시하고, 동시 업로드가 실제 문제가 되면 on_conflict_do_nothing으로 바꾼다.
    existing = await session.scalar(
        select(Document).where(
            Document.shipment_id == shipment_id,
            Document.file_hash == file_hash,
            Document.source_page_from == 1,
        )
    )
    if existing is not None:
        return DocumentUploadResponse(document_id=existing.id)

    document = Document(
        tenant_id=shipment.tenant_id,
        shipment_id=shipment_id,
        doc_type=doc_type,
        original_filename=file.filename,
        mime_type=file.content_type,
        byte_size=len(content),
        file_hash=file_hash,
        storage_uri=storage_uri,
        uploaded_by=BOOTSTRAP_USER_ID,
    )
    session.add(document)
    await session.commit()
    await session.refresh(document)
    return DocumentUploadResponse(document_id=document.id)


@app.get("/api/v1/shipments/{shipment_id}/documents/{document_id}/file")
async def get_document_file(
    shipment_id: UUID,
    document_id: UUID,
    session: AsyncSession = Depends(get_session),
) -> FileResponse:
    document = await _get_tenant_document(session, document_id)
    if document is None or document.shipment_id != shipment_id:
        raise HTTPException(status_code=404, detail="document not found")
    path = Path(document.storage_uri)
    if not path.is_file():
        raise HTTPException(status_code=404, detail="file not found")
    return FileResponse(path, media_type=document.mime_type or "application/octet-stream")


class FieldValueIn(BaseModel):
    field_name: str
    value: str | None
    normalized_value: str | None = None
    # DB의 field_value_confidence_ck 와 같은 범위다 — 범위 밖 값은 여기서
    # 422로 걸러지지 않으면 그대로 DB 제약 위반(500)까지 굴러간다 (P2-9)
    confidence: float | None = Field(None, ge=0, le=1)
    # 정의 밖 값(오타 등)은 KeyError→500 대신 여기서 422로 걸러진다 (P1-6)
    grade: Literal["CONFIRMED", "ADVISORY", "REQUIRED", "NOT_FOUND"]
    extractor: str
    bbox: tuple[float, float, float, float] | None = None
    conflict_flag: bool = False

    @field_validator("bbox")
    @classmethod
    def _bbox_in_bounds(cls, v: tuple[float, float, float, float] | None):
        if v is None:
            return v
        x1, y1, x2, y2 = v
        # field_value_bbox_ck 와 같은 규칙: 0~1 정규화 좌표이고 좌상단이
        # 우하단보다 작아야 한다.
        if not (0 <= x1 < x2 <= 1 and 0 <= y1 < y2 <= 1):
            raise ValueError("bbox는 0~1 범위이고 x1<x2, y1<y2 여야 합니다")
        return v


class SaveFieldsRequest(BaseModel):
    document_id: UUID
    # DB의 field_value_page_ck 와 같은 범위다 (P2-9)
    page: int = Field(ge=1)
    fields: list[FieldValueIn]


class SaveFieldsResponse(BaseModel):
    saved: int
    # field_definition 카탈로그에 없는 field_name (예: total_freight) — 지어내지 않고 버린 목록
    skipped: list[str]


@app.put("/api/v1/shipments/{shipment_id}/fields", response_model=SaveFieldsResponse)
async def save_fields(
    shipment_id: UUID,
    body: SaveFieldsRequest,
    session: AsyncSession = Depends(get_session),
) -> SaveFieldsResponse:
    shipment = await _get_tenant_shipment(session, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="shipment not found")

    # body.document_id가 다른 선적 소속이면 그 문서의 bbox 근거를 이 선적
    # 필드값에 잘못 연결하게 된다 — 저장 전에 소속을 확인한다 (P1-7)
    document = await _get_tenant_document(session, body.document_id)
    if document is None or document.shipment_id != shipment_id:
        raise HTTPException(status_code=404, detail="document not found")

    known_codes = set((await session.scalars(select(FieldDefinition.code))).all())

    saved = 0
    skipped: list[str] = []
    for f in body.fields:
        code = _field_code(f.field_name)
        if code not in known_codes:
            skipped.append(f.field_name)
            continue

        has_evidence = f.bbox is not None
        extractor = _extractor_kind(f.extractor, has_evidence)
        # 미검출은 값을 갖지 않는다(field_value_not_found_ck) — 프론트가 실수로 값을
        # 같이 보내도 여기서 걸러 DB 제약 위반으로 요청 전체가 실패하지 않게 한다.
        value = f.value if f.grade != "NOT_FOUND" else None

        values = {
            "tenant_id": shipment.tenant_id,
            "shipment_id": shipment_id,
            "field_code": code,
            "document_id": body.document_id if has_evidence or f.extractor == "json" else None,
            "page": body.page if has_evidence else None,
            "bbox_x1": f.bbox[0] if f.bbox else None,
            "bbox_y1": f.bbox[1] if f.bbox else None,
            "bbox_x2": f.bbox[2] if f.bbox else None,
            "bbox_y2": f.bbox[3] if f.bbox else None,
            "value": value,
            "normalized_value": f.normalized_value,
            "confidence": f.confidence,
            "grade": _GRADE_TO_DB[f.grade],
            "extractor": extractor,
            "conflict_flag": f.conflict_flag,
            "is_representative": True,
        }
        stmt = pg_insert(FieldValue).values(**values)
        update_cols = {
            k: v
            for k, v in values.items()
            if k not in ("tenant_id", "shipment_id", "field_code", "is_representative")
        }
        stmt = stmt.on_conflict_do_update(
            index_elements=[FieldValue.shipment_id, FieldValue.field_code],
            index_where=FieldValue.is_representative,
            set_=update_cols,
        )
        await session.execute(stmt)
        saved += 1

        # 대시보드 카드가 읽는 선적 헤더의 bl_no는 어디서도 채워지지 않아
        # 항상 null이었다 — BL.BL_NO 필드가 저장될 때 같이 갱신한다. 빈 값으로
        # 덮어쓰면 이미 있던 번호가 지워지므로 값이 있을 때만 반영한다.
        # shipment_tenant_bl_no_key(UNIQUE tenant_id, bl_no) 위반을 피하려고
        # 대입 전에 같은 tenant 안에서 그 번호를 쓰는 다른 선적이 있는지 확인한다
        # (자기 자신 재저장은 제외). 있으면 헤더 갱신만 건너뛰고 필드값 저장은
        # 그대로 진행한다 — 번호 표시는 못 하지만 업로드가 500으로 죽지는 않는다.
        # ponytail: 사전 조회 후 대입까지는 원자적이지 않아 동시에 같은 bl_no로
        # 두 요청이 들어오면 여전히 유니크 제약 위반이 날 수 있다. 단일 사용자
        # 시연 환경이라 감수한다 — 막으려면 SELECT ... FOR UPDATE나 격리 수준 상향 필요.
        if code == "BL.BL_NO" and value:
            conflict = await session.scalar(
                select(Shipment.id).where(
                    Shipment.tenant_id == shipment.tenant_id,
                    Shipment.bl_no == value,
                    Shipment.id != shipment_id,
                )
            )
            if conflict is None:
                shipment.bl_no = value

    await session.commit()
    return SaveFieldsResponse(saved=saved, skipped=skipped)


# ── 검증 실행 결과 저장 ───────────────────────────────────────────
#
# "검증 실행"을 누르면 화면은 aiService(/verify)를 직접 호출해 판정을 얻지만,
# 그 결과가 여기 저장되기 전까지는 새로고침하면 사라지고 shipment.status도
# 영원히 DRAFT입니다. 이 엔드포인트가 그 상태 전이 + 감사 로그를 담당합니다.


class SaveVerificationRequest(BaseModel):
    # 화면 도메인 타입(Verdict[], DefectPrediction)을 그대로 받아 그대로 저장하는
    # 감사 로그 스냅샷이라 정확한 모양을 여기서 강제하지 않는다.
    verdict: Any
    prediction: Any | None = None
    override_reason: str | None = None


class SaveVerificationResponse(BaseModel):
    status: ShipmentStatus


@app.post(
    "/api/v1/shipments/{shipment_id}/verification",
    response_model=SaveVerificationResponse,
)
async def save_verification(
    shipment_id: UUID,
    body: SaveVerificationRequest,
    session: AsyncSession = Depends(get_session),
) -> SaveVerificationResponse:
    """검증 실행 결과를 저장하고 선적 상태를 전이시킨다.

    ponytail: verdict/prediction을 verdict·defect_prediction 테이블에 정규화해
    넣지 않고 audit_log에 스냅샷(JSONB)으로만 남긴다 — 이 게이트웨이의 rule
    카탈로그(R-UCP-*, migrations/sql/09_seed_catalog.sql)가 aiService 룰엔진의
    실제 카탈로그(D001 등, ai/defect_model/ruleEngine/rules.yaml)와 코드 체계가
    달라 verdict.rule_id FK를 채울 방법이 없다. 두 카탈로그를 맞추는 별도
    작업이 생기면 그때 정규화 저장(Verdict/VerdictEvidence)으로 바꾼다.
    """
    shipment = await _get_tenant_shipment(session, shipment_id)
    if shipment is None:
        raise HTTPException(status_code=404, detail="shipment not found")

    from_status = shipment.status
    if from_status in (ShipmentStatus.DRAFT, ShipmentStatus.REVIEWING):
        shipment.status = ShipmentStatus.VERIFIED

    session.add(
        ShipmentStatusHistory(
            shipment_id=shipment_id,
            from_status=from_status,
            to_status=shipment.status,
            is_forced=body.override_reason is not None,
            force_reason=body.override_reason,
            actor_id=BOOTSTRAP_USER_ID,
        )
    )
    session.add(
        AuditLog(
            tenant_id=shipment.tenant_id,
            actor_id=BOOTSTRAP_USER_ID,
            action="VERIFY_RUN",
            entity_type="shipment",
            entity_id=shipment_id,
            shipment_id=shipment_id,
            after_state={"verdict": body.verdict, "prediction": body.prediction},
        )
    )
    await session.commit()
    return SaveVerificationResponse(status=shipment.status)
