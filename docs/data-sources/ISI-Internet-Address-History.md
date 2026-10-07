# ISI Internet Address History: Data Use Agreement and Release Treatment

This document records the controlling Data Use Agreement, publication conditions, and attribution requirement for the USC Information Sciences Institute (ISI) Internet Address History dataset.

The public snapshots do not reproduce the ISI address-history files, responsive IP addresses, responsive `/24` lists, per-census observations, or the structure of the source dataset. They contain only one per-AS aggregate count produced by combining ISI observations with an independently obtained prefix-to-AS dataset.

## Source and governing terms

- Data source: [ISI ANT Internet Address History](https://ant.isi.edu/datasets/address/index.html)
- Dataset index: [ISI ANT Datasets](https://ant.isi.edu/datasets/)
- Governing agreement: **USC Data Use Agreement (USC/LANDER and Researcher Agreement 2016-08-16-ni)**, as executed by USC and the authorized researcher
- Methodology paper: John Heidemann, Yuri Pradkin, Ramesh Govindan, Christos Papadopoulos, Genevieve Bartlett, and Joseph Bannister, [*Census and Survey of the Visible Internet*](https://doi.org/10.1145/1452520.1452568), ACM Internet Measurement Conference, 2008

The ISI dataset is access-controlled rather than distributed under a general open-data license. The executed Data Use Agreement grants the researcher a limited, non-exclusive, revocable, and non-transferable license to use the covered Confidential Information for the research described in the agreement.

The agreement nevertheless expressly authorizes publication of analytical results. Section 5 states:

> “Researcher may publish research results based on the analysis of the Confidential Information”

This permission is conditioned on published results excluding personally identifiable or otherwise sensitive information, including information that could recreate the contents or structure of the original trace data or map data to a specific individual. Section 5 also requires USC/ITS acknowledgment in published works, including the measurement type, dataset identifier, and measurement dates.

The agreement does not authorize redistribution of the underlying Confidential Information. Sections 1 and 6 require it to remain confidential, and Section 7 makes the researcher's license non-transferable. The project therefore distinguishes the permitted publication of non-reconstructable research results under Section 5 from the prohibited disclosure or transfer of the source data governed by Sections 1, 6, and 7.

## Features included in the public snapshots

The snapshots include the following per-AS feature:

- `isi_/24_cnt`: number of distinct IPv4 `/24` networks associated with the AS that contained at least one responsive address in the census selected for the snapshot

The feature uses one selected census and an independently obtained prefix-to-AS mapping. ISI does not supply the released ASN association.

## Public-snapshot treatment

The public snapshots contain no ISI files, IP addresses, `/24` lists, per-census records, or individual-level information. The aggregate count does not reveal which addresses or networks produced it and is treated as a non-reconstructable research result permitted by Section 5, not as a transfer of the underlying Confidential Information.

## License for the released features

The released features described above form part of IIL-AS-Tagging and are distributed under the repository-wide [Georgia Tech Acceptable Use Agreement](https://github.com/InetIntel/IIL-as-tagging/blob/main/LICENSE).

The repository-wide agreement governs only the released feature representation. It does not relicense or grant rights in upstream source data or files.

The USC Data Use Agreement continues to govern the ISI source data and does not permit its transfer or redistribution.

## Attribution and publication requirements

Section 5 of the USC Data Use Agreement requires an acknowledgment substantially similar to the following, with the actual dataset identifier and measurement dates inserted:

> Internet Address History, IMPACT ID US/[dataset identifier] ([measurement start date] to [measurement end date]). Provided by USC. <https://ant.isi.edu/datasets>

The repository documentation and publications using `isi_/24_cnt` should also cite the census paper from which this dataset and methodology originate:

> John Heidemann, Yuri Pradkin, Ramesh Govindan, Christos Papadopoulos, Genevieve Bartlett, and Joseph Bannister. “Census and Survey of the Visible Internet.” *Proceedings of the 8th ACM SIGCOMM Conference on Internet Measurement (IMC '08)*, 2008. <https://doi.org/10.1145/1452520.1452568>

The paper citation supplements rather than replaces the dataset acknowledgment required by the Data Use Agreement. The dataset identifier and date range in that acknowledgment should be taken from the specific ISI release used to generate the published snapshot rather than replaced with a generic citation.
