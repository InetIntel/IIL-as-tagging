import os
import json
import abc
import glob
import tarfile
import tempfile
import shutil
import hashlib
import pandas as pd
from pathlib import Path
from typing import List, Optional, Dict, Any


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
        self._snapshots: Dict[str, Dict[str, Any]] = {
            snap["month"]: snap for snap in self.index.get("snapshots", [])
        }
        
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
        if date in self._package_overrides:
            return self._package_overrides[date]
        snapshot_info = self._snapshots.get(date)
        if snapshot_info:
            return snapshot_info.get("package", f"{self.PACKAGE_PREFIX}.{date}.tar.gz")
        return f"{self.PACKAGE_PREFIX}.{date}.tar.gz"

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
        return self.cache_dir / date
    
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
        
        cache_path = self._get_cache_path(date)
        
        # Extract to cache
        with tarfile.open(tarball_path, 'r:gz') as tar:
            # The tar contains a folder named {date}/, we extract to cache_dir
            # so we get cache_dir/{date}/ 
            tar.extractall(self.cache_dir)

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
            date: Specific date to clear. If None, clears entire cache.
        """
        if date:
            cache_path = self._get_cache_path(date)
            if cache_path.exists():
                shutil.rmtree(cache_path)
        else:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)

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
        self.base_path = base_path
        if not os.path.exists(self.base_path):
            raise FileNotFoundError(f"Snapshot base path not found: {self.base_path}")

    def list_snapshots(self) -> List[str]:
        # List subdirectories that look like dates
        snapshots = []
        for entry in os.listdir(self.base_path):
            full_path = os.path.join(self.base_path, entry)
            if os.path.isdir(full_path):
                snapshots.append(entry)
        return sorted(snapshots)

    def get_snapshot(self, date: str, use_cache: bool = True) -> pd.DataFrame:
        _ = use_cache  # ignored: reads directly from base_path (no extract cache)
        snapshot_dir = os.path.join(self.base_path, date)
        if not os.path.exists(snapshot_dir):
            raise FileNotFoundError(f"Snapshot directory for date {date} not found at {snapshot_dir}")
        
        # Look for supported files: parquet first, then json
        parquet_path = os.path.join(snapshot_dir, f"IIL-as-feature-snapshot.{date}.parquet")
        json_path = os.path.join(snapshot_dir, f"IIL-as-feature-snapshot.{date}.json")
        
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
        json_files = glob.glob(os.path.join(snapshot_dir, "*.json"))
        if json_files:
            with open(json_files[0], 'r', encoding='utf-8') as f:
                data = json.load(f)
            df = pd.DataFrame.from_dict(data, orient='index')
            df.index.name = 'asn'
            return df
            
        raise FileNotFoundError(f"No supported snapshot file (json/parquet) found in {snapshot_dir}")

    def get_manifest(self, date: str) -> Optional[Dict[str, Any]]:
        """Load manifest.json from legacy local snapshot directory."""
        snapshot_dir = os.path.join(self.base_path, date)
        manifest_path = os.path.join(snapshot_dir, "manifest.json")
        if not os.path.exists(manifest_path):
            return None
        with open(manifest_path, "r", encoding="utf-8") as f:
            return json.load(f)

    def get_schema(self, date: str) -> Optional[Dict[str, Any]]:
        """Load schema.json from legacy local snapshot directory."""
        snapshot_dir = os.path.join(self.base_path, date)
        schema_path = os.path.join(snapshot_dir, "schema.json")
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

    # TODO(HF mirror): the HuggingFace dataset still uses the old id/name; update
    # DEFAULT_DATASET_ID and re-upload the renamed packages under archives/ when
    # the mirror is refreshed to match IIL-as-feature-snapshot.*.
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
            token: HuggingFace access token. If None, uses cached login or HF_TOKEN env var.
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
        self._snapshots: Dict[str, Dict[str, Any]] = {
            snap["month"]: snap for snap in self.index.get("snapshots", [])
        }
    
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
        return self.cache_dir / date
    
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
        
        package_name = snapshot_info.get("package", f"{self.PACKAGE_PREFIX}.{date}.tar.gz")
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
        
        cache_path = self._get_cache_path(date)
        
        # Extract to cache
        with tarfile.open(tarball_path, 'r:gz') as tar:
            tar.extractall(self.cache_dir)
        
        if not cache_path.exists():
            raise RuntimeError(f"Failed to extract snapshot to: {cache_path}")
        
        return cache_path
    
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
            date: Specific date to clear. If None, clears entire cache.
        """
        if date:
            cache_path = self._get_cache_path(date)
            if cache_path.exists():
                shutil.rmtree(cache_path)
        else:
            if self.cache_dir.exists():
                shutil.rmtree(self.cache_dir)
                self.cache_dir.mkdir(parents=True, exist_ok=True)
    
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

