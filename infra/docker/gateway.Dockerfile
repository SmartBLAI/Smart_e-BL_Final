FROM python:3.12-slim

# uv 프로젝트라 pip 대신 uv sync 사용 (aiService는 requirements.txt라 pip를 씀 — 이 서비스만
# uv.lock이 있는 루트 pyproject를 씀). 빌드 컨텍스트는 repo 루트여야 한다
# (docker-compose.yml 의 context: . 참고) — pyproject.toml·uv.lock·src/ 가 전부 루트에 있음.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable

COPY infra/docker/gateway-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uv", "run", "uvicorn", "smart_e_bl.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
