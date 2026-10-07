# AS feature snapshots (IIL-as-feature-snapshot)

Monthly **per-ASN feature tables** aggregating signals from routing, DNS, scanning,
geolocation, topology, and organization-mapping data sources.

These feature snapshots are published with the **[AS Tagging Toolkit](https://github.com/InetIntel/IIL-as-tagging)**
(`pip install as-tagging`). The methodology is described in the paper *Rethinking and
Facilitating How We Classify Autonomous Systems by Network Properties* (ACM IMC 2026).

- **Canonical source:** the GitHub repo [InetIntel/IIL-as-tagging](https://github.com/InetIntel/IIL-as-tagging)
  — `data/` holds every released month; new months are committed there.
- **DOI Reference:** Zenodo — https://doi.org/10.5281/zenodo.22232206
- The HuggingFace dataset is a mirror, kept in sync with the GitHub repo.

## How to use

With the toolkit (recommended):

```python
from as_tagging import ASTagging, OnlineSnapshotProvider

provider = OnlineSnapshotProvider()          # reads this dataset
tagger = ASTagging(snapshot_provider=provider, date="2026-07")
```

Or access the files directly. On GitHub, each released month is stored as
`data/IIL-as-feature-snapshot.<YYYY-MM>.tar.gz`; on HuggingFace, the corresponding archive
is under `archives/`. Each archive unpacks to a `<YYYY-MM>/` folder containing:

- `IIL-as-feature-snapshot.<YYYY-MM>.parquet` — the feature table, one row per ASN (Snappy-compressed)
- `manifest.json` — per-source input dates, provenance, row count
- `schema.json` / `schema.md` — column definitions
- `data_sources.txt` — raw source listing

`index.json` lists every released month with its size, SHA-256, and per-source input dates.
The HuggingFace mirror also exposes each month pre-extracted under
`snapshots/<YYYY-MM>/`, with the parquet file named `data.parquet`, for direct access.

The dataset is organized per ASN. Each ASN is associated with the features below (feature
keys are shown as they appear in the snapshots).

## Schema version

The current schema version is **v1**. The feature set has grown slightly over time as new
sources were added, so `schema.json` and `schema.md` inside each monthly package are the
authoritative column definitions for that snapshot.

---

## Monthly aggregation strategy

We generate monthly feature snapshots by aggregating data from the sources below.

- For six measurement-based sources that update daily or at least weekly (**RouteViews Prefix-to-AS**, **IIJ AS Hegemony**, **APNIC Eyeball**, **LACeS Anycast Census**, **OpenIntel Tranco**, and **IIJ Traceroute Hegemony**), we collect all available data within each month and compute the **monthly average** (mean), to mitigate daily fluctuations and leverage all available measurements.  
  **Note:** For these sources, features with names like `*_cnt` may be **floats** because they are monthly averages.

- For **Censys Universal Internet**, we use snapshots published on **Tuesdays** (more comprehensive because they include scans for both hosts and virtual hosts). Due to Google BigQuery quota constraints, we average over **two Tuesday snapshots per month**.

- For other sources that update more frequently than monthly, we use simpler strategies:
  - **M-Lab NDT**: aggregate speed tests from the **entire month**, deduplicated across
    NDT5 and NDT7.
  - **PeeringDB** and **RIR delegation**: use a **single snapshot per month** (no averaging).
  - **MaxMind GeoLite2**: use one release per monthly snapshot to geolocate
    prefixes. The 2024-08 through 2024-11 snapshots use the 2024-11-22 release;
    each month's `manifest.json` records its source date.

---

## Data sources and citations

Each snapshot aggregates the upstream datasets below. The exact per-source input date for
a given month is recorded in that month's `manifest.json` (`source_dates`) and
`data_sources.txt`; the list here is the static provenance and citations.

- **RouteViews Prefix2AS** (CAIDA) — https://www.caida.org/catalog/datasets/routeviews-prefix2as/
- **IIJ AS Hegemony**, IPv4 & IPv6 [1] — https://ihr-archive.iijlab.net/ihr/hegemony/
- **IIJ Traceroute Hegemony** [2] — https://ihr-archive.iijlab.net/ihr/tr_hegemony/
- **APNIC Eyeball** — https://stats.labs.apnic.net/aspop/
- **LACeS Anycast Census** [3] — https://github.com/ut-dacs/anycast-census/
- **OpenIntel Active DNS Measurements: Tranco** [4] — https://www.openintel.nl/data-access/
- **M-Lab NDT** — https://www.measurementlab.net/tests/ndt/
- **PeeringDB** (daily snapshot via CAIDA) — https://www.caida.org/catalog/datasets/peeringdb/
- **RIR delegation files** — ARIN, AFRINIC, APNIC, LACNIC, RIPE NCC public stats
- **MaxMind GeoLite2** — https://dev.maxmind.com/geoip/geolite2-free-geolocation-data/
- **Censys Universal Internet** (BigQuery) [5] — https://support.censys.io/hc/en-us/articles/360056063151-About-the-Censys-Universal-Internet-Dataset-BigQuery-Dataset
- **CAIDA AS Relationships** — https://www.caida.org/catalog/datasets/as-relationships/
- **Internet Intelligence Lab AS2Org** [6] — https://github.com/InetIntel/Dataset-AS-to-Organization-Mapping
- **ISI ANT Censuses of the Internet Address Space**, internet_address_history [7] — https://comunda.isi.edu/artifact/
- **CAIDA Macroscopic Internet Topology Data Kit (ITDK)** — https://www.caida.org/catalog/datasets/internet-topology-data-kit/
- **Hypergiants' off-net estimations** [8] — generated with our implementation of the SIGCOMM 2021 method
- **Merit Network Telescope** — https://www.merit.edu/research/projects/orion-network-telescope/

[1] Fontugne, Romain, Anant Shah, and Emile Aben. "The (thin) bridges of as connectivity: Measuring dependency using as hegemony." Passive and Active Measurement: 19th International Conference, PAM 2018, Berlin, Germany, March 26–27, 2018, Proceedings 19. Springer International Publishing, 2018.

[2] Tashiro, Malte, Romain Fontugne, and Kensuke Fukuda. "Following the Data Trail: An Analysis of IXP Dependencies." International Conference on Passive and Active Network Measurement. Cham: Springer Nature Switzerland, 2024.

[3] Hendriks, Remi, et al. "Laces: an open, fast, responsible and efficient longitudinal anycast census system." Proceedings of the 2025 ACM Internet Measurement Conference. 2025.

[4] van Rijswijk-Deij, Roland, et al. "A high-performance, scalable infrastructure for large-scale active DNS measurements." IEEE journal on selected areas in communications 34.6 (2016): 1877-1888.

[5] Durumeric, Zakir, et al. "A search engine backed by Internet-wide scanning." Proceedings of the 22nd ACM SIGSAC conference on computer and communications security. 2015.

[6] Chen, Zhiyi, et al. "Improving the Inference of Sibling Autonomous Systems." International Conference on Passive and Active Network Measurement. Cham: Springer Nature Switzerland, 2023.

[7] Heidemann, John, et al. "Census and survey of the visible Internet." Proceedings of the 8th ACM SIGCOMM conference on Internet measurement. 2008.

[8] Gigis, Petros, et al. "Seven years in the life of Hypergiants' off-nets." Proceedings of the 2021 ACM SIGCOMM 2021 Conference. 2021.

---

## Features per data source

- **Delegation** (*delegation*): (single monthly snapshot)
  - `delegation_rir` (qualitative): The Regional Internet Registry that delegated the AS number.
  - `delegation_cc` (qualitative): The country code where the AS number was registered.

- **APNIC eyeball dataset** (*apnic-eyeball*): (monthly average over all available days in the month)
  - `apnic-eyeball_top_frac`: Monthly average of the maximal country eyeball fraction across all countries.
  - `apnic-eyeball_eyeball_cnt`: Monthly average of total inferred eyeballs across all countries.
  - `apnic-eyeball_cc_cnt`: Monthly average number of countries in which the AS has eyeballs.
  - `apnic-eyeball_gini`: Monthly average Gini coefficient of the country eyeball distribution (higher means more uneven).
  - `apnic-eyeball_top_cc(frac)` (qualitative): Most frequent daily country code with the maximal eyeball fraction.
  - `apnic-eyeball_top_cc(num)` (qualitative): Most frequent daily country code with the maximal inferred-eyeball count.

- **Hypergiants' off-nets estimations** (*hg-offnet*): (single monthly snapshot / simple aggregation)
  - `hg-offnet_v4addr_cnt`: Number of inferred Hypergiant off-net IPv4 prefixes associated with the ASN.

- **MaxMind GeoLite2** (*maxmind-geolite2*): (one source release per monthly
  snapshot; see `manifest.json` for its date)
  - `maxmind-geolite2_cc_v4_cnt`: Number of geolocated countries for originated IPv4 addresses.
  - `maxmind-geolite2_cc_v6_cnt`: Number of geolocated countries for originated IPv6 addresses.
  - `maxmind-geolite2_topfrac_v4`: Fraction of IPv4 addresses in the top geolocated country.
  - `maxmind-geolite2_topfrac_v6`: Fraction of IPv6 addresses in the top geolocated country.
  - `maxmind-geolite2_gini_v4`: Gini coefficient of the IPv4 geolocation distribution (higher means more uneven).
  - `maxmind-geolite2_gini_v6`: Gini coefficient of the IPv6 geolocation distribution (higher means more uneven).
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

  - Top OS (monthly-averaged counts + names):
    - `censys_os_1_cnt`, `censys_os_1_name` (qualitative)
    - `censys_os_2_cnt`, `censys_os_2_name` (qualitative)
    - `censys_os_3_cnt`, `censys_os_3_name` (qualitative)

  - Top Port (monthly-averaged counts + names):
    - `censys_port_1_cnt`, `censys_port_1_name` (qualitative)
    - `censys_port_2_cnt`, `censys_port_2_name` (qualitative)
    - `censys_port_3_cnt`, `censys_port_3_name` (qualitative)

  - Top Service (monthly-averaged counts + names):
    - `censys_service_1_cnt`, `censys_service_1_name` (qualitative)
    - `censys_service_2_cnt`, `censys_service_2_name` (qualitative)
    - `censys_service_3_cnt`, `censys_service_3_name` (qualitative)

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
  - `caida-asrel_customer_all_sibling`: Whether all customer ASes from CAIDA AS Relationship are sibling ASes in IIL-AS2Org (false if the AS has no customers).
  - `caida-asrel_customer_has_nonsibling`: Whether at least one customer AS from CAIDA AS Relationship is not a sibling AS in IIL-AS2Org.

  The raw per-ASN provider/customer/peer/customer-cone AS lists are omitted from
  public releases and may be reconstructed locally from CAIDA data obtained by
  the user under the Public-AUA. The two booleans above are derived from those
  lists at generation time and are what the AS Tagging Toolkit's *Sibling
  Transit* / *Public Transit* composite tags read from this dataset.

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
  - Aggregate:
    - `caida-itdk_router_cnt`: Number of routers.
    - `caida-itdk_topfrac`: Fraction of routers in the top geolocated country.
    - `caida-itdk_cc_cnt`: Number of geolocated countries for routers.
    - `caida-itdk_gini`: Gini coefficient of router geolocation distribution (higher means more uneven).
    - `caida-itdk_topcc` (qualitative): Top geolocated country code for routers.
  - IPv4-only:
    - `caida-itdk_router_cnt_v4`
    - `caida-itdk_topfrac_v4`
    - `caida-itdk_cc_cnt_v4`
    - `caida-itdk_gini_v4`
    - `caida-itdk_topcc_v4` (qualitative)
  - IPv6-only:
    - `caida-itdk_router_cnt_v6`
    - `caida-itdk_topfrac_v6`
    - `caida-itdk_cc_cnt_v6`
    - `caida-itdk_gini_v6`
    - `caida-itdk_topcc_v6` (qualitative)

- **IIJ AS Hegemony** (*iij-hege*): (monthly average over all available data in the month)
  - `iij-hege_global_hege_v4`: Monthly average AS hegemony based on global IPv4 BGP data.
  - `iij-hege_global_hege_v6`: Monthly average AS hegemony based on global IPv6 BGP data.

- **IIJ Traceroute Hegemony** (*iij-tr-hege*): (monthly average over all available data in the month)
  - `iij-tr-hege_ix_cnt`: Monthly-averaged number of peered IXPs (traceroute-based).
  - `iij-tr-hege_peers_cnt`: Monthly-averaged number of peered ASNs through IXPs (traceroute-based).
  - `iij-tr-hege_ix_hegemony`: Monthly-averaged summation of IXP-peered ASNs hegemony.

- **Internet Intelligence Lab AS2Org** (*inetintel-as2org*): (single monthly snapshot)
  - `inetintel-as2org_sibling_cnt`: Number of inferred sibling ASes.
  - `inetintel-as2org_sibling_list` (qualitative): List of inferred sibling ASes.

- **PeeringDB** (*pdb*): (single monthly snapshot)
  - `pdb_ix_cnt`: Number of peered IXPs based on PeeringDB.

- **LACeS Anycast Census** (*LACeS-anycast*): (monthly average over all available data in the month)
  - `LACeS-anycast_v4_cnt`: Monthly average sum of per-prefix IPv4 anycast-site estimates for the AS.
  - `LACeS-anycast_v6_cnt`: Monthly average sum of per-prefix IPv6 anycast-site estimates for the AS.

---

## License

The feature-snapshot data, like the toolkit code and the rest of the IIL-AS-Tagging
repository, is distributed under Georgia Tech's Acceptable Use Agreement. See the
repository-wide [`LICENSE`](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).
