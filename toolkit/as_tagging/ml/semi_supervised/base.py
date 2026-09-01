"""
Base class for semi-supervised ML models.

Semi-supervised learning is used when only a small labeled set is available
(positive and optionally a small negative set). New models can be added by
subclassing BaseSemiSupervisedModel and registering in SEMI_SUPERVISED_MODEL_REGISTRY.
"""

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any

import numpy as np


class BaseSemiSupervisedModel(ABC):
    """Abstract base for semi-supervised models (e.g., PUN)."""

    @abstractmethod
    def fit(
        self,
        positive_asns: List[str],
        negative_asns: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        """
        Fit the model using positive (and optionally negative) labeled ASNs.

        Args:
            positive_asns: ASNs known to have the target property.
            negative_asns: Optional ASNs known NOT to have the property.
            **kwargs: Model-specific options.
        """
        pass

    @abstractmethod
    def predict_proba(self, asns: Optional[List[str]] = None) -> np.ndarray:
        """
        Predict scores (probability-like, in [0,1]) for ASNs.

        Args:
            asns: ASNs to score. If None, score all.

        Returns:
            1D array of scores, aligned with the requested asn order.
        """
        pass

    @property
    def name(self) -> str:
        return self.__class__.__name__
