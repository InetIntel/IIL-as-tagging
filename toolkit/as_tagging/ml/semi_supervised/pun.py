"""
PUN model: Positive, Unlabeled, and small Negative.

Inspired by the PUbN (Positive, Unlabeled, biased Negative) formulation of Hsieh et al.
Supports graph-based PPR propagation, feature-based scoring (LogReg, OCC, AE),
and combined graph+feature scores.
"""

import numpy as np
from typing import Dict, List, Optional, Any

from .base import BaseSemiSupervisedModel


def _to_int_set(asns) -> set:
    """Normalize ASNs to integer set."""
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


def _canonicalize_asn(asn) -> str:
    s = str(asn).strip().upper()
    return s[2:] if s.startswith("AS") else s


def _pick_threshold_at_precision(
    y_true: np.ndarray, score: np.ndarray, target_p: float = 0.95, default: float = 0.5
) -> tuple:
    """Return threshold for target precision with max recall. Returns (thr, p, r)."""
    from sklearn.metrics import precision_recall_curve

    p, r, thr = precision_recall_curve(y_true, score)
    p, r = p[:-1], r[:-1]
    ok = np.where(p >= target_p)[0]
    if ok.size:
        i = ok[np.argmax(r[ok])]
        return float(thr[i]), float(p[i]), float(r[i])
    if thr.size == 0:
        return default, 0.0, 0.0
    i_best = np.argmax(p)
    return float(thr[i_best]), float(p[i_best]), float(r[i_best])


def _safe_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    from sklearn.metrics import f1_score

    try:
        return float(f1_score(y_true, y_pred, zero_division=0))
    except Exception:
        return 0.0


