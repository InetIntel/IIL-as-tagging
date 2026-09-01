"""
Graph building utilities for graph-based ML models.

Builds DGL heterogeneous graphs from CAIDA AS-relationship features
in the snapshot, and provides propagation matrix construction for APPNP.
"""

import numpy as np
from typing import Dict, Tuple, Set, Any, Optional


# Feature keys for AS relationships
PROV_KEY = "caida-asrel_provider_list"
PEER_KEY = "caida-asrel_peer_list"
CUST_KEY = "caida-asrel_customer_list"
PDB_KEY = "pdb_ix_peer"
TR_KEY = "tr_ix_peer"

# Minimum set of keys needed for graph construction
REQUIRED_TOPOLOGY_KEYS = {PROV_KEY, CUST_KEY}


def has_topology_features(snapshot_dict: Dict[str, Dict[str, Any]]) -> bool:
    """
    Check if the snapshot has AS-relationship features needed for graph models.
    
    Args:
        snapshot_dict: {asn: {feature: value}}
        
    Returns:
        True if topology features are available
    """
    if not snapshot_dict:
        return False
    
    # Check a sample of ASNs
    sample_asns = list(snapshot_dict.keys())[:20]
    for asn in sample_asns:
        feats = snapshot_dict[asn]
        if any(key in feats for key in REQUIRED_TOPOLOGY_KEYS):
            return True
    
    return False


def _to_int_set(values, valid_asns: Set[int]) -> list:
    """Convert a list of ASN values to valid integer ASNs."""
    result = []
    if not values:
        return result
    for x in values:
        try:
            xi = int(x)
            if xi in valid_asns:
                result.append(xi)
        except (ValueError, TypeError):
            continue
    return result


def _parse_list_value(val) -> list:
    """Parse a list value that may be stored as JSON string."""
    import json
    if val is None:
        return []
    if isinstance(val, list):
        return val
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            if isinstance(parsed, list):
                return parsed
        except (json.JSONDecodeError, TypeError):
            pass
    return []


def build_dgl_graph(
    snapshot_dict: Dict[str, Dict[str, Any]],
    collapse_peering: bool = False,
    add_self_loops: bool = True,
) -> Tuple[Any, Dict[int, int]]:
    """
    Build a DGL heterogeneous graph from AS-relationship features.
    
    Creates edge types for provider-to-customer (p2c), peering (p2p),
    and optionally IXP peering relationships.
    
    Args:
        snapshot_dict: {asn: {feature: value}}
        collapse_peering: If True, merge all peering types into one edge type
        add_self_loops: If True, add self-loop edges
        
    Returns:
        (dgl.DGLHeteroGraph, asn2id mapping)
    """
    import torch
    import dgl
    
    p2c = set()
    p2p_caida = set()
    p2p_tr = set()
    all_asns = set(int(a) for a in snapshot_dict.keys())
    
    for a_str, rec in snapshot_dict.items():
        a = int(a_str)
        provs = _to_int_set(_parse_list_value(rec.get(PROV_KEY, [])), all_asns)
        peers = _to_int_set(_parse_list_value(rec.get(PEER_KEY, [])), all_asns)
        custs = _to_int_set(_parse_list_value(rec.get(CUST_KEY, [])), all_asns)
        trps = _to_int_set(_parse_list_value(rec.get(TR_KEY, [])), all_asns)
        
        for p in provs:
            p2c.add((p, a))
            all_asns.add(p)
        for c in custs:
            p2c.add((a, c))
            all_asns.add(c)
        for b in peers:
            p2p_caida.add((a, b))
            p2p_caida.add((b, a))
            all_asns.add(b)
        for b in trps:
            p2p_tr.add((a, b))
            p2p_tr.add((b, a))
            all_asns.add(b)
    
    asn_list = sorted(all_asns)
    asn2id = {asn: i for i, asn in enumerate(asn_list)}
    
    def _idx(pairs):
        if not pairs:
            return torch.empty(0, dtype=torch.long), torch.empty(0, dtype=torch.long)
        s = torch.tensor([asn2id[u] for (u, v) in pairs], dtype=torch.long)
        t = torch.tensor([asn2id[v] for (u, v) in pairs], dtype=torch.long)
        return s, t
    
    data_dict = {}
    if p2c:
        s, t = _idx(sorted(p2c))
        data_dict[('asn', 'p2c', 'asn')] = (s, t)
        data_dict[('asn', 'p2c_rev', 'asn')] = (t, s)
    
    if collapse_peering:
        union_p2p = p2p_caida | p2p_tr
        if union_p2p:
            data_dict[('asn', 'p2p', 'asn')] = _idx(sorted(union_p2p))
    else:
        if p2p_caida:
            data_dict[('asn', 'p2p_caida', 'asn')] = _idx(sorted(p2p_caida))
        if p2p_tr:
            data_dict[('asn', 'p2p_tr', 'asn')] = _idx(sorted(p2p_tr))
    
    if add_self_loops:
        n = len(asn_list)
        ids = torch.arange(n)
        data_dict[('asn', 'self', 'asn')] = (ids, ids)
    
    g = dgl.heterograph(data_dict, num_nodes_dict={'asn': len(asn_list)})
    g.ndata['asn'] = torch.tensor(asn_list, dtype=torch.long)
    
    return g, asn2id


def build_propagation_matrix(hg) -> Any:
    """
    Build a row-normalized sparse propagation matrix from a homogeneous graph.
    
    Used by the APPNP model for label propagation. Makes the graph
    undirected, adds self-loops, and row-normalizes.
    
    Args:
        hg: DGL homogeneous graph (output of dgl.to_homogeneous)
        
    Returns:
        Sparse torch tensor P (row-normalized adjacency)
    """
    import torch
    import dgl
    
    g = hg
    try:
        g = dgl.to_bidirected(g, copy_ndata=False, copy_edata=False)
    except TypeError:
        g = dgl.to_bidirected(g)
    
    g = dgl.add_self_loop(g)
    
    deg = g.out_degrees().float().clamp(min=1)
    src, dst = g.edges()
    N = g.num_nodes()
    w = 1.0 / deg[src]
    
    P = torch.sparse_coo_tensor(
        torch.stack([dst, src], dim=0),
        w,
        size=(N, N),
        device=g.device,
        dtype=torch.float32,
    ).coalesce()
    
    return P


def attach_node_features(
    g,
    asn2id: Dict[int, int],
    feat_dict: Dict[int, list],
    key: str = "x",
):
    """
    Attach feature vectors to graph nodes.
    
    Args:
        g: DGL graph
        asn2id: ASN to node-id mapping
        feat_dict: {asn_int: feature_vector}
        key: Node data key name
    """
    import torch
    
    dim = len(next(iter(feat_dict.values())))
    X = torch.zeros((g.num_nodes('asn'), dim), dtype=torch.float32)
    for asn, vec in feat_dict.items():
        i = asn2id.get(int(asn))
        if i is not None:
            X[i] = torch.tensor(vec, dtype=torch.float32)
    g.nodes['asn'].data[key] = X
    return g
