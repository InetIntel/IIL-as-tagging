"""
Feature engineering pipeline for ML-based AS tagging.

Handles:
- Automatic feature type detection (numerical, categorical, list, dict)
- DataFrame construction from raw snapshot dictionaries
- Log1p transforms for count features
- Fraction/share feature computation
- Categorical encoding with schema fit/apply pattern
- Conversion to PyTorch tensors for neural network models
"""

import re
import json
import numpy as np
import pandas as pd
from collections import Counter
from typing import Dict, List, Tuple, Optional, Any, Set


# ============================================================================
# Feature type detection
# ============================================================================

# Patterns that indicate count-like numerical features
COUNT_PATTERNS = [r'cnt$', r'cnt(avg)$']

# Known categorical feature suffixes/names
CATEGORICAL_SUFFIXES = ['_name', '_rir', '_cc', '_type']

# Features to exclude from ML (identifiers, raw lists/dicts not useful as-is)
EXCLUDE_PATTERNS = [r'_list$', r'_dict$']

# Notebook-parity explicit denylist (new_ml_tagging_final_access.ipynb exclude_f_name)
EXPLICIT_EXCLUDE_FEATURES = {
    "asn",  # row identifier / index — not a predictive feature
    "pdb_website",
    "tr_ix_peer",
    "pfx2as_v4pfx_cnt",
    "pfx2as_v6pfx_cnt",
    "openintel-opentld_v4addr_cnt",
    "openintel-opentld_v6addr_cnt",
    "openintel-opentld_cctld_cnt",
}


def _looks_like_count(name: str) -> bool:
    """Check if a feature name looks like a count feature."""
    s = name.lower()
    return any(re.search(pat, s) for pat in COUNT_PATTERNS)


def _looks_like_categorical(name: str) -> bool:
    """Check if a feature name looks like a categorical feature."""
    s = name.lower()
    return any(s.endswith(suf) for suf in CATEGORICAL_SUFFIXES)


def _should_exclude(name: str) -> bool:
    """Check if a feature should be excluded from ML."""
    s = name.lower()
    return s in EXPLICIT_EXCLUDE_FEATURES or any(re.search(pat, s) for pat in EXCLUDE_PATTERNS)


def identify_feature_types(
    snapshot_dict: Dict[str, Dict[str, Any]],
    sample_size: int = 100,
) -> Tuple[List[str], List[str]]:
    """
    Auto-classify features into numerical and categorical types.
    
    Examines a sample of ASNs to determine feature types based on
    naming conventions and value types.
    
    Args:
        snapshot_dict: {asn: {feature: value}} dictionary
        sample_size: Number of ASNs to sample for type detection
        
    Returns:
        (numerical_features, categorical_features) lists
    """
    if not snapshot_dict:
        return [], []
    
    # Sample ASNs for type detection
    all_asns = list(snapshot_dict.keys())
    sample_asns = all_asns[:min(sample_size, len(all_asns))]
    
    # Collect all feature names
    all_features: Set[str] = set()
    for asn in sample_asns:
        all_features.update(snapshot_dict[asn].keys())
    
    numerical = []
    categorical = []
    
    for feat in sorted(all_features):
        if _should_exclude(feat):
            continue
        
        # Check naming convention first
        if _looks_like_categorical(feat):
            categorical.append(feat)
            continue
        
        # Sample values to determine type
        sample_values = []
        for asn in sample_asns:
            val = snapshot_dict[asn].get(feat)
            if val is not None:
                sample_values.append(val)
        
        if not sample_values:
            continue
        
        # Check if values are numeric
        numeric_count = 0
        str_count = 0
        for v in sample_values[:50]:
            if isinstance(v, (int, float, np.integer, np.floating)):
                numeric_count += 1
            elif isinstance(v, str):
                str_count += 1
        
        if numeric_count > str_count:
            numerical.append(feat)
        elif str_count > 0 and not isinstance(sample_values[0], (list, dict)):
            categorical.append(feat)
    
    return numerical, categorical


