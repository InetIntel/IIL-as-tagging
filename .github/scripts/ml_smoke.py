"""CI smoke test for the `[ml]` extra.

Exercises the two feature-only ML paths (XGBoost, MLP) end to end on small
synthetic data -- install, train/CV/select, and tag(). No real dataset and no
DGL. Exits non-zero on any failure.

    python .github/scripts/ml_smoke.py
"""
import random
import sys


def make_snapshot(n_pos=120, n_neg=120, n_bg=400, seed=0):
    rng = random.Random(seed)
    rirs = ["arin", "ripencc", "apnic", "lacnic", "afrinic"]
    ccs = ["US", "DE", "CN", "BR", "IN", "GB", "FR"]
    num_feats = [f"f_num_{i}" for i in range(15)]

    def row(high):
        d = {f: rng.gauss(8.0 if high else 1.0, 2.5) for f in num_feats}
        d["delegation_rir"] = rng.choice(rirs)
        d["delegation_cc"] = rng.choice(ccs)
        return d

    snap, pos, neg = {}, [], []
    aid = 1000
    for _ in range(n_pos):
        a = str(aid); aid += 1
        snap[a] = row(True); pos.append(a)
    for _ in range(n_neg):
        a = str(aid); aid += 1
        snap[a] = row(False); neg.append(a)
    for _ in range(n_bg):
        a = str(aid); aid += 1
        snap[a] = row(rng.random() < 0.5)

    features = num_feats + ["delegation_rir", "delegation_cc"]
    return snap, pos, neg, features


def main():
    import as_tagging
    from as_tagging.ml import MLTagger, SemiSupervisedMLTagger
    print("as_tagging:", as_tagging.__file__, flush=True)

    snap, pos, neg, features = make_snapshot()

    for models in (["xgboost"], ["mlp"]):
        print(f"--- MLTagger(models={models}) ---", flush=True)
        ml = MLTagger(snap, models=models, verbose=False,
                      features=features, share_specs=[])
        ml.train_and_select(pos, neg)
        preds = ml.tag(threshold=0.5)
        assert isinstance(preds, dict), f"tag() returned {type(preds)}"
        assert len(preds) == len(snap), f"{len(preds)} preds != {len(snap)} ASNs"
        npos = sum(1 for v in preds.values() if v)
        print(f"    OK: {len(preds)} ASNs, {npos} tagged positive", flush=True)

    print("--- SemiSupervisedMLTagger(model='pun') ---", flush=True)
    ss = SemiSupervisedMLTagger(snap, model="pun", verbose=False,
                                features=features, share_specs=[])
    ss.fit(pos, neg)
    preds = ss.tag(threshold=0.5)
    assert isinstance(preds, dict) and len(preds) == len(snap)
    print(f"    OK: {len(preds)} ASNs, "
          f"{sum(1 for v in preds.values() if v)} tagged positive", flush=True)

    print("ml smoke: PASS")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        import traceback
        traceback.print_exc()
        sys.exit(1)
