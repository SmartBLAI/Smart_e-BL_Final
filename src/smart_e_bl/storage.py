"""업로드 원본 파일의 로컬 디스크 저장.

콘텐츠 주소 저장(파일명이 아니라 내용의 sha256으로 경로를 정함)을 쓰는 이유는 둘:
같은 내용을 두 번 올려도 디스크에 중복 저장되지 않고, 사용자가 올린 파일명을 경로에
전혀 쓰지 않으므로 경로 조작(`../..` 등) 걱정이 없다.
"""

from __future__ import annotations

import hashlib
import os
import tempfile
from pathlib import Path


def save(root: str, content: bytes, ext: str) -> tuple[str, str]:
    """파일을 저장하고 (sha256_hex, storage_uri) 를 돌려준다.

    같은 해시가 이미 있으면 다시 쓰지 않는다 — 어차피 내용이 같다.
    """
    digest = hashlib.sha256(content).hexdigest()
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