def identify_feature_types_from_manifest(
    manifest: Optional[Dict[str, Any]]
) -> Tuple[List[str], List[str]]:
    """
    Identify feature types from snapshot manifest metadata.

    Uses manifest['column_storage_types'] with policy:
    - int/float -> numerical
    - string -> categorical
    Then removes list/dict-style features from categorical by name pattern.
    """
    if not manifest or not isinstance(manifest, dict):
        return [], []
    col_types = manifest.get("column_storage_types")
    if not isinstance(col_types, dict):
        snapshot_block = manifest.get("snapshot")
        if isinstance(snapshot_block, dict):
            col_types = snapshot_block.get("column_storage_types")
    if not isinstance(col_types, dict):
        return [], []

    numerical: List[str] = []
    categorical: List[str] = []

    for feat, storage_type in sorted(col_types.items()):
        if _should_exclude(feat):
            continue
        st = str(storage_type).strip().lower()
        if st in {"int", "int32", "int64", "float", "float32", "float64", "double"}:
            numerical.append(feat)
        elif st == "string":
            if feat.lower().endswith("_list") or feat.lower().endswith("_dict"):
                continue
            categorical.append(feat)

    return numerical, categorical


def identify_feature_types_from_schema(
    schema: Optional[Dict[str, Any]]
) -> Tuple[List[str], List[str]]:
    """
    Identify feature types from schema.json metadata.

    Uses schema['types'][<feature>]['logical'] with policy:
    - int/float -> numerical
    - string -> categorical
    - list/dict/unknown -> skipped
    """
    if not schema or not isinstance(schema, dict):
        return [], []
    type_map = schema.get("types")
    if not isinstance(type_map, dict):
        return [], []

    numerical: List[str] = []
    categorical: List[str] = []

    for feat, spec in sorted(type_map.items()):
        if _should_exclude(feat):
            continue
        if not isinstance(spec, dict):
            continue
        logical = str(spec.get("logical", "")).strip().lower()
        if logical in {"int", "int32", "int64", "float", "float32", "float64", "double"}:
            numerical.append(feat)
        elif logical == "string":
            if feat.lower().endswith("_list") or feat.lower().endswith("_dict"):
                continue
            categorical.append(feat)

    return numerical, categorical


def identify_feature_types_from_metadata(
    manifest: Optional[Dict[str, Any]],
    schema: Optional[Dict[str, Any]],
) -> Tuple[List[str], List[str], str]:
    """
    Identify feature types with precedence:
    1) schema.json logical types
    2) manifest column storage types
    3) unavailable
    """
    num_schema, cat_schema = identify_feature_types_from_schema(schema)
    if num_schema or cat_schema:
        return num_schema, cat_schema, "schema_json_logical"

    num_manifest, cat_manifest = identify_feature_types_from_manifest(manifest)
    if num_manifest or cat_manifest:
        return num_manifest, cat_manifest, "manifest_column_storage_types"

    return [], [], "unavailable"


# ============================================================================
# Share/fraction feature specs
# ============================================================================

# (numerator_col, denominator_col, output_col, alpha, K)
# Laplace-smoothed share: (num + alpha) / (denom + K * alpha)
DEFAULT_SHARE_SPECS = [
    ("censys_port_1_cnt", "censys_v4addr_cnt", "censys_port_1_frac", 1.0, 2),
    ("censys_port_2_cnt", "censys_v4addr_cnt", "censys_port_2_frac", 1.0, 2),
    ("censys_port_3_cnt", "censys_v4addr_cnt", "censys_port_3_frac", 1.0, 2),
    ("censys_os_1_cnt", "censys_v4addr_cnt", "censys_os_1_frac", 1.0, 2),
    ("censys_os_2_cnt", "censys_v4addr_cnt", "censys_os_2_frac", 1.0, 2),
    ("censys_os_3_cnt", "censys_v4addr_cnt", "censys_os_3_frac", 1.0, 2),
    ("censys_service_1_cnt", "censys_v4addr_cnt", "censys_service_1_frac", 1.0, 2),
    ("censys_service_2_cnt", "censys_v4addr_cnt", "censys_service_2_frac", 1.0, 2),
    ("censys_service_3_cnt", "censys_v4addr_cnt", "censys_service_3_frac", 1.0, 2),
]


