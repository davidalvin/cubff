# histogram_tracker.py

import matplotlib.pyplot as plt
import matplotlib.ticker as ticker
import imageio.v2 as imageio
from collections import Counter
import io
import os

class HistogramTracker:
    def __init__(self, save_path, enabled=True, fps=5):
        self.frames = []
        self.save_path = save_path
        self.enabled = enabled
        self.fps = fps

    def add_frame(self, steps, epoch):
        if not self.enabled or not steps:
            return

        bin_size = 25
        max_step = 2000
        max_count = 1000

        # Group steps into bins of size 25
        dist = Counter((s // bin_size) * bin_size for s in steps if s <= max_step)
        bins = sorted(dist)
        counts = [dist[b] for b in bins]

        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(bins, counts, width=bin_size * 0.9, align='edge', color='skyblue')

        ax.set_title(f"Steps per Program – Epoch {epoch}")
        ax.set_xlabel("Step Count Range")
        ax.set_ylabel("Number of Programs")
        ax.set_xlim(0, max_step)
        ax.set_ylim(0, max_count)

        # Label x-axis with ranges like "0–24"
        ax.set_xticks(bins)
        ax.set_xticklabels([f"{b}-{b + bin_size - 1}" for b in bins], rotation=45)

        ax.grid(True, axis='y', linestyle='--', alpha=0.6)

        for x, y in zip(bins, counts):
            if y > 25:
                ax.text(x + bin_size / 2, y + 5, str(y), ha='center', va='bottom', fontsize=8)

        fig.tight_layout()

        buf = io.BytesIO()
        plt.savefig(buf, format='png')
        plt.close(fig)
        buf.seek(0)
        self.frames.append(imageio.imread(buf))

    def save_gif(self, filename="step_histograms.gif"):
        if not self.enabled or not self.frames:
            return
        out_path = os.path.join(self.save_path, filename)
        imageio.mimsave(out_path, self.frames, fps=self.fps)
        print(f"\nSaved animated histogram to {out_path}")
