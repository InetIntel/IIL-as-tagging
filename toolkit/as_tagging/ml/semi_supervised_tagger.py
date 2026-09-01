"""
SemiSupervisedMLTagger - Orchestrator for semi-supervised ML-based AS tagging.

Supports learning from small labeled sets (PUN: Positive, Unlabeled, small Negative).
Uses existing feature engineering and graph infrastructure.
"""

import numpy as np
from typing import Dict, List, Optional, Any

from .feature_engineering import (
    identify_feature_types,
    identify_feature_types_from_metadata,
    build_feature_dataframe,
)
from .graph_builder import has_topology_features, build_dgl_graph, build_propagation_matrix
from .semi_supervised import SEMI_SUPERVISED_MODEL_REGISTRY
from .semi_supervised.pun import _canonicalize_asn, _pick_threshold_at_precision
from ..utils import normalize_asn_list


def _to_int_set(asns) -> set:
    out = set()
    for a in asns:
        try:
            s = str(a).strip().upper()
            if s.startswith("AS"):
                s = s[2:]
            out.add(int(s))
        except (ValueError, TypeError):
            continue
    return out


class SemiSupervisedMLTagger:
    """
    Semi-supervised ML tagger for small labeled sets.

    Supports PUN (Positive, Unlabeled, small Negative) and extensible
    to other semi-supervised models via SEMI_SUPERVISED_MODEL_REGISTRY.

    Usage:
        tagger = SemiSupervisedMLTagger(snapshot_dict, model="pun")
        tagger.fit(positive_asns, negative_asns)
        scores = tagger.predict()
        tags = tagger.tag(threshold=0.5)
    """

    def __init__(
        self,
        snapshot_dict: Dict[str, Dict[str, Any]],
        model: str = "pun",
        pun_method: str = "combined",
        features: Optional[List[str]] = None,
        share_specs: Optional[List[tuple]] = None,
        drop_numerators: bool = True,
        manifest: Optional[Dict[str, Any]] = None,
        snapshot_schema: Optional[Dict[str, Any]] = None,
        verbose: bool = True,
    ):
        """
        Args:
            snapshot_dict: {asn: {feature: value}} from ASTagging.atomic_tags
            model: Semi-supervised model name. Default "pun".
            pun_method: PUN sub-method: "graph_ppr", "logreg", "occ", "ae", "combined".
            features: Optional feature subset. None = all auto-detected numerical.
            share_specs: Share feature specs. None = DEFAULT_SHARE_SPECS.
            manifest: Snapshot manifest for feature typing.
            snapshot_schema: Schema for feature typing.
        """
        self.snapshot_dict = snapshot_dict
        self.model_name = model.lower()
        self.pun_method = pun_method
        self.requested_features = features
        self.share_specs = share_specs
        self.drop_numerators = drop_numerators
        self.manifest = manifest
        self.snapshot_schema = snapshot_schema
        self.verbose = verbose

        if self.model_name not in SEMI_SUPERVISED_MODEL_REGISTRY:
            raise ValueError(
                f"Unknown model '{model}'. "
                f"Available: {list(SEMI_SUPERVISED_MODEL_REGISTRY.keys())}"
            )

        self._feature_df = None
        self._num_cols = None
        self._asn_list = None
        self._P = None
        self._asn_to_graph_id = None
        self._has_graph = False
        self._model = None

    def _log(self, msg: str):
        if self.verbose:
            print(f"[SemiSupervisedMLTagger] {msg}")

    def _prepare_features(self):
        if self._feature_df is not None:
            return

        from .feature_engineering import DEFAULT_SHARE_SPECS

        self._log("Detecting feature types...")
        num_feats, cat_feats, _ = identify_feature_types_from_metadata(
            manifest=self.manifest, schema=self.snapshot_schema
        )
        if not num_feats and not cat_feats:
            num_feats, cat_feats = identify_feature_types(self.snapshot_dict)
        self._log(f"  Found {len(num_feats)} numerical, {len(cat_feats)} categorical features")

        if self.requested_features:
            requested = set(self.requested_features)
            all_valid = set(num_feats) | set(cat_feats)
            num_feats = [f for f in num_feats if f in requested]
            cat_feats = [f for f in cat_feats if f in requested]

        share_specs = self.share_specs if self.share_specs is not None else DEFAULT_SHARE_SPECS
        self._feature_df, self._num_cols, _ = build_feature_dataframe(
            self.snapshot_dict,
            num_feats,
            cat_feats,
            share_specs=share_specs,
            drop_numerators=self.drop_numerators,
        )
        self._asn_list = list(self._feature_df.index)
        self._log(f"  DataFrame shape: {self._feature_df.shape}")

    def _prepare_graph(self):
        if self._P is not None:
            return

        if not has_topology_features(self.snapshot_dict):
            self._has_graph = False
            if self.pun_method in ("graph_ppr", "combined"):
                self._log("  No topology; graph score will be zero.")
            return

        try:
            import dgl

            self._log("Building AS topology graph...")
            self._graph, asn2id = build_dgl_graph(self.snapshot_dict)
            self._hg = dgl.to_homogeneous(self._graph, ndata=["asn"])
            self._P = build_propagation_matrix(self._hg)
            self._has_graph = True

            self._asn_to_graph_id = {}
            for asn in self._asn_list:
                try:
                    k = int(_canonicalize_asn(asn))
                    if k in asn2id:
                        self._asn_to_graph_id[k] = asn2id[k]
                except (ValueError, TypeError):
                    pass
            self._log(f"  Graph: {self._hg.num_nodes()} nodes, {len(self._asn_to_graph_id)} in snapshot")
        except ImportError:
            self._log("DGL not installed. Graph-based scoring disabled.")
            self._has_graph = False

    def fit(
        self,
        positive_asns: List[str],
        negative_asns: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        """Fit the semi-supervised model."""
        positive_asns = normalize_asn_list(positive_asns)
        negative_asns = normalize_asn_list(negative_asns, allow_none=True) if negative_asns else []

        self._prepare_features()
        self._prepare_graph()

        X = self._feature_df[self._num_cols].values.astype(np.float32)
        X = np.nan_to_num(X, nan=0.0, posinf=0.0, neginf=0.0)

        P = self._P if self._has_graph else None
        asn_to_graph_id = self._asn_to_graph_id if self._has_graph else None

        model_cls = SEMI_SUPERVISED_MODEL_REGISTRY[self.model_name]
        self._model = model_cls(
            X=X,
            asn_list=self._asn_list,
            P=P,
            asn_to_graph_id=asn_to_graph_id,
            method=self.pun_method,
            verbose=self.verbose,
        )
        self._model.fit(positive_asns=positive_asns, negative_asns=negative_asns or None, **kwargs)
        self._log("Fit complete.")

    def predict(self, asns: Optional[List[str]] = None) -> Dict[str, float]:
        """Return score dict {asn: score}."""
        if self._model is None:
            raise RuntimeError("Model not fitted. Call fit() first.")

        scores = self._model.predict_proba(asns)
        if asns is None:
            return {a: float(scores[i]) for i, a in enumerate(self._asn_list)}
        asns = normalize_asn_list(asns)
        return {a: float(scores[i]) for i, a in enumerate(asns)}

    def tag(
        self,
        threshold: float = 0.5,
        asns: Optional[List[str]] = None,
        target_precision: Optional[float] = None,
        positive_asns: Optional[List[str]] = None,
        negative_asns: Optional[List[str]] = None,
    ) -> Dict[str, bool]:
        """
        Assign binary tags from scores.

        Args:
            threshold: Fixed threshold. Ignored if target_precision is set.
            asns: ASNs to tag. None = all.
            target_precision: If set, pick threshold for this precision on labeled data.
            positive_asns: For target_precision tuning.
            negative_asns: For target_precision tuning.
        """
        probs = self.predict(asns)
        if target_precision is not None and positive_asns and negative_asns:
            pos_int = _to_int_set(positive_asns)
            neg_int = _to_int_set(negative_asns)
            oof_scores = {}
            if hasattr(self._model, "get_oof_labeled_scores"):
                try:
                    oof_scores = self._model.get_oof_labeled_scores() or {}
                except Exception:
                    oof_scores = {}
            y_true = []
            scores_sub = []
            for a, s in probs.items():
                try:
                    k = int(_canonicalize_asn(a))
                    if k in pos_int:
                        y_true.append(1)
                        scores_sub.append(oof_scores.get(str(a), s))
                    elif k in neg_int:
                        y_true.append(0)
                        scores_sub.append(oof_scores.get(str(a), s))
                except (ValueError, TypeError):
                    pass
            if y_true and scores_sub:
                thr, _, _ = _pick_threshold_at_precision(
                    np.array(y_true), np.array(scores_sub), target_p=target_precision
                )
                threshold = thr
                if self.verbose:
                    self._log(f"Threshold at precision {target_precision}: {threshold:.3f}")

        return {a: (p >= threshold) for a, p in probs.items()}
