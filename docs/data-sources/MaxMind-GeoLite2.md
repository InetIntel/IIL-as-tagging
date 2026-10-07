# MaxMind GeoLite2: Source Terms and Release Treatment

This document records the license, attribution requirement, and public-release treatment for MaxMind GeoLite2 City data used by this repository.

The public snapshots do not reproduce a GeoLite2 database or MaxMind's IP-block-to-country mappings. They contain AS-level features calculated by combining GeoLite2 with an independently obtained prefix-to-AS dataset and then aggregating the resulting address-space geolocation by AS.

## Source and governing terms

- Data source: [MaxMind GeoLite Databases and Web Services](https://dev.maxmind.com/geoip/geolite2-free-geolocation-data/)
- Governing agreement: [GeoLite End User License Agreement](https://www.maxmind.com/en/geolite/eula)
- Incorporated public license: [Creative Commons Attribution-ShareAlike 4.0 International](https://creativecommons.org/licenses/by-sa/4.0/)
- MaxMind guidance on external display and attribution: [Sell or display data from GeoLite databases and web services](https://support.maxmind.com/knowledge-base/articles/sell-or-display-data-from-geolite-databases-and-web-services)
- MaxMind guidance on database updates: [Maintain up-to-date data](https://support.maxmind.com/knowledge-base/articles/maintain-up-to-date-data)

The GeoLite EULA applies to users of the GeoLite databases and incorporates CC BY-SA 4.0 for copyrightable elements. Its limited grant states that:

> “those copyrightable elements are governed by the Creative Commons License.”

The EULA separately requires attribution:

> “You must provide attribution of your use to MaxMind”

MaxMind's published guidance expressly permits applications available outside the user's organization, and the display of GeoLite-derived information to external users, provided that MaxMind is attributed. GeoLite is not subject to a non-commercial-use restriction.

The EULA also requires users not to use GeoLite Data to identify or locate a specific household, individual, or street address. The features described here operate only at AS and country level and are not designed or released for any such purpose.

Feature generation uses current GeoLite2 releases as required by the EULA; GeoLite2 databases are not included in this repository.

## Features included in the public snapshots

The snapshots include the following per-AS features:

- `maxmind-geolite2_cc_v4_cnt`: number of countries represented in the AS's GeoLite2-geolocated originated IPv4 address space
- `maxmind-geolite2_cc_v6_cnt`: number of countries represented in the AS's GeoLite2-geolocated originated IPv6 address space
- `maxmind-geolite2_topfrac_v4`: fraction of the AS's originated IPv4 address space assigned to its largest country bucket
- `maxmind-geolite2_topfrac_v6`: fraction of the AS's originated IPv6 address space assigned to its largest country bucket
- `maxmind-geolite2_gini_v4`: Gini-based distribution summary of the AS's originated IPv4 address space across country buckets
- `maxmind-geolite2_gini_v6`: Gini-based distribution summary of the AS's originated IPv6 address space across country buckets
- `maxmind-geolite2_cc_v4_dict`: country-to-address-count distribution calculated for the AS's originated IPv4 address space
- `maxmind-geolite2_cc_v6_dict`: country-to-address-count distribution calculated for the AS's originated IPv6 address space
- `maxmind-geolite2_topcc_v4`: country code of the largest IPv4 country bucket calculated for the AS
- `maxmind-geolite2_topcc_v6`: country code of the largest IPv6 country bucket calculated for the AS

These fields also support higher-level project tags such as `Any Presence`, `Domestic`, and `Major Access`. Those tags are further computations over the AS-level distributions rather than fields obtained from GeoLite2.

## Public-snapshot treatment

GeoLite2 maps IP blocks to geographic attributes; it does not provide the AS-level distributions released here. The project combines GeoLite2 with an independent prefix-to-AS source to calculate per-AS country distributions and summaries. The ASN association and the resulting `ASN -> country/address-count` values are not supplied by MaxMind.

The public snapshots do not include GeoLite2 files, IP-block mappings, location records, or a replacement lookup table. The released AS-level values do not preserve the database's row structure or lookup functionality and are treated as independently calculated, non-reconstructable statistics rather than copies of the GeoLite2 database.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

CC BY-SA 4.0 and the GeoLite EULA continue to govern the GeoLite2 database itself. Because the repository does not distribute that database, its records, or a replacement IP-geolocation lookup product, it does not apply CC BY-SA 4.0 to the independently generated AS-level statistics.

## Attribution and publication requirements

The repository should include the following attribution wherever the MaxMind-derived features are documented:

> These AS-level features were derived in part from GeoLite Data created by MaxMind, available from <https://www.maxmind.com>. This repository does not redistribute the GeoLite2 database or its IP-level geolocation mappings.
