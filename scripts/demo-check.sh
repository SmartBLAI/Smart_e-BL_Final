#!/usr/bin/env bash
# 시연 촬영 전 점검. 통과하지 못한 항목이 하나라도 있으면 1을 돌려준다.
#
# 여기 있는 검사는 전부 실제로 한 번씩 촬영을 망칠 뻔했던 것들이다.
# 특히 [1] 유령 프로세스 — 호스트에 남은 uvicorn 이 127.0.0.1:5050 을 잡으면
# 브라우저 요청이 컨테이너 대신 그쪽으로 새고, 구버전 코드가 응답한다.
set -uo pipefail
cd "$(dirname "$0")/.."
FAIL=0
ok()   { printf "  \033[32m✓\033[0m %s\n" "$1"; }
bad()  { printf "  \033[31m✗\033[0m %s\n" "$1"; FAIL=1; }
warn() { printf "  \033[33m!\033[0m %s\n" "$1"; }

echo "[1] 포트를 가로채는 유령 프로세스"
for port in 5050 8080 8001; do
  strays=$(lsof -nP -iTCP:$port -sTCP:LISTEN 2>/dev/null | awk 'NR>1 && $1 !~ /^com\.docke/ {print $1" (pid "$2")"}')
  if [ -n "$strays" ]; then
    bad "$port 를 도커가 아닌 프로세스가 잡고 있습니다: $strays  → kill 하세요"
  else
    ok "$port — 도커만 리스닝"
  fi
done

echo "[2] 실행 중 컨테이너가 최신 이미지인지 (--build 만으로는 안 바뀝니다)"
for svc in ai-service api frontend; do
  running=$(docker inspect "smart-ebl-${svc}" --format '{{.Image}}' 2>/dev/null)
  built=$(docker images --no-trunc --format '{{.Repository}} {{.ID}}' | awk -v s="smart_e-bl_integrated-${svc}" '$1==s {print $2}')
  if [ -z "$running" ]; then bad "$svc 컨테이너가 없습니다"
  elif [ "$running" = "$built" ]; then ok "$svc — 최신"
  else bad "$svc — 구버전 실행 중. docker compose up -d --force-recreate --no-deps $svc"
  fi
done

echo "[3] 서비스 응답"
curl -sf http://127.0.0.1:5050/health >/dev/null && ok "aiService /health" || bad "aiService 응답 없음"
curl -sf -o /dev/null "http://127.0.0.1:8001/api/v1/shipments?limit=1" -H "X-Tenant-Id: demo" && ok "게이트웨이" || bad "게이트웨이 응답 없음"
curl -sf -o /dev/null http://localhost:8080/ && ok "프론트 :8080" || bad "프론트 응답 없음"
curl -sf -o /dev/null "http://localhost:8080/gw-api/api/v1/shipments?limit=1" -H "X-Tenant-Id: demo" && ok "프론트 → 게이트웨이 프록시" || bad "/gw-api 프록시 실패"

echo "[4] 브라우저가 aiService 를 직접 부를 수 있는지 (CORS + 토큰)"
allow=$(curl -s -D- -o /dev/null -X OPTIONS http://localhost:5050/verify \
  -H "Origin: http://localhost:8080" -H "Access-Control-Request-Method: POST" \
  -H "Access-Control-Request-Headers: content-type,x-internal-token" \
  | tr -d '\r' | awk -F': ' 'tolower($1)=="access-control-allow-origin"{print $2}')
[ "$allow" = "http://localhost:8080" ] && ok "CORS 허용: $allow" || bad "CORS preflight 실패 (받은 값: '${allow:-없음}')"
tok_env=$(grep -E '^AI_INTERNAL_TOKEN=' .env | cut -d= -f2-)
tok_vite=$(grep -E '^VITE_AI_INTERNAL_TOKEN=' .env | cut -d= -f2-)
[ -n "$tok_env" ] && [ "$tok_env" = "$tok_vite" ] && ok "X-Internal-Token 일치" || bad "AI_INTERNAL_TOKEN 과 VITE_AI_INTERNAL_TOKEN 이 다릅니다 (프론트 호출이 전부 401)"

echo "[5] 촬영용 데이터"
[ -f "docs/frontend/샘플_B_L_SHP-2026-0812-001.pdf" ] && ok "샘플 B/L" || bad "샘플 B/L 없음"
[ -f "docs/frontend/샘플_L_C_MT700_SHP-2026-0812-001.txt" ] && ok "샘플 L/C" || bad "샘플 L/C 없음"
ships=$(curl -s "http://127.0.0.1:8001/api/v1/shipments?limit=200" -H "X-Tenant-Id: demo" \
  | python3 -c "import sys,json;s=json.load(sys.stdin)['shipments'];print(len(s), sum(1 for x in s if x['bl_no']=='HLCUBUS2608001'))" 2>/dev/null)
count=${ships%% *}; squat=${ships##* }
if [ "${count:-0}" -gt 3 ]; then warn "선적 ${count}건 — 대시보드가 지저분합니다. S1 카드의 삭제 버튼으로 정리하세요"
else ok "선적 ${count}건"; fi
if [ "${squat:-0}" -gt 0 ]; then
  bad "B/L 번호 HLCUBUS2608001 을 이미 쓰는 선적이 있습니다 → 새로 올려도 대시보드 B/L 칸이 빈칸으로 찍힙니다"
else ok "HLCUBUS2608001 사용 가능"; fi

echo
[ $FAIL -eq 0 ] && echo "촬영해도 됩니다." || echo "위 ✗ 를 먼저 해결하세요."
exit $FAIL
