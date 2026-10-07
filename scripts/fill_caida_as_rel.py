#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fill_caida_as_rel.py

The public AS feature snapshots omit four list-valued fields derived from
the CAIDA AS Relationships Dataset:

    caida-asrel_provider_list
    caida-asrel_customer_list
    caida-asrel_peer_list
    caida-asrel_cone_as_list

This script reconstructs those fields locally from CAIDA data obtained by
the user.  It accepts either a monthly ``.tar.gz`` snapshot package or an
extracted Parquet snapshot.  The exact CAIDA date is normally read from the
package's ``manifest.json``; ``--date`` can override it.

Two ways to provide the CAIDA inputs are supported:

1. Let the script download the two dated files directly from CAIDA.  This is
   the default when ``--as-rel2`` and ``--ppdc-ases`` are omitted.  Downloads
   go to a temporary directory and are deleted after the run unless
   ``--cache-dir`` is supplied.
2. Supply files already obtained from CAIDA with both ``--as-rel2`` and
   ``--ppdc-ases``.  Compressed ``.bz2`` and uncompressed text are accepted.

The reconstructed lists are JSON-encoded strings, matching the snapshot
schema.  Before writing, the script checks that every reconstructed list
length agrees with the corresponding aggregate count already present in the
public snapshot.  A mismatch aborts by default.

Examples:

    # Fill a monthly package; infer the CAIDA date from its manifest.
    python3 scripts/fill_caida_as_rel.py \\
        --input data/IIL-as-feature-snapshot.2026-07.tar.gz

    # Persist/reuse the two CAIDA downloads instead of using temp files.
    python3 scripts/fill_caida_as_rel.py \\
        --input data/IIL-as-feature-snapshot.2026-07.tar.gz \\
        --cache-dir ~/.cache/caida-as-relationships

    # Use CAIDA files already downloaded by the user.
    python3 scripts/fill_caida_as_rel.py \\
        --input path/to/IIL-as-feature-snapshot.2026-07.parquet \\
        --date 20260701 \\
        --as-rel2 path/to/20260701.as-rel2.txt.bz2 \\
        --ppdc-ases path/to/20260701.ppdc-ases.txt.bz2

PyArrow is required to read and write Parquet files:

    python3 -m pip install pyarrow
"""

from __future__ import annotations

import argparse
import bz2
import contextlib
import datetime as dt
import hashlib
import json
import os
import re
import shutil
import sys
import tarfile
import tempfile
import urllib.error
import urllib.request
from collections import defaultdict
from pathlib import Path
from typing import IO, Iterable


CAIDA_BASE_URL = "https://publicdata.caida.org/datasets/as-relationships"
RELATIVE_URLS = {
    "as_rel2": "serial-2/{date}.as-rel2.txt.bz2",
    "ppdc_ases": "serial-1/{date}.ppdc-ases.txt.bz2",
}

LIST_TO_COUNT = {
    "caida-asrel_provider_list": "caida-asrel_provider_cnt",
    "caida-asrel_customer_list": "caida-asrel_customer_cnt",
    "caida-asrel_peer_list": "caida-asrel_peer_cnt",
    "caida-asrel_cone_as_list": "caida-asrel_cone_as_cnt",
}

NOTICE_RULE = "=" * 79
LICENSE_NOTICE = f"""\
{NOTICE_RULE}
CAIDA AS Relationships Dataset Notice
{NOTICE_RULE}

This script uses a CAIDA AS Relationships Dataset snapshot that you provide,
or that it downloads on your behalf, from CAIDA's public archive:

{CAIDA_BASE_URL}/

Before accessing the dataset for the first time, visit the CAIDA dataset
page and follow its Data Access link to submit CAIDA's user-information
form:

https://www.caida.org/catalog/datasets/request_user_info_forms/as_relationships/

If you already obtained the CAIDA files you plan to use, you may proceed to
the notice below.

Dataset catalog page:
https://www.caida.org/catalog/datasets/as-relationships/

