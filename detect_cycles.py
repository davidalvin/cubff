import pandas as pd
import argparse
from igraph import Graph

def build_igraph_from_csv(filename, min_weight=10000):
    df = pd.read_csv(filename)

    if "Weight" not in df.columns:
        raise ValueError("CSV file must include a 'Weight' column.")

    # Filter by minimum edge weight
    df = df[df["Weight"] >= min_weight]

    # Create node map
    all_nodes = pd.unique(df[['Source', 'Target']].values.ravel())
    node_map = {str(node): idx for idx, node in enumerate(all_nodes)}
    reverse_map = {idx: str(node) for node, idx in node_map.items()}

    # Build edges and weights
    edges = [(node_map[str(s)], node_map[str(t)]) for s, t in zip(df['Source'], df['Target'])]
    edge_weights = {(str(s), str(t)): w for s, t, w in zip(df['Source'], df['Target'], df['Weight'])}

    # Build graph
    g = Graph(directed=True)
    g.add_vertices(len(node_map))
    g.vs["name"] = [reverse_map[idx] for idx in range(len(reverse_map))]
    g.add_edges(edges)

    return g, edge_weights

def find_cycles_dfs_limited(g, edge_weights, max_len=4):
    visited_cycles = {}

    def dfs(path, start, depth):
        current = path[-1]
        if depth > max_len:
            return
        for neighbor in g.successors(current):
            if neighbor == start and len(path) >= 1:
                cycle = tuple(g.vs[idx]["name"] for idx in path)
                weights = [
                    edge_weights.get((cycle[i], cycle[(i + 1) % len(cycle)]), 0)
                    for i in range(len(cycle))
                ]
                visited_cycles[cycle] = min(weights)
            elif neighbor not in path:
                dfs(path + [neighbor], start, depth + 1)

    for v in range(len(g.vs)):
        dfs([v], v, 1)

    return visited_cycles

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Detect cycles in a weighted directed graph CSV.")
    parser.add_argument("filename", help="Path to the input CSV file")
    parser.add_argument("--min-weight", type=int, default=10000, help="Minimum edge weight to include")
    parser.add_argument("--max-len", type=int, default=4, help="Maximum length of cycles to detect")
    parser.add_argument("--top", type=int, default=50, help="Number of top cycles to show")
    args = parser.parse_args()

    print(f"Loading graph from {args.filename}...")
    graph, edge_weights = build_igraph_from_csv(args.filename, min_weight=args.min_weight)

    print(f"Finding cycles (length ≤ {args.max_len})...")
    cycle_dict = find_cycles_dfs_limited(graph, edge_weights, max_len=args.max_len)

    if not cycle_dict:
        print("No cycles found.")
    else:
        sorted_cycles = sorted(cycle_dict.items(), key=lambda x: x[1], reverse=True)
        print(f"\nTop {min(args.top, len(sorted_cycles))} cycles (sorted by minimum edge weight):\n")
        for i, (cycle, weight) in enumerate(sorted_cycles[:args.top], 1):
            print(f"{i:2}: {cycle}  (min edge weight: {weight})")
