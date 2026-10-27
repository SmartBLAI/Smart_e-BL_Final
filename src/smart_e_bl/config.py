"""애플리케이션 설정.

.env 의 DATABASE_URL 하나를 접속 정보의 단일 출처로 씁니다.
드라이버는 용도에 따라 갈립니다 — API 는 asyncpg, 마이그레이션·워커는 psycopg.
"""

from functools import cached_property
from typing import Literal
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict

# AUTH_MODE=bootstrap 일 때 쓰는 고정 부트스트랩 테넌트/사용자.
# migrations/sql/10_bootstrap_tenant.sql 이 심는 값과 반드시 일치해야 합니다.
BOOTSTRAP_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
BOOTSTRAP_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql://smart_ebl:smart_ebl@localhost:5432/smart_ebl"

    # oidc: RS256 토큰 검증(미구성이면 보호 엔드포인트 503, fail-closed).
    # bootstrap: 토큰 없이 부트스트랩 ADMIN 으로 동작 — 로컬·시연 전용, 운영 금지.
    auth_mode: Literal["oidc", "bootstrap"] = "oidc"

    # OIDC access token(RS256). IdP 가 app_user_id(UUID) 커스텀 클레임을 발급해야 한다.
    oidc_issuer: str = ""
    oidc_audience: str = ""
    oidc_jwks_url: str = ""

    # S3 는 원본 파일 보관, 워커는 stateless AI 서비스를 호출한다.
    aws_region: str = "ap-northeast-2"
    s3_document_bucket: str = ""
    ai_service_url: str = ""
    ai_internal_token: str = ""
    max_document_bytes: int = 30 * 1024 * 1024

    # 기획안 6.1 이중 배포 프로파일. LLM 호출 경로가 갈립니다.
    deployment_profile: str = "saas"  # saas | onpremise

    # 기획안 5.1: 10페이지 문서 세트 60초(SaaS) / 120초(온프레미스)
    extraction_timeout_seconds: int = 60

    # 워커 폴링 간격
    worker_poll_seconds: float = 2.0

    # 업로드 원본 파일을 저장하는 경로. docker-compose는 DOCUMENT_STORAGE_ROOT를
    # /data/documents(볼륨 마운트)로 덮어쓴다. 로컬 기본값은 Docker 밖에서
    # uvicorn을 직접 띄워도(컨테이너 전용 절대경로가 없어) 바로 동작하도록
    # 실행 디렉터리 기준 상대경로로 둔다.
    document_storage_root: str = "./data/documents"

    # 원본 저장소. local: document_storage_root 디스크, s3: s3_document_bucket(SSE-S3).
    storage_backend: Literal["local", "s3"] = "local"

    # true 면 업로드 때 IngestJob 을 큐에 넣어 워커가 OCR 한다. 기본 false —
    # 프론트가 ai-service 를 동기 호출해 필드를 직접 저장하는 기존 흐름과 이중 기록되지 않게.
    ingest_on_upload: bool = False

    # F6 현실 대조 주기 점검(Phase 4d). 0 = 끔. 워커가 이 간격마다 최근 울산 선적을 재점검한다.
    reality_poll_interval_seconds: int = 0
    reality_poll_lookback_days: int = 30

    @cached_property
    def async_database_url(self) -> str:
        """FastAPI 용 asyncpg URL."""
        return self._with_driver("postgresql+asyncpg")

    @cached_property
    def sync_database_url(self) -> str:
        """Alembic·워커 용 psycopg URL."""
        return self._with_driver("postgresql+psycopg")

    def _with_driver(self, prefix: str) -> str:
        url = self.database_url
        for known in ("postgresql+asyncpg://", "postgresql+psycopg://", "postgresql://", "postgres://"):
            if url.startswith(known):
                return prefix + "://" + url[len(known) :]
        raise ValueError(f"지원하지 않는 DATABASE_URL 형식입니다: {url[:20]}...")


settings = Settings()
