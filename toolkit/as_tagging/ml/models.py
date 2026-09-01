"""
ML model definitions for AS tagging.

Provides 4 supervised learning models with a common interface:
- XGBoostModel: Tree-based ensemble (feature-only)
- TabularMLP: Feed-forward neural network with categorical embeddings
- GraphTabularNet: Graph Convolutional Network (requires topology)
- MLP_APPNP: MLP + Approximate Personalized PageRank (requires topology)
"""

import numpy as np
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Tuple


class BaseMLModel(ABC):
    """Abstract base class for all ML models used in AS tagging."""
    
    @abstractmethod
    def train(self, train_data: dict, val_data: dict, **kwargs) -> dict:
        """
        Train the model.
        
        Args:
            train_data: Dict with keys depending on model type
            val_data: Dict with keys depending on model type
            
        Returns:
            Training metrics dict
        """
        pass
    
    @abstractmethod
    def predict_proba(self, data: dict) -> np.ndarray:
        """
        Predict probabilities for all samples.
        
        Args:
            data: Dict with model-specific input data
            
        Returns:
            1D array of probabilities
        """
        pass
    
    @abstractmethod
    def requires_graph(self) -> bool:
        """Whether this model requires graph/topology information."""
        pass
    
    @property
    def name(self) -> str:
        return self.__class__.__name__


def _metrics(y_true, y_prob, thr=0.5) -> dict:
    """Compute binary classification metrics."""
    from sklearn.metrics import (
        precision_recall_fscore_support, accuracy_score,
        roc_auc_score, average_precision_score
    )
    
    y_pred = (np.asarray(y_prob) >= thr).astype(int)
    y_true = np.asarray(y_true).astype(int)
    
    p, r, f1, _ = precision_recall_fscore_support(
        y_true, y_pred, average="binary", zero_division=0
    )
    acc = accuracy_score(y_true, y_pred)
    
    try:
        auroc = roc_auc_score(y_true, y_prob)
    except (ValueError, IndexError):
        auroc = float("nan")
    
    try:
        auprc = average_precision_score(y_true, y_prob)
    except (ValueError, IndexError):
        auprc = float("nan")
    
    return {
        "precision": float(p),
        "recall": float(r),
        "f1": float(f1),
        "accuracy": float(acc),
        "auroc": float(auroc),
        "auprc": float(auprc),
    }


# ============================================================================
# XGBoost Model
# ============================================================================

# Predefined hyperparameter profiles for automated selection
# "stochastic" matches the old pipeline (new_ml_tagging_final_access.ipynb) for parity
XGB_PROFILES = {
    "stochastic": dict(
        n_estimators=1200, max_depth=5, learning_rate=0.08,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=4,
        gamma=0.0, reg_alpha=0.0, reg_lambda=1.0,
    ),
    "default": dict(
        n_estimators=600, max_depth=6, learning_rate=0.05,
        subsample=0.8, colsample_bytree=0.8, min_child_weight=3,
        gamma=0.1, reg_alpha=0.1, reg_lambda=1.0,
    ),
    "deep": dict(
        n_estimators=800, max_depth=8, learning_rate=0.03,
        subsample=0.7, colsample_bytree=0.7, min_child_weight=5,
        gamma=0.2, reg_alpha=0.5, reg_lambda=2.0,
    ),
    "shallow": dict(
        n_estimators=400, max_depth=4, learning_rate=0.1,
        subsample=0.9, colsample_bytree=0.9, min_child_weight=1,
        gamma=0.0, reg_alpha=0.0, reg_lambda=1.0,
    ),
}


