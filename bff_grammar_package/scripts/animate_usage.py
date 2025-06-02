import json
import argparse
import os
import hashlib
import matplotlib.pyplot as plt
import matplotlib.animation as animation
import matplotlib.colors as mcolors

# === Argument parsing ===
parser = argparse.ArgumentParser(description="Animate rule usage over time")
parser.add_argument("--input", type=str, required=True, help="Path to rule usage JSON file")
parser.add_argument("--output", type=str, required=True, help="Path to save animated GIF")
parser.add_argument("--grammar-dir", type=str, required=True, help="Directory containing grammar JSON files")
parser.add_argument("--fps", type=int, default=5, help="Frames per second for animation")
parser.add_argument("--max-rules", type=int, default=50, help="Maximum number of rules to display")
args = parser.parse_args()

print("\U0001F4C2 Loading rule usage data...")
with open(args.input) as f:
    usage_data = json.load(f)

sorted_epochs = sorted(map(int, usage_data.keys()))
print(f"\U0001F4CA Processing epochs: {sorted_epochs[0]} → {sorted_epochs[-1]}")

# === Load latest valid grammar and expand rules ===
def load_latest_valid_grammar(grammar_dir):
    grammar_files = sorted(
        [f for f in os.listdir(grammar_dir) if f.startswith("grammar_") and f.endswith(".json")],
        reverse=True
    )
    for fname in grammar_files:
        try:
            with open(os.path.join(grammar_dir, fname)) as f:
                data = json.load(f)
                if "rules" in data:
                    print(f"📑 Loaded grammar from {fname}")
                    return data["rules"]
        except Exception as e:
            print(f"⚠️ Skipping invalid grammar file {fname}: {e}")
    raise RuntimeError("No valid grammar files found.")

def fully_expand(rhs, grammar):
    result = []
    for tok in rhs:
        if tok in grammar:
            result.extend(fully_expand(grammar[tok], grammar))
        else:
            result.append(tok)
    return result

# === Consistent color generator for rules ===
def get_color_for_rule(rule_label):
    """Generate a consistent RGB color for a rule label."""
    h = hashlib.md5(rule_label.encode()).hexdigest()
    hue = int(h[:2], 16) / 255.0  # Hue between 0 and 1
    return mcolors.hsv_to_rgb((hue, 0.6, 0.85))

# === Prepare grammar rules and label map ===
grammar = load_latest_valid_grammar(args.grammar_dir)
expanded_labels = {
    rule: f"{rule} | {' '.join(fully_expand(rhs, grammar))}"
    for rule, rhs in grammar.items()
}

print("🔎 Expanding rule labels...")
print(f"✅ Expanded {len(expanded_labels)} rules")

# === Per-epoch sorted frames ===
frames = []
for i, epoch in enumerate(sorted_epochs):
    epoch_data = usage_data[str(epoch)]
    sorted_rules = sorted(epoch_data.items(), key=lambda x: -x[1])[:args.max_rules]
    label_counts = [
        (expanded_labels.get(rule, rule), count)
        for rule, count in sorted_rules if count > 0
    ]
    if not label_counts:
        print(f"⚠️ Skipping epoch {epoch} (no rules passed filtering)")
        continue
    frames.append((epoch, label_counts))
    top_rules = ", ".join([f"{label} ({count})" for label, count in label_counts[:3]])
    print(f"📈 Processing epoch {epoch} ({i+1}/{len(sorted_epochs)})\n    Top rules: {top_rules}")

if not frames:
    raise ValueError("No valid frames to animate. Check rule usage or filtering.")

# === Setup figure and axis ===
fig, ax = plt.subplots(figsize=(14, 0.4 * args.max_rules))
labels_init = [label for label, _ in frames[0][1]]
counts_init = [count for _, count in frames[0][1]]
colors_init = [get_color_for_rule(label) for label in labels_init]

ax.barh(range(len(labels_init)), counts_init, color=colors_init)
ax.set_xlabel("Frequency")
ax.set_yticks(range(len(labels_init)))
ax.set_yticklabels(labels_init, fontsize=8)
title = ax.set_title(f"Grammar Rule Usage – Epoch {frames[0][0]}")

# === Determine consistent x-axis limit ===
all_counts = [count for _, label_counts in frames for _, count in label_counts]
max_freq = max(all_counts) * 1.1
ax.set_xlim(0, max_freq)

# === Animation update function ===
def update(frame_idx):
    epoch, label_counts = frames[frame_idx]
    labels = [label for label, _ in label_counts]
    counts = [count for _, count in label_counts]
    colors = [get_color_for_rule(label) for label in labels]

    ax.clear()
    ax.barh(range(len(labels)), counts, color=colors)
    ax.set_xlim(0, max_freq)
    ax.set_xlabel("Frequency")
    ax.set_yticks(range(len(labels)))
    ax.set_yticklabels(labels, fontsize=8)
    ax.set_title(f"Grammar Rule Usage – Epoch {epoch}")
    return ax.patches

print("🎞 Rendering animation...")
ani = animation.FuncAnimation(
    fig, update, frames=len(frames), blit=False, repeat=False
)
ani.save(args.output, writer="pillow", fps=args.fps)
print(f"✅ Animation saved as {args.output}")
