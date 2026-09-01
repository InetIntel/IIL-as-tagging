"""
AS Tagging Toolkit - Core Tagging Engine

This module provides the main ASTagging class for assigning and retrieving
tags for Autonomous Systems (ASes) based on feature snapshots.

Usage:
    # With snapshot provider
    from as_tagging import ASTagging, OfflineSnapshotProvider
    provider = OfflineSnapshotProvider("/path/to/data")
    tagger = ASTagging(snapshot_provider=provider, date="2024-08")
    
    # Simplified (requires default data path)
    tagger = ASTagging("2024-08")
    
    # Assign custom tag
    tagger.AssignTag(
        tag_name="Anycast",
        expression=lambda tags: tags.get("anycast_v4_cnt") > 0
    )
    
    # Fetch tag value
    result = tagger.FetchTag("Anycast", asns="12389")
"""

import pandas as pd
import json
from importlib import resources
import importlib
import inspect
import sys
import os
import re
from typing import Dict, List, Any, Optional, Union, Callable, Tuple

from .utils import (
    normalize_asn_input,
    normalize_asn_list,
    resolve_asn_to_key,
)


class ASTagging:
    """
    Main class for AS tagging operations.
    
    Supports:
    - Atomic tags: direct features from snapshots
    - Composite tags: derived from atomic tags via expressions
    """
    
    def __init__(
        self,
        snapshot_provider=None,
        date: str = None,
        use_cache: bool = True,
    ):
        """
        Initialize the ASTagging engine.

        Args:
            snapshot_provider: An instance of SnapshotProvider to load data from.
            date: The specific date string (e.g., '2024-08') to load.
            use_cache: If False, the snapshot provider reloads this month from its
                source (re-extract local tarball or re-download from HuggingFace)
                instead of using an existing on-disk extract under cache_dir.
        
        Raises:
            ValueError: If snapshot_provider and date are not both provided.
        """
        if snapshot_provider and date:
            self.snapshot_provider = snapshot_provider
            self.date = date
            # Load the snapshot as a DataFrame
            self.df = self.snapshot_provider.get_snapshot(self.date, use_cache=use_cache)
            # Convert to dictionary format for compatibility with tag logic
            # Orient='index' converts {index: {col: val}} which matches {asn: {tag: val}}
            self.atomic_tags = self.df.to_dict(orient='index')
        else:
            raise ValueError("snapshot_provider and date must be provided.")
        
        # Calculate country sums for geolocation tags
        self.country_sums = self._calculate_country_sums()
        
        # Load tag descriptions
        self.atomic_tag_description = self._load_atomic_tag_descriptions()
        self.composite_tag_description = self._load_package_data('data/composite_tag_description.json')
        
        # Tag expression registry
        self.tag_expressions: Dict[str, Callable] = {}
        
        # Composite tag results cache
        self.composite_tags: Dict[str, Dict[str, Any]] = {}
        
        # Load and apply preset tag definitions
        self._load_preset_tags()
        self._assign_all_preset_tags()
        
    def _load_json(self, file_path: str) -> dict:
        """Load a JSON file and return its content."""
        try:
            with open(file_path, 'r') as json_file:
                return json.load(json_file)
        except FileNotFoundError:
            raise FileNotFoundError(f"File not found at: {file_path}")
        except json.JSONDecodeError:
            raise ValueError(f"Invalid JSON format in file: {file_path}")
        
    def _load_package_data(self, relative_path: str) -> dict:
        """
        Load a JSON file included in the package data.

        Args:
            relative_path: Relative path to the data file within the package.
            
        Returns:
            Parsed JSON data as a Python dictionary.
        """
        try:
            package_root = (__package__ or "as_tagging").split(".")[0]
            resource_path = resources.files(package_root) / relative_path
            with resource_path.open("r", encoding="utf-8") as json_file:
                return json.load(json_file)
        except Exception as e:
            raise ValueError(f"Failed to load package data from {relative_path}: {e}")

    def _parse_atomic_descriptions_from_readme(self, readme_text: str) -> Dict[str, str]:
        """
        Parse atomic tag (feature key) descriptions from a dataset README.md.

        Expected structure includes bullet items like:
          - `feature_key`: Human-readable description...
        Some lines may contain multiple keys in backticks; the same description
        is assigned to each key.
        """
        descriptions: Dict[str, str] = {}
        if not readme_text:
            return descriptions

        for raw_line in readme_text.splitlines():
            line = raw_line.rstrip()

            # Example:
            # - `delegation_rir` (qualitative): The Regional Internet Registry ...
            m = re.match(r"^\s*-\s*(.+?)\s*:\s*(.+?)\s*$", line)
            if not m:
                continue

            left, desc = m.group(1), m.group(2).strip()
            keys = re.findall(r"`([^`]+)`", left)
            if not keys:
                continue

            for k in keys:
                k = k.strip()
                if k and k not in descriptions:
                    descriptions[k] = desc

        return descriptions

    def _load_atomic_tag_descriptions(self) -> Dict[str, str]:
        """
        Prefer provider README.md for atomic tag descriptions; fallback to package JSON.
        """
        readme_text: Optional[str] = None
        try:
            if getattr(self, "snapshot_provider", None) and hasattr(self.snapshot_provider, "get_readme_text"):
                readme_text = self.snapshot_provider.get_readme_text()
        except Exception:
            readme_text = None

        if readme_text:
            parsed = self._parse_atomic_descriptions_from_readme(readme_text)
            if parsed:
                return parsed

        return self._load_package_data("data/atomic_tag_description.json")
    
    def _calculate_country_sums(self) -> Dict[str, int]:
        """
        Calculate the sum of IP addresses for each country across all ASNs.
        
        Used for Major Access tag calculation.
        
        Returns:
            Dictionary with country codes as keys and their total IP counts as values.
        """
        import json
        
        country_sums = {}
        for tags in self.atomic_tags.values():
            # Use '_dict' suffix as per actual snapshot column names
            cc_dict = tags.get('maxmind-geolite2_cc_v4_dict', {})
            
            # Handle JSON string encoding
            if isinstance(cc_dict, str):
                try:
                    cc_dict = json.loads(cc_dict)
                except (json.JSONDecodeError, TypeError):
                    cc_dict = {}
            
            if cc_dict and isinstance(cc_dict, dict):
                for country, value in cc_dict.items():
                    country_sums[country] = country_sums.get(country, 0) + value
        return country_sums
    
    def _load_preset_tags(self):
        """Load preset tag expressions from the preset_lambda module."""
        sys.path.append(os.path.abspath(os.path.dirname(__file__)))
        
        try:
            preset_module = importlib.import_module("data.preset_lambda")
            
            # Get the PRESET_TAG_FUNCTIONS mapping
            if hasattr(preset_module, 'PRESET_TAG_FUNCTIONS'):
                for tag_name, func in preset_module.PRESET_TAG_FUNCTIONS.items():
                    self.tag_expressions[tag_name] = func
            
            # Store reference to tags requiring country_sums
            self._tags_requiring_country_sums = getattr(
                preset_module, 'TAGS_REQUIRING_COUNTRY_SUMS', set()
            )
        except ImportError as e:
            print(f"Warning: Could not load preset_lambda module: {e}")
            self._tags_requiring_country_sums = set()
    
    def _assign_all_preset_tags(self):
        """Evaluate and assign all preset composite tags for all ASNs."""
        # First, compute Global Transit rankings (requires all ASN data)
        self._compute_global_transit_rankings()
        
        # Then assign regular preset tags
        for tag_name, expression in self.tag_expressions.items():
            for asn, tags in self.atomic_tags.items():
                try:
                    # Check if this tag requires country_sums
                    if tag_name in self._tags_requiring_country_sums:
                        tag_value = expression(tags, self.country_sums)
                    elif 'country_sums' in inspect.signature(expression).parameters:
                        tag_value = expression(tags, self.country_sums)
                    else:
                        tag_value = expression(tags)
                    
                    if tag_value is not None:
                        if asn not in self.composite_tags:
                            self.composite_tags[asn] = {}
                        self.composite_tags[asn][tag_name] = tag_value
                except Exception as e:
                    # Silently skip errors during bulk assignment
                    pass
    
    def _compute_global_transit_rankings(self):
        """
        Compute Global Transit Nth-ranked tag using Borda count method.
        
        Uses 5 transit-related features to rank ASes by global transit significance.
        """
        try:
            preset_module = importlib.import_module("data.preset_lambda")
            if hasattr(preset_module, 'compute_global_transit_rankings'):
                rankings = preset_module.compute_global_transit_rankings(self.atomic_tags)
                
                # Assign rank to each ASN that made the ranking
                for asn, rank in rankings.items():
                    if asn not in self.composite_tags:
                        self.composite_tags[asn] = {}
                    self.composite_tags[asn]["Global Transit Nth-ranked"] = rank
        except Exception as e:
            print(f"Warning: Could not compute Global Transit rankings: {e}")
    
    # =========================================================================
    # Public API - Paper-aligned method names
    # =========================================================================
    
    def AssignTag(self, tag_name: str, expression: Union[dict, Callable]) -> None:
        """
        Assign a composite tag to ASes.
        
        This is the main method for users to define custom tags.
        
        Args:
            tag_name: The name of the tag to assign.
            expression: Either:
                - A dictionary mapping ASNs to tag values
                - A callable (lambda) that takes tags dict and returns tag value
        
        Examples:
            # Using a lambda expression
            tagger.AssignTag(
                tag_name="Anycast",
                expression=lambda tags: tags.get("anycast_v4_cnt") > 0
            )
            
            # Using a dictionary
            tagger.AssignTag(
                tag_name="Custom Label",
                expression={"AS12389": True, "AS7018": False}
            )
        """
        if isinstance(expression, dict):
            # Direct assignment from dictionary (normalize ASN keys)
            keys = set(self.atomic_tags.keys()) | set(self.composite_tags.keys())
            for asn, value in expression.items():
                canon = normalize_asn_input(asn)
                key = resolve_asn_to_key(canon, keys)
                if key is None:
                    key = canon  # fallback to canonical if not in snapshot
                if key not in self.composite_tags:
                    self.composite_tags[key] = {}
                self.composite_tags[key][tag_name] = value
        elif callable(expression):
            # Store expression for future use
            self.tag_expressions[tag_name] = expression
            
            # Evaluate for all ASNs
            for asn, tags in self.atomic_tags.items():
                try:
                    tag_value = expression(tags)
                    if tag_value is not None:
                        if asn not in self.composite_tags:
                            self.composite_tags[asn] = {}
                        self.composite_tags[asn][tag_name] = tag_value
                except Exception as e:
                    print(f"Error assigning tag '{tag_name}' for ASN {asn}: {e}")
                    raise
        else:
            raise ValueError("expression must be either a dictionary or a callable.")
    
    def AssignMLTag(
        self,
        tag_name: str,
        positive_asns: Optional[List[str]] = None,
        negative_asns: Optional[List[str]] = None,
        models: Optional[List[str]] = None,
        n_folds: int = 5,
        metric: str = "f1",
        threshold: float = 0.5,
        verbose: bool = True,
        log_dir: Optional[str] = None,
        model_dir: Optional[str] = None,
        model_path: Optional[str] = None,
        features: Optional[List[str]] = None,
        share_specs: Optional[List[tuple]] = None,
        drop_numerators: bool = True,
        asns: Optional[List[str]] = None,
        keep_training_labels: bool = False,
        xgboost_profile: Optional[str] = None,
    ) -> dict:
        """
        Train ML models, auto-select the best, and assign a binary tag to ASNs.
        
        Supports 4 supervised learning models:
        - XGBoost (tree-based ensemble, feature-only)
        - MLP (neural network with categorical embeddings, feature-only)
        - GraphConv (graph neural network, uses AS topology)
        - APPNP (MLP + PageRank propagation, uses AS topology)
        
        The method runs stratified K-fold cross-validation on all requested models,
        selects the best one by the chosen metric, retrains on all labeled data,
        and assigns predictions as a composite tag.
        
        Args:
            tag_name: Name of the tag to assign (e.g., "Residential Access").
            positive_asns: List of ASNs known to have the target property.
            negative_asns: List of ASNs known NOT to have the target property.
            models: List of models to try. Default: all available.
                    Options: "xgboost", "mlp", "graphconv", "appnp"
            n_folds: Number of cross-validation folds (default 5).
            metric: Metric for model selection ("f1", "auroc", "auprc", etc.).
            threshold: Probability threshold for binary tag assignment (default 0.5).
            verbose: Print progress and comparison table.
            log_dir: Optional directory path to save training logs.
                     When set, saves log.txt (streaming text log) and
                     ml_training_log.json (structured results) to this directory.
            model_dir: Optional directory to save the trained model (config.json + model weights).
            model_path: Optional path to load a previously saved model; skips training and
                        assigns tags from the loaded model. positive_asns/negative_asns
                        optional when using model_path (only needed if keep_training_labels=True).
            features: Optional list of feature names to use for training.
                      Default: None (use all auto-detected numerical and
                      categorical features). Unrecognized feature names
                      are skipped with a warning.
            share_specs: Optional list of tuples defining share features.
                         Format: (numerator, denominator, out_name, alpha, K).
                         Default: None (use DEFAULT_SHARE_SPECS).
                         Pass [] (empty list) to disable share features.
            drop_numerators: If True (default), drop numerator cols when computing
                  share features. If False, keep both numerators and share outputs.
            asns: Optional list of ASNs to predict and tag. If None, tag all ASNs
                  in the snapshot.
            keep_training_labels: If True, for ASNs in positive_asns or negative_asns,
                  use the literal training label (True/False) instead of the model
                  prediction. If False (default), use model prediction for all ASNs.
            xgboost_profile: If set (e.g. "stochastic"), use this XGBoost profile
                  instead of inner-CV selection. Reduces fold variance; "stochastic"
                  matches the old pipeline.
        
        Returns:
            dict with keys:
                - "best_model": name of the selected model
                - "cv_results": DataFrame comparing all models
                - "cv_raw": per-fold results for each model
        
        Raises:
            ImportError: If ML dependencies are not installed.
                        Install with: pip install as-tagging[ml]
        
        Examples:
            results = tagger.AssignMLTag(
                tag_name="Residential Access",
                positive_asns=["7018", "7922", "20001"],
                negative_asns=["13335", "15169", "32934"],
                metric="f1",
            )
            # Check results
            print(results["cv_results"])
            # Use the tag
            tagger.FetchTag("Residential Access", asns="7018")  # -> True
            
            # With logging to disk
            results = tagger.AssignMLTag(
                tag_name="Residential Access",
                positive_asns=pos, negative_asns=neg,
                log_dir="./ml_logs/residential",
            )
            # Tag only a specific list of ASes
            results = tagger.AssignMLTag(
                tag_name="Residential Access",
                positive_asns=pos, negative_asns=neg,
                asns=["7018", "13335", "15169"],
            )
            # Keep training labels for labeled ASes (don't overwrite with predictions)
            results = tagger.AssignMLTag(
                tag_name="Residential Access",
                positive_asns=pos, negative_asns=neg,
                keep_training_labels=True,
            )
            # Save model after training
            results = tagger.AssignMLTag(..., model_dir="./data/residential_isp")
            # Load saved model and assign tags without retraining
            tagger.AssignMLTag(
                tag_name="Residential Access",
                model_path="./data/residential_isp",
                asns=["7018", "13335", "15169"],
            )
        """
        try:
            from .ml import MLTagger
        except ImportError:
            raise ImportError(
                "ML dependencies not installed. "
                "Install them with: pip install as-tagging[ml]\n"
                "Required packages: xgboost, torch, scikit-learn, "
                "and optionally dgl for graph-based models."
            )
        
        # Create MLTagger with current snapshot data
        manifest = None
        if hasattr(self.snapshot_provider, "get_manifest"):
            try:
                manifest = self.snapshot_provider.get_manifest(self.date)
            except Exception:
                manifest = None
        snapshot_schema = None
        if hasattr(self.snapshot_provider, "get_schema"):
            try:
                snapshot_schema = self.snapshot_provider.get_schema(self.date)
            except Exception:
                snapshot_schema = None
        # Normalize ASN inputs (1234, "1234", "AS1234" -> canonical)
        asns = normalize_asn_list(asns, allow_none=True) if asns is not None else None

        if model_path is not None:
            # Load saved model and predict without retraining
            if keep_training_labels and (positive_asns is None or negative_asns is None):
                raise ValueError(
                    "positive_asns and negative_asns are required when "
                    "model_path is set with keep_training_labels=True."
                )
            positive_asns = normalize_asn_list(positive_asns) if positive_asns else []
            negative_asns = normalize_asn_list(negative_asns) if negative_asns else []

            ml_tagger = MLTagger(
                snapshot_dict=self.atomic_tags,
                manifest=manifest,
                snapshot_schema=snapshot_schema,
                model_path=model_path,
                verbose=verbose,
            )
            predictions = ml_tagger.tag(
                threshold=threshold,
                asns=asns,
                keep_training_labels=keep_training_labels,
                positive_asns=positive_asns or None,
                negative_asns=negative_asns or None,
            )
            self.AssignTag(tag_name, predictions)
            return {"best_model": ml_tagger._best_model_name, "cv_results": None, "cv_raw": None}

        # Training path
        if positive_asns is None or negative_asns is None:
            raise ValueError("positive_asns and negative_asns are required when not using model_path.")
        positive_asns = normalize_asn_list(positive_asns)
        negative_asns = normalize_asn_list(negative_asns)

        ml_tagger = MLTagger(
            snapshot_dict=self.atomic_tags,
            manifest=manifest,
            snapshot_schema=snapshot_schema,
            models=models,
            verbose=verbose,
            log_dir=log_dir,
            model_dir=model_dir,
            features=features,
            share_specs=share_specs,
            drop_numerators=drop_numerators,
            xgboost_profile=xgboost_profile,
        )
        
        # Run cross-validation and select best model
        results = ml_tagger.train_and_select(
            positive_asns=positive_asns,
            negative_asns=negative_asns,
            n_folds=n_folds,
            metric=metric,
        )
        
        # Get predictions and assign as composite tag
        predictions = ml_tagger.tag(
            threshold=threshold,
            asns=asns,
            keep_training_labels=keep_training_labels,
            positive_asns=positive_asns,
            negative_asns=negative_asns,
        )
        self.AssignTag(tag_name, predictions)
        
        return results
    
    # Backward compatibility alias
    def assign_ml_tag(self, *args, **kwargs):
        """Alias for AssignMLTag (backward compatibility)."""
        return self.AssignMLTag(*args, **kwargs)

    def AssignSemiSupervisedMLTag(
        self,
        tag_name: str,
        positive_asns: List[str],
        negative_asns: Optional[List[str]] = None,
        model: str = "pun",
        pun_method: str = "combined",
        threshold: float = 0.5,
        target_precision: Optional[float] = None,
        asns: Optional[List[str]] = None,
        features: Optional[List[str]] = None,
        share_specs: Optional[List[tuple]] = None,
        drop_numerators: bool = True,
        verbose: bool = True,
    ) -> dict:
        """
        Assign tags using semi-supervised learning (PUN: Positive, Unlabeled, small Negative).

        Use when you have only a small labeled set (tens of positive and optionally
        negative ASes). Inspired by PUbN (Hsieh et al.).

        Args:
            tag_name: Name of the tag to assign (e.g., "Mobile ISP").
            positive_asns: ASNs known to have the target property (required).
            negative_asns: Optional ASNs known NOT to have the property.
            model: Semi-supervised model. Default "pun".
            pun_method: PUN sub-method: "graph_ppr", "logreg", "occ", "ae", "combined".
            threshold: Probability threshold (default 0.5). Ignored if target_precision set.
            target_precision: If set, pick threshold for this precision on labeled data.
            asns: ASNs to tag. None = all.
            features: Optional feature subset.
            share_specs: Share feature specs.
            drop_numerators: Drop numerator cols when computing share features.

        Returns:
            dict with "model" and "n_tagged" keys.
        """
        try:
            from .ml import SemiSupervisedMLTagger
        except ImportError:
            raise ImportError(
                "ML dependencies not installed. "
                "Install them with: pip install as-tagging[ml]"
            )

        manifest = None
        if hasattr(self.snapshot_provider, "get_manifest"):
            try:
                manifest = self.snapshot_provider.get_manifest(self.date)
            except Exception:
                manifest = None
        snapshot_schema = None
        if hasattr(self.snapshot_provider, "get_schema"):
            try:
                snapshot_schema = self.snapshot_provider.get_schema(self.date)
            except Exception:
                snapshot_schema = None

        ss_tagger = SemiSupervisedMLTagger(
            snapshot_dict=self.atomic_tags,
            model=model,
            pun_method=pun_method,
            features=features,
            share_specs=share_specs,
            drop_numerators=drop_numerators,
            manifest=manifest,
            snapshot_schema=snapshot_schema,
            verbose=verbose,
        )
        ss_tagger.fit(
            positive_asns=normalize_asn_list(positive_asns),
            negative_asns=normalize_asn_list(negative_asns, allow_none=True) if negative_asns else None,
        )

        predictions = ss_tagger.tag(
            threshold=threshold,
            asns=asns,
            target_precision=target_precision,
            positive_asns=positive_asns,
            negative_asns=negative_asns,
        )
        self.AssignTag(tag_name, predictions)
        return {"model": model, "n_tagged": sum(1 for v in predictions.values() if v)}

    def FetchTag(
        self, 
        tag_name: str, 
        asns: Optional[Union[str, List[str]]] = None,
        **kwargs
    ) -> Union[Any, Dict[str, Any]]:
        """
        Retrieve the value of a specific tag for given ASN(s).
        
        Args:
            tag_name: The name of the tag to fetch.
            asns: A single ASN (str) or list of ASNs. 
                  If None, returns all ASNs with non-empty values.
            **kwargs: Additional parameters for dynamic tag evaluation.
        
        Returns:
            - If single ASN: the tag value
            - If multiple ASNs: dict mapping ASNs to values
            - If no ASNs specified: dict of all ASNs with non-empty values
        
        Examples:
            # Single ASN
            tagger.FetchTag("Any Presence", asns="12389")
            # Output: ['RU', 'US', 'UA']
            
            # Multiple ASNs
            tagger.FetchTag("Domestic", asns=["12389", "7018"])
            # Output: {"12389": ["RU"], "7018": ["US"]}
        """
        # Normalize asns to list and resolve to actual keys in data
        if asns is not None:
            canonical_list = normalize_asn_list(asns)
            # Resolve each canonical to actual key format used in atomic_tags/composite_tags
            keys = set(self.atomic_tags.keys()) | set(self.composite_tags.keys())
            asns = []
            for canon in canonical_list:
                k = resolve_asn_to_key(canon, keys)
                if k is not None:
                    asns.append(k)
                else:
                    asns.append(canon)  # fallback: use canonical (may not exist)
        else:
            # Return all ASNs with non-empty values
            result = {}
            all_asns = set(self.atomic_tags.keys()) | set(self.composite_tags.keys())
            for asn in all_asns:
                # Merge tags at the tag level, not ASN level
                all_tags = {**self.atomic_tags.get(asn, {}), **self.composite_tags.get(asn, {})}
                if tag_name in all_tags and all_tags[tag_name] not in [None, 0, [], {}, False]:
                    result[asn] = all_tags[tag_name]
            if not result:
                raise KeyError(f"Tag '{tag_name}' does not exist or is empty for all ASNs.")
            return result
        
        # Check if tag has a dynamic expression
        if tag_name in self.tag_expressions and kwargs:
            expression = self.tag_expressions[tag_name]
            result = {}
            for asn in asns:
                tags = {**self.atomic_tags.get(asn, {}), **self.composite_tags.get(asn, {})}
                try:
                    tag_value = expression(tags, **kwargs)
                    result[asn] = tag_value
                except Exception as e:
                    print(f"Error computing tag for ASN {asn}: {e}")
                    raise
            return result[asns[0]] if len(asns) == 1 else result
        
        # Fetch from cached values
        result = {}
        for asn in asns:
            all_tags = {**self.atomic_tags.get(asn, {}), **self.composite_tags.get(asn, {})}
            result[asn] = all_tags.get(tag_name, None)
        
        return result[asns[0]] if len(asns) == 1 else result
    
    def ListTags(self, asn: str) -> Dict[str, Dict[str, Any]]:
        """
        List both atomic and composite tags for a given ASN.
        
        Args:
            asn: The ASN to list tags for.
            
        Returns:
            Dictionary with "Atomic" and "Composite" keys containing respective tags.
            
        Raises:
            ValueError: If no ASN is provided.
        """
        if not asn:
            raise ValueError("Please provide an ASN.")
        canon = normalize_asn_input(asn)
        keys = set(self.atomic_tags.keys()) | set(self.composite_tags.keys())
        key = resolve_asn_to_key(canon, keys)
        if key is None:
            key = canon
        atomic = self.atomic_tags.get(key, {})
        composite = self.composite_tags.get(key, {})
        
        return {"Atomic": atomic, "Composite": composite}

    def ListASNsWithoutTag(
        self,
        tag_name: str,
        treat_false_as_missing: bool = False,
    ) -> List[Any]:
        """
        List ASNs that do not have a given tag value.

        Args:
            tag_name: The tag name to check.
            treat_false_as_missing: If True, consider falsy values
                (None/False/0/[]/{}) as missing. If False, only absence/None
                is treated as missing.

        Returns:
            List of ASNs missing the specified tag.
        """
        missing_asns = []
        all_asns = set(self.atomic_tags.keys()) | set(self.composite_tags.keys())

        for asn in all_asns:
            all_tags = {**self.atomic_tags.get(asn, {}), **self.composite_tags.get(asn, {})}
            value = all_tags.get(tag_name, None)

            if treat_false_as_missing:
                if value in [None, 0, [], {}, False]:
                    missing_asns.append(asn)
            else:
                if value is None:
                    missing_asns.append(asn)

        return missing_asns
    
    def Help(self, tag_name: str) -> Union[str, dict]:
        """
        Get description and metadata for a tag.
        
        Args:
            tag_name: Name of the tag to get help for.
            
        Returns:
            Tag description string or dict with metadata.
        """
        if tag_name in self.atomic_tag_description:
            return self.atomic_tag_description[tag_name]
        elif tag_name in self.composite_tag_description:
            return self.composite_tag_description[tag_name]
        else:
            return "ASTagging does not contain this tag. Please double-check the tag name."
    
    # =========================================================================
    # Backward compatibility aliases (lowercase method names)
    # =========================================================================
    
    def assign_tag(self, tag_name: str, expression: Union[dict, Callable]) -> None:
        """Alias for AssignTag (backward compatibility)."""
        return self.AssignTag(tag_name, expression)
    
    def fetch_tag(
        self, 
        tag_name: str, 
        asns: Optional[Union[str, List[str]]] = None,
        **kwargs
    ) -> Union[Any, Dict[str, Any]]:
        """Alias for FetchTag (backward compatibility)."""
        return self.FetchTag(tag_name, asns, **kwargs)
    
    def list_tags(self, asn: str) -> Dict[str, Dict[str, Any]]:
        """Alias for ListTags (backward compatibility)."""
        return self.ListTags(asn)

    def list_asns_without_tag(
        self,
        tag_name: str,
        treat_false_as_missing: bool = False,
    ) -> List[Any]:
        """Alias for ListASNsWithoutTag (backward compatibility)."""
        return self.ListASNsWithoutTag(
            tag_name=tag_name,
            treat_false_as_missing=treat_false_as_missing,
        )
    
    def help(self, tag_name: str) -> Union[str, dict]:
        """Alias for Help (backward compatibility)."""
        return self.Help(tag_name)
    
    # =========================================================================
    # Utility methods
    # =========================================================================
    
    def calculate_sum(self, key: str, subkey: str, as_list: List[str] = None) -> float:
        """
        Sum values of a specific key and subkey across ASes.
        
        Args:
            key: The main key in the tags dictionary.
            subkey: The subkey to sum up.
            as_list: Optional list of ASes to sum over. If None, sum across all.
            
        Returns:
            Total sum across specified ASes.
        """
        if as_list is None:
            as_list = self.atomic_tags.keys()
        else:
            # Normalize ASN inputs and resolve to actual keys
            keys = set(self.atomic_tags.keys())
            resolved = []
            for a in as_list:
                canon = normalize_asn_input(a)
                k = resolve_asn_to_key(canon, keys)
                if k is not None:
                    resolved.append(k)
            as_list = resolved
        
        return sum(
            self.atomic_tags.get(asn, {}).get(key, {}).get(subkey, 0) 
            for asn in as_list 
            if asn in self.atomic_tags
        )
    
    # Legacy attribute for backward compatibility
    @property
    def tags(self):
        """Legacy property - use atomic_tags instead."""
        return self.atomic_tags
    
    # Keep old method names working
    def load_preset_lambda(self, module_path="data.preset_lambda"):
        """Legacy method - preset tags are now loaded automatically."""
        self._load_preset_tags()
    
    def assign_composite_tags(self):
        """Legacy method - preset tags are now assigned automatically."""
        self._assign_all_preset_tags()
    
    def calculate_country_sums(self) -> Dict[str, int]:
        """Legacy method - use _calculate_country_sums instead."""
        return self._calculate_country_sums()