class XGBoostModel(BaseMLModel):
    """XGBoost tree-based ensemble model."""

    def __init__(
        self,
        profiles: Optional[Dict[str, dict]] = None,
        random_seed: int = 42,
        n_jobs: int = 4,
        force_profile: Optional[str] = None,
    ):
        self.profiles = profiles or XGB_PROFILES
        self.random_seed = random_seed
        self.n_jobs = n_jobs
        self.force_profile = force_profile  # Skip inner CV when set (old pipeline parity)
        self.clf = None
        self.best_profile = None
    
    def requires_graph(self) -> bool:
        return False
    
    def _balanced_weights(self, y):
        """Compute balanced class weights."""
        y = np.asarray(y)
        n_pos = max(1, int((y == 1).sum()))
        n_neg = max(1, int((y == 0).sum()))
        N = len(y)
        w_pos = N / (2.0 * n_pos)
        w_neg = N / (2.0 * n_neg)
        return np.where(y == 1, w_pos, w_neg).astype(np.float32)
    
    def _select_profile_by_inner_cv(
        self, X, y, labeled_idx, n_splits=3
    ) -> Tuple[str, dict]:
        """Select best XGBoost profile via inner cross-validation."""
        import xgboost as xgb
        from sklearn.model_selection import StratifiedKFold
        from sklearn.metrics import average_precision_score
        
        X_lbl = X.iloc[labeled_idx] if hasattr(X, 'iloc') else X[labeled_idx]
        y_lbl = y[labeled_idx] if isinstance(y, np.ndarray) else np.array(y)[labeled_idx]
        
        best_name = "default"
        best_auprc = -1.0
        summary = {}
        
        for name, params in self.profiles.items():
            fold_metrics = []
            skf = StratifiedKFold(
                n_splits=n_splits, shuffle=True, random_state=self.random_seed
            )
            
            for tr_idx, va_idx in skf.split(X_lbl, y_lbl):
                X_tr = X_lbl.iloc[tr_idx] if hasattr(X_lbl, 'iloc') else X_lbl[tr_idx]
                X_va = X_lbl.iloc[va_idx] if hasattr(X_lbl, 'iloc') else X_lbl[va_idx]
                y_tr = y_lbl[tr_idx]
                y_va = y_lbl[va_idx]
                
                clf = xgb.XGBClassifier(
                    objective="binary:logistic",
                    tree_method="hist",
                    enable_categorical=True,
                    eval_metric="aucpr",
                    random_state=self.random_seed,
                    n_jobs=self.n_jobs,
                    **params,
                )
                clf.fit(
                    X_tr, y_tr,
                    sample_weight=self._balanced_weights(y_tr),
                    verbose=False,
                )
                prob_va = clf.predict_proba(X_va)[:, 1]
                m = _metrics(y_va, prob_va)
                fold_metrics.append(m)
            
            mean_auprc = np.mean([m["auprc"] for m in fold_metrics])
            mean_f1 = np.mean([m["f1"] for m in fold_metrics])
            summary[name] = {"auprc": mean_auprc, "f1": mean_f1}
            
            if mean_auprc > best_auprc:
                best_auprc = mean_auprc
                best_name = name
        
        return best_name, summary
    
    def train(self, train_data: dict, val_data: dict, **kwargs) -> dict:
        """
        Train XGBoost model.
        
        train_data keys: X (DataFrame), y (array), labeled_mask (bool array)
        val_data keys: X (DataFrame), y (array)
        """
        import xgboost as xgb
        
        X_all = train_data["X"]
        y_all = train_data["y"]
        labeled_mask = train_data.get("labeled_mask", y_all >= 0)
        labeled_idx = np.where(labeled_mask)[0]

        # Use forced profile or auto-select via inner CV
        if self.force_profile is not None:
            if self.force_profile not in self.profiles:
                raise ValueError(
                    f"Unknown XGBoost profile '{self.force_profile}'. "
                    f"Available: {list(self.profiles.keys())}"
                )
            self.best_profile = self.force_profile
        else:
            self.best_profile, inner_summary = self._select_profile_by_inner_cv(
                X_all, y_all, labeled_idx, n_splits=3
            )

        best_params = self.profiles[self.best_profile]
        
        X_lbl = X_all.iloc[labeled_idx] if hasattr(X_all, 'iloc') else X_all[labeled_idx]
        y_lbl = y_all[labeled_idx]
        
        self.clf = xgb.XGBClassifier(
            objective="binary:logistic",
            tree_method="hist",
            enable_categorical=True,
            eval_metric="aucpr",
            random_state=self.random_seed,
            n_jobs=self.n_jobs,
            **best_params,
        )
        self.clf.fit(
            X_lbl, y_lbl,
            sample_weight=self._balanced_weights(y_lbl),
            verbose=False,
        )
        
        # Evaluate on validation data if provided
        if val_data and "X" in val_data and "y" in val_data:
            prob_val = self.clf.predict_proba(val_data["X"])[:, 1]
            return _metrics(val_data["y"], prob_val)
        
        return {}
    
    def predict_proba(self, data: dict) -> np.ndarray:
        """Predict probabilities. data keys: X (DataFrame)"""
        if self.clf is None:
            raise RuntimeError("Model not trained. Call train() first.")
        return self.clf.predict_proba(data["X"])[:, 1]
    
    def save(self, path: str):
        if self.clf is not None:
            self.clf.get_booster().save_model(path)
    
    def load(self, path: str):
        import xgboost as xgb
        self.clf = xgb.XGBClassifier()
        self.clf.load_model(path)


