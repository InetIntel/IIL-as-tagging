# Censys Universal Internet Data: Terms and Release Treatment

This document records the applicable terms, direct permission confirmation, and public-release treatment for features derived from the Censys Universal Internet Dataset.

## Source and governing terms

- Source: [Censys Universal Internet Dataset](https://docs.censys.com/docs/research-access-to-censys-data)
- Terms: [Censys Terms of Service](https://censys.com/terms-of-service)

Censys researcher terms generally prohibit redistribution of Censys Data without prior written consent while allowing its inclusion in written reports and publications. Censys confirmed in writing that the AS-level features described below may be included in the public IIL-AS-Tagging artifact.

## Features included in the public snapshots

The snapshots include monthly per-AS aggregates calculated from two Tuesday snapshots per month:

- counts of responsive IPv4 addresses and distinct forward- and reverse-DNS names;
- counts of operating-system products, ports, services, selected service categories, and DNS server categories; and
- top-three operating-system products, ports, and service names, together with their AS-level counts.

These fields use the `censys_*` prefix in the public schema.

## Public-snapshot treatment

The snapshots contain only AS-level aggregate features. They do not contain host-level records or identifiers and do not retain the detail needed to reconstruct the underlying Censys observations.

## License for the released features

The released features form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE), in accordance with Censys's written permission.

The repository-wide agreement governs only the released feature representation. The Censys Terms of Service continue to govern the underlying Censys data and access to the Censys service.

## Attribution and publication requirements

The repository must identify Censys as the upstream source and link to Censys. Publications using these features should cite:

> Zakir Durumeric, David Adrian, Ariana Mirian, Michael Bailey, and J. Alex Halderman. “A Search Engine Backed by Internet-Wide Scanning.” *Proceedings of the 22nd ACM SIGSAC Conference on Computer and Communications Security (CCS '15)*, 2015. <https://doi.org/10.1145/2810103.2813703>

