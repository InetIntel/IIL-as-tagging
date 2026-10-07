# Local reconstruction scripts

The scripts in this directory reconstruct fields that are intentionally
omitted from the public AS feature snapshots because they depend on
separately obtained third-party data. Reconstructed outputs are for local use
and are written under `filled_data/` by default; they should not be committed
to the public repository (keep `filled_data/` in `.gitignore`).

## Installation

Python 3.10 or newer is required. Create a virtual environment and install the
script dependencies with the same Python interpreter that will run the
script:

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r scripts/requirements.txt
```

On Windows PowerShell:

```powershell
py -3 -m venv .venv
.venv\Scripts\python.exe -m pip install -r scripts\requirements.txt
```

Using `python -m pip` rather than a standalone `pip` command helps ensure the
dependency is installed into the environment that actually runs the script.

## CAIDA AS Relationship lists (`fill_caida_as_rel.py`)

`fill_caida_as_rel.py` locally adds these four list-valued columns to a public
AS feature snapshot:

- `caida-asrel_provider_list`
- `caida-asrel_customer_list`
- `caida-asrel_peer_list`
- `caida-asrel_cone_as_list`

The script accepts either a monthly `.tar.gz` package or an extracted
`.parquet` file. For a monthly package, it reads the exact CAIDA AS
Relationship snapshot date from `manifest.json`, downloads the corresponding
serial-2 relationship file and serial-1 customer-cone file, and writes a
locally reconstructed package under `filled_data/`.

Before accessing this dataset for the first time, review the CAIDA AS
Relationships Dataset page, follow its Data Access instructions, and review
the CAIDA Public-AUA:

- Dataset page: https://www.caida.org/catalog/datasets/as-relationships/
- Public-AUA: https://www.caida.org/about/legal/aua/public_aua/

The script displays the applicable notice and waits for acknowledgement before
reading supplied CAIDA data or downloading anything from CAIDA. Publications
using the dataset must follow CAIDA's citation and publication-reporting
requirements.

### Quick start

```bash
.venv/bin/python scripts/fill_caida_as_rel.py \
    --input data/IIL-as-feature-snapshot.2026-07.tar.gz
.venv/bin/python scripts/build_filled_data_index.py
```

On Windows PowerShell, use `.venv\Scripts\python.exe` in place of
`.venv/bin/python`.

By default, the two downloaded CAIDA files are placed in a temporary directory
and deleted when the run finishes. To deliberately retain and reuse them:

```bash
.venv/bin/python scripts/fill_caida_as_rel.py \
    --input data/IIL-as-feature-snapshot.2026-07.tar.gz \
    --cache-dir path/to/caida-cache
```

To use files already obtained from CAIDA instead of downloading them:

```bash
.venv/bin/python scripts/fill_caida_as_rel.py \
    --input path/to/IIL-as-feature-snapshot.2026-07.parquet \
    --date 20260701 \
    --as-rel2 path/to/20260701.as-rel2.txt.bz2 \
    --ppdc-ases path/to/20260701.ppdc-ases.txt.bz2
```

The script verifies, for every ASN, that each reconstructed list length equals
the corresponding aggregate count in the public snapshot. It aborts without
writing an output if the values disagree. The generated package records local
reconstruction provenance in `manifest.json` and in the Parquet metadata; it
does not include the CAIDA source files.

## Indexing filled packages (`build_filled_data_index.py`)

`OfflineSnapshotProvider` requires an `index.json` next to the packages it
loads -- without one it raises `FileNotFoundError` before reading anything, so
`filled_data/` needs its own index, separate from `data/index.json`.

**Run this script every time the contents of `filled_data/` change** -- after
filling a new month, re-filling one (e.g. with `--allow-count-mismatch`), or
removing a package. It does not patch the existing index incrementally; it
rescans `filled_data/` from scratch and writes a complete replacement, so it
can never drift out of sync with what is actually on disk:

```bash
python3 scripts/build_filled_data_index.py
```

This only reads each package's `manifest.json` and hashes the `.tar.gz` file
itself -- it needs no dependencies beyond the standard library, so it works
with a plain `python3`, not just the `.venv` used for `fill_caida_as_rel.py`.
Pass `--filled-dir` if you write filled packages somewhere other than
`filled_data/`.

`filled_data/` is expected to hold only whichever months you have chosen to
fill -- not a full mirror of `data/`. Point `OfflineSnapshotProvider` at
whichever directory matches what you want for a given month:

```python
from as_tagging import OfflineSnapshotProvider

public_provider = OfflineSnapshotProvider("data")          # no raw AS-relationship lists
filled_provider = OfflineSnapshotProvider("filled_data")   # only the months you've filled

filled_provider.list_snapshots()  # only months actually present under filled_data/
```

Use `public_provider` for a month you have not filled, or `filled_provider`
(after running `build_filled_data_index.py`) for a month whose raw lists you
need; there is no single provider that automatically falls back from one
directory to the other.