# ============================================================================
# MLP Model
# ============================================================================

class TabularMLP(BaseMLModel):
    """
    Feed-forward MLP with categorical embeddings.
    
    Uses BatchNorm + ReLU + Dropout between layers.
    Categorical features are embedded into dense vectors.
    """
    
    def __init__(
        self,
        hidden: tuple = (256, 128),
        emb_dim_max: int = 32,
        p_drop: float = 0.2,
        lr: float = 1e-3,
        weight_decay: float = 1e-5,
        max_epochs: int = 250,
        patience: int = 25,
        batch_size: int = 256,
    ):
        self.hidden = hidden
        self.emb_dim_max = emb_dim_max
        self.p_drop = p_drop
        self.lr = lr
        self.weight_decay = weight_decay
        self.max_epochs = max_epochs
        self.patience = patience
        self.batch_size = batch_size
        self.model = None
        self.device = "cpu"
    
    def requires_graph(self) -> bool:
        return False
    
    def _build_model(self, num_dim: int, cat_cardinalities: list):
        """Build the PyTorch MLP module."""
        import torch
        import torch.nn as nn
        
        class _MLP(nn.Module):
            def __init__(self, num_dim, cat_cardinalities, emb_dim_max, hidden, p_drop):
                super().__init__()
                self.cat_cardinalities = list(cat_cardinalities)
                
                # Embeddings for categorical features
                self.emb_layers = nn.ModuleList()
                emb_dims = []
                for card in self.cat_cardinalities:
                    emb_dim = min(emb_dim_max, (card + 1) // 2)
                    self.emb_layers.append(nn.Embedding(card, emb_dim))
                    emb_dims.append(emb_dim)
                total_emb_dim = sum(emb_dims)
                
                in_dim = num_dim + total_emb_dim
                layers = []
                prev = in_dim
                for h in hidden:
                    layers.append(nn.Linear(prev, h))
                    layers.append(nn.BatchNorm1d(h))
                    layers.append(nn.ReLU())
                    layers.append(nn.Dropout(p_drop))
                    prev = h
                layers.append(nn.Linear(prev, 1))
                self.mlp = nn.Sequential(*layers)
            
            def _build_input(self, x_num, x_cat=None):
                if self.emb_layers and x_cat is not None:
                    embs = [emb(x_cat[:, j]) for j, emb in enumerate(self.emb_layers)]
                    x_cat_emb = torch.cat(embs, dim=1)
                    return torch.cat([x_num, x_cat_emb], dim=1)
                return x_num
            
            def forward(self, x_num, x_cat=None):
                x = self._build_input(x_num, x_cat)
                return self.mlp(x).squeeze(-1)
        
        return _MLP(num_dim, cat_cardinalities, self.emb_dim_max, self.hidden, self.p_drop)
    
    def train(self, train_data: dict, val_data: dict, **kwargs) -> dict:
        """
        Train MLP model.
        
        train_data/val_data keys: X_num (tensor), X_cat (tensor or None),
                                   y (array), cat_cards (list)
        """
        import torch
        import torch.nn as nn
        from copy import deepcopy
        
        X_num_tr = train_data["X_num"].to(self.device)
        X_cat_tr = train_data.get("X_cat")
        if X_cat_tr is not None:
            X_cat_tr = X_cat_tr.to(self.device)
        y_tr = torch.tensor(train_data["y"], dtype=torch.float32).to(self.device)
        
        X_num_va = val_data["X_num"].to(self.device)
        X_cat_va = val_data.get("X_cat")
        if X_cat_va is not None:
            X_cat_va = X_cat_va.to(self.device)
        y_va = torch.tensor(val_data["y"], dtype=torch.float32).to(self.device)
        
        cat_cards = train_data.get("cat_cards", [])
        num_dim = X_num_tr.shape[1]
        
        self.model = self._build_model(num_dim, cat_cards).to(self.device)
        
        # Class imbalance weight
        n_pos = max(1, int((y_tr == 1).sum().item()))
        n_neg = max(1, int((y_tr == 0).sum().item()))
        pos_weight = torch.tensor(n_neg / n_pos, device=self.device)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        
        optimizer = torch.optim.Adam(
            self.model.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )
        
        best_state = None
        best_val_f1 = -1.0
        no_improve = 0
        
        def _batch_iter(X_num, X_cat, y, batch_size, shuffle=True):
            n = X_num.shape[0]
            idx = torch.randperm(n) if shuffle else torch.arange(n)
            for start in range(0, n, batch_size):
                end = min(start + batch_size, n)
                bi = idx[start:end]
                xn = X_num[bi]
                xc = X_cat[bi] if X_cat is not None else None
                yb = y[bi]
                yield xn, xc, yb
        
        for epoch in range(1, self.max_epochs + 1):
            self.model.train()
            for xb, xcb, yb in _batch_iter(X_num_tr, X_cat_tr, y_tr, self.batch_size):
                optimizer.zero_grad()
                logits = self.model(xb, xcb)
                loss = criterion(logits, yb)
                loss.backward()
                optimizer.step()
            
            # Validation
            self.model.eval()
            with torch.no_grad():
                logits_va = self.model(X_num_va, X_cat_va)
                prob_va = torch.sigmoid(logits_va).cpu().numpy()
                y_va_np = y_va.cpu().numpy()
                m_va = _metrics(y_va_np, prob_va)
                val_f1 = m_va["f1"]
            
            if val_f1 > best_val_f1 + 1e-4:
                best_val_f1 = val_f1
                best_state = deepcopy(self.model.state_dict())
                no_improve = 0
            else:
                no_improve += 1
            
            if no_improve >= self.patience:
                break
        
        if best_state is not None:
            self.model.load_state_dict(best_state)
        
        return m_va
    
    def predict_proba(self, data: dict) -> np.ndarray:
        """
        Predict probabilities.
        data keys: X_num (tensor), X_cat (tensor or None)
        """
        import torch
        
        if self.model is None:
            raise RuntimeError("Model not trained.")
        
        self.model.eval()
        with torch.no_grad():
            X_num = data["X_num"].to(self.device)
            X_cat = data.get("X_cat")
            if X_cat is not None:
                X_cat = X_cat.to(self.device)
            logits = self.model(X_num, X_cat)
            return torch.sigmoid(logits).cpu().numpy()

    def save(self, path: str) -> None:
        """Save model state_dict to path."""
        import torch
        if self.model is not None:
            torch.save(self.model.state_dict(), path)

    def load(self, path: str, num_dim: int, cat_cardinalities: List[int]) -> None:
        """Load model from path. Rebuilds architecture using num_dim and cat_cardinalities."""
        import torch
        self.model = self._build_model(num_dim, cat_cardinalities).to(self.device)
        state = torch.load(path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)


# ============================================================================
# GraphConv GNN Model
# ============================================================================

class GraphTabularNet(BaseMLModel):
    """
    2-layer GraphConv GNN with categorical embeddings.
    
    Uses DGL's GraphConv layers to aggregate information from
    neighboring ASes in the topology graph.
    """
    
    def __init__(
        self,
        hidden: tuple = (128, 64),
        emb_dim_max: int = 32,
        p_drop: float = 0.3,
        lr: float = 1e-3,
        weight_decay: float = 5e-4,
        max_epochs: int = 250,
        patience: int = 25,
    ):
        self.hidden = hidden
        self.emb_dim_max = emb_dim_max
        self.p_drop = p_drop
        self.lr = lr
        self.weight_decay = weight_decay
        self.max_epochs = max_epochs
        self.patience = patience
        self.model = None
        self.device = "cpu"
    
    def requires_graph(self) -> bool:
        return True
    
    def _build_model(self, num_dim: int, cat_cardinalities: list):
        """Build the GraphConv model."""
        import torch
        import torch.nn as nn
        import torch.nn.functional as F
        from dgl.nn import GraphConv
        
        class _GNN(nn.Module):
            def __init__(self, num_dim, cat_cardinalities, emb_dim_max, hidden, p_drop):
                super().__init__()
                self.cat_cardinalities = list(cat_cardinalities)
                
                self.emb_layers = nn.ModuleList()
                emb_dims = []
                for card in self.cat_cardinalities:
                    emb_dim = min(emb_dim_max, (card + 1) // 2)
                    self.emb_layers.append(nn.Embedding(card, emb_dim))
                    emb_dims.append(emb_dim)
                total_emb_dim = sum(emb_dims)
                
                in_dim = num_dim + total_emb_dim
                self.gc1 = GraphConv(in_dim, hidden[0], activation=F.relu)
                self.gc2 = GraphConv(hidden[0], hidden[-1])
                self.dropout = nn.Dropout(p_drop)
                self.out = nn.Linear(hidden[-1], 1)
            
            def _build_input(self, x_num, x_cat=None):
                if self.emb_layers and x_cat is not None:
                    embs = [emb(x_cat[:, j]) for j, emb in enumerate(self.emb_layers)]
                    return torch.cat([x_num] + embs, dim=1)
                return x_num
            
            def forward(self, g, x_num, x_cat=None):
                h0 = self._build_input(x_num, x_cat)
                h = self.gc1(g, h0)
                h = self.dropout(h)
                h = self.gc2(g, h)
                h = self.dropout(h)
                return self.out(h).squeeze(-1)
        
        return _GNN(num_dim, cat_cardinalities, self.emb_dim_max, self.hidden, self.p_drop)
    
    def train(self, train_data: dict, val_data: dict, **kwargs) -> dict:
        """
        Train GraphConv GNN.
        
        train_data keys: X_num_all (tensor), X_cat_all (tensor or None),
                          y_all (tensor), train_mask (bool tensor),
                          val_mask (bool tensor), graph (DGL homogeneous),
                          cat_cards (list)
        """
        import torch
        import torch.nn as nn
        from copy import deepcopy
        
        hg = train_data["graph"].to(self.device)
        X_num = train_data["X_num_all"].to(self.device)
        X_cat = train_data.get("X_cat_all")
        if X_cat is not None:
            X_cat = X_cat.to(self.device)
        y_t = train_data["y_all"].to(self.device)
        train_mask = train_data["train_mask"].to(self.device)
        val_mask = train_data["val_mask"].to(self.device)
        cat_cards = train_data.get("cat_cards", [])
        
        num_dim = X_num.shape[1]
        self.model = self._build_model(num_dim, cat_cards).to(self.device)
        
        # Class weight
        y_train = y_t[train_mask].cpu().numpy()
        n_pos = max(1, int((y_train == 1).sum()))
        n_neg = max(1, int((y_train == 0).sum()))
        pos_weight = torch.tensor(n_neg / n_pos, device=self.device)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        
        optimizer = torch.optim.Adam(
            self.model.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )
        
        best_state = None
        best_val_f1 = -1.0
        no_improve = 0
        m_va = {}
        
        for epoch in range(1, self.max_epochs + 1):
            self.model.train()
            optimizer.zero_grad()
            logits = self.model(hg, X_num, X_cat)
            loss = criterion(logits[train_mask], y_t[train_mask].float())
            loss.backward()
            optimizer.step()
            
            self.model.eval()
            with torch.no_grad():
                logits_val = self.model(hg, X_num, X_cat)[val_mask]
                prob_val = torch.sigmoid(logits_val).cpu().numpy()
                y_val_np = y_t[val_mask].cpu().numpy()
                m_va = _metrics(y_val_np, prob_val)
                val_f1 = m_va["f1"]
            
            if val_f1 > best_val_f1 + 1e-4:
                best_val_f1 = val_f1
                best_state = deepcopy(self.model.state_dict())
                no_improve = 0
            else:
                no_improve += 1
            
            if no_improve >= self.patience:
                break
        
        if best_state is not None:
            self.model.load_state_dict(best_state)
        
        return m_va
    
    def predict_proba(self, data: dict) -> np.ndarray:
        """
        Predict probabilities for all nodes.
        data keys: graph (DGL), X_num_all (tensor), X_cat_all (tensor or None)
        """
        import torch
        
        if self.model is None:
            raise RuntimeError("Model not trained.")
        
        self.model.eval()
        with torch.no_grad():
            hg = data["graph"].to(self.device)
            X_num = data["X_num_all"].to(self.device)
            X_cat = data.get("X_cat_all")
            if X_cat is not None:
                X_cat = X_cat.to(self.device)
            logits = self.model(hg, X_num, X_cat)
            return torch.sigmoid(logits).cpu().numpy()

    def save(self, path: str) -> None:
        """Save model state_dict to path."""
        import torch
        if self.model is not None:
            torch.save(self.model.state_dict(), path)

    def load(self, path: str, num_dim: int, cat_cardinalities: List[int]) -> None:
        """Load model from path. Rebuilds architecture using num_dim and cat_cardinalities."""
        import torch
        self.model = self._build_model(num_dim, cat_cardinalities).to(self.device)
        state = torch.load(path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)


# ============================================================================
# APPNP Model
# ============================================================================

class MLPAPPNPModel(BaseMLModel):
    """
    MLP backbone with Approximate Personalized PageRank (APPNP) propagation.
    
    Computes base logits with an MLP, then propagates them through the
    AS topology graph using the APPNP algorithm.
    """
    
    def __init__(
        self,
        hidden: tuple = (256, 128),
        emb_dim_max: int = 32,
        p_drop: float = 0.2,
        alpha: float = 0.1,
        K: int = 10,
        lr: float = 1e-3,
        weight_decay: float = 1e-5,
        max_epochs: int = 250,
        patience: int = 25,
    ):
        self.hidden = hidden
        self.emb_dim_max = emb_dim_max
        self.p_drop = p_drop
        self.alpha = alpha
        self.K = K
        self.lr = lr
        self.weight_decay = weight_decay
        self.max_epochs = max_epochs
        self.patience = patience
        self.model = None
        self.device = "cpu"
    
    def requires_graph(self) -> bool:
        return True
    
    def _build_model(self, num_dim: int, cat_cardinalities: list):
        """Build the MLP + APPNP model."""
        import torch
        import torch.nn as nn
        
        alpha = self.alpha
        K_steps = self.K
        
        class _APPNP(nn.Module):
            def __init__(self, num_dim, cat_cardinalities, emb_dim_max, hidden, p_drop, alpha, K):
                super().__init__()
                self.cat_cardinalities = list(cat_cardinalities)
                self.alpha = alpha
                self.K = K
                
                self.emb_layers = nn.ModuleList()
                emb_dims = []
                for card in self.cat_cardinalities:
                    emb_dim = min(emb_dim_max, (card + 1) // 2)
                    self.emb_layers.append(nn.Embedding(card, emb_dim))
                    emb_dims.append(emb_dim)
                total_emb_dim = sum(emb_dims)
                
                in_dim = num_dim + total_emb_dim
                layers = []
                prev = in_dim
                for h in hidden:
                    layers.append(nn.Linear(prev, h))
                    layers.append(nn.BatchNorm1d(h))
                    layers.append(nn.ReLU())
                    layers.append(nn.Dropout(p_drop))
                    prev = h
                layers.append(nn.Linear(prev, 1))
                self.mlp = nn.Sequential(*layers)
            
            def _build_input(self, x_num, x_cat=None):
                if self.emb_layers and x_cat is not None:
                    embs = [emb(x_cat[:, j]) for j, emb in enumerate(self.emb_layers)]
                    return torch.cat([x_num] + embs, dim=1)
                return x_num
            
            def forward(self, P, x_num, x_cat=None):
                X = self._build_input(x_num, x_cat)
                z0 = self.mlp(X).squeeze(-1)  # [N] base logits
                
                # APPNP propagation on logits
                Z = z0.unsqueeze(1)  # [N,1]
                Z0 = Z.clone()
                for _ in range(self.K):
                    Z = (1 - self.alpha) * Z0 + self.alpha * torch.sparse.mm(P, Z)
                return Z.squeeze(1)  # [N] propagated logits
        
        return _APPNP(
            num_dim, cat_cardinalities, self.emb_dim_max,
            self.hidden, self.p_drop, alpha, K_steps
        )
    
    def train(self, train_data: dict, val_data: dict, **kwargs) -> dict:
        """
        Train MLP + APPNP model.
        
        train_data keys: X_num_all (tensor), X_cat_all (tensor or None),
                          y_all (tensor), train_mask (bool tensor),
                          val_mask (bool tensor), P (sparse propagation matrix),
                          cat_cards (list)
        """
        import torch
        import torch.nn as nn
        
        P = train_data["P"].to(self.device)
        X_num = train_data["X_num_all"].to(self.device)
        X_cat = train_data.get("X_cat_all")
        if X_cat is not None:
            X_cat = X_cat.to(self.device)
        y_t = train_data["y_all"].to(self.device)
        train_mask = train_data["train_mask"].to(self.device)
        val_mask = train_data["val_mask"].to(self.device)
        cat_cards = train_data.get("cat_cards", [])
        
        num_dim = X_num.shape[1]
        self.model = self._build_model(num_dim, cat_cards).to(self.device)
        
        y_train = y_t[train_mask].cpu().numpy()
        n_pos = max(1, int((y_train == 1).sum()))
        n_neg = max(1, int((y_train == 0).sum()))
        pos_weight = torch.tensor(n_neg / n_pos, device=self.device)
        criterion = nn.BCEWithLogitsLoss(pos_weight=pos_weight)
        
        optimizer = torch.optim.Adam(
            self.model.parameters(), lr=self.lr, weight_decay=self.weight_decay
        )
        
        best_state = None
        best_val_f1 = -1.0
        no_improve = 0
        m_va = {}
        
        for epoch in range(1, self.max_epochs + 1):
            self.model.train()
            optimizer.zero_grad()
            logits = self.model(P, X_num, X_cat)
            loss = criterion(logits[train_mask], y_t[train_mask].float())
            loss.backward()
            optimizer.step()
            
            self.model.eval()
            with torch.no_grad():
                logits_val = self.model(P, X_num, X_cat)[val_mask]
                prob_val = torch.sigmoid(logits_val).cpu().numpy()
                y_val_np = y_t[val_mask].cpu().numpy()
                m_va = _metrics(y_val_np, prob_val)
                val_f1 = m_va["f1"]
            
            if val_f1 > best_val_f1 + 1e-4:
                best_val_f1 = val_f1
                best_state = {k: v.cpu().clone() for k, v in self.model.state_dict().items()}
                no_improve = 0
            else:
                no_improve += 1
            
            if no_improve >= self.patience:
                break
        
        if best_state is not None:
            self.model.load_state_dict({k: v.to(self.device) for k, v in best_state.items()})
        
        return m_va
    
    def predict_proba(self, data: dict) -> np.ndarray:
        """
        Predict probabilities.
        data keys: P (sparse matrix), X_num_all (tensor), X_cat_all (tensor or None)
        """
        import torch
        
        if self.model is None:
            raise RuntimeError("Model not trained.")
        
        self.model.eval()
        with torch.no_grad():
            P = data["P"].to(self.device)
            X_num = data["X_num_all"].to(self.device)
            X_cat = data.get("X_cat_all")
            if X_cat is not None:
                X_cat = X_cat.to(self.device)
            logits = self.model(P, X_num, X_cat)
            return torch.sigmoid(logits).cpu().numpy()

    def save(self, path: str) -> None:
        """Save model state_dict to path."""
        import torch
        if self.model is not None:
            torch.save(self.model.state_dict(), path)

    def load(self, path: str, num_dim: int, cat_cardinalities: List[int]) -> None:
        """Load model from path. Rebuilds architecture using num_dim and cat_cardinalities."""
        import torch
        self.model = self._build_model(num_dim, cat_cardinalities).to(self.device)
        state = torch.load(path, map_location=self.device, weights_only=True)
        self.model.load_state_dict(state)


# ============================================================================
# Model registry
# ============================================================================

MODEL_REGISTRY = {
    "xgboost": XGBoostModel,
    "mlp": TabularMLP,
    "graphconv": GraphTabularNet,
    "appnp": MLPAPPNPModel,
}

ALL_MODEL_NAMES = list(MODEL_REGISTRY.keys())
FEATURE_ONLY_MODELS = ["xgboost", "mlp"]
GRAPH_MODELS = ["graphconv", "appnp"]
