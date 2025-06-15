import argparse
import glob
import os
import pandas as pd
from collections import Counter


def compute_weights(run_dir: str, context: int):
    edge_files = sorted(glob.glob(os.path.join(run_dir, "edges_*.csv")))
    for path in edge_files:
        epoch = int(os.path.basename(path).split("_")[1].split(".")[0])
        counts = Counter()
        for prev in range(max(0, epoch - context + 1), epoch + 1):
            p = os.path.join(run_dir, f"edges_{prev:04d}.csv")
            if not os.path.exists(p):
                continue
            df = pd.read_csv(p)
            for _, row in df.iterrows():
                counts[(row["source"], row["target"])] += 1
        df_cur = pd.read_csv(path)
        weights = []
        for _, row in df_cur.iterrows():
            w = counts.get((row["source"], row["target"]), 0) / context
            weights.append(w)
        df_cur["weight"] = weights
        out_path = os.path.join(run_dir, f"edges_weighted_{epoch:04d}.csv")
        df_cur.to_csv(out_path, index=False)
        print(f"Saved {out_path}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Compute weighted edges")
    parser.add_argument("run_dir", help="Directory containing edges_*.csv")
    parser.add_argument("--context", type=int, default=10,
                        help="Number of epochs to look back")
    args = parser.parse_args()
    compute_weights(args.run_dir, args.context)