"""애플리케이션 설정.

.env 의 DATABASE_URL 하나를 접속 정보의 단일 출처로 씁니다.
드라이버는 용도에 따라 갈립니다 — API 는 asyncpg, 마이그레이션·워커는 psycopg.
"""

from functools import cached_property
from uuid import UUID

from pydantic_settings import BaseSettings, SettingsConfigDict

# 인증이 생기기 전까지 쓰는 고정 부트스트랩 테넌트/사용자.
# migrations/sql/10_bootstrap_tenant.sql 이 심는 값과 반드시 일치해야 합니다.
BOOTSTRAP_TENANT_ID = UUID("00000000-0000-0000-0000-000000000001")
BOOTSTRAP_USER_ID = UUID("00000000-0000-0000-0000-000000000002")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_file_encoding="utf-8", extra="ignore"
    )

    database_url: str = "postgresql://smart_ebl:smart_ebl@localhost:5432/smart_ebl"

    # 기획안 6.1 이중 배포 프로파일. LLM 호출 경로가 갈립니다.
    deployment_profile: str = "saas"  # saas | onpremise

    # 기획안 5.1: 10페이지 문서 세트 60초(SaaS) / 120초(온프레미스)
    extraction_timeout_seconds: int = 60

    # 워커가 한 번에 집어가는 잡 수와 폴링 간격
    worker_batch_size: int = 1
    worker_poll_seconds: float = 2.0

    # 업로드 원본 파일을 저장하는 경로. docker-compose는 DOCUMENT_STORAGE_ROOT를
    # /data/documents(볼륨 마운트)로 덮어쓴다. 로컬 기본값은 Docker 밖에서
    # uvicorn을 직접 띄워도(컨테이너 전용 절대경로가 없어) 바로 동작하도록
    # 실행 디렉터리 기준 상대경로로 둔다.
    document_storage_root: str = "./data/documents"

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
