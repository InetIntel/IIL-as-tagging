import os
import json
import abc
import glob
import tarfile
import tempfile
import shutil
import hashlib
import re
import pandas as pd
from pathlib import Path, PurePosixPath
from typing import List, Optional, Dict, Any


_SNAPSHOT_DATE_RE = re.compile(r"^\d{4}-(?:0[1-9]|1[0-2])$")
_SHA256_RE = re.compile(r"^[0-9a-fA-F]{64}$")


def _validate_snapshot_date(date: str) -> str:
    """Validate the canonical YYYY-MM identifier used in paths and indexes."""
    if not isinstance(date, str) or not _SNAPSHOT_DATE_RE.fullmatch(date):
        raise ValueError(f"Invalid snapshot date: {date!r}; expected YYYY-MM")
    return date


def _validate_package_name(package: str) -> str:
    """Require a plain tarball filename, never a path supplied by an index."""
    if (
        not isinstance(package, str)
        or not package.endswith(".tar.gz")
        or package in {".tar.gz", "..tar.gz"}
        or "/" in package
        or "\\" in package
        or Path(package).name != package
    ):
        raise ValueError(f"Invalid snapshot package filename: {package!r}")
    return package


def _build_snapshot_lookup(index: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    """Validate snapshot index records before they are used to form paths."""
    snapshots = index.get("snapshots", [])
    if not isinstance(snapshots, list):
        raise ValueError("index.json field 'snapshots' must be a list")

    lookup: Dict[str, Dict[str, Any]] = {}
    for snapshot in snapshots:
        if not isinstance(snapshot, dict):
            raise ValueError("Each snapshot entry in index.json must be an object")
        date = _validate_snapshot_date(snapshot.get("month"))
        package = snapshot.get("package")
        if package is not None:
            _validate_package_name(package)
        checksum = snapshot.get("sha256")
        if checksum is not None and (
            not isinstance(checksum, str) or not _SHA256_RE.fullmatch(checksum)
        ):
            raise ValueError(f"Invalid SHA-256 checksum for snapshot {date}")
        if date in lookup:
            raise ValueError(f"Duplicate snapshot month in index.json: {date}")
        lookup[date] = snapshot
    return lookup


def _safe_cache_path(cache_dir: Path, date: str) -> Path:
    """Return a cache child guaranteed to remain inside cache_dir."""
    _validate_snapshot_date(date)
    root = cache_dir.resolve()
    candidate = (root / date).resolve()
    try:
        candidate.relative_to(root)
    except ValueError as exc:
        raise ValueError(f"Snapshot cache path escapes cache directory: {date!r}") from exc
    return candidate


def _verify_sha256(path: Path, expected: str, date: str) -> None:
    """Verify a downloaded/local archive against its published checksum."""
    if not isinstance(expected, str) or not _SHA256_RE.fullmatch(expected):
        raise ValueError(f"Missing or invalid SHA-256 checksum for snapshot {date}")
    digest = hashlib.sha256()
    with path.open("rb") as archive:
        for chunk in iter(lambda: archive.read(1024 * 1024), b""):
            digest.update(chunk)
    actual = digest.hexdigest()
    if actual.lower() != expected.lower():
        raise ValueError(
            f"SHA-256 mismatch for snapshot {date}: expected {expected}, got {actual}"
        )


def _safe_extract_snapshot(
    tarball_path: Path,
    cache_dir: Path,
    date: str,
    parquet_basename: str,
) -> Path:
    """Extract regular files from one snapshot archive without trusting paths."""
    _validate_snapshot_date(date)
    if Path(parquet_basename).name != parquet_basename or not parquet_basename.endswith(
        ".parquet"
    ):
        raise ValueError(f"Invalid parquet filename: {parquet_basename!r}")

    cache_dir.mkdir(parents=True, exist_ok=True)
    cache_path = _safe_cache_path(cache_dir, date)
    temporary_root: Optional[Path] = None

    try:
        with tarfile.open(tarball_path, "r:gz") as archive:
            file_members: Dict[str, tarfile.TarInfo] = {}
            for member in archive.getmembers():
                normalized = PurePosixPath(member.name)
                parts = normalized.parts
                if member.isdir() and parts == (date,):
                    continue
                if (
                    member.name != normalized.as_posix()
                    or normalized.is_absolute()
                    or ".." in parts
                    or "\\" in member.name
                    or len(parts) != 2
                    or parts[0] != date
                    or not member.isfile()
                ):
                    raise ValueError(
                        f"Unsafe or unexpected member in snapshot {date}: {member.name!r}"
                    )
                filename = parts[1]
                if filename in file_members:
                    raise ValueError(
                        f"Duplicate member in snapshot {date}: {member.name!r}"
                    )
                file_members[filename] = member

            required = {parquet_basename, "manifest.json", "schema.json"}
            missing = sorted(required - file_members.keys())
            if missing:
                raise ValueError(
                    f"Snapshot {date} archive is missing required files: {missing}"
                )

            temporary_root = Path(
                tempfile.mkdtemp(prefix=".as-tagging-extract-", dir=cache_dir)
            )
            temporary_snapshot = temporary_root / date
            temporary_snapshot.mkdir()
            for filename, member in file_members.items():
                source = archive.extractfile(member)
                if source is None:
                    raise ValueError(
                        f"Could not read archive member for snapshot {date}: {member.name!r}"
                    )
                with source, (temporary_snapshot / filename).open("wb") as destination:
                    shutil.copyfileobj(source, destination)

        if cache_path.exists():
            shutil.rmtree(cache_path)
        os.replace(temporary_snapshot, cache_path)
        return cache_path
    finally:
        if temporary_root is not None and temporary_root.exists():
            shutil.rmtree(temporary_root)


class SnapshotProvider(abc.ABC):
    """
    Abstract base class for accessing AS feature snapshots.
    """

    @abc.abstractmethod
    def list_snapshots(self) -> List[str]:
        """
        List available snapshot dates (e.g., ['2024-01', '2024-08']).
        """
        pass

    @abc.abstractmethod
    def get_snapshot(self, date: str, use_cache: bool = True) -> pd.DataFrame:
        """
        Retrieve the snapshot data for a specific date as a pandas DataFrame.
        DataFrame index should be the ASN (string).

        Args:
            date: Snapshot month string (e.g. '2024-08').
            use_cache: If False, invalidate cached data for this date and
                re-fetch / re-extract before loading (provider-dependent).
        """
        pass

    def get_manifest(self, date: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve manifest metadata for a specific snapshot date.

        Default implementation returns None for providers that do not expose
        manifest metadata.
        """
        return None

    def get_schema(self, date: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve schema metadata for a specific snapshot date.

        Default implementation returns None for providers that do not expose
        schema metadata.
        """
        return None

    def get_readme_text(self) -> Optional[str]:
        """
        Return README contents for feature/tag descriptions, if available.

        Providers may implement this to expose human-readable descriptions of
        atomic feature keys (used by ASTagging help()).
        """
        return None


class OfflineSnapshotProvider(SnapshotProvider):
    """
    Implementation of SnapshotProvider for offline dataset access.

    Expects a directory structure containing:
    - index.json  (metadata about all snapshots)
    - IIL-as-feature-snapshot.YYYY-MM.tar.gz (compressed snapshots; optional
      variant suffixes via package_overrides, e.g. YYYY-MM_geovariant)

    Each tar.gz contains:
    - YYYY-MM/IIL-as-feature-snapshot.YYYY-MM.parquet
    - YYYY-MM/manifest.json
    - YYYY-MM/schema.json

    Tarballs are looked up flat under ``data_path`` first, then under
    ``data_path/YYYY-MM/`` (the per-month subdirectory layout).
    """

    DEFAULT_CACHE_DIR = os.path.expanduser("~/.cache/as_tagging")
    PACKAGE_PREFIX = "IIL-as-feature-snapshot"

    def __init__(
        self,
        data_path: str,
        cache_dir: Optional[str] = None,
        package_overrides: Optional[Dict[str, str]] = None,
    ):
        """
        Initialize the OfflineSnapshotProvider.

        Args:
            data_path: Path to directory containing index.json and tar.gz files.
            cache_dir: Optional cache directory for extracted files.
                       Defaults to ~/.cache/as_tagging/
            package_overrides: Optional map of snapshot month (e.g. ``"2026-01"``)
                to tarball filename under ``data_path`` (e.g.
                ``"IIL-as-feature-snapshot.2026-01_geovariant.tar.gz"``).
                Overrides the ``package`` field in index.json for that month.
                If you switch variants for the same month, use ``use_cache=False``
                on the first load or ``clear_cache(date)`` so the correct tarball
                is re-extracted (cache tracks which package was extracted).
        """
        self.data_path = Path(data_path)
        self.cache_dir = Path(cache_dir) if cache_dir else Path(self.DEFAULT_CACHE_DIR)
        self._package_overrides: Dict[str, str] = dict(package_overrides or {})
        for override_date, package in self._package_overrides.items():
            _validate_snapshot_date(override_date)
            _validate_package_name(package)

        # Validate data_path exists
        if not self.data_path.exists():
            raise FileNotFoundError(f"Data path not found: {self.data_path}")

        # Load index.json
        self.index_path = self.data_path / "index.json"
        if not self.index_path.exists():
            raise FileNotFoundError(f"index.json not found in: {self.data_path}")

        with open(self.index_path, 'r', encoding='utf-8') as f:
            self.index = json.load(f)

        # Build a lookup from month to snapshot info
        self._snapshots = _build_snapshot_lookup(self.index)

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def list_snapshots(self) -> List[str]:
        """
        List available snapshot dates from index.json.

        Returns:
            List of date strings (e.g., ['2024-08', '2024-09', ...])
        """
        return sorted(self._snapshots.keys())

    def get_snapshot_info(self, date: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific snapshot.

        Args:
            date: The date string (e.g., '2024-08')

        Returns:
            Dictionary with snapshot metadata (num_asns, source_dates, sha256, etc.)
            or None if date not found.
        """
        return self._snapshots.get(date)

    def get_package_name(self, date: str) -> str:
        """Return the tarball filename that will be used for ``date``."""
        return self._resolve_package_name(date)

    def _resolve_package_name(self, date: str) -> str:
        """Resolve tarball filename: override > index.json > default."""
        _validate_snapshot_date(date)
        if date in self._package_overrides:
            return self._package_overrides[date]
        snapshot_info = self._snapshots.get(date)
        if snapshot_info:
            package = snapshot_info.get("package", f"{self.PACKAGE_PREFIX}.{date}.tar.gz")
        else:
            package = f"{self.PACKAGE_PREFIX}.{date}.tar.gz"
        return _validate_package_name(package)

    def _resolve_parquet_basename(self, date: str) -> str:
        """
        Parquet filename inside the extracted ``{date}/`` folder.

        Standard package ``IIL-as-feature-snapshot.2026-01.tar.gz`` →
        ``IIL-as-feature-snapshot.2026-01.parquet``; variant packages keep the
        suffix (e.g. ``...2026-01_geovariant.parquet``).
        """
        package = self._resolve_package_name(date)
        stem = package[:-7] if package.endswith(".tar.gz") else package
        prefix = f"{self.PACKAGE_PREFIX}."
        snapshot_id = stem[len(prefix):] if stem.startswith(prefix) else date
        return f"{self.PACKAGE_PREFIX}.{snapshot_id}.parquet"

    def _get_parquet_path(self, date: str) -> Path:
        return self._get_cache_path(date) / self._resolve_parquet_basename(date)

    def _get_tarball_path(self, date: str) -> Path:
        """
        Locate the tar.gz for ``date``: flat under ``data_path`` first, then
        under the per-month subdirectory ``data_path/{date}/``.
        """
        package = self._resolve_package_name(date)
        flat = self.data_path / package
        if flat.exists():
            return flat
        nested = self.data_path / date / package
        if nested.exists():
            return nested
        return flat

    def _cache_marker_path(self, date: str) -> Path:
        """Path to file recording which tarball was extracted for this month."""
        return self._get_cache_path(date) / ".extracted_package"

    def _get_cache_path(self, date: str) -> Path:
        """Get the cache directory path for the extracted snapshot."""
        return _safe_cache_path(self.cache_dir, date)

    def _is_cached(self, date: str) -> bool:
        """Check if the snapshot is already extracted in cache."""
        parquet_path = self._get_parquet_path(date)
        if not parquet_path.exists():
            return False
        marker = self._cache_marker_path(date)
        if not marker.exists():
            return True
        try:
            return marker.read_text(encoding="utf-8").strip() == self._resolve_package_name(date)
        except OSError:
            return False

    def _extract_snapshot(self, date: str) -> Path:
        """
        Extract the snapshot tar.gz to cache directory.

        Args:
            date: The date string (e.g., '2024-08')

        Returns:
            Path to the extracted snapshot directory.
        """
        tarball_path = self._get_tarball_path(date)
        if not tarball_path.exists():
            raise FileNotFoundError(f"Snapshot tarball not found: {tarball_path}")

        snapshot_info = self._snapshots[date]
        if date not in self._package_overrides and snapshot_info.get("sha256"):
            _verify_sha256(tarball_path, snapshot_info["sha256"], date)

        cache_path = _safe_extract_snapshot(
            tarball_path,
            self.cache_dir,
            date,
            self._resolve_parquet_basename(date),
        )

        try:
            self._cache_marker_path(date).write_text(
                self._resolve_package_name(date), encoding="utf-8"
            )
        except OSError:
            pass

        if not cache_path.exists():
            raise RuntimeError(f"Failed to extract snapshot to: {cache_path}")

        parquet_path = self._get_parquet_path(date)
        if not parquet_path.exists():
            found = sorted(p.name for p in cache_path.glob("*.parquet"))
            raise FileNotFoundError(
                f"Parquet file not found after extract: {parquet_path}. "
                f"Found in {cache_path}: {found or '(none)'}"
            )

        return cache_path

    def get_snapshot(self, date: str, use_cache: bool = True) -> pd.DataFrame:
        """
        Retrieve the snapshot data for a specific date as a pandas DataFrame.

        Extracts from tar.gz if not already cached.

        Args:
            date: The date string (e.g., '2024-08')
            use_cache: If False, removes any cached extract for this date and
                re-extracts from the tarball under data_path.

        Returns:
            pandas DataFrame with ASN features.
        """
        if date not in self._snapshots:
            available = ", ".join(self.list_snapshots()[:5])
            raise ValueError(f"Snapshot for date '{date}' not found. Available: {available}...")

        if not use_cache:
            self.clear_cache(date)

        # Extract if not cached
        if not self._is_cached(date):
            self._extract_snapshot(date)

        parquet_path = self._get_parquet_path(date)

        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

        df = pd.read_parquet(parquet_path)

        # Set ASN as index if it's a column
        if 'asn' in df.columns:
            df = df.set_index('asn')

        return df

    def get_manifest(self, date: str) -> Optional[Dict[str, Any]]:
        """Load manifest.json for a snapshot date from cache/extracted files."""
        if date not in self._snapshots:
            return None
        if not self._is_cached(date):
            self._extract_snapshot(date)
        manifest_path = self._get_cache_path(date) / "manifest.json"
        if not manifest_path.exists():
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_schema(self, date: str) -> Optional[Dict[str, Any]]:
        """Load schema.json for a snapshot date from cache/extracted files."""
        if date not in self._snapshots:
            return None
        if not self._is_cached(date):
            self._extract_snapshot(date)
        schema_path = self._get_cache_path(date) / "schema.json"
        if not schema_path.exists():
            return None
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def clear_cache(self, date: Optional[str] = None):
        """
        Clear cached extracted files.

        Args:
            date: Specific date to clear. If None, clears extracted snapshots
                known to this provider while preserving unrelated cache files.
        """
        if date:
            cache_path = self._get_cache_path(date)
            if cache_path.exists():
                shutil.rmtree(cache_path)
        else:
            for snapshot_date in self._snapshots:
                cache_path = self._get_cache_path(snapshot_date)
                if cache_path.exists():
                    shutil.rmtree(cache_path)

    def get_readme_text(self) -> Optional[str]:
        readme_path = self.data_path / "README.md"
        if not readme_path.exists():
            return None
        try:
            return readme_path.read_text(encoding="utf-8")
        except Exception:
            return None


# Keep LocalSnapshotProvider as an alias for backward compatibility
# but mark it as deprecated
class LocalSnapshotProvider(SnapshotProvider):
    """
    Legacy implementation of SnapshotProvider for pre-extracted directories.

    DEPRECATED: Use OfflineSnapshotProvider instead.

    Expects a directory structure like:
    base_path/
        YYYY-MM/
            IIL-as-feature-snapshot.YYYY-MM.parquet
            (or .json)
    """

    def __init__(self, base_path: str):
        import warnings
        warnings.warn(
            "LocalSnapshotProvider is deprecated. Use OfflineSnapshotProvider instead.",
            DeprecationWarning,
            stacklevel=2
        )
        self.base_path = Path(base_path)
        if not self.base_path.exists():
            raise FileNotFoundError(f"Snapshot base path not found: {self.base_path}")

    def _snapshot_dir(self, date: str) -> Path:
        return _safe_cache_path(self.base_path, date)

    def list_snapshots(self) -> List[str]:
        # List subdirectories that look like dates
        snapshots = []
        for entry in os.listdir(self.base_path):
            full_path = self.base_path / entry
            if full_path.is_dir() and _SNAPSHOT_DATE_RE.fullmatch(entry):
                snapshots.append(entry)
        return sorted(snapshots)

    def get_snapshot(self, date: str, use_cache: bool = True) -> pd.DataFrame:
        _ = use_cache  # ignored: reads directly from base_path (no extract cache)
        snapshot_dir = self._snapshot_dir(date)
        if not snapshot_dir.exists():
            raise FileNotFoundError(f"Snapshot directory for date {date} not found at {snapshot_dir}")

        # Look for supported files: parquet first, then json
        parquet_path = snapshot_dir / f"IIL-as-feature-snapshot.{date}.parquet"
        json_path = snapshot_dir / f"IIL-as-feature-snapshot.{date}.json"

        if os.path.exists(parquet_path):
            df = pd.read_parquet(parquet_path)
            if 'asn' in df.columns:
                df = df.set_index('asn')
            return df

        if os.path.exists(json_path):
            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            df = pd.DataFrame.from_dict(data, orient='index')
            df.index.name = 'asn'
            return df

        # Fallback: search for any json/parquet file in the directory
        json_files = glob.glob(str(snapshot_dir / "*.json"))
        if json_files:
            with open(json_files[0], 'r', encoding='utf-8') as f:
                data = json.load(f)
            df = pd.DataFrame.from_dict(data, orient='index')
            df.index.name = 'asn'
            return df

        raise FileNotFoundError(f"No supported snapshot file (json/parquet) found in {snapshot_dir}")

    def get_manifest(self, date: str) -> Optional[Dict[str, Any]]:
        """Load manifest.json from legacy local snapshot directory."""
        snapshot_dir = self._snapshot_dir(date)
        manifest_path = snapshot_dir / "manifest.json"
        if not os.path.exists(manifest_path):
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_schema(self, date: str) -> Optional[Dict[str, Any]]:
        """Load schema.json from legacy local snapshot directory."""
        snapshot_dir = self._snapshot_dir(date)
        schema_path = snapshot_dir / "schema.json"
        if not os.path.exists(schema_path):
            return None
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)


class OnlineSnapshotProvider(SnapshotProvider):
    """
    Implementation of SnapshotProvider for HuggingFace dataset access.

    Downloads snapshots from the HuggingFace Hub and caches them locally.

    Dataset structure expected on HuggingFace:
    - index.json (metadata about all snapshots)
    - archives/IIL-as-feature-snapshot.YYYY-MM.tar.gz (compressed snapshots)
    """

    # The legacy dataset ID is retained for compatibility; its archives already
    # use the current IIL-as-feature-snapshot.* package names.
    DEFAULT_DATASET_ID = "zchen798/as_feature_snapshot"
    DEFAULT_CACHE_DIR = os.path.expanduser("~/.cache/as_tagging")
    PACKAGE_PREFIX = "IIL-as-feature-snapshot"

    def __init__(
        self,
        dataset_id: Optional[str] = None,
        token: Optional[str] = None,
        cache_dir: Optional[str] = None
    ):
        """
        Initialize the OnlineSnapshotProvider.

        Args:
            dataset_id: HuggingFace dataset ID. Defaults to "zchen798/as_feature_snapshot".
            token: Optional HuggingFace access token for private/custom datasets.
                The default public dataset does not require one. If omitted, the
                HF_TOKEN environment variable is used when present.
            cache_dir: Optional cache directory for downloaded/extracted files.
                       Defaults to ~/.cache/as_tagging/
        """
        try:
            from huggingface_hub import HfApi, hf_hub_download
        except ImportError:
            raise ImportError(
                "huggingface_hub is required for OnlineSnapshotProvider. "
                "Install it with: pip install huggingface_hub"
            )

        self.dataset_id = dataset_id or self.DEFAULT_DATASET_ID
        self.token = token or os.environ.get("HF_TOKEN")
        self.cache_dir = Path(cache_dir) if cache_dir else Path(self.DEFAULT_CACHE_DIR)

        self._api = HfApi()
        self._hf_hub_download = hf_hub_download

        # Ensure cache directory exists
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        # Load index.json from HuggingFace
        self._load_index()

    def _load_index(self):
        """Download and load index.json from HuggingFace."""
        index_cache_path = self.cache_dir / "index.json"

        # Always download fresh index to check for new snapshots
        try:
            downloaded_path = self._hf_hub_download(
                repo_id=self.dataset_id,
                filename="index.json",
                repo_type="dataset",
                token=self.token,
                local_dir=self.cache_dir,
                force_download=True
            )
        except Exception as e:
            # If download fails but we have cached index, use it
            if index_cache_path.exists():
                downloaded_path = str(index_cache_path)
            else:
                raise RuntimeError(f"Failed to download index.json from {self.dataset_id}: {e}")

        with open(downloaded_path, 'r', encoding='utf-8') as f:
            self.index = json.load(f)

        # Build a lookup from month to snapshot info
        self._snapshots = _build_snapshot_lookup(self.index)

    def list_snapshots(self) -> List[str]:
        """
        List available snapshot dates from index.json.

        Returns:
            List of date strings (e.g., ['2024-08', '2024-09', ...])
        """
        return sorted(self._snapshots.keys())

    def get_snapshot_info(self, date: str) -> Optional[Dict[str, Any]]:
        """
        Get metadata for a specific snapshot.

        Args:
            date: The date string (e.g., '2024-08')

        Returns:
            Dictionary with snapshot metadata (num_asns, source_dates, sha256, etc.)
            or None if date not found.
        """
        return self._snapshots.get(date)

    def _get_cache_path(self, date: str) -> Path:
        """Get the cache directory path for the extracted snapshot."""
        return _safe_cache_path(self.cache_dir, date)

    def _is_cached(self, date: str) -> bool:
        """Check if the snapshot is already extracted in cache."""
        cache_path = self._get_cache_path(date)
        parquet_path = cache_path / f"{self.PACKAGE_PREFIX}.{date}.parquet"
        return parquet_path.exists()

    def _download_and_extract_snapshot(self, date: str, *, force_download: bool = False) -> Path:
        """
        Download the snapshot tar.gz from HuggingFace and extract to cache.

        Args:
            date: The date string (e.g., '2024-08')
            force_download: If True, re-download the tarball even if the Hub cache has a copy.

        Returns:
            Path to the extracted snapshot directory.
        """
        snapshot_info = self._snapshots.get(date)
        if not snapshot_info:
            raise ValueError(f"Snapshot for date '{date}' not found in index.")

        package_name = _validate_package_name(
            snapshot_info.get("package", f"{self.PACKAGE_PREFIX}.{date}.tar.gz")
        )
        hf_path = f"archives/{package_name}"

        # Download tar.gz to a temp location
        tarball_path = self._hf_hub_download(
            repo_id=self.dataset_id,
            filename=hf_path,
            repo_type="dataset",
            token=self.token,
            local_dir=self.cache_dir / "_downloads",
            force_download=force_download,
        )

        expected_checksum = snapshot_info.get("sha256")
        _verify_sha256(Path(tarball_path), expected_checksum, date)
        return _safe_extract_snapshot(
            Path(tarball_path),
            self.cache_dir,
            date,
            f"{self.PACKAGE_PREFIX}.{date}.parquet",
        )

    def get_snapshot(self, date: str, use_cache: bool = True) -> pd.DataFrame:
        """
        Retrieve the snapshot data for a specific date as a pandas DataFrame.

        Downloads and extracts from HuggingFace if not already cached.

        Args:
            date: The date string (e.g., '2024-08')
            use_cache: If False, drops the cached extract for this date (if any),
                re-downloads the tarball from the Hub, and re-extracts.

        Returns:
            pandas DataFrame with ASN features.
        """
        if date not in self._snapshots:
            available = ", ".join(self.list_snapshots()[:5])
            raise ValueError(f"Snapshot for date '{date}' not found. Available: {available}...")

        refresh = not use_cache
        if refresh:
            self.clear_cache(date)

        # Download and extract if not cached
        if not self._is_cached(date):
            self._download_and_extract_snapshot(date, force_download=refresh)

        cache_path = self._get_cache_path(date)
        parquet_path = cache_path / f"{self.PACKAGE_PREFIX}.{date}.parquet"

        if not parquet_path.exists():
            raise FileNotFoundError(f"Parquet file not found: {parquet_path}")

        df = pd.read_parquet(parquet_path)

        # Set ASN as index if it's a column
        if 'asn' in df.columns:
            df = df.set_index('asn')

        return df

    def get_manifest(self, date: str) -> Optional[Dict[str, Any]]:
        """Load manifest.json for a snapshot date from cache/extracted files."""
        if date not in self._snapshots:
            return None
        if not self._is_cached(date):
            self._download_and_extract_snapshot(date)
        manifest_path = self._get_cache_path(date) / "manifest.json"
        if not manifest_path.exists():
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_schema(self, date: str) -> Optional[Dict[str, Any]]:
        """Load schema.json for a snapshot date from cache/extracted files."""
        if date not in self._snapshots:
            return None
        if not self._is_cached(date):
            self._download_and_extract_snapshot(date)
        schema_path = self._get_cache_path(date) / "schema.json"
        if not schema_path.exists():
            return None
        with open(schema_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def clear_cache(self, date: Optional[str] = None):
        """
        Clear cached extracted files.

        Args:
            date: Specific date to clear. If None, clears extracted snapshots
                known to this provider while preserving downloads and metadata.
        """
        if date:
            cache_path = self._get_cache_path(date)
            if cache_path.exists():
                shutil.rmtree(cache_path)
        else:
            for snapshot_date in self._snapshots:
                cache_path = self._get_cache_path(snapshot_date)
                if cache_path.exists():
                    shutil.rmtree(cache_path)

    def refresh_index(self):
        """Re-download index.json to check for new snapshots."""
        self._load_index()

    def get_readme_text(self) -> Optional[str]:
        """
        Download and return README.md from the dataset repo if present.
        """
        readme_cache_path = self.cache_dir / "README.md"
        try:
            downloaded_path = self._hf_hub_download(
                repo_id=self.dataset_id,
                filename="README.md",
                repo_type="dataset",
                token=self.token,
                local_dir=self.cache_dir,
                force_download=False,
            )
            return Path(downloaded_path).read_text(encoding="utf-8")
        except Exception:
            if readme_cache_path.exists():
                try:
                    return readme_cache_path.read_text(encoding="utf-8")
                except Exception:
                    return None
            return None
