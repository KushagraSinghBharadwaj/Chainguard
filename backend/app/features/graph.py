"""Transaction graph signals. Pure functions over already-fetched transactions: no network.

The graph only contains what was fetched, so "no listed address found" means "none within the
searched graph", never "no link exists". All three signals are descriptive until thresholds
are measured on real data.
"""

from collections.abc import Iterable
from dataclasses import dataclass

import networkx as nx

from app.providers.base import Transaction

PEEL_SHARE = 0.8
MAX_CYCLE_LEN = 4
MAX_PEEL_HOPS = 10


@dataclass(frozen=True)
class GraphSignals:
    node_count: int
    edge_count: int
    nearest_listed_address: str | None
    hop_distance: int | None  # None: none found within searched_hops
    searched_hops: int
    cycle_count: int  # distinct first hops whose value returns to the subject
    shortest_cycle: int | None
    peel_chain_length: int


def build_graph(txs: Iterable[Transaction]) -> nx.DiGraph:
    g = nx.DiGraph()
    for t in txs:
        if t.is_error or t.to_address is None:
            continue
        a, b = t.from_address.lower(), t.to_address.lower()
        if a == b:
            continue
        if g.has_edge(a, b):
            g[a][b]["value_wei"] += t.value_wei
            g[a][b]["count"] += 1
        else:
            g.add_edge(a, b, value_wei=t.value_wei, count=1)
    return g


def nearest_listed(g: nx.DiGraph, subject: str, listed: set[str], max_hops: int) -> tuple[str, int] | None:
    if subject not in g:
        return None
    dist = nx.single_source_shortest_path_length(g.to_undirected(as_view=True), subject, cutoff=max_hops)
    found = sorted((d, a) for a, d in dist.items() if a in listed and a != subject)
    if not found:
        return None
    d, a = found[0]
    return a, d


def cycles_through(g: nx.DiGraph, subject: str, max_len: int = MAX_CYCLE_LEN) -> tuple[int, int | None]:
    if subject not in g:
        return 0, None
    count, shortest = 0, None
    for n in g.successors(subject):
        dist = nx.single_source_shortest_path_length(g, n, cutoff=max_len - 1)
        if subject in dist:
            count += 1
            length = dist[subject] + 1
            shortest = length if shortest is None else min(shortest, length)
    return count, shortest


def peel_chain_length(
    g: nx.DiGraph, subject: str, share: float = PEEL_SHARE, max_hops: int = MAX_PEEL_HOPS
) -> int:
    if subject not in g:
        return 0
    length, node, seen = 0, subject, {subject}
    while length < max_hops:
        outs = [(d["value_wei"], n) for n, d in g[node].items()]
        total = sum(v for v, _ in outs)
        if len(outs) < 2 or total == 0:
            break
        top_value, top_node = max(outs)
        if top_value / total < share or top_node in seen:
            break
        length += 1
        seen.add(top_node)
        node = top_node
    return length


def compute_graph_signals(
    txs: Iterable[Transaction], subject: str, listed: set[str], max_hops: int
) -> GraphSignals:
    subject = subject.lower()
    g = build_graph(txs)
    near = nearest_listed(g, subject, {a.lower() for a in listed}, max_hops)
    count, shortest = cycles_through(g, subject)
    return GraphSignals(
        node_count=g.number_of_nodes(),
        edge_count=g.number_of_edges(),
        nearest_listed_address=near[0] if near else None,
        hop_distance=near[1] if near else None,
        searched_hops=max_hops,
        cycle_count=count,
        shortest_cycle=shortest,
        peel_chain_length=peel_chain_length(g, subject),
    )
