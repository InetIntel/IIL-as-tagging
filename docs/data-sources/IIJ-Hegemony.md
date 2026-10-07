# IIJ Internet Health Report Hegemony Data: License and Release Treatment

This document records the license, direct permission confirmation, and public-release treatment for IIJ Internet Health Report (IHR) AS Hegemony and Traceroute Hegemony data.

## Source and governing terms

- AS Hegemony archive: [IIJ IHR AS Hegemony](https://ihr-archive.iijlab.net/ihr/hegemony/)
- Traceroute Hegemony archive: [IIJ IHR Traceroute Hegemony](https://ihr-archive.iijlab.net/ihr/tr_hegemony/)
- IHR license statement: [IHR Archive](https://archive.ihr.live/)
- Public license: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

The IHR archive states:

> Internet Health Report data is licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License.

IIJ/IHR confirmed in writing that the five derived features below may be published as part of the IIL-AS-Tagging artifact.

## Features included in the public snapshots

- `iij-hege_global_hege_v4`: monthly average global AS Hegemony based on IPv4 BGP data
- `iij-hege_global_hege_v6`: monthly average global AS Hegemony based on IPv6 BGP data
- `iij-tr-hege_ix_cnt`: monthly average number of peered IXPs inferred from traceroute data
- `iij-tr-hege_peers_cnt`: monthly average number of AS peers reached through IXPs
- `iij-tr-hege_ix_hegemony`: monthly average aggregate hegemony of IXP-peered ASes

## Public-snapshot treatment

The public snapshots contain only the monthly per-AS fields above, not IIJ/IHR archive files, daily records, BGP paths, traceroutes, or per-observation dependency records.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

## Attribution and publication requirements

The repository and publications using these features should identify IIJ's Internet Health Report as the source and cite:

> Romain Fontugne, Anant Shah, and Emile Aben. “The (Thin) Bridges of AS Connectivity: Measuring Dependency Using AS Hegemony.” *Passive and Active Measurement (PAM 2018)*, pp. 216–227, 2018. <https://www.iijlab.net/en/members/romain/pdf/romain_pam2018.pdf>

> Malte Tashiro, Romain Fontugne, and Kensuke Fukuda. “Following the Data Trail: An Analysis of IXP Dependencies.” *Passive and Active Measurement (PAM 2024)*, pp. 199–227, 2024. <https://doi.org/10.1007/978-3-031-56252-5_10>
