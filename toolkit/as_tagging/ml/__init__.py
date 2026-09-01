"""
AS Tagging - Machine Learning Module

Provides:
- Supervised ML: XGBoost, MLP, GraphConv, APPNP
- Semi-supervised ML: PUN (Positive, Unlabeled, small Negative)

Usage:
    from as_tagging.ml import MLTagger, SemiSupervisedMLTagger

    # Supervised
    ml = MLTagger(tagger.atomic_tags)
    results = ml.train_and_select(positive_asns, negative_asns)
    predictions = ml.tag(threshold=0.5)

    # Semi-supervised (PUN)
    ss = SemiSupervisedMLTagger(tagger.atomic_tags, model="pun")
    ss.fit(positive_asns, negative_asns)
    predictions = ss.tag(threshold=0.5)
"""

from .ml_tagger import MLTagger
from .semi_supervised_tagger import SemiSupervisedMLTagger
from .semi_supervised import SEMI_SUPERVISED_MODEL_REGISTRY

__all__ = ["MLTagger", "SemiSupervisedMLTagger", "SEMI_SUPERVISED_MODEL_REGISTRY"]
