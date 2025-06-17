import pandas as pd
import networkx as nx
import argparse
import os
import math

def csv_to_gexf(df, output_path, log_weight=False):
    G = nx.DiGraph()
    for _, row in df.iterrows():
        source = str(row['source_bin'])
        target = str(row['target_bin'])
        weight = float(row['weight'])

        if log_weight:
            if weight <= 0:
                continue  # skip invalid weights
            weight = math.log(weight)

        G.add_edge(source, target, weight=weight)
    nx.write_gexf(G, output_path)
    print(f"GEXF file written to: {output_path}")

def csv_to_graphml(df, output_path, log_weight=False):
    G = nx.DiGraph()
    for _, row in df.iterrows():
        source = str(row['source_bin'])
        target = str(row['target_bin'])
        weight = float(row['weight'])

        if log_weight:
            if weight <= 0:
                continue  # skip invalid weights
            weight = math.log(weight)

        G.add_edge(source, target, weight=weight)
    nx.write_graphml(G, output_path)
    print(f"GraphML file written to: {output_path}")

# Set up CLI
parser = argparse.ArgumentParser(description="Convert a CSV edge list to GEXF or GraphML (Directed Graph).")
parser.add_argument("input_csv", help="Path to the input CSV file")
parser.add_argument("-f", "--format", choices=["gexf", "graphml"], default="gexf",
                    help="Output format: gexf or graphml (default: gexf)")
parser.add_argument("-o", "--output", help="Output file path (default: input filename with appropriate extension)")
parser.add_argument("--log-weight", action="store_true", help="Apply natural log scale to edge weights")

args = parser.parse_args()

# Determine output filename
input_path = args.input_csv
default_ext = ".gexf" if args.format == "gexf" else ".graphml"
output_path = args.output or os.path.splitext(input_path)[0] + default_ext

# Read CSV
df = pd.read_csv(input_path)

# Convert based on selected format
if args.format == "gexf":
    csv_to_gexf(df, output_path, log_weight=args.log_weight)
else:
    csv_to_graphml(df, output_path, log_weight=args.log_weight)