def _safe_div_share(n, d, alpha=1.0, K=1):
    """Laplace-smoothed division: (n + alpha) / (d + K*alpha)."""
    try:
        n = float(n) if n is not None else 0.0
        d = float(d) if d is not None else 0.0
    except (ValueError, TypeError):
        n, d = 0.0, 0.0
    return (n + alpha) / (d + max(K * alpha, 1e-9))


def _clean_categorical_value(v: Any, col: Optional[str] = None) -> Any:
    """
    Legacy notebook-style categorical cleaning for parity.

    - None/NaN/blank/null-like strings -> None
    - Optional top_cc normalization: uppercase and keep only 2-letter codes
    """
    if v is None:
        return None
    if isinstance(v, float) and np.isnan(v):
        return None
    if isinstance(v, str):
        s = v.strip()
        if s == "" or s.lower() in {"nan", "none", "null", "na", "n/a"}:
            return None
        if col and "top_cc" in col.lower():
            s = s.upper()
            if not re.fullmatch(r"[A-Z]{2}", s):
                return None
        return s
    return v


# ============================================================================
# DataFrame construction
# ============================================================================

def build_feature_dataframe(
    snapshot_dict: Dict[str, Dict[str, Any]],
    numerical_features: List[str],
    categorical_features: List[str],
    share_specs: Optional[List[tuple]] = None,
    log1p_counts: bool = True,
    drop_numerators: bool = True,
) -> Tuple[pd.DataFrame, List[str], List[str]]:
    """
    Build a clean feature DataFrame from raw snapshot dict.
    
    Applies:
    - Log1p transform for count-like numerical features
    - Laplace-smoothed share features
    - NaN filling (0 for numerical, 'MISSING' for categorical)
    
    Args:
        snapshot_dict: {asn: {feature: value}}
        numerical_features: List of numerical feature names
        categorical_features: List of categorical feature names
        share_specs: Optional share feature specifications
        log1p_counts: Whether to apply log1p to count features
        drop_numerators: If True (default), drop numerator cols to avoid redundancy
                        with share features. If False, keep them.
        
    Returns:
        (DataFrame, num_cols_in_df, cat_cols_in_df)
    """
    if share_specs is None:
        share_specs = DEFAULT_SHARE_SPECS
    
    asns = sorted(snapshot_dict.keys())
    
    # Build base DataFrame from numerical + categorical features
    records = []
    for asn in asns:
        row = {}
        feats = snapshot_dict[asn]
        
        for col in numerical_features:
            val = feats.get(col, 0)
            try:
                val = float(val) if val is not None else 0.0
            except (ValueError, TypeError):
                val = 0.0
            
            # Apply log1p to count features
            if log1p_counts and _looks_like_count(col):
                val = np.log1p(val)
            
            row[col] = val
        
        for col in categorical_features:
            # Keep legacy behavior from old notebook:
            # clean null-like values to None before schema fitting.
            val = feats.get(col, None)
            row[col] = _clean_categorical_value(val, col=col)
        
        # Compute share features
        for num_col, denom_col, out_col, alpha, K in share_specs:
            n_val = feats.get(num_col, 0)
            d_val = feats.get(denom_col, 0)
            row[out_col] = _safe_div_share(n_val, d_val, alpha, K)
        
        records.append(row)
    
    df = pd.DataFrame(records, index=asns)
    
    # Identify numerator columns (dropped by default to avoid redundancy with share features)
    numerator_cols = {spec[0] for spec in share_specs}

    # Determine actual columns present
    share_cols = [spec[2] for spec in share_specs if spec[2] in df.columns]
    
    # Base numerical columns (excluding numerators if drop_numerators)
    if drop_numerators:
        base_num_cols = [
            c for c in numerical_features
            if c in df.columns and c not in numerator_cols
        ]
        cols_to_drop = [c for c in numerator_cols if c in df.columns]
        if cols_to_drop:
            df.drop(columns=cols_to_drop, inplace=True)
    else:
        base_num_cols = [c for c in numerical_features if c in df.columns]
    num_cols_present = base_num_cols + share_cols
    cat_cols_present = [c for c in categorical_features if c in df.columns]
    
    # Fill NaN for numerics; keep categorical NaN/None for schema fitting parity.
    for c in num_cols_present:
        df[c] = pd.to_numeric(df[c], errors='coerce').fillna(0.0)
    for c in cat_cols_present:
        df[c] = df[c].astype(object)
    
    return df, num_cols_present, cat_cols_present


