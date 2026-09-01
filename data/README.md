# AS feature snapshots (`IIL-as-feature-snapshot`)

Monthly **per-ASN feature tables** aggregating signals from routing, DNS, scanning,
geolocation, topology, and organization-mapping data sources. Generated with the
methodology described in *Rethinking and Facilitating How We Classify Autonomous Systems
by Network Properties* (IMC '26).

This directory is the data half of the [AS Tagging Toolkit](../README.md) and the
**canonical home** of the snapshots — each new month is committed here. The toolkit's
`OfflineSnapshotProvider` reads these packages directly. The HuggingFace mirror
([zchen798/as_feature_snapshot](https://huggingface.co/datasets/zchen798/as_feature_snapshot))
tracks this directory and backs `OnlineSnapshotProvider` (per-month download); Zenodo holds
a frozen copy per tagged release, for citation.

Please open an issue to report inaccuracies (include ASN, month, and feature name).

## Packaging

Each month is `IIL-as-feature-snapshot.<YYYY-MM>.tar.gz`, which unpacks to a `<YYYY-MM>/`
folder containing:

- `IIL-as-feature-snapshot.<YYYY-MM>.parquet` — the feature table (one row per ASN, Snappy-compressed)
- `manifest.json` — per-source input dates, provenance, and row count
- `schema.json` / `schema.md` — column definitions
- `data_sources.txt` — raw source listing

`index.json` lists every released month with its size, SHA-256 checksum, and per-source
input dates for provenance / reproducibility.

## Schema version

- **v1** — initial schema (current). See `schema.json` / `schema.md` inside each monthly
  package for the authoritative column list for that month; the feature set has grown
  slightly over time as new sources were added (e.g. `caida-itdk` v4/v6 splits,
  `iij-tr-hege`, `LACeS-anycast`).

## Monthly aggregation strategy

- For six measurement-based sources that update daily or at least weekly (**RouteViews
  Prefix-to-AS**, **IIJ AS Hegemony**, **APNIC Eyeball**, **LACeS Anycast Census**,
  **OpenIntel Tranco**, and **IIJ Traceroute Hegemony**), we collect all available data
  within each month and compute the **monthly average** (mean), to mitigate daily
  fluctuations and leverage all available measurements.
  **Note:** for these sources, features named like `*_cnt` may be **floats** because they
  are monthly averages.

- For **Censys Universal Internet**, we use snapshots published on **Tuesdays** (more
  comprehensive: they include scans for both hosts and virtual hosts). Due to Google
  BigQuery quota constraints, we average over **two Tuesday snapshots per month**.

- For other sources that update more frequently than monthly:
  - **M-Lab NDT**: average over speed tests from the **first week** of each month.
  - **PeeringDB** and **RIR delegation**: **single snapshot per month** (no averaging).
  - **MaxMind GeoLite2**: version available on the **first day of the month**, to
    geolocate prefixes for that month's snapshot.

## Features per data source

- **Delegation** (*delegation*): (single monthly snapshot)
  - `delegation_rir` (qualitative): The Regional Internet Registry that delegated the AS number.
  - `delegation_cc` (qualitative): The country code where the AS number was registered.

- **APNIC eyeball dataset** (*apnic-eyeball*): (monthly average over all available days in the month)
  - `apnic-eyeball_top_frac`: Monthly average of the maximal country eyeball fraction across all countries.
  - `apnic-eyeball_eyeball_cnt`: Monthly average of total inferred eyeballs across all countries.
  - `apnic-eyeball_cc_cnt`: Monthly average number of countries in which the AS has eyeballs.
  - `apnic-eyeball_gini`: Monthly average equality level of country eyeball fraction.
  - `apnic-eyeball_top_cc(frac)` (qualitative): Country code with maximal eyeball fraction (derived from the aggregated month).
  - `apnic-eyeball_top_cc(num)` (qualitative): Country code with maximal inferred eyeballs (derived from the aggregated month).

- **Hypergiants' off-nets estimations** (*hg-offnet*): (single monthly snapshot / simple aggregation)
  - `hg-offnet_v4addr_cnt`: Number of distinct IPv4 addresses hosting hypergiants' off-net servers (for the month).

- **MaxMind GeoLite2** (*maxmind-geolite2*): (use the version on the first day of the month)
  - `maxmind-geolite2_cc_v4_cnt`: Number of geolocated countries for originated IPv4 addresses.
  - `maxmind-geolite2_cc_v6_cnt`: Number of geolocated countries for originated IPv6 addresses.
  - `maxmind-geolite2_topfrac_v4`: Fraction of IPv4 addresses in the top geolocated country.
  - `maxmind-geolite2_topfrac_v6`: Fraction of IPv6 addresses in the top geolocated country.
  - `maxmind-geolite2_gini_v4`: Equality level of IPv4 geolocation distribution.
  - `maxmind-geolite2_gini_v6`: Equality level of IPv6 geolocation distribution.
  - `maxmind-geolite2_cc_v4_dict` (qualitative): Country distribution dictionary for IPv4 geolocation.
  - `maxmind-geolite2_cc_v6_dict` (qualitative): Country distribution dictionary for IPv6 geolocation.
  - `maxmind-geolite2_topcc_v4` (qualitative): Top geolocated country code for IPv4.
  - `maxmind-geolite2_topcc_v6` (qualitative): Top geolocated country code for IPv6.

- **Censys Universal Internet** (*censys*): (average of two Tuesday snapshots per month)
  - `censys_v4addr_cnt`: Monthly-averaged number of responsive IPv4 addresses.
  - `censys_os_cnt`: Monthly-averaged number of distinct scanned operating systems.
  - `censys_service_cnt`: Monthly-averaged number of distinct scanned services.
  - `censys_port_cnt`: Monthly-averaged number of distinct scanned ports.
  - `censys_voip_cnt`: Monthly-averaged number of IPs with open port 5060 or 5061.
  - `censys_ics_cnt`: Monthly-averaged number of IPs with ports commonly used by industrial control systems.
  - `censys_http_cnt`: Monthly-averaged number of IPs hosting the HTTP service.
  - `censys_ssh_cnt`: Monthly-averaged number of IPs with open port 22.
  - `censys_auth_cnt`: Monthly-averaged number of IPs hosting an authoritative DNS server.
  - `censys_forw_cnt`: Monthly-averaged number of IPs hosting a forwarding DNS server.
  - `censys_recu_cnt`: Monthly-averaged number of IPs hosting a recursive DNS server.
  - `censys_fdnsname_cnt`: Monthly-averaged number of host names detected via forward DNS.
  - `censys_rdnsname_cnt`: Monthly-averaged number of host names detected via reverse DNS.
  - Top OS (monthly-averaged counts + names): `censys_os_1_cnt`/`_name`, `censys_os_2_cnt`/`_name`, `censys_os_3_cnt`/`_name`
  - Top Port (monthly-averaged counts + names): `censys_port_1_cnt`/`_name`, `censys_port_2_cnt`/`_name`, `censys_port_3_cnt`/`_name`
  - Top Service (monthly-averaged counts + names): `censys_service_1_cnt`/`_name`, `censys_service_2_cnt`/`_name`, `censys_service_3_cnt`/`_name`

- **OpenIntel Active DNS Measurements: Tranco** (*openintel-tranco*): (monthly average over all available data in the month)
  - `openintel-tranco_v4addr_cnt`: Monthly-averaged number of distinct IPv4 addresses hosting web servers for Tranco domains.
  - `openintel-tranco_v6addr_cnt`: Monthly-averaged number of distinct IPv6 addresses hosting web servers for Tranco domains.
  - `openintel-tranco_topdomain_cnt`: Monthly-averaged number of distinct hosted Tranco top domains.

- **CAIDA AS Relationship** (*caida-asrel*): (single monthly snapshot)
  - `caida-asrel_provider_cnt`: Number of inferred providers.
  - `caida-asrel_customer_cnt`: Number of inferred customers.
  - `caida-asrel_peer_cnt`: Number of inferred peers.
  - `caida-asrel_cone_/24_cnt`: IPv4 space in /24s of the customer cone.
  - `caida-asrel_cone_/64_cnt`: IPv6 space in /64s of the customer cone.
  - `caida-asrel_cone_as_cnt`: Number of ASes inferred in the customer cone.
  - `caida-asrel_provider_list` (qualitative): List of inferred providers.
  - `caida-asrel_customer_list` (qualitative): List of inferred customers.
  - `caida-asrel_peer_list` (qualitative): List of inferred peers.
  - `caida-asrel_cone_as_list` (qualitative): List of ASes inferred in the customer cone.

- **RouteViews Prefix2AS from CAIDA** (*pfx2as*): (monthly average over all available days in the month)
  - `pfx2as_/24_cnt`: Monthly-averaged IPv4 space in /24s originated by the AS.
  - `pfx2as_/64_cnt`: Monthly-averaged IPv6 space in /64s originated by the AS.

- **ISI ANT Censuses of the Internet Address Space** (*isi*): (single monthly snapshot / simple aggregation)
  - `isi_/24_cnt`: Number of /24s with at least one active IP address based on ISI Internet Census.

- **Merit Network Telescope** (*merit*): (single monthly snapshot / simple aggregation)
  - `merit_/24_cnt`: Maximal number of /24s observed hourly by Merit network telescope within one month.

- **M-Lab NDT** (*mlab-ndt*): (aggregate over the entire month)
  - `mlab-ndt_v4addr_cnt`: Number of distinct IPv4 client IP addresses that initiated at least one NDT speed test during the month (deduplicated across NDT5 and NDT7).
  - `mlab-ndt_v6addr_cnt`: Number of distinct IPv6 client IP addresses that initiated at least one NDT speed test during the month (deduplicated across NDT5 and NDT7).
  - `mlab-ndt_/24_cnt`: Number of distinct IPv4 /24 client subnets (derived from client IPs) that initiated at least one NDT speed test during the month.
  - `mlab-ndt_/64_cnt`: Number of distinct IPv6 /64 client subnets (derived from client IPs) that initiated at least one NDT speed test during the month.

- **CAIDA Macroscopic Internet Topology Data Kit (ITDK)** (*caida-itdk*): (single monthly snapshot)
  - Aggregate: `caida-itdk_router_cnt`, `caida-itdk_topfrac`, `caida-itdk_cc_cnt`, `caida-itdk_gini`, `caida-itdk_topcc` (qualitative)
  - IPv4-only: `caida-itdk_router_cnt_v4`, `caida-itdk_topfrac_v4`, `caida-itdk_cc_cnt_v4`, `caida-itdk_gini_v4`, `caida-itdk_topcc_v4` (qualitative)
  - IPv6-only: `caida-itdk_router_cnt_v6`, `caida-itdk_topfrac_v6`, `caida-itdk_cc_cnt_v6`, `caida-itdk_gini_v6`, `caida-itdk_topcc_v6` (qualitative)

- **IIJ AS Hegemony** (*iij-hege*): (monthly average over all available data in the month)
  - `iij-hege_global_hege_v4`: Monthly average AS hegemony based on global IPv4 BGP data.
  - `iij-hege_global_hege_v6`: Monthly average AS hegemony based on global IPv6 BGP data.

- **IIJ Traceroute Hegemony** (*iij-tr-hege*): (monthly average over all available data in the month)
  - `iij-tr-hege_ix_cnt`: Monthly-averaged number of peered IXPs (traceroute-based).
  - `iij-tr-hege_peers_cnt`: Monthly-averaged number of peered ASNs through IXPs (traceroute-based).
  - `iij-tr-hege_ix_hegemony`: Monthly-averaged summation of IXP-peered ASNs hegemony.

- **IIL-AS2Org** (*inetintel-as2org*): (single monthly snapshot, from [Dataset-AS-to-Organization-Mapping](https://github.com/InetIntel/Dataset-AS-to-Organization-Mapping))
  - `inetintel-as2org_sibling_cnt`: Number of inferred sibling ASes.
  - `inetintel-as2org_sibling_list` (qualitative): List of inferred sibling ASes.

- **PeeringDB** (*pdb*): (single monthly snapshot)
  - `pdb_ix_cnt`: Number of peered IXPs based on PeeringDB.
  - `pdb_website` (qualitative): Website URL based on PeeringDB.

- **LACeS Anycast Census** (*LACeS-anycast*): (monthly average over all available data in the month)
  - `LACeS-anycast_v4_cnt`: Monthly-averaged number of distinct IPv4 addresses detected as anycast.
  - `LACeS-anycast_v6_cnt`: Monthly-averaged number of distinct IPv6 addresses detected as anycast.

## License

The feature-snapshot data is distributed under Georgia Tech's Acceptable Use Agreement.
See [`LICENSE`](LICENSE) in this directory. This is separate from the MIT license that
covers the toolkit code.