Use of the dataset is subject to the CAIDA Acceptable Use Agreement for
Publicly Accessible Datasets (Public-AUA):

https://www.caida.org/about/legal/aua/public_aua/

If you create a publication using this dataset, CAIDA requires you to cite
the dataset and report the publication to CAIDA.  CAIDA's suggested citation
form is:

    The CAIDA AS Relationships Dataset, <date range used>
    https://www.caida.org/catalog/datasets/as-relationships/

This project does not redistribute the CAIDA AS Relationships files. You
are responsible for obtaining the data separately (yourself, or via this
script's default download, which fetches it from CAIDA's own public
archive) and complying with the applicable CAIDA terms.

Filling these fields does not replace the license that applies to
IIL-AS-Tagging itself:

https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE

The original IIL-AS-Tagging content remains subject to the IIL-AS-Tagging
repository's license, while the four AS lists added by this script
(caida-asrel_provider_list, caida-asrel_customer_list,
caida-asrel_peer_list, and caida-asrel_cone_as_list), which are taken
directly from the CAIDA AS Relationships Dataset, remain subject to the
applicable CAIDA Public-AUA terms.

{NOTICE_RULE}"""


class FillError(RuntimeError):
    """A user-facing reconstruction error."""


def show_license_notice(auto_yes: bool) -> None:
    print()
    print(LICENSE_NOTICE)
    print()
    if auto_yes:
        print("(--yes passed: notice acknowledged non-interactively)")
        print()
        return
    try:
        input(">>> Press Enter to acknowledge this notice and continue, or Ctrl+C to exit. ")
    except (EOFError, KeyboardInterrupt):
        raise FillError(
            "Notice not acknowledged; exiting without contacting CAIDA or writing output."
        ) from None
    print()


def normalize_date(value: str) -> str:
    """Return a CAIDA snapshot date as YYYYMMDD."""
    compact = value.strip().replace("-", "")
    if not re.fullmatch(r"\d{8}", compact):
        raise FillError(f"Invalid date {value!r}; expected YYYYMMDD or YYYY-MM-DD")
    try:
        dt.datetime.strptime(compact, "%Y%m%d")
    except ValueError as exc:
        raise FillError(f"Invalid date {value!r}: {exc}") from exc
    return compact


def infer_date_from_caida_filename(path: Path) -> str | None:
    match = re.search(r"(?<!\d)(\d{8})(?!\d)", path.name)
    return normalize_date(match.group(1)) if match else None


def date_from_manifest(manifest: dict) -> str | None:
    value = manifest.get("source_dates", {}).get("CAIDA AS Relationship")
    if value is None:
        return None
    return normalize_date(str(value))


def open_maybe_bz2(path: Path) -> IO[str]:
    if path.name.lower().endswith(".bz2"):
        return bz2.open(path, "rt", encoding="utf-8")
    return path.open("rt", encoding="utf-8")


def _asn_sort_key(asn: str) -> tuple[int, int | str]:
    try:
        return (0, int(asn))
    except ValueError:
        return (1, asn)


def parse_relationships(path: Path) -> dict[str, dict[str, list[str]]]:
    """Parse a CAIDA as-rel2 file into provider/customer/peer lists.

    In CAIDA's format, ``provider|customer|-1`` is a provider-to-customer
    edge.  Other relationship values are treated as peer-to-peer, matching
    the snapshot generator used to produce the aggregate count fields.
    """
    providers: dict[str, set[str]] = defaultdict(set)
    customers: dict[str, set[str]] = defaultdict(set)
    peers: dict[str, set[str]] = defaultdict(set)
    seen_asns: set[str] = set()

    with open_maybe_bz2(path) as source:
        for line_number, raw_line in enumerate(source, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            fields = line.split("|")
            if len(fields) < 3:
                raise FillError(
                    f"Malformed AS relationship record at {path}:{line_number}: {line!r}"
                )
            left, right, relationship = fields[0].strip(), fields[1].strip(), fields[2].strip()
            if not left or not right:
                raise FillError(
                    f"Missing ASN at {path}:{line_number}: {line!r}"
                )
            seen_asns.update((left, right))
            if relationship == "-1":
                customers[left].add(right)
                providers[right].add(left)
            else:
                peers[left].add(right)
                peers[right].add(left)

    relationships: dict[str, dict[str, list[str]]] = {}
    for asn in seen_asns:
        relationships[asn] = {
            "provider": sorted(providers[asn], key=_asn_sort_key),
            "customer": sorted(customers[asn], key=_asn_sort_key),
            "peer": sorted(peers[asn], key=_asn_sort_key),
        }
    return relationships


def parse_customer_cones(path: Path) -> dict[str, list[str]]:
    """Parse CAIDA's ppdc-ases file while preserving its AS order."""
    cones: dict[str, list[str]] = {}
    with open_maybe_bz2(path) as source:
        for line_number, raw_line in enumerate(source, start=1):
            line = raw_line.strip()
            if not line or line.startswith("#"):
                continue
            values = line.split()
            if not values:
                continue
            root = values[0]
            deduplicated: list[str] = []
            seen: set[str] = set()
            for asn in values:
                if asn not in seen:
                    seen.add(asn)
                    deduplicated.append(asn)
            if deduplicated[0] != root:
                raise FillError(
                    f"Malformed customer-cone record at {path}:{line_number}: {line!r}"
                )
            cones[root] = deduplicated
    return cones