# ============================================================================
# Categorical schema (fit on train, apply everywhere)
# ============================================================================

def fit_cat_schema(
    df: pd.DataFrame,
    cat_cols: List[str],
    train_idx: Optional[List[int]] = None,
    min_count: int = 10,
    top_k: Optional[int] = None,
    unknown_token: str = "Unknown",
    other_token: str = "Other",
) -> Dict[str, Any]:
    """
    Fit categorical encoding schema from training data.
    
    Learns the set of categories for each categorical column from the
    training subset. Unknown categories at inference time become 'OTHER'.
    
    Args:
        df: Full DataFrame
        cat_cols: Categorical column names
        train_idx: Row indices for training data (if None, use all)
        
    Returns:
        Schema dictionary keyed by column name. Each value stores:
        {"keep": [...], "order": [...], "unknown_token": str, "other_token": str}
    """
    schema = {}
    subset = df.iloc[train_idx] if train_idx is not None else df
    
    for col in cat_cols:
        if col not in df.columns:
            continue
        vals = subset[col].astype(object)
        counts = Counter(
            x for x in vals.tolist()
            if pd.notna(x) and x not in (unknown_token, other_token)
        )
        if top_k is not None:
            keep = [lvl for lvl, _ in counts.most_common(top_k)]
        else:
            keep = [lvl for lvl, cnt in counts.items() if cnt >= min_count]
        keep = [k for k in keep if k not in (unknown_token, other_token)]
        order = keep + [other_token, unknown_token]
        schema[col] = {
            "keep": keep,
            "order": order,
            "unknown_token": unknown_token,
            "other_token": other_token,
        }
    
    return schema


def apply_cat_schema(
    df: pd.DataFrame,
    cat_cols: List[str],
    schema: Dict[str, Any],
) -> pd.DataFrame:
    """
    Apply a fitted categorical schema to a DataFrame.
    
    Maps unseen categories to 'OTHER' and converts to pandas Categorical.
    
    Args:
        df: DataFrame to transform
        cat_cols: Categorical column names
        schema: Output of fit_cat_schema()
        
    Returns:
        DataFrame with categorical columns converted
    """
    df = df.copy()
    for col in cat_cols:
        if col not in df.columns or col not in schema:
            continue
        spec = schema[col]
        if isinstance(spec, dict) and "order" in spec:
            keep = spec.get("keep", [])
            order = spec.get("order", [])
            unknown_token = spec.get("unknown_token", "Unknown")
            other_token = spec.get("other_token", "Other")
            s_obj = df[col].astype(object)
            s_obj = s_obj.where(pd.notna(s_obj), unknown_token)
            mask_keep = s_obj.isin(keep)
            s_obj = s_obj.where(mask_keep, other_token)
            df[col] = pd.Categorical(s_obj, categories=order, ordered=False)
        else:
            # Backward-compatible fallback for old schema format: list of categories.
            cats = list(spec)
            df[col] = df[col].astype(str).where(
                df[col].astype(str).isin(cats), other="OTHER"
            )
            df[col] = pd.Categorical(df[col], categories=cats)
    return df


# ============================================================================
# Tensor conversion for PyTorch models
# ============================================================================

