"""업로드 원본 파일 저장(로컬 디스크 또는 S3 — STORAGE_BACKEND).

콘텐츠 주소 저장(파일명이 아니라 내용의 sha256으로 경로를 정함)을 쓰는 이유는 둘:
같은 내용을 두 번 올려도 디스크에 중복 저장되지 않고, 사용자가 올린 파일명을 경로에
전혀 쓰지 않으므로 경로 조작(`../..` 등) 걱정이 없다.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path
from urllib.parse import urlparse

from smart_e_bl.config import settings


def save(root: str, content: bytes, ext: str) -> tuple[str, str]:
    """파일을 저장하고 (sha256_hex, storage_uri) 를 돌려준다.

    같은 해시가 이미 있으면 다시 쓰지 않는다 — 어차피 내용이 같다.
    """
    digest = hashlib.sha256(content).hexdigest()
    if settings.storage_backend == "s3":
        import boto3

        # 키는 로컬과 같이 내용 해시 — 같은 내용이면 같은 객체를 덮어쓸 뿐이다.
        # 실패 시 삭제는 하지 않는다: 키를 다른 문서가 공유할 수 있다.
        key = f"documents/{digest[:2]}/{digest}{ext}"
        boto3.client("s3", region_name=settings.aws_region).put_object(
            Bucket=settings.s3_document_bucket, Key=key, Body=content,
            ServerSideEncryption="AES256",
        )
        return digest, f"s3://{settings.s3_document_bucket}/{key}"
    path = Path(root) / digest[:2] / f"{digest}{ext}"
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        # 곧바로 최종 경로에 쓰면, 쓰는 도중 죽었을 때(디스크 가득 참·프로세스
        # 강제 종료) path.exists() 가 참인 잘린 파일이 남아 다음 호출이 그걸
        # 완성본으로 착각하고 재사용한다(P2-7). 같은 디렉터리에 임시로 쓰고
        # os.replace 로 옮긴다 — 이 교체는 원자적이라 절반만 쓰인 상태가
        # 밖에서 보이지 않는다.
        fd, tmp_name = tempfile.mkstemp(dir=path.parent, prefix=f".{digest}.")
        try:
            with os.fdopen(fd, "wb") as f:
                f.write(content)
            os.replace(tmp_name, path)
        except BaseException:
            Path(tmp_name).unlink(missing_ok=True)
            raise
    return digest, str(path)


def read(uri: str) -> bytes:
    """save() 가 돌려준 storage_uri 의 바이트를 읽는다(로컬 경로 또는 s3://)."""
    if not uri.startswith("s3://"):
        return Path(uri).read_bytes()
    import boto3

    parsed = urlparse(uri)
    bucket, key = parsed.netloc, parsed.path.lstrip("/")
    if not key or not settings.s3_document_bucket or bucket != settings.s3_document_bucket:
        raise ValueError("설정된 문서 버킷 외의 파일은 읽을 수 없습니다.")
    s3 = boto3.client("s3", region_name=settings.aws_region)
    return s3.get_object(Bucket=bucket, Key=key)["Body"].read(settings.max_document_bytes + 1)
