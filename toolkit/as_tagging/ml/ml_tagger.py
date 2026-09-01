"""
MLTagger - Main orchestrator for ML-based AS tagging.

Provides an end-to-end pipeline for:
1. Feature engineering from snapshot data
2. Graph construction (if topology available)
3. K-fold cross-validation across multiple models
4. Automatic best-model selection
5. Final model training and prediction
"""

import json
import os
import numpy as np
import pandas as pd
from datetime import datetime
from typing import Dict, List, Optional, Tuple, Any

from .feature_engineering import (
    identify_feature_types,
    identify_feature_types_from_metadata,
    build_feature_dataframe,
    fit_cat_schema,
    apply_cat_schema,
    prepare_tabular_tensors,
)
from .models import (
    MODEL_REGISTRY,
    ALL_MODEL_NAMES,
    GRAPH_MODELS,
    _metrics,
)
from ..utils import normalize_asn_list


class MLTagger:
    """
    End-to-end ML-based AS tagger.
    
    Trains multiple ML models, cross-validates them, selects the best one,
    and assigns binary tags to all ASNs.
    
    Usage:
        ml = MLTagger(snapshot_dict)
        results = ml.train_and_select(pos_asns, neg_asns)
        predictions = ml.tag(threshold=0.5)
    """
    
    def __init__(
        self,
        snapshot_dict: Dict[str, Dict[str, Any]],
        models: Optional[List[str]] = None,
        verbose: bool = True,
        log_dir: Optional[str] = None,
        model_dir: Optional[str] = None,
        model_path: Optional[str] = None,
        features: Optional[List[str]] = None,
        share_specs: Optional[List[tuple]] = None,
        drop_numerators: bool = True,
        manifest: Optional[Dict[str, Any]] = None,
        snapshot_schema: Optional[Dict[str, Any]] = None,
        xgboost_profile: Optional[str] = None,
    ):
        """
        Args:
            snapshot_dict: {asn: {feature: value}} from ASTagging.atomic_tags
            models: List of model names to use. Default: all available.
                    Options: "xgboost", "mlp", "graphconv", "appnp"
            verbose: Print progress information
            log_dir: Optional directory path to save training logs.
                     When set, saves log.txt (text log) and
                     ml_training_log.json (structured results).
            features: Optional list of feature names to use for training.
                      Default: None (use all auto-detected numerical and
                      categorical features). Feature names that do not exist
                      in the snapshot or are of unsupported types (list/dict)
                      will be skipped with a warning.
            share_specs: Optional list of tuples defining share features.
                         Format: (numerator, denominator, out_name, alpha, K).
                         Default: None (use DEFAULT_SHARE_SPECS).
                         Pass [] (empty list) to disable share features.
            drop_numerators: If True (default), drop numerator cols (e.g. censys_port_1_cnt)
                            when computing share features. If False, keep both.
            xgboost_profile: If set (e.g. "stochastic"), use this XGBoost profile
                         instead of inner-CV selection. Reduces fold variance and
                         matches old pipeline parity.
            model_dir: Optional directory to save the trained model after training.
            model_path: Optional path to load a previously saved model (skips training).
        """
        self.snapshot_dict = snapshot_dict
        self.model_dir = model_dir
        self.model_path = model_path
        self.xgboost_profile = xgboost_profile
        self.manifest = manifest
        self.snapshot_schema = snapshot_schema
        self.verbose = verbose
        self.log_dir = log_dir
        self.requested_features = features
        self.share_specs = share_specs
        self.drop_numerators = drop_numerators
        self._log_file = None
        
        # Set up file logging
        if log_dir is not None:
            os.makedirs(log_dir, exist_ok=True)
            log_path = os.path.join(log_dir, "log.txt")
            self._log_file = open(log_path, "w", encoding="utf-8")
            self._log(f"Log directory: {os.path.abspath(log_dir)}")
            self._log(f"Started at: {datetime.now().isoformat()}")
        
        # Determine which models to use (skip validation when loading from path)
        if model_path is not None:
            self.requested_models = []
        elif models is None:
            models = list(ALL_MODEL_NAMES)
            self.requested_models = [m.lower() for m in models]
        else:
            self.requested_models = [m.lower() for m in models]

        # Validate model names (when not loading)
        if model_path is None:
            for m in self.requested_models:
                if m not in MODEL_REGISTRY:
                    raise ValueError(
                        f"Unknown model '{m}'. Available: {ALL_MODEL_NAMES}"
                    )
        
        # State
        self._feature_df = None
        self._num_cols = None
        self._cat_cols = None
        self._asn_list = None
        self._asn_to_idx = None
        self._asn_normalized_to_key = None
        self._graph = None
        self._hg = None
        self._P = None
        self._has_graph = False
        self._best_model = None
        self._best_model_name = None
        self._cv_results = None
        self._cat_schema = None

        # Load from path if provided
        if model_path is not None:
            self.load_model(model_path)
    
    def _log(self, msg: str):
        line = f"[MLTagger] {msg}"
        if self.verbose:
            print(line)
        if self._log_file is not None:
            self._log_file.write(line + "\n")
            self._log_file.flush()
    
    def _prepare_features(self):
        """Build feature DataFrame from snapshot."""
        if self._feature_df is not None:
            return
        
        self._log("Detecting feature types...")
        num_feats, cat_feats, typing_source = identify_feature_types_from_metadata(
            manifest=self.manifest,
            schema=self.snapshot_schema,
        )
        if num_feats or cat_feats:
            if typing_source == "schema_json_logical":
                self._log("  Using schema.json logical types for feature typing")
            elif typing_source == "manifest_column_storage_types":
                self._log("  Using manifest column_storage_types for feature typing")
        else:
            num_feats, cat_feats = identify_feature_types(self.snapshot_dict)
            self._log("  Schema/manifest unavailable for typing; using heuristic typing")
        self._log(f"  Found {len(num_feats)} numerical, {len(cat_feats)} categorical features")
        
        # Filter to user-requested features if specified
        if self.requested_features is not None:
            requested = set(self.requested_features)
            all_valid = set(num_feats) | set(cat_feats)
            
            # Warn about unrecognized feature names
            unknown = requested - all_valid
            for feat_name in sorted(unknown):
                self._log(
                    f"  WARNING: Feature '{feat_name}' not found or is an "
                    f"unsupported type (list/dict). Skipping."
                )
            
            # Filter
            num_feats = [f for f in num_feats if f in requested]
            cat_feats = [f for f in cat_feats if f in requested]
            
            if not num_feats and not cat_feats:
                raise ValueError(
                    f"No valid features remain after filtering. "
                    f"Requested: {self.requested_features}. "
                    f"Available numerical: {sorted(all_valid & set(identify_feature_types(self.snapshot_dict)[0]))}. "
                    f"Available categorical: {sorted(all_valid & set(identify_feature_types(self.snapshot_dict)[1]))}."
                )
            
            self._log(f"  Using user-selected features: "
                      f"{len(num_feats)} numerical, {len(cat_feats)} categorical")
        
        self._log("Building feature DataFrame...")
        self._feature_df, self._num_cols, self._cat_cols = build_feature_dataframe(
            self.snapshot_dict, num_feats, cat_feats,
            share_specs=self.share_specs, drop_numerators=self.drop_numerators
        )
        self._asn_list = list(self._feature_df.index)
        self._asn_to_idx = {asn: i for i, asn in enumerate(self._asn_list)}
        self._asn_normalized_to_key = {}
        for asn in self._asn_list:
            canonical = self._canonicalize_asn(asn)
            # Keep the first-seen key for each canonical ASN form
            if canonical not in self._asn_normalized_to_key:
                self._asn_normalized_to_key[canonical] = asn
        self._log(f"  DataFrame shape: {self._feature_df.shape}")
    
    def _prepare_graph(self):
        """Build graph structures if topology features are available."""
        if self._graph is not None:
            return
        
        from .graph_builder import has_topology_features, build_dgl_graph, build_propagation_matrix
        
        if not has_topology_features(self.snapshot_dict):
            self._log("No topology features found. Graph-based models will be skipped.")
            self._has_graph = False
            return
        
        self._log("Building AS topology graph...")
        try:
            # PyTorch 2.3.0 removed DILL_AVAILABLE; torchdata needs it. Patch before importing dgl.
            import torch
            _common = torch.utils.data.datapipes.utils.common
            if not hasattr(_common, "DILL_AVAILABLE"):
                try:
                    _common.DILL_AVAILABLE = torch.utils._import_utils.dill_available()
                except (AttributeError, ImportError):
                    try:
                        import dill
                        _common.DILL_AVAILABLE = True
                    except ImportError:
                        _common.DILL_AVAILABLE = False
            import dgl
            self._graph, self._graph_asn2id = build_dgl_graph(self.snapshot_dict)
            self._log(f"  Graph: {self._graph.num_nodes('asn')} nodes, "
                      f"{sum(self._graph.num_edges(et) for et in self._graph.etypes)} edges")
            
            # Build homogeneous version for GNN
            self._hg = dgl.to_homogeneous(self._graph, ndata=['asn'])
            
            # Build propagation matrix for APPNP
            self._P = build_propagation_matrix(self._hg)
            self._has_graph = True
        except ImportError:
            self._log("DGL not installed. Graph-based models will be skipped.")
            self._has_graph = False
        except Exception as e:
            err_msg = str(e)
            self._log(f"Graph construction failed: {e}. Graph-based models will be skipped.")
            if "pydantic" in err_msg.lower() or "sentinel" in err_msg.lower() or "typing_extensions" in err_msg.lower():
                self._log("  [Tip] pip install pydantic typing-extensions>=4.14.0")
            elif "graphbolt" in err_msg.lower() or "libgraphbolt" in err_msg.lower():
                self._log(
                    "  [Tip] DGL GraphBolt needs matching PyTorch. In your env: "
                    "pip uninstall torch torchdata dgl -y; pip install torch==2.3.0 torchdata==0.7.1; "
                    "pip install dgl -f https://data.dgl.ai/wheels/torch-2.3/repo.html"
                )
            self._has_graph = False
    
    def _get_available_models(self) -> List[str]:
        """Return list of models that can actually run given available data."""
        available = []
        for m in self.requested_models:
            if m in GRAPH_MODELS and not self._has_graph:
                self._log(f"Skipping {m} (no graph data)")
                continue
            available.append(m)
        return available
    
    def _canonicalize_asn(self, asn: Any) -> str:
        """Return canonical ASN string without 'AS' prefix."""
        s = str(asn).strip().upper()
        if s.startswith("AS"):
            s = s[2:]
        return s

    def _normalize_asn(self, asn) -> Any:
        """
        Normalize ASN to the exact key type/value used in snapshot data.

        Falls back to the canonical string form if no snapshot key matches.
        """
        canonical = self._canonicalize_asn(asn)
        if self._asn_normalized_to_key is not None and canonical in self._asn_normalized_to_key:
            return self._asn_normalized_to_key[canonical]
        # Backward-compatible fallback when no mapping is available
        if self._asn_to_idx is not None:
            if canonical in self._asn_to_idx:
                return canonical
            as_prefixed = f"AS{canonical}"
            if as_prefixed in self._asn_to_idx:
                return as_prefixed
        return canonical
    
    def _build_label_array(
        self,
        positive_asns: List[str],
        negative_asns: List[str],
    ) -> np.ndarray:
        """
        Build label array: 1 = positive, 0 = negative, -1 = unlabeled.
        """
        N = len(self._asn_list)
        y = np.full(N, -1, dtype=np.int32)
        
        pos_set = set(self._normalize_asn(a) for a in positive_asns)
        neg_set = set(self._normalize_asn(a) for a in negative_asns)
        
        pos_found = 0
        neg_found = 0
        for i, asn in enumerate(self._asn_list):
            if asn in pos_set:
                y[i] = 1
                pos_found += 1
            elif asn in neg_set:
                y[i] = 0
                neg_found += 1
        
        self._log(f"Labels: {pos_found} positive, {neg_found} negative, "
                  f"{N - pos_found - neg_found} unlabeled out of {N} total ASNs")
        
        if pos_found == 0 or neg_found == 0:
            raise ValueError(
                f"Need both positive and negative labels. "
                f"Found {pos_found} positive and {neg_found} negative in snapshot."
            )
        
        return y
    
    def _run_cv_xgboost(
        self,
        df_raw: pd.DataFrame,
        y: np.ndarray,
        labeled_idx: np.ndarray,
        folds: List[Tuple[np.ndarray, np.ndarray]],
    ) -> List[dict]:
        """Run K-fold CV for XGBoost. Fits categorical schema per fold on train only (old pipeline parity)."""
        results = []
        model_cls = MODEL_REGISTRY["xgboost"]
        model_kwargs = {"force_profile": self.xgboost_profile} if self.xgboost_profile else {}
        feature_cols = self._num_cols + self._cat_cols

        for fold_i, (train_asn_idx, test_asn_idx) in enumerate(folds):
            model = model_cls(**model_kwargs)

            # Fit categorical schema on this fold's training data only (no test leakage)
            schema = fit_cat_schema(
                df_raw, self._cat_cols, train_idx=train_asn_idx.tolist()
            )
            df_encoded = apply_cat_schema(df_raw, self._cat_cols, schema)

            X_train = df_encoded.iloc[train_asn_idx][feature_cols]
            y_train = y[train_asn_idx]
            X_test = df_encoded.iloc[test_asn_idx][feature_cols]
            y_test = y[test_asn_idx]

            train_data = {"X": X_train, "y": y_train, "labeled_mask": y_train >= 0}
            val_data = {"X": X_test, "y": y_test}

            model.train(train_data, val_data)

            prob_test = model.predict_proba({"X": X_test})
            m = _metrics(y_test, prob_test)
            m["fold"] = fold_i + 1
            results.append(m)

            if self.verbose:
                print(f"  [XGBoost fold {fold_i+1}] F1={m['f1']:.3f}, "
                      f"P={m['precision']:.3f}, R={m['recall']:.3f}, "
                      f"AUROC={m['auroc']:.3f}")

        return results
    
    def _run_cv_neural(
        self,
        model_name: str,
        df: pd.DataFrame,
        y: np.ndarray,
        labeled_idx: np.ndarray,
        folds: List[Tuple[np.ndarray, np.ndarray]],
        cat_schema_base: dict,
    ) -> List[dict]:
        """Run K-fold CV for neural models (MLP, GraphConv, APPNP)."""
        import torch
        from sklearn.model_selection import train_test_split
        
        results = []
        model_cls = MODEL_REGISTRY[model_name]
        is_graph = model_name in GRAPH_MODELS
        
        for fold_i, (train_asn_idx, test_asn_idx) in enumerate(folds):
            model = model_cls()
            
            y_train_all = y[train_asn_idx]
            y_test = y[test_asn_idx]
            
            # Fit cat schema on this fold's training data
            schema = fit_cat_schema(df, self._cat_cols, train_idx=train_asn_idx.tolist())
            df_encoded = apply_cat_schema(df, self._cat_cols, schema)
            
            # Get tensors
            X_num_all, X_cat_all, cat_cards = prepare_tabular_tensors(
                df_encoded, self._num_cols, self._cat_cols
            )
            
            if is_graph:
                # For graph models, we need node-level masks
                # Map labeled ASN indices to graph node IDs
                N = len(y)
                y_t = torch.from_numpy(y.astype(np.int32))
                
                # Train/val split from training set
                tr_ids, va_ids = train_test_split(
                    train_asn_idx, test_size=0.1, random_state=42,
                    stratify=y_train_all
                )
                
                train_mask = torch.zeros(N, dtype=torch.bool)
                val_mask = torch.zeros(N, dtype=torch.bool)
                test_mask = torch.zeros(N, dtype=torch.bool)
                train_mask[tr_ids] = True
                val_mask[va_ids] = True
                test_mask[test_asn_idx] = True
                
                labeled = y_t >= 0
                train_mask = train_mask & labeled
                val_mask = val_mask & labeled
                test_mask = test_mask & labeled
                
                if model_name == "graphconv":
                    train_input = {
                        "graph": self._hg,
                        "X_num_all": X_num_all,
                        "X_cat_all": X_cat_all,
                        "y_all": y_t,
                        "train_mask": train_mask,
                        "val_mask": val_mask,
                        "cat_cards": cat_cards,
                    }
                else:  # appnp
                    train_input = {
                        "P": self._P,
                        "X_num_all": X_num_all,
                        "X_cat_all": X_cat_all,
                        "y_all": y_t,
                        "train_mask": train_mask,
                        "val_mask": val_mask,
                        "cat_cards": cat_cards,
                    }
                
                model.train(train_input, {})
                
                # Evaluate on test
                if model_name == "graphconv":
                    pred_data = {
                        "graph": self._hg,
                        "X_num_all": X_num_all,
                        "X_cat_all": X_cat_all,
                    }
                else:
                    pred_data = {
                        "P": self._P,
                        "X_num_all": X_num_all,
                        "X_cat_all": X_cat_all,
                    }
                
                prob_all = model.predict_proba(pred_data)
                prob_test = prob_all[test_asn_idx]
            else:
                # MLP: split into train/val tensors
                tr_ids, va_ids = train_test_split(
                    np.arange(len(train_asn_idx)), test_size=0.1, random_state=42,
                    stratify=y_train_all
                )
                actual_tr = train_asn_idx[tr_ids]
                actual_va = train_asn_idx[va_ids]
                
                train_input = {
                    "X_num": X_num_all[actual_tr],
                    "X_cat": X_cat_all[actual_tr] if X_cat_all is not None else None,
                    "y": y[actual_tr],
                    "cat_cards": cat_cards,
                }
                val_input = {
                    "X_num": X_num_all[actual_va],
                    "X_cat": X_cat_all[actual_va] if X_cat_all is not None else None,
                    "y": y[actual_va],
                }
                
                model.train(train_input, val_input)
                
                pred_data = {
                    "X_num": X_num_all[test_asn_idx],
                    "X_cat": X_cat_all[test_asn_idx] if X_cat_all is not None else None,
                }
                prob_test = model.predict_proba(pred_data)
            
            m = _metrics(y_test, prob_test)
            m["fold"] = fold_i + 1
            results.append(m)
            
            if self.verbose:
                label = model_name.upper()
                print(f"  [{label} fold {fold_i+1}] F1={m['f1']:.3f}, "
                      f"P={m['precision']:.3f}, R={m['recall']:.3f}, "
                      f"AUROC={m['auroc']:.3f}")
        
        return results
    
    def train_and_select(
        self,
        positive_asns: List[str],
        negative_asns: List[str],
        n_folds: int = 5,
        metric: str = "f1",
        random_seed: int = 42,
    ) -> dict:
        """
        Run stratified K-fold CV on all models, select best by metric.

        Args:
            positive_asns: ASNs with the target property
            negative_asns: ASNs without the target property
            n_folds: Number of CV folds
            metric: Metric to select best model ("f1", "auroc", "auprc", etc.)
            random_seed: Random seed for reproducibility

        Returns:
            {
                "best_model": str,
                "cv_results": pd.DataFrame,
                "cv_raw": dict of per-fold results,
            }
        """
        from sklearn.model_selection import StratifiedKFold

        # Normalize ASN inputs (1234, "1234", "AS1234" -> canonical)
        positive_asns = normalize_asn_list(positive_asns)
        negative_asns = normalize_asn_list(negative_asns)

        # Prepare features
        self._prepare_features()

        # Prepare graph (for graph-based models)
        if any(m in GRAPH_MODELS for m in self.requested_models):
            self._prepare_graph()

        # Build labels
        y = self._build_label_array(positive_asns, negative_asns)
        labeled_idx = np.where(y >= 0)[0]
        y_labeled = y[labeled_idx]
        
        # Build stratified folds: sort labeled ASNs by integer value first (old pipeline parity)
        def _asn_sort_key(i):
            a = self._asn_list[i]
            try:
                return int(str(a).lstrip("AS"))
            except (ValueError, TypeError):
                return 0
        ord_idx = np.argsort([_asn_sort_key(i) for i in labeled_idx])
        sorted_labeled_idx = labeled_idx[ord_idx]
        y_sorted = y_labeled[ord_idx]

        skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=random_seed)
        folds = []
        for tr_local, te_local in skf.split(np.arange(len(sorted_labeled_idx)), y_sorted):
            train_global = sorted_labeled_idx[tr_local]
            test_global = sorted_labeled_idx[te_local]
            folds.append((train_global, test_global))

        # Run CV for each available model
        available_models = self._get_available_models()
        if not available_models:
            requested = ", ".join(self.requested_models) or "(none)"
            raise RuntimeError(
                f"No models can run: requested [{requested}] but none are available. "
                f"Graph models (graphconv, appnp) need DGL plus topology features in "
                f"the snapshot -- install DGL with `pip install as-tagging[ml-graph]` "
                f"-- or request a feature-only model such as 'xgboost' or 'mlp'."
            )
        cv_raw = {}
        
        for model_name in available_models:
            self._log(f"\n{'='*50}")
            self._log(f"Cross-validating: {model_name}")
            self._log(f"{'='*50}")
            
            if model_name == "xgboost":
                # XGBoost fits categorical schema per fold (train only) in _run_cv_xgboost
                cv_raw[model_name] = self._run_cv_xgboost(
                    self._feature_df, y, labeled_idx, folds
                )
            else:
                cv_raw[model_name] = self._run_cv_neural(
                    model_name, self._feature_df, y, labeled_idx, folds, None
                )
        
        # Summarize results
        self._log(f"\n{'='*50}")
        self._log("Cross-Validation Summary")
        self._log(f"{'='*50}")
        
        summary_rows = []
        for model_name, fold_results in cv_raw.items():
            row = {"model": model_name}
            for key in ["precision", "recall", "f1", "accuracy", "auroc", "auprc"]:
                vals = [r[key] for r in fold_results if key in r and not np.isnan(r[key])]
                if vals:
                    row[f"{key}_mean"] = np.mean(vals)
                    row[f"{key}_std"] = np.std(vals, ddof=1) if len(vals) > 1 else 0.0
                else:
                    row[f"{key}_mean"] = np.nan
                    row[f"{key}_std"] = np.nan
            summary_rows.append(row)
        
        cv_df = pd.DataFrame(summary_rows)
        
        # Select best model
        metric_col = f"{metric}_mean"
        if metric_col not in cv_df.columns:
            raise ValueError(f"Unknown metric '{metric}'. Available: "
                           f"{[c.replace('_mean','') for c in cv_df.columns if c.endswith('_mean')]}")
        
        best_idx = cv_df[metric_col].idxmax()
        self._best_model_name = cv_df.loc[best_idx, "model"]
        
        self._log(f"\nBest model by {metric}: {self._best_model_name} "
                  f"({metric}={cv_df.loc[best_idx, metric_col]:.3f} "
                  f"± {cv_df.loc[best_idx, f'{metric}_std']:.3f})")
        
        # Print comparison table
        if self.verbose:
            for _, row in cv_df.iterrows():
                parts = [f"{row['model']:>15}"]
                for k in ["precision", "recall", "f1", "auroc", "auprc"]:
                    mu = row.get(f"{k}_mean", np.nan)
                    sd = row.get(f"{k}_std", np.nan)
                    if not np.isnan(mu):
                        parts.append(f"{k}={mu:.3f}±{sd:.3f}")
                print("  " + "  ".join(parts))
        
        # Train final model on ALL labeled data
        self._log(f"\nTraining final {self._best_model_name} on all labeled data...")
        self._train_final_model(y, labeled_idx)
        
        # Save model to disk if model_dir is set
        if self.model_dir is not None:
            self.save_model(self.model_dir)
        
        self._cv_results = cv_df
        
        result = {
            "best_model": self._best_model_name,
            "cv_results": cv_df,
            "cv_raw": cv_raw,
        }
        
        # Save structured log to disk
        if self.log_dir is not None:
            self._save_log_json(result, positive_asns, negative_asns,
                                n_folds, metric, random_seed)
        
        return result
    
    def _save_log_json(
        self,
        result: dict,
        positive_asns: List[str],
        negative_asns: List[str],
        n_folds: int,
        metric: str,
        random_seed: int,
    ):
        """Save a structured JSON log of the training run."""
        log = {
            "timestamp": datetime.now().isoformat(),
            "config": {
                "models_requested": self.requested_models,
                "n_folds": n_folds,
                "selection_metric": metric,
                "random_seed": random_seed,
            },
            "data": {
                "total_asns": len(self._asn_list) if self._asn_list else 0,
                "positive_asns": positive_asns,
                "negative_asns": negative_asns,
                "n_positive": len(positive_asns),
                "n_negative": len(negative_asns),
            },
            "features": {
                "n_numerical": len(self._num_cols) if self._num_cols else 0,
                "n_categorical": len(self._cat_cols) if self._cat_cols else 0,
                "numerical_features": self._num_cols or [],
                "categorical_features": self._cat_cols or [],
            },
            "graph": {
                "available": self._has_graph,
            },
            "best_model": result["best_model"],
            "cv_summary": result["cv_results"].to_dict(orient="records"),
            "cv_per_fold": {
                model: folds for model, folds in result["cv_raw"].items()
            },
        }
        
        log_path = os.path.join(self.log_dir, "ml_training_log.json")
        with open(log_path, "w", encoding="utf-8") as f:
            json.dump(log, f, indent=2, default=str)
        
        self._log(f"\nTraining log saved to: {os.path.abspath(log_path)}")
        
        # Close text log file
        if self._log_file is not None:
            self._log(f"Finished at: {datetime.now().isoformat()}")
            self._log_file.close()
            self._log_file = None
    
    def save_model(self, dir_path: str) -> None:
        """
        Save the trained model and feature pipeline config to a directory.
        
        Writes:
        - config.json: model_name, num_cols, cat_cols, cat_schema, share_specs, etc.
        - model.xgb: XGBoost weights (when best model is xgboost)
        - model.pt: PyTorch state_dict (when best model is mlp/graphconv/appnp)
        """
        if self._best_model is None:
            raise RuntimeError("No model trained. Call train_and_select() first.")
        
        os.makedirs(dir_path, exist_ok=True)
        
        # Serialize share_specs: tuples -> lists for JSON
        share_specs_ser = None
        if self.share_specs is not None:
            share_specs_ser = [list(s) for s in self.share_specs]
        
        config = {
            "model_name": self._best_model_name,
            "num_cols": self._num_cols,
            "cat_cols": self._cat_cols,
            "cat_schema": self._cat_schema,
            "share_specs": share_specs_ser,
            "drop_numerators": self.drop_numerators,
            "xgboost_profile": self.xgboost_profile,
        }
        config_path = os.path.join(dir_path, "config.json")
        with open(config_path, "w", encoding="utf-8") as f:
            json.dump(config, f, indent=2, default=str)
        
        model_name = self._best_model_name
        if model_name == "xgboost":
            model_path = os.path.join(dir_path, "model.xgb")
            self._best_model.save(model_path)
        else:
            import torch
            model_path = os.path.join(dir_path, "model.pt")
            torch.save(self._best_model.model.state_dict(), model_path)
        
        self._log(f"Model saved to: {os.path.abspath(dir_path)}")
    
    def load_model(self, dir_path: str) -> None:
        """
        Load a previously saved model from a directory.
        
        Requires snapshot_dict to be set for feature DataFrame construction.
        For graph models (graphconv, appnp), topology is rebuilt from the current
        snapshot at predict time.
        """
        config_path = os.path.join(dir_path, "config.json")
        if not os.path.exists(config_path):
            raise FileNotFoundError(f"Config not found: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            config = json.load(f)
        
        self._best_model_name = config["model_name"]
        self._num_cols = config["num_cols"]
        self._cat_cols = config["cat_cols"]
        self._cat_schema = config["cat_schema"]
        self.drop_numerators = config.get("drop_numerators", True)
        self.xgboost_profile = config.get("xgboost_profile")
        
        # Deserialize share_specs: lists -> tuples
        share_specs_ser = config.get("share_specs")
        if share_specs_ser is not None:
            self.share_specs = [tuple(s) for s in share_specs_ser] if share_specs_ser else []
        else:
            from .feature_engineering import DEFAULT_SHARE_SPECS
            self.share_specs = DEFAULT_SHARE_SPECS
        
        # Reconstruct numerical_features input for build_feature_dataframe
        # num_cols = base_num_cols + share_output_cols; we need base_num + numerators
        share_output_cols = {spec[2] for spec in self.share_specs}
        numerator_cols = list({spec[0] for spec in self.share_specs})
        base_num_cols = [c for c in self._num_cols if c not in share_output_cols]
        numerical_features = base_num_cols + numerator_cols
        
        # Build feature DataFrame from snapshot using loaded columns
        self._log("Building feature DataFrame from loaded config...")
        self._feature_df, loaded_num, loaded_cat = build_feature_dataframe(
            self.snapshot_dict,
            numerical_features,
            self._cat_cols,
            share_specs=self.share_specs,
            drop_numerators=self.drop_numerators,
        )
        # Use loaded output (may be subset if snapshot missing columns)
        required_cols = set(self._num_cols + self._cat_cols)
        have_cols = set(loaded_num + loaded_cat)
        missing = required_cols - have_cols
        if missing:
            raise ValueError(
                f"Cannot load model: snapshot missing required columns: {sorted(missing)}"
            )
        self._num_cols = loaded_num
        self._cat_cols = loaded_cat
        self._asn_list = list(self._feature_df.index)
        self._asn_to_idx = {asn: i for i, asn in enumerate(self._asn_list)}
        self._asn_normalized_to_key = {}
        for asn in self._asn_list:
            canonical = self._canonicalize_asn(asn)
            if canonical not in self._asn_normalized_to_key:
                self._asn_normalized_to_key[canonical] = asn
        self._log(f"  DataFrame shape: {self._feature_df.shape}")
        
        # For graph models, build graph from current snapshot
        if self._best_model_name in GRAPH_MODELS:
            self._prepare_graph()
            if not self._has_graph:
                raise RuntimeError(
                    f"Loaded model '{self._best_model_name}' requires graph, but "
                    "current snapshot has no topology features (caida-asrel_*_list)."
                )
        
        # Load model weights
        model_cls = MODEL_REGISTRY[self._best_model_name]
        model_kwargs = {}
        if self._best_model_name == "xgboost" and self.xgboost_profile:
            model_kwargs["force_profile"] = self.xgboost_profile
        self._best_model = model_cls(**model_kwargs)
        
        if self._best_model_name == "xgboost":
            model_path = os.path.join(dir_path, "model.xgb")
            self._best_model.load(model_path)
        else:
            import torch
            model_path = os.path.join(dir_path, "model.pt")
            num_dim = len(self._num_cols)
            cat_cards = [
                len(self._cat_schema[col].get("order", []))
                for col in self._cat_cols
                if col in self._cat_schema
            ]
            self._best_model.load(model_path, num_dim=num_dim, cat_cardinalities=cat_cards)
        
        self._log(f"Model loaded from: {os.path.abspath(dir_path)}")
    
    def _train_final_model(self, y: np.ndarray, labeled_idx: np.ndarray):
        """Train the best model on all labeled data."""
        import torch
        from sklearn.model_selection import train_test_split

        model_name = self._best_model_name
        model_cls = MODEL_REGISTRY[model_name]
        model_kwargs = {"force_profile": self.xgboost_profile} if model_name == "xgboost" and self.xgboost_profile else {}
        self._best_model = model_cls(**model_kwargs)
        
        y_labeled = y[labeled_idx]
        
        # Prepare encoded DataFrame
        schema = fit_cat_schema(self._feature_df, self._cat_cols, train_idx=labeled_idx.tolist())
        self._cat_schema = schema
        df_encoded = apply_cat_schema(self._feature_df, self._cat_cols, schema)
        
        if model_name == "xgboost":
            X_all = df_encoded[self._num_cols + self._cat_cols]
            train_data = {"X": X_all, "y": y, "labeled_mask": y >= 0}
            self._best_model.train(train_data, {})
        else:
            X_num_all, X_cat_all, cat_cards = prepare_tabular_tensors(
                df_encoded, self._num_cols, self._cat_cols
            )
            
            # Train/val split
            tr_ids, va_ids = train_test_split(
                labeled_idx, test_size=0.1, random_state=42,
                stratify=y_labeled
            )
            
            if model_name in GRAPH_MODELS:
                N = len(y)
                y_t = torch.from_numpy(y.astype(np.int32))
                train_mask = torch.zeros(N, dtype=torch.bool)
                val_mask = torch.zeros(N, dtype=torch.bool)
                train_mask[tr_ids] = True
                val_mask[va_ids] = True
                labeled = y_t >= 0
                train_mask = train_mask & labeled
                val_mask = val_mask & labeled
                
                if model_name == "graphconv":
                    train_input = {
                        "graph": self._hg,
                        "X_num_all": X_num_all,
                        "X_cat_all": X_cat_all,
                        "y_all": y_t,
                        "train_mask": train_mask,
                        "val_mask": val_mask,
                        "cat_cards": cat_cards,
                    }
                else:
                    train_input = {
                        "P": self._P,
                        "X_num_all": X_num_all,
                        "X_cat_all": X_cat_all,
                        "y_all": y_t,
                        "train_mask": train_mask,
                        "val_mask": val_mask,
                        "cat_cards": cat_cards,
                    }
                self._best_model.train(train_input, {})
            else:
                # MLP
                train_input = {
                    "X_num": X_num_all[tr_ids],
                    "X_cat": X_cat_all[tr_ids] if X_cat_all is not None else None,
                    "y": y[tr_ids],
                    "cat_cards": cat_cards,
                }
                val_input = {
                    "X_num": X_num_all[va_ids],
                    "X_cat": X_cat_all[va_ids] if X_cat_all is not None else None,
                    "y": y[va_ids],
                }
                self._best_model.train(train_input, val_input)
        
        self._log("Final model training complete.")
    
    def predict(self, asns: Optional[List[str]] = None) -> Dict[str, float]:
        """
        Predict probabilities for ASNs using the best model.
        
        Args:
            asns: List of ASNs to predict. If None, predict all.
            
        Returns:
            {asn: probability}
        """
        if self._best_model is None:
            raise RuntimeError("No model trained. Call train_and_select() first.")
        
        # Prepare full data
        df_encoded = apply_cat_schema(self._feature_df, self._cat_cols, self._cat_schema)
        
        model_name = self._best_model_name
        
        if model_name == "xgboost":
            X = df_encoded[self._num_cols + self._cat_cols]
            probs = self._best_model.predict_proba({"X": X})
        else:
            import torch
            X_num_all, X_cat_all, _ = prepare_tabular_tensors(
                df_encoded, self._num_cols, self._cat_cols
            )
            
            if model_name == "graphconv":
                pred_data = {
                    "graph": self._hg,
                    "X_num_all": X_num_all,
                    "X_cat_all": X_cat_all,
                }
            elif model_name == "appnp":
                pred_data = {
                    "P": self._P,
                    "X_num_all": X_num_all,
                    "X_cat_all": X_cat_all,
                }
            else:
                pred_data = {
                    "X_num": X_num_all,
                    "X_cat": X_cat_all,
                }
            probs = self._best_model.predict_proba(pred_data)
        
        # Build result dict
        result = {}
        for i, asn in enumerate(self._asn_list):
            if i < len(probs):
                result[asn] = float(probs[i])
        
        # Filter to requested ASNs if specified (normalize input formats)
        if asns is not None:
            asns = normalize_asn_list(asns)
            filtered = {}
            for a in asns:
                norm = self._normalize_asn(a)
                if norm in result:
                    filtered[norm] = result[norm]
            return filtered
        
        return result
    
    def tag(
        self,
        threshold: float = 0.5,
        asns: Optional[List[str]] = None,
        keep_training_labels: bool = False,
        positive_asns: Optional[List[str]] = None,
        negative_asns: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """
        Assign binary tags based on threshold.
        
        Args:
            threshold: Probability threshold for positive classification
            asns: List of ASNs to tag. If None, tag all.
            keep_training_labels: If True, for ASNs in positive_asns or negative_asns,
                  use the literal training label instead of model prediction.
            positive_asns: ASNs with the target property (required if keep_training_labels).
            negative_asns: ASNs without the target property (required if keep_training_labels).
            
        Returns:
            {asn: True/False}
        """
        # Normalize ASN inputs when provided
        if asns is not None:
            asns = normalize_asn_list(asns)
        probs = self.predict(asns)
        result = {asn: prob >= threshold for asn, prob in probs.items()}
        
        # Override with literal training labels for labeled ASes if requested
        if keep_training_labels and positive_asns is not None and negative_asns is not None:
            positive_asns = normalize_asn_list(positive_asns)
            negative_asns = normalize_asn_list(negative_asns)
            pos_set = set(self._normalize_asn(a) for a in positive_asns)
            neg_set = set(self._normalize_asn(a) for a in negative_asns)
            for asn in list(result.keys()):
                if asn in pos_set:
                    result[asn] = True
                elif asn in neg_set:
                    result[asn] = False
        
        return result
