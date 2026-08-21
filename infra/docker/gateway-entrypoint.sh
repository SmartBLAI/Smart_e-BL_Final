#!/bin/sh
# POSTGRES_PASSWORD를 그대로 URL에 이어붙이면 비밀번호에 @/:# 같은 문자가
# 있을 때 접속 문자열이 깨진다(P2-13) — user:password 구간이 엉뚱한 곳에서
# 끊긴다. docker-compose.yml의 YAML 보간은 URL 인코딩을 못 하므로, 여기서
# Python 표준 라이브러리(urllib.parse.quote)로 인코딩해 DATABASE_URL을
# 조립한다. DATABASE_URL이 이미 주어졌으면(로컬에서 .env로 직접 띄울 때)
# 그 값을 그대로 쓴다.
set -eu

if [ -z "${DATABASE_URL:-}" ]; then
  export DATABASE_URL=$(python3 -c '
import os, urllib.parse as u
user = u.quote(os.environ["POSTGRES_USER"], safe="")
password = u.quote(os.environ["POSTGRES_PASSWORD"], safe="")
host = os.environ.get("POSTGRES_HOST", "postgres")
port = os.environ.get("POSTGRES_PORT", "5432")
db = os.environ.get("POSTGRES_DB", "smart_ebl")
print(f"postgresql://{user}:{password}@{host}:{port}/{db}")
')
fi

exec "$@"
