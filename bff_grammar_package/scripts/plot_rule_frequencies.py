import json
import argparse
import os
import plotly.express as px
import pandas as pd

# === Argument parsing ===
parser = argparse.ArgumentParser(description="Interactive line chart of rule frequency over time")
parser.add_argument("--input", type=str, required=True, help="Path to rule usage JSON file")
parser.add_argument("--output", type=str, required=True, help="Path to save HTML plot")
parser.add_argument("--grammar-dir", type=str, required=True, help="Directory containing grammar JSON files")
parser.add_argument("--max-rules", type=int, default=50, help="Maximum number of rules to plot")
parser.add_argument("--log-scale", action="store_true", help="Use log scale for Y-axis")
args = parser.parse_args()

# === Load data ===
with open(args.input) as f:
    usage_data = json.load(f)
epochs = sorted(map(int, usage_data.keys()))

# === Load grammar ===
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
                    print(f"📁 Loaded grammar from {fname}")
                    return data["rules"]
        except Exception as e:
            print(f"⚠️ Skipping {fname}: {e}")
    raise RuntimeError("No valid grammar file found")

grammar = load_latest_valid_grammar(args.grammar_dir)

def fully_expand(rhs, grammar):
    result = []
    for tok in rhs:
        if tok in grammar:
            result.extend(fully_expand(grammar[tok], grammar))
        else:
            result.append(tok)
    return result

# === Determine top rules ===
total_counts = {}
for epoch in epochs:
    for rule, count in usage_data[str(epoch)].items():
        total_counts[rule] = total_counts.get(rule, 0) + count

top_rules = sorted(total_counts.items(), key=lambda x: -x[1])[:args.max_rules]
top_rule_names = [r for r, _ in top_rules]

# === Build data frame ===
records = []
for rule in top_rule_names:
    label = f"{rule} | {' '.join(fully_expand(grammar[rule], grammar))}" if rule in grammar else rule
    for epoch in epochs:
        freq = usage_data[str(epoch)].get(rule, 0)
        records.append({"epoch": epoch, "frequency": freq, "rule": label})

df = pd.DataFrame(records)

# === Plot ===
fig = px.line(df, x="epoch", y="frequency", color="rule", hover_name="rule",
              title=f"Rule Frequency Over Time (Top {args.max_rules})")

fig.update_layout(
    yaxis=dict(
        title="Frequency",
        type="log" if args.log_scale else "linear"
    ),
    width=1000,
    height=600,
    legend_title_text="Rule",
    hovermode="closest"
)

fig.write_html(args.output)
print(f"✅ Line chart saved as {args.output}")