def _download(url: str, destination: Path) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    request = urllib.request.Request(
        url,
        headers={"User-Agent": "IIL-AS-feature-snapshot-local-reconstruction/1.0"},
    )
    print(f"[fill_caida_as_rel] downloading {url}")
    try:
        with urllib.request.urlopen(request) as response, temporary.open("wb") as output:
            shutil.copyfileobj(response, output)
        os.replace(temporary, destination)
    except (OSError, urllib.error.URLError) as exc:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass
        raise FillError(f"Could not download {url}: {exc}") from exc


def acquire_caida_files(
    args: argparse.Namespace,
    snapshot_date: str,
    stack: contextlib.ExitStack,
) -> tuple[Path, Path, str, dict[str, str]]:
    supplied = bool(args.as_rel2 or args.ppdc_ases)
    if supplied:
        if not (args.as_rel2 and args.ppdc_ases):
            raise FillError("Pass both --as-rel2 and --ppdc-ases, or neither")
        relation_path = Path(args.as_rel2)
        cone_path = Path(args.ppdc_ases)
        for path in (relation_path, cone_path):
            if not path.is_file():
                raise FillError(f"CAIDA input file not found: {path}")
            file_date = infer_date_from_caida_filename(path)
            if file_date and file_date != snapshot_date:
                raise FillError(
                    f"{path.name} looks like CAIDA snapshot {file_date}, but the target "
                    f"snapshot date (from --date or manifest.json) is {snapshot_date}. "
                    f"Supply the CAIDA files for {snapshot_date}."
                )
        return relation_path, cone_path, "user_provided_caida_snapshot", {}

    urls = {
        key: f"{CAIDA_BASE_URL}/{template.format(date=snapshot_date)}"
        for key, template in RELATIVE_URLS.items()
    }
    if args.cache_dir:
        download_dir = Path(args.cache_dir)
        download_dir.mkdir(parents=True, exist_ok=True)
    else:
        download_dir = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="fill_caida_as_rel_"))
        )

    relation_path = download_dir / f"{snapshot_date}.as-rel2.txt.bz2"
    cone_path = download_dir / f"{snapshot_date}.ppdc-ases.txt.bz2"
    for key, path in (("as_rel2", relation_path), ("ppdc_ases", cone_path)):
        if path.exists():
            print(f"[fill_caida_as_rel] reusing cached {path}")
        else:
            _download(urls[key], path)
    return relation_path, cone_path, "direct_download", urls


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _expected_count(value: object, field: str, asn: str) -> int:
    if value is None:
        return 0
    try:
        integer = int(value)
    except (TypeError, ValueError) as exc:
        raise FillError(f"Invalid {field}={value!r} for ASN {asn}") from exc
    if isinstance(value, float) and not value.is_integer():
        raise FillError(f"Non-integral {field}={value!r} for ASN {asn}")
    return integer


