import json
import argparse
import matplotlib.pyplot as plt
import matplotlib.animation as animation

# === Load rule usage data ===
parser = argparse.ArgumentParser(description="Animate rule usage over time")
parser.add_argument("--input", type=str, default="bff_grammar_package/output/rule_usage_over_time.json", help="Path to rule usage JSON file")
parser.add_argument("--output", type=str, default="bff_grammar_package/output/rule_usage_over_time.gif", help="Path to save animated GIF")
parser.add_argument("--fps", type=int, default=5, help="Frames per second for animation")
args = parser.parse_args()

print("\U0001F4C2 Loading rule usage data...")
with open(args.input) as f:
    data = json.load(f)

print("\U0001F4CA Preparing list of all grammar rules...")
all_rules = sorted({rule for epoch_data in data for rule in epoch_data})
print(f"✅ Found {len(all_rules)} unique grammar rules")

print("\U0001F4C8 Building per-epoch rule usage matrix...")
frame_counts = []
for i, epoch_data in enumerate(data):
    counts = [epoch_data.get(rule, 0) for rule in all_rules]
    frame_counts.append(counts)
    if i % 10 == 0 or i == len(data) - 1:
        print(f"  Processed epoch {i + 1}/{len(data)}")

print("\U0001F3A8 Setting up animation canvas...")
fig, ax = plt.subplots(figsize=(12, 6))
bar_container = ax.bar(all_rules, frame_counts[0])
title = ax.set_title("Grammar Rule Usage – Epoch 0")
ax.set_ylim(0, max(max(fc) for fc in frame_counts) * 1.1)
ax.set_ylabel("Usage Count")
ax.set_xlabel("Grammar Rules")
plt.xticks(rotation=90)

def update(frame_idx):
    counts = frame_counts[frame_idx]
    for rect, h in zip(bar_container, counts):
        rect.set_height(h)
    title.set_text(f"Grammar Rule Usage – Epoch {frame_idx + 1}")
    return bar_container

print("\U0001F39E️ Rendering animation...")
ani = animation.FuncAnimation(
    fig, update, frames=len(frame_counts), blit=False, repeat=False
)
ani.save(args.output, writer="pillow", fps=args.fps)
print(f"✅ Animation saved as {args.output}")
