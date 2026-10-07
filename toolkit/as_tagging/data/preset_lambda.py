"""
Preset composite tag definitions for AS Tagging toolkit.

This module contains lambda expressions for all preset composite tags
described in the AS Tagging paper (Chen, Bischof, Testart, and Dainotti,
"Rethinking and facilitating how we classify Autonomous Systems by
network properties," IMC 2026, https://doi.org/10.1145/3777912.3839831).
Each function implements a specific tag logic that can be applied to AS
feature snapshots. See toolkit/as_tagging/data/composite_tag_description.json
for the rationale and literature background behind each tag's criteria
and thresholds (surfaced via ASTagging.Help(tag_name)).

Tag Categories:
1. Basic network properties (Anycast, Tranco 10k Host, IPv6 Only, No Eyeball)
2. Transit behavior (No Transit, Sibling Transit, Public Transit)
3. Global transit ranking (requires Borda count aggregation)
4. Geolocation-based (Country Code, Any Presence, Domestic, Major Access)

NOTE: Feature names must match the actual column names in the snapshot parquet files.
NOTE: Dict/list columns may be stored as JSON strings - use _safe_get_dict helper.
NOTE: List columns may mix ASN types (int vs "AS123" vs "123") across sources; use
      _asn_set_normalized for set logic.
NOTE: The published snapshot release omits the raw caida-asrel_provider_list /
      customer_list / peer_list / cone_as_list columns for compliance reasons
      (the *_cnt columns are unaffected; the raw lists are still available by
      regenerating a snapshot locally). Sibling Transit / Public Transit fall
      back to precomputed caida-asrel_customer_all_sibling / customer_has_nonsibling
      booleans in that case - see sibling_transit()/public_transit() below.
"""

import json


def _safe_get_dict(tags, key, default=None):
    """
    Safely get a dict value from tags, handling JSON strings.

    Parquet files may store dict columns as JSON strings.
    """
    if default is None:
        default = {}

    val = tags.get(key, default)

    if val is None:
        return default

    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    if isinstance(val, dict):
        return val

    return default


def _safe_get_list(tags, key, default=None):
    """
    Safely get a list value from tags, handling JSON strings.

    Parquet files may store list columns as JSON strings.
    """
    if default is None:
        default = []

    val = tags.get(key, default)

    if val is None:
        return default

    if isinstance(val, str):
        try:
            return json.loads(val)
        except (json.JSONDecodeError, TypeError):
            return default

    if isinstance(val, list):
        return val

    return default


def _safe_get_bool(tags, key):
    """
    Safely get a precomputed boolean value from tags.

    Public snapshots store caida-asrel_customer_all_sibling /
    customer_has_nonsibling as native bool (parquet -> pandas .to_dict()
    yields Python bool for a clean bool column). This also accepts
    numpy.bool_ defensively, since numpy.bool_ is not a `bool` instance and
    is not `is True`/`is False`, without coercing ints/strings - an
    unrecognized type means "not actually a bool value here", same as the
    rest of this module treats unparseable values as absent.

    Returns None if the key is absent or the value isn't bool-like.
    """
    if key not in tags:
        return None
    val = tags.get(key)
    if isinstance(val, bool):
        return val
    if type(val).__name__ == "bool_":  # numpy.bool_, without importing numpy
        return bool(val)
    return None


def _canonical_asn_str(asn):
    """
    Normalize one ASN from int/str/AS-prefix to a numeric string for comparisons.

    Matches as_tagging.utils.normalize_asn_input semantics (without raising on bad
    tokens — those are skipped when building sets).
    """
    if asn is None:
        return None
    s = str(asn).strip().upper()
    if s.startswith("AS"):
        s = s[2:].strip()
    if not s or not s.replace("-", "").isdigit():
        return None
    return s


def _asn_set_normalized(items):
    """Set of canonical ASN strings from a snapshot list column (mixed element types)."""
    out = set()
    for x in items or []:
        c = _canonical_asn_str(x)
        if c is not None:
            out.add(c)
    return out


# =============================================================================
# Basic Network Property Tags
# =============================================================================

