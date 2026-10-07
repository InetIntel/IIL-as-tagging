import builtins
from unittest import mock

import numpy as np
import pandas as pd

import as_tagging.ml.ml_tagger as ml_tagger


class FakeXGBoostModel:
    def __init__(self, **kwargs):
        self.train_data = None

    def train(self, train_data, val_data):
        self.train_data = train_data


def test_final_xgboost_training_does_not_import_neural_dependencies():
    tagger = ml_tagger.MLTagger.__new__(ml_tagger.MLTagger)
    tagger._best_model_name = "xgboost"
    tagger.xgboost_profile = None
    tagger._feature_df = pd.DataFrame({"feature": [1.0, 2.0, 3.0, 4.0]})
    tagger._num_cols = ["feature"]
    tagger._cat_cols = []
    tagger._log = lambda message: None

    original_import = builtins.__import__

    def import_without_neural_dependencies(name, *args, **kwargs):
        if name == "torch" or name.startswith("torch."):
            raise ModuleNotFoundError("No module named 'torch'")
        if name == "sklearn" or name.startswith("sklearn."):
            raise ModuleNotFoundError("No module named 'sklearn'")
        return original_import(name, *args, **kwargs)

    with mock.patch.dict(
        ml_tagger.MODEL_REGISTRY, {"xgboost": FakeXGBoostModel}
    ), mock.patch(
        "builtins.__import__", side_effect=import_without_neural_dependencies
    ):
        tagger._train_final_model(
            np.array([0, 1, -1, 0]), np.array([0, 1, 3])
        )

    assert isinstance(tagger._best_model, FakeXGBoostModel)
    assert tagger._best_model.train_data["labeled_mask"].sum() == 3
