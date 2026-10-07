#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_filled_data_index.py

Rebuilds filled_data/index.json from whatever monthly .tar.gz packages
currently sit in filled_data/ (as written by fill_caida_as_rel.py).

Without this file, OfflineSnapshotProvider cannot load anything from
filled_data/ at all -- it requires index.json unconditionally and raises
FileNotFoundError before reading a single snapshot. There is deliberately no
incremental "patch one month" mode: every run rescans the whole directory and
writes a fresh index reflecting exactly what is there, so it can never drift
from the actual files -- run it again any time filled_data/ changes (a month
added, replaced with --allow-count-mismatch, or removed).

This script only reads manifest.json out of each package (via tarfile, no
extraction to disk) and hashes the package itself; it does not need pyarrow.

Usage:
    python3 scripts/build_filled_data_index.py
    python3 scripts/build_filled_data_index.py --filled-dir filled_data
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
import tarfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PACKAGE_PREFIX = "IIL-as-feature-snapshot"
PACKAGE_RE = re.compile(rf"^{re.escape(PACKAGE_PREFIX)}\.(\d{{4}}-\d{{2}})\.tar\.gz$")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def read_manifest_from_package(tar_path: Path) -> dict[str, Any] | None:
    """Read <month>/manifest.json out of a package without extracting it."""
    try:
        with tarfile.open(tar_path, "r:gz") as archive:
            member = next(
                (m for m in archive.getmembers() if m.name.endswith("/manifest.json")),
                None,
            )
            if member is None:
                return None
            handle = archive.extractfile(member)
            if handle is None:
                return None
            return json.load(handle)
    except (tarfile.TarError, OSError, json.JSONDecodeError) as exc:
        print(f"[build_filled_data_index] WARNING: could not read manifest from {tar_path}: {exc}", file=sys.stderr)
        return None


def build_entry(tar_path: Path, month: str) -> dict[str, Any] | None:
    manifest = read_manifest_from_package(tar_path)
    if manifest is None:
        print(f"[build_filled_data_index] SKIP {month}: no readable manifest.json in {tar_path.name}")
        return None

    snapshot = manifest.get("snapshot", {})
    return {
        "month": month,
        "package": tar_path.name,
        "size": tar_path.stat().st_size,
        "sha256": sha256_file(tar_path),
        "schema_version": manifest.get("schema_version"),
        "num_asns": snapshot.get("num_asns"),
        "source_dates": manifest.get("source_dates", {}),
        # Present only when fill_caida_as_rel.py added it; absent for a package
        # that was copied into filled_data/ without being filled.
        "caida_asrel_list_enrichment": manifest.get("caida_asrel_list_enrichment"),
    }


def find_packages(filled_dir: Path) -> list[tuple[Path, str]]:
    if not filled_dir.is_dir():
        raise FileNotFoundError(f"filled-dir not found: {filled_dir}")
    found = []
    for path in sorted(filled_dir.glob("*.tar.gz")):
        match = PACKAGE_RE.match(path.name)
        if not match:
            print(f"[build_filled_data_index] SKIP {path.name}: does not match {PACKAGE_PREFIX}.<YYYY-MM>.tar.gz")
            continue
        found.append((path, match.group(1)))
    return found


def build_index(filled_dir: Path) -> dict[str, Any]:
    entries = []
    for tar_path, month in find_packages(filled_dir):
        entry = build_entry(tar_path, month)
        if entry is not None:
            entries.append(entry)
            print(f"[build_filled_data_index] OK {month}: {tar_path.name}")

    entries.sort(key=lambda e: e["month"])
    return {
        "dataset": "AS Feature Snapshots (locally filled -- see scripts/README.md)",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "schema_version": "v1",
        # Deliberately no concept_doi / record_id: this is not the citable
        # published record, and columns filled in by fill_caida_as_rel.py
        # carry separate CAIDA Public-AUA terms (see each entry's
        # caida_asrel_list_enrichment and scripts/README.md).
        "package_prefix": PACKAGE_PREFIX,
        "months": [e["month"] for e in entries],
        "snapshots": entries,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        "--filled-dir",
        default="filled_data",
        help="Directory containing filled .tar.gz packages (default: filled_data)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    filled_dir = Path(args.filled_dir)

    index = build_index(filled_dir)
    if not index["snapshots"]:
        print(
            f"[build_filled_data_index] WARNING: no packages indexed under {filled_dir}; "
            f"wrote an index.json with an empty snapshot list.",
            file=sys.stderr,
        )

    index_path = filled_dir / "index.json"
    tmp_path = index_path.with_suffix(index_path.suffix + ".tmp")
    with tmp_path.open("w", encoding="utf-8", newline="\n") as f:
        json.dump(index, f, ensure_ascii=False, indent=2)
        f.write("\n")
    tmp_path.replace(index_path)

    print(f"[build_filled_data_index] wrote {index_path} ({len(index['snapshots'])} month(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