def anycast(tags):
    """
    Tag: Anycast

    Returns True if the AS has any IPv4 or IPv6 anycast addresses.
    Uses LACeS anycast census data.

    Reimplements the intended semantics of BGP.tools's identically-named
    public tag; BGP.tools does not publish its methodology. See AS Tagging
    paper Appendix G.2 (module docstring for full citation).
    """
    v4 = tags.get("LACeS-anycast_v4_cnt", 0) or 0
    v6 = tags.get("LACeS-anycast_v6_cnt", 0) or 0
    return v4 > 0 or v6 > 0


def tranco_10k_host(tags):
    """
    Tag: Tranco 10k Host

    Returns True if the AS hosts any domains in the Tranco top domains list.

    Reimplements the intended semantics of BGP.tools's identically-named
    public tag; BGP.tools does not publish its methodology. See AS Tagging
    paper Appendix G.2 (module docstring for full citation).
    """
    return (tags.get("openintel-tranco_topdomain_cnt", 0) or 0) > 0


def ipv6_only(tags):
    """
    Tag: IPv6 Only

    Returns True if the AS originates IPv6 prefixes but no IPv4 prefixes.

    Reimplements the intended semantics of BGP.tools's identically-named
    public tag; BGP.tools does not publish its methodology. See AS Tagging
    paper Appendix G.2 (module docstring for full citation).
    """
    v6_cnt = tags.get("pfx2as_/64_cnt", 0) or 0
    v4_cnt = tags.get("pfx2as_/24_cnt", 0) or 0
    return v6_cnt > 0 and v4_cnt == 0


def no_eyeball(tags):
    """
    Tag: No Eyeball

    Returns True if the AS has no inferred eyeballs.

    Introduced in AS Tagging paper Appendix I to let ASes be tagged along
    the transit and residential-access dimensions independently, instead
    of the small number of mutually exclusive AS-type categories that the
    paper's Section 4 shows fail to separate ASes with similar features
    (module docstring for full citation).
    """
    return (tags.get("apnic-eyeball_eyeball_cnt", 0) or 0) == 0


# =============================================================================
# Transit Behavior Tags
# =============================================================================

def no_transit(tags):
    """
    Tag: No Transit

    Returns True if the AS does not provide IP transit to any other AS.
    Logic: AS has no customers.

    One of three transit-role tags (No Transit / Sibling Transit / Public
    Transit) introduced in AS Tagging paper Section 6, motivated by the
    observation that inferring transit status from CAIDA AS
    Classification's coarse Transit/Access category (a common practice,
    e.g. Marcos et al., "AS-Path Prepending: There Is No Rush Without a
    Push," IMC 2020, https://doi.org/10.1145/3419394.3423642) misses many
    ASes that do provide transit (module docstring for full citation).
    """
    return (tags.get("caida-asrel_customer_cnt", 0) or 0) == 0


def _customer_sibling_sets(tags):
    """Normalized (customer_set, sibling_set) from the raw relationship lists."""
    customers = _safe_get_list(tags, "caida-asrel_customer_list", [])
    siblings = _safe_get_list(tags, "inetintel-as2org_sibling_list", [])
    return _asn_set_normalized(customers), _asn_set_normalized(siblings)


def sibling_transit(tags):
    """
    Tag: Sibling Transit

    Returns True if the AS only provides transit to sibling ASes
    (owned by the same organization).
    Logic: All direct customers are siblings.

    One of three transit-role tags introduced in AS Tagging paper Section 6
    to distinguish transit kept within an organization from transit sold
    externally (module docstring for full citation). Paper example: AS20940
    (Akamai) is the sole upstream for 15 sibling Akamai ASes.

    Data availability:
      1. If caida-asrel_customer_list is present (a locally regenerated
         snapshot, or any historical snapshot that still carries it),
         compute directly from the raw customer/sibling lists.
      2. Otherwise, fall back to the precomputed
         caida-asrel_customer_all_sibling column (present on the published
         snapshot release, which does not include the raw list - see
         module docstring).
      3. Otherwise, return None: this tag cannot be determined from the
         given snapshot.
    """
    if "caida-asrel_customer_list" in tags:
        customer_set, sibling_set = _customer_sibling_sets(tags)
        if not customer_set:
            return False  # No customers (or none parseable) means no transit at all
        return customer_set.issubset(sibling_set)

    return _safe_get_bool(tags, "caida-asrel_customer_all_sibling")


