# AS tags (as2tags)

Monthly **per-ASN tag values** for every ASN in the corresponding month's AS
feature snapshot.

These tag values are published with the **[AS Tagging Toolkit](https://github.com/InetIntel/IIL-as-tagging)**
(`pip install as-tagging`). The tag catalog is defined in **Appendix J** of the
paper *Rethinking and Facilitating How We Classify Autonomous Systems by Network
Properties* (ACM IMC 2026): 12 predefined composite tags, `Residential Access`,
and `Mobile/Cellular`.

- **Canonical source:** the GitHub repo [InetIntel/IIL-as-tagging](https://github.com/InetIntel/IIL-as-tagging)
  — `tags/` holds every released month; new months are committed here.
- **Upstream:** each month is derived from that same month's
  `data/IIL-as-feature-snapshot.<YYYY-MM>.tar.gz` — see [`../data/README.md`](../data/README.md).

## How to use

```python
import gzip, json

with gzip.open("tags/as2tags.2026-07.json.gz", "rt", encoding="utf-8") as f:
    doc = json.load(f)

tags = doc["as2tags"]                       # {asn: {tag: value}}
tags["7018"]["Residential Access"]          # -> True
tags["2516"]["Mobile/Cellular"]             # -> True
tags["3356"]["Mobile/Cellular"]             # -> None (not labeled positive)
tags["7018"]["Any Presence"]                # -> ["US", ...]
```

`tags/index.json` lists every released month with its size, SHA-256, ASN count, and
per-tag counts (`tag_counts`), read from each file's own `metadata`.

## The 12 predefined composite tags

| Tag | Output type |
| --- | --- |
| Anycast, Tranco 10k Host, IPv6 Only, No Eyeball, No Transit, Sibling Transit, Public Transit | `true` / `false` |
| Country Code | `"US"` / `null` (RIR delegation country) |
| Any Presence, Domestic, Major Access | sorted `list[str]` of country codes (may be `[]`) |
| Global Transit Nth-ranked | `int` / `null` (sparse — ~130 ASNs/month) |

Defined in Appendix J of the paper. For these 12 predefined tags, every ASN
carries every tag key. A `null` value on a Boolean or list tag would mean the
toolkit could not compute it that month; this does not occur in current releases.
`Mobile/Cellular` uses `null` differently, as explained below.

## The `Residential Access` tag

`true` / `false` per ASN — the paper's supervised residential-access classifier
(XGBoost, trained on an RIR-stratified sample of ASes labeled via the paper's
sampling and reference-labeling strategy), applied monthly and stabilised with
hysteresis so the label does not flap month to month on borderline ASes.

- **Retraining methodology:** if the model is retrained, it will be done in
  step with refreshes of the
  [AS2Biz](https://github.com/InetIntel/Dataset-AS2Biz) business-classification
  dataset that supplies new reference labels, using the paper's sampling,
  training, and reference-labeling strategy.
- **Before 2026-01:** AS2Biz-derived reference labels do not exist retroactively, so
  months before 2026-01 are not independently retrained. They instead reuse the
  **2026-01 model** and apply the same hysteresis method backward in time, anchored
  at 2026-01's raw (threshold-0.5) label.
- **Scope:** the classifier is only valid among eyeball ASes
  (`apnic-eyeball_eyeball_cnt > 0`); non-eyeball ASNs always publish `false`.
- **Hysteresis:** `raw = P(residential) >= 0.5`. Given the previous month's
  published label, an ASN stays residential while `p >= 0.3` and becomes
  residential only when `p > 0.7` — `[0.3, 0.7]` preserves the prior state. An ASN
  returning from non-eyeball (or newly observed) re-initialises at `raw` rather than
  inheriting a stale label.
- Each month's `metadata.residential_access` records the model identity
  (`model_sha256`, `model_snapshot`), the thresholds, whether that month is the
  hysteresis chain anchor, and `degraded_features` — model input columns not yet
  present in that month's feature snapshot (the Merit-telescope feature
  `merit_/24_cnt` is absent before 2026-01; measured effect is ~1-2% of eyeball
  labels, well within normal month-to-month churn).

## The `Mobile/Cellular` tag

`true` / `null` per ASN. For the current release, the
`Mobile/Cellular` tag uses a frozen set of 124 positive ASNs from the paper's
semi-supervised PUN mobile/cellular experiment:

- ASNs in the frozen positive set publish `true` in every monthly snapshot in
  which they appear.
- Every other ASN publishes `null`, meaning **not labeled positive**. A `null`
  value must not be interpreted as a confirmed non-mobile label; the seed
  negative examples used by the experiment are also published as `null`.
- This initial version is static: it is not retrained or re-inferred separately
  for each month. All 124 positive ASNs occur in every currently published month
  (2024-08 through 2026-07).

The frozen artifact identity is:

- `label_version`: `pun_v1_frozen_25seed_plus_audited_top99`
- source feature snapshot: `2026-01`
- SHA-256: `ad410b07a6f106a085c2ac100cc2a03f6b920f61a0292a92eb8168459e7d0770`

Each month's `metadata.mobile_cellular` records this identity, the frozen-set
size (`n_frozen_positive_asns`), the number present that month
(`n_positive_asns_present`), and the published-value policy.

## File format

One gzipped JSON per month, `as2tags.<YYYY-MM>.json.gz`:

```json
{
  "metadata": {
    "month": "2026-07",
    "as_tagging_version": "2.0.0",
    "source_feature_snapshot": {"month": "2026-07", "sha256": "...", "package": "..."},
    "tags": ["Anycast", "...", "Residential Access", "Mobile/Cellular"],
    "n_asns": 121666,
    "tag_counts": {"Anycast": 12345, "...": 0, "Residential Access": 24723, "Mobile/Cellular": 124},
    "residential_access": {
      "model_sha256": "5708bcdb...", "model_snapshot": "2026-01",
      "raw_threshold": 0.5, "t_up": 0.7, "t_down": 0.3,
      "is_chain_anchor": false, "prev_month_file": "as2tags.2026-06.json.gz",
      "degraded_features": [],
      "n_eyeball": 40275, "n_raw_positive": 24559, "n_state_reset": 1052
    },
    "mobile_cellular": {
      "label_version": "pun_v1_frozen_25seed_plus_audited_top99",
      "labels_sha256": "ad410b07...", "source_feature_snapshot": "2026-01",
      "n_frozen_positive_asns": 124, "n_positive_asns_present": 124,
      "policy": "frozen positive set is true; every other ASN is null"
    }
  },
  "as2tags": {
    "3356": {"Anycast": true, "Country Code": "US", "Any Presence": ["NL", "US"], "Global Transit Nth-ranked": 1, "Residential Access": false, "Mobile/Cellular": null, ...},
    ...
  }
}
```

Consumer: `json.load(gzip.open(path))["as2tags"]`.

## License

The tags data, like the toolkit code and the rest of the IIL-AS-Tagging repository,
is distributed under Georgia Tech's Acceptable Use Agreement. See the
repository-wide [`LICENSE`](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).
