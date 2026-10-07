# APNIC Labs Eyeball Population Data: Source Terms and Release Treatment

This document records the source terms and release treatment for APNIC Labs Customer Population data used by this repository.

## Source and governing terms

- Data source: [APNIC Labs Customer Populations (Est.) per Network](https://stats.labs.apnic.net/aspop/)
- APNIC Labs measurement index: [APNIC Labs Measurements](https://labs.apnic.net/measurements/)
- Measurement data-handling statement: [Data Handling Practices for APNIC Measurements using Ad Serving](https://labs.apnic.net/privacy.shtml)
- APNIC statement of purpose for its statistics: [APNIC Statistics](https://www.apnic.net/statistics/)
- Accuracy and liability terms: [APNIC Statistics Disclaimer](https://www.apnic.net/stats/terms/)

As of September 2026, no dataset-specific license, Acceptable Use Agreement, click-through agreement, or reuse and redistribution terms were identified on the Customer Populations endpoint or the linked APNIC Labs pages. The source endpoint publicly offers the reports in display, CSV, and JSON formats without requiring authentication, but does not display a license or AUA.

APNIC describes the intended role of its statistics as:

> “for use in research and analysis on global and regional Internet operation trends.”

APNIC also explains that its measurement system produces:

> “aggregate totals by country and by originating Autonomous System (network).”

The APNIC Statistics Disclaimer addresses accuracy and liability rather than granting or restricting reuse. It states:

> “APNIC is not responsible for any issues that may arise from the use of this data.”

The absence of a published dataset-specific license is not treated as an express grant to redistribute APNIC's source files or daily reports.

## Features included in the public snapshots

The snapshots include these monthly per-AS summaries:

- `apnic-eyeball_top_frac`: monthly average of the maximal country eyeball fraction across all countries
- `apnic-eyeball_eyeball_cnt`: monthly average of total inferred eyeballs across all countries
- `apnic-eyeball_cc_cnt`: monthly average number of countries in which the AS has eyeballs
- `apnic-eyeball_gini`: monthly average Gini coefficient of the AS's daily country eyeball distribution; larger values indicate a more uneven distribution
- `apnic-eyeball_top_cc(frac)`: mode of the daily country codes having the maximal eyeball fraction
- `apnic-eyeball_top_cc(num)`: most frequent country code among the daily maximum inferred-eyeball countries

## Public-snapshot treatment

APNIC's input is already aggregated by day, country, and ASN. The public snapshots contain only the monthly per-AS summaries above, not APNIC's daily files, complete ASN-by-country tables, or measurement records. The project therefore treats the released fields as non-reconstructable statistical summaries rather than redistribution of APNIC's source reports.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

Because APNIC has not published an explicit reuse license for this dataset, this conclusion is limited to the derived features above and does not extend to republication of APNIC's daily reports or source files.

## Attribution and publication requirements

We did not identify an APNIC-specific attribution, citation, publication-reporting, non-commercial-use, or share-alike requirement for the Customer Populations reports. The project nevertheless identifies APNIC Labs as the upstream source for provenance and reproducibility.

Recommended source attribution:

> APNIC Labs, “Customer Populations (Est.) per Network,” data for the applicable snapshot month, <https://stats.labs.apnic.net/aspop/>.

