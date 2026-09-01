"""
Preset composite tag definitions for AS Tagging toolkit.

This module contains lambda expressions for all preset composite tags
described in the AS Tagging paper. Each function implements a specific
tag logic that can be applied to AS feature snapshots.

Tag Categories:
1. Basic network properties (Anycast, Tranco 10k Host, IPv6 Only, No Eyeball)
2. Transit behavior (No Transit, Sibling Transit, Public Transit)
3. Global transit ranking (requires Borda count aggregation)
4. Geolocation-based (Country Code, Any Presence, Domestic, Major Access)

NOTE: Feature names must match the actual column names in the snapshot parquet files.
NOTE: Dict/list columns may be stored as JSON strings - use _safe_get_dict helper.
NOTE: List columns may mix ASN types (int vs "AS123" vs "123") across sources; use
      _asn_set_normalized for set logic.
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
    """
    v4 = tags.get("LACeS-anycast_v4_cnt", 0) or 0
    v6 = tags.get("LACeS-anycast_v6_cnt", 0) or 0
    return v4 > 0 or v6 > 0


def tranco_10k_host(tags):
    """
    Tag: Tranco 10k Host
    
    Returns True if the AS hosts any domains in the Tranco top domains list.
    """
    return (tags.get("openintel-tranco_topdomain_cnt", 0) or 0) > 0


def ipv6_only(tags):
    """
    Tag: IPv6 Only
    
    Returns True if the AS originates IPv6 prefixes but no IPv4 prefixes.
    """
    v6_cnt = tags.get("pfx2as_/64_cnt", 0) or 0
    v4_cnt = tags.get("pfx2as_/24_cnt", 0) or 0
    return v6_cnt > 0 and v4_cnt == 0


def no_eyeball(tags):
    """
    Tag: No Eyeball
    
    Returns True if the AS has no inferred eyeballs.
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
    """
    return (tags.get("caida-asrel_customer_cnt", 0) or 0) == 0


def sibling_transit(tags):
    """
    Tag: Sibling Transit
    
    Returns True if the AS only provides transit to sibling ASes 
    (owned by the same organization).
    Logic: All direct customers are siblings.
    """
    customers = _safe_get_list(tags, "caida-asrel_customer_list", [])
    siblings = _safe_get_list(tags, "inetintel-as2org_sibling_list", [])

    customer_set = _asn_set_normalized(customers)
    sibling_set = _asn_set_normalized(siblings)

    if not customer_set:
        return False  # No customers (or none parseable) means no transit at all

    return customer_set.issubset(sibling_set)


def public_transit(tags):
    """
    Tag: Public Transit
    
    Returns True if the AS provides IP transit to non-sibling ASes.
    Logic: Some direct customers are not siblings.
    """
    customers = _safe_get_list(tags, "caida-asrel_customer_list", [])
    siblings = _safe_get_list(tags, "inetintel-as2org_sibling_list", [])

    customer_set = _asn_set_normalized(customers)
    sibling_set = _asn_set_normalized(siblings)

    # Has at least one customer that is not a sibling
    return len(customer_set - sibling_set) > 0


# =============================================================================
# Geolocation Tags (parameterized by country)
# =============================================================================

def any_presence(tags):
    """
    Tag: Any Presence
    
    Returns a list of country codes where the AS has any IP presence
    (either IPv4 or IPv6 addresses geolocated to that country).
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
    "Any Presence": any_presence,
    "Domestic": domestic,
    "Major Access": major_access,  # Requires country_sums
}

# Tags requiring special handling (country_sums parameter)
TAGS_REQUIRING_COUNTRY_SUMS = {"Major Access"}

# Tags requiring all ASN data for ranking computation
TAGS_REQUIRING_ALL_ASNS = {"Global Transit Nth-ranked"}