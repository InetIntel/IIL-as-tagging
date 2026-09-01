# AS Tagging Toolkit

An open, flexible, and extensible toolkit to **assign, retrieve, and customize tags
for Autonomous Systems (ASes)** from monthly *AS feature snapshots* — per-ASN feature
tables aggregating signals from routing, DNS, scanning, geolocation, topology, and
organization-mapping data sources.

This repository contains **both**:

| Path        | What                                                                                     | License |
|-------------|------------------------------------------------------------------------------------------|---------|
| `toolkit/`  | The `as_tagging` Python package (also on PyPI), example notebooks                        | MIT     |
| `data/`     | The monthly AS feature-snapshot packages (`IIL-as-feature-snapshot.YYYY-MM.tar.gz`) + `index.json` / schema | Georgia Tech AUA |

Both are artifacts of the paper *Rethinking and Facilitating How We Classify Autonomous
Systems by Network Properties* (IMC '26).

- Paper (ACM DL): https://doi.org/10.1145/3777912.3839831
- Archived release (Zenodo): https://doi.org/10.5281/zenodo.22232206
- Feature snapshots also mirrored on HuggingFace: [zchen798/as_feature_snapshot](https://huggingface.co/datasets/zchen798/as_feature_snapshot)

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.22232206.svg)](https://doi.org/10.5281/zenodo.22232206)

Please open an issue to report bugs, request features, or flag dataset inaccuracies
(include ASN, month, and feature name).

---

## Which do you need?

**Just the toolkit** (assign/retrieve tags, run your own analyses) — you do **not** need
to clone this repo or download the snapshot packages:

```bash
pip install as-tagging          # core
pip install "as-tagging[ml]"    # + supervised / semi-supervised ML tagging
```

The toolkit reads snapshots on demand from the **HuggingFace mirror** via
`OnlineSnapshotProvider` (one month at a time), or from a local clone of this repo via
`OfflineSnapshotProvider` (see [Quick start](#quick-start)).

**The monthly feature snapshots themselves:**

- **This repo is the canonical source.** `git clone` it and every released month is under
  `data/` as `IIL-as-feature-snapshot.<YYYY-MM>.tar.gz`; new months are committed here.
  A full clone pulls every historical month (hundreds of MB, growing monthly).
- Only need a few months? Download individual `data/*.tar.gz` straight from GitHub, or use
  the **HuggingFace mirror** ([zchen798/as_feature_snapshot](https://huggingface.co/datasets/zchen798/as_feature_snapshot)),
  which supports per-file download and is what `OnlineSnapshotProvider` uses.
- **Zenodo** holds a frozen, citable copy of a tagged release for archival and citation —
  not the day-to-day data source.

---

## Installation (from source, for development)

```bash
git clone https://github.com/InetIntel/IIL-as-tagging.git
cd IIL-as-tagging

python -m venv .venv
source .venv/bin/activate
pip install -U pip setuptools wheel

pip install -e .            # toolkit in editable mode
pip install -e ".[ml]"      # + ML extras
```

### Jupyter kernel for the venv

```bash
source .venv/bin/activate
python -m pip install -U ipykernel
python -m ipykernel install --user --name as-tagging-venv --display-name "Python (as-tagging-venv)"
```

Then select `Python (as-tagging-venv)` as the notebook kernel (reload the window if it
does not appear).

---

## Quick start

### 1) Load snapshot data

From a local clone of this repo (the canonical source — `data/` holds every month):

```python
from as_tagging import ASTagging, OfflineSnapshotProvider

provider = OfflineSnapshotProvider("/path/to/IIL-as-tagging/data")
tagger = ASTagging(snapshot_provider=provider, date="2024-08")
```

Or from the HuggingFace mirror, which downloads one month at a time (no clone needed):

```python
from as_tagging import ASTagging, OnlineSnapshotProvider

provider = OnlineSnapshotProvider()          # zchen798/as_feature_snapshot
tagger = ASTagging(snapshot_provider=provider, date="2024-08")
```

### 2) Query and inspect tags

```python
tagger.list_tags(asn="12345")
tagger.help(tag_name="Domestic")
tagger.fetch_tag(tag_name="Domestic", asns=["12345", "67890"])
```

### 3) Define a custom composite tag

```python
tagger.assign_tag(
    tag_name="Has IPv6 and Anycast",
    expression=lambda tags: bool(tags.get("IPv6 Only")) and bool(tags.get("Anycast")),
)
```

### Example notebooks

Under `toolkit/notebooks/`:

- `manual_tagging_example.ipynb` — manual tag definition workflows
- `ml_tagging_example.ipynb` — supervised ML tagging
- `semi_supervised_ml_tagging_example.ipynb` — semi-supervised (PUN) ML tagging
- `ml_feature_importance.ipynb`, `ml_classification_stability.ipynb` — ML analyses

---

## The AS feature snapshots (`data/`)

The `data/` directory in this repo is the canonical, continuously-updated home of the
snapshots — each new month is committed here. The HuggingFace mirror tracks it; Zenodo
gets a frozen copy per tagged release.

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

---

## Repository layout

```
IIL-as-tagging/
├── toolkit/
│   ├── as_tagging/         # the installable package
│   ├── notebooks/          # example + analysis notebooks
│   ├── requirements.txt
│   └── LICENSE             # MIT (toolkit code)
├── data/
│   ├── index.json          # release index (months, sizes, checksums, source dates)
│   ├── README.md           # full feature catalog + methodology
│   ├── LICENSE             # Georgia Tech Acceptable Use Agreement (data)
│   └── IIL-as-feature-snapshot.YYYY-MM.tar.gz
├── pyproject.toml
├── CITATION.cff
└── LICENSE                 # copy of toolkit/LICENSE (MIT), for GitHub/PyPI detection
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

And the archived release (Zenodo **concept DOI**, all versions). For a specific
snapshot/release, cite the corresponding Zenodo *version DOI*:

```bibtex
@software{chen_as_tagging,
  author    = {Chen, Zhiyi and Bischof, Zachary and Testart, Cecilia and Dainotti, Alberto},
  title     = {AS Tagging Toolkit (with monthly AS feature snapshots)},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.22232206},
  url       = {https://doi.org/10.5281/zenodo.22232206},
  note      = {Concept DOI (all versions). For a specific snapshot/release, please cite the corresponding Zenodo *version DOI*.},
}
```

---

## License

- **Toolkit code** (`toolkit/`, and the `as-tagging` PyPI package): MIT — see
  [`toolkit/LICENSE`](toolkit/LICENSE) (mirrored at the repo root as [`LICENSE`](LICENSE)).
- **AS feature snapshot data** (`data/`): distributed under Georgia Tech's Acceptable Use
  Agreement — see [`data/LICENSE`](data/LICENSE). Any access and use of the data is subject
  to that agreement.

The code license (MIT) is separate from and does not apply to the data.
