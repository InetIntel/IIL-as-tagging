# Hypergiant Off-Net Inference: Provenance and Release Terms

This document records the provenance and release treatment of the Hypergiant off-net feature in this repository.

## Source and governing terms

The inference methodology is based on:

> P. Gigis et al., "Seven Years in the Life of Hypergiants' Off-Nets," ACM SIGCOMM 2021.  
> <https://doi.org/10.1145/3452296.3472928>

The [paper](https://doi.org/10.1145/3452296.3472928) is published under the [Creative Commons Attribution 4.0 International license](https://creativecommons.org/licenses/by/4.0/). The project cites the paper as the methodological reference but uses its own implementation and does not redistribute the authors' software or paper text.

## Features included in the public snapshots

The snapshots include one per-AS feature:

- `hg-offnet_v4addr_cnt`: number of inferred Hypergiant off-net IPv4 prefixes associated with the ASN

## Public-snapshot treatment

### Historical author-shared input

The authors of the SIGCOMM 2021 paper shared the historical `2023-04` ASN-to-prefix material directly with us for research use. It identified inferred Hypergiant off-net deployments.

The public snapshots contain only the per-AS count, not the shared ASN-to-prefix associations. The count does not identify or permit reconstruction of the listed prefixes.

### Project-generated releases

For newer releases, the project independently implements the paper's methodology. Only the final per-AS count is released; input records, inferred prefix lists, and intermediate artifacts are not distributed.

Historical author-shared material and newer project-generated results receive the same treatment: only the non-reconstructable per-AS count is released.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

## Attribution and publication requirements

Publications using this feature must comply with the repository-wide citation and publication-reporting requirements and should cite the SIGCOMM 2021 paper above as the methodological reference.
