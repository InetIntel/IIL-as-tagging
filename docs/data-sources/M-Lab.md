# M-Lab NDT Data and License

This document records the source terms for Measurement Lab (M-Lab) Network Diagnostic Test data used by this repository.

The public snapshots do not include M-Lab test records, client IP addresses, or other row-level NDT data. They contain only monthly per-AS aggregates derived from the public NDT dataset.

## Source and governing terms

- Source: [M-Lab NDT](https://www.measurementlab.net/tests/ndt/)
- Data-policy statement: [M-Lab Frequently Asked Questions](https://www.measurementlab.net/frequently-asked-questions/)
- License: [Creative Commons CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/)

M-Lab describes all test data as released under CC0 1.0 and states:

> everyone is free to use M-Lab data for any purpose, without needing to seek prior permission from M-Lab.

The CC0 summary further states:

> You can copy, modify, distribute and perform the work, even for commercial purposes, all without asking permission.

CC0 does not impose attribution, non-commercial, or share-alike requirements. This project nevertheless identifies M-Lab as the source for provenance and reproducibility.

## Features included in the public snapshots

The snapshots include the following monthly per-AS features:

- `mlab-ndt_v4addr_cnt`: number of distinct IPv4 client addresses that initiated at least one NDT test during the month
- `mlab-ndt_v6addr_cnt`: number of distinct IPv6 client addresses that initiated at least one NDT test during the month
- `mlab-ndt_/24_cnt`: number of distinct IPv4 `/24` client subnets that initiated at least one NDT test during the month
- `mlab-ndt_/64_cnt`: number of distinct IPv6 `/64` client subnets that initiated at least one NDT test during the month

The counts combine deduplicated NDT5 and NDT7 observations.

## Public-snapshot treatment

M-Lab releases the source data under CC0, which permits copying, modification, and distribution for any purpose. The snapshots publish only monthly per-AS counts and identify M-Lab as the source, although attribution is not required by CC0.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

CC0 continues to govern the M-Lab source data and permits its reuse independently of this repository.

## Attribution and publication requirements

No separate M-Lab data-access agreement or publication-reporting requirement applies to redistribution of these derived features under CC0.

Attribution is not required by CC0, but the repository identifies M-Lab as the upstream source for provenance and reproducibility.
