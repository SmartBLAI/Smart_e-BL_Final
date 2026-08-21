# backend/api — 사용 안 함 (범위 밖)

초기 기획 당시 Node/Express로 계획했던 게이트웨이 스캐폴드입니다. 실제 구현은
`src/smart_e_bl`(Python/FastAPI)로 대체되었고, `docker-compose.yml`의 `api`
서비스도 그쪽을 빌드합니다(`docker-compose.yml` 상단 주석 참고).

이 디렉터리는 코드 없이 `.gitkeep`과 `.env.example`만 있어 "명세-구현 괴리"로
보일 수 있어 남겨두지 않고 여기 상태를 적어둡니다. `.env.example`의
JWT·PKI·블록체인 변수는 실제로 읽는 코드가 없으므로 채우지 마세요.