def prepare_tabular_tensors(
    df: pd.DataFrame,
    num_cols: List[str],
    cat_cols: List[str],
) -> Tuple[Any, Optional[Any], List[int]]:
    """
    Convert DataFrame columns to PyTorch tensors.
    
    Args:
        df: DataFrame with numerical and categorical columns
        num_cols: Numerical column names
        cat_cols: Categorical column names
        
    Returns:
        (X_num_tensor, X_cat_tensor_or_None, cat_cardinalities)
    """
    import torch
    
    # Numerical tensor
    X_num = torch.tensor(
        df[num_cols].values.astype(np.float32),
        dtype=torch.float32
    )
    
    # Categorical tensor (integer codes)
    if cat_cols:
        cat_arrays = []
        cat_cards = []
        for col in cat_cols:
            if str(df[col].dtype) == 'category':
                codes = df[col].cat.codes.values.copy()
                codes[codes < 0] = len(df[col].cat.categories) - 1  # map -1 to OTHER
                cat_arrays.append(codes)
                cat_cards.append(len(df[col].cat.categories))
            else:
                # Fallback: label encode
                uniq = sorted(df[col].unique())
                mapping = {v: i for i, v in enumerate(uniq)}
                codes = df[col].map(mapping).fillna(len(uniq) - 1).astype(int).values
                cat_arrays.append(codes)
                cat_cards.append(len(uniq))
        
        X_cat = torch.tensor(
            np.column_stack(cat_arrays).astype(np.int64),
            dtype=torch.long
        )
    else:
        X_cat = None
        cat_cards = []
    
    return X_num, X_cat, cat_cards


# ============================================================================
# Comparison helpers (old vs new pipeline parity checks)
# ============================================================================

def build_df_all_m_for_fold_comparison(
    snapshot_dict: Dict[str, Dict[str, Any]],
    manifest: Optional[Dict[str, Any]],
    num_cols_present: List[str],
    cat_cols_present_global: List[str],
    asn2fold: Dict[str, int],
    fold: int,
    share_specs: Optional[List[tuple]] = None,
    drop_numerators: bool = True,
    snapshot_schema: Optional[Dict[str, Any]] = None,
) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """
    Build fold-specific df_all_m in the same shape style as the notebook workflow.

    Steps:
    1) Feature typing from schema/manifest (fallback to heuristic).
    2) Base feature DataFrame via build_feature_dataframe().
    3) Ensure requested numeric/categorical columns exist.
    4) Fit categorical schema on train rows for the chosen fold.
    5) Apply schema to all rows and return ordered columns.
    """
    num_feats, cat_feats, typing_source = identify_feature_types_from_metadata(
        manifest=manifest,
        schema=snapshot_schema,
    )
    used_metadata = bool(num_feats or cat_feats)
    if not used_metadata:
        num_feats, cat_feats = identify_feature_types(snapshot_dict)
        typing_source = "heuristic"

    base_df, _, _ = build_feature_dataframe(
        snapshot_dict=snapshot_dict,
        numerical_features=num_feats,
        categorical_features=cat_feats,
        share_specs=share_specs,
        drop_numerators=drop_numerators,
    )

    # Ensure requested columns exist to match old pipeline column contracts.
    for c in num_cols_present:
        if c not in base_df.columns:
            base_df[c] = 0.0
    for c in cat_cols_present_global:
        if c not in base_df.columns:
            base_df[c] = np.nan

    def _canon_asn(a: Any) -> str:
        s = str(a).strip().upper()
        if s.startswith("AS"):
            s = s[2:]
        return s

    asn2fold_norm = {_canon_asn(k): int(v) for k, v in asn2fold.items()}
    idx_canon = pd.Index([_canon_asn(i) for i in base_df.index])

    # Train rows = rows mapped to folds and not in current fold.
    train_mask = idx_canon.map(lambda a: asn2fold_norm.get(a, -1) not in (-1, fold))
    train_idx = np.where(train_mask.to_numpy())[0].tolist()

    schema = fit_cat_schema(base_df, cat_cols_present_global, train_idx=train_idx)
    df_all_m = apply_cat_schema(base_df, cat_cols_present_global, schema)
    ordered_cols = list(num_cols_present) + list(cat_cols_present_global)
    df_all_m = df_all_m[ordered_cols]

    diagnostics = {
        "used_manifest_typing": typing_source == "manifest_column_storage_types",
        "used_schema_typing": typing_source == "schema_json_logical",
        "typing_source": typing_source,
        "base_shape": tuple(base_df.shape),
        "df_all_m_shape": tuple(df_all_m.shape),
        "n_train_idx": len(train_idx),
        "n_num_cols": len(num_cols_present),
        "n_cat_cols": len(cat_cols_present_global),
    }
    return df_all_m, diagnostics
