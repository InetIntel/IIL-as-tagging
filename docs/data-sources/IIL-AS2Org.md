# IIL-AS2Org Data and Acceptable-Use Terms

This document records the terms and publication requirements for IIL-AS2Org features used by this repository.

IIL-AS2Org and IIL-AS-Tagging are both published by the Internet Intelligence Lab at Georgia Tech. The feature snapshots include only IIL-AS2Org's inferred sibling-AS results; they do not republish the WHOIS, PeeringDB, or other source records used by the AS2Org methodology.

## Source and governing terms

- Source: [IIL-AS2Org repository](https://github.com/InetIntel/Dataset-AS-to-Organization-Mapping)
- License: [Georgia Tech Acceptable Use Agreement for IIL-AS2Org](https://github.com/InetIntel/Dataset-AS-to-Organization-Mapping/blob/master/LICENSE)

The IIL-AS2Org license grants:

> a limited, non-exclusive, non-transferable, non-assignable, and terminable license to copy, modify, and use the data in accordance with this Public Agreement.

The agreement also requires publications—including web pages, third-party papers, and publicly available presentations—that use IIL-AS2Org data to:

1. cite the IIL-AS2Org dataset; and
2. report the publication to the Internet Intelligence Lab at `inetintel@cc.gatech.edu`, with a copy of or link to the publication.

## Features included in the public snapshots

The snapshots include the following per-AS features:

- `inetintel-as2org_sibling_cnt`: number of other ASes inferred to belong to the same organization, excluding the focal ASN
- `inetintel-as2org_sibling_list`: list of those other ASNs, excluding the focal ASN

The list-valued field is an inference produced by IIL-AS2Org. It is not a copy of an upstream WHOIS, PeeringDB, or CAIDA source field.

## Public-snapshot treatment

IIL-AS2Org and IIL-AS-Tagging are published by the same Georgia Tech research group under compatible acceptable-use terms. The released fields contain IIL-AS2Org's inferred sibling-AS outputs, not the third-party records used as methodological inputs.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

## Attribution and publication requirements

The IIL-AS2Org agreement requires publications to cite both the associated paper and the dataset:

> Z. Chen, Z. Bischof, C. Testart, A. Dainotti, “Improving the Inference of Sibling Autonomous Systems,” *Passive and Active Measurement (PAM)*, 2023. <https://doi.org/10.1007/978-3-031-28486-1_15>

> Z. Chen, Z. Bischof, C. Testart, A. Dainotti, “AS to Organization Mapping (IIL-AS2Org) dataset,” Internet Intelligence Lab at Georgia Tech, `<version or dates used>`. <https://doi.org/10.5281/zenodo.18340700>; <https://github.com/InetIntel/Dataset-AS-to-Organization-Mapping>

The publication must also be reported to `inetintel@cc.gatech.edu` as required by the IIL-AS2Org agreement. These source-specific requirements apply in addition to the citation and reporting requirements in the repository-wide IIL-AS-Tagging agreement.
