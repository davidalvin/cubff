import pandas as pd
import matplotlib.pyplot as plt
import imageio.v2 as imageio
import os
import io
from collections import defaultdict

# === Config ===
CSV_PATH = "./runs/20250612-COUNT-STEPS-CSV-4096E-128x1024P-0SEED/histogram_data.csv"
OUTPUT_DIR = "./runs/20250612-COUNT-STEPS-CSV-4096E-128x1024P-0SEED"
GIF_PREFIX = "histogram_epoch"
FPS = 5
MAX_STEP = 2500
MAX_COUNT = 50000
BIN_SIZE = 25
EPOCH_INTERVAL = 256
XTICK_SKIP = 5

# === Load CSV ===
print("🔍 Loading histogram data from CSV...")
if not os.path.exists(CSV_PATH):
    raise FileNotFoundError(f"❌ CSV file not found: {CSV_PATH}")
df = pd.read_csv(CSV_PATH)
print(f"✅ Loaded {len(df)} rows")

# === Group histogram data by epoch ===
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

# === Create GIFs in batches ===
print(f"🎞 Rendering and saving GIFs every {EPOCH_INTERVAL} epochs...")
frames = []
batch_index = 0

for i, epoch in enumerate(epochs):
    if epoch % EPOCH_INTERVAL == 0 and epoch != 0:
        # Save interim GIF
        gif_path = os.path.join(OUTPUT_DIR, f"{GIF_PREFIX}_batch{batch_index:03}.gif")
        imageio.mimsave(gif_path, frames, fps=FPS)
        print(f"💾 Saved batch GIF: {gif_path}")
        frames.clear()
        batch_index += 1

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

    for x, y in zip(bin_edges, counts):
        if y > 25:
            ax.text(x + BIN_SIZE / 2, y + 200, str(y), ha='center', va='bottom', fontsize=6)

    plt.subplots_adjust(bottom=0.2, left=0.1, right=0.95, top=0.85)
    buf = io.BytesIO()
    plt.savefig(buf, format="png", dpi=100)
    plt.close(fig)
    buf.seek(0)
    frames.append(imageio.imread(buf))

# Save final batch
if frames:
    gif_path = os.path.join(OUTPUT_DIR, f"{GIF_PREFIX}_batch{batch_index:03}.gif")
    imageio.mimsave(gif_path, frames, fps=FPS)
    print(f"💾 Saved final batch GIF: {gif_path}")

print("✅ All batches complete! You can now stitch with `gifsicle --loop *.gif > full.gif`")
