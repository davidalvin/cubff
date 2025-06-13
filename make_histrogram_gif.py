import pandas as pd
import matplotlib.pyplot as plt
import imageio.v2 as imageio
import os
import io
from collections import defaultdict

# === Config ===
CSV_PATH = "./runs/20250612-COUNT-STEPS-CSV-4096E-128x1024P-0SEED/histogram_data.csv"
OUTPUT_GIF = "./runs/20250612-COUNT-STEPS-CSV-4096E-128x1024P-0SEED/histogram_from_csv.gif"
FPS = 5
MAX_STEP = 2500
MAX_COUNT = 50000
BIN_SIZE = 25
EPOCH_INTERVAL = 16
XTICK_SKIP = 5

print("🔍 Loading histogram data from CSV...")
if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"❌ CSV file not found: {CSV_PATH}")

# === Load CSV ===
df = pd.read_csv(CSV_PATH)
print(f"✅ Loaded {len(df)} rows from {CSV_PATH}")

# === Group histogram by epoch ===
print("📊 Grouping histogram data by epoch...")
grouped = defaultdict(list)
for _, row in df.iterrows():
    grouped[int(row["epoch"])].append((int(row["bin_start"]), int(row["count"])))

epochs = sorted(grouped.keys())
print(f"📈 Found data for {len(epochs)} epochs")

# === Prepare bin edges and fixed ticks ===
bin_edges = list(range(0, MAX_STEP + BIN_SIZE, BIN_SIZE))
xticks = bin_edges
xticklabels = [f"{b}-{b + BIN_SIZE - 1}" if i % XTICK_SKIP == 0 else "" for i, b in enumerate(bin_edges)]
yticks = list(range(0, MAX_COUNT + 1, 5000))

# === Generate frames ===
print("🎞 Rendering frames...")
frames = []

for i, epoch in enumerate(epochs[::EPOCH_INTERVAL]):
    print(f"  ➤ Epoch {epoch} ({i+1}/{len(epochs[::EPOCH_INTERVAL])})")
    bins_counts = dict(grouped[epoch])
    counts = [bins_counts.get(b, 0) for b in bin_edges]

    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(bin_edges, counts, width=BIN_SIZE * 0.9, align='edge', color='skyblue')
    ax.set_title(f"Steps per Program – Epoch {epoch}", fontsize=14)
    ax.set_xlabel("Step Count Range", fontsize=12)
    ax.set_ylabel("Number of Programs", fontsize=12)

    # Lock axis limits and ticks
    ax.set_xlim(0, MAX_STEP)
    ax.set_ylim(0, MAX_COUNT)
    ax.set_xticks(xticks)
    ax.set_xticklabels(xticklabels, rotation=45, fontsize=8)
    ax.set_yticks(yticks)
    ax.set_yticklabels([str(y) for y in yticks], fontsize=10)
    ax.grid(True, axis='y', linestyle='--', alpha=0.6)

    # Optional annotations
    for x, y in zip(bin_edges, counts):
        if y > 25:
            ax.text(x + BIN_SIZE / 2, y + 200, str(y), ha='center', va='bottom', fontsize=6)

    # Remove tight_layout, manually control spacing
    plt.subplots_adjust(bottom=0.2, left=0.1, right=0.95, top=0.85)

    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    frames.append(imageio.imread(buf))

# === Save GIF ===
print("💾 Saving animated GIF...")
imageio.mimsave(OUTPUT_GIF, frames, fps=FPS)
print(f"✅ Saved to: {OUTPUT_GIF}")
