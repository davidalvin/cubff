import os
import json
import argparse
from collections import Counter, OrderedDict
from bff_grammar_package.grammar_core.io import load_soup, to_symbol_sequences
from bff_grammar_package.grammar_core.grammar import rewrite_with_grammar
from multiprocessing import Pool, cpu_count

# === LOAD GRAMMARS ONCE (for reuse by worker processes) ===
grammar_by_epoch = {}
sorted_grammar_rules = {}

def load_grammars(grammar_dir, grammar_epochs):
    print("\U0001F4DA Loading grammars...")
    for epoch in grammar_epochs:
        path = os.path.join(grammar_dir, f"grammar_{epoch:04}.json")
        with open(path) as f:
            rules = json.load(f)["rules"]
            grammar_by_epoch[epoch] = rules
            sorted_grammar_rules[epoch] = sorted(rules.items(), key=lambda kv: -len(kv[1]))
        print(f"✅ Grammar {epoch} loaded with {len(rules)} rules")

    return grammar_by_epoch, sorted_grammar_rules

def nearest_grammar(epoch: int, grammar_epochs, grammar_by_epoch, sorted_grammar_rules) -> tuple[dict, list[tuple[str, list[str]]]]:
    nearest = min(grammar_epochs, key=lambda e: abs(e - epoch))
    return grammar_by_epoch[nearest], sorted_grammar_rules[nearest]

def process_epoch(epoch: int, soup_dir, max_programs, grammar_epochs) -> dict:
    path = os.path.join(soup_dir, f"{epoch:010}.dat")
    if not os.path.exists(path):
        print(f"⚠️ Skipping missing file: {path}")
        return {}

    print(f"🔄 Processing epoch {epoch}")
    raw = load_soup(path, max_programs=max_programs)
    seqs = to_symbol_sequences(raw, normalize_noops=True)

    grammar, rules = nearest_grammar(epoch, grammar_epochs, grammar_by_epoch, sorted_grammar_rules)

    rewritten = []
    for prog in seqs:
        i = 0
        out = []
        while i < len(prog):
            matched = False
            for sym, rhs in rules:
                ln = len(rhs)
                if prog[i:i+ln] == rhs:
                    out.append(sym)
                    i += ln
                    matched = True
                    break
            if not matched:
                out.append(prog[i])
                i += 1
        rewritten.append(out)

    usage = Counter(sym for prog in rewritten for sym in prog if sym in grammar)
    print(f"✅ Epoch {epoch} done — {len(usage)} rules used")
    return dict(usage)

# === MAIN EXECUTION ===
if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rewrite programs using grammar and count rule usage")
    parser.add_argument("--grammar-epochs", nargs="*", type=int, default=[30, 60, 90], help="Epochs for which grammars exist")
    parser.add_argument("--soup-dir", type=str, default="runs/test_grammar_100", help="Directory containing soup .dat files")
    parser.add_argument("--grammar-dir", type=str, default="bff_grammar_package/output/grammars", help="Directory containing grammar JSONs")
    parser.add_argument("--output-file", type=str, default="bff_grammar_package/output/rule_usage_over_time.json", help="Path to save usage data JSON")
    parser.add_argument("--start", type=int, default=1, help="Start epoch for rewriting")
    parser.add_argument("--stop", type=int, default=100, help="Stop epoch for rewriting")
    parser.add_argument("--max-programs", type=int, default=5000, help="Max programs per soup file")

    args = parser.parse_args()

    grammar_by_epoch, sorted_grammar_rules = load_grammars(args.grammar_dir, args.grammar_epochs)

    print(f"\n🚀 Starting parallel processing with {cpu_count()} CPUs")
    epochs = list(range(args.start, args.stop + 1))

    with Pool(processes=cpu_count()) as pool:
        results = pool.starmap(process_epoch, [(epoch, args.soup_dir, args.max_programs, args.grammar_epochs) for epoch in epochs])

    print(f"\n💾 Writing results to {args.output_file}")
    with open(args.output_file, "w") as f:
        json.dump(results, f)
