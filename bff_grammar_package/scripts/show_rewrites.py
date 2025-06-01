# bff_grammar_package/scripts/show_rewrites.py

import os
import json
import argparse
from bff_grammar_package.grammar_core.io import load_soup, to_symbol_sequences

def load_grammar(grammar_dir, target_epoch, step):
    while target_epoch >= 0:
        path = os.path.join(grammar_dir, f"grammar_{target_epoch:04}.json")
        if os.path.exists(path):
            with open(path) as f:
                return json.load(f)["rules"]
        target_epoch -= step
    return {}

def rewrite_sequence(seq, sorted_rules):
    i = 0
    out = []
    while i < len(seq):
        matched = False
        for sym, rhs in sorted_rules:
            ln = len(rhs)
            if seq[i:i+ln] == rhs:
                out.append(sym)
                i += ln
                matched = True
                break
        if not matched:
            out.append(seq[i])
            i += 1
    return out

def main():
    parser = argparse.ArgumentParser(description="Show rewrites of programs using grammar rules")
    parser.add_argument("--epoch", type=int, required=True, help="Epoch to pull soup and grammar from")
    parser.add_argument("--soup-dir", type=str, required=True)
    parser.add_argument("--grammar-dir", type=str, required=True)
    parser.add_argument("--step", type=int, default=256)
    parser.add_argument("--count", type=int, default=10, help="Number of programs to display")
    args = parser.parse_args()

    soup_file = os.path.join(args.soup_dir, f"{args.epoch:010}.dat")
    if not os.path.exists(soup_file):
        print(f"❌ Soup file not found: {soup_file}")
        return

    print(f"📦 Loading soup from {soup_file}")
    soup = load_soup(soup_file, max_programs=args.count)
    sequences = to_symbol_sequences(soup, normalize_noops=True)

    print(f"📜 Loaded {len(sequences)} programs")

    grammar = load_grammar(args.grammar_dir, args.epoch, args.step)
    sorted_rules = sorted(grammar.items(), key=lambda kv: -len(kv[1]))

    print(f"📘 Using grammar with {len(grammar)} rules (nearest <= {args.epoch})")

    print("\n🔍 Showing rewrites:\n")
    for i, seq in enumerate(sequences[:args.count]):
        rewritten = rewrite_sequence(seq, sorted_rules)
        print(f"[Program {i+1}]")
        print("  Original: ", " ".join(seq))
        print("  Rewritten:", " ".join(rewritten))
        print()

if __name__ == "__main__":
    main()
