pipeline {
  agent any

  environment {
    // 배포 대상 경로. .env 는 git 이 아니라 SSM Parameter Store 에서 생성합니다.
    DEPLOY_DIR = '/deploy'

    // SSM Parameter Store 설정.
    // 이 경로 하위의 파라미터 이름이 그대로 .env 의 키가 됩니다.
    //   /smart-ebl/prod/POSTGRES_PASSWORD -> POSTGRES_PASSWORD=...
    SSM_PATH   = '/smart-ebl/prod/'
    AWS_REGION = 'ap-northeast-2'
  }

  stages {
    stage('Checkout') {
      steps {
        checkout scm
      }
    }

    stage('Run aiService Tests') {
      steps {
        sh '''
          set -eu
          cd "$WORKSPACE/backend/aiService"

          # requirements.txt 만 쓰는 트리라(uv/lock 파일 없음) 배포와 겹치지
          # 않게 워크스페이스 안에 임시 venv 를 만든다.
          python3 -m venv .ci-venv
          . .ci-venv/bin/activate
          pip install --quiet -r requirements.txt
          pytest -q
          deactivate
          rm -rf .ci-venv
        '''
      }
    }

    stage('Verify Compose Config') {
      steps {
        sh '''
          set -eu
          docker compose -f "$WORKSPACE/docker-compose.yml" config --quiet
        '''
      }
    }

    stage('Deploy to Host') {
      steps {
        sh '''
          set -eu

          # .env 는 gitignore 대상이라 워크스페이스에 없습니다.
          # --delete 와 함께 rsync 하면 서버의 .env 가 지워지므로 반드시 제외합니다.
          rsync -a --delete --exclude='.git' --exclude='.env' --exclude='__pycache__/' --exclude='.venv/' --exclude='.ci-venv/' --exclude='node_modules/' "$WORKSPACE/" "$DEPLOY_DIR/"
        '''
      }
    }

    stage('Fetch Secrets from SSM') {
      steps {
        // 값을 콘솔에 출력하지 않습니다. sh 블록에 set -x 를 추가하면
        // 비밀번호가 Jenkins 빌드 로그에 그대로 남으니 주의하세요.
        sh '''
          set -eu
          umask 077

          command -v aws >/dev/null 2>&1 || { echo "ERROR: Jenkins 에이전트에 AWS CLI 가 없습니다." >&2; exit 1; }

          raw=$(mktemp)
          env_tmp=$(mktemp)
          trap 'rm -f "$raw" "$env_tmp"' EXIT

          aws ssm get-parameters-by-path --path "$SSM_PATH" --recursive --with-decryption --region "$AWS_REGION" --query "Parameters[].[Name,Value]" --output text > "$raw"

          # "경로/키<TAB>값" -> "키=값".
          # - 값 안에 탭이 있어도 첫 번째 탭만 구분자로 씁니다.
          # - $ 는 $$ 로 이스케이프합니다. compose 가 .env 값에 변수 치환을 적용하기 때문에
          #   그냥 두면 p@ss$w0rd 가 p@ss 로 잘려서 SSM 값과 다른 비밀번호로 DB 가 만들어집니다.
          awk '{ i = index($0, "\\t"); if (i == 0) next; k = substr($0, 1, i - 1); v = substr($0, i + 1); sub(/.*\\//, "", k); gsub(/[$]/, "$$", v); print k "=" v }' "$raw" > "$env_tmp"

          count=$(wc -l < "$env_tmp" | tr -d " ")
          if [ "$count" -eq 0 ]; then
            echo "ERROR: $SSM_PATH 하위에 파라미터가 없습니다. 경로와 IAM 권한(ssm:GetParametersByPath, kms:Decrypt)을 확인하세요." >&2
            exit 1
          fi

          # 여기까지 성공했을 때만 교체합니다. 중간에 실패하면 기존 .env 가 그대로 남습니다.
          mv "$env_tmp" "$DEPLOY_DIR/.env"
          chmod 600 "$DEPLOY_DIR/.env"
          echo "SSM 에서 파라미터 ${count}개를 가져와 .env 를 생성했습니다."
        '''
      }
    }

    stage('Start Database') {
      steps {
        sh '''
          set -eu
          cd "$DEPLOY_DIR"

          # SSM 스테이지가 정상 동작하면 항상 통과합니다. 해당 스테이지를 비활성화한 경우를 대비한 안전장치입니다.
          if [ ! -f .env ]; then
            echo "ERROR: $DEPLOY_DIR/.env 가 없습니다. SSM 스테이지를 확인하세요 (.env.example 참고)." >&2
            exit 1
          fi

          # postgres만 먼저 띄웁니다 — api/ai-service를 마이그레이션 전에 같이
          # 올리면, 그 사이 스키마가 없는 DB로 기동해 헬스체크 실패 루프에
          # 빠집니다(P1-10). 나머지 서비스는 Migrate Schema 뒤 Start Services에서 올립니다.
          docker compose up -d postgres
        '''
      }
    }

    stage('Migrate Schema') {
      steps {
        sh '''
          set -eu
          cd "$DEPLOY_DIR"

          # DB가 뜬 뒤에 실행해야 합니다. Start Database 뒤, 애플리케이션 기동 앞.
          ok=""
          for i in $(seq 1 30); do
            status=$(docker inspect -f '{{.State.Health.Status}}' smart-ebl-postgres 2>/dev/null || echo starting)
            if [ "$status" = "healthy" ]; then
              ok=1
              break
            fi
            sleep 5
          done
          # 대기가 끝나도 healthy가 아니면 여기서 멈춥니다 — 그냥 넘어가면
          # 아직 준비 안 된 DB에 마이그레이션을 돌리게 됩니다(P2-12).
          if [ -z "$ok" ]; then
            echo "ERROR: smart-ebl-postgres 가 150초 내에 healthy 상태가 되지 않았습니다." >&2
            docker compose logs --tail=50 postgres >&2
            exit 1
          fi

          uv run alembic upgrade head
          uv run alembic current
        '''
      }
    }

    stage('Gateway Smoke Tests') {
      steps {
        sh '''
          set -eu
          cd "$DEPLOY_DIR"

          # 마이그레이션 직후, 실서비스 기동 전에 돌립니다 — 실제 Postgres와
          # .env(DATABASE_URL)가 필요하고, 여기서 실패하면 깨진 스키마/부트스트랩
          # 시드로 서비스를 올리는 것을 막을 수 있습니다(P1-11).
          uv run pytest src/smart_e_bl/tests/ -q
        '''
      }
    }

    stage('Start Services') {
      steps {
        sh '''
          set -eu
          cd "$DEPLOY_DIR"

          # --pull 을 쓰지 않습니다. 이미지가 갱신되면 DB 컨테이너가 재생성되어
          # 배포마다 예기치 않은 다운타임이 발생합니다. 설정이 바뀐 서비스만 재생성됩니다.
          # --build 는 필요합니다 — 없으면 소스를 갱신해도 애플리케이션 이미지가
          # 구버전 그대로 남아, "고쳤는데 서버엔 반영 안 됨" 상태가 됩니다.
          # 로컬 Dockerfile로 빌드하는 서비스만 재빌드되므로 postgres 처럼
          # 레지스트리 이미지를 쓰는 서비스는 여전히 영향받지 않습니다.
          # postgres는 이미 떠 있어(Start Database) 마이그레이션이 끝난
          # 뒤에야 나머지 서비스가 기동됩니다.
          docker compose up -d --build
        '''
      }
    }

    stage('Health Check') {
      steps {
        sh '''
          set -eu
          cd "$DEPLOY_DIR"

          for pair in "smart-ebl-postgres:postgres" "smart-ebl-ai-service:ai-service" "smart-ebl-api:api" "smart-ebl-frontend:frontend"; do
            container="${pair%%:*}"
            service="${pair##*:}"
            ok=""
            for i in $(seq 1 30); do
              status=$(docker inspect -f '{{.State.Health.Status}}' "$container" 2>/dev/null || echo starting)
              if [ "$status" = "healthy" ]; then
                ok=1
                break
              fi
              sleep 5
            done
            if [ -z "$ok" ]; then
              echo "ERROR: $container 가 150초 내에 healthy 상태가 되지 않았습니다." >&2
              docker compose logs --tail=50 "$service" >&2
              exit 1
            fi
          done
        '''
      }
    }
  }

  post {
    success { echo "배포 완료: ${env.DEPLOY_DIR}" }
    failure { echo '배포 실패' }
  }
}