def public_transit(tags):
    """
    Tag: Public Transit

    Returns True if the AS provides IP transit to non-sibling ASes.
    Logic: Some direct customers are not siblings.

    One of three transit-role tags introduced in AS Tagging paper Section 6
    to identify ASes that sell transit to unrelated organizations (module
    docstring for full citation). Paper example: AS23686 (Equinix Connect)
    is identified as a transit provider despite IPinfo labeling it "Hosting."

    Data availability: see sibling_transit() above - same priority order,
    falling back to the precomputed caida-asrel_customer_has_nonsibling
    column, then to None.
    """
    if "caida-asrel_customer_list" in tags:
        customer_set, sibling_set = _customer_sibling_sets(tags)
        # Has at least one customer that is not a sibling
        return len(customer_set - sibling_set) > 0

    return _safe_get_bool(tags, "caida-asrel_customer_has_nonsibling")


# =============================================================================
# Geolocation Tags (parameterized by country)
# =============================================================================

def country_code(tags):
    """
    Tag: Country Code

    ISO country code of the country where the AS number was registered
    (RIR delegation record). This is an administrative attribute, distinct
    from Any Presence / Domestic, which are geolocation-based.

    Returns None when the delegation country is unknown.

    Covers the jurisdiction-based notion of AS "nationality" (registered
    location rather than physical/geolocated infrastructure) used e.g. by
    Trusin, Bertholdo, and Santanna, "The Effect of the Russian-Ukrainian
    Conflict from the Perspective of Internet eXchanges," CNSM 2022,
    https://doi.org/10.23919/CNSM55787.2022.9964765, to track Russian/
    Ukrainian AS reachability during the conflict. See AS Tagging paper
    Appendix H (module docstring for full citation).
    """
    cc = tags.get("delegation_cc")
    if cc is None:
        return None
    cc = str(cc).strip().upper()
    return cc or None


def any_presence(tags):
    """
    Tag: Any Presence

    Returns a list of country codes where the AS has any IP presence
    (either IPv4 or IPv6 addresses geolocated to that country).

    Covers the geolocation-based "any presence" definition used e.g. by
    Padmanabhan et al., "A Multi-Perspective View of Internet Censorship
    in Myanmar," FOCI @ ACM SIGCOMM 2021,
    https://doi.org/10.1145/3473604.3474562, to define ASes "potentially
    impacted" by Myanmar's 2021 Internet shutdown. See AS Tagging paper
    Appendix H (module docstring for full citation).
    """
    v4_dict = _safe_get_dict(tags, "maxmind-geolite2_cc_v4_dict", {})
    v6_dict = _safe_get_dict(tags, "maxmind-geolite2_cc_v6_dict", {})

    return list(set(v4_dict.keys()).union(set(v6_dict.keys())))


def domestic(tags, threshold=2/3):
    """
    Tag: Domestic

    Returns a list of country codes where the AS is considered "domestic",
    meaning >= threshold of its IP addresses are geolocated in that country.

    Default threshold: 2/3 (66.7%)

    Threshold and definition from Gamero-Garrido, Carisimo, Hao, Huffaker,
    Snoeren, and Dainotti, "Quantifying Nations' Exposure to Traffic
    Observation and Selective Tampering," PAM 2022 (Best Dataset award),
    https://doi.org/10.1007/978-3-030-98785-5_29, who used it to study what
    fraction of a country's transit links come from foreign vs. domestic
    providers. See AS Tagging paper Appendix H (module docstring for full
    citation).
    """
    v4_dict = _safe_get_dict(tags, "maxmind-geolite2_cc_v4_dict", {})
    total = sum(v4_dict.values())

    if total == 0:
        return []

    return [
        cc for cc, count in v4_dict.items()
        if count / total >= threshold
    ]


