# CAIDA Data Sources and Acceptable-Use Terms

This document records the agreement terms and public-release treatment for CAIDA-hosted data used by this repository. CAIDA source data remains subject to CAIDA's agreement and is not relicensed by this project.

The public snapshots do not bundle or republish CAIDA source files. They contain aggregate, derived features that are not designed to reconstruct the underlying records. Four list-valued AS-relationship features are omitted from the public snapshots and can be added locally, at the user's option, using separately obtained CAIDA data.

## Source and governing terms

The CAIDA-hosted sources used here are:

- [RouteViews Prefix-to-AS mappings](https://www.caida.org/catalog/datasets/routeviews-prefix2as/)
- [CAIDA AS Relationships](https://www.caida.org/catalog/datasets/as-relationships/)
- [Macroscopic Internet Topology Data Kit (ITDK)](https://www.caida.org/catalog/datasets/internet-topology-data-kit/), using only releases that were already more than one year old when incorporated into a public snapshot
- [CAIDA UCSD PeeringDB archive](https://www.caida.org/catalog/datasets/peeringdb/)

These uses are governed by the [CAIDA Public Dataset Acceptable Use Agreement (Public-AUA)](https://www.caida.org/about/legal/aua/public_aua/). Its grant states:

> CAIDA's authorization to access the data grants You a limited, non-exclusive, non-transferable, non-assignable, and terminable license to copy, modify, and use the data in accordance with this Public Agreement.

The Public-AUA also requires users to acknowledge the relevant CAIDA dataset in publications and to report publications—including papers, presentations, websites, and similar public outputs—to CAIDA. Users of this repository remain responsible for reviewing and complying with the current Public-AUA and the instructions on each dataset's access page.

## Features included in the public snapshots

### RouteViews Prefix-to-AS mappings

The snapshots include these per-AS monthly averages, calculated over the available daily Prefix-to-AS mappings in the month:

- `pfx2as_/24_cnt`: monthly average originated IPv4 address space, expressed in equivalent `/24` units
- `pfx2as_/64_cnt`: monthly average originated IPv6 address space, expressed in equivalent `/64` units

These are aggregate address-space-size statistics; the underlying prefix-to-AS mappings are not included.

### CAIDA AS Relationships

The public snapshots include the following aggregate per-AS features:

- `caida-asrel_provider_cnt`
- `caida-asrel_customer_cnt`
- `caida-asrel_peer_cnt`
- `caida-asrel_cone_/24_cnt`
- `caida-asrel_cone_/64_cnt`
- `caida-asrel_cone_as_cnt`

The following list-valued features are not included in the public snapshots:

- `caida-asrel_provider_list`
- `caida-asrel_customer_list`
- `caida-asrel_peer_list`
- `caida-asrel_cone_as_list`

Users may optionally add these fields with [`scripts/fill_caida_as_rel.py`](../../scripts/fill_caida_as_rel.py) (see [`scripts/README.md`](../../scripts/README.md)) after obtaining the data directly from CAIDA and agreeing to and complying with the Public-AUA.

### Macroscopic Internet Topology Data Kit (ITDK)

CAIDA makes ITDK releases more than one year old available under the Public-AUA. Public snapshots use only releases that are already more than one year old when the artifact is published; for example, release `202508` was more than one year old by September 2026.

The public snapshots include the following per-AS features derived from an eligible ITDK release:

- `caida-itdk_router_cnt`, `caida-itdk_topfrac`, `caida-itdk_cc_cnt`, `caida-itdk_gini`, `caida-itdk_topcc`: compatibility names for the IPv4 summaries
- `caida-itdk_router_cnt_v4`: number of IPv4 routers
- `caida-itdk_topfrac_v4`: fraction of IPv4 routers in the most common geolocated country
- `caida-itdk_cc_cnt_v4`: number of countries in which IPv4 routers are geolocated
- `caida-itdk_gini_v4`: Gini coefficient of the IPv4 router geolocation distribution; larger values indicate a more uneven distribution
- `caida-itdk_topcc_v4`: country code containing the largest number of geolocated IPv4 routers
- `caida-itdk_router_cnt_v6`: number of IPv6 routers
- `caida-itdk_topfrac_v6`: fraction of IPv6 routers in the most common geolocated country
- `caida-itdk_cc_cnt_v6`: number of countries in which IPv6 routers are geolocated
- `caida-itdk_gini_v6`: Gini coefficient of the IPv6 router geolocation distribution; larger values indicate a more uneven distribution
- `caida-itdk_topcc_v6`: country code containing the largest number of geolocated IPv6 routers

These are aggregate per-AS router and country statistics; the public snapshots do not include ITDK router-level source records.

### CAIDA UCSD PeeringDB archive

The project uses historical PeeringDB snapshots from CAIDA's [PeeringDB dataset page](https://www.caida.org/catalog/datasets/peeringdb/) and [data archive](https://data.caida.org/datasets/peeringdb-v2/). The public feature snapshot includes only:

- `pdb_ix_cnt`: the number of peered IXPs associated with an AS in the selected monthly source snapshot

This is an aggregate count; the underlying PeeringDB records are not included.

## Public-snapshot treatment

CAIDA source files are not included. The snapshots contain aggregate, non-reconstructable features; the four AS-relationship lists are omitted and may be added locally only from data obtained directly from CAIDA. ITDK uses only releases older than one year at publication. Publications must cite the relevant datasets and be reported to CAIDA as required by the Public-AUA.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

## Attribution and publication requirements

The Public-AUA requires acknowledgment of the relevant CAIDA datasets and reporting of publications to CAIDA. The requested dataset citations are:

> Routeviews Prefix to AS mappings Dataset for IPv4 and IPv6  
> <https://www.caida.org/catalog/datasets/routeviews-prefix2as/>

> The CAIDA AS Relationships Dataset, `<date range used>`  
> <https://www.caida.org/catalog/datasets/as-relationships/>

> The CAIDA Macroscopic Internet Topology Data Kit - `<release date(s)>`  
> <https://www.caida.org/catalog/datasets/internet-topology-data-kit/>

> The CAIDA UCSD PeeringDB Dataset, `<date range used>`  
> <https://www.caida.org/catalog/datasets/peeringdb/>
