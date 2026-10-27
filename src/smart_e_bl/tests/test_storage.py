"""P2-7: 저장이 원자적인지 확인한다 — 쓰다 죽어도 잘린 파일이 완성본
행세를 하면 안 된다.
"""

from pathlib import Path

from smart_e_bl.storage import save


def test_저장한_파일을_그대로_읽는다(tmp_path):
    digest, uri = save(str(tmp_path), b"hello", ".bin")

    assert Path(uri).read_bytes() == b"hello"
    assert digest == __import__("hashlib").sha256(b"hello").hexdigest()


def test_같은_내용은_두번_쓰지_않는다(tmp_path):
    _, uri1 = save(str(tmp_path), b"same", ".bin")
    path = Path(uri1)
    path.write_bytes(b"same")
    mtime_before = path.stat().st_mtime_ns

    _, uri2 = save(str(tmp_path), b"same", ".bin")

    assert uri1 == uri2
    assert path.stat().st_mtime_ns == mtime_before


def test_쓰다가_실패하면_임시파일만_남고_최종_경로는_비어있다(tmp_path, monkeypatch):
    import os

    real_replace = os.replace

    def _boom(*a, **kw):
        raise OSError("disk full")

    monkeypatch.setattr("smart_e_bl.storage.os.replace", _boom)

    with __import__("pytest").raises(OSError):
        save(str(tmp_path), b"partial", ".bin")

    leftovers = list(tmp_path.rglob("*"))
    assert not any(p.is_file() and not p.name.startswith(".") for p in leftovers)
    monkeypatch.setattr("smart_e_bl.storage.os.replace", real_replace)


def test_read_로컬_경로(tmp_path):
    from smart_e_bl.storage import read

    _, uri = save(str(tmp_path), b"local", ".bin")
    assert read(uri) == b"local"


def _fake_s3(monkeypatch, store):
    import io
    from unittest.mock import MagicMock

    from smart_e_bl.config import settings

    monkeypatch.setattr(settings, "storage_backend", "s3")
    monkeypatch.setattr(settings, "s3_document_bucket", "bkt")
    client = MagicMock()
    client.put_object.side_effect = lambda Bucket, Key, Body, **kw: store.update({Key: (Body, kw)})
    client.get_object.side_effect = lambda Bucket, Key: {"Body": io.BytesIO(store[Key][0])}
    monkeypatch.setattr("boto3.client", lambda *a, **kw: client)
    return client


def test_s3_저장과_읽기(tmp_path, monkeypatch):
    from smart_e_bl.storage import read

    store: dict = {}
    _fake_s3(monkeypatch, store)

    digest, uri = save(str(tmp_path), b"remote", ".pdf")

    assert uri == f"s3://bkt/documents/{digest[:2]}/{digest}.pdf"
    assert next(iter(store.values()))[1]["ServerSideEncryption"] == "AES256"
    assert read(uri) == b"remote"
    assert not list(tmp_path.iterdir())  # 로컬 디스크에는 쓰지 않는다


def test_s3_다른_버킷_URI는_거부(monkeypatch):
    from smart_e_bl.storage import read

    _fake_s3(monkeypatch, {})
    with __import__("pytest").raises(ValueError):
        read("s3://other/documents/aa/x.pdf")
