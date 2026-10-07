# LACeS Anycast Census: License and Release Treatment

This document records the license, citation request, and public-release treatment for the LACeS Anycast Census.

The public snapshots do not reproduce the LACeS daily census files or any lists of detected anycast prefixes. They contain only monthly per-AS counts derived from the census results.

## Source and governing terms

- Dataset repository: [LACeS Anycast Census](https://github.com/ut-dacs/anycast-census)
- Archived release: [LACeS on Zenodo](https://doi.org/10.5281/zenodo.17174468)
- Repository license: [Mozilla Public License 2.0](https://github.com/ut-dacs/anycast-census/blob/main/LICENSE)
- Official license text: [Mozilla Public License 2.0](https://www.mozilla.org/MPL/2.0/)
- Methodology paper: [LACeS: An Open, Fast, Responsible and Efficient Longitudinal Anycast Census System](https://doi.org/10.1145/3730567.3764484)

The LACeS census files are distributed under MPL-2.0. Because the public snapshots do not redistribute those files or modified versions of them, the released aggregate features do not inherit MPL-2.0.

## Features included in the public snapshots

The snapshots include the following monthly per-AS features:

- `LACeS-anycast_v4_cnt`: monthly average sum of per-prefix IPv4 anycast-site estimates for the AS
- `LACeS-anycast_v6_cnt`: monthly average sum of per-prefix IPv6 anycast-site estimates for the AS

These values are monthly per-AS summaries derived from the daily census. The composite `Anycast` tag indicates whether either count is greater than zero.

## Public-snapshot treatment

The public snapshots contain only the monthly per-AS summaries above, not LACeS files, prefix lists, daily observations, or measurement records. The released values do not identify or permit reconstruction of the underlying records.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

## Attribution and publication requirements

The LACeS repository states:

> “When using this dataset for academic research, please cite the following paper.”

Publications using the LACeS-derived features should cite:

> Remi Hendriks, Matthew Luckie, Mattijs Jonker, Raffaele Sommese, and Roland van Rijswijk-Deij. “LACeS: An Open, Fast, Responsible and Efficient Longitudinal Anycast Census System.” *Proceedings of the 2025 ACM Internet Measurement Conference (IMC '25)*, pp. 445–461, 2025. <https://doi.org/10.1145/3730567.3764484>

