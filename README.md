# AS Tagging Toolkit

AS Tagging provides monthly *AS feature snapshots* and a scientific toolkit for **defining, assigning, and retrieving tags that describe the network properties of Autonomous Systems (ASes)**.

This repository contains:

| Path        | What                                                                                     |
|-------------|------------------------------------------------------------------------------------------|
| `toolkit/`  | The `as_tagging` Python package (also on PyPI), example notebooks                        |
| `data/`     | Monthly AS feature-snapshot packages + `index.json`; each package includes its own schema metadata        |
| `tags/`     | Monthly Appendix J per-ASN AS tags (`as2tags`), already computed from `data/`, + `index.json` |

The Georgia Tech Acceptable Use Agreement in [`LICENSE`](LICENSE) applies to the
entire repository, including its software, documentation, and data.

These resources are artifacts of the paper *Rethinking and Facilitating How We Classify Autonomous
Systems by Network Properties* (IMC '26).

- Paper (ACM DL): https://doi.org/10.1145/3777912.3839831
- DOI reference (Zenodo): https://doi.org/10.5281/zenodo.22232206
- Feature snapshots also mirrored on HuggingFace: [zchen798/as_feature_snapshot](https://huggingface.co/datasets/zchen798/as_feature_snapshot)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22232206.svg)](https://doi.org/10.5281/zenodo.22232206)

Please open an issue to report bugs, request features, or flag dataset inaccuracies
(include ASN, month, and feature name).

---

## Getting started

### Install the toolkit

Install the core package from PyPI. You can load snapshots online without cloning this repository:

```bash
pip install as-tagging
```

### Load a snapshot

From the HuggingFace mirror, which downloads one month at a time (no clone needed):

```python
from as_tagging import ASTagging, OnlineSnapshotProvider

provider = OnlineSnapshotProvider()          # zchen798/as_feature_snapshot
tagger = ASTagging(snapshot_provider=provider, date="2024-08")
```

Or from a local clone of this repository:

```python
from as_tagging import ASTagging, OfflineSnapshotProvider

provider = OfflineSnapshotProvider("/path/to/IIL-as-tagging/data")
tagger = ASTagging(snapshot_provider=provider, date="2024-08")
```

### Query and inspect tags

```python
tagger.list_tags(asn="12345")
tagger.help(tag_name="Domestic")
tagger.fetch_tag(tag_name="Domestic", asns=["12345", "67890"])
```

### Define a custom composite tag

```python
tagger.assign_tag(
    tag_name="Has IPv6 and Anycast",
    expression=lambda tags: bool(tags.get("IPv6 Only")) and bool(tags.get("Anycast")),
)
```

---

## Optional setup

Use these steps if you need ML models, want to modify the toolkit, or plan to run the notebooks in a dedicated virtual environment.

### ML dependencies

If you need ML tagging, install one of these variants:

```bash
pip install "as-tagging[ml]"         # XGBoost / MLP / semi-supervised (PUN) tagging
pip install "as-tagging[ml-graph]"   # also includes graph models (GraphConv / APPNP), needs DGL
```

> `[ml]` works on Python 3.11–3.13. `[ml-graph]` adds DGL, which currently has no
> wheels for Python ≥ 3.13 and is unmaintained — the graph models are skipped
> gracefully at runtime if DGL is absent. The graph models also need the AS topology
> from the CAIDA AS-relationship lists, which the published snapshots omit (see
> [Fields omitted from the public snapshots](#fields-omitted-from-the-public-snapshots));
> on the published `data/` they are skipped unless you add the lists locally with
> `scripts/fill_caida_as_rel.py`. The semi-supervised `graph_ppr` / `combined` PUN
> scores likewise need them. On macOS, XGBoost also needs the OpenMP
> runtime (`brew install libomp`). Current XGBoost and PyTorch releases may still
> conflict when trained in the same process, even with
> `KMP_DUPLICATE_LIB_OK=TRUE`; run one model family per Jupyter kernel, or use
> Python 3.11 with PyTorch 2.3 for combined comparisons. Linux / CI are unaffected.

### Install from source for development

```bash
git clone https://github.com/InetIntel/IIL-as-tagging.git
cd IIL-as-tagging

python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel

pip install -e .                  # toolkit in editable mode
```

For an editable install with optional models, use `pip install -e ".[ml]"` or
`pip install -e ".[ml-graph]"` in place of `pip install -e .`.

### Jupyter kernel

To run the example notebooks in the virtual environment, register it as a Jupyter kernel:

```bash
source .venv/bin/activate
python -m pip install -U ipykernel
python -m ipykernel install --user --name as-tagging-venv --display-name "Python (as-tagging-venv)"
```

Then select `Python (as-tagging-venv)` as the notebook kernel (reload the window if it
does not appear).

---

## Example notebooks

Under `toolkit/notebooks/`:

- `manual_tagging_example.ipynb` — manual tag definition workflows
- `ml_tagging_example.ipynb` — supervised ML tagging
- `semi_supervised_ml_tagging_example.ipynb` — semi-supervised (PUN) ML tagging
- `ml_feature_importance.ipynb`, `ml_classification_stability.ipynb` — ML analyses
  that require the `residential_isp_v2` model produced by `ml_tagging_example.ipynb`

---

## The AS feature snapshots (`data/`)

The snapshots are published in this repository, mirrored on HuggingFace, and cited through Zenodo:

- **This repo is the canonical source.** `git clone` it and every released month is under
  `data/` as `IIL-as-feature-snapshot.<YYYY-MM>.tar.gz`; new months are committed here.
  A full clone pulls every historical month (hundreds of MB, growing monthly).
- Only need a few months? Download individual `data/*.tar.gz` straight from GitHub, or
  download the corresponding `archives/IIL-as-feature-snapshot.<YYYY-MM>.tar.gz` from the
  **HuggingFace mirror** ([zchen798/as_feature_snapshot](https://huggingface.co/datasets/zchen798/as_feature_snapshot)),
  which is what `OnlineSnapshotProvider` uses.
- **Zenodo** provides the DOI reference for this dataset; it is not the day-to-day data
  source.

Each month is packaged as `IIL-as-feature-snapshot.YYYY-MM.tar.gz`, containing (under a
`YYYY-MM/` folder):

- `IIL-as-feature-snapshot.YYYY-MM.parquet` — the feature table (one row per ASN, Snappy-compressed)
- `manifest.json` — per-source input dates, provenance, row count
- `schema.json` / `schema.md` — column definitions
- `data_sources.txt` — raw source listing

A global `data/index.json` lists every released month with its size, SHA-256 checksum,
and per-source input dates. The feature set is **schema v1**; it has grown over time as
sources were added — see the `schema.*` inside each package for that month's authoritative
column list.

**Full feature catalog and monthly aggregation strategy:** see [`data/README.md`](data/README.md).

Data sources include RIR delegation, APNIC Eyeball, MaxMind GeoLite2, Censys Universal
Internet, OpenIntel Tranco, CAIDA AS Relationship / ITDK, RouteViews Prefix2AS, ISI ANT
Census, Merit Telescope, M-Lab NDT, IIJ AS Hegemony / Traceroute Hegemony, IIL-AS2Org,
PeeringDB, LACeS Anycast Census, and hypergiant off-net estimates.

### Fields omitted from the public snapshots

The list-valued fields below are omitted from the published snapshots. If you
need them, you can add them locally with the corresponding script in
[`scripts/`](scripts/), using data obtained directly from the upstream provider
under that provider's terms.

Currently omitted:

- **CAIDA AS Relationships** — terms: CAIDA Public-AUA
  ([details](docs/data-sources/CAIDA.md)); fill with
  [`scripts/fill_caida_as_rel.py`](scripts/fill_caida_as_rel.py)
  - `caida-asrel_provider_list`
  - `caida-asrel_customer_list`
  - `caida-asrel_peer_list`
  - `caida-asrel_cone_as_list`

For example, to add the CAIDA AS Relationships lists to one month and load the
result with the toolkit:

```bash
python3 scripts/fill_caida_as_rel.py --input data/IIL-as-feature-snapshot.YYYY-MM.tar.gz
python3 scripts/build_filled_data_index.py
```

```python
from as_tagging import ASTagging, OfflineSnapshotProvider

provider = OfflineSnapshotProvider("/path/to/IIL-as-tagging/filled_data")
tagger = ASTagging(snapshot_provider=provider, date="YYYY-MM")
```

Locally filled packages are written to `filled_data/`, which is git-ignored and
must not be redistributed as part of this repository. See
[`scripts/README.md`](scripts/README.md) for options and details, and
[`docs/data-sources/`](docs/data-sources/) for the terms of each upstream source.


---

## The AS tags (`tags/`)

We publish the per-ASN tag catalog defined in Appendix J of our paper in
`tags/`, one release per month (`as2tags.YYYY-MM.json.gz`), already computed
from the corresponding `data/` snapshot. `tags/index.json` lists every released
month.

**Full tag catalog, value semantics, file format, and methodology:** see
[`tags/README.md`](tags/README.md).

---

## Data sources and attribution

Source-specific terms, attribution requirements, and public-release treatment for the
upstream data sources are documented in [`docs/data-sources/`](docs/data-sources/).

---

## Repository layout

```
IIL-as-tagging/
├── toolkit/
│   ├── as_tagging/         # the installable package
│   ├── notebooks/          # example + analysis notebooks
│   └── requirements.txt
├── data/
│   ├── index.json          # release index (months, sizes, checksums, source dates)
│   ├── README.md           # full feature catalog + methodology
│   └── IIL-as-feature-snapshot.YYYY-MM.tar.gz
├── tags/
│   ├── index.json          # release index (months, checksums, tag catalog)
│   ├── README.md           # full tag catalog, value semantics, and methodology
│   └── as2tags.YYYY-MM.json.gz
├── scripts/                # local reconstruction of omitted third-party fields
├── docs/
│   └── data-sources/       # upstream terms and public-release treatment, per source
├── filled_data/            # (git-ignored) locally reconstructed snapshots
├── pyproject.toml
├── CITATION.cff
└── LICENSE                 # repository-wide Georgia Tech Acceptable Use Agreement
```

---

## Citation

If you use this toolkit or the feature snapshots, please cite the paper:

```bibtex
@inproceedings{chen2026rethinking,
  title        = {Rethinking and Facilitating How We Classify Autonomous Systems by Network Properties},
  author       = {Chen, Zhiyi and Bischof, Zachary and Testart, Cecilia and Dainotti, Alberto},
  booktitle    = {Proceedings of the 2026 ACM Internet Measurement Conference (IMC '26)},
  year         = {2026},
  address      = {Karlsruhe, Germany},
  publisher    = {ACM},
  isbn         = {979-8-4007-2327-8/2026/10},
  doi          = {10.1145/3777912.3839831},
  url          = {https://doi.org/10.1145/3777912.3839831},
}
```

And the DOI reference for the dataset on Zenodo (concept DOI):

```bibtex
@software{chen_iil_as_tagging,
  author    = {Chen, Zhiyi and Bischof, Zachary and Testart, Cecilia and Dainotti, Alberto},
  title     = {IIL-AS-Tagging Dataset},
  publisher = {Internet Intelligence Lab at Georgia Tech},
  doi       = {10.5281/zenodo.22232206},
  url       = {https://doi.org/10.5281/zenodo.22232206}
}
```

---

## License

The entire IIL-AS-Tagging repository—including the `as-tagging` toolkit and Python
package, documentation, notebooks, and AS feature snapshot data—is distributed under
Georgia Tech's Acceptable Use Agreement. See [`LICENSE`](LICENSE). Any access and use
of these materials is subject to that agreement.
