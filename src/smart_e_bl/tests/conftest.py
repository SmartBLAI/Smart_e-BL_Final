"""게이트웨이(src/smart_e_bl) 스모크 테스트 픽스처.

실제 Postgres가 필요합니다 (settings.database_url — .env 또는 기본값인
로컬 docker-compose postgres). alembic 마이그레이션과 부트스트랩 테넌트
시드(migrations/sql/10_bootstrap_tenant.sql)가 이미 적용돼 있어야 합니다 —
Jenkinsfile의 Migrate Schema 스테이지가 CI에서 이 순서를 보장합니다(P1-10).

⚠ 개발용 DB에 그대로 쓰기 때문에, 테스트가 만든 선적은 테스트가 직접
  치웁니다(아래 client 픽스처). 정리를 안 하면 실행할 때마다 대시보드에
  내용 없는 빈 선적이 쌓입니다 — 실제로 한 번에 11건이 남은 적이 있습니다.
"""

import httpx
import pytest

from smart_e_bl.api.main import app
from smart_e_bl.config import settings


async def _shipment_ids(client: httpx.AsyncClient) -> set[str]:
    res = await client.get("/api/v1/shipments")
    res.raise_for_status()
    return {s["shipment_id"] for s in res.json()["shipments"]}


@pytest.fixture(autouse=True)
def _bootstrap_auth(monkeypatch):
    # 기존 스모크 테스트는 토큰 없이 부트스트랩 ADMIN 으로 돈다.
    monkeypatch.setattr(settings, "auth_mode", "bootstrap")


@pytest.fixture
async def client():
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as ac:
        before = await _shipment_ids(ac)
        try:
            yield ac
        finally:
            # 테스트 시작 시점에 없던 선적만 지웁니다. 앞서 있던 것(시연용
            # 실제 데이터)은 건드리지 않습니다 — 통째로 비우면 팀이 올려둔
            # 선적까지 같이 날아갑니다.
            #
            # DB를 직접 지우지 않고 DELETE 엔드포인트를 쓰는 이유: 서류·필드값·
            # 판정을 같이 지우는 규칙(CASCADE + 파일 삭제)이 이미 거기 있어서,
            # 여기서 다시 쓰면 두 곳이 어긋납니다. 삭제 자체를 시험하는
            # 테스트라 이미 지워졌을 수도 있으므로 실패는 무시합니다.
            for shipment_id in await _shipment_ids(ac) - before:
                await ac.delete(f"/api/v1/shipments/{shipment_id}")
