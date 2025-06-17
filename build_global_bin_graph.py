import os
import glob
import csv
import argparse
from collections import defaultdict

def build_global_bin_graph(run_dir, output_file="global_bin_graph.csv"):
    bin_edge_counts = defaultdict(int)

    # Read all bin_edges_*.csv files
    for path in glob.glob(os.path.join(run_dir, "bin_edges_*.csv")):
        with open(path) as f:
            reader = csv.DictReader(f)
            for row in reader:
                src_bin = int(row["source_bin"])
                tgt_bin = int(row["target_bin"])
                count = int(row["count"])
                bin_edge_counts[(src_bin, tgt_bin)] += count

    # Write the global bin-level graph
    output_path = os.path.join(run_dir, output_file)
    with open(output_path, "w", newline="") as out:
        writer = csv.writer(out)
        writer.writerow(["source_bin", "target_bin", "weight"])
        for (src, tgt), weight in sorted(bin_edge_counts.items()):
            writer.writerow([src, tgt, weight])

    print(f"[✓] Global bin graph saved to: {output_path}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build a global bin-level lineage graph.")
    parser.add_argument("run_dir", type=str, help="Directory containing bin_edges_*.csv files")
    parser.add_argument("--output", type=str, default="global_bin_graph.csv", help="Output filename")
    args = parser.parse_args()

    build_global_bin_graph(args.run_dir, args.output)