def _import_pyarrow():
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except ImportError as exc:
        raise FillError(
            "PyArrow is required to fill Parquet snapshots. Install it with: "
            "python3 -m pip install pyarrow"
        ) from exc
    return pa, pq


def build_list_columns(
    asns: Iterable[object],
    relationships: dict[str, dict[str, list[str]]],
    cones: dict[str, list[str]],
) -> dict[str, list[str]]:
    columns = {name: [] for name in LIST_TO_COUNT}
    empty_relationship = {"provider": [], "customer": [], "peer": []}
    for raw_asn in asns:
        if raw_asn is None:
            raise FillError("The snapshot contains a null ASN")
        asn = str(int(raw_asn))
        relation = relationships.get(asn, empty_relationship)
        # The server generator only attaches cone data to ASNs that occur in
        # the relationship graph.  Preserve that behavior for exact count
        # compatibility, even if ppdc-ases contains an isolated root ASN.
        cone = cones.get(asn, []) if asn in relationships else []
        values_by_column = {
            "caida-asrel_provider_list": relation["provider"],
            "caida-asrel_customer_list": relation["customer"],
            "caida-asrel_peer_list": relation["peer"],
            "caida-asrel_cone_as_list": cone,
        }
        for column, values in values_by_column.items():
            columns[column].append(json.dumps(values, ensure_ascii=False))
    return columns


def validate_counts(table, list_columns: dict[str, list[str]]) -> tuple[int, list[str]]:
    missing = [field for field in LIST_TO_COUNT.values() if field not in table.column_names]
    if missing:
        raise FillError(
            "The public snapshot is missing count columns required for validation: "
            + ", ".join(missing)
        )

    asns = table.column("asn").to_pylist()
    mismatch_examples: list[str] = []
    mismatch_total = 0
    for list_field, count_field in LIST_TO_COUNT.items():
        counts = table.column(count_field).to_pylist()
        for raw_asn, raw_count, encoded_list in zip(asns, counts, list_columns[list_field]):
            asn = str(int(raw_asn))
            expected = _expected_count(raw_count, count_field, asn)
            actual = len(json.loads(encoded_list))
            if expected != actual:
                mismatch_total += 1
                if len(mismatch_examples) < 12:
                    mismatch_examples.append(
                        f"ASN {asn}: {count_field}={expected}, len({list_field})={actual}"
                    )

    return mismatch_total, mismatch_examples


def _replace_or_append_column(table, name: str, values, pa):
    array = pa.array(values, type=pa.string())
    index = table.schema.get_field_index(name)
    if index >= 0:
        return table.set_column(index, name, array)
    return table.append_column(name, array)


