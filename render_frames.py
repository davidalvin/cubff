import argparse
import os
import glob
import pandas as pd
import matplotlib.pyplot as plt


def render(run_dir: str, frames_dir: str | None = None):
    if frames_dir is None:
        frames_dir = os.path.join(run_dir, "frames")
    os.makedirs(frames_dir, exist_ok=True)
    node_files = sorted(glob.glob(os.path.join(run_dir, "nodes_*.csv")))
    prev_nodes = None
    for nf in node_files:
        epoch = int(os.path.basename(nf).split("_")[1].split(".")[0])
        nodes = pd.read_csv(nf)
        edges_path = os.path.join(run_dir, f"edges_weighted_{epoch:04d}.csv")
        edges = pd.read_csv(edges_path) if os.path.exists(edges_path) else None

        fig, ax = plt.subplots(figsize=(10, 6))
        ax.scatter(nodes["epoch"], nodes["exec_time"], s=2, color="tab:blue")

        if edges is not None and prev_nodes is not None:
            for _, row in edges.iterrows():
                src = row["source"]
                tgt = row["target"]
                w = row["weight"]
                if src in prev_nodes.index and tgt in nodes.index:
                    y1 = prev_nodes.loc[src, "exec_time"]
                    y2 = nodes.loc[tgt, "exec_time"]
                    ax.plot([epoch - 1, epoch], [y1, y2], color="gray", alpha=min(1.0, w), linewidth=0.5)

        ax.set_xlabel("Epoch")
        ax.set_ylabel("Execution time")
        ax.set_title(f"Epoch {epoch}")
        fig.tight_layout()
        out_path = os.path.join(frames_dir, f"frame_{epoch:04d}.png")
        fig.savefig(out_path)
        plt.close(fig)
        print(f"Saved {out_path}")

        prev_nodes = nodes.set_index("id")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Render frames from edge/node csvs")
    parser.add_argument("run_dir", help="Directory with nodes_*.csv and edges_weighted_*.csv")
    parser.add_argument("--frames-dir", default=None, help="Output directory for PNG frames")
    args = parser.parse_args()
    render(args.run_dir, args.frames_dir)
