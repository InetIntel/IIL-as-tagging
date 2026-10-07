# OpenINTEL Tranco Data: License and Release Treatment

This document records the license, direct permission confirmation, and public-release treatment for features derived from the OpenINTEL Tranco forward-DNS dataset.

## Source and governing terms

- Source: [OpenINTEL data access](https://openintel.nl/data-access/)
- Terms: [OpenINTEL Terms of Use](https://openintel.nl/download/terms/)
- Public license: [CC BY-NC-SA 4.0](https://creativecommons.org/licenses/by-nc-sa/4.0/)

The OpenINTEL Terms of Use apply CC BY-NC-SA 4.0 to the open-access source data and require attribution and citation. OpenINTEL confirmed in writing that the aggregate features below form a novel dataset rather than redistribution of OpenINTEL source data and may be released under the project's own terms, provided that the required attribution and citation are included.

## Features included in the public snapshots

- `openintel-tranco_topdomain_cnt`: monthly average daily count of distinct response names associated with the ASN
- `openintel-tranco_v4addr_cnt`: monthly average daily count of distinct IPv4 addresses in A responses associated with the ASN
- `openintel-tranco_v6addr_cnt`: monthly average daily count of distinct IPv6 addresses in AAAA responses associated with the ASN

## Public-snapshot treatment

The snapshots contain only the three monthly per-AS counts above. They do not contain domain names, IP addresses, DNS responses, daily observations, or OpenINTEL source records, and do not retain the detail needed to reconstruct those records.

## License for the released features

The released features form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE), in accordance with OpenINTEL's written confirmation.

The repository-wide agreement governs only the released feature representation. CC BY-NC-SA 4.0 and the OpenINTEL Terms of Use continue to govern the OpenINTEL source data.

## Attribution and publication requirements

The repository must include the attribution required by OpenINTEL:

> The research leading to these results was made possible by OpenINTEL (https://www.openintel.nl/), a joint project of the University of Twente, SIDN, NLnet Labs and SURF.

Publications using these features must cite:

> Roland van Rijswijk-Deij, Mattijs Jonker, Anna Sperotto, and Aiko Pras. “A High-Performance, Scalable Infrastructure for Large-Scale Active DNS Measurements.” *IEEE Journal on Selected Areas in Communications*, 34(7), pp. 1877–1888, 2016. <https://doi.org/10.1109/JSAC.2016.2558918>

