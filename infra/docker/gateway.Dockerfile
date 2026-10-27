FROM python:3.12-slim

# uv 프로젝트라 pip 대신 uv sync 사용 (ai 서비스는 requirements.txt라 pip를 씀 — 이 서비스만
# uv.lock이 있는 루트 pyproject를 씀). 빌드 컨텍스트는 repo 루트여야 한다
# (docker-compose.yml 의 context: . 참고) — pyproject.toml·uv.lock·src/ 가 전부 루트에 있음.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app
# 비루트 사용자는 uv 캐시(HOME)가 없으므로 uv run 대신 venv 의 uvicorn 을 직접 실행한다.
ENV PATH="/app/.venv/bin:$PATH"
COPY pyproject.toml uv.lock README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev --no-editable

COPY infra/docker/gateway-entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh

# 비루트 실행. /data/documents 는 named volume 이 처음 마운트될 때 이미지 안
# 디렉터리의 소유자를 물려받으므로 여기서 미리 만들어 chown 한다.
RUN useradd --system --uid 10001 smart-ebl \
    && mkdir -p /data/documents \
    && chown -R smart-ebl:smart-ebl /app /data/documents
USER smart-ebl

EXPOSE 8000
ENTRYPOINT ["/entrypoint.sh"]
CMD ["uvicorn", "smart_e_bl.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
