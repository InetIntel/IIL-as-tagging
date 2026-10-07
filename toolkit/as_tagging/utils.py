"""
AS Tagging utility functions.

Provides ASN format normalization to accommodate different input formats
(1234, "1234", "AS1234") across all public API entry points.
"""

from typing import Any, List, Optional, Set, Union


def normalize_asn_input(asn: Any) -> str:
    """
    Convert ASN to canonical string format (numeric only, no 'AS' prefix).

    Handles: 1234, "1234", "AS1234", "as1234", etc. -> "1234"

    Args:
        asn: ASN in any supported format (int, str with or without "AS" prefix).

    Returns:
        Canonical string, e.g. "1234".

    Raises:
        ValueError: If asn cannot be parsed.
    """
    if asn is None:
        raise ValueError("ASN cannot be None")
    s = str(asn).strip().upper()
    if s.startswith("AS"):
        s = s[2:].strip()
    if not s or not s.replace("-", "").isdigit():
        raise ValueError(f"Invalid ASN format: {repr(asn)}")
    return s


def normalize_asn_list(
    asns: Optional[Union[Any, List[Any]]],
    *,
    allow_none: bool = False,
) -> List[str]:
    """
    Normalize ASN(s) to a list of canonical strings.

    Args:
        asns: Single ASN or list of ASNs in any supported format.
        allow_none: If True and asns is None, return []. If False, None is invalid.

    Returns:
        List of canonical ASN strings.
    """
    if asns is None:
        if allow_none:
            return []
        raise ValueError("ASNs cannot be None")
    if isinstance(asns, (str, int)) or not isinstance(asns, (list, tuple)):
        asns = [asns]
    return [normalize_asn_input(a) for a in asns]


def resolve_asn_to_key(canonical: str, keys: Set[Any]) -> Optional[Any]:
    """
    Find the actual key in a set that corresponds to the canonical ASN.

    Tries: canonical, int(canonical), "AS"+canonical.

    Args:
        canonical: Canonical ASN string (e.g. "1234").
        keys: Set of keys (e.g. atomic_tags.keys()).

    Returns:
        The matching key from keys, or None if not found.
    """
    if canonical in keys:
        return canonical
    try:
        k = int(canonical)
        if k in keys:
            return k
    except (ValueError, TypeError):
        pass
    prefixed = f"AS{canonical}"
    if prefixed in keys:
        return prefixed
    return None


def build_asn_key_map(keys: Set[Any]) -> dict:
    """
    Build mapping from canonical ASN string to actual key format used in data.

    Args:
        keys: Set of ASN keys (e.g. from atomic_tags.keys()).

    Returns:
        Dict mapping canonical str -> actual key.
    """
    result = {}
    for k in keys:
        try:
            canon = normalize_asn_input(k)
            result[canon] = k
        except ValueError:
            continue
    return result
