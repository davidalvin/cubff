import matplotlib.pyplot as plt
import imageio.v2 as imageio
from collections import Counter
import numpy as np
import io
import os
import json
import csv
import warnings
warnings.filterwarnings("ignore", category=UserWarning, module="matplotlib")


class HistogramTracker:
    def __init__(self, save_path, enabled=True, fps=5, batch_size=50,
                 prefix="soup_4096", flush_interval=16, generate_gifs=True):
        self.save_path = save_path
        self.enabled = enabled
        self.fps = fps
        self.batch_size = batch_size
        self.prefix = prefix
        self.flush_interval = flush_interval
        self.generate_gifs = generate_gifs

        self.frames = []
        self.frame_count = 0
        self.batch_index = 0

        self.medians = []
        self.epochs = []
        self.histogram_data = []
        self._csv_buffer = []
        self._csv_path = os.path.join(self.save_path, "histogram_data.csv")
        self._csv_initialized = False

    def add_frame(self, steps, epoch):
        if not self.enabled or not steps:
            return

        # Median tracking
        self.epochs.append(epoch)
        self.medians.append(np.median(steps))

        # Histogram data
        bin_size = 25
        max_step = 2500
        max_count = 1000

        dist = Counter((s // bin_size) * bin_size for s in steps if s <= max_step)
        bins = sorted(dist)
        counts = [dist[b] for b in bins]

        # Save histogram data
        for b, c in zip(bins, counts):
            row = {
                "epoch": epoch,
                "bin_start": b,
                "bin_end": b + bin_size - 1,
                "count": c
            }
            self.histogram_data.append(row)
            self._csv_buffer.append(row)

        if epoch % self.flush_interval == 0:
            self._flush_csv_buffer()

        # Only generate plots if enabled
        if not self.generate_gifs:
            return

        # Create and store plot frame
        fig, ax = plt.subplots(figsize=(10, 5))
        ax.bar(bins, counts, width=bin_size * 0.9, align='edge', color='skyblue')
        ax.set_title(f"Steps per Program – Epoch {epoch}")
        ax.set_xlabel("Step Count Range")
        ax.set_ylabel("Number of Programs")
        ax.set_xlim(0, max_step)
        ax.set_ylim(0, max_count)

        label_skip = 5
        xticks = bins
        xticklabels = [
            f"{b}-{b + bin_size - 1}" if i % label_skip == 0 else ""
            for i, b in enumerate(bins)
        ]
        ax.set_xticks(xticks)
        ax.set_xticklabels(xticklabels, rotation=45)
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
        self.frame_count += 1

        if self.frame_count >= self.batch_size:
            self._save_batch_gif()
            self.frames.clear()
            self.frame_count = 0
            self.batch_index += 1

    def _flush_csv_buffer(self):
        if not self._csv_buffer:
            return

        write_header = not self._csv_initialized
        with open(self._csv_path, "a", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=["epoch", "bin_start", "bin_end", "count"])
            if write_header:
                writer.writeheader()
                self._csv_initialized = True
            writer.writerows(self._csv_buffer)
        print(f"📤 Flushed {len(self._csv_buffer)} rows to CSV: {self._csv_path}")
        self._csv_buffer.clear()

    def _save_batch_gif(self):
        if not self.frames:
            return
        filename = f"{self.prefix}_batch{self.batch_index:03d}.gif"
        path = os.path.join(self.save_path, filename)
        imageio.mimsave(path, self.frames, fps=self.fps)
        print(f"💾 Saved batch GIF: {path}")

    def save_gif(self, filename="final_batch.gif"):
        if not self.enabled or not self.frames or not self.generate_gifs:
            return
        path = os.path.join(self.save_path, filename)
        imageio.mimsave(path, self.frames, fps=self.fps)
        print(f"\n🧵 Saved final batch GIF: {path}")

    def plot_median_graph(self, filename="median_steps.png"):
        if not self.enabled or not self.medians:
            return
        fig, ax = plt.subplots()
        ax.plot(self.epochs, self.medians, marker='o', linestyle='-')
        ax.set_title("Median Steps Over Time")
        ax.set_xlabel("Epoch")
        ax.set_ylabel("Median Steps")
        ax.grid(True)
        fig.tight_layout()

        path = os.path.join(self.save_path, filename)
        fig.savefig(path)
        plt.close(fig)
        print(f"📈 Saved median step plot: {path}")

        json_path = os.path.join(self.save_path, "median_steps.json")
        with open(json_path, "w") as f:
            json.dump({
                "epochs": self.epochs,
                "medians": self.medians
            }, f, indent=2)
        print(f"📝 Saved median data to JSON: {json_path}")

    def save_histogram_csv(self):
        self._flush_csv_buffer()
        print(f"✅ Final histogram data saved to: {self._csv_path}")
