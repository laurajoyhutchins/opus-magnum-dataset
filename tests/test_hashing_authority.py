from __future__ import annotations

from pathlib import Path

from opus_corpus import hashing, serialization


def test_sha256_file_uses_stdlib_file_digest(tmp_path: Path, monkeypatch) -> None:
    path = tmp_path / "payload.bin"
    path.write_bytes(b"payload")
    calls: list[tuple[bytes, str]] = []

    class Digest:
        def hexdigest(self) -> str:
            return "sentinel-digest"

    def file_digest(handle, digest_name: str):
        calls.append((handle.read(), digest_name))
        return Digest()

    monkeypatch.setattr(hashing.hashlib, "file_digest", file_digest)

    assert hashing.sha256_file(path) == "sentinel-digest"
    assert calls == [(b"payload", "sha256")]


def test_canonical_json_serializer_consumes_shared_byte_primitive(monkeypatch) -> None:
    monkeypatch.setattr(
        serialization,
        "canonical_json_bytes",
        lambda value: b'{"shared":true}',
        raising=False,
    )

    serializer = serialization.CanonicalJsonSerializer()
    assert serializer.serialize_puzzle({"ignored": "value"}) == '{"shared":true}'
    assert serializer.serialize_solution({"ignored": "value"}) == '{"shared":true}'
