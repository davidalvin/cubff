import argparse
import subprocess
import os

def run_pipeline(args):
    os.makedirs(args.output, exist_ok=True)
    os.makedirs(args.grammar_dir, exist_ok=True)

    grammar_epochs = list(range(args.grammar_start, args.grammar_stop, args.grammar_step))

    print("🚀 Step 1: Building grammar across selected epochs...")
    subprocess.run([
        "python", "-m", "bff_grammar_package.scripts.build_grammar",
        "--start", str(args.grammar_start),
        "--stop", str(args.grammar_stop),
        "--step", str(args.grammar_step),
        "--minfreq", str(args.minfreq),
        "--minlen", str(args.minlen),
        "--maxlen", str(args.maxlen),
        "--input-dir", args.soup_dir,
        "--output-dir", args.grammar_dir
    ])

  
    grammar_epochs = list(range(args.grammar_start, args.grammar_stop, args.grammar_step))

    # Update subprocess for rewrite_and_count:
    subprocess.run([
        "python", "-m", "bff_grammar_package.scripts.rewrite_and_count",
        "--start", str(args.usage_start),
        "--stop", str(args.usage_stop),
        "--max-programs", str(args.max_programs),
        "--grammar-dir", "bff_grammar_package/output/grammars",
        "--grammar-epochs", *map(str, grammar_epochs),
        "--soup-dir", "runs/test_grammar_100",
        "--output-file", "bff_grammar_package/output/rule_usage_over_time.json"
    ])


    print("\n📊 Step 3: Generating animated GIF of rule usage...")
    subprocess.run([
        "python", "-m", "bff_grammar_package.scripts.animate_usage",
        "--input", os.path.join(args.output, "rule_usage_over_time.json"),
        "--output", os.path.join(args.output, "rule_usage_over_time.gif"),
        "--fps", str(args.fps)
    ])

    print("\n✅ Pipeline complete. Results in:", args.output)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Run full BFF grammar mining pipeline")

    # Grammar generation parameters
    parser.add_argument("--grammar-start", type=int, default=30)
    parser.add_argument("--grammar-stop", type=int, default=91)
    parser.add_argument("--grammar-step", type=int, default=30)
    parser.add_argument("--minfreq", type=int, default=500)
    parser.add_argument("--minlen", type=int, default=2)
    parser.add_argument("--maxlen", type=int, default=8)

    # Rewrite/count parameters
    parser.add_argument("--usage-start", type=int, default=1)
    parser.add_argument("--usage-stop", type=int, default=100)
    parser.add_argument("--max-programs", type=int, default=5000)

    # I/O paths
    parser.add_argument("--soup-dir", default="runs/test_grammar_100")
    parser.add_argument("--grammar-dir", default="bff_grammar_package/output/grammars")
    parser.add_argument("--output", default="bff_grammar_package/output")

    # Animation
    parser.add_argument("--fps", type=int, default=5)

    args = parser.parse_args()
    run_pipeline(args)