def major_access(tags, country_sums, threshold=0.05):
    """
    Tag: Major Access

    Returns a list of country codes where the AS is a "major access" network,
    meaning it originates >= threshold of the country's total globally routed IPs.

    Requires country_sums: {country_code: total_ip_count} for normalization.
    Default threshold: 5%

    Threshold and definition from Carisimo, Gamero-Garrido, Snoeren, and
    Dainotti, "Identifying ASes of State-Owned Internet Operators," IMC
    2021, https://doi.org/10.1145/3487552.3487822, who used it as one
    signal for identifying state-owned Internet operators within a
    country. See AS Tagging paper Appendix H (module docstring for full
    citation).
    """
    v4_dict = _safe_get_dict(tags, "maxmind-geolite2_cc_v4_dict", {})

    return [
        cc for cc, count in v4_dict.items()
        if country_sums.get(cc, 0) > 0 and count / country_sums[cc] >= threshold
    ]


# =============================================================================
# Global Transit Ranking Tag (requires all ASN data for ranking)
# =============================================================================

# The 5 transit-related features for Borda count ranking
GLOBAL_TRANSIT_FEATURES = [
    "caida-asrel_customer_cnt",   # Number of direct customers
    "caida-asrel_cone_/24_cnt",   # IPv4 customer cone size
    "caida-asrel_cone_/64_cnt",   # IPv6 customer cone size
    "iij-hege_global_hege_v4",    # IPv4 AS Hegemony
    "iij-hege_global_hege_v6",    # IPv6 AS Hegemony
]


def compute_global_transit_rankings(all_tags, top_n=50):
    """
    Compute Global Transit Nth-ranked tag using Borda Count method.

    This function must be called with all ASN tags to compute rankings.

    Args:
        all_tags: Dict[asn, tags] - all ASN tag data
        top_n: Number of top ASNs to rank (default 50)

    Returns:
        Dict[asn, rank] - Global transit rank for each ASN that made top-N

    Introduced in AS Tagging paper Appendix G.3 (module docstring for full
    citation) to rank ASes by overall transit significance without relying
    on any single metric. The 5 features and top_n=50 are the paper's own
    choices; Table 6 in the paper shows this reproduces the expected
    dominance of Tier-1 ASes while surfacing non-Tier-1 transit providers
    such as AS58453 (China Mobile) and AS4637 (Telstra).
    """
    # Step 1: For each feature, get top-N ASNs with their values
    feature_rankings = {}

    for feature in GLOBAL_TRANSIT_FEATURES:
        # Collect (asn, value) pairs
        asn_values = []
        for asn, tags in all_tags.items():
            val = tags.get(feature, 0) or 0
            if val > 0:
                asn_values.append((asn, val))

        # Sort by value descending and take top-N
        asn_values.sort(key=lambda x: x[1], reverse=True)
        top_asns = asn_values[:top_n]

        # Assign Borda points: top gets top_n points, 2nd gets top_n-1, etc.
        feature_rankings[feature] = {
            asn: top_n - i for i, (asn, _) in enumerate(top_asns)
        }

    # Step 2: Aggregate Borda points across all features
    borda_scores = {}
    for feature, rankings in feature_rankings.items():
        for asn, points in rankings.items():
            borda_scores[asn] = borda_scores.get(asn, 0) + points

    # Step 3: Sort by total Borda score and assign final ranks
    sorted_asns = sorted(borda_scores.items(), key=lambda x: x[1], reverse=True)

    # Return {asn: rank} for all ASNs with any score
    return {asn: rank + 1 for rank, (asn, _) in enumerate(sorted_asns)}


# =============================================================================
# Mapping of tag names to functions
# =============================================================================

PRESET_TAG_FUNCTIONS = {
    "Anycast": anycast,
    "Tranco 10k Host": tranco_10k_host,
    "IPv6 Only": ipv6_only,
    "No Eyeball": no_eyeball,
    "No Transit": no_transit,
    "Sibling Transit": sibling_transit,
    "Public Transit": public_transit,
    "Country Code": country_code,
    "Any Presence": any_presence,
    "Domestic": domestic,
    "Major Access": major_access,  # Requires country_sums
}

# Tags requiring special handling (country_sums parameter)
TAGS_REQUIRING_COUNTRY_SUMS = {"Major Access"}

# Tags requiring all ASN data for ranking computation
TAGS_REQUIRING_ALL_ASNS = {"Global Transit Nth-ranked"}