def fill_parquet(
    input_path: Path,
    output_path: Path,
    relationship_path: Path,
    cone_path: Path,
    enrichment: dict,
    allow_count_mismatch: bool,
) -> tuple[list[str], int, str, dict[str, int]]:
    pa, pq = _import_pyarrow()
    table = pq.read_table(input_path)
    if "asn" not in table.column_names:
        raise FillError(f"Parquet file has no 'asn' column: {input_path}")

    print(f"[fill_caida_as_rel] parsing {relationship_path}")
    relationships = parse_relationships(relationship_path)
    print(f"[fill_caida_as_rel] parsing {cone_path}")
    cones = parse_customer_cones(cone_path)
    list_columns = build_list_columns(table.column("asn").to_pylist(), relationships, cones)

    mismatch_total, mismatch_examples = validate_counts(table, list_columns)
    if mismatch_total:
        details = "\n  ".join(mismatch_examples)
        mismatch_message = (
            f"Reconstructed lists disagree with public aggregate counts in "
            f"{mismatch_total} row/field combinations. First mismatches:\n  {details}"
        )
        if not allow_count_mismatch:
            raise FillError(mismatch_message)
        print(
            "[fill_caida_as_rel] WARNING: --allow-count-mismatch was passed; "
            f"writing despite count mismatches\n{mismatch_message}",
            file=sys.stderr,
        )

    for name, values in list_columns.items():
        table = _replace_or_append_column(table, name, values, pa)

    ordered_columns = ["asn"] + sorted(name for name in table.column_names if name != "asn")
    table = table.select(ordered_columns)
    stats = {
        "relationship_graph_asns": len(relationships),
        "customer_cone_roots": len(cones),
        "snapshot_asns": table.num_rows,
        "count_mismatches": mismatch_total,
    }
    enrichment["count_validation"] = (
        "passed" if mismatch_total == 0 else "mismatches_allowed"
    )
    enrichment.update(stats)
    metadata = dict(table.schema.metadata or {})
    metadata[b"caida_asrel_list_enrichment"] = json.dumps(
        enrichment, ensure_ascii=False, sort_keys=True
    ).encode("utf-8")
    table = table.replace_schema_metadata(metadata)

    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    try:
        pq.write_table(table, temporary, compression="snappy")
        os.replace(temporary, output_path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass

    return ordered_columns, output_path.stat().st_size, sha256_file(output_path), stats


def _write_json_atomic(path: Path, value: dict) -> None:
    temporary = path.with_name(path.name + ".tmp")
    with temporary.open("w", encoding="utf-8", newline="\n") as output:
        json.dump(value, output, ensure_ascii=False, indent=2)
        output.write("\n")
    os.replace(temporary, path)


def update_schema_json(path: Path, ordered_columns: list[str]) -> dict:
    with path.open(encoding="utf-8") as source:
        schema = json.load(source)
    schema["columns"] = ordered_columns
    types = schema.setdefault("types", {})
    defaults = schema.setdefault("defaults", {})
    encodings = schema.setdefault("encodings", {})
    for field in LIST_TO_COUNT:
        types[field] = {"logical": "list", "storage": "string"}
        defaults[field] = "[]"
        encodings[field] = "json"
    _write_json_atomic(path, schema)
    return schema


def _markdown_cell(value: object) -> str:
    if value is None:
        return ""
    text = str(value).replace("\n", "\\n").replace("|", "\\|")
    return text if len(text) <= 80 else text[:77] + "..."


def rewrite_schema_markdown(path: Path, schema: dict) -> None:
    include_sources = bool(schema.get("sources"))
    include_notes = bool(schema.get("notes"))
    headers = ["Field", "Logical type", "Storage type", "Default", "Encoding"]
    if include_sources:
        headers.append("Source")
    if include_notes:
        headers.append("Notes")

    lines = [
        f"# Snapshot Schema ({schema.get('snapshot_month', '')})",
        "",
        f"- Schema version: `{schema.get('schema_version', '')}`",
        f"- Generated at (UTC): `{schema.get('generated_at_utc', '')}`",
        "- Complex fields stored as JSON strings: `True`",
        "",
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join(["---"] * len(headers)) + " |",
    ]
    types = schema.get("types", {})
    defaults = schema.get("defaults", {})
    encodings = schema.get("encodings", {})
    for field in schema.get("columns", []):
        field_type = types.get(field, {})
        row = [
            field,
            field_type.get("logical", ""),
            field_type.get("storage", ""),
            defaults.get(field),
            encodings.get(field),
        ]
        if include_sources:
            row.append(schema.get("sources", {}).get(field, ""))
        if include_notes:
            row.append(schema.get("notes", {}).get(field, ""))
        lines.append("| " + " | ".join(_markdown_cell(value) for value in row) + " |")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")


def update_manifest(
    path: Path,
    parquet_path: Path,
    ordered_columns: list[str],
    parquet_size: int,
    parquet_sha256: str,
    enrichment: dict,
) -> None:
    with path.open(encoding="utf-8") as source:
        manifest = json.load(source)

    public_snapshot_id = manifest.get("snapshot_id")
    if public_snapshot_id and public_snapshot_id != parquet_sha256:
        enrichment.setdefault("public_snapshot_id", public_snapshot_id)
    manifest["snapshot_id"] = parquet_sha256
    snapshot = manifest.setdefault("snapshot", {})
    snapshot["columns"] = ordered_columns
    storage_types = snapshot.setdefault("column_storage_types", {})
    for field in LIST_TO_COUNT:
        storage_types[field] = "string"
    snapshot["num_asns"] = enrichment["snapshot_asns"]
    manifest.setdefault("artifacts", {})["snapshot_parquet"] = parquet_path.name

    updated_file_entry = False
    for entry in manifest.setdefault("files", []):
        if str(entry.get("name", "")).endswith(".parquet"):
            entry.update(
                {"name": parquet_path.name, "size": parquet_size, "sha256": parquet_sha256}
            )
            updated_file_entry = True
    if not updated_file_entry:
        manifest["files"].append(
            {"name": parquet_path.name, "size": parquet_size, "sha256": parquet_sha256}
        )
    manifest["caida_asrel_list_enrichment"] = enrichment
    _write_json_atomic(path, manifest)


def _safe_extract(archive: Path, destination: Path) -> None:
    with tarfile.open(archive, "r:gz") as source:
        try:
            source.extractall(destination, filter="data")
        except TypeError:  # Python < 3.12
            root = destination.resolve()
            for member in source.getmembers():
                target = (destination / member.name).resolve()
                if root != target and root not in target.parents:
                    raise FillError(f"Unsafe path in archive: {member.name}")
            source.extractall(destination)


def _single_match(root: Path, pattern: str, label: str) -> Path:
    matches = list(root.rglob(pattern))
    if len(matches) != 1:
        raise FillError(
            f"Expected exactly one {label} in the package, found {len(matches)}"
        )
    return matches[0]


def inspect_package(extracted_root: Path) -> tuple[Path, Path, Path, Path]:
    manifest_path = _single_match(extracted_root, "manifest.json", "manifest.json")
    package_dir = manifest_path.parent
    schema_json_path = package_dir / "schema.json"
    schema_md_path = package_dir / "schema.md"
    if not schema_json_path.is_file() or not schema_md_path.is_file():
        raise FillError("Package must contain schema.json and schema.md beside manifest.json")

    with manifest_path.open(encoding="utf-8") as source:
        manifest = json.load(source)
    artifact_name = manifest.get("artifacts", {}).get("snapshot_parquet")
    parquet_path = package_dir / artifact_name if artifact_name else None
    if parquet_path is None or not parquet_path.is_file():
        parquet_path = _single_match(package_dir, "*.parquet", "Parquet snapshot")
    return manifest_path, schema_json_path, schema_md_path, parquet_path


def _default_output_path(input_path: Path) -> Path:
    parts = list(input_path.parts)
    lowered = [part.lower() for part in parts]
    if "data" in lowered:
        index = len(parts) - 1 - lowered[::-1].index("data")
        return Path("filled_data") / Path(*parts[index + 1 :])
    if "filled_data" in lowered:
        index = len(parts) - 1 - lowered[::-1].index("filled_data")
        return Path("filled_data") / Path(*parts[index + 1 :])
    if re.fullmatch(r"\d{4}-\d{2}", input_path.parent.name):
        return Path("filled_data") / input_path.parent.name / input_path.name
    return Path("filled_data") / input_path.name


def _resolve_snapshot_date(
    explicit_date: str | None,
    manifest: dict | None,
    relationship_path: str | None,
    cone_path: str | None,
) -> str:
    if explicit_date:
        return normalize_date(explicit_date)
    if manifest:
        value = date_from_manifest(manifest)
        if value:
            return value
    inferred = {
        date
        for date in (
            infer_date_from_caida_filename(Path(relationship_path)) if relationship_path else None,
            infer_date_from_caida_filename(Path(cone_path)) if cone_path else None,
        )
        if date
    }
    if len(inferred) == 1:
        return inferred.pop()
    if len(inferred) > 1:
        raise FillError("The supplied CAIDA filenames contain different snapshot dates")
    raise FillError(
        "Could not determine the CAIDA snapshot date. Pass --date YYYYMMDD, or use a "
        "package/sidecar manifest with source_dates['CAIDA AS Relationship']."
    )


def _load_json_if_present(path: Path) -> dict | None:
    if not path.is_file():
        return None
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def _make_enrichment(
    snapshot_date: str,
    input_type: str,
    relationship_path: Path,
    cone_path: Path,
    urls: dict[str, str],
    stats: dict[str, int] | None = None,
) -> dict:
    result = {
        "performed": True,
        "source": "CAIDA AS Relationships Dataset",
        "snapshot_date": snapshot_date,
        "input_type": input_type,
        "relationship_file": relationship_path.name,
        "customer_cone_file": cone_path.name,
        "retrieved_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "license": "CAIDA Public-AUA",
    }
    if urls:
        result["download_urls"] = urls
    if stats:
        result.update(stats)
    return result


def _write_archive(extracted_root: Path, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = output_path.with_name(output_path.name + ".tmp")
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            for child in sorted(extracted_root.iterdir(), key=lambda item: item.name):
                archive.add(child, arcname=child.name)
        os.replace(temporary, output_path)
    finally:
        try:
            temporary.unlink()
        except FileNotFoundError:
            pass


def process_archive(args: argparse.Namespace, input_path: Path, output_path: Path) -> None:
    with contextlib.ExitStack() as stack:
        extracted_root = Path(
            stack.enter_context(tempfile.TemporaryDirectory(prefix="fill_caida_as_rel_package_"))
        )
        _safe_extract(input_path, extracted_root)
        manifest_path, schema_json_path, schema_md_path, parquet_path = inspect_package(
            extracted_root
        )
        manifest = _load_json_if_present(manifest_path)
        snapshot_date = _resolve_snapshot_date(
            args.date, manifest, args.as_rel2, args.ppdc_ases
        )
        show_license_notice(args.yes)
        relationship_path, cone_path, input_type, urls = acquire_caida_files(
            args, snapshot_date, stack
        )
        enrichment = _make_enrichment(
            snapshot_date, input_type, relationship_path, cone_path, urls
        )
        columns, size, checksum, stats = fill_parquet(
            parquet_path,
            parquet_path,
            relationship_path,
            cone_path,
            enrichment,
            args.allow_count_mismatch,
        )
        schema = update_schema_json(schema_json_path, columns)
        rewrite_schema_markdown(schema_md_path, schema)
        update_manifest(
            manifest_path, parquet_path, columns, size, checksum, enrichment
        )
        _write_archive(extracted_root, output_path)

    print(f"[fill_caida_as_rel] {input_path} -> {output_path}")
    print(f"[fill_caida_as_rel] CAIDA snapshot date: {snapshot_date}")
    print(f"[fill_caida_as_rel] snapshot ASNs: {enrichment['snapshot_asns']}")
    if enrichment["count_mismatches"] == 0:
        print(
            "[fill_caida_as_rel] all reconstructed list lengths match the public count columns"
        )
    else:
        print(
            f"[fill_caida_as_rel] WARNING: wrote with "
            f"{enrichment['count_mismatches']} allowed count mismatches"
        )


def process_parquet(args: argparse.Namespace, input_path: Path, output_path: Path) -> None:
    manifest = _load_json_if_present(input_path.parent / "manifest.json")
    snapshot_date = _resolve_snapshot_date(
        args.date, manifest, args.as_rel2, args.ppdc_ases
    )
    show_license_notice(args.yes)
    with contextlib.ExitStack() as stack:
        relationship_path, cone_path, input_type, urls = acquire_caida_files(
            args, snapshot_date, stack
        )
        enrichment = _make_enrichment(
            snapshot_date, input_type, relationship_path, cone_path, urls
        )
        _, _, _, stats = fill_parquet(
            input_path,
            output_path,
            relationship_path,
            cone_path,
            enrichment,
            args.allow_count_mismatch,
        )

    print(f"[fill_caida_as_rel] {input_path} -> {output_path}")
    print(f"[fill_caida_as_rel] CAIDA snapshot date: {snapshot_date}")
    print(f"[fill_caida_as_rel] snapshot ASNs: {enrichment['snapshot_asns']}")
    if enrichment["count_mismatches"] == 0:
        print(
            "[fill_caida_as_rel] all reconstructed list lengths match the public count columns"
        )
    else:
        print(
            f"[fill_caida_as_rel] WARNING: wrote with "
            f"{enrichment['count_mismatches']} allowed count mismatches"
        )


def build_argument_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Public monthly .tar.gz package or extracted .parquet snapshot",
    )
    parser.add_argument(
        "--output",
        help=(
            "Output path. By default, the path under data/ is mirrored under "
            "filled_data/ (e.g. data/X.tar.gz -> filled_data/X.tar.gz)."
        ),
    )
    parser.add_argument(
        "--date",
        help=(
            "CAIDA snapshot date (YYYYMMDD or YYYY-MM-DD). Defaults to the exact "
            "'CAIDA AS Relationship' date in manifest.json."
        ),
    )
    parser.add_argument(
        "--as-rel2",
        help=(
            "Path to a user-provided YYYYMMDD.as-rel2.txt.bz2 (or uncompressed text) "
            "from CAIDA; must be used together with --ppdc-ases"
        ),
    )
    parser.add_argument(
        "--ppdc-ases",
        help=(
            "Path to a user-provided YYYYMMDD.ppdc-ases.txt.bz2 (or uncompressed text) "
            "from CAIDA; must be used together with --as-rel2"
        ),
    )
    parser.add_argument(
        "--cache-dir",
        help=(
            "Persist/reuse direct CAIDA downloads in this directory. Without this "
            "option, downloads are temporary and deleted after the run."
        ),
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help=(
            "Acknowledge the CAIDA notice non-interactively (you remain responsible "
            "for reading and complying with the Public-AUA)"
        ),
    )
    parser.add_argument(
        "--allow-count-mismatch",
        action="store_true",
        help=(
            "Write output even if reconstructed list lengths disagree with public "
            "aggregate counts. This is unsafe and mainly intended for diagnosis."
        ),
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_argument_parser()
    args = parser.parse_args(argv)
    input_path = Path(args.input)
    if not input_path.is_file():
        parser.error(f"input file not found: {input_path}")
    if args.cache_dir and (args.as_rel2 or args.ppdc_ases):
        parser.error("--cache-dir only applies to direct downloads, not supplied files")

    output_path = Path(args.output) if args.output else _default_output_path(input_path)
    try:
        if input_path.name.lower().endswith(".tar.gz"):
            if not output_path.name.lower().endswith(".tar.gz"):
                raise FillError("A .tar.gz input requires a .tar.gz output")
            process_archive(args, input_path, output_path)
        elif input_path.suffix.lower() == ".parquet":
            if output_path.suffix.lower() != ".parquet":
                raise FillError("A .parquet input requires a .parquet output")
            process_parquet(args, input_path, output_path)
        else:
            raise FillError("--input must be a monthly .tar.gz package or a .parquet file")
    except FillError as exc:
        print(f"[fill_caida_as_rel] ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
