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
- Feature snapshots also mirrored on HuggingFace: [zchen798/as_feature_snapshot](https://huggingface.co/datasets/zchen798/as_feature_snapshot)

<!-- Zenodo DOI badge -- add once the archived release is minted:
[![DOI](https://zenodo.org/badge/<REPO_ID>.svg)](https://doi.org/<CONCEPT_DOI>) -->

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

The toolkit pulls snapshot data on demand from the HuggingFace mirror via
`OnlineSnapshotProvider` (see [Quick start](#quick-start)).

**The monthly feature snapshots themselves** (bulk / offline / archival use):

- Grab individual months from **Zenodo** (versioned, citable) or the **HuggingFace**
  mirror — recommended if you only need a few months.
- `git clone` this repo for the full set plus version history. Note this pulls **every
  historical month** (hundreds of MB, growing monthly), so prefer the mirrors unless you
  want the complete local archive.

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

From the HuggingFace mirror (no local data needed):

```python
from as_tagging import ASTagging, OnlineSnapshotProvider

provider = OnlineSnapshotProvider()          # zchen798/as_feature_snapshot
tagger = ASTagging(snapshot_provider=provider, date="2024-08")
```

Or from a local copy of `data/` (e.g. a clone of this repo, or files pulled from Zenodo):

```python
from as_tagging import ASTagging, OfflineSnapshotProvider

provider = OfflineSnapshotProvider("/path/to/as-tagging/data")
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
│   └── requirements.txt
├── data/
│   ├── index.json          # release index (months, sizes, checksums, source dates)
│   ├── README.md           # full feature catalog + methodology
│   ├── LICENSE             # Georgia Tech Acceptable Use Agreement (data)
│   └── IIL-as-feature-snapshot.YYYY-MM.tar.gz
├── pyproject.toml
├── CITATION.cff
└── LICENSE                 # MIT (toolkit code)
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

<!-- TODO: once the Zenodo archived release is minted, add the software citation
here (concept DOI = all versions; version DOI for a specific release). -->


---

## License

- **Toolkit code** (`toolkit/`, and the `as-tagging` PyPI package): MIT — see [`LICENSE`](LICENSE).
- **AS feature snapshot data** (`data/`): distributed under Georgia Tech's Acceptable Use
  Agreement — see [`data/LICENSE`](data/LICENSE). Any access and use of the data is subject
  to that agreement.

The code license (MIT) is separate from and does not apply to the data.
