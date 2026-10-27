# SSM Parameter Store IAM 설정

Jenkins 배포 파이프라인이 `/smart-ebl/prod/` 하위 파라미터를 읽어 `/deploy/.env` 를 생성합니다.
(관련: [Jenkinsfile](../../../Jenkinsfile) 의 `Fetch Secrets from SSM` 스테이지)

## 정책 파일

| 파일 | 부여 대상 | 용도 |
|---|---|---|
| `jenkins-ssm-read-policy.json` | Jenkins 에이전트(EC2) 역할 | 배포 시 파라미터 **읽기 전용** |
| `ssm-parameter-admin-policy.json` | 운영자 IAM 사용자/역할 | 파라미터 등록·수정 |
| `ec2-trust-policy.json` | 위 역할의 신뢰 정책 | EC2 가 역할을 가정할 수 있게 함 |

## 치환해야 하는 값

모든 파일의 `<ACCOUNT_ID>`, `<KMS_KEY_ID>` 를 실제 값으로 바꾸세요.
리전은 `ap-northeast-2` 로 고정되어 있습니다 (`.env` 의 `AWS_REGION` 과 일치해야 함).

```bash
aws sts get-caller-identity --query Account --output text     # ACCOUNT_ID
aws kms describe-key --key-id alias/smart-ebl-ssm --query KeyMetadata.KeyId --output text
```

## 적용 순서

### 1. KMS 키 생성

```bash
aws kms create-key --description "smart-ebl SSM SecureString" --region ap-northeast-2
```

```bash
aws kms create-alias --alias-name alias/smart-ebl-ssm --target-key-id <KMS_KEY_ID> --region ap-northeast-2
```

AWS 관리형 키(`alias/aws/ssm`)를 써도 동작하지만, 그 키는 계정 내 모든 SSM 파라미터에 공유되므로
`kms:Decrypt` 를 이 프로젝트 범위로 좁힐 수 없습니다. 고객 관리형 키(CMK) 사용을 권장합니다.

### 2. Jenkins 에이전트 역할 생성 및 연결

```bash
aws iam create-role --role-name smart-ebl-jenkins --assume-role-policy-document file://ec2-trust-policy.json
```

```bash
aws iam put-role-policy --role-name smart-ebl-jenkins --policy-name ssm-read --policy-document file://jenkins-ssm-read-policy.json
```

```bash
aws iam create-instance-profile --instance-profile-name smart-ebl-jenkins && aws iam add-role-to-instance-profile --instance-profile-name smart-ebl-jenkins --role-name smart-ebl-jenkins
```

인스턴스 프로파일을 EC2 에 연결하면 **에이전트에 AWS 액세스 키를 저장할 필요가 없습니다.**
임시 자격증명이 자동 발급·갱신됩니다.

### 3. 파라미터 등록

```bash
aws ssm put-parameter --name /smart-ebl/prod/POSTGRES_DB --type String --value smart_ebl --region ap-northeast-2
```

```bash
aws ssm put-parameter --name /smart-ebl/prod/POSTGRES_USER --type String --value smart_ebl --region ap-northeast-2
```

```bash
read -rs -p "DB password: " PW && aws ssm put-parameter --name /smart-ebl/prod/POSTGRES_PASSWORD --type SecureString --key-id alias/smart-ebl-ssm --value "$PW" --region ap-northeast-2 && unset PW
```

비밀번호는 셸 히스토리에 남지 않도록 `read -rs` 로 입력받습니다.
기존 값을 바꿀 때는 `--overwrite` 를 추가하세요.

### 4. 권한 검증

Jenkins 에이전트에서 실행해 파이프라인과 동일한 호출이 되는지 확인합니다.

```bash
aws ssm get-parameters-by-path --path /smart-ebl/prod/ --recursive --with-decryption --region ap-northeast-2 --query "Parameters[].Name" --output text
```

## 설계 노트

**최소 권한.** 읽기 정책에는 `ssm:GetParametersByPath` 하나만 넣었습니다. 파이프라인이 그것만 쓰기
때문입니다. 개별 파라미터 조회가 필요해지면 `ssm:GetParameter`, `ssm:GetParameters` 를 같은
`Resource` 에 추가하세요.

**경로 ARN 2개.** `GetParametersByPath` 는 경로 자체(`parameter/smart-ebl/prod`)와 하위
항목(`parameter/smart-ebl/prod/*`) 양쪽에 권한이 필요합니다. 파라미터 이름은 `/` 로 시작하지만
ARN 에서는 `parameter` 뒤에 슬래시가 하나만 붙습니다.

**`kms:ViaService` 조건.** 이 조건이 없으면 해당 역할이 KMS 키로 임의의 데이터를 복호화할 수
있습니다. 조건을 걸면 SSM 을 경유한 호출로만 제한됩니다.

**`DescribeParameters` 는 `Resource: "*"`.** 이 API 는 리소스 단위 제한을 지원하지 않는
계정 수준 호출이라 운영자 정책에만 넣었고, 배포용 읽기 정책에서는 뺐습니다.

**환경 분리.** `dev` 환경을 추가하려면 경로만 `/smart-ebl/dev/` 로 바꿔 정책을 복제하세요.
Jenkinsfile 의 `SSM_PATH` 도 함께 바꿔야 합니다.
