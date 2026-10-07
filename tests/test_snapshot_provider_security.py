import hashlib
import io
import json
import tarfile

import pytest

from as_tagging import OfflineSnapshotProvider


DATE = "2025-01"
PACKAGE = f"IIL-as-feature-snapshot.{DATE}.tar.gz"
PARQUET = f"IIL-as-feature-snapshot.{DATE}.parquet"


def _write_archive(path, extra_members=None):
    members = {
        f"{DATE}/{PARQUET}": b"not-needed-for-metadata-tests",
        f"{DATE}/manifest.json": b'{"month": "2025-01"}',
        f"{DATE}/schema.json": b'{"schema_version": "v1"}',
    }
    members.update(extra_members or {})
    with tarfile.open(path, "w:gz") as archive:
        for name, content in members.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))


def _provider(tmp_path, *, checksum=None, extra_members=None):
    data_dir = tmp_path / "data"
    cache_dir = tmp_path / "cache"
    data_dir.mkdir()
    archive_path = data_dir / PACKAGE
    _write_archive(archive_path, extra_members)
    if checksum is None:
        checksum = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    index = {
        "snapshots": [
            {"month": DATE, "package": PACKAGE, "sha256": checksum}
        ]
    }
    (data_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")
    return OfflineSnapshotProvider(str(data_dir), cache_dir=str(cache_dir))


def test_valid_archive_is_verified_and_extracted(tmp_path):
    provider = _provider(tmp_path)

    assert provider.get_manifest(DATE) == {"month": DATE}
    assert (tmp_path / "cache" / DATE / PARQUET).is_file()


def test_checksum_mismatch_is_rejected_before_extraction(tmp_path):
    provider = _provider(tmp_path, checksum="0" * 64)

    with pytest.raises(ValueError, match="SHA-256 mismatch"):
        provider.get_manifest(DATE)

    assert not (tmp_path / "cache" / DATE).exists()


@pytest.mark.parametrize(
    "member_name",
    ["../escaped.txt", f"{DATE}/nested/escaped.txt", "/absolute.txt"],
)
def test_unsafe_archive_paths_are_rejected(tmp_path, member_name):
    provider = _provider(tmp_path, extra_members={member_name: b"unsafe"})

    with pytest.raises(ValueError, match="Unsafe or unexpected member"):
        provider.get_manifest(DATE)

    assert not (tmp_path / "escaped.txt").exists()
    assert not (tmp_path / "cache" / DATE).exists()


def test_archive_links_are_rejected(tmp_path):
    provider = _provider(tmp_path)
    archive_path = tmp_path / "data" / PACKAGE
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, content in {
            f"{DATE}/{PARQUET}": b"data",
            f"{DATE}/manifest.json": b"{}",
            f"{DATE}/schema.json": b"{}",
        }.items():
            info = tarfile.TarInfo(name)
            info.size = len(content)
            archive.addfile(info, io.BytesIO(content))
        link = tarfile.TarInfo(f"{DATE}/link")
        link.type = tarfile.SYMTYPE
        link.linkname = "../../outside"
        archive.addfile(link)
    digest = hashlib.sha256(archive_path.read_bytes()).hexdigest()
    provider._snapshots[DATE]["sha256"] = digest

    with pytest.raises(ValueError, match="Unsafe or unexpected member"):
        provider.get_manifest(DATE)


def test_cache_clear_rejects_path_traversal_and_preserves_unrelated_files(tmp_path):
    provider = _provider(tmp_path)
    provider.get_manifest(DATE)
    unrelated = tmp_path / "cache" / "keep.txt"
    unrelated.write_text("keep", encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid snapshot date"):
        provider.clear_cache("../outside")

    provider.clear_cache()
    assert unrelated.read_text(encoding="utf-8") == "keep"
    assert not (tmp_path / "cache" / DATE).exists()


def test_index_cannot_supply_package_paths(tmp_path):
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    index = {
        "snapshots": [
            {
                "month": DATE,
                "package": "../../outside.tar.gz",
                "sha256": "0" * 64,
            }
        ]
    }
    (data_dir / "index.json").write_text(json.dumps(index), encoding="utf-8")

    with pytest.raises(ValueError, match="Invalid snapshot package filename"):
        OfflineSnapshotProvider(str(data_dir), cache_dir=str(tmp_path / "cache"))
