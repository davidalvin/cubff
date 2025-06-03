import os
import json
import argparse
from collections import Counter
from bff_grammar_package.grammar_core.io import load_soup, to_symbol_sequences
from multiprocessing import Pool, cpu_count

CHECKPOINT_FILE = "bff_grammar_package/output/rewrite_checkpoint_unique.json"

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

def nearest_grammar(epoch, grammar_epochs):
    nearest = min(grammar_epochs, key=lambda e: abs(e - epoch))
    return grammar_by_epoch[nearest], sorted_grammar_rules[nearest]

def process_epoch(epoch, soup_dir, max_programs, grammar_epochs):
    path = os.path.join(soup_dir, f"{epoch:010}.dat")
    if not os.path.exists(path):
        print(f"⚠️ Skipping missing file: {path}")
        return epoch, {}

    print(f"🔄 Processing epoch {epoch}")
    raw = load_soup(path, max_programs=max_programs)
    seqs = to_symbol_sequences(raw, normalize_noops=True)

    grammar, rules = nearest_grammar(epoch, grammar_epochs)

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

    usage = Counter()
    for prog in rewritten:
        seen = set(sym for sym in prog if sym in grammar)
        usage.update(seen)

    print(f"✅ Epoch {epoch} done — {len(usage)} rules used")
    return epoch, dict(usage)

def load_checkpoint():
    if os.path.exists(CHECKPOINT_FILE):
        with open(CHECKPOINT_FILE) as f:
            return json.load(f)
    return {}

def save_checkpoint(data):
    with open(CHECKPOINT_FILE, "w") as f:
        json.dump(data, f, indent=2)

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Rewrite programs using grammar and count rule usage (unique per program)")
    parser.add_argument("--grammar-epochs", nargs="*", type=int, default=[0, 256, 512], help="Epochs for which grammars exist")
    parser.add_argument("--soup-dir", type=str, help="Directory containing soup .dat files")
    parser.add_argument("--grammar-dir", type=str, help="Directory containing grammar JSONs")
    parser.add_argument("--output-file", type=str, help="Path to save usage data JSON")
    parser.add_argument("--start", type=int, help="Start epoch for rewriting")
    parser.add_argument("--stop", type=int, help="Stop epoch for rewriting")
    parser.add_argument("--max-programs", type=int, default=5000, help="Max programs per soup file")

    args = parser.parse_args()

    checkpoint_data = load_checkpoint()
    load_grammars(args.grammar_dir, args.grammar_epochs)
    epochs = list(range(args.start, args.stop + 1, 32))
    completed = set(checkpoint_data.get("completed_epochs", []))
    pending = [e for e in epochs if e not in completed]

    results = checkpoint_data.get("results", {})

    print(f"\n🚀 Starting parallel processing for {len(pending)} epochs using {cpu_count()} CPUs")
    with Pool(processes=cpu_count()) as pool:
        for epoch, usage in pool.starmap(process_epoch, [(e, args.soup_dir, args.max_programs, args.grammar_epochs) for e in pending]):
            results[str(epoch)] = usage
            completed.add(epoch)
            save_checkpoint({"completed_epochs": sorted(completed), "results": results})

    print(f"\n💾 Writing final results to {args.output_file}")
    with open(args.output_file, "w") as f:
        json.dump(results, f, indent=2)
