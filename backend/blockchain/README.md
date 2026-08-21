# backend/blockchain — 사용 안 함 (범위 밖)

초기 기획 당시 계획했던 스마트컨트랙트/Hardhat 스캐폴드입니다. 현재 배포
구성(`docker-compose.yml`)에는 이 서비스가 없고, eBL 정합성 검증은
`backend/aiService`의 규칙 엔진(`ruleEngine/`)으로 대체되었습니다.

이 디렉터리는 코드 없이 `.gitkeep`과 `.env.example`만 있어 "명세-구현 괴리"로
보일 수 있어 남겨두지 않고 여기 상태를 적어둡니다. `.env.example`의 배포용
지갑 개인키·Etherscan 키 변수는 실제로 읽는 코드가 없으므로 채우지 마세요.
