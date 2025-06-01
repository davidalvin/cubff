# run_pipeline.py

import argparse
import subprocess
import os
import sys
import json

CHECKPOINT_FILE = "bff_grammar_package/output/pipeline_checkpoint.json"
COMMAND_FILE = "bff_grammar_package/output/pipeline_command.sh"

def save_checkpoint(state):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(state, f, indent=2)

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}

def save_command():
    cmd = " ".join(sys.argv)
    with open(COMMAND_FILE, "w") as f:
        f.write(cmd + "\n")

def run_pipeline(args):
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.grammar_dir, exist_ok=True)
    save_command()
    checkpoint = load_checkpoint()

    # Grammar: every 256 epochs
    grammar_epochs = list(range(args.grammar_start, args.grammar_stop, args.grammar_step))
    missing_epochs = [
        e for e in grammar_epochs
        if not os.path.exists(os.path.join(args.grammar_dir, f"grammar_{e:04}.json"))
    ]

    if missing_epochs:
        print(f"🚀 Step 1: Building grammar for missing epochs: {missing_epochs}")
        subprocess.run([
            "python", "-m", "bff_grammar_package.scripts.build_grammar",
            "--start", str(min(missing_epochs)),
            "--stop", str(max(missing_epochs) + args.grammar_step - 1),
            "--step", str(args.grammar_step),
            "--minfreq", str(args.minfreq),
            "--minlen", str(args.minlen),
            "--maxlen", str(args.maxlen),
            "--input-dir", args.soup_dir,
            "--output-dir", args.grammar_dir
        ])
    else:
        print("✅ All grammar files already exist. Skipping grammar build.")
    checkpoint["grammar_built"] = True
    save_checkpoint(checkpoint)

    # Rewrite/count: every 32 epochs
    usage_epochs = list(range(args.usage_start, args.usage_stop + 1, 32))
    print(f"\n📊 Step 2: Rewriting usage for epochs: {usage_epochs[0]} to {usage_epochs[-1]} ({len(usage_epochs)} total)")
    if not checkpoint.get("rewrite_done"):
        subprocess.run([
            "python", "-m", "bff_grammar_package.scripts.rewrite_and_count",
            "--start", str(args.usage_start),
            "--stop", str(args.usage_stop),
            "--max-programs", str(args.max_programs),
            "--grammar-dir", args.grammar_dir,
            "--grammar-epochs", *map(str, grammar_epochs),
            "--soup-dir", args.soup_dir,
            "--output-file", os.path.join(args.output, "rule_usage_over_time.json")
        ])
        checkpoint["rewrite_done"] = True
        save_checkpoint(checkpoint)
    else:
        print("✅ Skipping rewrite/count (already completed)")

    # Animation
    print("\n🎞 Step 3: Generating animated GIF of rule usage...")
    if not checkpoint.get("animation_done"):
        result = subprocess.run([
            "python", "-m", "bff_grammar_package.scripts.animate_usage",
            "--input", os.path.join(args.output, "rule_usage_over_time.json"),
            "--output", os.path.join(args.output, "rule_usage_over_time.gif"),
            "--fps", str(args.fps)
        ])

        if result.returncode == 0:
            checkpoint["animation_done"] = True
            save_checkpoint(checkpoint)
        else:
            print("❌ Animation failed — not marking as complete")
    else:
        print("✅ Skipping animation (already completed)")

    print(f"\n✅ Pipeline complete. Results in: {args.output}")

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full BFF grammar mining pipeline")

    # Grammar generation parameters
    parser.add_argument("--grammar-start", type=int, default=0)
    parser.add_argument("--grammar-stop", type=int, default=4096)
    parser.add_argument("--grammar-step", type=int, default=256)
    parser.add_argument("--minfreq", type=int, default=100)
    parser.add_argument("--minlen", type=int, default=2)
    parser.add_argument("--maxlen", type=int, default=8)

    # Rewrite/count parameters
    parser.add_argument("--usage-start", type=int, default=0)
    parser.add_argument("--usage-stop", type=int, default=4096)
    parser.add_argument("--max-programs", type=int, default=5000)

    # I/O paths
    parser.add_argument("--soup-dir", default="runs/20250531-4096E-128xSoup")
    parser.add_argument("--grammar-dir", default="bff_grammar_package/output/grammars")
    parser.add_argument("--output", default="bff_grammar_package/output")

    # Animation
    parser.add_argument("--fps", type=int, default=5)

    args = parser.parse_args()
    run_pipeline(args)
