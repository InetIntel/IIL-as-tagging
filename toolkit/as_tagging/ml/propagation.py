"""
Label propagation utilities for semi-supervised ML models.

Provides PPR-style (Personalized PageRank) diffusion used by the PUN model
for graph-based score propagation.
"""


def propagate(P, X, alpha: float = 0.9, steps: int = 10):
    """
    Classical label propagation: X^{(t+1)} = (1 - alpha) * X0 + alpha * P @ X^{(t)}.

    Used for PPR-style diffusion from seed vectors (e.g., 1 on positive ASes).

    Args:
        P: Sparse propagation matrix (N, N), row-normalized. From build_propagation_matrix.
        X: Initial vector or matrix. If 1D, treated as (N,); if 2D, (N, K).
        alpha: Teleport/restart probability. Higher = more diffusion.
        steps: Number of power-iteration steps.

    Returns:
        Propagated vector/matrix, same shape as X.
    """
    import torch

    X0 = X
    if X.dim() == 1:
        X0 = X.unsqueeze(1)
    Xp = X0
    for _ in range(steps):
        Xp = (1 - alpha) * X0 + alpha * torch.sparse.mm(P, Xp)
    if X.dim() == 1:
        return Xp.squeeze(1)
    return Xp
