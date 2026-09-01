from .as_tagging import ASTagging
from .utils import normalize_asn_input, normalize_asn_list
from .snapshot_provider import (
    SnapshotProvider, 
    OfflineSnapshotProvider, 
    OnlineSnapshotProvider,
    LocalSnapshotProvider,  # Deprecated
)

# ML module (optional, requires extras: pip install as-tagging[ml])
try:
    from .ml import MLTagger, SemiSupervisedMLTagger, SEMI_SUPERVISED_MODEL_REGISTRY
    _ml_available = True
except ImportError:
    _ml_available = False

__all__ = [
    "ASTagging",
    "normalize_asn_input",
    "normalize_asn_list",
    "SnapshotProvider",
    "OfflineSnapshotProvider",
    "OnlineSnapshotProvider",
    "LocalSnapshotProvider",  # Deprecated, kept for backward compatibility
]

if _ml_available:
    __all__.extend(["MLTagger", "SemiSupervisedMLTagger", "SEMI_SUPERVISED_MODEL_REGISTRY"])