class PUNModel(BaseSemiSupervisedModel):
    """
    PUN: Positive, Unlabeled, small Negative.

    Combines graph-based PPR propagation with feature-based scoring.
    Sub-methods: graph_ppr, logreg, occ, ae, combined.
    """

    def __init__(
        self,
        X: np.ndarray,
        asn_list: List[Any],
        P=None,
        asn_to_graph_id: Optional[Dict[int, int]] = None,
        method: str = "combined",
        w_feat: float = 0.5,
        w_graph: float = 0.5,
        ppr_alpha: float = 0.9,
        ppr_steps: int = 50,
        verbose: bool = True,
    ):
        """
        Args:
            X: Numeric feature matrix (N, F).
            asn_list: ASN per row, aligned with X.
            P: Optional sparse propagation matrix (graph nodes).
            asn_to_graph_id: Optional {asn_int: graph_node_id} for nodes in graph.
            method: "graph_ppr", "logreg", "occ", "ae", "combined".
            w_feat: Weight for feature score when method="combined".
            w_graph: Weight for graph score when method="combined".
            ppr_alpha: PPR diffusion alpha.
            ppr_steps: PPR diffusion steps.
        """
        self.X = np.asarray(X, dtype=np.float32)
        self.asn_list = list(asn_list)
        self.N = len(self.asn_list)
        self.asn_to_idx = {}
        for i, a in enumerate(self.asn_list):
            try:
                k = int(_canonicalize_asn(a))
                self.asn_to_idx[k] = i
            except (ValueError, TypeError):
                self.asn_to_idx[a] = i
        self.P = P
        self.asn_to_graph_id = asn_to_graph_id or {}
        self.method = method
        self.w_feat = w_feat
        self.w_graph = w_graph
        self.ppr_alpha = ppr_alpha
        self.ppr_steps = ppr_steps
        self.verbose = verbose

        self._feat_score = None
        self._graph_score = None
        self._combined_score = None
        self._scaler = None
        self._clf = None
        self._ocsvm = None
        self._ae = None
        self._oof_labeled_scores = {}

    def _log(self, msg: str):
        if self.verbose:
            print(f"[PUN] {msg}")

    def fit(
        self,
        positive_asns: List[str],
        negative_asns: Optional[List[str]] = None,
        **kwargs,
    ) -> None:
        pos_int = _to_int_set(positive_asns)
        neg_int = _to_int_set(negative_asns) if negative_asns else set()

        pos_idx = [self.asn_to_idx[a] for a in pos_int if a in self.asn_to_idx]
        neg_idx = [self.asn_to_idx[a] for a in neg_int if a in self.asn_to_idx]

        if not pos_idx:
            raise ValueError("No positive ASNs found in snapshot.")

        # Optional controls for the small-label PU+N regime.
        unlabeled_weight = float(kwargs.get("unlabeled_weight", 0.1))
        graph_neg_weight = float(kwargs.get("graph_neg_weight", 1.0))
        tune_blend_weight = bool(kwargs.get("tune_blend_weight", True))
        blend_grid = kwargs.get("blend_grid", [0.0, 0.25, 0.5, 0.75, 1.0])
        use_calibration = bool(kwargs.get("use_calibration", True))

        X_pos = self.X[pos_idx]
        X_neg = self.X[neg_idx] if neg_idx else None
        X_all = self.X
        unl_idx = [i for i in range(self.N) if i not in set(pos_idx) and i not in set(neg_idx)]

        # Graph score (PPR)
        if self.P is not None and self.asn_to_graph_id and self.method in ("graph_ppr", "combined"):
            import torch
            from ..propagation import propagate

            N_graph = self.P.shape[0]
            seed_pos = np.zeros(N_graph, dtype=np.float32)
            for a in pos_int:
                gid = self.asn_to_graph_id.get(a)
                if gid is not None:
                    seed_pos[gid] = 1.0
            device = self.P.device
            seed_pos_t = torch.from_numpy(seed_pos).to(device)
            with torch.no_grad():
                pos_prop = propagate(
                    self.P, seed_pos_t.unsqueeze(1), alpha=self.ppr_alpha, steps=self.ppr_steps
                )
                pos_prop = pos_prop.squeeze(1).clamp(0.0, 1.0).cpu().numpy()
                if neg_int:
                    seed_neg = np.zeros(N_graph, dtype=np.float32)
                    for a in neg_int:
                        gid = self.asn_to_graph_id.get(a)
                        if gid is not None:
                            seed_neg[gid] = 1.0
                    seed_neg_t = torch.from_numpy(seed_neg).to(device)
                    neg_prop = propagate(
                        self.P, seed_neg_t.unsqueeze(1), alpha=self.ppr_alpha, steps=self.ppr_steps
                    )
                    neg_prop = neg_prop.squeeze(1).clamp(0.0, 1.0).cpu().numpy()
                    graph_prop = np.clip(pos_prop - graph_neg_weight * neg_prop, 0.0, 1.0)
                else:
                    graph_prop = pos_prop
            self._graph_score = np.zeros(self.N, dtype=np.float32)
            for i, a in enumerate(self.asn_list):
                try:
                    k = int(_canonicalize_asn(a))
                    gid = self.asn_to_graph_id.get(k)
                    if gid is not None:
                        self._graph_score[i] = graph_prop[gid]
                except (ValueError, TypeError):
                    pass
        else:
            self._graph_score = np.zeros(self.N, dtype=np.float32)

        # Feature score
        if self.method in ("logreg", "occ", "ae", "combined"):
            from sklearn.preprocessing import StandardScaler

            self._scaler = StandardScaler()

            if self.method in ("logreg", "combined") and neg_idx:
                from sklearn.linear_model import LogisticRegression
                from sklearn.calibration import CalibratedClassifierCV

                # PU+N training: use positives + small negatives + unlabeled as weak negatives.
                X_train = np.vstack([X_pos, X_neg])
                y_train = np.array([1] * len(pos_idx) + [0] * len(neg_idx), dtype=np.int32)
                sw = np.ones(len(y_train), dtype=np.float32)
                pos_w = max(1.0, (len(y_train) - y_train.sum()) / max(y_train.sum(), 1))
                sw[: len(pos_idx)] *= pos_w

                if unlabeled_weight > 0 and unl_idx:
                    X_unl = X_all[unl_idx]
                    X_train = np.vstack([X_train, X_unl])
                    y_train = np.concatenate(
                        [y_train, np.zeros(len(unl_idx), dtype=np.int32)], axis=0
                    )
                    sw = np.concatenate(
                        [sw, np.full(len(unl_idx), float(unlabeled_weight), dtype=np.float32)],
                        axis=0,
                    )

                # Fit scaler on the same distribution used by the classifier.
                self._scaler.fit(X_train)
                X_train_s = self._scaler.transform(X_train)
                X_all_s = self._scaler.transform(X_all)

                base_clf = LogisticRegression(
                    penalty="l2",
                    C=1.0,
                    class_weight={0: 1.0, 1: pos_w},
                    max_iter=2000,
                    solver="lbfgs",
                )

                # Optional probability calibration (only when both classes are sufficient).
                min_class = min(int((y_train == 1).sum()), int((y_train == 0).sum()))
                if use_calibration and min_class >= 3:
                    cv_cal = min(3, min_class)
                    # sklearn calibration in some scipy/sklearn combos expects float64 buffers.
                    X_train_s = np.asarray(X_train_s, dtype=np.float64)
                    y_train = np.asarray(y_train, dtype=np.int64)
                    sw = np.asarray(sw, dtype=np.float64)
                    self._clf = CalibratedClassifierCV(base_clf, method="sigmoid", cv=cv_cal)
                    self._clf.fit(X_train_s, y_train, sample_weight=sw)
                else:
                    self._clf = base_clf
                    self._clf.fit(X_train_s, y_train, sample_weight=sw)

                if use_calibration and min_class >= 3:
                    X_all_s = np.asarray(X_all_s, dtype=np.float64)
                self._feat_score = self._clf.predict_proba(X_all_s)[:, 1].astype(np.float32)

                # Auto-tune graph/feature blend on labeled set.
                if tune_blend_weight and self.method == "combined" and len(neg_idx) > 0:
                    labeled_idx = np.array(pos_idx + neg_idx, dtype=np.int32)
                    y_l = np.array([1] * len(pos_idx) + [0] * len(neg_idx), dtype=np.int32)
                    feat_l = self._feat_score[labeled_idx]
                    graph_l = self._graph_score[labeled_idx]

                    best_w = float(self.w_feat)
                    best_f1 = -1.0
                    for w in blend_grid:
                        w = float(w)
                        comb_l = w * feat_l + (1.0 - w) * graph_l
                        f1 = _safe_f1(y_l, (comb_l >= 0.5).astype(np.int32))
                        if f1 > best_f1:
                            best_f1 = f1
                            best_w = w
                    self.w_feat = float(best_w)
                    self.w_graph = float(1.0 - best_w)
                    self._log(
                        f"Auto-tuned blend weights: w_feat={self.w_feat:.2f}, "
                        f"w_graph={self.w_graph:.2f}, labeled_F1={best_f1:.3f}"
                    )

                # Build out-of-fold labeled scores for less-leaky threshold tuning.
                self._oof_labeled_scores = {}
                try:
                    from sklearn.model_selection import StratifiedKFold

                    X_l = np.vstack([X_pos, X_neg])
                    y_l = np.array([1] * len(pos_idx) + [0] * len(neg_idx), dtype=np.int32)
                    labeled_asn = [self.asn_list[i] for i in (pos_idx + neg_idx)]
                    min_class = min(int((y_l == 1).sum()), int((y_l == 0).sum()))
                    n_splits = min(5, min_class)
                    if n_splits >= 2:
                        skf = StratifiedKFold(n_splits=n_splits, shuffle=True, random_state=42)
                        oof_feat = np.zeros(len(y_l), dtype=np.float32)
                        for tr, va in skf.split(X_l, y_l):
                            sc = StandardScaler()
                            X_tr = sc.fit_transform(X_l[tr])
                            X_va = sc.transform(X_l[va])
                            pos_tr = int((y_l[tr] == 1).sum())
                            neg_tr = int((y_l[tr] == 0).sum())
                            pos_w_tr = max(1.0, neg_tr / max(pos_tr, 1))
                            clf = LogisticRegression(
                                penalty="l2",
                                C=1.0,
                                class_weight={0: 1.0, 1: pos_w_tr},
                                max_iter=2000,
                                solver="lbfgs",
                            )
                            clf.fit(X_tr, y_l[tr])
                            oof_feat[va] = clf.predict_proba(X_va)[:, 1].astype(np.float32)

                        labeled_idx = np.array(pos_idx + neg_idx, dtype=np.int32)
                        oof_comb = self.w_feat * oof_feat + self.w_graph * self._graph_score[labeled_idx]
                        self._oof_labeled_scores = {
                            str(a): float(s) for a, s in zip(labeled_asn, oof_comb.tolist())
                        }
                except Exception:
                    self._oof_labeled_scores = {}

            elif self.method == "ae":
                import torch
                import torch.nn as nn

                X_pos_s = self._scaler.fit_transform(X_pos)
                X_all_s = self._scaler.transform(X_all)
                D = X_pos_s.shape[1]
                hidden, bottleneck = 64, 16

                class AE(nn.Module):
                    def __init__(self):
                        super().__init__()
                        self.encoder = nn.Sequential(
                            nn.Linear(D, hidden), nn.ReLU(),
                            nn.Linear(hidden, bottleneck), nn.ReLU(),
                        )
                        self.decoder = nn.Sequential(
                            nn.Linear(bottleneck, hidden), nn.ReLU(),
                            nn.Linear(hidden, D),
                        )

                    def forward(self, x):
                        return self.decoder(self.encoder(x))

                ae = AE()
                opt = torch.optim.Adam(ae.parameters(), lr=1e-3)
                crit = nn.MSELoss()
                X_pos_t = torch.from_numpy(X_pos_s.astype(np.float32))
                for _ in range(50):
                    opt.zero_grad()
                    loss = crit(ae(X_pos_t), X_pos_t)
                    loss.backward()
                    opt.step()

                ae.eval()
                with torch.no_grad():
                    X_all_t = torch.from_numpy(X_all_s.astype(np.float32))
                    recon = ae(X_all_t)
                    mse = ((recon - X_all_t) ** 2).mean(dim=1).numpy()
                mn, mx = mse.min(), mse.max()
                self._feat_score = (1.0 - (mse - mn) / (mx - mn + 1e-9)).astype(np.float32)

            elif self.method == "occ" or (self.method == "combined" and not neg_idx):
                from sklearn.svm import OneClassSVM

                X_pos_s = self._scaler.fit_transform(X_pos)
                X_all_s = self._scaler.transform(X_all)
                self._ocsvm = OneClassSVM(kernel="rbf", nu=0.1, gamma="scale")
                self._ocsvm.fit(X_pos_s)
                dec = self._ocsvm.decision_function(X_all_s)
                mn, mx = dec.min(), dec.max()
                self._feat_score = ((dec - mn) / (mx - mn + 1e-9)).astype(np.float32)

            else:
                self._feat_score = np.zeros(self.N, dtype=np.float32)

        else:
            self._feat_score = np.zeros(self.N, dtype=np.float32)

        # Combined
        if self.method == "combined":
            if self._graph_score.max() > 0:
                self._combined_score = (
                    self.w_feat * self._feat_score + self.w_graph * self._graph_score
                ).astype(np.float32)
            else:
                # Graph unavailable: use feat_score only so scores span [0, 1]
                self._combined_score = self._feat_score.copy().astype(np.float32)
        elif self.method == "graph_ppr":
            self._combined_score = self._graph_score
        else:
            self._combined_score = self._feat_score

    def get_oof_labeled_scores(self) -> Dict[str, float]:
        """Return out-of-fold scores for labeled ASNs (for threshold tuning)."""
        return dict(self._oof_labeled_scores or {})

    def predict_proba(self, asns: Optional[List[str]] = None) -> np.ndarray:
        if self._combined_score is None:
            raise RuntimeError("Model not fitted. Call fit() first.")
        if asns is None:
            return self._combined_score.copy()
        idx = []
        for a in asns:
            try:
                k = int(_canonicalize_asn(a))
                if k in self.asn_to_idx:
                    idx.append(self.asn_to_idx[k])
                else:
                    idx.append(-1)
            except (ValueError, TypeError):
                idx.append(-1)
        out = np.zeros(len(asns), dtype=np.float32)
        for i, j in enumerate(idx):
            out[i] = self._combined_score[j] if j >= 0 else 0.0
        return out


SEMI_SUPERVISED_MODEL_REGISTRY = {"pun": PUNModel}
